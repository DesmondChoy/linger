"""End-to-end tests driving the real chat route through Muse's serendipity_explore tool."""

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
    from apps.backend import chat_turn, main, sessions
    from apps.backend.schemas import ChatRequest
    get_settings()

from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from src.linger.agents.muse.agent import muse_chat_agent
from src.linger.agents.provenance.agent import provenance_agent
from src.linger.agents.serendipity.agent import serendipity_agent
from src.linger.agents.serendipity.models import (
    ConnectionExplorationResult,
    ConnectionProposal,
    InternalSearchResult,
)
from src.linger.services.memory import AccountContext, MemoryPolicyService
from src.linger.contracts.emotional import EmotionalBoundaryAssessment


def _provenance_pass(messages, info: AgentInfo) -> ModelResponse:
    tool = info.output_tools[0]
    return ModelResponse(
        parts=[
            ToolCallPart(
                tool.name,
                {
                    "findings": [],
                    "response_decision": "pass",
                    "emotional_boundary_decision": "not_required",
                    "capture_decision": "no_candidate",
                },
            )
        ]
    )


def _muse_calls_serendipity(captured: list):
    def _respond(messages, info: AgentInfo) -> ModelResponse:
        for message in messages:
            for part in getattr(message, "parts", []):
                if isinstance(part, ToolReturnPart) and part.tool_name == "serendipity_explore":
                    captured.append(part.content)
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("serendipity_explore", {})])
        output_tool = info.output_tools[0]
        exploration = ConnectionExplorationResult.model_validate(captured[-1])
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {
                        "reply": "Here's a connection worth sitting with.",
                        "evidence_uses": [
                            {
                                "source_kind": "book_corpus",
                                "evidence_id": item.evidence_id,
                                "source_location": item.location,
                                "exact_quote": None,
                            }
                            for item in exploration.evidence
                        ],
                        "memory": {
                            "kind": "no_memory_candidate",
                            "reason_code": "automatic_capture_disabled",
                        },
                    },
                )
            ]
        )

    return _respond


def _serendipity_proposes(messages, info: AgentInfo) -> ModelResponse:
    payload = None
    search_result = None
    for message in messages:
        for part in getattr(message, "parts", []):
            content = getattr(part, "content", None)
            if isinstance(content, str) and content.lstrip().startswith("{"):
                parsed = json.loads(content)
                if "scope" in parsed and "cue" in parsed:
                    payload = parsed
            if (
                isinstance(part, ToolReturnPart)
                and part.tool_name == "search_librarian"
            ):
                search_result = InternalSearchResult.model_validate(part.content)
    assert payload is not None
    if search_result is None:
        return ModelResponse(
            parts=[
                ToolCallPart(
                    "search_librarian",
                    {
                        "query": "Alice changing size identity Caterpillar",
                        "max_results_per_source": 5,
                    },
                )
            ]
        )

    evidence_ids = [item.evidence_id for item in search_result.evidence[:2]]
    assert evidence_ids
    second_ids = evidence_ids[-1:]
    tool = info.output_tools[0]
    return ModelResponse(
        parts=[
            ToolCallPart(
                tool.name,
                {
                    "status": "proposal",
                    "shortlist": [
                        {
                            "candidate_id": "candidate-identity",
                            "tentative_claim": "Two passages connect physical change with uncertain identity.",
                            "evidence_ids": evidence_ids,
                            "shared_structure": "Both passages unsettle a stable account of identity.",
                            "meaningful_difference": "One stages change; the other asks Alice to explain it.",
                            "interpretation": "The recurrence may make the question feel like a test.",
                            "rubric": {
                                "cue_fit": "direct",
                                "reflective_value": "high",
                                "safety": "clear",
                                "disqualifiers": [],
                            },
                            "comparison_note": "This is the most direct textual bridge.",
                        },
                        {
                            "candidate_id": "candidate-authority",
                            "tentative_claim": "The scene may also connect uncertainty with unequal authority.",
                            "evidence_ids": second_ids,
                            "shared_structure": "Alice is asked to account for herself from an unequal position.",
                            "meaningful_difference": "This focuses on the exchange rather than repeated bodily change.",
                            "interpretation": "The imbalance may add to the scene's discomfort.",
                            "rubric": {
                                "cue_fit": "partial",
                                "reflective_value": "medium",
                                "safety": "clear",
                                "disqualifiers": [],
                            },
                            "comparison_note": "This is plausible but less directly supported than identity change.",
                        },
                    ],
                    "selected_candidate_id": "candidate-identity",
                    "uncertainty": "medium",
                    "presentation": payload["presentation"],
                    "suggested_follow_up": "Does that recurrence change how the scene feels?",
                    "policy_flags": [],
                },
            )
        ]
    )


