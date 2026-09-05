"""Telemetry must carry operational metadata and no content (docs/telemetry.md), asserted against the real exported span payload."""

import asyncio
import json
import logging
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import logfire
from logfire.testing import TestExporter
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RequestUsage

from apps.backend.contracts import (
    BookScope,
    ConnectionBrief,
    ContextResolution,
    EvidenceBundle,
    EvidenceItem,
    LibrarianRequest,
    MuseDraftInput,
    MuseTurn,
    TurnPolicy,
)
from apps.backend.config import Settings
from apps.backend.telemetry import (
    connection_scope_attrs,
    evidence_attrs,
    librarian_request_attrs,
    review_attrs,
    run_agent_traced,
)
from evals.synthetic_journals.transcript import SceneTranscriptRecorder
from src.linger.agents.contracts import PromptFingerprint
from src.linger.agents.muse.models import MuseCandidate, NoMemoryCandidate
from src.linger.agents.provenance.models import ProvenanceReview, RiskFinding
from src.linger.agents.serendipity.models import ConnectionDiscoveryInput, ConnectionScope
from src.linger.contracts.turn import ConfirmedReading
from src.linger.evaluation_transcript import (
    active_evaluation_correlation_id,
    bind_evaluation_correlation_id,
    bind_evaluation_transcript_sink,
)
from src.linger.contracts.emotional import (
    EmotionalBoundaryAssessment,
    EmotionalContentPolicy,
)
from src.linger.orchestration.emotional import assess_emotional_boundary
from src.linger.orchestration import grounding as grounding_module
from src.linger.orchestration.reflection import (
    PIPELINE_FAILURE_DECLINE,
    SAFE_DECLINE,
    ReflectionRelease,
    reflection_reply as production_reflection_reply,
)
from src.linger.orchestration.turn_context import (
    reset_confirmed_reading,
    set_confirmed_reading,
)

with patch("src.linger.agents.build.build_model", return_value=TestModel()):
    from src.linger.orchestration.connection import connection_exploration

# Distinctive strings that must never reach a span.
SECRET_MESSAGE = "zqxjv my private reflection about the caterpillar zqxjv"
SECRET_EXCERPT = "wqmzk raw book excerpt text that must never be logged wqmzk"
SECRET_CUE = "vbnpl the cue the reader typed vbnpl"
SECRET_QUOTE = "hjklm the offending verbatim span hjklm"
SECRET_SYSTEM = "rtvbn private system instruction rtvbn"
SECRET_EXCEPTION = "plmok private provider failure plmok"


def result(output: object) -> SimpleNamespace:
    """Match the fake run-result shape used by tests/test_reflection.py."""
    if isinstance(output, str):
        output = MuseCandidate(
            reply=output,
            memory=NoMemoryCandidate(
                kind="no_memory_candidate",
                reason_code="transient_or_low_signal",
            ),
        )
    messages = [SimpleNamespace(parts=[])]
    return SimpleNamespace(output=output, new_messages=lambda: messages)


def muse_input(message: str) -> str:
    return MuseDraftInput(
        mode="draft",
        muse_turn=MuseTurn(
            turn_id="telemetry-test-turn",
            user_message=message,
            reading_context=None,
            policy=TurnPolicy(
                spoiler_ceiling=None,
                allow_retrieval=False,
                allow_connection=False,
                allow_memory_capture=False,
            ),
        ),
        context_resolution=ContextResolution(
            status="unknown",
            explanation="No reading context.",
        ),
    ).model_dump_json()


async def reflection_reply(message: str, *args, **kwargs):
    prompt = message if message.lstrip().startswith("{") else muse_input(message)
    kwargs.setdefault("capture_source_text", message)
    return await production_reflection_reply(prompt, *args, **kwargs)


class TelemetryTestCase(unittest.IsolatedAsyncioTestCase):
    """Capture spans in memory; nothing is sent anywhere."""

    def setUp(self) -> None:
        settings_patch = patch(
            "apps.backend.telemetry.get_settings",
            return_value=Settings(
                _env_file=None,
                linger_model="google:gemini-2.5-flash",
                google_api_key="test-key",
            ),
        )
        settings_patch.start()
        self.addCleanup(settings_patch.stop)
        self.exporter = TestExporter()
        logfire.configure(
            send_to_logfire=False,
            console=False,
            inspect_arguments=False,
            additional_span_processors=[logfire.testing.SimpleSpanProcessor(self.exporter)],
        )

    def exported_payload(self) -> str:
        """Every exported span, as one JSON blob for substring assertions."""
        return json.dumps(self.exporter.exported_spans_as_dict(), default=str)


