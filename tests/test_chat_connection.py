"""End-to-end tests driving the real chat route through Muse's serendipity_explore tool."""

import os
import unittest
from unittest.mock import patch

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

from apps.backend.contracts import ConnectionProposal
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from src.linger.agents.muse.agent import muse_chat_agent
from src.linger.agents.provenance.agent import provenance_agent


def _provenance_pass(messages, info: AgentInfo) -> ModelResponse:
    tool = info.output_tools[0]
    return ModelResponse(
        parts=[
            ToolCallPart(
                tool.name,
                {
                    "findings": [],
                    "response_decision": "pass",
                    "capture_decision": "no_candidate",
                },
            )
        ]
    )


def _muse_calls_serendipity(cue: str, captured: list):
    def _respond(messages, info: AgentInfo) -> ModelResponse:
        for message in messages:
            for part in getattr(message, "parts", []):
                if isinstance(part, ToolReturnPart) and part.tool_name == "serendipity_explore":
                    captured.append(part.content)
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("serendipity_explore", {"cue": cue})])
        return ModelResponse(parts=[TextPart("Here's a connection worth sitting with.")])

    return _respond


class ChatConnectionEndToEndTests(unittest.IsolatedAsyncioTestCase):
    session_id = "chat-connection-e2e"

    def tearDown(self) -> None:
        sessions.clear(self.session_id)

    async def test_confirmed_book_and_chapter_reaches_real_connection_pipeline(self) -> None:
        captured: list = []
        request = ChatRequest(
            session_id=self.session_id,
            message="I'm reading Alice Adventures in Wonderland and I've finished Chapter 5",
        )

        with muse_chat_agent.override(model=FunctionModel(_muse_calls_serendipity("growing caterpillar", captured))):
            with provenance_agent.override(model=FunctionModel(_provenance_pass)):
                response = await main.chat(request)

        self.assertTrue(response.reply)
        self.assertTrue(captured)
        self.assertIsInstance(captured[0], ConnectionProposal)

    async def test_slug_variance_still_reaches_corpus_and_yields_proposal(self) -> None:
        captured: list = []
        request = ChatRequest(
            session_id=self.session_id,
            message="I'm reading Alice's Adventures in Wonderland and I've finished Chapter 5",
        )

        with muse_chat_agent.override(model=FunctionModel(_muse_calls_serendipity("growing caterpillar", captured))):
            with provenance_agent.override(model=FunctionModel(_provenance_pass)):
                response = await main.chat(request)

        self.assertTrue(response.reply)
        self.assertTrue(captured)
        self.assertIsInstance(captured[0], ConnectionProposal)


if __name__ == "__main__":
    unittest.main()