class ChatConnectionEndToEndTests(unittest.IsolatedAsyncioTestCase):
    session_id = "chat-connection-e2e"

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.service = MemoryPolicyService(Path(self._directory.name))
        self.account = AccountContext("chat-connection-test")
        self._boundary_patcher = patch.object(
            chat_turn,
            "assess_emotional_boundary",
            return_value=EmotionalBoundaryAssessment(
                decision="continue_reflection"
            ),
        )
        self._boundary_patcher.start()
        self.addCleanup(self._boundary_patcher.stop)

    def tearDown(self) -> None:
        sessions.clear(self.session_id)

    async def test_confirmed_book_and_chapter_reaches_real_connection_pipeline(self) -> None:
        captured: list = []
        request = ChatRequest(
            session_id=self.session_id,
            message="I'm reading Alice's Adventures in Wonderland and I've finished Chapter 5",
        )

        with muse_chat_agent.override(model=FunctionModel(_muse_calls_serendipity(captured))):
            with serendipity_agent.override(model=FunctionModel(_serendipity_proposes)):
                with provenance_agent.override(model=FunctionModel(_provenance_pass)):
                    response = await main.chat(request, self.service, self.account)

        self.assertEqual("muse_candidate", response.inspection.release.release_source)
        self.assertIsNone(response.inspection.release.failure_stage)
        self.assertTrue(captured)
        self.assertIsInstance(captured[0], ConnectionExplorationResult)
        self.assertIsInstance(captured[0].decision, ConnectionProposal)
        self.assertTrue(captured[0].evidence)
        self.assertIsNone(response.inspection.connection_decline)
        self.assertEqual([], response.inspection.librarian_grounding)
        inspection_fields = response.inspection.model_dump()
        for removed_field in (
            "connection_discovery_input",
            "serendipity_searches",
            "librarian_request",
            "evidence_bundle",
            "connection_proposal",
        ):
            self.assertNotIn(removed_field, inspection_fields)
        self.assertNotIn(
            "Two passages connect physical change",
            response.model_dump_json(),
        )
        serendipity_trace = next(
            trace
            for trace in response.inspection.traces
            if trace["agent"] == "Serendipity"
        )
        self.assertEqual("complete", serendipity_trace["status"])
        librarian_trace = next(
            trace
            for trace in response.inspection.traces
            if trace["agent"] == "Librarian"
        )
        self.assertEqual("complete", librarian_trace["status"])

    async def test_slug_variance_still_reaches_corpus_and_yields_proposal(self) -> None:
        captured: list = []
        request = ChatRequest(
            session_id=self.session_id,
            message="I'm reading Alice's Adventures in Wonderland and I've finished Chapter 5",
        )

        with muse_chat_agent.override(model=FunctionModel(_muse_calls_serendipity(captured))):
            with serendipity_agent.override(model=FunctionModel(_serendipity_proposes)):
                with provenance_agent.override(model=FunctionModel(_provenance_pass)):
                    response = await main.chat(request, self.service, self.account)

        self.assertEqual("muse_candidate", response.inspection.release.release_source)
        self.assertTrue(captured)
        self.assertIsInstance(captured[0], ConnectionExplorationResult)
        self.assertIsInstance(captured[0].decision, ConnectionProposal)
        self.assertNotIn("connection_proposal", response.inspection.model_dump())
        self.assertNotIn("serendipity_searches", response.inspection.model_dump())


if __name__ == "__main__":
    unittest.main()
