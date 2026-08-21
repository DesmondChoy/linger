"""Tests for the mandatory Muse-to-Provenance release gate."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from pydantic_ai.messages import ToolReturnPart

from src.linger.agents.muse.models import (
    EvidenceUse,
    MuseCandidate,
    NoMemoryCandidate,
)
from src.linger.agents.provenance.models import ProvenanceReview, RiskFinding
from src.linger.contracts.turn import ReleaseScope
from src.linger.orchestration.reflection import SAFE_DECLINE, reflection_reply

EVIDENCE_ID = "pg11-v01b38ea4-ch02-ln0010-0011"
LOCATION = "Chapter 2 — The Pool of Tears, source lines 10-11"
QUOTE = "Who are you?"
RELEASE_SCOPE = ReleaseScope(
    work_id="pg11",
    book_version_id="pg11-v01b38ea4",
    chapter_max=3,
)


def candidate(
    reply: str,
    *,
    evidence_id: str | None = None,
    location: str = LOCATION,
    exact_quote: str | None = None,
) -> MuseCandidate:
    uses = ()
    if evidence_id is not None:
        uses = (
            EvidenceUse(
                source_kind="book_corpus",
                evidence_id=evidence_id,
                source_location=location,
                exact_quote=exact_quote,
            ),
        )
    return MuseCandidate(
        reply=reply,
        evidence_uses=uses,
        memory=NoMemoryCandidate(
            kind="no_memory_candidate",
            reason_code="transient_or_low_signal",
        ),
    )


def result(output: object, *tool_returns: ToolReturnPart) -> SimpleNamespace:
    if isinstance(output, str):
        output = candidate(output)
    messages = [SimpleNamespace(parts=list(tool_returns))]
    return SimpleNamespace(output=output, new_messages=lambda: messages)


def evidence_record(
    *,
    evidence_id: str = EVIDENCE_ID,
    work_id: str = "pg11",
    book_version_id: str = "pg11-v01b38ea4",
    chapter_number: int = 2,
    location: str = LOCATION,
    text: str = f'Alice asked, "{QUOTE}" before answering.',
) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "work_id": work_id,
        "book_version_id": book_version_id,
        "chapter_id": "pg11-v01b38ea4-ch02",
        "chapter_number": chapter_number,
        "location": location,
        "source_sha256": "a" * 64,
        "source_lines": [10, 11],
        "text": text,
    }


def retrieval_result(
    *,
    evidence: list[dict[str, object]] | None = None,
    work_id: str = "pg11",
    book_version_id: str = "pg11-v01b38ea4",
    chapter_max: int = 3,
    strength: str = "sufficient",
) -> dict[str, object]:
    records = [evidence_record()] if evidence is None else evidence
    return {
        "kind": "result",
        "request_id": "libreq-test",
        "outcome": "evidence_found" if records else "no_evidence",
        "evidence_strength": strength if records else "none",
        "strength_reason": "The returned text answers the question." if records else "No support found.",
        "searched_scope": {
            "work_id": work_id,
            "book_version_id": book_version_id,
            "max_chapter_inclusive": chapter_max,
        },
        "evidence": records,
        "limitations": [],
    }


def review(
    decision: str,
    *,
    capture: str = "no_candidate",
    finding: str = "",
) -> ProvenanceReview:
    """Build a review, supplying the finding a non-pass decision requires."""
    findings = ()
    if decision != "pass" or capture == "reject_capture":
        findings = (
            RiskFinding(
                code="unsupported_claim",
                quote="an unsupported span",
                explanation=finding or "The evidence does not support this.",
            ),
        )
    return ProvenanceReview(
        findings=findings,
        response_decision=decision,
        capture_decision=capture,
    )


class ReflectionReplyTests(unittest.IsolatedAsyncioTestCase):
    async def test_releases_only_after_pass(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result("Approved reply")
        provenance = AsyncMock()
        provenance.run.return_value = result(review("pass"))

        release = await reflection_reply(
            "Hello",
            [],
            muse=muse,
            provenance=provenance,
            review_context={"policy_constraints": {"spoiler_ceiling": 3}, "cited_evidence": {"items": []}},
        )

        self.assertEqual("Approved reply", release.reply)
        self.assertEqual("muse_candidate", release.release_source)
        self.assertEqual(("pass",), release.provenance_verdicts)
        provenance.run.assert_awaited_once()
        review_payload = json.loads(provenance.run.await_args.args[0])
        self.assertEqual(3, review_payload["policy_constraints"]["spoiler_ceiling"])
        self.assertEqual({"items": []}, review_payload["cited_evidence"])
        self.assertEqual([], review_payload["candidate_evidence_uses"])

    async def test_provenance_receives_actual_muse_tool_results(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result(
            candidate(
                f'The text asks, "{QUOTE}"',
                evidence_id=EVIDENCE_ID,
                exact_quote=QUOTE,
            ),
            ToolReturnPart(
                "librarian_search",
                retrieval_result(),
            ),
        )
        provenance = AsyncMock()
        provenance.run.return_value = result(review("pass"))

        await reflection_reply(
            "Hello",
            [],
            muse=muse,
            provenance=provenance,
            release_scope=RELEASE_SCOPE,
        )

        review_payload = json.loads(provenance.run.await_args.args[0])
        self.assertEqual("librarian_search", review_payload["muse_tool_results"][0]["tool_name"])
        self.assertEqual(
            EVIDENCE_ID,
            review_payload["cited_evidence"][0]["evidence"][0]["evidence_id"],
        )
        self.assertEqual(
            EVIDENCE_ID,
            review_payload["candidate_evidence_uses"][0]["evidence_id"],
        )

    async def test_direct_librarian_grounding_is_exposed_for_inspection(self) -> None:
        from pydantic_ai.messages import ToolCallPart

        call = ToolCallPart(
            "librarian_search",
            {"query": "the pool of tears", "work_id": "pg11"},
            "call-1",
        )
        tool_return = ToolReturnPart("librarian_search", retrieval_result(), "call-1")
        muse = AsyncMock()
        muse.run.return_value = SimpleNamespace(
            output=candidate(
                f'The text asks, "{QUOTE}"',
                evidence_id=EVIDENCE_ID,
                exact_quote=QUOTE,
            ),
            new_messages=lambda: [SimpleNamespace(parts=[call, tool_return])],
        )
        provenance = AsyncMock()
        provenance.run.return_value = result(review("pass"))

        release = await reflection_reply(
            "Hello",
            [],
            muse=muse,
            provenance=provenance,
            release_scope=RELEASE_SCOPE,
        )

        self.assertEqual(1, len(release.librarian_grounding_calls))
        grounding_call = release.librarian_grounding_calls[0]
        self.assertEqual(
            "the pool of tears", grounding_call["request"]["query"]
        )
        self.assertEqual("success", grounding_call["outcome"])
        self.assertEqual(
            "evidence_found", grounding_call["response"]["outcome"]
        )

    async def test_every_librarian_branch_reaches_provenance_unchanged(self) -> None:
        branches = (
            {
                "kind": "clarification",
                "request_id": "libreq-clarify",
                "clarification_id": "clarify-test",
                "reason_code": "current_chapter_state_ambiguous",
                "question": "Have you completed Chapter 5?",
                "expected_answer": {
                    "type": "one_of",
                    "values": ["completed", "started"],
                },
            },
            retrieval_result(),
            retrieval_result(strength="weak"),
            retrieval_result(evidence=[]),
            {
                "kind": "failure",
                "request_id": "libreq-failure",
                "error_code": "retrieval_unavailable",
                "retryable": True,
            },
        )

        for branch in branches:
            with self.subTest(branch=branch):
                muse = AsyncMock()
                muse.run.return_value = result(
                    "Candidate handled the Librarian response.",
                    ToolReturnPart("librarian_search", branch),
                )
                provenance = AsyncMock()
                provenance.run.return_value = result(
                    review("pass")
                )

                await reflection_reply(
                    "Hello",
                    [],
                    muse=muse,
                    provenance=provenance,
                    release_scope=RELEASE_SCOPE,
                )

                review_payload = json.loads(provenance.run.await_args.args[0])
                self.assertEqual(branch, review_payload["cited_evidence"][0])

    async def test_allows_one_reviewed_revision(self) -> None:
        muse = AsyncMock()
        muse.run.side_effect = [result("Draft"), result("Revised reply")]
        provenance = AsyncMock()
        provenance.run.side_effect = [
            result(review("revise", finding="Qualify the claim.")),
            result(review("pass")),
        ]

        release = await reflection_reply("Hello", [], muse=muse, provenance=provenance)

        self.assertEqual("Revised reply", release.reply)
        self.assertEqual(("revise", "pass"), release.provenance_verdicts)
        self.assertEqual(1, release.revision_count)
        self.assertEqual(2, muse.run.await_count)
        self.assertEqual(2, provenance.run.await_count)
        revision_payload = json.loads(muse.run.await_args_list[1].args[0])
        self.assertIn("Qualify the claim.", revision_payload["review_critique"])
        self.assertIn("an unsupported span", revision_payload["review_critique"])
        self.assertFalse(hasattr(release, "critiques"))

    async def test_valid_book_quote_passes_deterministic_validation(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result(
            candidate(
                f'Alice asks, "{QUOTE}"',
                evidence_id=EVIDENCE_ID,
                exact_quote=QUOTE,
            ),
            ToolReturnPart("librarian_search", retrieval_result()),
        )
        provenance = AsyncMock()
        provenance.run.return_value = result(review("pass"))

        release = await reflection_reply(
            "Hello",
            [],
            muse=muse,
            provenance=provenance,
            release_scope=RELEASE_SCOPE,
        )

        self.assertEqual("muse_candidate", release.release_source)
        self.assertIsNone(release.failure_stage)

    async def test_unresolved_or_non_librarian_evidence_fails_closed(self) -> None:
        cases = (
            (ToolReturnPart("librarian_search", retrieval_result()), "unknown-evidence"),
            (
                ToolReturnPart(
                    "serendipity_explore",
                    {
                        "status": "proposal",
                        "tentative_claim": "A connection",
                        "evidence_ids": [EVIDENCE_ID],
                        "interpretation": "Tentative",
                        "uncertainty": "medium",
                        "suggested_follow_up": "What do you think?",
                    },
                ),
                EVIDENCE_ID,
            ),
        )
        for tool_return, evidence_id in cases:
            with self.subTest(tool=tool_return.tool_name):
                muse = AsyncMock()
                muse.run.return_value = result(
                    candidate("A supported thought.", evidence_id=evidence_id),
                    tool_return,
                )
                provenance = AsyncMock()
                provenance.run.return_value = result(review("pass"))

                release = await reflection_reply(
                    "Hello",
                    [],
                    muse=muse,
                    provenance=provenance,
                    release_scope=RELEASE_SCOPE,
                )

                self.assertEqual(SAFE_DECLINE, release.reply)
                self.assertEqual("deterministic_validation", release.failure_stage)

    async def test_quote_and_location_mismatches_fail_closed(self) -> None:
        cases = (
            candidate(
                f'Alice asks, "{QUOTE}"',
                evidence_id=EVIDENCE_ID,
                location="Chapter 99",
                exact_quote=QUOTE,
            ),
            candidate(
                'Alice asks, "Invented words"',
                evidence_id=EVIDENCE_ID,
                exact_quote="Invented words",
            ),
            candidate(
                "Alice asks a question.",
                evidence_id=EVIDENCE_ID,
                exact_quote=QUOTE,
            ),
        )
        for invalid_candidate in cases:
            with self.subTest(candidate=invalid_candidate):
                muse = AsyncMock()
                muse.run.return_value = result(
                    invalid_candidate,
                    ToolReturnPart("librarian_search", retrieval_result()),
                )
                provenance = AsyncMock()
                provenance.run.return_value = result(review("pass"))

                release = await reflection_reply(
                    "Hello",
                    [],
                    muse=muse,
                    provenance=provenance,
                    release_scope=RELEASE_SCOPE,
                )

                self.assertEqual(SAFE_DECLINE, release.reply)
                self.assertEqual("deterministic_validation", release.failure_stage)

    async def test_work_revision_and_spoiler_mismatches_fail_closed(self) -> None:
        scopes = (
            RELEASE_SCOPE.model_copy(update={"work_id": "animal-farm"}),
            RELEASE_SCOPE.model_copy(update={"book_version_id": "pg11-other"}),
            RELEASE_SCOPE.model_copy(update={"chapter_max": 1}),
        )
        for scope in scopes:
            with self.subTest(scope=scope):
                muse = AsyncMock()
                muse.run.return_value = result(
                    candidate("A supported thought.", evidence_id=EVIDENCE_ID),
                    ToolReturnPart("librarian_search", retrieval_result()),
                )
                provenance = AsyncMock()
                provenance.run.return_value = result(review("pass"))

                release = await reflection_reply(
                    "Hello", [], muse=muse, provenance=provenance, release_scope=scope
                )

                self.assertEqual(SAFE_DECLINE, release.reply)
                self.assertEqual("deterministic_validation", release.failure_stage)

    async def test_unsupported_candidate_source_fails_closed_before_review(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result(
            {
                "reply": "Unsupported citation.",
                "evidence_uses": [
                    {
                        "source_kind": "web",
                        "evidence_id": "web-1",
                        "source_location": "https://example.com",
                        "exact_quote": None,
                    }
                ],
            }
        )
        provenance = AsyncMock()

        release = await reflection_reply("Hello", [], muse=muse, provenance=provenance)

        self.assertEqual(SAFE_DECLINE, release.reply)
        self.assertEqual("muse_draft", release.failure_stage)
        provenance.run.assert_not_awaited()

    async def test_malformed_librarian_result_fails_closed_after_review(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result(
            "Uncited reply.",
            ToolReturnPart(
                "librarian_search",
                {"kind": "result", "evidence": "not-a-valid-result"},
            ),
        )
        provenance = AsyncMock()
        provenance.run.return_value = result(review("pass"))

        release = await reflection_reply(
            "Hello",
            [],
            muse=muse,
            provenance=provenance,
            release_scope=RELEASE_SCOPE,
        )

        self.assertEqual(SAFE_DECLINE, release.reply)
        self.assertEqual("deterministic_validation", release.failure_stage)

    async def test_passed_revision_still_requires_deterministic_validation(self) -> None:
        muse = AsyncMock()
        muse.run.side_effect = [
            result("Draft"),
            result(candidate("Still unsupported.", evidence_id="unknown-evidence")),
        ]
        provenance = AsyncMock()
        provenance.run.side_effect = [
            result(review("revise", finding="Add support.")),
            result(review("pass")),
        ]

        release = await reflection_reply(
            "Hello",
            [],
            muse=muse,
            provenance=provenance,
            release_scope=RELEASE_SCOPE,
        )

        self.assertEqual(SAFE_DECLINE, release.reply)
        self.assertEqual(("revise", "pass"), release.provenance_verdicts)
        self.assertEqual("deterministic_validation", release.failure_stage)

    async def test_evidence_from_message_history_cannot_authorize_release(self) -> None:
        historical = [
            SimpleNamespace(
                parts=[ToolReturnPart("librarian_search", retrieval_result())]
            )
        ]
        current = [SimpleNamespace(parts=[])]
        muse = AsyncMock()
        muse.run.return_value = SimpleNamespace(
            output=candidate("A supported thought.", evidence_id=EVIDENCE_ID),
            all_messages=lambda: historical + current,
            new_messages=lambda: current,
        )
        provenance = AsyncMock()
        provenance.run.return_value = result(review("pass"))

        release = await reflection_reply(
            "Hello",
            [],
            muse=muse,
            provenance=provenance,
            release_scope=RELEASE_SCOPE,
        )

        self.assertEqual(SAFE_DECLINE, release.reply)
        self.assertEqual("deterministic_validation", release.failure_stage)

    async def test_reject_returns_safe_decline(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result("Unsafe draft")
        provenance = AsyncMock()
        provenance.run.return_value = result(review("reject"))

        release = await reflection_reply("Hello", [], muse=muse, provenance=provenance)

        self.assertEqual(SAFE_DECLINE, release.reply)
        self.assertEqual("application_safe_decline", release.release_source)
        self.assertEqual(("reject",), release.provenance_verdicts)
        self.assertEqual(1, muse.run.await_count)

    async def test_failed_review_returns_safe_decline(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result("Unreviewed draft")
        provenance = AsyncMock()
        provenance.run.side_effect = RuntimeError("provider failed")

        release = await reflection_reply("Hello", [], muse=muse, provenance=provenance)

        self.assertEqual(SAFE_DECLINE, release.reply)
        self.assertEqual("provenance_review", release.failure_stage)
        self.assertEqual((), release.provenance_verdicts)

    async def test_second_revision_request_returns_safe_decline(self) -> None:
        muse = AsyncMock()
        muse.run.side_effect = [result("Draft"), result("Still unsafe")]
        provenance = AsyncMock()
        provenance.run.side_effect = [
            result(review("revise", finding="Try again.")),
            result(review("revise", finding="Still unsafe.")),
        ]

        release = await reflection_reply("Hello", [], muse=muse, provenance=provenance)

        self.assertEqual(SAFE_DECLINE, release.reply)
        self.assertEqual(("revise", "revise"), release.provenance_verdicts)
        self.assertEqual(2, muse.run.await_count)
        self.assertEqual(2, provenance.run.await_count)
