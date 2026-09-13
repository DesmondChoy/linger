"""Combined replay preserves each Objective's inputs, identity, and grading boundary."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import logfire
import pytest
from logfire.testing import TestExporter
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from apps.backend import sessions
from apps.backend.schemas import ChatRequest, ChatResponse
from evals.synthetic_journals.adoption import build_ground_truth_adoption
from evals.synthetic_journals.capture_curation_replay import (
    EVALUATION_NAME,
    OBJECTIVE_IDS,
    CaptureCurationEvaluationRun,
    main as combined_main,
    replay_capture_curation_scenes,
)
from evals.synthetic_journals.curation_replay import (
    CurationSceneObservation,
    replay_curation_scenes,
)
from evals.synthetic_journals.models import (
    CaptureCandidate,
    ProposedGroundTruth,
    SyntheticBackstory,
)
from evals.synthetic_journals.replay import SceneObservation, replay_capture_scenes
from evals.synthetic_journals.validate_scenario import (
    DEFAULT_RUN_CONFIGURATION_DIRECTORY,
    load_run_configurations,
    validate_scenario,
)
from src.linger.agents.muse.agent import muse_chat_agent
from src.linger.agents.provenance.agent import provenance_agent
from src.linger.agents.sculptor.agent import sculptor_agent
from src.linger.agents.sculptor.models import (
    AccountScopedMemories,
    NoCurationProposal,
    SculptorResponse,
)
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.orchestration.curation import propose_curation
from src.linger.services.memory import AccountContext, MemoryPolicyService
from tests.test_synthetic_curation_replay import _curation_documents, _json_bytes, _response_for
from tests.test_synthetic_journal_replay import (
    BACKSTORY_PATH,
    GROUND_TRUTH_PATH,
    _no_capture_response,
)


def _combined_documents() -> tuple[dict[str, object], dict[str, object], bytes]:
    """Compose existing test fixtures under one Backstory without writing a Scenario."""

    backstory = json.loads(BACKSTORY_PATH.read_text(encoding="utf-8"))
    ground_truth = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    curation, curation_truth, _ = _curation_documents()
    backstory["objective_ids"] = list(OBJECTIVE_IDS)
    for prop in curation["props"]:
        for key in ("backstory_id", "person_id", "evaluation_account_id"):
            prop[key] = backstory["backstory"][key]
    for scene in curation["scenes"]:
        scene["backstory_id"] = backstory["backstory"]["backstory_id"]
        scene["order"] += len(backstory["scenes"])
    backstory["props"] = curation["props"]
    backstory["scenes"].extend(curation["scenes"])
    ground_truth["proposals"].extend(curation_truth["proposals"])
    backstory_bytes = _json_bytes(backstory)
    ground_truth["backstory_sha256"] = hashlib.sha256(backstory_bytes).hexdigest()
    return backstory, ground_truth, backstory_bytes


def _combined_models(
    *, reverse_objectives: bool = False, interleave: bool = False
) -> tuple[SyntheticBackstory, ProposedGroundTruth, bytes, bytes]:
    document, proposals, _ = _combined_documents()
    if reverse_objectives:
        document["objective_ids"].reverse()
    if interleave:
        scenes = document["scenes"]
        document["scenes"] = [*scenes[:7], *scenes[11:], *scenes[7:11]]
        for order, scene in enumerate(document["scenes"], start=1):
            scene["order"] = order
    backstory_bytes = _json_bytes(document)
    proposals["backstory_sha256"] = hashlib.sha256(backstory_bytes).hexdigest()
    ground_truth_bytes = _json_bytes(proposals)
    return (
        SyntheticBackstory.model_validate_json(backstory_bytes),
        ProposedGroundTruth.model_validate_json(ground_truth_bytes),
        backstory_bytes,
        ground_truth_bytes,
    )


def _payload(messages: list[object]) -> dict[str, object]:
    return json.loads(next(
        part.content
        for message in reversed(messages)
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    ))


@pytest.mark.parametrize("reverse_objectives", [False, True])
@pytest.mark.parametrize("interleave", [False, True])
def test_combined_replay_uses_production_handlers_and_original_adoption(
    reverse_objectives: bool, interleave: bool
) -> None:
    from apps.backend.chat_turn import run_chat_turn

    backstory, ground_truth, backstory_bytes, ground_truth_bytes = _combined_models(
        reverse_objectives=reverse_objectives, interleave=interleave
    )
    validate_scenario(
        backstory, ground_truth, backstory_bytes=backstory_bytes,
        run_configurations=load_run_configurations(DEFAULT_RUN_CONFIGURATION_DIRECTORY),
    )
    adoption = build_ground_truth_adoption(
        ground_truth, ground_truth_bytes, reviewer_id="independent.reviewer@example.com"
    )
    original = (
        backstory.model_dump_json(),
        ground_truth.model_dump_json(),
        adoption.model_dump_json(),
    )
    proposals = {proposal.scene_id: proposal for proposal in ground_truth.proposals}
    scenes_by_text = {
        line.text: next(scene for scene in backstory.scenes if scene.scene_id == line.scene_id)
        for line in backstory.lines
    }
    source_payloads: list[dict[str, object]] = []
    requests: list[ChatRequest] = []
    capture_store_counts: list[int] = []
    account_scopes: set[str] = set()
    roots: set[Path] = set()
    execution_order: list[str] = []
    curation_batches: list[AccountScopedMemories] = []

    def muse(messages: list[object], info: AgentInfo) -> ModelResponse:
        payload = _payload(messages)
        source_payloads.append(payload)
        scene = scenes_by_text[payload["muse_turn"]["user_message"]]
        nomination = proposals[scene.scene_id].capture.nomination
        memory = (
            {
                "kind": "memory_candidate",
                "text": nomination.span.text,
                "start_codepoint": nomination.span.start_codepoint,
                "end_codepoint": nomination.span.end_codepoint,
                "reason_code": "durable_reflection",
            }
            if isinstance(nomination, CaptureCandidate)
            else {"kind": "no_memory_candidate", "reason_code": "transient_or_low_signal"}
        )
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "reply": "A synthetic reviewed reply.", "memory": memory,
        })])

    def provenance(messages: list[object], info: AgentInfo) -> ModelResponse:
        payload = _payload(messages)
        source_payloads.append(payload)
        scene = scenes_by_text[payload["current_line"]["text"]]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "findings": [],
            "response_decision": "pass",
            "emotional_boundary_decision": "not_required",
            "capture_decision": proposals[scene.scene_id].capture.provenance_decision,
        })])

    def sculptor(messages: list[object], info: AgentInfo) -> ModelResponse:
        payload = _payload(messages)
        source_payloads.append(payload)
        assert info.function_tools == []
        batch = AccountScopedMemories(account_scope="test-only", memories=payload["memories"])
        response = _response_for(batch, ground_truth)
        output_tool = next(
            tool for tool in info.output_tools if type(response).__name__ in tool.name
        )
        return ModelResponse(parts=[
            ToolCallPart(output_tool.name, response.model_dump(mode="json"))
        ])

    async def chat(
        request: ChatRequest, service: MemoryPolicyService, account: AccountContext
    ) -> ChatResponse:
        assert not sessions.history(request.session_id)
        requests.append(request)
        account_scopes.add(account.account_id)
        roots.add(service.root)
        capture_store_counts.append(len(service.list_active(account)))
        execution_order.append(scenes_by_text[request.message].scene_id)
        assert not {prop.prop_id for prop in backstory.props} & {
            record.memory_id for record in service.list_active(account)
        }
        return await run_chat_turn(request, service, account)

    async def curate(batch: AccountScopedMemories) -> SculptorResponse:
        account_scopes.add(batch.account_scope)
        curation_batches.append(batch)
        scene = next(scene for scene in backstory.scenes if scene.prop_ids == tuple(
            memory.memory_id for memory in batch.memories
        ))
        execution_order.append(scene.scene_id)
        return await propose_curation(batch)

    with (
        patch("apps.backend.chat_turn.assess_emotional_boundary", AsyncMock(
            return_value=EmotionalBoundaryAssessment(decision="continue_reflection")
        )),
        muse_chat_agent.override(model=FunctionModel(muse)),
        provenance_agent.override(model=FunctionModel(provenance)),
        sculptor_agent.override(model=FunctionModel(sculptor)),
    ):
        result = asyncio.run(replay_capture_curation_scenes(
            backstory, ground_truth, adoption=adoption, chat_handler=chat,
            curation_handler=curate, configured_model="function:combined-test",
        ))

    assert result.objective_ids == backstory.objective_ids
    assert result.dataset_version == adoption.adopted_ground_truth_identity
    assert result.backstory_sha256 == hashlib.sha256(backstory_bytes).hexdigest()
    assert result.proposed_ground_truth_sha256 == hashlib.sha256(ground_truth_bytes).hexdigest()
    assert execution_order == [scene.scene_id for scene in backstory.scenes]
    assert [scene.scene_id for scene in result.scenes] == execution_order
    assert all(scene.ground_truth_result == "passes_hard_gates" for scene in result.scenes)
    assert len(result.scenes) == 16
    assert len(account_scopes) == len(roots) == 1
    assert all(not root.exists() for root in roots)
    assert len({request.session_id for request in requests}) == 11
    assert all(not sessions.history(request.session_id) for request in requests)
    assert capture_store_counts == [0] * 7 + [1] * 4
    assert len(result.final_active_memory_ids) == 1
    capture_observations = [
        scene for scene in result.scenes if isinstance(scene, SceneObservation)
    ]
    curation_observations = [
        scene for scene in result.scenes if isinstance(scene, CurationSceneObservation)
    ]
    assert len(capture_observations) == 11
    assert len(curation_observations) == len(curation_batches) == 5
    assert all(scene.hard_failures == () for scene in capture_observations)
    assert all(scene.grade.hard_pass and scene.source_hashes_before == scene.source_hashes_after
               for scene in curation_observations)
    assert sum(scene.grade.semantic_review_required for scene in curation_observations) == 2
    assert all([exchange.role for exchange in scene.agent_exchanges] == ["Sculptor"]
               for scene in curation_observations)
    assert all(
        {memory.memory_id for memory in scene.input_memories}.isdisjoint(
            result.final_active_memory_ids
        )
        for scene in curation_observations
    )
    assert original == (
        backstory.model_dump_json(),
        ground_truth.model_dump_json(),
        adoption.model_dump_json(),
    )
    prompts = json.dumps(source_payloads)
    for forbidden in (backstory.backstory.context, "expected_outcomes", "prohibited_outcomes",
                      "ground_truth_status", "semantic_review", "primary_behavior"):
        assert forbidden not in prompts
    restored = CaptureCurationEvaluationRun.model_validate_json(result.model_dump_json())
    assert restored.model_dump(mode="json") == result.model_dump(mode="json")


def test_combined_replay_emits_one_ordered_native_evaluation() -> None:
    backstory, ground_truth, _, _ = _combined_models(interleave=True)
    exporter = TestExporter()
    logfire.configure(send_to_logfire=False, console=False, inspect_arguments=False,
                      additional_span_processors=[logfire.testing.SimpleSpanProcessor(exporter)])

    async def chat(_request, _service, _account):
        return _no_capture_response()

    async def curate(batch):
        if batch.memories[0].memory_id == "prop-exact-1":
            return NoCurationProposal(
                kind="no_curation_proposal", reason="Test missed the duplicate."
            )
        return _response_for(batch, ground_truth)

    result = asyncio.run(replay_capture_curation_scenes(
        backstory, ground_truth, chat_handler=chat, curation_handler=curate,
        configured_model="function:test",
    ))
    failed_capture = next(
        scene for scene in result.scenes
        if isinstance(scene, SceneObservation) and scene.hard_failures
    )
    failed_curation = next(
        scene for scene in result.scenes
        if isinstance(scene, CurationSceneObservation) and not scene.grade.hard_pass
    )
    assert "capture_nomination_mismatch" in failed_capture.hard_failures
    assert failed_curation.grade.failures == ("expected_curation_proposal",)
    assert failed_curation.response.kind == "no_curation_proposal"
    assert failed_curation.ground_truth_result == "differs_from_proposal"
    spans = exporter.exported_spans_as_dict()
    experiments = [span for span in spans if span["name"] == "evaluate {name}"]
    assert len(experiments) == 1
    assert experiments[0]["attributes"]["dataset_name"] == EVALUATION_NAME
    metadata = experiments[0]["attributes"]["metadata"]
    assert result.run_id in metadata and ground_truth.backstory_sha256 in metadata
    assert all(objective in metadata for objective in OBJECTIVE_IDS)
    cases = [span for span in spans if span["name"] == "case: {case_name}"]
    assert len(cases) == 16
    assert [case["attributes"]["case_name"] for case in cases] == [
        scene.scene_id for scene in backstory.scenes
    ]
    assert {
        json.loads(case["attributes"]["labels"])["proposal_comparison"]["value"]
        for case in cases
    } == {
        "matches_proposal", "differs_from_proposal",
    }


@pytest.mark.parametrize("objective_ids", [(OBJECTIVE_IDS[0],), (OBJECTIVE_IDS[1],),
    (*OBJECTIVE_IDS, "proactive_memory_surfacing")])
def test_combined_replay_rejects_unsupported_objective_selections(objective_ids) -> None:
    backstory, ground_truth, _, _ = _combined_models()
    with pytest.raises(ValueError, match="combined replay requires"):
        asyncio.run(replay_capture_curation_scenes(
            backstory.model_copy(update={"objective_ids": objective_ids}), ground_truth,
        ))


@pytest.mark.parametrize("change, error", [
    ({"objective_ids": OBJECTIVE_IDS}, "exactly one"),
    ({"fresh_session": False}, "fresh session"),
    ({"prop_ids": ("prop-exact-1",)}, "cannot use Props"),
])
def test_combined_replay_rejects_unsupported_scene_topologies(change, error) -> None:
    backstory, ground_truth, _, _ = _combined_models()
    scenes = (backstory.scenes[0].model_copy(update=change), *backstory.scenes[1:])
    with pytest.raises(ValueError, match=error):
        asyncio.run(replay_capture_curation_scenes(
            backstory.model_copy(update={"scenes": scenes}), ground_truth
        ))


def test_single_objective_replays_continue_to_reject_combined_input() -> None:
    backstory, ground_truth, _, _ = _combined_models()
    for replay in (replay_capture_scenes, replay_curation_scenes):
        with pytest.raises(ValueError, match="requires only"):
            asyncio.run(replay(backstory, ground_truth))


@pytest.mark.parametrize("handler_name", ["chat_handler", "curation_handler"])
def test_combined_model_label_requires_both_injected_handlers(handler_name: str) -> None:
    backstory, ground_truth, _, _ = _combined_models()
    with pytest.raises(ValueError, match="requires both injected"):
        asyncio.run(replay_capture_curation_scenes(
            backstory,
            ground_truth,
            configured_model="function:shared-test-model",
            **{handler_name: AsyncMock()},
        ))


def test_combined_cli_rejects_invalid_scenario_before_replay(tmp_path: Path) -> None:
    with patch(
        "evals.synthetic_journals.capture_curation_replay.replay_capture_curation_scenes"
    ) as replay:
        assert combined_main([
            str(tmp_path / "missing"), str(tmp_path / "missing-ground-truth")
        ]) == 1
    replay.assert_not_called()


@pytest.mark.parametrize("tamper", [False, True])
def test_combined_cli_validates_original_complete_files_and_adoption(
    tmp_path: Path, tamper: bool
) -> None:
    backstory, ground_truth, backstory_bytes, ground_truth_bytes = _combined_models()
    adoption = build_ground_truth_adoption(
        ground_truth, ground_truth_bytes, reviewer_id="independent.reviewer@example.com"
    )
    backstory_path = tmp_path / "backstory.json"
    ground_truth_path = tmp_path / "ground-truth.json"
    adoption_path = tmp_path / "ground-truth-adoption.json"
    backstory_path.write_bytes(backstory_bytes)
    ground_truth_path.write_bytes(ground_truth_bytes + (b"\n" if tamper else b""))
    adoption_path.write_text(adoption.model_dump_json(), encoding="utf-8")
    with patch(
        "evals.synthetic_journals.capture_curation_replay.replay_capture_curation_scenes",
        new_callable=AsyncMock,
    ) as replay:
        replay.return_value.model_dump_json = lambda **_: "{}"
        result = combined_main([
            str(backstory_path), str(ground_truth_path), "--adoption", str(adoption_path),
        ])
    if tamper:
        assert result == 1
        replay.assert_not_called()
    else:
        assert result == 0
        replay.assert_awaited_once_with(backstory, ground_truth, adoption=adoption)
