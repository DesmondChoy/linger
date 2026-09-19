"""End-to-end test pinning the decline path a generic memory match must take."""

import json
import os
import tempfile
import unittest
from pathlib import Path
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
    from apps.backend import chat_turn, sessions
    from apps.backend.schemas import ChatRequest
    get_settings()

from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from src.linger.agents.muse.agent import muse_chat_agent
from src.linger.agents.provenance.agent import provenance_agent
from src.linger.agents.serendipity.agent import serendipity_agent
from src.linger.agents.serendipity.models import (
    ConnectionDecline,
    ConnectionExplorationResult,
    MemorySearchResult,
)
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.evaluation_transcript import bind_evaluation_transcript_sink
from src.linger.services.memory import (
    AccountContext,
    AutomaticMemoryCandidate,
    MemoryPolicyService,
)


LINE = (
    "The dance CCA is moving into the band room two afternoons a week from next "
    "term. How do I raise this with the dance teacher without coming across as "
    "territorial?"
)
LORRY_MEMORY = "The percussion lorry was late for the band concert, so I set up the hall myself."
PRACTICE_MEMORY = "Morning practice before school gives the band a predictable window."
REPLY = "Lead with the shared goal and ask what would work for both groups."
NO_MEMORY = {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"}


def _tool_returns(messages) -> dict[str, object]:
    return {
        part.tool_name: part.content
        for message in messages
        for part in getattr(message, "parts", ())
        if isinstance(part, ToolReturnPart)
    }


def _json_prompts(messages) -> list[dict]:
    return [
        json.loads(part.content)
        for message in messages
        for part in getattr(message, "parts", ())
        if isinstance(getattr(part, "content", None), str)
        and part.content.lstrip().startswith("{")
    ]


class SerendipityGenericDeclineTests(unittest.IsolatedAsyncioTestCase):
    session_id = "serendipity-generic-decline-e2e"

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.service = MemoryPolicyService(Path(self._directory.name))
        self.account = AccountContext("serendipity-generic-decline-test")
        self._boundary_patcher = patch.object(
            chat_turn,
            "assess_emotional_boundary",
            return_value=EmotionalBoundaryAssessment(decision="continue_reflection"),
        )
        self._boundary_patcher.start()
        self.addCleanup(self._boundary_patcher.stop)

    def tearDown(self) -> None:
        sessions.clear(self.session_id)

    async def test_generic_memory_matches_decline_and_release_a_plain_reply(self) -> None:
        self.service.set_capture_enabled(self.account, True)
        for index, text in enumerate((LORRY_MEMORY, PRACTICE_MEMORY)):
            self.service.save_automatic(self.account, AutomaticMemoryCandidate(
                text=text,
                source_event_id=f"fixture-band-{index}",
                review_allows_capture=True,
                contains_sensitive_content=False,
            ))
        self.service.set_capture_enabled(self.account, False)
        events = []
        provenance_inputs = []

        class Sink:
            def begin_agent_exchange(self, **kwargs):
                return None

            def complete_agent_exchange(self, *args, **kwargs):
                pass

            def record_connection_event(self, event):
                events.append(event)

        def discover(messages, info: AgentInfo) -> ModelResponse:
            returns = _tool_returns(messages)
            if "search_memories" not in returns:
                return ModelResponse(parts=[ToolCallPart(
                    "search_memories", {"query": "band room dance teacher"},
                )])
            found = MemorySearchResult.model_validate(returns["search_memories"])
            self.assertEqual("evidence_found", found.outcome)
            self.assertEqual(2, len(found.evidence))
            decline_tool = next(
                tool for tool in info.output_tools
                if ConnectionDecline.__name__ in tool.name
            )
            return ModelResponse(parts=[ToolCallPart(decline_tool.name, {
                "status": "decline",
                "reason": "generic_theme_match",
                "safe_next_step": "Reply to the new situation without a stored connection.",
            })])

        def muse(messages, info: AgentInfo) -> ModelResponse:
            returns = _tool_returns(messages)
            if "serendipity_explore" not in returns:
                return ModelResponse(parts=[ToolCallPart(
                    "serendipity_explore", {"intent": "find_connection"},
                )])
            exploration = ConnectionExplorationResult.model_validate(
                returns["serendipity_explore"]
            )
            self.assertEqual("decline", exploration.decision.status)
            self.assertEqual("generic_theme_match", exploration.decision.reason)
            self.assertEqual((), exploration.evidence)
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
                "reply": REPLY,
                "evidence_uses": [],
                "memory": NO_MEMORY,
            })])

        def provenance(messages, info: AgentInfo) -> ModelResponse:
            provenance_inputs.append(next(
                prompt for prompt in _json_prompts(messages)
                if "canonical_connection_evidence" in prompt
            ))
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
                "findings": [],
                "response_decision": "pass",
                "emotional_boundary_decision": "not_required",
                "capture_decision": "no_candidate",
            })])

        with bind_evaluation_transcript_sink(Sink()):
            with muse_chat_agent.override(model=FunctionModel(muse)):
                with serendipity_agent.override(model=FunctionModel(discover)):
                    with provenance_agent.override(model=FunctionModel(provenance)):
                        response = await chat_turn.run_chat_turn(
                            ChatRequest(session_id=self.session_id, message=LINE),
                            self.service, self.account,
                        )

        self.assertEqual("muse_candidate", response.inspection.release.release_source)
        self.assertEqual(("pass",), response.inspection.release.provenance_verdicts)
        self.assertEqual(REPLY, response.reply)

        self.assertEqual(1, len(provenance_inputs))
        payload = provenance_inputs[0]
        self.assertEqual([], payload["canonical_connection_evidence"])
        outcomes = payload["untrusted_tool_outcomes"]
        self.assertEqual(["serendipity_explore"], [item["tool_name"] for item in outcomes])
        self.assertEqual("decline", outcomes[0]["content"]["decision"]["status"])
        self.assertEqual(
            "generic_theme_match", outcomes[0]["content"]["decision"]["reason"],
        )

        searches = [event for event in events if event.kind == "search"]
        self.assertEqual(
            [("memory", "search_memories", "evidence_found")],
            [(event.source, event.operation, event.status) for event in searches],
        )
        self.assertEqual(2, len(searches[0].evidence_json))
        discoveries = [event for event in events if event.kind == "discovery"]
        self.assertEqual(["decline"], [event.status for event in discoveries])
        decision = json.loads(discoveries[0].decision_json)
        self.assertEqual("generic_theme_match", decision["reason"])
        self.assertEqual((), events[-1].released_evidence_ids)
        self.assertNotIn(LORRY_MEMORY, response.model_dump_json())
        self.assertNotIn(PRACTICE_MEMORY, response.model_dump_json())


if __name__ == "__main__":
    unittest.main()
