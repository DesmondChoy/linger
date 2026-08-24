"""Tests for isolated capture-only Scene replay."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import logfire
import pytest
from logfire.testing import TestExporter
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)

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
from evals.synthetic_journals.models import CaptureCandidate
from evals.synthetic_journals.replay import main as replay_main
from evals.synthetic_journals.replay import (
    CAPTURE_OBJECTIVE_ID,
    RUNTIME_PROMPT_FINGERPRINTS,
    SceneObservation,
    replay_capture_scenes,
)
from evals.synthetic_journals.transcript import SceneTranscriptRecorder
from evals.synthetic_journals.validate_package import validate_package_files
from src.linger.agents.muse.models import (
    MemoryCandidate,
    MuseCandidate,
    NoMemoryCandidate,
)
from src.linger.agents.provenance.models import ProvenanceReview
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.services.memory import AccountContext, MemoryPolicyService

ROOT = Path(__file__).resolve().parents[1]
CONTENT_PATH = (
    ROOT
    / "synthetic-journal-evaluation"
    / "reviewed-automatic-memory-capture-content.json"
)
MANIFEST_PATH = (
    ROOT
    / "synthetic-journal-evaluation"
    / "reviewed-automatic-memory-capture-authoring-manifest.json"
)


def _result(output: object) -> SimpleNamespace:
    return SimpleNamespace(output=output, new_messages=lambda: [])


def _no_capture_response() -> ChatResponse:
    capture = CaptureInspection(
        nomination="no_candidate",
        provenance_decision="no_candidate",
        binding="not_applicable",
        storage="not_applicable",
        reason_code="not_applicable",
    )
    return ChatResponse(
        reply="A synthetic reviewed reply.",
        inspection=TurnInspection(
            muse_turn={},
            context_resolution={},
            traces=[],
            prompt="synthetic",
            release=ReleaseInspection(
                release_source="muse_candidate",
                provenance_verdicts=("pass",),
                finding_codes=(),
                revision_count=0,
                failure_stage=None,
                capture=capture,
            ),
        ),
        trace=TraceReference(
            trace_id="0" * 32,
        ),
    )


def test_scene_observation_requires_boundary_origin_for_boundary_release() -> None:
    capture = CaptureInspection(
        nomination="unavailable",
        provenance_decision=None,
        binding="not_applicable",
        storage="suppressed",
        reason_code="emotional_boundary_capture_suppressed",
    )
    with pytest.raises(ValueError, match="boundary_origin"):
        SceneObservation(
            scene_id="scene",
            line_id="line",
            input_line="synthetic line",
            trace_id="0" * 32,
            expected_capture_label="no_candidate",
            actual_capture_label="unavailable",
            label_comparison="differs_from_proposal",
            agent_exchanges=(),
            reply="boundary",
            release_source="application_emotional_boundary",
            boundary_origin=None,
            capture=capture,
            memory_id=None,
            stored_text=None,
        )


def test_scene_transcript_records_tool_call_and_result() -> None:
    recorder = SceneTranscriptRecorder()
    handle = recorder.begin_agent_exchange(
        role="Muse",
        stage="draft",
        input_origin="Application",
        output_receiver="Application",
        input_contract="Input.v1",
        output_contract="Output.v1",
        prompt_template_id="muse.test",
        prompt_version="1",
        prompt_digest="0" * 64,
        input_prompt='{"line":"synthetic"}',
        message_history=(),
        trace_id="0" * 32,
        span_id="0" * 16,
    )
    tool_call = ToolCallPart(
        tool_name="librarian_search",
        args={"query": "synthetic query"},
        tool_call_id="call-1",
    )
    tool_return = ToolReturnPart(
        tool_name="librarian_search",
        content={"kind": "result", "evidence": []},
        tool_call_id="call-1",
    )
    result = SimpleNamespace(
        output={"reply": "synthetic reply"},
        new_messages=lambda: (
            ModelResponse(
                parts=(
                    ThinkingPart(
                        content="hidden model reasoning",
                        signature="opaque-signature",
                    ),
                    tool_call,
                )
            ),
            ModelRequest(parts=(tool_return,)),
        ),
    )

    recorder.complete_agent_exchange(
        handle,
        result=result,
        status="success",
        failure_code=None,
    )

    exchange = recorder.exchanges[0]
    assert exchange.output == {"reply": "synthetic reply"}
    assert exchange.tool_exchanges[0].tool_name == "librarian_search"
    assert exchange.tool_exchanges[0].arguments == {"query": "synthetic query"}
    assert exchange.tool_exchanges[0].result == {"kind": "result", "evidence": []}
    assert "hidden model reasoning" not in json.dumps(exchange.model_messages)
    assert "opaque-signature" not in json.dumps(exchange.model_messages)


def test_replay_isolates_account_store_sessions_and_turns() -> None:
    content, manifest = validate_package_files(CONTENT_PATH, MANIFEST_PATH)
    requests: list[ChatRequest] = []
    accounts: set[str] = set()
    store_roots: set[Path] = set()

    async def chat_handler(
        request: ChatRequest,
        service: MemoryPolicyService,
        account: AccountContext,
    ) -> ChatResponse:
        requests.append(request)
        accounts.add(account.account_id)
        store_roots.add(service.root)
        assert service.capture_enabled(account)
        return _no_capture_response()

    result = asyncio.run(
        replay_capture_scenes(content, manifest, chat_handler=chat_handler)
    )

    lines = {line.line_id: line for line in content.lines}
    expected_messages = [
        lines[scene.line_ids[0]].text
        for scene in sorted(content.scenes, key=lambda item: item.order)
    ]
    assert [request.message for request in requests] == expected_messages
    assert len({request.session_id for request in requests}) == len(content.scenes)
    assert len({request.turn_id for request in requests}) == len(content.scenes)
    assert len(accounts) == 1
    assert len(store_roots) == 1
    assert all(not path.exists() for path in store_roots)
    assert all(not sessions.history(item.session_id) for item in requests)
    assert result.capture_enabled is True
    assert result.runtime_prompt_fingerprints == RUNTIME_PROMPT_FINGERPRINTS
    assert result.dataset_version == manifest.content_sha256
    assert result.ground_truth_status == "proposed"
    assert len(result.system_variant) == 64
    assert len(result.trace_id) == 32
    assert len({item.template_id for item in RUNTIME_PROMPT_FINGERPRINTS}) == len(
        RUNTIME_PROMPT_FINGERPRINTS
    )
    assert all(len(item.digest) == 64 for item in RUNTIME_PROMPT_FINGERPRINTS)
    assert content.backstory.evaluation_account_id not in accounts
    assert result.final_active_memory_ids == ()

    serialized_requests = json.dumps(
        [request.model_dump(mode="json") for request in requests]
    )
    assert content.backstory.context not in serialized_requests
    assert "expected_outcomes" not in serialized_requests
    assert "prohibited_outcomes" not in serialized_requests
    assert "runtime_prompt_fingerprints" not in content.model_dump(mode="json")


def test_replay_rejects_more_than_one_line_per_scene() -> None:
    content, manifest = validate_package_files(CONTENT_PATH, MANIFEST_PATH)
    first_scene = content.scenes[0].model_copy(
        update={"line_ids": (content.lines[0].line_id, content.lines[1].line_id)}
    )
    invalid = content.model_copy(
        update={"scenes": (first_scene, *content.scenes[1:])}
    )

    with pytest.raises(ValueError, match="exactly one Line"):
        asyncio.run(
            replay_capture_scenes(
                invalid,
                manifest,
                chat_handler=lambda *args: None,  # type: ignore[arg-type]
            )
        )


def test_replay_exports_native_evaluation_cases_with_synthetic_content() -> None:
    content, manifest = validate_package_files(CONTENT_PATH, MANIFEST_PATH)
    exporter = TestExporter()
    logfire.configure(
        send_to_logfire=False,
        console=False,
        inspect_arguments=False,
        additional_span_processors=[logfire.testing.SimpleSpanProcessor(exporter)],
    )

    async def chat_handler(
        _request: ChatRequest,
        _service: MemoryPolicyService,
        _account: AccountContext,
    ) -> ChatResponse:
        return _no_capture_response()

    result = asyncio.run(
        replay_capture_scenes(content, manifest, chat_handler=chat_handler)
    )
    spans = exporter.exported_spans_as_dict()
    payload = json.dumps(spans, default=str)
    experiment = next(span for span in spans if span["name"] == "evaluate {name}")
    cases = [span for span in spans if span["name"] == "case: {case_name}"]

    assert experiment["attributes"]["gen_ai.operation.name"] == "experiment"
    assert experiment["attributes"]["dataset_name"] == CAPTURE_OBJECTIVE_ID
    assert result.run_id in experiment["attributes"]["metadata"]
    assert manifest.content_sha256 in experiment["attributes"]["metadata"]
    assert len(cases) == 11
    assert {span["attributes"]["case_name"] for span in cases} == {
        scene.scene_id for scene in content.scenes
    }
    assert {
        json.loads(span["attributes"]["inputs"])["line"] for span in cases
    } == {line.text for line in content.lines}
    assert "A synthetic reviewed reply." in payload
    assert {
        json.loads(span["attributes"]["expected_output"])["ground_truth_status"]
        for span in cases
    } == {"proposed"}
    comparisons = {
        json.loads(span["attributes"]["labels"])["proposal_comparison"]["value"]
        for span in cases
    }
    assert comparisons == {"matches_proposal", "differs_from_proposal"}


def test_cli_returns_nonzero_for_an_invalid_package(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = replay_main(
        [
            str(tmp_path / "missing-content.json"),
            str(tmp_path / "missing-manifest.json"),
        ]
    )

    assert result == 1
    assert "EVALUATION_RUN_ERROR=" in capsys.readouterr().err


def test_replay_uses_production_capture_path_without_handing_off_labels() -> None:
    content, manifest = validate_package_files(CONTENT_PATH, MANIFEST_PATH)
    lines = {line.line_id: line for line in content.lines}
    scenes_by_text = {
        lines[scene.line_ids[0]].text: scene.scene_id for scene in content.scenes
    }
    proposals = {proposal.scene_id: proposal for proposal in manifest.proposals}
    muse_payloads: list[dict[str, object]] = []
    histories: list[list[object]] = []

    async def muse_run(prompt: str, **kwargs: object) -> SimpleNamespace:
        payload = json.loads(prompt)
        muse_payloads.append(payload)
        histories.append(list(kwargs.get("message_history", [])))
        source = payload["muse_turn"]["user_message"]
        proposal = proposals[scenes_by_text[source]]
        if isinstance(proposal.capture, CaptureCandidate):
            span = proposal.capture.span
            memory = MemoryCandidate(
                kind="memory_candidate",
                text=span.text,
                start_codepoint=span.start_codepoint,
                end_codepoint=span.end_codepoint,
                reason_code="durable_reflection",
            )
        else:
            memory = NoMemoryCandidate(
                kind="no_memory_candidate",
                reason_code="transient_or_low_signal",
            )
        return _result(
            MuseCandidate(reply="A synthetic reviewed reply.", memory=memory)
        )

    async def provenance_run(prompt: str, **_: object) -> SimpleNamespace:
        payload = json.loads(prompt)
        proposal = proposals[scenes_by_text[payload["current_line"]["text"]]]
        decision = (
            "allow_capture"
            if isinstance(proposal.capture, CaptureCandidate)
            else "no_candidate"
        )
        return _result(
            ProvenanceReview(
                findings=(),
                response_decision="pass",
                emotional_boundary_decision="not_required",
                capture_decision=decision,
            )
        )

    get_settings.cache_clear()
    try:
        with patch.dict(
            os.environ,
            {
                "LINGER_MODEL": "openai:gpt-5.6-luna",
                "OPENAI_API_KEY": "test-key",
            },
        ):
            from apps.backend import main

            muse = AsyncMock()
            muse.run.side_effect = muse_run
            provenance = AsyncMock()
            provenance.run.side_effect = provenance_run
            boundary = AsyncMock()
            boundary.return_value = EmotionalBoundaryAssessment(
                decision="continue_reflection"
            )
            with (
                patch.object(main, "assess_emotional_boundary", boundary),
                patch.object(main, "muse_chat_agent", muse),
                patch.object(main, "provenance_agent", provenance),
            ):
                result = asyncio.run(
                    replay_capture_scenes(
                        content,
                        manifest,
                        chat_handler=main.chat,
                    )
                )
    finally:
        get_settings.cache_clear()

    committed = [scene for scene in result.scenes if scene.memory_id is not None]
    expected_span = next(
        proposal.capture.span
        for proposal in manifest.proposals
        if isinstance(proposal.capture, CaptureCandidate)
    )
    assert len(committed) == 1
    assert committed[0].stored_text == expected_span.text
    assert len(result.final_active_memory_ids) == 1
    assert all(scene.boundary_origin is None for scene in result.scenes)
    assert all(
        scene.label_comparison == "matches_proposal" for scene in result.scenes
    )
    assert all(
        [exchange.role for exchange in scene.agent_exchanges]
        == ["Muse", "Provenance"]
        for scene in result.scenes
    )
    assert all(
        scene.agent_exchanges[0].input_origin == "Application"
        and scene.agent_exchanges[0].output_origin == "Muse"
        and scene.agent_exchanges[1].input_origin == "Muse"
        and scene.agent_exchanges[1].input_receiver == "Provenance"
        for scene in result.scenes
    )
    assert all(
        scene.input_line in scene.agent_exchanges[0].input_prompt
        for scene in result.scenes
    )
    assert all(history == [] for history in histories)

    serialized_payloads = json.dumps(muse_payloads)
    assert content.backstory.context not in serialized_payloads
    assert "expected_outcomes" not in serialized_payloads
    assert "prohibited_outcomes" not in serialized_payloads
    assert "runtime_prompt_fingerprints" not in manifest.model_dump(mode="json")
