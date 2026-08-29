"""Production chat-path tests for reviewed automatic memory capture."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from apps.backend.config import get_settings

get_settings.cache_clear()
with patch.dict(
    os.environ,
    {
        "LINGER_MODEL": "google:gemini-2.5-flash",
        "GOOGLE_API_KEY": "test-key",
    },
):
    from apps.backend import main, sessions
    from apps.backend.schemas import ChatRequest
from src.linger.agents.muse.models import (
    BookEvidenceUse,
    MemoryCandidate,
    MuseCandidate,
    NoMemoryCandidate,
)
from src.linger.agents.provenance.models import ProvenanceReview, RiskFinding
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.services.memory import AccountContext, MemoryPolicyService


def result(output: object) -> SimpleNamespace:
    return SimpleNamespace(output=output, new_messages=lambda: [])


def muse_candidate(source: str, *, nominated: str | None) -> MuseCandidate:
    if nominated is None:
        memory = NoMemoryCandidate(
            kind="no_memory_candidate",
            reason_code="transient_or_low_signal",
        )
    else:
        start = source.index(nominated)
        memory = MemoryCandidate(
            kind="memory_candidate",
            text=nominated,
            start_codepoint=start,
            end_codepoint=start + len(nominated),
            reason_code="durable_reflection",
        )
    return MuseCandidate(reply="A reviewed reply.", memory=memory)


def review(
    capture_decision: str,
    *,
    risk_code: str | None = None,
    response_decision: str = "pass",
) -> ProvenanceReview:
    findings = []
    if risk_code is not None:
        findings.append(
            RiskFinding(
                code=risk_code,
                applies_to="capture",
                location={
                    "kind": "structural",
                    "source_field": "candidate.memory",
                    "path": "",
                },
                explanation="Capture must be refused.",
            )
        )
    if response_decision != "pass":
        findings.append(
            RiskFinding(
                code="unsupported_claim",
                applies_to="response",
                location={
                    "kind": "structural",
                    "source_field": "candidate.response",
                    "path": "",
                },
                explanation="The response must not be released.",
            )
        )
    return ProvenanceReview(
        findings=tuple(findings),
        response_decision=response_decision,
        emotional_boundary_decision="not_required",
        capture_decision=capture_decision,
    )


class ChatCaptureTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.service = MemoryPolicyService(Path(self._directory.name))
        self.account = AccountContext("synthetic-chat-account")

    def tearDown(self) -> None:
        for session_id in (
            "capture-allowed",
            "capture-none",
            "capture-substitution",
            "capture-sensitive",
            "capture-review-mismatch",
            "capture-safe-0",
            "capture-safe-1",
            "capture-safe-2",
            "capture-safe-3",
            "capture-safe-4",
            "capture-safe-5",
            "capture-safe-6",
        ):
            sessions.clear(session_id)

    async def run_chat(
        self,
        request: ChatRequest,
        candidate: MuseCandidate,
        provenance_review: ProvenanceReview,
    ):
        muse = AsyncMock()
        muse.run.return_value = result(candidate)
        provenance = AsyncMock()
        provenance.run.return_value = result(provenance_review)
        with (
            patch.object(
                main,
                "assess_emotional_boundary",
                AsyncMock(
                    return_value=EmotionalBoundaryAssessment(
                        decision="continue_reflection"
                    )
                ),
            ),
            patch.object(main, "muse_chat_agent", muse),
            patch.object(main, "provenance_agent", provenance),
        ):
            response = await main.chat(request, self.service, self.account)
        return response, provenance

    async def run_chat_sequence(
        self,
        request: ChatRequest,
        candidates: list[MuseCandidate | Exception],
        reviews: list[ProvenanceReview | Exception],
    ):
        muse = AsyncMock()
        muse.run.side_effect = [
            candidate if isinstance(candidate, Exception) else result(candidate)
            for candidate in candidates
        ]
        provenance = AsyncMock()
        provenance.run.side_effect = [
            item if isinstance(item, Exception) else result(item)
            for item in reviews
        ]
        with (
            patch.object(
                main,
                "assess_emotional_boundary",
                AsyncMock(
                    return_value=EmotionalBoundaryAssessment(
                        decision="continue_reflection"
                    )
                ),
            ),
            patch.object(main, "muse_chat_agent", muse),
            patch.object(main, "provenance_agent", provenance),
        ):
            return await main.chat(request, self.service, self.account)

    async def test_allowed_exact_nomination_commits_and_discloses(self) -> None:
        self.service.set_capture_enabled(self.account, True)
        source = "I notice that I fill silence when I feel rushed."
        nominated = "I fill silence when I feel rushed."
        request = ChatRequest(
            session_id="capture-allowed",
            turn_id="turn-capture-allowed",
            message=source,
        )

        response, provenance = await self.run_chat(
            request,
            muse_candidate(source, nominated=nominated),
            review("allow_capture"),
        )

        memories = self.service.list_active(self.account)
        self.assertEqual([nominated], [memory.text for memory in memories])
        self.assertEqual("turn-capture-allowed", memories[0].source_event_id)
        self.assertEqual("committed", response.inspection.release.capture.storage)
        self.assertEqual("Saved to your memories.", response.memory_capture.notice)
        payload = provenance.run.await_args.args[0]
        self.assertIn(nominated, payload)
        self.assertIn(source, payload)

    async def test_no_nomination_never_reaches_storage(self) -> None:
        self.service.set_capture_enabled(self.account, True)
        source = "The train was late."
        response, _ = await self.run_chat(
            ChatRequest(session_id="capture-none", message=source),
            muse_candidate(source, nominated=None),
            review("no_candidate"),
        )

        self.assertEqual([], self.service.list_active(self.account))
        self.assertEqual("not_applicable", response.inspection.release.capture.storage)
        self.assertEqual(
            "not_applicable",
            response.inspection.release.capture.reason_code,
        )
        self.assertIsNone(response.memory_capture)

    async def test_substituted_text_fails_binding_without_blocking_reply(self) -> None:
        self.service.set_capture_enabled(self.account, True)
        source = "The exact source words."
        candidate = muse_candidate(source, nominated=source)
        candidate = candidate.model_copy(
            update={
                "memory": candidate.memory.model_copy(
                    update={"text": "The wrong source words."}
                )
            }
        )

        response, _ = await self.run_chat(
            ChatRequest(session_id="capture-substitution", message=source),
            candidate,
            review("allow_capture"),
        )

        self.assertEqual("A reviewed reply.", response.reply)
        self.assertEqual([], self.service.list_active(self.account))
        self.assertEqual("invalid", response.inspection.release.capture.binding)
        self.assertEqual(
            "invalid_capture_binding",
            response.inspection.release.capture.reason_code,
        )

    async def test_sensitive_candidate_is_vetoed_without_suppressing_reply(self) -> None:
        self.service.set_capture_enabled(self.account, True)
        source = "I think my colleague has a medical condition."
        response, _ = await self.run_chat(
            ChatRequest(session_id="capture-sensitive", message=source),
            muse_candidate(source, nominated=source),
            review("reject_capture", risk_code="sensitive_content"),
        )

        self.assertEqual("A reviewed reply.", response.reply)
        self.assertEqual([], self.service.list_active(self.account))
        self.assertEqual("refused", response.inspection.release.capture.storage)
        self.assertEqual(
            "upstream_review_rejected_capture",
            response.inspection.release.capture.reason_code,
        )

    async def test_inspection_keeps_muse_nomination_separate_from_bad_review(self) -> None:
        self.service.set_capture_enabled(self.account, True)
        source = "I want to pause before I answer next time."
        response, _ = await self.run_chat(
            ChatRequest(session_id="capture-review-mismatch", message=source),
            muse_candidate(source, nominated=source),
            review("no_candidate"),
        )

        capture = response.inspection.release.capture
        self.assertEqual("candidate", capture.nomination)
        self.assertEqual("no_candidate", capture.provenance_decision)
        self.assertEqual("invalid", capture.binding)
        self.assertEqual([], self.service.list_active(self.account))

    async def test_every_safe_decline_path_suppresses_an_allowed_candidate(self) -> None:
        self.service.set_capture_enabled(self.account, True)
        source = "I want to pause before I answer next time."
        valid = muse_candidate(source, nominated=source)
        unsupported = valid.model_copy(
            update={
                "evidence_uses": (
                    BookEvidenceUse(
                        source_kind="book_corpus",
                        evidence_id="unknown-evidence",
                        source_location="Unknown source",
                        exact_quote=None,
                    ),
                )
            }
        )
        cases = (
            (
                [valid],
                [review("allow_capture", response_decision="reject")],
                None,
            ),
            (
                [valid, valid],
                [
                    review("allow_capture", response_decision="revise"),
                    review("allow_capture", response_decision="reject"),
                ],
                None,
            ),
            (
                [valid, valid],
                [
                    review("allow_capture", response_decision="revise"),
                    review("allow_capture", response_decision="revise"),
                ],
                None,
            ),
            (
                [unsupported],
                [review("allow_capture")],
                "deterministic_validation",
            ),
            (
                [valid, unsupported],
                [
                    review("allow_capture", response_decision="revise"),
                    review("allow_capture"),
                ],
                "deterministic_validation",
            ),
            (
                [valid, RuntimeError("revision failed")],
                [review("allow_capture", response_decision="revise")],
                "muse_revision",
            ),
            (
                [valid, valid],
                [
                    review("allow_capture", response_decision="revise"),
                    RuntimeError("second review failed"),
                ],
                "provenance_review",
            ),
        )

        for index, (candidates, reviews, failure_stage) in enumerate(cases):
            with self.subTest(index=index):
                response = await self.run_chat_sequence(
                    ChatRequest(
                        session_id=f"capture-safe-{index}",
                        turn_id=f"capture-safe-turn-{index}",
                        message=source,
                    ),
                    candidates,
                    reviews,
                )

                release = response.inspection.release
                self.assertEqual("application_safe_decline", release.release_source)
                self.assertEqual(failure_stage, release.failure_stage)
                self.assertEqual("suppressed", release.capture.storage)
                self.assertEqual(
                    "safe_decline_capture_suppressed",
                    release.capture.reason_code,
                )
                self.assertIsNone(response.memory_capture)
                self.assertEqual([], self.service.list_active(self.account))
