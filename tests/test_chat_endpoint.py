"""Tests for atomic chat history updates."""

import json
import os
import unittest
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
    from apps.backend import main, sessions
    from apps.backend.schemas import ChatRequest
    from src.linger.orchestration.reflection import ReflectionRelease


class ChatEndpointTests(unittest.IsolatedAsyncioTestCase):
    session_id = "endpoint-test"

    def tearDown(self) -> None:
        sessions.clear(self.session_id)

    async def test_success_stores_only_released_turn(self) -> None:
        request = ChatRequest(session_id=self.session_id, message="Hello")
        gate = AsyncMock(return_value=ReflectionRelease(
            reply="Approved reply",
            release_source="muse_candidate",
            provenance_verdicts=("pass",),
        ))

        with patch.object(main, "reflection_reply", gate):
            response = await main.chat(request)

        self.assertEqual("Approved reply", response.reply)
        history = sessions.history(self.session_id)
        self.assertEqual("Hello", history[0].parts[0].content)
        self.assertEqual("Approved reply", history[1].parts[0].content)
        self.assertEqual("muse_candidate", response.inspection.release["release_source"])
        self.assertEqual(["pass"], response.inspection.release["provenance_verdicts"])
        review_context = gate.await_args.kwargs["review_context"]
        self.assertIn("policy_constraints", review_context)
        self.assertIn("cited_evidence", review_context)
        muse_payload = json.loads(gate.await_args.args[0])
        self.assertEqual("Hello", muse_payload["muse_turn"]["user_message"])
        self.assertIn("context_resolution", muse_payload)

    async def test_failure_stores_nothing(self) -> None:
        request = ChatRequest(
            session_id=self.session_id,
            message="I am reading Animal Farm and I have finished Chapter 2.",
        )
        gate = AsyncMock(side_effect=RuntimeError("model failed"))

        with patch.object(main, "reflection_reply", gate):
            with self.assertRaises(HTTPException) as caught:
                await main.chat(request)

        self.assertEqual(502, caught.exception.status_code)
        self.assertEqual([], sessions.history(self.session_id))
        self.assertIsNone(sessions.book_selection(self.session_id))
        self.assertIsNone(sessions.reading_candidate(self.session_id))

    async def test_grounded_turn_shares_the_same_context_with_muse_and_provenance(self) -> None:
        request = ChatRequest(
            session_id=self.session_id,
            message=(
                "I am reading Animal Farm and I have finished Chapter 3. "
                "Why does the milk connect to power and equality?"
            ),
        )
        gate = AsyncMock(return_value=ReflectionRelease(
            reply="Approved grounded reply",
            release_source="muse_candidate",
            provenance_verdicts=("pass",),
        ))

        with patch.object(main, "reflection_reply", gate):
            await main.chat(request)

        muse_payload = json.loads(gate.await_args.args[0])
        review_context = gate.await_args.kwargs["review_context"]
        self.assertEqual(3, muse_payload["muse_turn"]["policy"]["spoiler_ceiling"])
        self.assertEqual(muse_payload["supporting_evidence"], review_context["cited_evidence"])
        self.assertEqual(muse_payload["connection_proposal"], review_context["connection_proposal"])

    async def test_safe_decline_rolls_back_tentative_reading_state(self) -> None:
        request = ChatRequest(
            session_id=self.session_id,
            message="Why does the Caterpillar ask who Alice is?",
        )
        gate = AsyncMock(return_value=ReflectionRelease(
            reply="Safe decline",
            release_source="application_safe_decline",
            failure_stage="provenance_review",
        ))

        with patch.object(main, "reflection_reply", gate):
            response = await main.chat(request)

        self.assertEqual("Safe decline", response.reply)
        self.assertIsNone(sessions.reading_candidate(self.session_id))
        self.assertEqual("application_safe_decline", response.inspection.release["release_source"])
