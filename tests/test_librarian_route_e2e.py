"""End-to-end tests for Muse-initiated Librarian routing through the real chat route.

These exercise the tool wiring itself (contextvars set by the application,
read by `librarian_route`/`librarian_search` inside one Muse turn, and by the
deterministic release gate afterward) rather than mocking `reflection_reply`.
"""

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
from pydantic_core import to_jsonable_python

from src.linger.agents.librarian.models import (
    BoundaryInferenceDecision,
    EvidenceStrengthDecision,
)
from src.linger.agents.muse.agent import muse_chat_agent
from src.linger.agents.provenance.agent import provenance_agent
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.services.memory import (
    AccountContext,
    AutomaticMemoryCandidate,
    MemoryPolicyService,
)

BOOK_REQUEST_MESSAGE = "Why does the Caterpillar ask who Alice is?"


async def _sufficient_strength(query, evidence):
    return EvidenceStrengthDecision(
        evidence_strength="sufficient",
        strength_reason="The passages directly answer the question.",
        relevant_evidence_ids=[record.evidence_id for record in evidence],
    )


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


def _provenance_pass_capturing(captured: list):
    """Same as `_provenance_pass`, but records the exact input Provenance saw.

    `_provenance_pass` alone would hide a stale-context bug: it passes
    unconditionally regardless of what `context` it was actually given.
    """

    def _respond(messages, info: AgentInfo) -> ModelResponse:
        import json as _json

        for message in messages:
            for part in getattr(message, "parts", []):
                content = getattr(part, "content", None)
                if isinstance(content, str) and content.lstrip().startswith("{"):
                    parsed = _json.loads(content)
                    if "context" in parsed and "candidate" in parsed:
                        captured.append(parsed)
        return _provenance_pass(messages, info)

    return _respond


def _no_memory() -> dict:
    return {"kind": "no_memory_candidate", "reason_code": "transient_or_low_signal"}


def _last_tool_return(messages, tool_name: str):
    result = None
    for message in messages:
        for part in getattr(message, "parts", []):
            if isinstance(part, ToolReturnPart) and part.tool_name == tool_name:
                result = part.content
    if result is None:
        return None
    # `part.content` is the tool's raw Python return value inside this same
    # agent run, not yet JSON-serialized the way `reflection.py` stores it.
    return to_jsonable_python(result, serialize_unknown=True)


def _plain_reply_model(reply: str):
    def _respond(messages, info: AgentInfo) -> ModelResponse:
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {"reply": reply, "evidence_uses": [], "memory": _no_memory()},
                )
            ]
        )

    return _respond


def _muse_routes_then_searches(captured: list):
    def _respond(messages, info: AgentInfo) -> ModelResponse:
        route_result = _last_tool_return(messages, "librarian_route")
        if route_result is None:
            return ModelResponse(parts=[ToolCallPart("librarian_route", {})])
        search_result = _last_tool_return(messages, "librarian_search")
        if search_result is None:
            captured.append(route_result)
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "librarian_search",
                        {
                            "query": BOOK_REQUEST_MESSAGE,
                            "work_id": route_result["work_id"],
                            "book_version_id": route_result["book_version_id"],
                            "reading_boundary": {
                                "chapter_number": route_result["max_chapter_inclusive"],
                                "chapter_state": "completed",
                            },
                            "max_final_evidence": 5,
                        },
                    )
                ]
            )
        captured.append(search_result)
        evidence = search_result.get("evidence") or []
        evidence_uses = (
            [
                {
                    "source_kind": "book_corpus",
                    "evidence_id": evidence[0]["evidence_id"],
                    "source_location": evidence[0]["location"],
                    "exact_quote": None,
                }
            ]
            if evidence
            else []
        )
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {
                        "reply": "The Caterpillar keeps pressing Alice to explain who she is.",
                        "evidence_uses": evidence_uses,
                        "memory": _no_memory(),
                    },
                )
            ]
        )

    return _respond


