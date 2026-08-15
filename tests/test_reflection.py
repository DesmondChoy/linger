"""Tests for the mandatory Muse-to-Provenance release gate."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.linger.agents.provenance.models import ProvenanceReview, RiskFinding
from src.linger.orchestration.reflection import SAFE_DECLINE, reflection_reply


def result(output: object) -> SimpleNamespace:
    return SimpleNamespace(output=output)


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

        reply = await reflection_reply("Hello", [], muse=muse, provenance=provenance)

        self.assertEqual("Approved reply", reply)
        provenance.run.assert_awaited_once()

    async def test_allows_one_reviewed_revision(self) -> None:
        muse = AsyncMock()
        muse.run.side_effect = [result("Draft"), result("Revised reply")]
        provenance = AsyncMock()
        provenance.run.side_effect = [
            result(review("revise", finding="Qualify the claim.")),
            result(review("pass")),
        ]

        reply = await reflection_reply("Hello", [], muse=muse, provenance=provenance)

        self.assertEqual("Revised reply", reply)
        self.assertEqual(2, muse.run.await_count)
        self.assertEqual(2, provenance.run.await_count)

    async def test_reject_returns_safe_decline(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result("Unsafe draft")
        provenance = AsyncMock()
        provenance.run.return_value = result(review("reject"))

        reply = await reflection_reply("Hello", [], muse=muse, provenance=provenance)

        self.assertEqual(SAFE_DECLINE, reply)
        self.assertEqual(1, muse.run.await_count)

    async def test_failed_review_returns_safe_decline(self) -> None:
        muse = AsyncMock()
        muse.run.return_value = result("Unreviewed draft")
        provenance = AsyncMock()
        provenance.run.side_effect = RuntimeError("provider failed")

        reply = await reflection_reply("Hello", [], muse=muse, provenance=provenance)

        self.assertEqual(SAFE_DECLINE, reply)

    async def test_second_revision_request_returns_safe_decline(self) -> None:
        muse = AsyncMock()
        muse.run.side_effect = [result("Draft"), result("Still unsafe")]
        provenance = AsyncMock()
        provenance.run.side_effect = [
            result(review("revise", finding="Try again.")),
            result(review("revise", finding="Still unsafe.")),
        ]

        reply = await reflection_reply("Hello", [], muse=muse, provenance=provenance)

        self.assertEqual(SAFE_DECLINE, reply)
        self.assertEqual(2, muse.run.await_count)
        self.assertEqual(2, provenance.run.await_count)
