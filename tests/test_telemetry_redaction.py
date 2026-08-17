"""Telemetry must carry operational metadata and no content.

`docs/telemetry.md` bars raw personal memories, full user or assistant
messages, photographs, raw book or web excerpts, credentials, API keys, and
sensitive-inference content from logs and spans.

These tests assert that prohibition against the real exported span payload
rather than against the projection functions in isolation, so an unredacted
field added anywhere in the pipeline fails here.
"""

import json
import logging
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import logfire
from logfire.testing import TestExporter
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from apps.backend.contracts import (
    ConnectionBrief,
    EvidenceBundle,
    EvidenceItem,
    LibrarianRequest,
)
from apps.backend.telemetry import (
    brief_attrs,
    evidence_attrs,
    librarian_request_attrs,
    review_attrs,
    run_agent_traced,
)
from src.linger.agents.muse.models import MuseCandidate
from src.linger.agents.provenance.models import ProvenanceReview, RiskFinding
from src.linger.orchestration.reflection import (
    SAFE_DECLINE,
    ReflectionRelease,
    reflection_reply,
)

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
        output = MuseCandidate(reply=output)
    messages = [SimpleNamespace(parts=[])]
    return SimpleNamespace(output=output, new_messages=lambda: messages)


class TelemetryTestCase(unittest.IsolatedAsyncioTestCase):
    """Capture spans in memory; nothing is sent anywhere."""

    def setUp(self) -> None:
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
        brief = ConnectionBrief(cue=SECRET_CUE, book_id="alice", chapter_max=3)
        request = LibrarianRequest(query=SECRET_CUE)

        brief_projection = brief_attrs(brief)
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
                    quote=SECRET_QUOTE,
                    explanation="explanatory prose about the quote",
                ),
            ),
            response_decision="reject",
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
        await run_agent_traced(
            agent,
            SECRET_MESSAGE,
            span_name="test.agent",
            role="Muse",
            stage="test",
            prompt_template_id="test.prompt",
            failure_code="test_model_failed",
        )

        payload = self.exported_payload()
        self.assertNotIn(SECRET_SYSTEM, payload)
        self.assertNotIn(SECRET_MESSAGE, payload)
        self.assertNotIn("zxcas private model output zxcas", payload)
        self.assertIn("test.prompt", payload)
        self.assertIn('"input_tokens": 12', payload)
        self.assertIn('"output_tokens": 4', payload)
        self.assertIn('"cost.usd": 0.0012', payload)

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
                prompt_template_id="test.prompt",
                failure_code="test_model_failed",
            )

        payload = self.exported_payload()
        self.assertNotIn(SECRET_SYSTEM, payload)
        self.assertNotIn(SECRET_MESSAGE, payload)
        self.assertNotIn(SECRET_EXCEPTION, payload)
        self.assertNotIn("RuntimeError", payload)
        self.assertIn("test_model_failed", payload)


class ReflectionSpanTests(TelemetryTestCase):
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
        payload = self.exported_payload()
        self.assertNotIn(SECRET_QUOTE, payload)
        self.assertNotIn("private-location", payload)

    async def test_released_turn_records_verdicts_without_content(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result("An approved reply mentioning nothing secret")
        provenance = AsyncMock()
        provenance.run.return_value = result(
            ProvenanceReview(findings=(), response_decision="pass", capture_decision="no_candidate")
        )

        release = await reflection_reply(
            SECRET_MESSAGE,
            [],
            muse=muse,
            provenance=provenance,
            review_context={"policy_constraints": {"spoiler_ceiling": 3}},
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

        # Behaviour is unchanged: the reader still gets the safe decline.
        self.assertEqual(SAFE_DECLINE, release.reply)
        self.assertEqual("application_safe_decline", release.release_source)
        self.assertEqual("provenance_review", release.failure_stage)

        payload = self.exported_payload()
        self.assertIn("provenance_review", payload)
        self.assertIn("provenance_model_failed", payload)
        self.assertNotIn(SECRET_EXCEPTION, payload)
        self.assertNotIn("RuntimeError", payload)
        self.assertNotIn(SECRET_MESSAGE, payload)

    async def test_reject_reports_risk_codes_without_the_quote(self) -> None:
        """A policy reject must be diagnosable from codes alone.

        `failure_stage` stays None here: Provenance ran fine and decided to
        block, which is not a failure.
        """
        muse = AsyncMock()
        muse.run.return_value = result("A candidate reply")
        provenance = AsyncMock()
        provenance.run.return_value = result(
            ProvenanceReview(
                findings=(
                    RiskFinding(
                        code="unsupported_claim",
                        quote=SECRET_QUOTE,
                        explanation="explanatory prose",
                    ),
                    RiskFinding(code="spoiler", quote=SECRET_QUOTE, explanation="prose"),
                ),
                response_decision="reject",
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
                            quote=SECRET_QUOTE,
                            explanation="needs support",
                        ),
                    ),
                    response_decision="revise",
                    capture_decision="no_candidate",
                )
            ),
            result(
                ProvenanceReview(
                    findings=(), response_decision="pass", capture_decision="no_candidate"
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