def _muse_routes_then_overreaches(captured: list):
    """Request a chapter far beyond the routed ceiling to probe clamping."""

    def _respond(messages, info: AgentInfo) -> ModelResponse:
        route_result = _last_tool_return(messages, "librarian_route")
        if route_result is None:
            return ModelResponse(parts=[ToolCallPart("librarian_route", {})])
        search_result = _last_tool_return(messages, "librarian_search")
        if search_result is None:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "librarian_search",
                        {
                            "query": BOOK_REQUEST_MESSAGE,
                            "work_id": route_result["work_id"],
                            "book_version_id": route_result["book_version_id"],
                            "reading_boundary": {
                                "chapter_number": 12,
                                "chapter_state": "completed",
                            },
                            "max_final_evidence": 5,
                        },
                    )
                ]
            )
        captured.append(search_result)
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {
                        "reply": "Here's what the confirmed chapters show.",
                        "evidence_uses": [],
                        "memory": _no_memory(),
                    },
                )
            ]
        )

    return _respond


def _muse_calls_route_then_replies():
    def _respond(messages, info: AgentInfo) -> ModelResponse:
        route_result = _last_tool_return(messages, "librarian_route")
        if route_result is None:
            return ModelResponse(parts=[ToolCallPart("librarian_route", {})])
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {
                        "reply": "Thanks for sharing that.",
                        "evidence_uses": [],
                        "memory": _no_memory(),
                    },
                )
            ]
        )

    return _respond


def _muse_routes_then_relays_clarification(reply: str | None = None):
    def _respond(messages, info: AgentInfo) -> ModelResponse:
        route_result = _last_tool_return(messages, "librarian_route")
        if route_result is None:
            return ModelResponse(parts=[ToolCallPart("librarian_route", {})])
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {
                        "reply": reply if reply is not None else route_result["question"],
                        "evidence_uses": [],
                        "memory": _no_memory(),
                    },
                )
            ]
        )

    return _respond


def _muse_searches_directly(captured: list, *, chapter: int):
    def _respond(messages, info: AgentInfo) -> ModelResponse:
        search_result = _last_tool_return(messages, "librarian_search")
        if search_result is None:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "librarian_search",
                        {
                            "query": BOOK_REQUEST_MESSAGE,
                            "work_id": "pg11",
                            "book_version_id": "pg11-v01b38ea4",
                            "reading_boundary": {
                                "chapter_number": chapter,
                                "chapter_state": "completed",
                            },
                            "max_final_evidence": 5,
                        },
                    )
                ]
            )
        captured.append(search_result)
        evidence = search_result.get("evidence") or []
        evidence_uses = (
            [
                {
                    "source_kind": "book_corpus",
                    "evidence_id": evidence[0]["evidence_id"],
                    "source_location": evidence[0]["location"],
                    "exact_quote": None,
                }
            ]
            if evidence
            else []
        )
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {
                        "reply": "Yes, that scene is about Alice struggling to say who she is.",
                        "evidence_uses": evidence_uses,
                        "memory": _no_memory(),
                    },
                )
            ]
        )

    return _respond


async def _confident_judge(_line, memories, evidence, _statements):
    return BoundaryInferenceDecision(
        outcome="candidate",
        work_id="pg11",
        book_version_id="pg11-v01b38ea4",
        chapter_number=max(record.chapter_number for record in evidence),
        confidence=0.95,
        authorization_basis="memory_supported",
        supporting_memory_ids=[memory.memory_id for memory in memories],
        supporting_evidence_ids=[record.evidence_id for record in evidence],
    )


async def _low_confidence_candidate_judge(_line, memories, evidence, _statements):
    return BoundaryInferenceDecision(
        outcome="candidate",
        work_id="pg11",
        book_version_id="pg11-v01b38ea4",
        chapter_number=max(record.chapter_number for record in evidence),
        confidence=0.6,
        authorization_basis="memory_supported",
        supporting_memory_ids=[memory.memory_id for memory in memories],
        supporting_evidence_ids=[record.evidence_id for record in evidence],
    )


async def _insufficient_context_judge(_line, _memories, _evidence, _statements):
    return BoundaryInferenceDecision(
        outcome="uncertain",
        confidence=0.2,
        reason_code="insufficient_context",
    )


