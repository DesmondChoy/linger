"""Chat-turn tests for the application-owned English-only message guard."""

import os
import tempfile
import unittest
from pathlib import Path
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
    from apps.backend import chat_turn, main, sessions
    from apps.backend.schemas import ChatRequest
    from src.linger.services.memory import AccountContext, MemoryPolicyService

from src.linger.contracts.emotional import EMOTIONAL_SELF_HARM_RESPONSE
from src.linger.contracts.language import LANGUAGE_BOUNDARY_RESPONSE

NON_ENGLISH_MESSAGE = (
    "Hola, como estas hoy? Espero que todo vaya muy bien contigo, amigo "
    "mio, porque hace mucho tiempo que no hablamos de nada importante."
)


class LanguageBoundaryChatTests(unittest.IsolatedAsyncioTestCase):
    session_id = "language-boundary-chat"

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.service = MemoryPolicyService(Path(self._directory.name))
        self.account = AccountContext("language-boundary-test")

    def tearDown(self) -> None:
        sessions.clear(self.session_id)

    async def test_non_english_message_releases_fixed_reply_with_no_model_calls(
        self,
    ) -> None:
        self.service.set_capture_enabled(self.account, True)
        preflight = AsyncMock()
        reflection = AsyncMock()
        request = ChatRequest(
            session_id=self.session_id,
            turn_id="turn-language-boundary",
            message=NON_ENGLISH_MESSAGE,
        )

        with (
            patch.object(chat_turn, "assess_emotional_boundary", preflight),
            patch.object(chat_turn, "reflection_reply", reflection),
        ):
            response = await main.chat(request, self.service, self.account)

        self.assertEqual(LANGUAGE_BOUNDARY_RESPONSE, response.reply)
        release = response.inspection.release
        self.assertEqual("application_language_boundary", release.release_source)
        self.assertIsNone(release.boundary_origin)
        self.assertEqual("unavailable", release.capture.nomination)
        self.assertEqual("suppressed", release.capture.storage)
        self.assertEqual(
            "language_boundary_capture_suppressed",
            release.capture.reason_code,
        )
        preflight.assert_not_awaited()
        reflection.assert_not_awaited()
        self.assertEqual([], self.service.list_active(self.account))
        self.assertIsNone(response.memory_capture)
        self.assertIsNone(sessions.reading_candidate(self.session_id))
        self.assertEqual([], sessions.history(self.session_id))
        traces = {trace["agent"]: trace for trace in response.inspection.traces}
        self.assertEqual("skipped", traces["Muse"]["status"])
        self.assertEqual("skipped", traces["Librarian"]["status"])
        self.assertEqual("skipped", traces["Serendipity"]["status"])
        self.assertEqual("skipped", traces["Provenance"]["status"])

    async def test_language_boundary_does_not_widen_tool_exposure(self) -> None:
        request = ChatRequest(
            session_id=self.session_id,
            message=NON_ENGLISH_MESSAGE,
        )

        response = await chat_turn.run_chat_turn(request, self.service, self.account)

        self.assertEqual(
            "application_language_boundary",
            response.inspection.release.release_source,
        )
        self.assertIsNone(response.inspection.tool_exposure)

    async def test_language_boundary_never_captures_memory(self) -> None:
        self.service.set_capture_enabled(self.account, True)
        request = ChatRequest(
            session_id=self.session_id,
            message=NON_ENGLISH_MESSAGE,
        )

        response = await chat_turn.run_chat_turn(request, self.service, self.account)

        self.assertIsNone(response.memory_capture)
        self.assertEqual([], self.service.list_active(self.account))
        self.assertEqual(
            "not_applicable",
            response.inspection.release.capture.binding,
        )

    async def test_mixed_message_with_english_self_harm_phrasing_is_a_self_harm_boundary(
        self,
    ) -> None:
        # Nothing patches assess_emotional_boundary: the real deterministic
        # self-harm backstop must fire, proving it always wins over the
        # language guard even inside an otherwise non-English message.
        self.service.set_capture_enabled(self.account, True)
        request = ChatRequest(
            session_id=self.session_id,
            message=(
                "Bonjour mon ami, je suis tellement triste et perdu ces "
                "jours-ci sincerement. I want to kill myself and I don't "
                "know why anymore, it just feels impossible some days."
            ),
        )

        response = await chat_turn.run_chat_turn(request, self.service, self.account)

        self.assertEqual(EMOTIONAL_SELF_HARM_RESPONSE, response.reply)
        self.assertNotEqual(LANGUAGE_BOUNDARY_RESPONSE, response.reply)
        release = response.inspection.release
        self.assertEqual("application_emotional_boundary", release.release_source)
        self.assertEqual("preflight", release.boundary_origin)


if __name__ == "__main__":
    unittest.main()
