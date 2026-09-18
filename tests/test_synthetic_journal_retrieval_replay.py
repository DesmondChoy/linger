"""Tests for longitudinal-retrieval Scene replay, alone and with continuity."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from apps.backend.schemas import ChatRequest, ChatResponse
from evals.synthetic_journals import retrieval_replay
from evals.synthetic_journals.continuity_replay import CONTINUITY_OBJECTIVE_ID
from evals.synthetic_journals.models import (
    GroundTruthProposal,
    OfflineInput,
    Prop,
    PropEvidence,
    PropLifecycle,
    PropRelevanceJudgment,
    ProposedGroundTruth,
    Scene,
    SyntheticBackstory,
)
from evals.synthetic_journals.replay_support import replay_support_for
from evals.synthetic_journals.retrieval_replay import (
    RETRIEVAL_OBJECTIVE_ID,
    RETRIEVAL_RUN_CONFIGURATION_ID,
    RetrievalSceneObservation,
    main as retrieval_main,
    replay_retrieval_scenes,
)
from evals.synthetic_journals.validate_scenario import (
    DEFAULT_RUN_CONFIGURATION_DIRECTORY,
    load_run_configurations,
    validate_scenario,
)
from src.linger.contracts.connection_evidence import MemoryConnectionEvidence
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.contracts.turn import ReleaseSource
from src.linger.evaluation_transcript import (
    ConnectionEvaluationEvent,
    record_connection_event,
)
from src.linger.services.memory import AccountContext, MemoryPolicyService
from tests.test_synthetic_journal_continuity_replay import (
    BACKSTORY_ID,
    COMPARISON_SCENE_ID,
    COMPARISON_TEXT,
    CONTINUITY_SCENE_ID,
    CONTINUITY_TEXTS,
    _adoption,
    _append,
    _backstory,
    _dummy_handler,
    _ground_truth,
    _line,
    _pairing,
    _proposal,
    _released_response,
    _scene,
)

PERSON_ID = "person-continuity"
ACCOUNT_ID = "account-continuity"
TARGET_SCENE_ID = "scene-retrieval-target"
RETRIEVAL_COMPARISON_SCENE_ID = "scene-retrieval-comparison"
TARGET_LINE_ID = "line-retrieval-target"
COMPARISON_LINE_ID = "line-retrieval-comparison"
TARGET_TEXT = "I keep returning to the same difficult decision."
COMPARISON_RETRIEVAL_TEXT = (
    "I have a nearby question that my earlier memories do not answer."
)
PROP_IDS = tuple(f"prop-{index:02d}" for index in range(1, 12))
RELEVANT_PROP_ID = PROP_IDS[0]
DISTRACTOR_PROP_IDS = PROP_IDS[1:]


def _prop_text(prop_id: str) -> str:
    return f"A plausible prior memory recorded as {prop_id}."


def _props(scene_ids: tuple[str, ...]) -> tuple[Prop, ...]:
    return tuple(
        Prop(
            prop_id=prop_id,
            backstory_id=BACKSTORY_ID,
            person_id=PERSON_ID,
            evaluation_account_id=ACCOUNT_ID,
            source_text=_prop_text(prop_id),
            lifecycle=tuple(
                PropLifecycle(scene_id=scene_id, state="active")
                for scene_id in scene_ids
            ),
        )
        for prop_id in PROP_IDS
    )


def _retrieval_scene(scene_id: str, order: int, line_id: str) -> Scene:
    return _scene(
        scene_id,
        order,
        (line_id,),
        objective_ids=(RETRIEVAL_OBJECTIVE_ID,),
        prop_ids=PROP_IDS,
    )


def _retrieval_lines() -> tuple:
    return (
        _line(TARGET_LINE_ID, TARGET_SCENE_ID, 1, TARGET_TEXT),
        _line(
            COMPARISON_LINE_ID,
            RETRIEVAL_COMPARISON_SCENE_ID,
            1,
            COMPARISON_RETRIEVAL_TEXT,
        ),
    )


def _retrieval_proposal(scene_id: str, relevant: tuple[str, ...]) -> GroundTruthProposal:
    return GroundTruthProposal(
        proposal_id=f"proposal-{scene_id}",
        scene_id=scene_id,
        objective_id=RETRIEVAL_OBJECTIVE_ID,
        expected_outcomes=("Retrieval follows the proposed relevance.",),
        prohibited_outcomes=("A distractor is presented as support.",),
        evidence=tuple(
            PropEvidence(
                kind="prop",
                evidence_id=f"evidence-{scene_id}-{prop_id}",
                prop_id=prop_id,
            )
            for prop_id in relevant
        ),
        prop_relevance=tuple(
            PropRelevanceJudgment(
                prop_id=prop_id,
                relevance="relevant" if prop_id in relevant else "distractor",
            )
            for prop_id in PROP_IDS
        ),
    )


def _retrieval_scenario() -> tuple[SyntheticBackstory, ProposedGroundTruth]:
    scene_ids = (TARGET_SCENE_ID, RETRIEVAL_COMPARISON_SCENE_ID)
    backstory = _backstory(
        scenes=(
            _retrieval_scene(TARGET_SCENE_ID, 1, TARGET_LINE_ID),
            _retrieval_scene(RETRIEVAL_COMPARISON_SCENE_ID, 2, COMPARISON_LINE_ID),
        ),
        lines=_retrieval_lines(),
        objective_ids=(RETRIEVAL_OBJECTIVE_ID,),
        run_configuration_ids=(RETRIEVAL_RUN_CONFIGURATION_ID,),
        props=_props(scene_ids),
    )
    ground_truth = _ground_truth(
        backstory,
        (
            _retrieval_proposal(TARGET_SCENE_ID, (RELEVANT_PROP_ID,)),
            _retrieval_proposal(RETRIEVAL_COMPARISON_SCENE_ID, ()),
        ),
    )
    _validate(backstory, ground_truth)
    return backstory, ground_truth


def _combined_scenario(
    objective_ids: tuple[str, ...],
) -> tuple[SyntheticBackstory, ProposedGroundTruth]:
    scene_ids = (TARGET_SCENE_ID, RETRIEVAL_COMPARISON_SCENE_ID)
    continuity_lines = tuple(
        _line(f"line-{order}", CONTINUITY_SCENE_ID, order, text)
        for order, text in enumerate(CONTINUITY_TEXTS, start=1)
    ) + (_line("line-comparison", COMPARISON_SCENE_ID, 1, COMPARISON_TEXT),)
    backstory = _backstory(
        scenes=(
            _scene(
                CONTINUITY_SCENE_ID,
                1,
                tuple(f"line-{order}" for order in range(1, len(CONTINUITY_TEXTS) + 1)),
            ),
            _scene(COMPARISON_SCENE_ID, 2, ("line-comparison",)),
            _retrieval_scene(TARGET_SCENE_ID, 3, TARGET_LINE_ID),
            _retrieval_scene(RETRIEVAL_COMPARISON_SCENE_ID, 4, COMPARISON_LINE_ID),
        ),
        lines=continuity_lines + _retrieval_lines(),
        objective_ids=objective_ids,
        run_configuration_ids=(RETRIEVAL_RUN_CONFIGURATION_ID,),
        props=_props(scene_ids),
    )
    ground_truth = _ground_truth(
        backstory,
        (
            _proposal(CONTINUITY_SCENE_ID),
            _proposal(COMPARISON_SCENE_ID, pairing=_pairing(CONTINUITY_SCENE_ID)),
            _retrieval_proposal(TARGET_SCENE_ID, (RELEVANT_PROP_ID,)),
            _retrieval_proposal(RETRIEVAL_COMPARISON_SCENE_ID, ()),
        ),
    )
    _validate(backstory, ground_truth)
    return backstory, ground_truth


def _validate(
    backstory: SyntheticBackstory, ground_truth: ProposedGroundTruth
) -> None:
    validate_scenario(
        backstory,
        ground_truth,
        backstory_bytes=backstory.model_dump_json().encode("utf-8"),
        run_configurations=load_run_configurations(
            DEFAULT_RUN_CONFIGURATION_DIRECTORY
        ),
    )


def _memory_ids(
    service: MemoryPolicyService, account: AccountContext
) -> dict[str, str]:
    by_text = {record.text: record.memory_id for record in service.list_active(account)}
    return {prop_id: by_text[_prop_text(prop_id)] for prop_id in PROP_IDS}


def _handler(
    plan: dict[str, tuple[tuple[str, ...], tuple[str, ...]]],
    *,
    release_source: ReleaseSource = "muse_candidate",
    side_effect: Callable[[MemoryPolicyService, AccountContext], None] | None = None,
) -> Callable[..., object]:
    """Record real transcript events for each retrieval Line, then release."""

    async def handler(
        request: ChatRequest,
        service: MemoryPolicyService,
        account: AccountContext,
    ) -> ChatResponse:
        if request.message in plan:
            retrieved, cited = plan[request.message]
            ids = _memory_ids(service, account)
            record_connection_event(
                ConnectionEvaluationEvent(
                    kind="search",
                    status="evidence_found" if retrieved else "no_evidence",
                    source="memory",
                    operation="search_memories",
                    evidence_json=tuple(
                        MemoryConnectionEvidence(
                            evidence_id=ids[prop_id], excerpt=_prop_text(prop_id)
                        ).model_dump_json()
                        for prop_id in retrieved
                    ),
                )
            )
            record_connection_event(
                ConnectionEvaluationEvent(
                    kind="release",
                    status=(
                        "released"
                        if release_source == "muse_candidate"
                        else "declined"
                    ),
                    release_source=release_source,
                    released_evidence_ids=tuple(ids[prop_id] for prop_id in cited),
                )
            )
            if side_effect is not None:
                side_effect(service, account)
            response = _released_response(release_source)
        else:
            response = _released_response()
        _append(request, response)
        return response

    return handler


def _clean_plan() -> dict[str, tuple[tuple[str, ...], tuple[str, ...]]]:
    return {
        TARGET_TEXT: ((RELEVANT_PROP_ID,), (RELEVANT_PROP_ID,)),
        COMPARISON_RETRIEVAL_TEXT: ((), ()),
    }


def _run(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    handler: Callable[..., object],
    **kwargs: object,
) -> object:
    return asyncio.run(
        replay_retrieval_scenes(
            backstory,
            ground_truth,
            chat_handler=handler,  # type: ignore[arg-type]
            **kwargs,  # type: ignore[arg-type]
        )
    )


def _retrieval_scenes(result: object) -> list[RetrievalSceneObservation]:
    return [
        scene
        for scene in result.scenes  # type: ignore[attr-defined]
        if isinstance(scene, RetrievalSceneObservation)
    ]


def test_retrieval_replay_passes_target_and_comparison_scenes() -> None:
    backstory, ground_truth = _retrieval_scenario()
    seen: list[tuple[str, bool, int]] = []

    async def handler(
        request: ChatRequest,
        service: MemoryPolicyService,
        account: AccountContext,
    ) -> ChatResponse:
        seen.append(
            (
                request.message,
                service.capture_enabled(account),
                len(service.list_active(account)),
            )
        )
        return await _handler(_clean_plan())(request, service, account)

    result = _run(backstory, ground_truth, handler)

    assert seen == [
        (TARGET_TEXT, False, len(PROP_IDS)),
        (COMPARISON_RETRIEVAL_TEXT, False, len(PROP_IDS)),
    ]
    target, comparison = _retrieval_scenes(result)
    assert [scene.scene_id for scene in result.scenes] == [
        TARGET_SCENE_ID,
        RETRIEVAL_COMPARISON_SCENE_ID,
    ]
    assert target.role == "target"
    assert comparison.role == "comparison"
    assert target.relevant_prop_ids == (RELEVANT_PROP_ID,)
    assert comparison.relevant_prop_ids == ()
    assert target.retrieved_prop_ids == (RELEVANT_PROP_ID,)
    assert target.cited_prop_ids == (RELEVANT_PROP_ID,)
    assert comparison.cited_prop_ids == ()
    assert target.hard_failures == ()
    assert comparison.hard_failures == ()
    assert target.ground_truth_result == "matches_proposal"
    assert comparison.ground_truth_result == "matches_proposal"
    assert target.release_source == "muse_candidate"
    assert target.semantic_review_required is True
    assert result.ground_truth_status == "proposed"
    assert result.dataset_version == ground_truth.backstory_sha256
    assert result.backstory_sha256 == ground_truth.backstory_sha256
    assert result.proposed_ground_truth_sha256 is None
    assert result.objective_ids == (RETRIEVAL_OBJECTIVE_ID,)
    assert result.capture_enabled is False


def test_retrieval_replay_keeps_labels_out_of_the_chat_boundary() -> None:
    backstory, ground_truth = _retrieval_scenario()
    requests: list[ChatRequest] = []

    async def handler(
        request: ChatRequest,
        service: MemoryPolicyService,
        account: AccountContext,
    ) -> ChatResponse:
        requests.append(request)
        return await _handler(_clean_plan())(request, service, account)

    _run(backstory, ground_truth, handler)

    serialized = json.dumps([request.model_dump(mode="json") for request in requests])
    assert backstory.backstory.context not in serialized
    assert "expected_outcomes" not in serialized
    assert "prop_relevance" not in serialized


def test_target_scene_fails_when_the_relevant_prop_is_not_retrieved() -> None:
    backstory, ground_truth = _retrieval_scenario()
    plan = _clean_plan()
    plan[TARGET_TEXT] = ((), ())

    result = _run(backstory, ground_truth, _handler(plan))

    target = _retrieval_scenes(result)[0]
    assert "relevant_prop_not_retrieved" in target.hard_failures
    assert "relevant_prop_not_cited" in target.hard_failures
    assert target.ground_truth_result == "differs_from_proposal"


def test_target_scene_fails_when_the_relevant_prop_is_not_cited() -> None:
    backstory, ground_truth = _retrieval_scenario()
    plan = _clean_plan()
    plan[TARGET_TEXT] = ((RELEVANT_PROP_ID,), ())

    result = _run(backstory, ground_truth, _handler(plan))

    target = _retrieval_scenes(result)[0]
    assert target.hard_failures == ("relevant_prop_not_cited",)
    assert target.retrieved_prop_ids == (RELEVANT_PROP_ID,)


def test_target_scene_fails_when_a_distractor_is_cited() -> None:
    backstory, ground_truth = _retrieval_scenario()
    plan = _clean_plan()
    plan[TARGET_TEXT] = (
        (RELEVANT_PROP_ID, DISTRACTOR_PROP_IDS[0]),
        (RELEVANT_PROP_ID, DISTRACTOR_PROP_IDS[0]),
    )

    result = _run(backstory, ground_truth, _handler(plan))

    target = _retrieval_scenes(result)[0]
    assert target.hard_failures == ("distractor_prop_cited",)
    assert target.cited_prop_ids == (RELEVANT_PROP_ID, DISTRACTOR_PROP_IDS[0])


def test_comparison_scene_fails_when_any_prop_is_cited() -> None:
    backstory, ground_truth = _retrieval_scenario()
    plan = _clean_plan()
    plan[COMPARISON_RETRIEVAL_TEXT] = (
        (DISTRACTOR_PROP_IDS[0],),
        (DISTRACTOR_PROP_IDS[0],),
    )

    result = _run(backstory, ground_truth, _handler(plan))

    comparison = _retrieval_scenes(result)[1]
    assert comparison.hard_failures == ("distractor_prop_cited",)
    assert comparison.ground_truth_result == "differs_from_proposal"


def test_retrieved_but_uncited_distractors_are_only_an_observation() -> None:
    backstory, ground_truth = _retrieval_scenario()
    plan = _clean_plan()
    plan[TARGET_TEXT] = (
        (RELEVANT_PROP_ID, DISTRACTOR_PROP_IDS[0], DISTRACTOR_PROP_IDS[1]),
        (RELEVANT_PROP_ID,),
    )

    result = _run(backstory, ground_truth, _handler(plan))

    target = _retrieval_scenes(result)[0]
    assert target.hard_failures == ()
    assert target.uncited_retrieved_distractor_prop_ids == (
        DISTRACTOR_PROP_IDS[0],
        DISTRACTOR_PROP_IDS[1],
    )
    assert target.ground_truth_result == "matches_proposal"


def test_a_safe_decline_release_fails_both_scenes() -> None:
    backstory, ground_truth = _retrieval_scenario()

    result = _run(
        backstory,
        ground_truth,
        _handler(_clean_plan(), release_source="application_safe_decline"),
    )

    target, comparison = _retrieval_scenes(result)
    assert "unexpected_release_source" in target.hard_failures
    assert comparison.hard_failures == ("unexpected_release_source",)
    assert comparison.release_source == "application_safe_decline"


def test_a_mutated_prop_store_fails_the_hard_gates() -> None:
    backstory, ground_truth = _retrieval_scenario()

    def remove_one(service: MemoryPolicyService, account: AccountContext) -> None:
        directory = service._account_dir(account)  # noqa: SLF001
        next(iter(sorted(directory.glob("*.md")))).unlink()

    result = _run(
        backstory, ground_truth, _handler(_clean_plan(), side_effect=remove_one)
    )

    target = _retrieval_scenes(result)[0]
    assert "props_changed" in target.hard_failures


def test_a_committed_memory_fails_the_hard_gates() -> None:
    backstory, ground_truth = _retrieval_scenario()

    def commit(service: MemoryPolicyService, account: AccountContext) -> None:
        service._save(  # noqa: SLF001
            account,
            text="a memory committed while capture is disabled",
            source_event_id="synthetic-source",
            evidence_ids=(),
        )

    result = _run(backstory, ground_truth, _handler(_clean_plan(), side_effect=commit))

    target = _retrieval_scenes(result)[0]
    assert "unexpected_memory_writes" in target.hard_failures


def _provenance_passes(messages: list, info: AgentInfo) -> ModelResponse:
    request = json.loads(messages[0].parts[0].content)
    assert request["candidate"]["response"] == "I do not have an earlier note that answers that."
    assert request["candidate"]["evidence_uses"] == []
    assert len(request["uncovered_response_spans"]) == 1
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
        "findings": [],
        "coverage_audit": [{"span_index": 0, "classification": "reader_reflection"}],
        "response_decision": "pass",
        "emotional_boundary_decision": "not_required",
        "capture_decision": "no_candidate",
    })])


def _muse_looks_up_then_replies_plainly(messages: list, info: AgentInfo) -> ModelResponse:
    looked_up = any(
        isinstance(part, ToolReturnPart) and part.tool_name == "serendipity_explore"
        for message in messages
        for part in getattr(message, "parts", ())
    )
    if not looked_up:
        return ModelResponse(parts=[
            ToolCallPart("serendipity_explore", {"intent": "find_connection"})
        ])
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
        "reply": "I do not have an earlier note that answers that.",
        "evidence_uses": [],
        "memory": {
            "kind": "no_memory_candidate",
            "reason_code": "automatic_capture_disabled",
        },
    })])


def _serendipity_raises(messages: object, info: AgentInfo) -> ModelResponse:
    raise RuntimeError("discovery provider unavailable")


def test_comparison_scene_fails_when_real_discovery_raises() -> None:
    from apps.backend import chat_turn
    from src.linger.orchestration import connection

    backstory, ground_truth = _retrieval_scenario()

    with (
        patch.object(
            chat_turn,
            "assess_emotional_boundary",
            AsyncMock(
                return_value=EmotionalBoundaryAssessment(decision="continue_reflection")
            ),
        ),
        chat_turn.muse_chat_agent.override(
            model=FunctionModel(_muse_looks_up_then_replies_plainly)
        ),
        connection.serendipity_agent.override(model=FunctionModel(_serendipity_raises)),
        chat_turn.provenance_agent.override(model=FunctionModel(_provenance_passes)),
    ):
        result = _run(backstory, ground_truth, chat_turn.run_chat_turn)

    comparison = _retrieval_scenes(result)[1]
    assert comparison.release_source == "muse_candidate"
    assert any(
        event.kind == "discovery" and event.status == "failed"
        for event in comparison.events
    )
    assert comparison.hard_failures == ("discovery_failure",)
    assert comparison.ground_truth_result == "differs_from_proposal"


def test_comparison_scene_fails_when_the_memory_search_fails() -> None:
    backstory, ground_truth = _retrieval_scenario()
    clean = _handler(_clean_plan())

    async def handler(
        request: ChatRequest, service: MemoryPolicyService, account: AccountContext
    ) -> ChatResponse:
        if request.message == COMPARISON_RETRIEVAL_TEXT:
            record_connection_event(
                ConnectionEvaluationEvent(
                    kind="search",
                    status="retrieval_unavailable",
                    source="memory",
                    operation="search_memories",
                )
            )
        return await clean(request, service, account)

    result = _run(backstory, ground_truth, handler)

    target, comparison = _retrieval_scenes(result)
    assert target.hard_failures == ()
    assert comparison.hard_failures == ("retrieval_failure",)
    assert comparison.ground_truth_result == "differs_from_proposal"


def test_comparison_scene_passes_without_any_lookup() -> None:
    backstory, ground_truth = _retrieval_scenario()
    clean = _handler(_clean_plan())

    async def handler(
        request: ChatRequest, service: MemoryPolicyService, account: AccountContext
    ) -> ChatResponse:
        if request.message != COMPARISON_RETRIEVAL_TEXT:
            return await clean(request, service, account)
        record_connection_event(
            ConnectionEvaluationEvent(
                kind="release", status="released", release_source="muse_candidate"
            )
        )
        response = _released_response()
        _append(request, response)
        return response

    result = _run(backstory, ground_truth, handler)

    comparison = _retrieval_scenes(result)[1]
    assert not [event for event in comparison.events if event.kind != "release"]
    assert comparison.hard_failures == ()
    assert comparison.ground_truth_result == "matches_proposal"


def test_a_missing_release_observation_fails_the_hard_gates() -> None:
    backstory, ground_truth = _retrieval_scenario()

    async def handler(
        request: ChatRequest,
        _service: MemoryPolicyService,
        _account: AccountContext,
    ) -> ChatResponse:
        response = _released_response()
        _append(request, response)
        return response

    result = _run(backstory, ground_truth, handler)

    target = _retrieval_scenes(result)[0]
    assert "missing_release_observation" in target.hard_failures


@pytest.mark.parametrize(
    "objective_ids",
    [
        (CONTINUITY_OBJECTIVE_ID, RETRIEVAL_OBJECTIVE_ID),
        (RETRIEVAL_OBJECTIVE_ID, CONTINUITY_OBJECTIVE_ID),
    ],
)
def test_combined_backstory_runs_every_scene_in_declared_order(
    objective_ids: tuple[str, ...],
) -> None:
    backstory, ground_truth = _combined_scenario(objective_ids)

    result = _run(backstory, ground_truth, _handler(_clean_plan()))

    assert [scene.scene_id for scene in result.scenes] == [
        CONTINUITY_SCENE_ID,
        COMPARISON_SCENE_ID,
        TARGET_SCENE_ID,
        RETRIEVAL_COMPARISON_SCENE_ID,
    ]
    continuity, comparison, target, retrieval_comparison = result.scenes
    assert continuity.ground_truth_result == "not_applicable"
    assert comparison.ground_truth_result == "matches_proposal"
    assert comparison.paired_scene_id == CONTINUITY_SCENE_ID
    assert target.ground_truth_result == "matches_proposal"
    assert retrieval_comparison.ground_truth_result == "matches_proposal"
    assert target.hard_failures == ()
    assert set(result.objective_ids) == set(objective_ids)


def test_combined_backstory_reports_a_failing_retrieval_scene() -> None:
    backstory, ground_truth = _combined_scenario(
        (CONTINUITY_OBJECTIVE_ID, RETRIEVAL_OBJECTIVE_ID)
    )
    plan = _clean_plan()
    plan[TARGET_TEXT] = ((), ())

    result = _run(backstory, ground_truth, _handler(plan))

    assert result.scenes[1].ground_truth_result == "matches_proposal"
    assert result.scenes[2].ground_truth_result == "differs_from_proposal"


def test_retrieval_replay_rejects_another_objective() -> None:
    backstory, ground_truth = _retrieval_scenario()
    scenes = tuple(
        scene.model_copy(update={"objective_ids": ("bounded_memory_curation",)})
        for scene in backstory.scenes
    )
    invalid = backstory.model_copy(
        update={"objective_ids": ("bounded_memory_curation",), "scenes": scenes}
    )

    with pytest.raises(ValueError, match="longitudinal_memory_retrieval"):
        _run(invalid, ground_truth, _dummy_handler)


def test_retrieval_replay_rejects_offline_inputs() -> None:
    backstory, ground_truth = _retrieval_scenario()
    offline_input = OfflineInput(
        offline_input_id="offline-1",
        scene_id=TARGET_SCENE_ID,
        order=1,
        kind="uploaded_note",
        text="An offline note that no retrieval Scene may use.",
    )
    scenes = (
        backstory.scenes[0].model_copy(update={"offline_input_ids": ("offline-1",)}),
        backstory.scenes[1],
    )
    invalid = backstory.model_copy(
        update={"offline_inputs": (offline_input,), "scenes": scenes}
    )

    with pytest.raises(ValueError, match="Lines and Props only"):
        _run(invalid, ground_truth, _dummy_handler)


def test_retrieval_replay_requires_the_run_configuration() -> None:
    backstory, ground_truth = _retrieval_scenario()
    invalid = backstory.model_copy(update={"run_configuration_ids": ()})

    with pytest.raises(ValueError, match=RETRIEVAL_RUN_CONFIGURATION_ID):
        _run(invalid, ground_truth, _dummy_handler)


def test_retrieval_replay_rejects_a_continued_session() -> None:
    backstory, ground_truth = _retrieval_scenario()
    scenes = (
        backstory.scenes[0].model_copy(update={"fresh_session": False}),
        backstory.scenes[1],
    )
    invalid = backstory.model_copy(update={"scenes": scenes})

    with pytest.raises(ValueError, match="fresh session"):
        _run(invalid, ground_truth, _dummy_handler)


def test_retrieval_replay_rejects_two_lines_in_one_scene() -> None:
    backstory, ground_truth = _retrieval_scenario()
    extra = _line("line-retrieval-extra", TARGET_SCENE_ID, 2, "A second Line.")
    scenes = (
        backstory.scenes[0].model_copy(
            update={"line_ids": (TARGET_LINE_ID, "line-retrieval-extra")}
        ),
        backstory.scenes[1],
    )
    invalid = backstory.model_copy(
        update={"scenes": scenes, "lines": (*backstory.lines, extra)}
    )

    with pytest.raises(ValueError, match="exactly one Line"):
        _run(invalid, ground_truth, _dummy_handler)


def test_retrieval_replay_rejects_a_scene_without_props() -> None:
    backstory, ground_truth = _retrieval_scenario()
    props = tuple(
        prop.model_copy(
            update={
                "lifecycle": tuple(
                    item
                    for item in prop.lifecycle
                    if item.scene_id != RETRIEVAL_COMPARISON_SCENE_ID
                )
            }
        )
        for prop in backstory.props
    )
    scenes = (
        backstory.scenes[0],
        backstory.scenes[1].model_copy(update={"prop_ids": ()}),
    )
    invalid = backstory.model_copy(update={"scenes": scenes, "props": props})

    with pytest.raises(ValueError, match="at least one active Prop"):
        _run(invalid, ground_truth, _dummy_handler)


def test_retrieval_replay_rejects_a_continuity_scene_with_props() -> None:
    backstory, ground_truth = _combined_scenario(
        (CONTINUITY_OBJECTIVE_ID, RETRIEVAL_OBJECTIVE_ID)
    )
    props = tuple(
        prop.model_copy(
            update={
                "lifecycle": (
                    *prop.lifecycle,
                    PropLifecycle(scene_id=CONTINUITY_SCENE_ID, state="active"),
                )
            }
        )
        for prop in backstory.props
    )
    scenes = (
        backstory.scenes[0].model_copy(update={"prop_ids": PROP_IDS}),
        *backstory.scenes[1:],
    )
    invalid = backstory.model_copy(update={"scenes": scenes, "props": props})

    with pytest.raises(ValueError, match="Props or offline inputs"):
        _run(invalid, ground_truth, _dummy_handler)


def test_retrieval_replay_rejects_a_scene_with_two_objectives() -> None:
    backstory, ground_truth = _combined_scenario(
        (CONTINUITY_OBJECTIVE_ID, RETRIEVAL_OBJECTIVE_ID)
    )
    scenes = (
        backstory.scenes[0].model_copy(
            update={
                "objective_ids": (CONTINUITY_OBJECTIVE_ID, RETRIEVAL_OBJECTIVE_ID)
            }
        ),
        *backstory.scenes[1:],
    )
    invalid = backstory.model_copy(update={"scenes": scenes})

    with pytest.raises(ValueError, match="exactly one"):
        _run(invalid, ground_truth, _dummy_handler)


def test_retrieval_replay_grades_adopted_ground_truth_with_hard_gates() -> None:
    backstory, ground_truth = _retrieval_scenario()
    adoption = _adoption(ground_truth)

    result = _run(
        backstory, ground_truth, _handler(_clean_plan()), adoption=adoption
    )

    target, comparison = _retrieval_scenes(result)
    assert result.ground_truth_status == "adopted"
    assert result.dataset_version == adoption.adopted_ground_truth_identity
    assert result.proposed_ground_truth_sha256 == (
        adoption.proposed_ground_truth_sha256
    )
    assert target.ground_truth_result == "passes_hard_gates"
    assert comparison.ground_truth_result == "passes_hard_gates"


def test_retrieval_replay_fails_hard_gates_under_adoption() -> None:
    backstory, ground_truth = _retrieval_scenario()
    adoption = _adoption(ground_truth)
    plan = _clean_plan()
    plan[TARGET_TEXT] = ((), ())

    result = _run(backstory, ground_truth, _handler(plan), adoption=adoption)

    assert _retrieval_scenes(result)[0].ground_truth_result == "fails_hard_gates"


def test_cli_writes_the_run_artifact(tmp_path: Path) -> None:
    backstory, ground_truth = _retrieval_scenario()
    backstory_path = tmp_path / "backstory.json"
    ground_truth_path = tmp_path / "ground-truth.json"
    output_path = tmp_path / "run.json"
    backstory_path.write_text(backstory.model_dump_json(), encoding="utf-8")
    ground_truth_path.write_text(ground_truth.model_dump_json(), encoding="utf-8")
    handler = _handler(_clean_plan())

    with (
        patch.object(
            retrieval_replay, "_production_chat_turn_handler", lambda: handler
        ),
        patch.object(
            retrieval_replay, "configure_synthetic_evaluation_telemetry", lambda _: None
        ),
    ):
        code = retrieval_main(
            [
                str(backstory_path),
                str(ground_truth_path),
                "--output",
                str(output_path),
            ]
        )

    assert code == 0
    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert [scene["scene_id"] for scene in artifact["scenes"]] == [
        TARGET_SCENE_ID,
        RETRIEVAL_COMPARISON_SCENE_ID,
    ]
    assert artifact["ground_truth_status"] == "proposed"


def test_cli_returns_nonzero_for_a_tampered_backstory_hash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    backstory, ground_truth = _retrieval_scenario()
    backstory_path = tmp_path / "backstory.json"
    ground_truth_path = tmp_path / "ground-truth.json"
    backstory_path.write_text(backstory.model_dump_json(), encoding="utf-8")
    tampered = ground_truth.model_copy(update={"backstory_sha256": "0" * 64})
    ground_truth_path.write_text(tampered.model_dump_json(), encoding="utf-8")

    code = retrieval_main([str(backstory_path), str(ground_truth_path)])

    assert code == 1
    assert "EVALUATION_RUN_ERROR=" in capsys.readouterr().err


@pytest.mark.parametrize(
    "objective_ids",
    [
        (RETRIEVAL_OBJECTIVE_ID,),
        (CONTINUITY_OBJECTIVE_ID, RETRIEVAL_OBJECTIVE_ID),
        (RETRIEVAL_OBJECTIVE_ID, CONTINUITY_OBJECTIVE_ID),
    ],
)
def test_replay_support_resolves_the_retrieval_selections(
    objective_ids: tuple[str, ...],
) -> None:
    support = replay_support_for(objective_ids)

    assert support is not None
    assert support.module == "evals.synthetic_journals.retrieval_replay"
