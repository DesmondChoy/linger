"""Tests for isolated capture-only Scene replay."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import replace
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
from evals.synthetic_journals.adoption import build_ground_truth_adoption
from evals.synthetic_journals.models import CaptureCandidate, NoCandidate
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
    MemoryNomination,
    MuseCandidate,
    NoMemoryCandidate,
)
from src.linger.agents.provenance.models import ProvenanceReview
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.evaluation_transcript import active_evaluation_transcript_sink
from src.linger.services.memory import (
    AccountContext,
    AutomaticMemoryCandidate,
    MemoryConflictError,
    MemoryPolicyService,
)

ROOT = Path(__file__).resolve().parents[1]
BACKSTORY_PATH = (
    ROOT
    / "synthetic-journal-evaluation"
    / "packages"
    / "2026-08-23T182725+0800"
    / "backstory.json"
)
GROUND_TRUTH_PATH = (
    ROOT
    / "synthetic-journal-evaluation"
    / "packages"
    / "2026-08-23T182725+0800"
    / "ground-truth.json"
)


def _result(output: object) -> SimpleNamespace:
    return SimpleNamespace(output=output, new_messages=lambda: [])


def _no_capture_response(
    nomination: MemoryNomination | None = None, *, stage: str = "draft"
) -> ChatResponse:
    sink = active_evaluation_transcript_sink()
    if sink is not None:
        handle = sink.begin_agent_exchange(
            role="Muse",
            stage=stage,
            input_origin="Application",
            output_receiver="Application",
            input_contract="Input.v1",
            output_contract="src.linger.agents.muse.models.MuseCandidate",
            prompt_template_id="muse.test",
            prompt_version="1",
            prompt_digest="0" * 64,
            input_prompt="synthetic input",
            message_history=(),
            trace_id="0" * 32,
            span_id="0" * 16,
        )
        sink.complete_agent_exchange(
            handle,
            result=_result(MuseCandidate(
                reply="A synthetic reviewed reply.",
                memory=nomination or NoMemoryCandidate(
                    kind="no_memory_candidate", reason_code="transient_or_low_signal"
                ),
            )),
            status="success",
            failure_code=None,
        )
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
                revision_count=int(stage == "revision"),
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
            expected_capture=NoCandidate(kind="no_candidate"),
            actual_capture_label="unavailable",
            actual_nomination=None,
            ground_truth_result="differs_from_proposal",
            hard_failures=("release_source_mismatch",),
            agent_exchanges=(),
            reply="boundary",
            release_source="application_emotional_boundary",
            boundary_origin=None,
            capture=capture,
            memory_id=None,
            stored_text=None,
            stored_record_count=0,
            created_memory_ids=(),
            existing_memories_unchanged=True,
            retry=None,
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
    content, ground_truth = validate_package_files(BACKSTORY_PATH, GROUND_TRUTH_PATH)
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
        replay_capture_scenes(content, ground_truth, chat_handler=chat_handler)
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
    assert result.dataset_version == ground_truth.backstory_sha256
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


def test_replay_grades_adopted_ground_truth_with_adoption_identity() -> None:
    content, ground_truth = validate_package_files(BACKSTORY_PATH, GROUND_TRUTH_PATH)
    adoption = build_ground_truth_adoption(
        ground_truth,
        GROUND_TRUTH_PATH.read_bytes(),
        reviewer_id="independent.developer@example.com",
    )

    async def chat_handler(
        _request: ChatRequest,
        _service: MemoryPolicyService,
        _account: AccountContext,
    ) -> ChatResponse:
        return _no_capture_response()

    result = asyncio.run(
        replay_capture_scenes(
            content,
            ground_truth,
            adoption=adoption,
            chat_handler=chat_handler,
        )
    )

    assert result.ground_truth_status == "adopted"
    assert result.dataset_version == adoption.adopted_ground_truth_identity
    assert {scene.ground_truth_result for scene in result.scenes} == {
        "passes_hard_gates",
        "fails_hard_gates",
    }


def test_replay_fails_a_nominated_positive_that_was_not_stored() -> None:
    content, ground_truth = validate_package_files(BACKSTORY_PATH, GROUND_TRUTH_PATH)
    positive = next(
        proposal for proposal in ground_truth.proposals
        if isinstance(proposal.capture, CaptureCandidate)
    )
    positive_line = next(
        line.text for line in content.lines
        if line.line_id == positive.capture.span.source_id
    )

    async def chat_handler(request, _service, _account):
        response = _no_capture_response()
        if request.message == positive_line:
            response.inspection.release.capture = CaptureInspection(
                nomination="candidate",
                provenance_decision="reject_capture",
                binding="invalid",
                storage="refused",
                reason_code="invalid_capture_binding",
            )
        return response

    result = asyncio.run(
        replay_capture_scenes(content, ground_truth, chat_handler=chat_handler)
    )
    observation = next(s for s in result.scenes if s.scene_id == positive.scene_id)
    assert result.final_active_memory_ids == ()
    assert observation.ground_truth_result == "differs_from_proposal"
    assert "capture_review_mismatch" in observation.hard_failures
    assert "capture_binding_mismatch" in observation.hard_failures
    assert "capture_storage_mismatch" in observation.hard_failures
    assert "stored_record_count_mismatch" in observation.hard_failures


@pytest.mark.parametrize(
    ("fault", "failure"),
    [
        ("none", None),
        ("revised_nomination", None),
        ("wrong_offsets", "nominated_span_mismatch"),
        ("wrong_text", "stored_text_mismatch"),
        ("wrong_review", "capture_review_mismatch"),
        ("wrong_binding", "capture_binding_mismatch"),
        ("safe_decline", "release_source_mismatch"),
        ("extra_write", "unexpected_memory_writes"),
        ("wrong_event", "stored_record_count_mismatch"),
        ("duplicate_retry", "capture_retry_not_idempotent"),
        ("failed_retry", "capture_retry_not_idempotent"),
    ],
)
def test_capture_replay_grades_observed_outcomes(
    fault: str, failure: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    content, ground_truth = validate_package_files(BACKSTORY_PATH, GROUND_TRUTH_PATH)
    proposal = next(
        item for item in ground_truth.proposals
        if isinstance(item.capture, CaptureCandidate)
    )
    assert isinstance(proposal.capture, CaptureCandidate)
    span = proposal.capture.span
    positive_line = next(
        line.text for line in content.lines if line.line_id == span.source_id
    )

    async def chat_handler(request, service, account):
        if request.message != positive_line:
            return _no_capture_response()
        nomination = MemoryCandidate(
            kind="memory_candidate",
            text=span.text,
            start_codepoint=span.start_codepoint,
            end_codepoint=span.end_codepoint,
            reason_code="durable_reflection",
        )
        wrong_nomination = nomination.model_copy(update={
            "start_codepoint": span.start_codepoint + 1,
            "end_codepoint": span.end_codepoint + 1,
        })
        if fault == "revised_nomination":
            _no_capture_response(wrong_nomination)
        response = _no_capture_response(
            wrong_nomination if fault == "wrong_offsets" else nomination,
            stage="revision" if fault == "revised_nomination" else "draft",
        )
        candidate = AutomaticMemoryCandidate(
            text="An unsupported substitute." if fault == "wrong_text" else span.text,
            source_event_id=request.turn_id + (":wrong" if fault == "wrong_event" else ""),
            review_allows_capture=True,
            contains_sensitive_content=False,
        )
        service.save_automatic(account, candidate)
        if fault == "extra_write":
            service.save_automatic(
                account, replace(candidate, source_event_id=request.turn_id + ":extra")
            )
        if fault == "duplicate_retry":
            save = service.save_automatic

            def duplicate_retry(context, retry_candidate):
                return save(context, replace(
                    retry_candidate, source_event_id=retry_candidate.source_event_id + ":duplicate"
                ))

            monkeypatch.setattr(service, "save_automatic", duplicate_retry)
        elif fault == "failed_retry":
            def failed_retry(_context, _candidate):
                raise MemoryConflictError("conflicting retry")

            monkeypatch.setattr(service, "save_automatic", failed_retry)
        release = response.inspection.release
        assert release is not None
        release.capture = CaptureInspection(
            nomination="candidate",
            provenance_decision="reject_capture" if fault == "wrong_review" else "allow_capture",
            binding="invalid" if fault == "wrong_binding" else "exact",
            storage="committed",
            reason_code=None,
        )
        if fault == "safe_decline":
            release.release_source = "application_safe_decline"
        return response

    result = asyncio.run(
        replay_capture_scenes(content, ground_truth, chat_handler=chat_handler)
    )
    observation = next(scene for scene in result.scenes if scene.scene_id == proposal.scene_id)
    if failure is None:
        assert observation.ground_truth_result == "matches_proposal"
        assert observation.hard_failures == ()
        assert observation.retry is not None
        assert observation.retry.created is False
        assert observation.retry.store_unchanged
        assert len(result.final_active_memory_ids) == 1
    else:
        assert observation.ground_truth_result == "differs_from_proposal"
        assert failure in observation.hard_failures
    assert result.artifact_schema_version == "2"
    assert observation.expected_capture == proposal.capture
    if fault == "failed_retry":
        assert observation.retry.error == "MemoryConflictError"
        assert observation.retry.store_unchanged
        assert observation.retry.original_unchanged


def test_replay_rejects_unexpected_writes_and_changes_to_earlier_memories() -> None:
    content, ground_truth = validate_package_files(BACKSTORY_PATH, GROUND_TRUTH_PATH)
    calls = 0
    stored = None

    async def chat_handler(request, service, account):
        nonlocal calls, stored
        calls += 1
        if calls == 1:
            stored = service.save_automatic(account, AutomaticMemoryCandidate(
                text="An unexpected memory.",
                source_event_id=request.turn_id,
                review_allows_capture=True,
                contains_sensitive_content=False,
            )).record
        elif calls == 2:
            path = service.root / stored.account_key / f"{stored.idempotency_key}.md"
            path.write_text(path.read_text().replace(stored.text, "An altered memory."))
        return _no_capture_response()

    result = asyncio.run(
        replay_capture_scenes(content, ground_truth, chat_handler=chat_handler)
    )
    assert "unexpected_memory_writes" in result.scenes[0].hard_failures
    assert "stored_record_count_mismatch" in result.scenes[0].hard_failures
    assert "existing_memories_changed" in result.scenes[1].hard_failures
    assert all(
        scene.ground_truth_result == "differs_from_proposal"
        for scene in result.scenes[:2]
    )


def test_replay_cannot_pass_without_recorded_muse_output() -> None:
    content, ground_truth = validate_package_files(BACKSTORY_PATH, GROUND_TRUTH_PATH)
    response = _no_capture_response()

    async def chat_handler(_request, _service, _account):
        return response

    result = asyncio.run(
        replay_capture_scenes(content, ground_truth, chat_handler=chat_handler)
    )
    assert all("muse_nomination_unavailable" in scene.hard_failures for scene in result.scenes)
    assert all(scene.ground_truth_result == "differs_from_proposal" for scene in result.scenes)


def test_replay_rejects_more_than_one_line_per_scene() -> None:
    content, ground_truth = validate_package_files(BACKSTORY_PATH, GROUND_TRUTH_PATH)
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
                ground_truth,
                chat_handler=lambda *args: None,  # type: ignore[arg-type]
            )
        )


def test_replay_exports_native_evaluation_cases_with_synthetic_backstory() -> None:
    content, ground_truth = validate_package_files(BACKSTORY_PATH, GROUND_TRUTH_PATH)
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
        replay_capture_scenes(content, ground_truth, chat_handler=chat_handler)
    )
    spans = exporter.exported_spans_as_dict()
    payload = json.dumps(spans, default=str)
    experiment = next(span for span in spans if span["name"] == "evaluate {name}")
    cases = [span for span in spans if span["name"] == "case: {case_name}"]

    assert experiment["attributes"]["gen_ai.operation.name"] == "experiment"
    assert experiment["attributes"]["dataset_name"] == CAPTURE_OBJECTIVE_ID
    assert result.run_id in experiment["attributes"]["metadata"]
    assert ground_truth.backstory_sha256 in experiment["attributes"]["metadata"]
    assert json.loads(experiment["attributes"]["metadata"])["artifact_schema_version"] == "2"
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
    for case in cases:
        expected = json.loads(case["attributes"]["expected_output"])
        output = json.loads(case["attributes"]["output"])
        assert "capture" in expected
        assert output["ground_truth_result"] == (
            "differs_from_proposal" if output["hard_failures"] else "matches_proposal"
        )


def test_cli_returns_nonzero_for_an_invalid_package(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = replay_main(
        [
            str(tmp_path / "missing-backstory.json"),
            str(tmp_path / "missing-ground-truth.json"),
        ]
    )

    assert result == 1
    assert "EVALUATION_RUN_ERROR=" in capsys.readouterr().err


def test_replay_uses_production_capture_path_without_handing_off_labels() -> None:
    content, ground_truth = validate_package_files(BACKSTORY_PATH, GROUND_TRUTH_PATH)
    lines = {line.line_id: line for line in content.lines}
    scenes_by_text = {
        lines[scene.line_ids[0]].text: scene.scene_id for scene in content.scenes
    }
    proposals = {proposal.scene_id: proposal for proposal in ground_truth.proposals}
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
            from apps.backend import chat_turn

            muse = AsyncMock()
            muse.run.side_effect = muse_run
            provenance = AsyncMock()
            provenance.run.side_effect = provenance_run
            boundary = AsyncMock()
            boundary.return_value = EmotionalBoundaryAssessment(
                decision="continue_reflection"
            )
            with (
                patch.object(chat_turn, "assess_emotional_boundary", boundary),
                patch.object(chat_turn, "muse_chat_agent", muse),
                patch.object(chat_turn, "provenance_agent", provenance),
            ):
                result = asyncio.run(
                    replay_capture_scenes(
                        content,
                        ground_truth,
                        chat_handler=chat_turn.run_chat_turn,
                    )
                )
    finally:
        get_settings.cache_clear()

    committed = [scene for scene in result.scenes if scene.memory_id is not None]
    expected_span = next(
        proposal.capture.span
        for proposal in ground_truth.proposals
        if isinstance(proposal.capture, CaptureCandidate)
    )
    assert len(committed) == 1
    assert committed[0].stored_text == expected_span.text
    assert len(result.final_active_memory_ids) == 1
    assert all(scene.boundary_origin is None for scene in result.scenes)
    assert all(
        scene.ground_truth_result == "matches_proposal" for scene in result.scenes
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
    assert "runtime_prompt_fingerprints" not in ground_truth.model_dump(mode="json")
