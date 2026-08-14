"""Tests for atomic chat history updates."""

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


class ChatEndpointTests(unittest.IsolatedAsyncioTestCase):
    session_id = "endpoint-test"

    def tearDown(self) -> None:
        sessions.clear(self.session_id)

    async def test_success_stores_only_released_turn(self) -> None:
        request = ChatRequest(session_id=self.session_id, message="Hello")
        gate = AsyncMock(return_value="Approved reply")

        with patch.object(main, "reflection_reply", gate):
            response = await main.chat(request)

        self.assertEqual("Approved reply", response.reply)
        history = sessions.history(self.session_id)
        self.assertEqual("Hello", history[0].parts[0].content)
        self.assertEqual("Approved reply", history[1].parts[0].content)

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
        self.assertIsNone(sessions.book_context(self.session_id))
        self.assertIsNone(sessions.book_selection(self.session_id))
        self.assertIsNone(sessions.reading_candidate(self.session_id))
