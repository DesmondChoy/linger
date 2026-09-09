"""End-to-end tests driving the real chat route through Muse's serendipity_explore tool."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
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
from src.linger.services.memory import AccountContext, MemoryPolicyService, AutomaticMemoryCandidate
from src.linger.agents.serendipity.tools import GuardedExaSearch
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.contracts.turn import ReleaseScope
from src.linger.corpus.alice import BOOK
from src.linger.evaluation_transcript import bind_evaluation_transcript_sink


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

    async def test_mixed_sources_release_through_real_tools_and_independent_review(self) -> None:
        url = "https://example.com/continuity"
        memory_text = "My piano routine changed after moving home."
        self.service.set_capture_enabled(self.account, True)
        saved = self.service.save_automatic(self.account, AutomaticMemoryCandidate(
            text=memory_text, source_event_id="fixture-prior-reflection",
            review_allows_capture=True, contains_sensitive_content=False,
        )).record
        self.service.set_capture_enabled(self.account, False)
        provider_calls = []
        provenance_inputs = []
        events = []

        class ExaClient:
            async def search(self, query, **kwargs):
                provider_calls.append(("search", query))
                return SimpleNamespace(results=[SimpleNamespace(
                    url=url, title="Continuity", published_date=None, author=None,
                    highlights=["A public lead about continuity."],
                )], output=None)
            async def get_contents(self, urls, **kwargs):
                provider_calls.append(("get_page", urls))
                return SimpleNamespace(results=[SimpleNamespace(
                    url=url, title="Continuity", published_date=None, author=None,
                    text="Continuity can coexist with gradual variation.",
                )])

        class Sink:
            def begin_agent_exchange(self, **kwargs):
                return None
            def complete_agent_exchange(self, *args, **kwargs):
                pass
            def record_connection_event(self, event):
                events.append(event)

        def discover(messages, info):
            returns = {
                part.tool_name: part.content
                for message in messages for part in getattr(message, "parts", ())
                if isinstance(part, ToolReturnPart)
            }
            if "search_librarian" not in returns:
                return ModelResponse(parts=[ToolCallPart("search_librarian", {"query": "Alice changing size identity Caterpillar"})])
            if "search_memories" not in returns:
                return ModelResponse(parts=[ToolCallPart("search_memories", {"query": "piano routine"})])
            if "web_search" not in returns:
                return ModelResponse(parts=[ToolCallPart("web_search", {"query": "metaphysics continuity"})])
            if "get_page" not in returns:
                return ModelResponse(parts=[ToolCallPart("get_page", {"url": url})])
            response = _serendipity_proposes(messages, info)
            args = response.parts[0].args
            for item in args["shortlist"]:
                item["evidence_ids"] = [item["evidence_ids"][0], saved.memory_id, url]
            args["policy_flags"] = ["contains_web_claim"]
            return response

        def muse(messages, info):
            results = [part.content for message in messages for part in getattr(message, "parts", ())
                       if isinstance(part, ToolReturnPart) and part.tool_name == "serendipity_explore"]
            if not results:
                return ModelResponse(parts=[ToolCallPart("serendipity_explore", {})])
            exploration = ConnectionExplorationResult.model_validate(results[-1])
            self.assertIsInstance(exploration.decision, ConnectionProposal)
            uses = []
            for item in exploration.evidence:
                use = {"source_kind": item.source_kind, "evidence_id": item.evidence_id, "exact_quote": None}
                if item.source_kind == "book_corpus":
                    use["source_location"] = item.location
                uses.append(use)
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
                "reply": f"Your earlier reflection may resonate with Alice's changes and [this essay]({url}).",
                "evidence_uses": uses,
                "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
            })])

        def provenance(messages, info):
            for message in messages:
                for part in getattr(message, "parts", ()):
                    text = getattr(part, "content", None)
                    if isinstance(text, str) and text.startswith("{"):
                        payload = json.loads(text)
                        if "canonical_connection_evidence" in payload:
                            provenance_inputs.append(payload)
            return _provenance_pass(messages, info)

        scope = ReleaseScope(work_id=BOOK.work_id, book_version_id=BOOK.book_version_id, chapter_max=5)
        with patch("src.linger.orchestration.connection.web_reach_permitted", return_value=True), patch.object(
            chat_turn, "web_reach_permitted", return_value=True,
        ), patch("src.linger.orchestration.connection._web_capability", return_value=GuardedExaSearch(client=ExaClient())):
            with bind_evaluation_transcript_sink(Sink()):
                with muse_chat_agent.override(model=FunctionModel(muse)):
                    with serendipity_agent.override(model=FunctionModel(discover)):
                        with provenance_agent.override(model=FunctionModel(provenance)):
                            response = await chat_turn.run_chat_turn(
                                ChatRequest(session_id=self.session_id, message="Could my earlier reflection connect to the book and a public essay?"),
                                self.service, self.account, initial_reading=scope, public_source_urls=(url,),
                            )
        self.assertEqual("muse_candidate", response.inspection.release.release_source)
        self.assertEqual(["search", "get_page"], [call[0] for call in provider_calls])
        self.assertTrue(provenance_inputs[-1]["canonical_book_evidence"])
        self.assertEqual({"memory", "web"}, {
            item["source_kind"] for item in provenance_inputs[-1]["canonical_connection_evidence"]
        })
        self.assertEqual(["sent"], [event.status for event in events if event.kind == "query"])
        self.assertNotIn(memory_text, response.model_dump_json())
        self.assertEqual(1, len(self.service.list_active(self.account)))
        self.assertIn(url, events[-1].released_evidence_ids)
        self.assertIn(saved.memory_id, events[-1].released_evidence_ids)

    async def test_trusted_initial_reading_reaches_real_discovery_without_extra_line(self) -> None:
        captured: list = []
        scope = ReleaseScope(work_id=BOOK.work_id, book_version_id=BOOK.book_version_id, chapter_max=5)
        request = ChatRequest(session_id=self.session_id, message="Could this change echo an earlier passage?")
        events = []

        class Sink:
            def begin_agent_exchange(self, **kwargs):
                return None
            def complete_agent_exchange(self, *args, **kwargs):
                pass
            def record_connection_event(self, event):
                events.append(event)

        with bind_evaluation_transcript_sink(Sink()):
            with muse_chat_agent.override(model=FunctionModel(_muse_calls_serendipity(captured))):
                with serendipity_agent.override(model=FunctionModel(_serendipity_proposes)):
                    with provenance_agent.override(model=FunctionModel(_provenance_pass)):
                        response = await chat_turn.run_chat_turn(
                            request, self.service, self.account,
                            initial_reading=scope, public_source_urls=(),
                        )
        self.assertEqual("muse_candidate", response.inspection.release.release_source)
        self.assertEqual(1, len(sessions.reader_statements(self.session_id)))
        self.assertEqual("proposal", next(event.status for event in events if event.kind == "discovery"))
        self.assertEqual("muse_candidate", events[-1].release_source)
        self.assertTrue(next(event.evidence_json for event in events if event.kind == "discovery"))
        self.assertNotIn("evidence_json", response.model_dump_json())

    def test_initial_reading_rejects_conflicting_or_stale_setup(self) -> None:
        scope = ReleaseScope(work_id=BOOK.work_id, book_version_id=BOOK.book_version_id, chapter_max=5)
        request = ChatRequest(session_id=self.session_id, message="I've finished Chapter 2.")
        with self.assertRaisesRegex(ValueError, "conflicts"):
            chat_turn._apply_initial_reading(request, scope)
        with self.assertRaisesRegex(ValueError, "unfinished"):
            chat_turn._apply_initial_reading(
                ChatRequest(session_id=self.session_id, message="I haven't finished Alice's Adventures in Wonderland; could you explain its ending?"),
                scope,
            )
        with self.assertRaisesRegex(ValueError, "registered"):
            chat_turn._apply_initial_reading(
                ChatRequest(session_id=self.session_id, message="A connection?"),
                scope.model_copy(update={"book_version_id": "unknown"}),
            )
        sessions.set_book_selection(self.session_id, sessions.BookSelection(book_id=BOOK.work_id))
        with self.assertRaisesRegex(ValueError, "fresh"):
            chat_turn._apply_initial_reading(ChatRequest(session_id=self.session_id, message="A connection?"), scope)

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
