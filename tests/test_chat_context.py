"""Tests that the chat route sets the request-scoped confirmed-reading ContextVar."""

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

from src.linger.contracts.turn import ConfirmedReading
from src.linger.orchestration.reflection import ReflectionRelease
from src.linger.orchestration.turn_context import confirmed_reading


def released(text: str = "reply") -> ReflectionRelease:
    return ReflectionRelease(
        reply=text,
        release_source="muse_candidate",
        provenance_verdicts=("pass",),
    )


class ChatContextVarTests(unittest.IsolatedAsyncioTestCase):
    session_id = "chat-context-test"

    def tearDown(self) -> None:
        sessions.clear(self.session_id)

    async def test_confirmed_context_exposed_to_reflection_reply(self) -> None:
        seen: dict[str, ConfirmedReading | None] = {}

        async def fake_reflection_reply(*args, **kwargs) -> ReflectionRelease:
            seen["value"] = confirmed_reading()
            return released()

        request = ChatRequest(
            session_id=self.session_id,
            message="I'm reading Alice Adventures in Wonderland and I've finished Chapter 3.",
        )

        with patch.object(main, "reflection_reply", AsyncMock(side_effect=fake_reflection_reply)):
            await main.chat(request)

        self.assertEqual(
            ConfirmedReading(work_id="alice-adventures-in-wonderland", chapter_max=3),
            seen["value"],
        )

    async def test_no_confirmed_context_exposes_none(self) -> None:
        seen: dict[str, ConfirmedReading | None] = {}

        async def fake_reflection_reply(*args, **kwargs) -> ReflectionRelease:
            seen["value"] = confirmed_reading()
            return released()

        request = ChatRequest(session_id=self.session_id, message="Hello")

        with patch.object(main, "reflection_reply", AsyncMock(side_effect=fake_reflection_reply)):
            await main.chat(request)

        self.assertIsNone(seen["value"])

    async def test_inferred_only_context_exposes_none(self) -> None:
        seen: dict[str, ConfirmedReading | None] = {}

        async def fake_reflection_reply(*args, **kwargs) -> ReflectionRelease:
            seen["value"] = confirmed_reading()
            return released()

        request = ChatRequest(session_id=self.session_id, message="Why is the Caterpillar so rude?")

        with patch.object(main, "reflection_reply", AsyncMock(side_effect=fake_reflection_reply)):
            await main.chat(request)

        self.assertIsNone(seen["value"])
        self.assertIsNone(sessions.book_selection(self.session_id))

    async def test_var_reset_after_successful_turn(self) -> None:
        request = ChatRequest(
            session_id=self.session_id,
            message="I'm reading Alice Adventures in Wonderland and I've finished Chapter 3.",
        )

        with patch.object(main, "reflection_reply", AsyncMock(return_value=released())):
            await main.chat(request)

        self.assertIsNone(confirmed_reading())

    async def test_var_reset_after_failed_turn(self) -> None:
        request = ChatRequest(
            session_id=self.session_id,
            message="I'm reading Alice Adventures in Wonderland and I've finished Chapter 3.",
        )

        with patch.object(main, "reflection_reply", AsyncMock(side_effect=RuntimeError("boom"))):
            with self.assertRaises(HTTPException):
                await main.chat(request)

        self.assertIsNone(confirmed_reading())


if __name__ == "__main__":
    unittest.main()
