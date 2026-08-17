"""Tests for the mandatory Muse-to-Provenance release gate."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from pydantic_ai.messages import ToolReturnPart

from src.linger.agents.provenance.models import ProvenanceReview, RiskFinding
from src.linger.orchestration.reflection import SAFE_DECLINE, reflection_reply


def result(output: object, *tool_returns: ToolReturnPart) -> SimpleNamespace:
    messages = [SimpleNamespace(parts=list(tool_returns))]
    return SimpleNamespace(output=output, all_messages=lambda: messages)


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

    async def test_provenance_receives_actual_muse_tool_results(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result(
            "Grounded reply",
            ToolReturnPart(
                "librarian_search",
                {"kind": "result", "evidence": [{"evidence_id": "alice-ch2-identity"}]},
            ),
        )
        provenance = AsyncMock()
        provenance.run.return_value = result(review("pass"))

        await reflection_reply("Hello", [], muse=muse, provenance=provenance)

        review_payload = json.loads(provenance.run.await_args.args[0])
        self.assertEqual("librarian_search", review_payload["muse_tool_results"][0]["tool_name"])
        self.assertEqual(
            "alice-ch2-identity",
            review_payload["cited_evidence"][0]["evidence"][0]["evidence_id"],
        )

    async def test_every_librarian_branch_reaches_provenance_unchanged(self) -> None:
        branches = (
            {
                "kind": "clarification",
                "question": "Have you completed Chapter 5?",
            },
            {
                "kind": "result",
                "outcome": "evidence_found",
                "evidence_strength": "sufficient",
                "evidence": [{"evidence_id": "e-sufficient"}],
            },
            {
                "kind": "result",
                "outcome": "evidence_found",
                "evidence_strength": "weak",
                "evidence": [{"evidence_id": "e-weak"}],
                "limitations": ["The motive is not directly stated."],
            },
            {
                "kind": "result",
                "outcome": "no_evidence",
                "evidence_strength": "none",
                "evidence": [],
            },
            {
                "kind": "failure",
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

                await reflection_reply("Hello", [], muse=muse, provenance=provenance)

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