def _muse_searches_cold_then_relays_clarification():
    """Muse calls librarian_search before any route."""

    def _respond(messages, info: AgentInfo) -> ModelResponse:
        search_result = _last_tool_return(messages, "librarian_search")
        if search_result is None:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "librarian_search",
                        {
                            "query": BOOK_REQUEST_MESSAGE,
                            "work_id": "pg11",
                            "book_version_id": "pg11-v01b38ea4",
                            "reading_boundary": None,
                            "max_final_evidence": 5,
                        },
                    )
                ]
            )
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {
                        "reply": search_result["question"],
                        "evidence_uses": [],
                        "memory": _no_memory(),
                    },
                )
            ]
        )

    return _respond


class LibrarianRouteEndToEndTests(unittest.IsolatedAsyncioTestCase):
    session_id = "librarian-route-e2e"

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.service = MemoryPolicyService(Path(self._directory.name))
        self.account = AccountContext("librarian-route-e2e-account")
        # `authorization_basis="memory_supported"` needs a backing memory.
        self.service.set_capture_enabled(self.account, True)
        self.service.save_automatic(
            self.account,
            AutomaticMemoryCandidate(
                text="Alice and the Caterpillar made me think about identity.",
                source_event_id="event-route-e2e-backing",
                review_allows_capture=True,
                contains_sensitive_content=False,
            ),
        )
        self._boundary_patcher = patch.object(
            chat_turn,
            "assess_emotional_boundary",
            return_value=EmotionalBoundaryAssessment(decision="continue_reflection"),
        )
        self._boundary_patcher.start()
        self.addCleanup(self._boundary_patcher.stop)

    def tearDown(self) -> None:
        sessions.clear(self.session_id)

    async def test_lone_garden_word_releases_without_routing_or_clarification(self) -> None:
        request = ChatRequest(
            session_id=self.session_id,
            message=(
                "My afternoon in the garden while journaling about my grandmother "
                "was calming."
            ),
        )
        reply_text = "That sounds like a gentle way to spend the afternoon."

        with muse_chat_agent.override(model=FunctionModel(_plain_reply_model(reply_text))):
            with provenance_agent.override(model=FunctionModel(_provenance_pass)):
                response = await main.chat(request, self.service, self.account)

        self.assertEqual("muse_candidate", response.inspection.release.release_source)
        self.assertEqual(reply_text, response.reply)
        self.assertEqual([], response.inspection.librarian_grounding)
        librarian_trace = next(
            trace for trace in response.inspection.traces if trace["agent"] == "Librarian"
        )
        self.assertEqual("skipped", librarian_trace["status"])
        self.assertIsNone(sessions.book_selection(self.session_id))

    async def test_genuine_book_request_routes_and_same_turn_search_succeeds(self) -> None:
        captured: list = []
        request = ChatRequest(session_id=self.session_id, message=BOOK_REQUEST_MESSAGE)

        with (
            patch(
                "src.linger.orchestration.boundary.judge_spoiler_boundary",
                side_effect=_confident_judge,
            ),
            patch(
                "src.linger.orchestration.grounding.judge_evidence_strength",
                side_effect=_sufficient_strength,
            ),
        ):
            with muse_chat_agent.override(model=FunctionModel(_muse_routes_then_searches(captured))):
                with provenance_agent.override(model=FunctionModel(_provenance_pass)):
                    response = await main.chat(request, self.service, self.account)

        self.assertEqual("muse_candidate", response.inspection.release.release_source)
        self.assertIsNone(response.inspection.release.failure_stage)
        self.assertEqual(2, len(captured))
        route_result, search_result = captured
        self.assertEqual("routed", route_result["kind"])
        self.assertEqual("pg11", route_result["work_id"])
        # The same-turn `librarian_search` call was not rejected as
        # unconfirmed: the application bound `confirmed_reading()` from the
        # routed work before Muse's next tool call in this turn.
        self.assertEqual("result", search_result["kind"])
        self.assertTrue(search_result.get("evidence"))
        librarian_trace = next(
            trace for trace in response.inspection.traces if trace["agent"] == "Librarian"
        )
        self.assertEqual("complete", librarian_trace["status"])

    async def test_provenance_sees_the_routed_authority_not_stale_pre_muse_context(
        self,
    ) -> None:
        muse_captured: list = []
        provenance_captured: list = []
        request = ChatRequest(session_id=self.session_id, message=BOOK_REQUEST_MESSAGE)

        with (
            patch(
                "src.linger.orchestration.boundary.judge_spoiler_boundary",
                side_effect=_confident_judge,
            ),
            patch(
                "src.linger.orchestration.grounding.judge_evidence_strength",
                side_effect=_sufficient_strength,
            ),
        ):
            with muse_chat_agent.override(
                model=FunctionModel(_muse_routes_then_searches(muse_captured))
            ):
                with provenance_agent.override(
                    model=FunctionModel(_provenance_pass_capturing(provenance_captured))
                ):
                    response = await main.chat(request, self.service, self.account)

        self.assertEqual("muse_candidate", response.inspection.release.release_source)
        self.assertEqual(1, len(provenance_captured))
        context = provenance_captured[0]["context"]
        # Not the stale pre-Muse view (spoiler_ceiling=None, reading_context
        # unset): Provenance sees the same routed authority the deterministic
        # release gate derived from the same tool payload.
        self.assertEqual("pg11", context["reading_context"]["work_id"])
        self.assertEqual(5, context["reading_context"]["chapter_max"])
        self.assertEqual("librarian_inferred", context["reading_context"]["boundary_source"])
        self.assertEqual(5, context["policy"]["spoiler_ceiling"])
        self.assertTrue(context["policy"]["allow_retrieval"])

    async def test_same_turn_search_clamps_to_the_routed_ceiling(self) -> None:
        captured: list = []
        request = ChatRequest(session_id=self.session_id, message=BOOK_REQUEST_MESSAGE)

        with (
            patch(
                "src.linger.orchestration.boundary.judge_spoiler_boundary",
                side_effect=_confident_judge,
            ),
            patch(
                "src.linger.orchestration.grounding.judge_evidence_strength",
                side_effect=_sufficient_strength,
            ),
        ):
            with muse_chat_agent.override(model=FunctionModel(_muse_routes_then_overreaches(captured))):
                with provenance_agent.override(model=FunctionModel(_provenance_pass)):
                    response = await main.chat(request, self.service, self.account)

        self.assertEqual("muse_candidate", response.inspection.release.release_source)
        self.assertEqual(1, len(captured))
        # Muse asked for chapter 12; the routed ceiling (chapter 5, from the
        # confident judge) still bounds what was actually searched.
        self.assertEqual(5, captured[0]["searched_scope"]["max_chapter_inclusive"])

    async def test_routing_never_widens_a_reader_confirmed_ceiling(self) -> None:
        captured: list = []
        # The reader has explicitly confirmed chapter 3 in this very message;
        # `resolve_reading_context` resolves that pre-Muse. The message also
        # carries a confident title match, so Muse (forced here, adversarially)
        # can still call `librarian_route`, and the private judge below would
        # otherwise infer as far as chapter 5.
        request = ChatRequest(
            session_id=self.session_id,
            message=(
                "I am reading Alice's Adventures in Wonderland and I have "
                "finished Chapter 3. Why does the Caterpillar ask who Alice is?"
            ),
        )

        with (
            patch(
                "src.linger.orchestration.boundary.judge_spoiler_boundary",
                side_effect=_confident_judge,
            ),
            patch(
                "src.linger.orchestration.grounding.judge_evidence_strength",
                side_effect=_sufficient_strength,
            ),
        ):
            with muse_chat_agent.override(model=FunctionModel(_muse_routes_then_overreaches(captured))):
                with provenance_agent.override(model=FunctionModel(_provenance_pass)):
                    response = await main.chat(request, self.service, self.account)

        self.assertEqual(
            "confirmed", response.inspection.context_resolution["status"]
        )
        self.assertEqual(3, response.inspection.context_resolution["chapter_max"])
        self.assertEqual("muse_candidate", response.inspection.release.release_source)
        self.assertEqual(1, len(captured))
        # The routed ceiling (5, from the confident judge) never widened the
        # reader's own confirmed chapter 3, despite Muse requesting chapter 12.
        self.assertEqual(3, captured[0]["searched_scope"]["max_chapter_inclusive"])

    async def test_routing_reads_only_the_calling_account_memories(self) -> None:
        other_account = AccountContext("librarian-route-e2e-other-account")
        self.service.set_capture_enabled(self.account, True)
        self.service.set_capture_enabled(other_account, True)
        self.service.save_automatic(
            self.account,
            AutomaticMemoryCandidate(
                text="Alice and the Caterpillar made me think about identity.",
                source_event_id="event-mine",
                review_allows_capture=True,
                contains_sensitive_content=False,
            ),
        )
        self.service.save_automatic(
            other_account,
            AutomaticMemoryCandidate(
                text="PRIVATE_OTHER_ACCOUNT_MEMORY",
                source_event_id="event-other",
                review_allows_capture=True,
                contains_sensitive_content=False,
            ),
        )

        seen_memories: list = []

        async def capturing_judge(_line, memories, evidence, statements):
            seen_memories.extend(memory.text for memory in memories)
            return await _confident_judge(_line, memories, evidence, statements)

        request = ChatRequest(session_id=self.session_id, message=BOOK_REQUEST_MESSAGE)
        with patch(
            "src.linger.orchestration.boundary.judge_spoiler_boundary",
            side_effect=capturing_judge,
        ):
            with muse_chat_agent.override(
                model=FunctionModel(_muse_calls_route_then_replies())
            ):
                with provenance_agent.override(model=FunctionModel(_provenance_pass)):
                    await main.chat(request, self.service, self.account)

        self.assertIn(
            "Alice and the Caterpillar made me think about identity.", seen_memories
        )
        self.assertNotIn("PRIVATE_OTHER_ACCOUNT_MEMORY", seen_memories)

    async def test_bare_chapter_answer_after_route_clarification_reaches_bounded_search(
        self,
    ) -> None:
        request = ChatRequest(session_id=self.session_id, message=BOOK_REQUEST_MESSAGE)

        with patch(
            "src.linger.orchestration.boundary.judge_spoiler_boundary",
            side_effect=_insufficient_context_judge,
        ):
            with muse_chat_agent.override(
                model=FunctionModel(_muse_routes_then_relays_clarification(
                    "Before we continue, which chapter have you finished?"
                ))
            ):
                with provenance_agent.override(model=FunctionModel(_provenance_pass)):
                    first_response = await main.chat(request, self.service, self.account)

        self.assertEqual("application_clarification", first_response.inspection.release.release_source)
        route = first_response.inspection.librarian_grounding[0]["response"]
        self.assertEqual(route["question"], first_response.reply)
        self.assertNotEqual("Before we continue, which chapter have you finished?", first_response.reply)
        self.assertEqual((), first_response.inspection.release.released_evidence_ids)
        self.assertIsNone(first_response.inspection.release.failure_stage)
        history = sessions.history(self.session_id)
        self.assertEqual(2, len(history))
        self.assertEqual(BOOK_REQUEST_MESSAGE, history[0].parts[0].content)
        self.assertEqual(first_response.reply, history[1].parts[0].content)
        self.assertIsNone(sessions.reading_candidate(self.session_id))
        pending = sessions.pending_clarification(self.session_id)
        self.assertIsNotNone(pending)
        assert pending is not None
        self.assertEqual("pg11", pending.book_id)
        self.assertEqual("insufficient_context", pending.reason_code)

        captured: list = []
        follow_up = ChatRequest(session_id=self.session_id, message="chapter 2")
        with patch(
            "src.linger.orchestration.grounding.judge_evidence_strength",
            side_effect=_sufficient_strength,
        ):
            with muse_chat_agent.override(
                model=FunctionModel(_muse_searches_directly(captured, chapter=2))
            ):
                with provenance_agent.override(model=FunctionModel(_provenance_pass)):
                    second_response = await main.chat(follow_up, self.service, self.account)

        context = second_response.inspection.context_resolution
        self.assertEqual("confirmed", context["status"])
        self.assertEqual("pg11", context["work_id"])
        self.assertEqual(2, context["chapter_max"])
        self.assertEqual("reader_confirmed", context["boundary_source"])
        self.assertEqual("muse_candidate", second_response.inspection.release.release_source)
        self.assertEqual(1, len(captured))
        self.assertEqual("result", captured[0]["kind"])
        self.assertEqual(2, captured[0]["searched_scope"]["max_chapter_inclusive"])
        grounding = second_response.inspection.librarian_grounding
        self.assertEqual(1, len(grounding))
        self.assertEqual(BOOK_REQUEST_MESSAGE, grounding[0]["request"]["query"])
        self.assertIsNone(sessions.pending_clarification(self.session_id))

    async def test_bare_chapter_answer_after_search_clarification_reaches_bounded_search(
        self,
    ) -> None:
        request = ChatRequest(session_id=self.session_id, message=BOOK_REQUEST_MESSAGE)

        with muse_chat_agent.override(
            model=FunctionModel(_muse_searches_cold_then_relays_clarification())
        ):
            with provenance_agent.override(model=FunctionModel(_provenance_pass)):
                first_response = await main.chat(request, self.service, self.account)

        self.assertEqual("muse_candidate", first_response.inspection.release.release_source)
        grounding = first_response.inspection.librarian_grounding
        self.assertEqual(1, len(grounding))
        self.assertEqual("clarification", grounding[0]["response"]["kind"])
        self.assertEqual("reading_boundary_unconfirmed", grounding[0]["response"]["reason_code"])
        pending = sessions.pending_clarification(self.session_id)
        self.assertIsNotNone(pending)
        assert pending is not None
        self.assertEqual("pg11", pending.book_id)
        self.assertEqual("reading_boundary_unconfirmed", pending.reason_code)

        captured: list = []
        follow_up = ChatRequest(session_id=self.session_id, message="chapter 2")
        with patch(
            "src.linger.orchestration.grounding.judge_evidence_strength",
            side_effect=_sufficient_strength,
        ):
            with muse_chat_agent.override(
                model=FunctionModel(_muse_searches_directly(captured, chapter=2))
            ):
                with provenance_agent.override(model=FunctionModel(_provenance_pass)):
                    second_response = await main.chat(follow_up, self.service, self.account)

        self.assertEqual("confirmed", second_response.inspection.context_resolution["status"])
        self.assertEqual(2, second_response.inspection.context_resolution["chapter_max"])
        self.assertEqual(1, len(captured))
        self.assertEqual("result", captured[0]["kind"])
        self.assertEqual(2, captured[0]["searched_scope"]["max_chapter_inclusive"])
        self.assertIsNone(sessions.pending_clarification(self.session_id))

    async def test_boundary_uncertain_clarification_then_followup_reaches_routed_work(
        self,
    ) -> None:
        request = ChatRequest(session_id=self.session_id, message=BOOK_REQUEST_MESSAGE)

        with patch(
            "src.linger.orchestration.boundary.judge_spoiler_boundary",
            side_effect=_low_confidence_candidate_judge,
        ):
            with muse_chat_agent.override(
                model=FunctionModel(_muse_routes_then_relays_clarification())
            ):
                with provenance_agent.override(model=FunctionModel(_provenance_pass)):
                    first_response = await main.chat(request, self.service, self.account)

        self.assertEqual("application_clarification", first_response.inspection.release.release_source)
        self.assertTrue(first_response.reply.endswith("?"))
        candidate = sessions.reading_candidate(self.session_id)
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual("pg11", candidate.book_id)
        selection = sessions.book_selection(self.session_id)
        self.assertIsNotNone(selection)
        assert selection is not None
        self.assertEqual("pg11", selection.book_id)
        self.assertIsNotNone(sessions.pending_clarification(self.session_id))

        captured: list = []
        follow_up = ChatRequest(
            session_id=self.session_id,
            message=f"I've finished Chapter {candidate.chapter}.",
        )
        with patch(
            "src.linger.orchestration.grounding.judge_evidence_strength",
            side_effect=_sufficient_strength,
        ):
            with muse_chat_agent.override(
                model=FunctionModel(_muse_searches_directly(captured, chapter=candidate.chapter))
            ):
                with provenance_agent.override(model=FunctionModel(_provenance_pass)):
                    second_response = await main.chat(follow_up, self.service, self.account)

        self.assertEqual(
            "confirmed", second_response.inspection.context_resolution["status"]
        )
        self.assertEqual("pg11", second_response.inspection.context_resolution["work_id"])
        self.assertEqual(
            candidate.chapter, second_response.inspection.context_resolution["chapter_max"]
        )
        self.assertEqual("muse_candidate", second_response.inspection.release.release_source)
        self.assertEqual(1, len(captured))
        self.assertEqual("result", captured[0]["kind"])
        self.assertIsNone(sessions.pending_clarification(self.session_id))


if __name__ == "__main__":
    unittest.main()