class EmotionalPreflightTelemetryTests(TelemetryTestCase):
    async def test_emotional_preflight_exports_only_fixed_metadata(self) -> None:
        provenance = AsyncMock()
        provenance.run.return_value = result(
            EmotionalBoundaryAssessment(decision="apply_boundary")
        )

        await assess_emotional_boundary(
            SECRET_MESSAGE,
            EmotionalContentPolicy(),
            provenance=provenance,
        )

        payload = self.exported_payload()
        self.assertIn("provenance.emotional-boundary", payload)
        self.assertIn("emotional_boundary_preflight", payload)
        self.assertIn("apply_boundary", payload)
        self.assertNotIn(SECRET_MESSAGE, payload)

    async def test_emotional_preflight_records_continue_without_line_content(
        self,
    ) -> None:
        provenance = AsyncMock()
        provenance.run.return_value = result(
            EmotionalBoundaryAssessment(decision="continue_reflection")
        )

        await assess_emotional_boundary(
            SECRET_MESSAGE,
            EmotionalContentPolicy(),
            provenance=provenance,
        )

        payload = self.exported_payload()
        self.assertIn("continue_reflection", payload)
        self.assertNotIn(SECRET_MESSAGE, payload)


class ProjectionRedactionTests(TelemetryTestCase):
    def test_evidence_projection_drops_excerpts(self) -> None:
        bundle = EvidenceBundle(
            items=[
                EvidenceItem(
                    evidence_id="alice-ch3-rules",
                    work_id="pg11",
                    book_version_id="pg11-v01b38ea4",
                    chapter_id="pg11-v01b38ea4-ch03",
                    source_title="Alice",
                    location="ch3",
                    chapter=3,
                    source_sha256=(
                        "01b38ea4c710a84bc18d0bd41271a5a1a92b94e97b2812f4dece97d4a694725e"
                    ),
                    source_lines=(1, 2),
                    excerpt=SECRET_EXCERPT,
                    relevance=0.8,
                )
            ],
            retrieval_note="note",
        )
        attrs = evidence_attrs(bundle)

        self.assertNotIn(SECRET_EXCERPT, json.dumps(attrs))
        self.assertEqual(1, attrs["retrieval.item_count"])
        self.assertEqual(
            ["alice-ch3-rules"], attrs["retrieval.evidence_ids"]
        )
        self.assertNotIn("chapters", attrs)

    def test_brief_and_request_projections_drop_reader_text(self) -> None:
        task = ConnectionDiscoveryInput(
            cue=SECRET_CUE,
            intent="find_connection",
            presentation="ask_before_showing",
            scope=ConnectionScope(
                allowed_sources=("book_corpus",),
                book_scopes=(
                    BookScope(
                        work_id="pg11",
                        book_version_id="pg11-v01b38ea4",
                        chapter_max=3,
                    ),
                ),
            ),
        )
        request = LibrarianRequest(query=SECRET_CUE)

        brief_projection = connection_scope_attrs(task)
        request_projection = librarian_request_attrs(request)
        self.assertNotIn(SECRET_CUE, json.dumps(brief_projection))
        self.assertNotIn(SECRET_CUE, json.dumps(request_projection))
        self.assertNotIn("cue_length", brief_projection)
        self.assertNotIn("query_length", request_projection)
        self.assertEqual("serendipity_explore", brief_projection["tool.name"])
        self.assertEqual("librarian_search", request_projection["tool.name"])

    def test_review_projection_keeps_codes_and_drops_quotes(self) -> None:
        review = ProvenanceReview(
            findings=(
                RiskFinding(
                    code="unsupported_claim",
                    applies_to="response",
                    location={
                        "kind": "text_span",
                        "source_field": "candidate.response",
                        "path": "",
                        "quote": SECRET_QUOTE,
                    },
                    explanation="explanatory prose about the quote",
                ),
            ),
            response_decision="reject",
            emotional_boundary_decision="not_required",
            capture_decision="no_candidate",
        )
        attrs = review_attrs(review)

        payload = json.dumps(attrs)
        self.assertNotIn(SECRET_QUOTE, payload)
        self.assertNotIn("explanatory prose", payload)
        self.assertEqual(
            ["unsupported_claim"], attrs["provenance.finding_codes"]
        )
        self.assertEqual("reject", attrs["provenance.response_decision"])


