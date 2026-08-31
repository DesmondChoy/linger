"""Tests for session-continuity Scene replay across one persisted session."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import logfire
import pytest
from logfire.testing import TestExporter
from pydantic_evals.evaluators import EvaluatorContext
from pydantic_evals.evaluators.context import SpanTreeRecordingError

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from apps.backend import sessions
from apps.backend.config import get_settings
from apps.backend.schemas import (
    CaptureInspection,
    ChatRequest,
    ChatResponse,
    ReleaseInspection,
    TraceReference,
    TurnInspection,
)
from evals.synthetic_journals.adoption import build_ground_truth_adoption
from evals.synthetic_journals.continuity_replay import main as continuity_main
from evals.synthetic_journals.continuity_replay import (
    CONTINUITY_OBJECTIVE_ID,
    RUNTIME_PROMPT_FINGERPRINTS,
    ContinuityEvaluationExpected,
    ContinuityEvaluationInput,
    ContinuityEvaluationOutput,
    ContinuityEvaluationResult,
    ContinuitySceneObservation,
    ContinuityStructuralEvaluator,
    GroundTruthStatus,
    ReleaseSource,
    SceneRole,
    TurnObservation,
    replay_continuity_scenes,
)
from evals.synthetic_journals.models import (
    Backstory,
    GroundTruthAdoption,
    GroundTruthProposal,
    Line,
    OfflineInput,
    Prop,
    PropLifecycle,
    ProposedGroundTruth,
    Scene,
    ScenePairing,
    SyntheticBackstory,
)
from evals.synthetic_journals.validate_package import validate_package
from src.linger.agents.muse.agent import muse_chat_agent
from src.linger.agents.provenance.agent import provenance_agent
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.evaluation_transcript import active_evaluation_transcript_sink
from src.linger.services.memory import AccountContext, MemoryPolicyService

BACKSTORY_ID = "backstory-continuity"
CONTINUITY_SCENE_ID = "scene-continuity"
COMPARISON_SCENE_ID = "scene-comparison"
CONTINUITY_TEXTS = (
    "I keep circling the same worry about moving away next spring.",
    "Most of it is about leaving the Thursday reading group behind.",
    "That is wrong: the reading group already meets online every week.",
    "What did I say the worry was actually about?",
)
COMPARISON_TEXT = CONTINUITY_TEXTS[-1]


def _line(line_id: str, scene_id: str, order: int, text: str) -> Line:
    return Line(line_id=line_id, scene_id=scene_id, order=order, text=text)


def _scene(
    scene_id: str,
    order: int,
    line_ids: tuple[str, ...],
    *,
    objective_ids: tuple[str, ...] = (CONTINUITY_OBJECTIVE_ID,),
    fresh_session: bool = True,
    prop_ids: tuple[str, ...] = (),
    offline_input_ids: tuple[str, ...] = (),
) -> Scene:
    return Scene(
        scene_id=scene_id,
        backstory_id=BACKSTORY_ID,
        objective_ids=objective_ids,
        order=order,
        fresh_session=fresh_session,
        prop_ids=prop_ids,
        line_ids=line_ids,
        offline_input_ids=offline_input_ids,
    )


def _backstory(
    scenes: tuple[Scene, ...],
    lines: tuple[Line, ...],
    *,
    objective_ids: tuple[str, ...] = (CONTINUITY_OBJECTIVE_ID,),
    run_configuration_ids: tuple[str, ...] = (),
    props: tuple[Prop, ...] = (),
    offline_inputs: tuple[OfflineInput, ...] = (),
) -> SyntheticBackstory:
    return SyntheticBackstory(
        objective_ids=objective_ids,
        run_configuration_ids=run_configuration_ids,
        backstory=Backstory(
            backstory_id=BACKSTORY_ID,
            person_id="person-continuity",
            evaluation_account_id="account-continuity",
            context="A generator-only history that must never reach the boundary.",
        ),
        props=props,
        scenes=scenes,
        lines=lines,
        offline_inputs=offline_inputs,
    )


def _proposal(
    scene_id: str,
    *,
    objective_id: str = CONTINUITY_OBJECTIVE_ID,
    pairing: ScenePairing | None = None,
) -> GroundTruthProposal:
    return GroundTruthProposal(
        proposal_id=f"proposal-{scene_id}",
        scene_id=scene_id,
        objective_id=objective_id,
        expected_outcomes=("The reply reflects the corrected reading-group fact.",),
        prohibited_outcomes=("The reply repeats the superseded worry as current.",),
        pairing=pairing,
    )


def _ground_truth(
    backstory: SyntheticBackstory,
    proposals: tuple[GroundTruthProposal, ...],
) -> ProposedGroundTruth:
    backstory_bytes = backstory.model_dump_json().encode("utf-8")
    return ProposedGroundTruth(
        backstory_sha256=hashlib.sha256(backstory_bytes).hexdigest(),
        ground_truth_status="proposed",
        proposals=proposals,
    )


def _pairing(paired_scene_id: str) -> ScenePairing:
    return ScenePairing(
        paired_scene_id=paired_scene_id,
        match_fields=("backstory_id", "fresh_session"),
        difference_fields=("line_count",),
    )


def _continuity_package() -> tuple[SyntheticBackstory, ProposedGroundTruth]:
    """Build a validated four-Line continuity Scene and its comparison Scene."""

    lines = tuple(
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
        ),
        lines=lines,
    )
    ground_truth = _ground_truth(
        backstory,
        (
            _proposal(CONTINUITY_SCENE_ID),
            _proposal(
                COMPARISON_SCENE_ID,
                pairing=_pairing(CONTINUITY_SCENE_ID),
            ),
        ),
    )
    validate_package(
        backstory,
        ground_truth,
        backstory_bytes=backstory.model_dump_json().encode("utf-8"),
        run_configurations={},
    )
    return backstory, ground_truth


def _released_response(
    release_source: ReleaseSource = "muse_candidate",
    *,
    prior_evidence_count: int = 0,
    context_resolution_status: str = "unknown",
) -> ChatResponse:
    declined = release_source != "muse_candidate"
    capture = CaptureInspection(
        nomination="unavailable" if declined else "no_candidate",
        provenance_decision=None if declined else "no_candidate",
        binding="not_applicable",
        storage="suppressed" if declined else "not_applicable",
        reason_code="not_applicable",
    )
    return ChatResponse(
        reply="A synthetic reviewed reply.",
        inspection=TurnInspection(
            muse_turn={},
            context_resolution={"status": context_resolution_status},
            prior_evidence_count=prior_evidence_count,
            traces=[],
            prompt="synthetic",
            release=ReleaseInspection(
                release_source=release_source,
                boundary_origin=(
                    "preflight"
                    if release_source == "application_emotional_boundary"
                    else None
                ),
                provenance_verdicts=("pass",),
                finding_codes=(),
                revision_count=0,
                failure_stage=None,
                capture=capture,
            ),
        ),
        trace=TraceReference(trace_id="0" * 32),
    )


def _append(request: ChatRequest, response: ChatResponse) -> None:
    """Append the released turn exactly as production chat does."""

    assert request.turn_id is not None
    release = response.inspection.release
    assert release is not None
    sessions.append_turn(
        request.session_id,
        request.message,
        response.reply,
        turn_id=request.turn_id,
        release_source=release.release_source,
    )


def _turn_fields(**overrides: object) -> dict[str, object]:
    """Return valid TurnObservation fields with one deliberate substitution."""

    response = _released_response()
    release = response.inspection.release
    assert release is not None
    fields: dict[str, object] = {
        "line_id": "line-1",
        "order": 1,
        "input_line": CONTINUITY_TEXTS[0],
        "reply": response.reply,
        "release_source": release.release_source,
        "boundary_origin": None,
        "store_messages_before": 0,
        "store_messages_appended": 2,
        "prior_evidence_rehydrated": 0,
        "context_resolution_status": "unknown",
        "capture": release.capture,
        "span_id": "0" * 16,
    }
    fields.update(overrides)
    return fields


def _record_exchange(input_prompt: str) -> None:
    """Drive the bound transcript sink the way instrumented agent calls do."""

    sink = active_evaluation_transcript_sink()
    assert sink is not None
    handle = sink.begin_agent_exchange(
        role="Muse",
        stage="draft",
        input_origin="Application",
        output_receiver="Application",
        input_contract="MuseTurn.v1",
        output_contract="MuseCandidate.v1",
        prompt_template_id="muse.draft",
        prompt_version="1",
        prompt_digest="0" * 64,
        input_prompt=input_prompt,
        message_history=(),
        trace_id="0" * 32,
        span_id="0" * 16,
    )
    sink.complete_agent_exchange(
        handle,
        result=SimpleNamespace(
            output={"reply": "synthetic"},
            new_messages=lambda: [],
        ),
        status="success",
        failure_code=None,
    )


def _record_routed_exchange(role: str) -> None:
    """Drive the bound transcript sink as a Librarian or Serendipity call would."""

    sink = active_evaluation_transcript_sink()
    assert sink is not None
    handle = sink.begin_agent_exchange(
        role=role,
        stage="retrieval",
        input_origin="Muse",
        output_receiver="Muse",
        input_contract=f"{role}Request.v1",
        output_contract=f"{role}Response.v1",
        prompt_template_id=f"{role.lower()}.request",
        prompt_version="1",
        prompt_digest="0" * 64,
        input_prompt="synthetic",
        message_history=(),
        trace_id="0" * 32,
        span_id="0" * 16,
    )
    sink.complete_agent_exchange(
        handle,
        result=SimpleNamespace(output={}, new_messages=lambda: []),
        status="success",
        failure_code=None,
    )


def _dummy_handler(*_args: object) -> None:  # pragma: no cover - guard tests only
    raise AssertionError("guarded replay must not reach the chat boundary")


def test_continuity_replay_threads_one_session_per_scene() -> None:
    backstory, ground_truth = _continuity_package()
    requests: list[ChatRequest] = []
    store_lengths: list[int] = []
    accounts: set[str] = set()
    store_roots: set[Path] = set()

    async def chat_handler(
        request: ChatRequest,
        service: MemoryPolicyService,
        account: AccountContext,
    ) -> ChatResponse:
        requests.append(request)
        store_lengths.append(len(sessions.history(request.session_id)))
        accounts.add(account.account_id)
        store_roots.add(service.root)
        assert not service.capture_enabled(account)
        response = _released_response()
        _append(request, response)
        return response

    result = asyncio.run(
        replay_continuity_scenes(backstory, ground_truth, chat_handler=chat_handler)
    )

    assert [request.message for request in requests] == [
        *CONTINUITY_TEXTS,
        COMPARISON_TEXT,
    ]
    assert store_lengths == [0, 2, 4, 6, 0]
    assert len({request.session_id for request in requests}) == 2
    assert len({request.turn_id for request in requests}) == len(requests)
    assert len(accounts) == 1
    assert len(store_roots) == 1
    assert all(not path.exists() for path in store_roots)
    assert all(not sessions.history(item.session_id) for item in requests)
    assert backstory.backstory.evaluation_account_id not in accounts
    assert result.capture_enabled is False
    assert result.final_active_memory_ids == ()
    assert result.runtime_prompt_fingerprints == RUNTIME_PROMPT_FINGERPRINTS
    assert result.dataset_version == ground_truth.backstory_sha256
    assert result.ground_truth_status == "proposed"
    assert len(result.trace_id) == 32

    continuity, comparison = result.scenes
    assert [scene.scene_id for scene in result.scenes] == [
        CONTINUITY_SCENE_ID,
        COMPARISON_SCENE_ID,
    ]
    assert continuity.role == "continuity"
    assert continuity.paired_scene_id is None
    assert comparison.role == "comparison"
    assert comparison.paired_scene_id == CONTINUITY_SCENE_ID
    assert [turn.store_messages_before for turn in continuity.turns] == [0, 2, 4, 6]
    assert [turn.store_messages_appended for turn in continuity.turns] == [2, 2, 2, 2]
    assert all(turn.exchange_sequence_first is None for turn in continuity.turns)
    assert continuity.session_turn_release_sources == ("muse_candidate",) * 4
    assert continuity.structural_findings == ()
    assert comparison.structural_findings == ()


def test_continuity_replay_grades_only_the_proposed_session_boundary() -> None:
    backstory, ground_truth = _continuity_package()

    async def chat_handler(
        request: ChatRequest,
        _service: MemoryPolicyService,
        _account: AccountContext,
    ) -> ChatResponse:
        response = _released_response()
        _append(request, response)
        return response

    result = asyncio.run(
        replay_continuity_scenes(backstory, ground_truth, chat_handler=chat_handler)
    )

    continuity, comparison = result.scenes
    assert continuity.ground_truth_result == "not_applicable"
    assert comparison.ground_truth_result == "matches_proposal"


def test_continuity_replay_reports_a_broken_session_boundary() -> None:
    backstory, ground_truth = _continuity_package()

    async def chat_handler(
        request: ChatRequest,
        _service: MemoryPolicyService,
        _account: AccountContext,
    ) -> ChatResponse:
        response = _released_response()
        _append(request, response)
        if request.session_id.endswith(CONTINUITY_SCENE_ID):
            leaked = request.session_id.replace(
                CONTINUITY_SCENE_ID, COMPARISON_SCENE_ID
            )
            sessions.append_turn(
                leaked,
                request.message,
                response.reply,
                turn_id=f"{request.turn_id}:leaked",
                release_source="muse_candidate",
            )
        return response

    result = asyncio.run(
        replay_continuity_scenes(backstory, ground_truth, chat_handler=chat_handler)
    )

    continuity, comparison = result.scenes
    assert continuity.ground_truth_result == "not_applicable"
    assert continuity.structural_findings == ()
    assert comparison.ground_truth_result == "differs_from_proposal"
    assert comparison.turns[0].store_messages_before == 8
    assert "history_thread_broken:line-comparison" in comparison.structural_findings


def test_continuity_replay_records_a_mid_sequence_decline() -> None:
    backstory, ground_truth = _continuity_package()

    async def chat_handler(
        request: ChatRequest,
        _service: MemoryPolicyService,
        _account: AccountContext,
    ) -> ChatResponse:
        release: ReleaseSource = (
            "application_safe_decline"
            if request.message == CONTINUITY_TEXTS[2]
            else "muse_candidate"
        )
        response = _released_response(release)
        _append(request, response)
        return response

    result = asyncio.run(
        replay_continuity_scenes(backstory, ground_truth, chat_handler=chat_handler)
    )

    continuity = result.scenes[0]
    assert len(continuity.turns) == len(CONTINUITY_TEXTS)
    assert continuity.turns[2].release_source == "application_safe_decline"
    assert continuity.structural_findings == ("unreleased_turn:line-3",)
    assert continuity.session_turn_release_sources == (
        "muse_candidate",
        "muse_candidate",
        "application_safe_decline",
        "muse_candidate",
    )
    assert [turn.store_messages_appended for turn in continuity.turns] == [2, 2, 0, 2]
    assert continuity.ground_truth_result == "not_applicable"
    assert result.scenes[1].ground_truth_result == "matches_proposal"


def test_continuity_replay_reports_an_unrecorded_turn() -> None:
    backstory, ground_truth = _continuity_package()

    async def chat_handler(
        request: ChatRequest,
        _service: MemoryPolicyService,
        _account: AccountContext,
    ) -> ChatResponse:
        response = _released_response()
        if request.message != CONTINUITY_TEXTS[1]:
            _append(request, response)
        return response

    result = asyncio.run(
        replay_continuity_scenes(backstory, ground_truth, chat_handler=chat_handler)
    )

    continuity = result.scenes[0]
    assert continuity.turns[1].store_messages_appended == 0
    assert "history_thread_broken:line-2" in continuity.structural_findings
    assert "turn_record_mismatch" in continuity.structural_findings
    assert json.loads(result.model_dump_json())["scenes"][0]["structural_findings"] == (
        list(continuity.structural_findings)
    )


def test_continuity_replay_keeps_backstory_context_out_of_every_request() -> None:
    backstory, ground_truth = _continuity_package()
    requests: list[ChatRequest] = []

    async def chat_handler(
        request: ChatRequest,
        _service: MemoryPolicyService,
        _account: AccountContext,
    ) -> ChatResponse:
        requests.append(request)
        response = _released_response()
        _append(request, response)
        return response

    asyncio.run(
        replay_continuity_scenes(backstory, ground_truth, chat_handler=chat_handler)
    )

    serialized_requests = json.dumps(
        [request.model_dump(mode="json") for request in requests]
    )
    assert backstory.backstory.context not in serialized_requests
    assert "expected_outcomes" not in serialized_requests
    assert "prohibited_outcomes" not in serialized_requests


def test_continuity_replay_rejects_another_objective() -> None:
    backstory, ground_truth = _continuity_package()
    scenes = tuple(
        scene.model_copy(
            update={"objective_ids": ("reviewed_automatic_memory_capture",)}
        )
        for scene in backstory.scenes
    )
    invalid = backstory.model_copy(
        update={
            "objective_ids": ("reviewed_automatic_memory_capture",),
            "scenes": scenes,
        }
    )

    with pytest.raises(ValueError, match="session_scoped_conversation_continuity"):
        asyncio.run(
            replay_continuity_scenes(
                invalid,
                ground_truth,
                chat_handler=_dummy_handler,  # type: ignore[arg-type]
            )
        )


def test_continuity_replay_rejects_a_run_configuration() -> None:
    backstory, ground_truth = _continuity_package()
    invalid = backstory.model_copy(
        update={"run_configuration_ids": ("continuity-run-configuration",)}
    )

    with pytest.raises(ValueError, match="no run configuration"):
        asyncio.run(
            replay_continuity_scenes(
                invalid,
                ground_truth,
                chat_handler=_dummy_handler,  # type: ignore[arg-type]
            )
        )


def test_continuity_replay_rejects_props() -> None:
    backstory, ground_truth = _continuity_package()
    prop = Prop(
        prop_id="prop-1",
        backstory_id=BACKSTORY_ID,
        person_id=backstory.backstory.person_id,
        evaluation_account_id=backstory.backstory.evaluation_account_id,
        source_text="A separate source record.",
        lifecycle=(PropLifecycle(scene_id=CONTINUITY_SCENE_ID, state="active"),),
    )
    scenes = (
        backstory.scenes[0].model_copy(update={"prop_ids": ("prop-1",)}),
        backstory.scenes[1],
    )
    invalid = backstory.model_copy(update={"props": (prop,), "scenes": scenes})

    with pytest.raises(ValueError, match="Props or offline inputs"):
        asyncio.run(
            replay_continuity_scenes(
                invalid,
                ground_truth,
                chat_handler=_dummy_handler,  # type: ignore[arg-type]
            )
        )


def test_continuity_replay_rejects_offline_inputs() -> None:
    backstory, ground_truth = _continuity_package()
    offline_input = OfflineInput(
        offline_input_id="offline-1",
        scene_id=CONTINUITY_SCENE_ID,
        order=1,
        kind="uploaded_note",
        text="An offline note that no continuity Scene may use.",
    )
    scenes = (
        backstory.scenes[0].model_copy(update={"offline_input_ids": ("offline-1",)}),
        backstory.scenes[1],
    )
    invalid = backstory.model_copy(
        update={"offline_inputs": (offline_input,), "scenes": scenes}
    )

    with pytest.raises(ValueError, match="Props or offline inputs"):
        asyncio.run(
            replay_continuity_scenes(
                invalid,
                ground_truth,
                chat_handler=_dummy_handler,  # type: ignore[arg-type]
            )
        )


def test_continuity_replay_rejects_a_continued_session() -> None:
    backstory, ground_truth = _continuity_package()
    scenes = (
        backstory.scenes[0],
        backstory.scenes[1].model_copy(update={"fresh_session": False}),
    )
    invalid = backstory.model_copy(update={"scenes": scenes})

    with pytest.raises(ValueError, match="fresh session"):
        asyncio.run(
            replay_continuity_scenes(
                invalid,
                ground_truth,
                chat_handler=_dummy_handler,  # type: ignore[arg-type]
            )
        )


def test_continuity_replay_rejects_a_pairing_tie() -> None:
    lines = (
        _line("line-1", CONTINUITY_SCENE_ID, 1, CONTINUITY_TEXTS[0]),
        _line("line-2", CONTINUITY_SCENE_ID, 2, CONTINUITY_TEXTS[3]),
        _line("line-3", COMPARISON_SCENE_ID, 1, CONTINUITY_TEXTS[1]),
        _line("line-4", COMPARISON_SCENE_ID, 2, CONTINUITY_TEXTS[3]),
    )
    backstory = _backstory(
        scenes=(
            _scene(CONTINUITY_SCENE_ID, 1, ("line-1", "line-2")),
            _scene(COMPARISON_SCENE_ID, 2, ("line-3", "line-4")),
        ),
        lines=lines,
    )
    ground_truth = _ground_truth(
        backstory,
        (
            _proposal(CONTINUITY_SCENE_ID),
            _proposal(
                COMPARISON_SCENE_ID,
                pairing=ScenePairing(
                    paired_scene_id=CONTINUITY_SCENE_ID,
                    difference_fields=("line_text",),
                ),
            ),
        ),
    )

    with pytest.raises(ValueError, match="must differ in Line count"):
        asyncio.run(
            replay_continuity_scenes(
                backstory,
                ground_truth,
                chat_handler=_dummy_handler,  # type: ignore[arg-type]
            )
        )


def test_continuity_replay_rejects_a_scene_in_two_pairing_edges() -> None:
    lines = (
        _line("line-1", CONTINUITY_SCENE_ID, 1, CONTINUITY_TEXTS[0]),
        _line("line-2", CONTINUITY_SCENE_ID, 2, CONTINUITY_TEXTS[1]),
        _line("line-3", CONTINUITY_SCENE_ID, 3, COMPARISON_TEXT),
        _line("line-4", COMPARISON_SCENE_ID, 1, COMPARISON_TEXT),
        _line("line-5", "scene-comparison-two", 1, COMPARISON_TEXT),
    )
    backstory = _backstory(
        scenes=(
            _scene(CONTINUITY_SCENE_ID, 1, ("line-1", "line-2", "line-3")),
            _scene(COMPARISON_SCENE_ID, 2, ("line-4",)),
            _scene("scene-comparison-two", 3, ("line-5",)),
        ),
        lines=lines,
    )
    ground_truth = _ground_truth(
        backstory,
        (
            _proposal(CONTINUITY_SCENE_ID),
            _proposal(COMPARISON_SCENE_ID, pairing=_pairing(CONTINUITY_SCENE_ID)),
            _proposal("scene-comparison-two", pairing=_pairing(CONTINUITY_SCENE_ID)),
        ),
    )

    with pytest.raises(ValueError, match="more than one pairing edge"):
        asyncio.run(
            replay_continuity_scenes(
                backstory,
                ground_truth,
                chat_handler=_dummy_handler,  # type: ignore[arg-type]
            )
        )


def test_continuity_replay_rejects_an_unpaired_single_line_scene() -> None:
    backstory, ground_truth = _continuity_package()
    extra_scene = _scene("scene-single", 3, ("line-single",))
    invalid = backstory.model_copy(
        update={
            "scenes": (*backstory.scenes, extra_scene),
            "lines": (
                *backstory.lines,
                _line("line-single", "scene-single", 1, CONTINUITY_TEXTS[0]),
            ),
        }
    )

    with pytest.raises(ValueError, match="without a paired comparison"):
        asyncio.run(
            replay_continuity_scenes(
                invalid,
                ground_truth,
                chat_handler=_dummy_handler,  # type: ignore[arg-type]
            )
        )


def test_continuity_replay_rejects_a_comparison_line_that_differs() -> None:
    backstory, ground_truth = _continuity_package()
    lines = (
        *backstory.lines[:-1],
        _line(
            "line-comparison",
            COMPARISON_SCENE_ID,
            1,
            "A different question altogether.",
        ),
    )
    invalid = backstory.model_copy(update={"lines": lines})

    with pytest.raises(ValueError, match="must repeat the final Line"):
        asyncio.run(
            replay_continuity_scenes(
                invalid,
                ground_truth,
                chat_handler=_dummy_handler,  # type: ignore[arg-type]
            )
        )


def test_continuity_replay_requires_at_least_one_pairing() -> None:
    backstory, _ = _continuity_package()
    ground_truth = _ground_truth(
        backstory,
        (_proposal(CONTINUITY_SCENE_ID), _proposal(COMPARISON_SCENE_ID)),
    )

    with pytest.raises(ValueError, match="at least one paired Scene"):
        asyncio.run(
            replay_continuity_scenes(
                backstory,
                ground_truth,
                chat_handler=_dummy_handler,  # type: ignore[arg-type]
            )
        )


def test_scene_observation_requires_a_pair_only_for_a_comparison_scene() -> None:
    turn = TurnObservation(**_turn_fields())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="paired_scene_id"):
        ContinuitySceneObservation(
            scene_id=CONTINUITY_SCENE_ID,
            role="continuity",
            paired_scene_id=COMPARISON_SCENE_ID,
            trace_id="0" * 32,
            turns=(turn,),
            session_turn_release_sources=("muse_candidate",),
            ground_truth_result="not_applicable",
            structural_findings=(),
            agent_exchanges=(),
        )

    with pytest.raises(ValueError, match="paired_scene_id"):
        ContinuitySceneObservation(
            scene_id=COMPARISON_SCENE_ID,
            role="comparison",
            paired_scene_id=None,
            trace_id="0" * 32,
            turns=(turn,),
            session_turn_release_sources=("muse_candidate",),
            ground_truth_result="matches_proposal",
            structural_findings=(),
            agent_exchanges=(),
        )


def test_turn_observation_requires_boundary_origin_for_boundary_release() -> None:
    with pytest.raises(ValueError, match="boundary_origin"):
        TurnObservation(
            **_turn_fields(  # type: ignore[arg-type]
                release_source="application_emotional_boundary",
                boundary_origin=None,
            )
        )

    with pytest.raises(ValueError, match="boundary_origin"):
        TurnObservation(
            **_turn_fields(  # type: ignore[arg-type]
                release_source="muse_candidate",
                boundary_origin="preflight",
            )
        )


def test_turn_observation_requires_a_complete_exchange_range() -> None:
    with pytest.raises(ValueError, match="both bounds or neither"):
        TurnObservation(
            **_turn_fields(exchange_sequence_first=2)  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="both bounds or neither"):
        TurnObservation(
            **_turn_fields(exchange_sequence_last=2)  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="precedes"):
        TurnObservation(
            **_turn_fields(  # type: ignore[arg-type]
                exchange_sequence_first=2,
                exchange_sequence_last=1,
            )
        )


def test_continuity_replay_grades_a_declined_comparison_turn_on_the_boundary() -> None:
    backstory, ground_truth = _continuity_package()

    async def chat_handler(
        request: ChatRequest,
        _service: MemoryPolicyService,
        _account: AccountContext,
    ) -> ChatResponse:
        release: ReleaseSource = (
            "application_safe_decline"
            if request.session_id.endswith(COMPARISON_SCENE_ID)
            else "muse_candidate"
        )
        response = _released_response(release)
        _append(request, response)
        return response

    result = asyncio.run(
        replay_continuity_scenes(backstory, ground_truth, chat_handler=chat_handler)
    )

    comparison = result.scenes[1]
    assert comparison.turns[0].release_source == "application_safe_decline"
    assert comparison.turns[0].store_messages_before == 0
    assert comparison.session_turn_release_sources == ("application_safe_decline",)
    assert comparison.structural_findings == ("unreleased_turn:line-comparison",)
    assert comparison.ground_truth_result == "matches_proposal"


def test_continuity_replay_indexes_recorded_exchanges_by_turn() -> None:
    backstory, ground_truth = _continuity_package()

    async def chat_handler(
        request: ChatRequest,
        _service: MemoryPolicyService,
        _account: AccountContext,
    ) -> ChatResponse:
        _record_exchange(request.message)
        if request.message == CONTINUITY_TEXTS[0]:
            _record_exchange(f"revision of {request.message}")
        response = _released_response()
        _append(request, response)
        return response

    result = asyncio.run(
        replay_continuity_scenes(backstory, ground_truth, chat_handler=chat_handler)
    )

    continuity, comparison = result.scenes
    ranges = [
        (turn.exchange_sequence_first, turn.exchange_sequence_last)
        for turn in continuity.turns
    ]
    assert ranges == [(1, 2), (3, 3), (4, 4), (5, 5)]
    assert len(continuity.agent_exchanges) == 5
    for turn in continuity.turns:
        assert turn.exchange_sequence_first is not None
        assert turn.exchange_sequence_last is not None
        recorded = continuity.agent_exchanges[
            turn.exchange_sequence_first - 1 : turn.exchange_sequence_last
        ]
        assert [item.sequence for item in recorded] == list(
            range(turn.exchange_sequence_first, turn.exchange_sequence_last + 1)
        )
        assert recorded[0].input_prompt == turn.input_line
    assert comparison.turns[0].exchange_sequence_first == 1
    assert comparison.turns[0].exchange_sequence_last == 1
    assert len(comparison.agent_exchanges) == 1


def _case_labels(exporter: TestExporter) -> dict[str, dict[str, dict[str, object]]]:
    spans = exporter.exported_spans_as_dict()
    cases = [span for span in spans if span["name"] == "case: {case_name}"]
    return {
        span["attributes"]["case_name"]: json.loads(span["attributes"]["labels"])
        for span in cases
    }


def test_continuity_replay_labels_every_case_with_a_role_honest_grade() -> None:
    backstory, ground_truth = _continuity_package()
    exporter = TestExporter()
    logfire.configure(
        send_to_logfire=False,
        console=False,
        inspect_arguments=False,
        additional_span_processors=[logfire.testing.SimpleSpanProcessor(exporter)],
    )

    async def chat_handler(
        request: ChatRequest,
        _service: MemoryPolicyService,
        _account: AccountContext,
    ) -> ChatResponse:
        response = _released_response()
        _append(request, response)
        return response

    asyncio.run(
        replay_continuity_scenes(backstory, ground_truth, chat_handler=chat_handler)
    )
    labels = _case_labels(exporter)

    assert set(labels) == {CONTINUITY_SCENE_ID, COMPARISON_SCENE_ID}
    continuity = labels[CONTINUITY_SCENE_ID]
    comparison = labels[COMPARISON_SCENE_ID]
    assert continuity["proposal_comparison"]["value"] == "not_applicable"
    assert comparison["proposal_comparison"]["value"] == "matches_proposal"
    # Logfire's default scrubber redacts every exported attribute path that
    # contains "session": on these case spans that covers metadata.objective_id,
    # output.session_boundary_held, output.session_turn_release_sources, and the
    # session_state_invariants label. The Ground-truth grade and the durable run
    # artifact are unaffected; the invariant label's value and reason are
    # asserted on the evaluator itself below.
    assert "session_state_invariants" in continuity
    assert "session_state_invariants" in comparison


def _evaluator_context(
    scene_id: str,
    role: SceneRole,
    output: ContinuityEvaluationOutput,
    *,
    ground_truth_status: GroundTruthStatus = "proposed",
) -> EvaluatorContext[
    ContinuityEvaluationInput,
    ContinuityEvaluationResult,
    dict[str, object],
]:
    return EvaluatorContext(
        name=scene_id,
        inputs=ContinuityEvaluationInput(
            order=1,
            scene_id=scene_id,
            role=role,
            lines=(COMPARISON_TEXT,),
        ),
        metadata=None,
        expected_output=ContinuityEvaluationExpected(
            role=role,
            paired_scene_id=CONTINUITY_SCENE_ID if role == "comparison" else None,
            ground_truth_status=ground_truth_status,
        ),
        output=output,
        duration=0.0,
        _span_tree=SpanTreeRecordingError("spans are not recorded in this test"),
        attributes={},
        metrics={},
    )


def _evaluation_output(
    role: SceneRole,
    *,
    session_boundary_held: bool | None,
    ground_truth_result: str,
    structural_findings: tuple[str, ...] = (),
) -> ContinuityEvaluationOutput:
    return ContinuityEvaluationOutput(
        role=role,
        session_boundary_held=session_boundary_held,
        ground_truth_result=ground_truth_result,  # type: ignore[arg-type]
        structural_findings=structural_findings,
        session_turn_release_sources=("muse_candidate",),
        replies=("A synthetic reviewed reply.",),
    )


def test_structural_evaluator_labels_both_scene_roles() -> None:
    evaluator = ContinuityStructuralEvaluator(ground_truth_status="proposed")

    comparison = evaluator.evaluate(
        _evaluator_context(
            COMPARISON_SCENE_ID,
            "comparison",
            _evaluation_output(
                "comparison",
                session_boundary_held=True,
                ground_truth_result="matches_proposal",
            ),
        )
    )
    assert comparison["proposal_comparison"] == "matches_proposal"
    assert comparison["session_state_invariants"].value == "held"
    assert comparison["session_state_invariants"].reason is None

    leaked = evaluator.evaluate(
        _evaluator_context(
            COMPARISON_SCENE_ID,
            "comparison",
            _evaluation_output(
                "comparison",
                session_boundary_held=False,
                ground_truth_result="differs_from_proposal",
            ),
        )
    )
    assert leaked["proposal_comparison"] == "differs_from_proposal"

    continuity = evaluator.evaluate(
        _evaluator_context(
            CONTINUITY_SCENE_ID,
            "continuity",
            _evaluation_output(
                "continuity",
                session_boundary_held=None,
                ground_truth_result="not_applicable",
            ),
        )
    )
    assert continuity["proposal_comparison"] == "not_applicable"
    assert continuity["session_state_invariants"].value == "held"
    assert continuity["session_state_invariants"].reason is None


def test_structural_evaluator_reports_findings_without_grading_them() -> None:
    evaluator = ContinuityStructuralEvaluator(ground_truth_status="proposed")
    findings = ("unreleased_turn:line-3", "turn_record_mismatch")

    continuity = evaluator.evaluate(
        _evaluator_context(
            CONTINUITY_SCENE_ID,
            "continuity",
            _evaluation_output(
                "continuity",
                session_boundary_held=None,
                ground_truth_result="not_applicable",
                structural_findings=findings,
            ),
        )
    )
    assert continuity["proposal_comparison"] == "not_applicable"
    assert continuity["session_state_invariants"].value == "deviated"
    assert continuity["session_state_invariants"].reason == ", ".join(findings)

    comparison = evaluator.evaluate(
        _evaluator_context(
            COMPARISON_SCENE_ID,
            "comparison",
            _evaluation_output(
                "comparison",
                session_boundary_held=True,
                ground_truth_result="matches_proposal",
                structural_findings=("unreleased_turn:line-comparison",),
            ),
        )
    )
    assert comparison["proposal_comparison"] == "matches_proposal"
    assert comparison["session_state_invariants"].value == "deviated"


def test_structural_evaluator_rejects_a_recomputed_grade_mismatch() -> None:
    evaluator = ContinuityStructuralEvaluator(ground_truth_status="proposed")

    with pytest.raises(ValueError, match="inconsistent"):
        evaluator.evaluate(
            _evaluator_context(
                COMPARISON_SCENE_ID,
                "comparison",
                _evaluation_output(
                    "comparison",
                    session_boundary_held=False,
                    ground_truth_result="matches_proposal",
                ),
            )
        )

    with pytest.raises(ValueError, match="inconsistent"):
        evaluator.evaluate(
            _evaluator_context(
                CONTINUITY_SCENE_ID,
                "continuity",
                _evaluation_output(
                    "continuity",
                    session_boundary_held=None,
                    ground_truth_result="matches_proposal",
                ),
            )
        )


def test_continuity_replay_labels_a_broken_session_as_deviated() -> None:
    backstory, ground_truth = _continuity_package()

    async def chat_handler(
        request: ChatRequest,
        _service: MemoryPolicyService,
        _account: AccountContext,
    ) -> ChatResponse:
        response = _released_response()
        if request.message != CONTINUITY_TEXTS[1]:
            _append(request, response)
        return response

    result = asyncio.run(
        replay_continuity_scenes(backstory, ground_truth, chat_handler=chat_handler)
    )
    evaluator = ContinuityStructuralEvaluator(ground_truth_status="proposed")
    continuity = result.scenes[0]
    labels = evaluator.evaluate(
        _evaluator_context(
            continuity.scene_id,
            continuity.role,
            _evaluation_output(
                continuity.role,
                session_boundary_held=None,
                ground_truth_result=continuity.ground_truth_result,
                structural_findings=continuity.structural_findings,
            ),
        )
    )
    reason = labels["session_state_invariants"].reason

    assert labels["proposal_comparison"] == "not_applicable"
    assert labels["session_state_invariants"].value == "deviated"
    assert "history_thread_broken:line-2" in reason
    assert "turn_record_mismatch" in reason


def _adoption(ground_truth: ProposedGroundTruth) -> GroundTruthAdoption:
    return build_ground_truth_adoption(
        ground_truth,
        ground_truth.model_dump_json().encode("utf-8"),
        reviewer_id="independent.developer@example.com",
    )


async def _clean_handler(
    request: ChatRequest,
    _service: MemoryPolicyService,
    _account: AccountContext,
) -> ChatResponse:
    response = _released_response()
    _append(request, response)
    return response


def test_continuity_replay_grades_adopted_ground_truth_with_hard_gates() -> None:
    backstory, ground_truth = _continuity_package()
    adoption = _adoption(ground_truth)

    result = asyncio.run(
        replay_continuity_scenes(
            backstory,
            ground_truth,
            adoption=adoption,
            chat_handler=_clean_handler,
        )
    )

    continuity, comparison = result.scenes
    assert result.ground_truth_status == "adopted"
    assert result.dataset_version == adoption.adopted_ground_truth_identity
    assert result.dataset_version != ground_truth.backstory_sha256
    assert comparison.ground_truth_result == "passes_hard_gates"
    assert continuity.ground_truth_result == "not_applicable"
    assert continuity.ground_truth_result not in {
        "passes_hard_gates",
        "fails_hard_gates",
    }

    evaluator = ContinuityStructuralEvaluator(ground_truth_status="adopted")
    labels = evaluator.evaluate(
        _evaluator_context(
            comparison.scene_id,
            comparison.role,
            _evaluation_output(
                comparison.role,
                session_boundary_held=True,
                ground_truth_result=comparison.ground_truth_result,
            ),
            ground_truth_status="adopted",
        )
    )
    assert set(labels) == {"adopted_hard_gate_grade", "session_state_invariants"}
    assert labels["adopted_hard_gate_grade"] == "passes_hard_gates"

    unjudged = evaluator.evaluate(
        _evaluator_context(
            continuity.scene_id,
            continuity.role,
            _evaluation_output(
                continuity.role,
                session_boundary_held=None,
                ground_truth_result=continuity.ground_truth_result,
            ),
            ground_truth_status="adopted",
        )
    )
    assert unjudged["adopted_hard_gate_grade"] == "not_applicable"
    assert unjudged["session_state_invariants"].value == "held"


def test_continuity_replay_fails_hard_gates_for_a_leaked_comparison_session() -> None:
    backstory, ground_truth = _continuity_package()
    adoption = _adoption(ground_truth)

    async def chat_handler(
        request: ChatRequest,
        _service: MemoryPolicyService,
        _account: AccountContext,
    ) -> ChatResponse:
        response = _released_response()
        _append(request, response)
        if request.session_id.endswith(CONTINUITY_SCENE_ID):
            leaked = request.session_id.replace(
                CONTINUITY_SCENE_ID, COMPARISON_SCENE_ID
            )
            sessions.append_turn(
                leaked,
                request.message,
                response.reply,
                turn_id=f"{request.turn_id}:leaked",
                release_source="muse_candidate",
            )
        return response

    result = asyncio.run(
        replay_continuity_scenes(
            backstory,
            ground_truth,
            adoption=adoption,
            chat_handler=chat_handler,
        )
    )

    continuity, comparison = result.scenes
    assert comparison.ground_truth_result == "fails_hard_gates"
    assert continuity.ground_truth_result == "not_applicable"


def test_continuity_replay_exports_adopted_cases_in_scene_order() -> None:
    backstory, ground_truth = _continuity_package()
    adoption = _adoption(ground_truth)
    exporter = TestExporter()
    logfire.configure(
        send_to_logfire=False,
        console=False,
        inspect_arguments=False,
        additional_span_processors=[logfire.testing.SimpleSpanProcessor(exporter)],
    )

    result = asyncio.run(
        replay_continuity_scenes(
            backstory,
            ground_truth,
            adoption=adoption,
            chat_handler=_clean_handler,
        )
    )
    spans = exporter.exported_spans_as_dict()
    case_names = [
        span["attributes"]["case_name"]
        for span in spans
        if span["name"] == "case: {case_name}"
    ]

    # Logfire scrubs exported values containing "session", so the experiment's
    # dataset name and metadata are asserted on the run model instead.
    assert case_names == [CONTINUITY_SCENE_ID, COMPARISON_SCENE_ID]
    assert case_names == [scene.scene_id for scene in result.scenes]
    assert result.objective_id == CONTINUITY_OBJECTIVE_ID
    assert result.dataset_version == adoption.adopted_ground_truth_identity
    assert result.ground_truth_status == "adopted"


def _muse_replies(_messages: list[object], info: AgentInfo) -> ModelResponse:
    """Return one released Muse candidate without a memory nomination."""

    tool = info.output_tools[0]
    return ModelResponse(
        parts=[
            ToolCallPart(
                tool.name,
                {
                    "reply": "A synthetic reviewed reply.",
                    "evidence_uses": [],
                    "memory": {
                        "kind": "no_memory_candidate",
                        "reason_code": "automatic_capture_disabled",
                    },
                },
            )
        ]
    )


def _provenance_passes(_messages: list[object], info: AgentInfo) -> ModelResponse:
    tool = info.output_tools[0]
    return ModelResponse(
        parts=[
            ToolCallPart(
                tool.name,
                {
                    "findings": [],
                    "response_decision": "pass",
                    "emotional_boundary_decision": "not_required",
                    "capture_decision": "no_candidate",
                },
            )
        ]
    )


def _muse_drafts(scene: object) -> list[object]:
    return [
        exchange
        for exchange in scene.agent_exchanges  # type: ignore[attr-defined]
        if exchange.role == "Muse" and exchange.stage == "draft"
    ]


def test_continuity_replay_threads_history_through_the_production_pipeline() -> None:
    backstory, ground_truth = _continuity_package()
    get_settings.cache_clear()
    try:
        with patch.dict(
            os.environ,
            {
                "LINGER_MODEL": "openai:gpt-5.6-luna",
                "OPENAI_API_KEY": "test-key",
            },
        ):
            from apps.backend import chat_turn, main

            async def chat_handler(
                request: ChatRequest,
                service: MemoryPolicyService,
                account: AccountContext,
            ) -> ChatResponse:
                return await main.chat(request, service, account)

            boundary = AsyncMock()
            boundary.return_value = EmotionalBoundaryAssessment(
                decision="continue_reflection"
            )
            with (
                patch.object(chat_turn, "assess_emotional_boundary", boundary),
                muse_chat_agent.override(model=FunctionModel(_muse_replies)),
                provenance_agent.override(model=FunctionModel(_provenance_passes)),
            ):
                result = asyncio.run(
                    replay_continuity_scenes(
                        backstory,
                        ground_truth,
                        chat_handler=chat_handler,
                    )
                )
    finally:
        get_settings.cache_clear()

    continuity, comparison = result.scenes
    assert [turn.release_source for turn in continuity.turns] == [
        "muse_candidate"
    ] * len(CONTINUITY_TEXTS)
    assert continuity.structural_findings == ()
    assert comparison.ground_truth_result == "matches_proposal"
    assert result.final_active_memory_ids == ()

    drafts = _muse_drafts(continuity)
    assert len(drafts) == len(CONTINUITY_TEXTS)
    fourth_history = drafts[-1].message_history
    assert [message["kind"] for message in fourth_history] == [
        "request",
        "response",
    ] * 3
    rendered_history = json.dumps(fourth_history)
    for text in CONTINUITY_TEXTS[:3]:
        assert text in rendered_history
    assert CONTINUITY_TEXTS[3] not in rendered_history
    assert [len(draft.message_history) for draft in drafts] == [0, 2, 4, 6]

    comparison_drafts = _muse_drafts(comparison)
    assert len(comparison_drafts) == 1
    assert comparison_drafts[0].message_history == ()
    assert COMPARISON_TEXT in comparison_drafts[0].input_prompt

    serialized = json.dumps(
        [exchange.model_dump(mode="json") for exchange in continuity.agent_exchanges]
    )
    assert backstory.backstory.context not in serialized
    assert "expected_outcomes" not in serialized
    assert "prohibited_outcomes" not in serialized


def test_continuity_replay_gates_the_comparison_scene_on_rehydrated_evidence() -> None:
    backstory, ground_truth = _continuity_package()

    async def chat_handler(
        request: ChatRequest,
        _service: MemoryPolicyService,
        _account: AccountContext,
    ) -> ChatResponse:
        leaked = request.session_id.endswith(COMPARISON_SCENE_ID)
        response = _released_response(prior_evidence_count=2 if leaked else 0)
        _append(request, response)
        return response

    result = asyncio.run(
        replay_continuity_scenes(backstory, ground_truth, chat_handler=chat_handler)
    )

    comparison = result.scenes[1]
    assert comparison.turns[0].prior_evidence_rehydrated == 2
    assert comparison.ground_truth_result == "differs_from_proposal"


def test_continuity_replay_flags_routed_agent_participation() -> None:
    backstory, ground_truth = _continuity_package()

    async def chat_handler(
        request: ChatRequest,
        _service: MemoryPolicyService,
        _account: AccountContext,
    ) -> ChatResponse:
        _record_routed_exchange("Librarian")
        response = _released_response(context_resolution_status="inferred")
        _append(request, response)
        return response

    result = asyncio.run(
        replay_continuity_scenes(backstory, ground_truth, chat_handler=chat_handler)
    )

    continuity = result.scenes[0]
    assert all(
        f"routed_agent_engaged:{turn.line_id}" in continuity.structural_findings
        for turn in continuity.turns
    )


def test_continuity_replay_does_not_flag_unrouted_agent_participation() -> None:
    backstory, ground_truth = _continuity_package()

    async def chat_handler(
        request: ChatRequest,
        _service: MemoryPolicyService,
        _account: AccountContext,
    ) -> ChatResponse:
        _record_routed_exchange("Librarian")
        response = _released_response(context_resolution_status="unknown")
        _append(request, response)
        return response

    result = asyncio.run(
        replay_continuity_scenes(backstory, ground_truth, chat_handler=chat_handler)
    )

    continuity = result.scenes[0]
    assert not any(
        finding.startswith("routed_agent_engaged")
        for finding in continuity.structural_findings
    )


def test_continuity_replay_attributes_routed_agent_findings_per_turn() -> None:
    backstory, ground_truth = _continuity_package()

    async def chat_handler(
        request: ChatRequest,
        _service: MemoryPolicyService,
        _account: AccountContext,
    ) -> ChatResponse:
        if request.message == CONTINUITY_TEXTS[0]:
            _record_routed_exchange("Librarian")
        response = _released_response(context_resolution_status="inferred")
        _append(request, response)
        return response

    result = asyncio.run(
        replay_continuity_scenes(backstory, ground_truth, chat_handler=chat_handler)
    )

    continuity = result.scenes[0]
    flagged_line_id = continuity.turns[0].line_id
    assert f"routed_agent_engaged:{flagged_line_id}" in continuity.structural_findings
    assert all(
        f"routed_agent_engaged:{turn.line_id}" not in continuity.structural_findings
        for turn in continuity.turns[1:]
    )


def test_continuity_replay_does_not_flag_resolved_context_without_routing() -> None:
    backstory, ground_truth = _continuity_package()

    async def chat_handler(
        request: ChatRequest,
        _service: MemoryPolicyService,
        _account: AccountContext,
    ) -> ChatResponse:
        response = _released_response(context_resolution_status="inferred")
        _append(request, response)
        return response

    result = asyncio.run(
        replay_continuity_scenes(backstory, ground_truth, chat_handler=chat_handler)
    )

    continuity = result.scenes[0]
    assert not any(
        finding.startswith("routed_agent_engaged")
        for finding in continuity.structural_findings
    )


def test_continuity_replay_rejects_a_non_empty_store_at_scene_entry() -> None:
    backstory, ground_truth = _continuity_package()

    async def chat_handler(
        request: ChatRequest,
        service: MemoryPolicyService,
        account: AccountContext,
    ) -> ChatResponse:
        response = _released_response()
        _append(request, response)
        if request.message == CONTINUITY_TEXTS[0]:
            service._save(  # noqa: SLF001
                account,
                text="a memory committed during the first Scene",
                source_event_id=request.turn_id or "synthetic-source",
                evidence_ids=(),
            )
        return response

    with pytest.raises(RuntimeError, match=COMPARISON_SCENE_ID):
        asyncio.run(
            replay_continuity_scenes(backstory, ground_truth, chat_handler=chat_handler)
        )


def test_continuity_replay_rejects_a_committed_memory_while_capture_is_disabled() -> (
    None
):
    backstory, ground_truth = _continuity_package()

    async def chat_handler(
        request: ChatRequest,
        service: MemoryPolicyService,
        account: AccountContext,
    ) -> ChatResponse:
        response = _released_response()
        _append(request, response)
        if request.session_id.endswith(COMPARISON_SCENE_ID):
            service._save(  # noqa: SLF001
                account,
                text="a memory committed while capture is disabled",
                source_event_id=request.turn_id or "synthetic-source",
                evidence_ids=(),
            )
        return response

    with pytest.raises(RuntimeError, match="committed memories"):
        asyncio.run(
            replay_continuity_scenes(backstory, ground_truth, chat_handler=chat_handler)
        )


def test_cli_returns_nonzero_for_an_invalid_package(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    backstory, ground_truth = _continuity_package()
    backstory_path = tmp_path / "backstory.json"
    ground_truth_path = tmp_path / "ground-truth.json"
    backstory_path.write_text(backstory.model_dump_json(), encoding="utf-8")
    tampered = ground_truth.model_copy(update={"backstory_sha256": "0" * 64})
    ground_truth_path.write_text(tampered.model_dump_json(), encoding="utf-8")

    result = continuity_main([str(backstory_path), str(ground_truth_path)])

    assert result == 1
    assert "EVALUATION_RUN_ERROR=" in capsys.readouterr().err
