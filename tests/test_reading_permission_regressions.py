"""Only asserted, current reading progress may authorize book access."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_core import to_jsonable_python

from test_progress_store import ALICE, BOOK_QUESTION, NO_MEMORY, _provenance
from apps.backend import chat_turn, reading_progress, sessions
from apps.backend.progress_store import ReadingProgressStore, SavedProgress
from apps.backend.schemas import ChatRequest
from src.linger.agents.muse.agent import muse_chat_agent
from src.linger.agents.provenance.agent import provenance_agent
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.contracts.triage import TurnNeeds
from src.linger.contracts.turn import ConfirmedReading
from src.linger.orchestration import routing, turn_context
from src.linger.services.memory import AccountContext, MemoryPolicyService


UNCERTAIN_COMPLETIONS = (
    "I cannot remember whether I finished chapter 9.",
    "I don't know if I've finished chapter 9.",
    "If I've finished chapter 9, what will I know?",
    "Have I finished chapter 9?",
    "I've finished chapter 9?",
    "Maybe I've finished chapter 9.",
    "I didn't say I finished chapter 9.",
    "I never said I've finished chapter 9.",
    "My friend said I finished chapter 9.",
)
RETRACTION = "Wait, I'm not that far in Alice's Adventures in Wonderland."
QUALIFIED_COMPLETIONS = (
    "I've finished chapter 9, if my memory is right.",
    "I've finished Ch. 9, if my memory is right.",
    "I've finished chapter 9, or maybe I haven't.",
    "I've finished chapter 9, I think, but I am not sure.",
    "I've finished chapter 9, but I am unsure.",
    "I've finished chapter 9, but I am uncertain.",
    "I've finished chapter 9, possibly.",
    "I've finished chapter 9, but I cannot remember.",
    "I've finished chapter 9, but I can't remember.",
)


@pytest.mark.parametrize("message", (*UNCERTAIN_COMPLETIONS, *QUALIFIED_COMPLETIONS))
def test_uncertain_completion_never_grants_a_chapter(message):
    session_id = "uncertain-completion"
    sessions.set_book_selection(session_id, sessions.BookSelection(book_id=ALICE))
    try:
        resolution = chat_turn.resolve_reading_context(ChatRequest(session_id=session_id, message=message))
        assert resolution.status != "confirmed"
        assert chat_turn._saved_progress_to_record(resolution) is None
    finally:
        sessions.clear(session_id)


@pytest.mark.parametrize("message", (
    "I've finished chapter 9. What happens next?",
    "I've finished chapter 9. I think the ending is strange.",
    "I've finished Ch. 9. I think the ending is strange.",
    "Chapter 9 is the last chapter I've finished.",
    'The note says "if I finished chapter 2". I finished chapter 9.',
))
def test_asserted_completion_keeps_its_authority(message):
    session_id = "asserted-completion"
    sessions.set_book_selection(session_id, sessions.BookSelection(book_id=ALICE))
    try:
        resolution = chat_turn.resolve_reading_context(ChatRequest(session_id=session_id, message=message))
        assert resolution.status == "confirmed"
        assert resolution.chapter_max == 9
    finally:
        sessions.clear(session_id)


@pytest.mark.parametrize("chapter_max", (None, 2))
def test_retained_corrections_filter_evidence_after_the_active_book_changes(chapter_max):
    session_id = "retained-correction-evidence"
    version = chat_turn.librarian_service.version_for(ALICE)
    record = chat_turn.librarian_service.fetch_by_id(f"{version}-ch05-ln0964-0964")
    assert record is not None
    try:
        sessions.set_reading_progress(session_id, sessions.ReadingProgress(ALICE, version, "main", chapter_max))
        sessions.set_reading_progress(session_id, sessions.ReadingProgress(
            "pg500", chat_turn.librarian_service.version_for("pg500"), "main", 4,
        ))
        assert reading_progress.permitted_evidence(session_id, (record,)) == ()
        sessions.set_reading_progress(session_id, None)
        assert reading_progress.permitted_evidence(session_id, (record,)) == ()
    finally:
        sessions.clear(session_id)


class ReadingPermissionPipelineTests(unittest.IsolatedAsyncioTestCase):
    session_id = "reading-permission-regression"

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = ReadingProgressStore(Path(directory.name) / "progress.sqlite3")
        self.service = MemoryPolicyService(Path(directory.name) / "memories")
        self.account = AccountContext("reading-permission-reader")
        self.routes = []
        boundary = patch.object(
            chat_turn, "assess_emotional_boundary",
            return_value=EmotionalBoundaryAssessment(decision="continue_reflection"),
        )
        boundary.start()
        self.addCleanup(boundary.stop)
        self.addCleanup(sessions.clear, self.session_id)

    async def turn(self, message, *, route=False, comparison=False):
        async def triage(*_args, **_kwargs):
            return TurnNeeds(book_content="yes" if route or comparison else "no",
                             memory="source_comparison" if comparison else "none")

        def muse(messages, info):
            returns = [part for message in messages for part in message.parts
                       if isinstance(part, ToolReturnPart) and part.tool_name == "librarian_route"]
            if route and not returns:
                return ModelResponse(parts=[ToolCallPart("librarian_route", {})])
            self.routes.extend(to_jsonable_python(part.content) for part in returns)
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
                "reply": "What part of feeling out of place stays with you?",
                "evidence_uses": [], "memory": NO_MEMORY,
            })])

        with patch.object(chat_turn, "triage_turn", triage), \
                muse_chat_agent.override(model=FunctionModel(muse)), \
                provenance_agent.override(model=FunctionModel(_provenance)):
            return await chat_turn.run_chat_turn(
                ChatRequest(session_id=self.session_id, message=message),
                self.service, self.account, progress_store=self.store,
            )

    async def test_uncertainty_cannot_raise_persisted_progress(self):
        await self.turn("I've finished chapter 2 of Alice's Adventures in Wonderland.")
        response = await self.turn(UNCERTAIN_COMPLETIONS[0])

        self.assertIsNone(response.inspection.muse_turn["reading_context"])
        # Withdrawing the ceiling here also erases it for later conversations.
        self.assertIsNone(self.store.get(self.account.account_id, ALICE))
        self.assertIsNone(sessions.reading_progress(self.session_id).chapter_max)

    async def test_qualified_completion_cannot_raise_persisted_progress(self):
        for message in QUALIFIED_COMPLETIONS:
            with self.subTest(message=message):
                sessions.clear(self.session_id)
                await self.turn("I've finished chapter 2 of Alice's Adventures in Wonderland.")
                response = await self.turn(message)
                self.assertIsNone(response.inspection.muse_turn["reading_context"])
                self.assertIsNone(self.store.get(self.account.account_id, ALICE))
                await self.turn("Actually, I've finished chapter 3.")
                self.assertEqual(3, self.store.get(self.account.account_id, ALICE).chapter_max)

    async def test_retraction_withholds_routing_on_this_and_later_turns(self):
        await self.turn("I've finished chapter 9 of Alice's Adventures in Wonderland.")
        infer = AsyncMock(side_effect=AssertionError("A retraction requires reader confirmation."))
        with patch.object(routing, "infer_spoiler_boundary", infer):
            await self.turn(f"{RETRACTION} {BOOK_QUESTION}", route=True)
            await self.turn(BOOK_QUESTION, route=True)

        self.assertEqual(["clarification", "clarification"], [result["kind"] for result in self.routes])
        self.assertIsNone(sessions.reading_progress(self.session_id).chapter_max)
        infer.assert_not_awaited()

    async def test_new_conversation_retraction_withholds_saved_routing(self):
        self.store.record(self.account.account_id, SavedProgress(ALICE, "main", 9))
        infer = AsyncMock(side_effect=AssertionError("A retraction requires reader confirmation."))
        with patch.object(routing, "infer_spoiler_boundary", infer):
            await self.turn(f"{RETRACTION} {BOOK_QUESTION}", route=True)
            await self.turn(BOOK_QUESTION, route=True)

        self.assertEqual(["clarification", "clarification"], [result["kind"] for result in self.routes])
        infer.assert_not_awaited()

    async def test_retraction_withholds_comparison_on_this_and_later_turns(self):
        await self.turn("I've finished chapter 9 of Alice's Adventures in Wonderland.")
        for work_id in ("pg500", "pg23"):
            self.store.record(self.account.account_id, SavedProgress(work_id, "main", 4))

        first = await self.turn(f"{RETRACTION} Does it connect to anything else?", comparison=True)
        following = await self.turn("Does it connect to anything else?", comparison=True)

        for response in (first, following):
            scopes = response.inspection.muse_turn["connection_book_scopes"]
            self.assertEqual({"pg500", "pg23"}, {scope["work_id"] for scope in scopes})

    async def test_new_explicit_progress_replaces_a_retraction(self):
        await self.turn("I've finished chapter 9 of Alice's Adventures in Wonderland.")
        await self.turn(RETRACTION)
        await self.turn("Actually, I've finished chapter 3.")
        await self.turn(BOOK_QUESTION, route=True)

        self.assertEqual([("routed", 3)], [
            (result["kind"], result["max_chapter_inclusive"]) for result in self.routes
        ])
        self.assertEqual(3, self.store.get(self.account.account_id, ALICE).chapter_max)

    async def test_retraction_survives_a_different_books_progress(self):
        await self.turn("I've finished chapter 9 of Alice's Adventures in Wonderland.")
        await self.turn(RETRACTION)
        await self.turn("I've finished chapter 4 of Pinocchio.")
        infer = AsyncMock(side_effect=AssertionError("A retraction requires reader confirmation."))
        with patch.object(routing, "infer_spoiler_boundary", infer):
            await self.turn(BOOK_QUESTION, route=True)

        self.assertEqual(["clarification"], [result["kind"] for result in self.routes])
        infer.assert_not_awaited()

    async def test_correction_targets_its_book_and_preserves_other_comparison_permissions(self):
        await self.turn("I've finished chapter 9 of Alice's Adventures in Wonderland.")
        await self.turn("I've finished chapter 4 of Pinocchio.")
        self.store.record(self.account.account_id, SavedProgress("pg23", "main", 4))
        await self.turn(RETRACTION)

        self.assertIsNone(sessions.reading_progress_for(self.session_id, ALICE).chapter_max)
        self.assertEqual(4, sessions.reading_progress_for(self.session_id, "pg500").chapter_max)
        response = await self.turn("Does it connect to anything else?", comparison=True)
        self.assertEqual({"pg500", "pg23"}, {
            scope["work_id"] for scope in response.inspection.muse_turn["connection_book_scopes"]
        })

    async def test_retracted_work_cannot_fall_back_to_inferred_permission(self):
        version = chat_turn.librarian_service.version_for(ALICE)
        sessions.set_book_selection(self.session_id, sessions.BookSelection(book_id=ALICE))
        sessions.set_reading_progress(
            self.session_id, sessions.ReadingProgress(ALICE, version, "main", None),
        )
        for saved in ({}, {ALICE: ConfirmedReading(work_id=ALICE, chapter_max=9)}):
            with self.subTest(saved=bool(saved)):
                tokens = (
                    turn_context.set_confirmed_reading(None),
                    turn_context.set_saved_readings(saved),
                    turn_context.set_session_id(self.session_id),
                )
                infer = AsyncMock(side_effect=AssertionError("A retraction requires reader confirmation."))
                try:
                    with patch.object(routing, "infer_spoiler_boundary", infer):
                        result = await routing.route_reader_message(BOOK_QUESTION)
                    self.assertEqual("clarification", result.kind)
                    self.assertIsNone(turn_context.confirmed_reading())
                    infer.assert_not_awaited()
                finally:
                    turn_context.reset_session_id(tokens[2])
                    turn_context.reset_saved_readings(tokens[1])
                    turn_context.reset_confirmed_reading(tokens[0])
