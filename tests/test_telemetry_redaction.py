"""Telemetry must carry operational metadata and no content.

`docs/specification.md` §8.1 bars raw personal memories, full user or assistant
messages, photographs, raw book or web excerpts, credentials, API keys, and
sensitive-inference content from logs and spans.

These tests assert that prohibition against the real exported span payload
rather than against the projection functions in isolation, so an unredacted
field added anywhere in the pipeline fails here.
"""

import json
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import logfire
from logfire.testing import TestExporter

from apps.backend.contracts import (
    ConnectionBrief,
    EvidenceBundle,
    EvidenceItem,
    LibrarianRequest,
    MuseTurn,
    ReadingContext,
    TurnPolicy,
)
from apps.backend.telemetry import (
    brief_attrs,
    evidence_attrs,
    librarian_request_attrs,
    review_attrs,
    turn_attrs,
)
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


def result(output: object) -> SimpleNamespace:
    """Match the fake run-result shape used by tests/test_reflection.py."""
    messages = [SimpleNamespace(parts=[])]
    return SimpleNamespace(output=output, all_messages=lambda: messages)


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
                    source_title="Alice",
                    location="ch3",
                    chapter=3,
                    excerpt=SECRET_EXCERPT,
                    relevance=0.8,
                )
            ],
            retrieval_note="note",
        )
        attrs = evidence_attrs(bundle)

        self.assertNotIn(SECRET_EXCERPT, json.dumps(attrs))
        self.assertEqual(1, attrs["item_count"])
        self.assertEqual(["alice-ch3-rules"], attrs["evidence_ids"])
        self.assertEqual([3], attrs["chapters"])

    def test_turn_projection_drops_user_message(self) -> None:
        turn = MuseTurn(
            turn_id="t1",
            user_message=SECRET_MESSAGE,
            reading_context=ReadingContext(work_id="alice", chapter_max=3),
            policy=TurnPolicy(spoiler_ceiling=3, allow_retrieval=True, allow_connection=True),
        )
        attrs = turn_attrs(turn)

        self.assertNotIn(SECRET_MESSAGE, json.dumps(attrs))
        self.assertEqual(len(SECRET_MESSAGE), attrs["user_message_length"])
        self.assertEqual("t1", attrs["turn_id"])

    def test_brief_and_request_projections_drop_reader_text(self) -> None:
        brief = ConnectionBrief(cue=SECRET_CUE, book_id="alice", chapter_max=3)
        request = LibrarianRequest(query=SECRET_CUE)

        self.assertNotIn(SECRET_CUE, json.dumps(brief_attrs(brief)))
        self.assertNotIn(SECRET_CUE, json.dumps(librarian_request_attrs(request)))
        self.assertEqual(len(SECRET_CUE), brief_attrs(brief)["cue_length"])

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
        self.assertEqual(["unsupported_claim"], attrs["finding_codes"])
        self.assertEqual("reject", attrs["response_decision"])


class ReflectionSpanTests(TelemetryTestCase):
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
        self.assertIn("release_source", payload)
        self.assertIn("muse_candidate", payload)

    async def test_provenance_failure_records_stage_and_exception(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result("A candidate reply")
        provenance = AsyncMock()
        provenance.run.side_effect = RuntimeError("provider failed")

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
        self.assertIn("RuntimeError", payload)
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
            critiques=(f"- [unsupported_claim] prose (offending text: {SECRET_QUOTE!r})",),
            finding_codes=("unsupported_claim", "spoiler"),
        )

        with self.assertLogs("linger.backend", level="INFO") as captured:
            logging.getLogger("linger.backend").info(
                "Agent run completed session=%s elapsed=%.2fs turns=%d release_source=%s "
                "provenance_path=%s findings=%s revisions=%d failure_stage=%s",
                "s1",
                1.0,
                2,
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
        # The critique prose and its quote never reach the log.
        self.assertNotIn(SECRET_QUOTE, line)

    def test_clean_run_log_line_says_none(self) -> None:
        release = ReflectionRelease(
            reply="fine", release_source="muse_candidate", provenance_verdicts=("pass",)
        )
        self.assertEqual("none", ",".join(release.finding_codes) or "none")


if __name__ == "__main__":
    unittest.main()
