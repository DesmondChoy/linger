"""Tests for request-scoped chat context and released-evidence recovery."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from apps.backend.config import get_settings

get_settings.cache_clear()
with patch.dict(
    os.environ,
    {
        "LINGER_MODEL": "google:gemini-2.5-flash",
        "GOOGLE_API_KEY": "test-key",
    },
):
    from apps.backend import chat_turn, main, sessions
    from apps.backend.schemas import ChatRequest

from src.linger.contracts.librarian import EvidenceRecord
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.contracts.turn import ConfirmedReading, ReleaseScope
from src.linger.orchestration.reflection import ReflectionRelease
from src.linger.orchestration.turn_context import confirmed_reading, turn_evidence
from src.linger.services.memory import AccountContext, MemoryPolicyService


EVIDENCE_ID = "pg11-v01b38ea4-ch05-ln0974-0975"
PRIVATE_PASSAGE = "PRIVATE_REHYDRATED_PASSAGE_46f2"


def evidence_record() -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=EVIDENCE_ID,
        work_id="pg11",
        book_version_id="pg11-v01b38ea4",
        chapter_id="pg11-v01b38ea4-ch05",
        chapter_number=5,
        location="Chapter 5, lines 974-975",
        source_sha256="a" * 64,
        source_lines=(974, 975),
        text=PRIVATE_PASSAGE,
    )


def released(text: str = "reply") -> ReflectionRelease:
    return ReflectionRelease(
        reply=text,
        release_source="muse_candidate",
        provenance_verdicts=("pass",),
    )


class ChatContextVarTests(unittest.IsolatedAsyncioTestCase):
    session_id = "chat-context-test"

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.service = MemoryPolicyService(Path(self._directory.name))
        self.account = AccountContext("chat-context-test")
        self._boundary_patcher = patch.object(
            chat_turn,
            "assess_emotional_boundary",
            AsyncMock(
                return_value=EmotionalBoundaryAssessment(
                    decision="continue_reflection"
                )
            ),
        )
        self._boundary_patcher.start()
        self.addCleanup(self._boundary_patcher.stop)

    async def call_chat(self, request: ChatRequest):
        return await main.chat(request, self.service, self.account)

    def tearDown(self) -> None:
        sessions.clear(self.session_id)

    async def test_confirmed_context_exposed_to_reflection_reply(self) -> None:
        seen: dict[str, object] = {}

        async def fake_reflection_reply(*args, **kwargs) -> ReflectionRelease:
            seen["value"] = confirmed_reading()
            seen["release_scope"] = kwargs["release_scope"]
            return released()

        request = ChatRequest(
            session_id=self.session_id,
            message="I'm reading Alice Adventures in Wonderland and I've finished Chapter 3.",
        )

        with patch.object(chat_turn, "reflection_reply", AsyncMock(side_effect=fake_reflection_reply)):
            await self.call_chat(request)

        self.assertEqual(
            ConfirmedReading(work_id="pg11", chapter_max=3),
            seen["value"],
        )
        self.assertEqual(
            ReleaseScope(
                work_id="pg11",
                book_version_id="pg11-v01b38ea4",
                chapter_max=3,
            ),
            seen["release_scope"],
        )

    async def test_no_confirmed_context_exposes_none(self) -> None:
        seen: dict[str, object] = {}

        async def fake_reflection_reply(*args, **kwargs) -> ReflectionRelease:
            seen["value"] = confirmed_reading()
            seen["release_scope"] = kwargs["release_scope"]
            return released()

        request = ChatRequest(session_id=self.session_id, message="Hello")

        with patch.object(chat_turn, "reflection_reply", AsyncMock(side_effect=fake_reflection_reply)):
            await self.call_chat(request)

        self.assertIsNone(seen["value"])
        self.assertIsNone(seen["release_scope"])

    async def test_uncertain_message_exposes_no_retrieval_scope(self) -> None:
        # Librarian routing no longer runs pre-Muse: a catalog-cue message with
        # no explicit reader confirmation resolves to "unknown" here. Whether
        # Muse asks Librarian at all is now its own tool decision, covered by
        # tests/test_librarian_routing.py.
        seen: dict[str, object] = {}

        async def fake_reflection_reply(*args, **kwargs) -> ReflectionRelease:
            seen["value"] = confirmed_reading()
            seen["release_scope"] = kwargs["release_scope"]
            return released()

        request = ChatRequest(session_id=self.session_id, message="Why is the Caterpillar so rude?")

        with patch.object(chat_turn, "reflection_reply", AsyncMock(side_effect=fake_reflection_reply)):
            await self.call_chat(request)

        self.assertIsNone(seen["value"])
        self.assertIsNone(seen["release_scope"])
        self.assertIsNone(sessions.book_selection(self.session_id))

    async def test_var_reset_after_successful_turn(self) -> None:
        request = ChatRequest(
            session_id=self.session_id,
            message="I'm reading Alice Adventures in Wonderland and I've finished Chapter 3.",
        )

        with patch.object(chat_turn, "reflection_reply", AsyncMock(return_value=released())):
            await self.call_chat(request)

        self.assertIsNone(confirmed_reading())
        self.assertEqual({}, turn_evidence())

    async def test_var_reset_after_failed_turn(self) -> None:
        record = evidence_record()
        sessions.append_turn(
            self.session_id,
            "earlier question",
            "earlier grounded answer",
            turn_id="earlier-turn",
            release_source="muse_candidate",
            evidence_ids=(EVIDENCE_ID,),
        )
        request = ChatRequest(
            session_id=self.session_id,
            message="I'm reading Alice Adventures in Wonderland and I've finished Chapter 3.",
        )

        async def fail_with_evidence(*args, **kwargs) -> ReflectionRelease:
            self.assertEqual({EVIDENCE_ID: record}, dict(turn_evidence()))
            raise RuntimeError("boom")

        with (
            patch.object(
                chat_turn,
                "reflection_reply",
                AsyncMock(side_effect=fail_with_evidence),
            ),
            patch.object(chat_turn.librarian_service, "fetch_by_id", return_value=record),
        ):
            with self.assertRaises(HTTPException):
                await self.call_chat(request)

        self.assertIsNone(confirmed_reading())
        self.assertEqual({}, turn_evidence())

    async def test_released_evidence_is_rehydrated_for_a_later_turn(self) -> None:
        seen: dict[str, object] = {}
        call_count = 0

        async def fake_reflection_reply(*args, **kwargs) -> ReflectionRelease:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ReflectionRelease(
                    reply="grounded answer",
                    release_source="muse_candidate",
                    provenance_verdicts=("pass",),
                    evidence_ids=(EVIDENCE_ID,),
                    review_finding_codes=((),),
                )
            seen["muse_input"] = json.loads(args[0])
            seen["turn_evidence"] = dict(turn_evidence())
            seen["released_ids"] = kwargs["previously_released_evidence_ids"]
            return released("follow-up")

        record = evidence_record()
        with (
            patch.object(
                chat_turn,
                "reflection_reply",
                AsyncMock(side_effect=fake_reflection_reply),
            ),
            patch.object(
                chat_turn.librarian_service,
                "fetch_by_id",
                return_value=record,
            ) as fetch,
        ):
            await self.call_chat(
                ChatRequest(session_id=self.session_id, message="First question")
            )
            response = await self.call_chat(
                ChatRequest(session_id=self.session_id, message="What did that mean?")
            )

        fetch.assert_called_once_with(EVIDENCE_ID)
        self.assertEqual((EVIDENCE_ID,), sessions.released_evidence_ids(self.session_id))
        self.assertEqual(
            [record.model_dump(mode="json")],
            seen["muse_input"]["prior_evidence"],
        )
        self.assertEqual({EVIDENCE_ID: record}, seen["turn_evidence"])
        self.assertEqual(frozenset({EVIDENCE_ID}), seen["released_ids"])
        self.assertNotIn(PRIVATE_PASSAGE, response.inspection.prompt)
        self.assertNotIn("prior_evidence", json.loads(response.inspection.prompt))
        self.assertEqual({}, turn_evidence())

    async def test_safe_decline_evidence_is_not_rehydrated(self) -> None:
        seen: dict[str, object] = {}
        call_count = 0

        async def fake_reflection_reply(*args, **kwargs) -> ReflectionRelease:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ReflectionRelease(
                    reply="safe decline",
                    release_source="application_safe_decline",
                    provenance_verdicts=("reject",),
                    evidence_ids=(EVIDENCE_ID,),
                    review_finding_codes=(("unsupported_claim",),),
                )
            seen["muse_input"] = json.loads(args[0])
            seen["turn_evidence"] = dict(turn_evidence())
            seen["released_ids"] = kwargs["previously_released_evidence_ids"]
            return released("follow-up")

        with (
            patch.object(
                chat_turn,
                "reflection_reply",
                AsyncMock(side_effect=fake_reflection_reply),
            ),
            patch.object(chat_turn.librarian_service, "fetch_by_id") as fetch,
        ):
            await self.call_chat(
                ChatRequest(session_id=self.session_id, message="First question")
            )
            await self.call_chat(
                ChatRequest(session_id=self.session_id, message="Follow-up question")
            )

        fetch.assert_not_called()
        audit = sessions.turn_records(self.session_id)[0]
        self.assertEqual("application_safe_decline", audit.release_source)
        self.assertEqual((EVIDENCE_ID,), audit.evidence_ids)
        self.assertEqual((("unsupported_claim",),), audit.review_finding_codes)
        self.assertEqual((), sessions.released_evidence_ids(self.session_id))
        self.assertEqual([], seen["muse_input"]["prior_evidence"])
        self.assertEqual({}, seen["turn_evidence"])
        self.assertEqual(frozenset(), seen["released_ids"])
        self.assertEqual({}, turn_evidence())


if __name__ == "__main__":
    unittest.main()