class AgentInstrumentationTests(TelemetryTestCase):
    def test_prompt_digest_covers_only_the_static_artifact(self) -> None:
        first = PromptFingerprint.from_artifact(
            template_id="test.prompt",
            version="test-v1",
            instructions="Static instructions.",
            input_contract="TestInput.v1",
            output_contract="TestOutput.v1",
        )
        same = PromptFingerprint.from_artifact(
            template_id="test.prompt",
            version="test-v2",
            instructions="Static instructions.",
            input_contract="TestInput.v1",
            output_contract="TestOutput.v1",
        )
        changed = PromptFingerprint.from_artifact(
            template_id="test.prompt",
            version="test-v1",
            instructions="Changed static instructions.",
            input_contract="TestInput.v1",
            output_contract="TestOutput.v1",
        )

        self.assertEqual(first.digest, same.digest)
        self.assertNotEqual(first.digest, changed.digest)
        self.assertNotIn(SECRET_MESSAGE, first.model_dump_json())

    async def test_explicit_agent_span_excludes_all_model_content(self) -> None:
        def respond(_messages, _info):
            return ModelResponse(
                parts=[TextPart("zxcas private model output zxcas")],
                usage=RequestUsage(
                    input_tokens=12,
                    output_tokens=4,
                    cost=Decimal("0.0012"),
                ),
            )

        agent = Agent(FunctionModel(respond), instructions=SECRET_SYSTEM)
        recorder = SceneTranscriptRecorder()
        with bind_evaluation_transcript_sink(recorder):
            await run_agent_traced(
                agent,
                SECRET_MESSAGE,
                span_name="test.agent",
                role="Muse",
                stage="test",
                input_contract="TestInput.v1",
                output_contract="TestOutput.v1",
                prompt_template_id="test.prompt",
                prompt_version="test-v1",
                prompt_digest="0" * 64,
                failure_code="test_model_failed",
            )

        payload = self.exported_payload()
        self.assertNotIn(SECRET_SYSTEM, payload)
        self.assertNotIn(SECRET_MESSAGE, payload)
        self.assertNotIn("zxcas private model output zxcas", payload)
        self.assertIn("test.prompt", payload)
        self.assertIn("test-v1", payload)
        self.assertIn('"prompt.digest": "' + "0" * 64 + '"', payload)
        self.assertIn('"input_tokens": 12', payload)
        self.assertIn('"output_tokens": 4', payload)
        self.assertIn('"cost.usd": 0.0012', payload)
        self.assertIn('"handoff.input.origin": "Application"', payload)
        self.assertIn('"handoff.input.receiver": "Muse"', payload)
        self.assertIn('"handoff.input.contract": "TestInput.v1"', payload)
        self.assertIn('"handoff.output.origin": "Muse"', payload)
        self.assertIn('"handoff.output.receiver": "Application"', payload)
        self.assertIn('"handoff.output.contract": "TestOutput.v1"', payload)

        exchange = recorder.exchanges[0]
        self.assertEqual(SECRET_MESSAGE, exchange.input_prompt)
        self.assertEqual("Muse", exchange.role)
        self.assertEqual("Application", exchange.input_origin)
        self.assertEqual("Application", exchange.output_receiver)
        self.assertIn(SECRET_SYSTEM, json.dumps(exchange.model_messages))
        self.assertIn(
            "zxcas private model output zxcas",
            json.dumps(exchange.model_messages),
        )

    async def test_evaluation_correlation_is_recorded_without_entering_telemetry(self) -> None:
        correlation_id = "routereq_evaluation_only"
        agent = Agent(
            FunctionModel(
                lambda _messages, _info: ModelResponse(parts=[TextPart("ok")])
            ),
            instructions="Static instructions.",
        )
        recorder = SceneTranscriptRecorder()

        with (
            bind_evaluation_transcript_sink(recorder),
            bind_evaluation_correlation_id(correlation_id),
        ):
            await run_agent_traced(
                agent,
                "synthetic prompt",
                span_name="test.correlated-agent",
                role="Librarian",
                stage="boundary_inference",
                input_contract="BoundaryInput.v1",
                output_contract="BoundaryOutput.v1",
                prompt_template_id="test.boundary",
                prompt_version="1",
                prompt_digest="0" * 64,
                failure_code="test_boundary_failed",
            )

        self.assertEqual(correlation_id, recorder.exchanges[0].correlation_id)
        self.assertIsNone(active_evaluation_correlation_id())
        self.assertNotIn(correlation_id, self.exported_payload())

    async def test_explicit_agent_span_maps_failure_without_exception(self) -> None:
        def fail(_messages, _info):
            raise RuntimeError(SECRET_EXCEPTION)

        agent = Agent(FunctionModel(fail), instructions=SECRET_SYSTEM)
        with self.assertRaises(RuntimeError):
            await run_agent_traced(
                agent,
                SECRET_MESSAGE,
                span_name="test.agent",
                role="Muse",
                stage="test",
                input_contract="TestInput.v1",
                output_contract="TestOutput.v1",
                prompt_template_id="test.prompt",
                prompt_version="test-v1",
                prompt_digest="0" * 64,
                failure_code="test_model_failed",
            )

        payload = self.exported_payload()
        self.assertNotIn(SECRET_SYSTEM, payload)
        self.assertNotIn(SECRET_MESSAGE, payload)
        self.assertNotIn(SECRET_EXCEPTION, payload)
        self.assertNotIn("RuntimeError", payload)
        self.assertIn("test_model_failed", payload)

    async def test_result_projection_failure_is_application_owned(self) -> None:
        agent = AsyncMock()
        agent.run.return_value = result("A valid result")

        def fail_projection(_result):
            raise RuntimeError(SECRET_EXCEPTION)

        projected_result = await run_agent_traced(
            agent,
            SECRET_MESSAGE,
            span_name="test.agent",
            role="Muse",
            stage="test",
            input_contract="TestInput.v1",
            output_contract="TestOutput.v1",
            prompt_template_id="test.prompt",
            prompt_version="test-v1",
            prompt_digest="0" * 64,
            failure_code="test_model_failed",
            result_attrs=fail_projection,
        )

        self.assertEqual("A valid result", projected_result.output.reply)
        payload = self.exported_payload()
        self.assertIn("agent_result_projection_failed", payload)
        self.assertIn('"failure.type": "application"', payload)
        self.assertIn('"failure.retryable": false', payload)
        self.assertNotIn("test_model_failed", payload)
        self.assertNotIn(SECRET_EXCEPTION, payload)

    async def test_agent_cancellation_uses_fixed_metadata_only(self) -> None:
        agent = AsyncMock()
        agent.run.side_effect = asyncio.CancelledError(SECRET_EXCEPTION)

        with self.assertRaises(asyncio.CancelledError):
            await run_agent_traced(
                agent,
                SECRET_MESSAGE,
                span_name="test.agent",
                role="Muse",
                stage="test",
                input_contract="TestInput.v1",
                output_contract="TestOutput.v1",
                prompt_template_id="test.prompt",
                prompt_version="test-v1",
                prompt_digest="0" * 64,
                failure_code="test_model_failed",
            )

        payload = self.exported_payload()
        self.assertIn("request_cancelled", payload)
        self.assertNotIn(SECRET_EXCEPTION, payload)
        self.assertNotIn("CancelledError", payload)


