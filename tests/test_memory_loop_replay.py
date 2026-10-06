"""Tests for recall before and after cumulative curation rounds."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models.test import TestModel

from apps.backend.schemas import ChatRequest, ChatResponse
from evals.synthetic_journals.models import (
    CurationRecallLoop,
    GroundTruthProposal,
    Prop,
    PropEvidence,
    PropLifecycle,
    PropRelevanceJudgment,
    ProposedGroundTruth,
    SyntheticBackstory,
)
from evals.synthetic_journals.replay_support import (
    MEMORY_LOOP_RUN_CONFIGURATION_ID,
    replay_support_for,
)
from evals.synthetic_journals.scenario_catalog import inspect_scenario
from evals.synthetic_journals.scenario_diagnostics import (
    recorded_execution_diagnostics,
    summarize_artifact,
)
from evals.synthetic_journals.validate_scenario import (
    DEFAULT_RUN_CONFIGURATION_DIRECTORY,
    ScenarioValidationError,
    load_run_configurations,
    validate_scenario,
    validate_scenario_files,
)
from src.linger.agents.provenance.curation_models import CurationProvenanceReview
from src.linger.agents.sculptor.models import CurationProposal
from src.linger.contracts.connection_evidence import MemoryConnectionEvidence
from src.linger.evaluation_transcript import (
    ConnectionEvaluationEvent,
    record_connection_event,
)
from src.linger.services.memory import AccountContext, MemoryPolicyService
from tests.test_synthetic_journal_continuity_replay import (
    BACKSTORY_ID,
    _adoption,
    _append,
    _backstory,
    _ground_truth,
    _line,
    _released_response,
    _scene,
)

with patch("src.linger.agents.build.build_model", return_value=TestModel()):
    from evals.synthetic_journals import memory_loop_replay
    from evals.synthetic_journals.memory_loop_replay import (
        DerivedCitation,
        ResolvedEvidence,
        grade_recall_evidence,
        main as memory_loop_main,
        replay_memory_loop,
    )

OBJECTIVE_ID = "longitudinal_memory_retrieval"
ROOT = Path(__file__).resolve().parents[1]
SAVED_SCENARIO = (
    ROOT
    / "synthetic-journal-evaluation"
    / "scenarios"
    / "supper-club-curation-then-recall--muse-serendipity-sculptor-provenance--2026-09-30"
)
PROPS = {
    "prop-old": "I host on Thursdays.",
    "prop-new": "Hosting moved to Tuesdays.",
    "prop-copy-a": "People remember who they sat beside.",
    "prop-copy-b": "People remember who they sat beside.",
    "prop-other": "I borrow chairs every week.",
}
NIGHT_SCENE, NIGHT_LINE = "scene-night", "Which night do I host, and was it different?"
NONE_SCENE, NONE_LINE = "scene-none", "Should I start charging?"
SETTINGS = CurationRecallLoop(curation_rounds=3, repetitions=2)
RECORDED_AT = {
    prop_id: datetime(2026, month, 1, 20, tzinfo=UTC)
    for month, prop_id in enumerate(PROPS, start=2)
}


def _scenario(
    *,
    run_configuration_ids: tuple[str, ...] = (MEMORY_LOOP_RUN_CONFIGURATION_ID,),
    night_relevant: tuple[str, ...] = ("prop-old", "prop-new"),
    none_prop_ids: tuple[str, ...] = tuple(PROPS),
) -> tuple[SyntheticBackstory, ProposedGroundTruth]:
    scene_props = {NIGHT_SCENE: tuple(PROPS), NONE_SCENE: none_prop_ids}
    backstory = _backstory(
        scenes=tuple(
            _scene(
                scene_id,
                order,
                (f"line-{scene_id}",),
                objective_ids=(OBJECTIVE_ID,),
                prop_ids=scene_props[scene_id],
            )
            for order, scene_id in enumerate((NIGHT_SCENE, NONE_SCENE), start=1)
        ),
        lines=(
            _line(f"line-{NIGHT_SCENE}", NIGHT_SCENE, 1, NIGHT_LINE),
            _line(f"line-{NONE_SCENE}", NONE_SCENE, 1, NONE_LINE),
        ),
        objective_ids=(OBJECTIVE_ID,),
        run_configuration_ids=run_configuration_ids,
        props=tuple(
            Prop(
                prop_id=prop_id,
                backstory_id=BACKSTORY_ID,
                person_id="person-continuity",
                evaluation_account_id="account-continuity",
                source_text=text,
                recorded_at=RECORDED_AT[prop_id],
                lifecycle=tuple(
                    PropLifecycle(scene_id=scene_id, state="active")
                    for scene_id, prop_ids in scene_props.items()
                    if prop_id in prop_ids
                ),
            )
            for prop_id, text in PROPS.items()
        ),
    )
    relevant = {NIGHT_SCENE: night_relevant, NONE_SCENE: ()}
    ground_truth = _ground_truth(
        backstory,
        tuple(
            GroundTruthProposal(
                proposal_id=f"proposal-{scene_id}",
                scene_id=scene_id,
                objective_id=OBJECTIVE_ID,
                expected_outcomes=("Recall follows the proposed relevance.",),
                prohibited_outcomes=("A distractor is presented as support.",),
                evidence=tuple(
                    PropEvidence(
                        kind="prop",
                        evidence_id=f"evidence-{scene_id}-{prop_id}",
                        prop_id=prop_id,
                    )
                    for prop_id in relevant[scene_id]
                ),
                prop_relevance=tuple(
                    PropRelevanceJudgment(
                        prop_id=prop_id,
                        relevance=(
                            "relevant"
                            if prop_id in relevant[scene_id]
                            else "distractor"
                        ),
                    )
                    for prop_id in scene_props[scene_id]
                ),
            )
            for scene_id in (NIGHT_SCENE, NONE_SCENE)
        ),
    )
    return backstory, ground_truth


def _validate(backstory: SyntheticBackstory, ground_truth: ProposedGroundTruth) -> None:
    validate_scenario(
        backstory,
        ground_truth,
        backstory_bytes=backstory.model_dump_json().encode("utf-8"),
        run_configurations={
            MEMORY_LOOP_RUN_CONFIGURATION_ID: load_run_configurations(
                DEFAULT_RUN_CONFIGURATION_DIRECTORY
            )[MEMORY_LOOP_RUN_CONFIGURATION_ID].model_copy(update={"scene_count": 2})
        },
    )


def _sculptor(prompts: list[dict]) -> AsyncMock:
    """Link the copies, hide one, then summarise the night, reading prior state."""

    agent = AsyncMock()

    async def run(prompt: str, **_kwargs: object) -> SimpleNamespace:
        payload = json.loads(prompt)
        prompts.append(payload)
        ids = {item["text"]: item["memory_id"] for item in payload["memories"]}
        copies = [
            item["memory_id"]
            for item in payload["memories"]
            if item["text"] == PROPS["prop-copy-a"]
        ]
        existing = payload.get("existing_curation", {})
        if not existing.get("duplicate_links"):
            action: dict = {"action": "link_duplicates", "source_memory_ids": copies}
        elif not existing.get("tombstones"):
            action = {
                "action": "tombstone_for_retrieval",
                "source_memory_ids": copies,
                "memory_id": copies[1],
                "canonical_memory_id": copies[0],
            }
        else:
            action = {
                "action": "update_derived_summary",
                "source_memory_ids": [
                    ids[PROPS["prop-old"]],
                    ids[PROPS["prop-new"]],
                ],
                "summary": "Hosting moved from Thursdays to Tuesdays.",
            }
        return SimpleNamespace(
            output=CurationProposal.model_validate(
                {"kind": "curation_proposal", "action": action}
            ),
            new_messages=lambda: (),
        )

    agent.run.side_effect = run
    return agent


def _provenance(decision: str = "allow") -> AsyncMock:
    agent = AsyncMock()

    async def run(prompt: str, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            output=CurationProvenanceReview(
                proposal_digest=json.loads(prompt)["proposal_digest"],
                decision=decision,
                findings=()
                if decision == "allow"
                else (
                    {
                        "code": "incorrect_duplicate",
                        "source_memory_ids": (
                            json.loads(prompt)["sources"][0]["memory_id"],
                        ),
                        "explanation": "Not the same memory.",
                    },
                ),
            ),
            new_messages=lambda: (),
        )

    agent.run.side_effect = run
    return agent


async def _recall_handler(
    request: ChatRequest,
    service: MemoryPolicyService,
    account: AccountContext,
) -> ChatResponse:
    """Cite the night summary when it exists, otherwise both night originals."""

    view = service.list_for_retrieval(account)
    night_texts = {PROPS["prop-old"], PROPS["prop-new"]}
    summaries = [item for item in view if item.kind == "derived_summary"]
    wanted = (
        []
        if request.message != NIGHT_LINE
        else summaries or [item for item in view if item.text in night_texts]
    )
    record_connection_event(
        ConnectionEvaluationEvent(
            kind="search",
            status="evidence_found" if wanted else "no_evidence",
            source="memory",
            operation="search_memories",
            evidence_json=tuple(
                MemoryConnectionEvidence(
                    evidence_id=item.memory_id, excerpt=item.text
                ).model_dump_json()
                for item in wanted
            ),
        )
    )
    record_connection_event(
        ConnectionEvaluationEvent(
            kind="release",
            status="released",
            release_source="muse_candidate",
            released_evidence_ids=tuple(item.memory_id for item in wanted),
        )
    )
    response = _released_response()
    _append(request, response)
    return response


def _run(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    **kwargs: object,
) -> memory_loop_replay.MemoryLoopRun:
    kwargs.setdefault("chat_handler", _recall_handler)
    kwargs.setdefault("provenance", _provenance())
    kwargs.setdefault("settings", SETTINGS)
    return asyncio.run(replay_memory_loop(backstory, ground_truth, **kwargs))  # type: ignore[arg-type]


def test_each_round_builds_on_earlier_curation_and_each_repetition_starts_clean() -> None:
    backstory, ground_truth = _scenario()
    _validate(backstory, ground_truth)
    prompts: list[dict] = []

    result = _run(backstory, ground_truth, sculptor=_sculptor(prompts))

    assert [(item.repetition, item.round, item.status, item.action) for item in result.curation] == [
        (repetition, round_number, "applied", action)
        for repetition in (1, 2)
        for round_number, action in enumerate(
            ("link_duplicates", "tombstone_for_retrieval", "update_derived_summary"),
            start=1,
        )
    ]
    assert result.curation[0].source_prop_ids == ("prop-copy-a", "prop-copy-b")
    first, second, third = prompts[:3]
    assert [
        datetime.fromisoformat(memory["recorded_at"]) for memory in first["memories"]
    ] == [RECORDED_AT[prop_id] for prop_id in PROPS]
    assert "existing_curation" not in first
    assert len(second["existing_curation"]["duplicate_links"]) == 2
    assert second["existing_curation"]["tombstones"] == []
    assert len(third["existing_curation"]["tombstones"]) == 1
    assert "existing_curation" not in prompts[3]
    serialized = json.dumps(prompts)
    assert NIGHT_LINE not in serialized
    assert NONE_LINE not in serialized
    assert "relevant" not in serialized


def test_recall_is_graded_the_same_way_before_and_after_curation() -> None:
    backstory, ground_truth = _scenario()
    result = _run(backstory, ground_truth, sculptor=_sculptor([]))

    night, none = result.scenes
    assert [(grade.repetition, grade.curation_rounds) for grade in night.grades] == [
        (repetition, rounds) for repetition in (1, 2) for rounds in range(4)
    ]
    assert all(grade.hard_failures == () for grade in (*night.grades, *none.grades))
    raw, _, _, summarised = night.grades[:4]
    assert raw.cited_prop_ids == ("prop-old", "prop-new")
    assert raw.cited_derived == ()
    assert summarised.cited_prop_ids == ()
    assert summarised.cited_derived == (
        DerivedCitation(
            kind="derived_summary",
            text="Hosting moved from Thursdays to Tuesdays.",
            source_prop_ids=("prop-old", "prop-new"),
        ),
    )
    hidden = [
        item for item in result.curation[1].retrieval_view if item.kind == "original"
    ]
    assert ("prop-copy-b",) not in [item.source_prop_ids for item in hidden]
    assert [(item.scene_id, item.curation_rounds, item.passed) for item in result.comparison] == [
        (scene_id, rounds, 2)
        for scene_id in (NIGHT_SCENE, NONE_SCENE)
        for rounds in range(4)
    ]
    assert result.ground_truth_status == "proposed"
    assert result.capture_enabled is False
    summary = summarize_artifact(result.model_dump(mode="json"))
    assert summary["scenes_passed"] == 2
    assert summary["judgments_total"] == 16


def test_rejected_and_failed_rounds_are_reported_and_recall_still_runs() -> None:
    backstory, ground_truth = _scenario()
    rejected = _run(
        backstory,
        ground_truth,
        sculptor=_sculptor([]),
        provenance=_provenance("reject"),
    )
    failing = AsyncMock()
    failing.run.side_effect = UnexpectedModelBehavior("provider unavailable")
    failed = _run(backstory, ground_truth, sculptor=failing)

    assert {item.status for item in rejected.curation} == {"provenance_reject"}
    assert {item.provenance_decision for item in rejected.curation} == {"reject"}
    assert {item.status for item in failed.curation} == {"failed"}
    assert all(item.failure for item in failed.curation)
    for result in (rejected, failed):
        assert all(len(scene.grades) == 8 for scene in result.scenes)
        assert all(
            len(item.retrieval_view) == len(PROPS) for item in result.curation
        )


def test_adopted_ground_truth_is_graded_with_hard_gates() -> None:
    backstory, ground_truth = _scenario()
    adoption = _adoption(ground_truth)

    result = _run(
        backstory,
        ground_truth,
        sculptor=_sculptor([]),
        adoption=adoption,
        settings=CurationRecallLoop(curation_rounds=1, repetitions=1),
    )

    assert result.ground_truth_status == "adopted"
    assert result.dataset_version == adoption.adopted_ground_truth_identity
    assert {
        grade.ground_truth_result
        for scene in result.scenes
        for grade in scene.grades
    } == {"passes_hard_gates"}


def _evidence(
    direct: tuple[str, ...] = (),
    derived: tuple[tuple[str, ...], ...] = (),
    unknown: tuple[str, ...] = (),
) -> ResolvedEvidence:
    return ResolvedEvidence(
        direct_prop_ids=direct,
        derived=tuple(
            DerivedCitation(kind="derived_summary", text="Summary.", source_prop_ids=ids)
            for ids in derived
        ),
        unknown_ids=unknown,
    )


@pytest.mark.parametrize(
    ("cited", "canonical_of", "expected"),
    [
        (_evidence(direct=("a", "b")), {}, ()),
        (_evidence(derived=(("a", "b"),)), {}, ()),
        (_evidence(direct=("a",)), {}, ("relevant_prop_not_retrieved", "relevant_prop_not_cited")),
        (_evidence(direct=("a", "b", "x")), {}, ("distractor_prop_cited",)),
        (_evidence(direct=("a", "b"), derived=(("x", "y"),)), {}, ("distractor_prop_cited",)),
        (_evidence(derived=(("a", "b", "x"),)), {}, ("distractor_prop_cited",)),
        (_evidence(direct=("a", "x")), {"b": "x"}, ()),
        (_evidence(direct=("a", "y")), {"b": "x", "x": "y"}, ()),
        (_evidence(derived=(("a", "x"),)), {"b": "x"}, ()),
        (_evidence(direct=("a", "x")), {"b": "x", "x": "b"}, ()),
        (_evidence(direct=("a", "b"), unknown=("gone",)), {}, ("unknown_evidence_cited",)),
    ],
)
def test_evidence_grading_counts_summaries_and_canonical_duplicates(
    cited: ResolvedEvidence,
    canonical_of: dict[str, str],
    expected: tuple[str, ...],
) -> None:
    assert (
        grade_recall_evidence(
            relevant_prop_ids=("a", "b"),
            distractor_prop_ids=("x", "y"),
            retrieved=cited,
            cited=cited,
            canonical_of=canonical_of,
        )
        == expected
    )


def test_comparison_scene_fails_when_any_record_is_cited() -> None:
    assert grade_recall_evidence(
        relevant_prop_ids=(),
        distractor_prop_ids=("x", "y"),
        retrieved=_evidence(direct=("x",)),
        cited=_evidence(derived=(("x", "y"),)),
        canonical_of={},
    ) == ("distractor_prop_cited",)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"night_relevant": ()}, "a Scene with a relevant Prop and a Scene with none"),
        ({"none_prop_ids": tuple(PROPS)[:4]}, "share one Prop bank"),
    ],
)
def test_validator_rejects_a_scenario_the_loop_cannot_compare(
    overrides: dict, message: str
) -> None:
    backstory, ground_truth = _scenario(**overrides)

    with pytest.raises(ScenarioValidationError, match=message):
        _validate(backstory, ground_truth)


def test_scenes_may_list_the_shared_prop_bank_in_any_order() -> None:
    backstory, ground_truth = _scenario(none_prop_ids=tuple(reversed(PROPS)))
    _validate(backstory, ground_truth)

    result = _run(
        backstory,
        ground_truth,
        sculptor=_sculptor([]),
        settings=CurationRecallLoop(curation_rounds=1, repetitions=1),
    )

    assert all(grade.hard_failures == () for scene in result.scenes for grade in scene.grades)


def test_failed_exchanges_inside_grades_reach_execution_diagnostics() -> None:
    failed = {
        "role": "Serendipity",
        "stage": "memory_recall",
        "status": "failed",
        "failure_code": "serendipity_model_failed",
        "failure_category": "provider_error",
        "provider_error_kind": "http",
        "provider_status_code": 429,
    }
    scene = {
        "scene_id": NIGHT_SCENE,
        "grades": [
            {"hard_failures": []},
            {"hard_failures": ["discovery_failure"], "agent_exchanges": [failed]},
        ],
    }

    (diagnostic,) = recorded_execution_diagnostics(scene, 0)
    summary = summarize_artifact({"scenes": [scene]})

    assert diagnostic["category"] == "provider_http_error"
    assert diagnostic["evidence_refs"] == [
        "artifact.scenes[0].grades[1].agent_exchanges[0]"
    ]
    assert {
        "scene_id": NIGHT_SCENE,
        "detail": "Serendipity memory_recall: serendipity_model_failed",
    } in summary["execution_failures"]


def test_prop_recording_time_requires_a_timezone() -> None:
    backstory, _ = _scenario()
    prop = backstory.props[0].model_dump()
    prop["recorded_at"] = datetime(2026, 2, 1, 20)

    with pytest.raises(ValueError, match="recorded_at must include a timezone"):
        Prop.model_validate(prop)


def test_runner_requires_the_loop_run_configuration() -> None:
    backstory, ground_truth = _scenario(run_configuration_ids=())

    with pytest.raises(ValueError, match=MEMORY_LOOP_RUN_CONFIGURATION_ID):
        _run(backstory, ground_truth, sculptor=_sculptor([]))


def test_dispatch_selects_the_loop_only_for_its_run_configuration() -> None:
    loop = replay_support_for((OBJECTIVE_ID,), (MEMORY_LOOP_RUN_CONFIGURATION_ID,))
    plain = replay_support_for((OBJECTIVE_ID,))

    assert loop is not None and plain is not None
    assert loop.module == "evals.synthetic_journals.memory_loop_replay"
    assert plain.module == "evals.synthetic_journals.retrieval_replay"
    assert (
        replay_support_for(
            (OBJECTIVE_ID, "session_scoped_conversation_continuity"),
            (MEMORY_LOOP_RUN_CONFIGURATION_ID,),
        )
        is None
    )


def test_saved_scenario_validates_and_is_offered_the_loop_runner() -> None:
    backstory, ground_truth = validate_scenario_files(
        SAVED_SCENARIO / "backstory.json", SAVED_SCENARIO / "ground-truth.json"
    )

    assert backstory.run_configuration_ids == (MEMORY_LOOP_RUN_CONFIGURATION_ID,)
    assert len(ground_truth.proposals) == 5
    assert (
        inspect_scenario(SAVED_SCENARIO, ROOT)["runner"]
        == "evals.synthetic_journals.memory_loop_replay"
    )


def test_cli_reports_an_invalid_scenario(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    backstory, ground_truth = _scenario()
    backstory_path = tmp_path / "backstory.json"
    ground_truth_path = tmp_path / "ground-truth.json"
    backstory_path.write_text(backstory.model_dump_json(), encoding="utf-8")
    ground_truth_path.write_text(
        ground_truth.model_copy(update={"backstory_sha256": "0" * 64}).model_dump_json(),
        encoding="utf-8",
    )

    assert memory_loop_main([str(backstory_path), str(ground_truth_path)]) == 1
    assert "EVALUATION_RUN_ERROR=" in capsys.readouterr().err