class ReflectionSpanTests(TelemetryTestCase):
    async def test_reflection_cancellation_uses_fixed_metadata_only(self) -> None:
        muse = AsyncMock()
        muse.run.side_effect = asyncio.CancelledError(SECRET_EXCEPTION)

        with self.assertRaises(asyncio.CancelledError):
            await reflection_reply(
                SECRET_MESSAGE,
                [],
                muse=muse,
                provenance=AsyncMock(),
            )

        payload = self.exported_payload()
        self.assertIn("request_cancelled", payload)
        self.assertNotIn(SECRET_EXCEPTION, payload)
        self.assertNotIn("CancelledError", payload)

    async def test_invalid_typed_candidate_does_not_leak_through_exception_span(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result(
            {
                "reply": SECRET_QUOTE,
                "evidence_uses": [
                    {
                        "source_kind": "web",
                        "evidence_id": "web-secret",
                        "source_location": "private-location",
                    }
                ],
            }
        )
        provenance = AsyncMock()

        release = await reflection_reply(
            SECRET_MESSAGE, [], muse=muse, provenance=provenance
        )

        self.assertEqual("muse_draft", release.failure_stage)
        self.assertEqual("validation", release.failure_type)
        self.assertFalse(release.failure_retryable)
        payload = self.exported_payload()
        self.assertNotIn(SECRET_QUOTE, payload)
        self.assertNotIn("private-location", payload)

    async def test_invalid_review_envelope_is_not_reported_as_model_failure(
        self,
    ) -> None:
        muse = AsyncMock()
        muse.run.return_value = result("A candidate reply")
        provenance = AsyncMock()

        release = await reflection_reply(
            SECRET_MESSAGE,
            [],
            muse=muse,
            provenance=provenance,
            review_context={"unexpected": True},
        )

        self.assertEqual("provenance_review", release.failure_stage)
        self.assertEqual("validation", release.failure_type)
        self.assertFalse(release.failure_retryable)
        provenance.run.assert_not_awaited()

        payload = self.exported_payload()
        self.assertIn('"failure.type": "validation"', payload)
        self.assertIn('"failure.retryable": false', payload)
        self.assertNotIn("provenance_model_failed", payload)
        self.assertNotIn(SECRET_MESSAGE, payload)

    async def test_released_turn_records_verdicts_without_content(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result("An approved reply mentioning nothing secret")
        provenance = AsyncMock()
        provenance.run.return_value = result(
            ProvenanceReview(
                findings=(),
                response_decision="pass",
                emotional_boundary_decision="not_required",
                capture_decision="no_candidate",
            )
        )

        release = await reflection_reply(
            SECRET_MESSAGE,
            [],
            muse=muse,
            provenance=provenance,
            review_context={
                "policy_constraints": {
                    "spoiler_ceiling": 3,
                    "allow_retrieval": True,
                    "allow_connection": False,
                    "allow_memory_capture": False,
                },
                "reading_context": None,
            },
        )

        self.assertEqual("muse_candidate", release.release_source)
        payload = self.exported_payload()
        # The message was passed straight into reflection_reply; no span may echo it.
        self.assertNotIn(SECRET_MESSAGE, payload)
        self.assertIn("release.source", payload)
        self.assertIn("muse_candidate", payload)

    async def test_provenance_failure_records_fixed_metadata_only(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result("A candidate reply")
        provenance = AsyncMock()
        provenance.run.side_effect = RuntimeError(SECRET_EXCEPTION)

        release = await reflection_reply(
            SECRET_MESSAGE,
            [],
            muse=muse,
            provenance=provenance,
            review_context={},
        )

        # Behaviour is unchanged: the reader still gets a safe decline.
        self.assertEqual(PIPELINE_FAILURE_DECLINE, release.reply)
        self.assertEqual("application_safe_decline", release.release_source)
        self.assertEqual("provenance_review", release.failure_stage)
        self.assertEqual("model", release.failure_type)
        self.assertTrue(release.failure_retryable)

        payload = self.exported_payload()
        self.assertIn("provenance_review", payload)
        self.assertIn("provenance_model_failed", payload)
        self.assertIn('"failure.type": "model"', payload)
        self.assertIn('"failure.retryable": true', payload)
        self.assertNotIn(SECRET_EXCEPTION, payload)
        self.assertNotIn("RuntimeError", payload)
        self.assertNotIn(SECRET_MESSAGE, payload)

    async def test_reject_reports_risk_codes_without_the_quote(self) -> None:
        """`failure_stage` stays None: Provenance ran fine and decided to block."""
        muse = AsyncMock()
        muse.run.return_value = result("A candidate reply")
        provenance = AsyncMock()
        provenance.run.return_value = result(
            ProvenanceReview(
                findings=(
                    RiskFinding(
                        code="unsupported_claim",
                        applies_to="response",
                        location={
                            "kind": "structural",
                            "source_field": "candidate.response",
                            "path": "",
                        },
                        explanation="explanatory prose",
                    ),
                    RiskFinding(
                        code="spoiler",
                        applies_to="response",
                        location={
                            "kind": "structural",
                            "source_field": "candidate.response",
                            "path": "",
                        },
                        explanation="prose",
                    ),
                ),
                response_decision="reject",
                emotional_boundary_decision="not_required",
                capture_decision="no_candidate",
            )
        )

        release = await reflection_reply(
            SECRET_MESSAGE, [], muse=muse, provenance=provenance, review_context={}
        )

        self.assertEqual(SAFE_DECLINE, release.reply)
        self.assertEqual(("reject",), release.provenance_verdicts)
        self.assertIsNone(release.failure_stage)
        # Deduplicated, first occurrence first.
        self.assertEqual(("unsupported_claim", "spoiler"), release.finding_codes)

        payload = self.exported_payload()
        self.assertIn("unsupported_claim", payload)
        self.assertNotIn(SECRET_QUOTE, payload)
        self.assertNotIn("explanatory prose", payload)

    async def test_revision_path_records_revision_count(self) -> None:
        muse = AsyncMock()
        muse.run.side_effect = [result("First draft"), result("Revised draft")]
        provenance = AsyncMock()
        provenance.run.side_effect = [
            result(
                ProvenanceReview(
                    findings=(
                        RiskFinding(
                            code="unsupported_claim",
                            applies_to="response",
                            location={
                                "kind": "structural",
                                "source_field": "candidate.response",
                                "path": "",
                            },
                            explanation="needs support",
                        ),
                    ),
                    response_decision="revise",
                    emotional_boundary_decision="not_required",
                    capture_decision="no_candidate",
                )
            ),
            result(
                ProvenanceReview(
                    findings=(),
                    response_decision="pass",
                    emotional_boundary_decision="not_required",
                    capture_decision="no_candidate",
                )
            ),
        ]

        release = await reflection_reply(
            SECRET_MESSAGE, [], muse=muse, provenance=provenance, review_context={}
        )

        self.assertEqual(1, release.revision_count)
        self.assertEqual(("revise", "pass"), release.provenance_verdicts)

        payload = self.exported_payload()
        self.assertIn("revision_count", payload)
        # The critique quotes the candidate verbatim and must not be exported.
        self.assertNotIn(SECRET_QUOTE, payload)


class ManualToolSpanCancellationTests(TelemetryTestCase):
    async def test_grounding_cancellation_uses_fixed_metadata_only(self) -> None:
        cancelled_call = AsyncMock(
            side_effect=asyncio.CancelledError(SECRET_EXCEPTION)
        )
        with patch.object(
            grounding_module,
            "_grounding_evidence",
            new=cancelled_call,
        ):
            with self.assertRaises(asyncio.CancelledError):
                await grounding_module.grounding_evidence(object())  # type: ignore[arg-type]

        payload = self.exported_payload()
        self.assertIn("request_cancelled", payload)
        self.assertNotIn(SECRET_EXCEPTION, payload)
        self.assertNotIn("CancelledError", payload)

    async def test_connection_cancellation_uses_fixed_metadata_only(self) -> None:
        reading_token = set_confirmed_reading(
            ConfirmedReading(work_id="pg11", chapter_max=3)
        )
        explorer = AsyncMock(side_effect=asyncio.CancelledError(SECRET_EXCEPTION))
        try:
            with patch(
                "src.linger.orchestration.connection.web_reach_permitted",
                return_value=False,
            ):
                with self.assertRaises(asyncio.CancelledError):
                    await connection_exploration(
                        ConnectionBrief(cue=SECRET_CUE),
                        explorer=explorer,
                    )
        finally:
            reset_confirmed_reading(reading_token)

        payload = self.exported_payload()
        self.assertIn("request_cancelled", payload)
        self.assertNotIn(SECRET_CUE, payload)
        self.assertNotIn(SECRET_EXCEPTION, payload)
        self.assertNotIn("CancelledError", payload)


class LogLineTests(unittest.TestCase):
    """The file log is the only evidence when no LOGFIRE_TOKEN is set."""

    def test_reject_log_line_names_the_risk_codes(self) -> None:
        release = ReflectionRelease(
            reply=SAFE_DECLINE,
            release_source="application_safe_decline",
            provenance_verdicts=("reject",),
            finding_codes=("unsupported_claim", "spoiler"),
        )

        with self.assertLogs("linger.backend", level="INFO") as captured:
            logging.getLogger("linger.backend").info(
                "Agent run completed elapsed=%.2fs release_source=%s "
                "provenance_path=%s findings=%s revisions=%d failure_stage=%s",
                1.0,
                release.release_source,
                ",".join(release.provenance_verdicts) or "none",
                ",".join(release.finding_codes) or "none",
                release.revision_count,
                release.failure_stage or "none",
            )

        line = captured.output[0]
        self.assertIn("findings=unsupported_claim,spoiler", line)
        self.assertIn("provenance_path=reject", line)
        self.assertIn("failure_stage=none", line)
        # Rejected quote-bearing critique prose never enters the release object.
        self.assertNotIn(SECRET_QUOTE, line)

    def test_clean_run_log_line_says_none(self) -> None:
        release = ReflectionRelease(
            reply="fine", release_source="muse_candidate", provenance_verdicts=("pass",)
        )
        self.assertEqual("none", ",".join(release.finding_codes) or "none")


if __name__ == "__main__":
    unittest.main()
