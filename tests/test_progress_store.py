"""Reader-stated reading progress persists per account and book across conversations."""

import json
import os
import sqlite3
import subprocess
import sys
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
    from apps.backend import chat_turn, sessions
    from apps.backend.progress_store import ReadingProgressStore, SavedProgress
    from apps.backend.schemas import ChatRequest
    get_settings()

from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_core import to_jsonable_python
from provenance_fixtures import review_with_audits
from src.linger.agents.muse.agent import muse_chat_agent
from src.linger.agents.provenance.agent import provenance_agent
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.contracts.triage import TurnNeeds
from src.linger.contracts.turn import ConfirmedReading, ReleaseScope
from src.linger.orchestration import routing, turn_context
from src.linger.orchestration.reflection import ReflectionRelease
from src.linger.services.memory import AccountContext, MemoryPolicyService

ALICE = "pg11"
DECLARATION = (
    "I've finished Chapter 2 of Alice's Adventures in Wonderland. "
    "Alice's changes in size made me think about feeling out of place."
)
RETURNING = "I keep coming back to Alice's Adventures in Wonderland and feeling out of place."
BOOK_QUESTION = "In Alice's Adventures in Wonderland, why does the Caterpillar ask who Alice is?"


def _saved(chapter: int, work_id: str = ALICE, part_id: str = "main") -> ConfirmedReading:
    return ConfirmedReading(work_id=work_id, chapter_max=chapter, part_id=part_id)
NO_MEMORY = {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"}


def _json_prompts(messages) -> list[dict]:
    return [
        json.loads(part.content)
        for message in messages
        for part in getattr(message, "parts", ())
        if isinstance(getattr(part, "content", None), str)
        and part.content.lstrip().startswith("{")
    ]


ROUTE_RESULTS: list[dict] = []


def _muse(messages, info: AgentInfo) -> ModelResponse:
    returns = [
        part for message in messages for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == "librarian_route"
    ]
    ROUTE_RESULTS.extend(to_jsonable_python(part.content) for part in returns)
    routed = bool(returns)
    asks_book = any(
        prompt.get("muse_turn", {}).get("user_message") == BOOK_QUESTION
        for prompt in _json_prompts(messages)
    )
    if asks_book and not routed:
        return ModelResponse(parts=[ToolCallPart("librarian_route", {})])
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
        "reply": "What part of feeling out of place stays with you?",
        "evidence_uses": [],
        "memory": NO_MEMORY,
    })])


def _provenance(messages, info: AgentInfo) -> ModelResponse:
    payload = next(
        prompt for prompt in _json_prompts(messages)
        if "canonical_connection_evidence" in prompt
    )
    review = review_with_audits(payload, {
        "findings": [],
        "response_decision": "pass",
        "emotional_boundary_decision": "not_required",
        "capture_decision": "no_candidate",
        "coverage_audit": [
            {"span_index": span["span_index"], "classification": "reader_reflection"}
            for span in payload["uncovered_response_spans"]
        ],
    })
    return ModelResponse(parts=[ToolCallPart(
        info.output_tools[0].name, review.model_dump(mode="json"),
    )])


class ReadingProgressStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "r.sqlite3"
        self.store = ReadingProgressStore(self.path)

    def test_latest_statement_wins_even_when_lower(self) -> None:
        self.store.release(self.store.declare("reader", SavedProgress(ALICE, "main", 5)))
        self.store.release(self.store.declare("reader", SavedProgress(ALICE, "main", 2)))

        self.assertEqual(SavedProgress(ALICE, "main", 2), self.store.get("reader", ALICE))

    def test_progress_is_kept_per_book_and_per_account(self) -> None:
        self.store.release(self.store.declare("reader", SavedProgress(ALICE, "main", 3)))
        self.store.release(self.store.declare("reader", SavedProgress("pg84", "main", 7)))

        self.assertEqual(3, self.store.get("reader", ALICE).chapter_max)
        self.assertEqual(7, self.store.get("reader", "pg84").chapter_max)
        self.assertIsNone(self.store.get("someone-else", ALICE))

    def test_restriction_only_lowers_an_existing_matching_book_part(self) -> None:
        self.store.release(self.store.declare("reader", SavedProgress(ALICE, "main", 5)))
        for account, progress in (
            ("reader", SavedProgress(ALICE, "other-part", 2)),
            ("reader", SavedProgress("pg84", "main", 2)),
            ("someone-else", SavedProgress(ALICE, "main", 2)),
            ("reader", SavedProgress(ALICE, "main", 7)),
        ):
            self.store.declare(account, progress)
        self.assertEqual((SavedProgress(ALICE, "main", 5),), self.store.list_for("reader"))
        self.assertEqual((), self.store.list_for("someone-else"))

        self.store.declare("reader", SavedProgress(ALICE, "main", 2))
        self.assertEqual(SavedProgress(ALICE, "main", 2), self.store.get("reader", ALICE))

    def test_a_later_lower_declaration_wins_before_either_reply_releases(self) -> None:
        self.store.release(self.store.declare("reader", SavedProgress(ALICE, "main", 5)))
        older = self.store.declare("reader", SavedProgress(ALICE, "main", 7))
        later = self.store.declare("reader", SavedProgress(ALICE, "main", 2))

        self.assertEqual(2, self.store.get("reader", ALICE).chapter_max)
        self.assertFalse(self.store.release(older))
        self.assertTrue(self.store.release(later))

    def test_an_equal_unreleased_declaration_invalidates_an_older_raise(self) -> None:
        self.store.release(self.store.declare("reader", SavedProgress(ALICE, "main", 5)))
        snapshot = self.store.list_snapshots("reader")[0]
        older = self.store.declare("reader", SavedProgress(ALICE, "main", 7))
        self.store.declare("reader", SavedProgress(ALICE, "main", 5))

        self.assertFalse(self.store.release(older))
        self.assertFalse(self.store.is_current(snapshot))
        self.assertEqual(5, self.store.get("reader", ALICE).chapter_max)

    def test_a_snapshot_expires_when_its_pending_revision_releases_a_different_part(self) -> None:
        self.store.release(self.store.declare("reader", SavedProgress(ALICE, "main", 5)))
        pending = self.store.declare("reader", SavedProgress(ALICE, "other-part", 2))
        snapshot = self.store.snapshot("reader", ALICE)
        self.assertEqual(pending.revision, snapshot.revision)
        self.assertTrue(self.store.is_current(snapshot))

        self.assertTrue(self.store.release(pending))
        self.assertFalse(self.store.is_current(snapshot))

    def test_withdrawal_invalidates_an_unsaved_first_declaration(self) -> None:
        older = self.store.declare("reader", SavedProgress(ALICE, "main", 7))
        self.store.withdraw("reader", ALICE)

        self.assertIsNone(self.store.get("reader", ALICE))
        self.assertFalse(self.store.release(older))
        self.assertGreater(self.store.snapshot("reader", ALICE).revision, older.revision)

    def test_deletion_and_recreation_do_not_make_an_old_token_current(self) -> None:
        self.store.release(self.store.declare("reader", SavedProgress(ALICE, "main", 5)))
        older = self.store.declare("reader", SavedProgress(ALICE, "main", 7))
        self.store.withdraw("reader", ALICE)
        self.store.release(self.store.declare("reader", SavedProgress(ALICE, "main", 5)))

        self.assertFalse(self.store.release(older))
        self.assertEqual(5, self.store.get("reader", ALICE).chapter_max)

    def test_revision_survives_another_process_and_reopened_store(self) -> None:
        older = self.store.declare("reader", SavedProgress(ALICE, "main", 7))
        subprocess.run([
            sys.executable, "-B", "-c",
            "import sys; from pathlib import Path; "
            "from apps.backend.progress_store import ReadingProgressStore; "
            "ReadingProgressStore(Path(sys.argv[1])).withdraw('reader', 'pg11')",
            str(self.path),
        ], check=True, timeout=10)

        reopened = ReadingProgressStore(self.path)
        self.assertFalse(reopened.release(older))
        self.assertIsNone(reopened.get("reader", ALICE))
        self.assertEqual(self.store.snapshot("reader", ALICE), reopened.snapshot("reader", ALICE))

    def test_declaration_revision_is_scoped_to_account_and_work(self) -> None:
        alice = self.store.declare("reader", SavedProgress(ALICE, "main", 5))
        other_account = self.store.declare("other", SavedProgress(ALICE, "main", 7))
        pinocchio = self.store.declare("reader", SavedProgress("pg500", "main", 4))
        self.store.withdraw("reader", "pg84")

        self.assertTrue(self.store.release(alice))
        self.assertTrue(self.store.release(other_account))
        self.assertTrue(self.store.release(pinocchio))

    def test_a_changed_part_invalidates_an_older_token_without_granting_the_new_part(self) -> None:
        self.store.release(self.store.declare("reader", SavedProgress(ALICE, "main", 5)))
        older = self.store.declare("reader", SavedProgress(ALICE, "main", 7))
        later = self.store.declare("reader", SavedProgress(ALICE, "other-part", 2))

        self.assertEqual(SavedProgress(ALICE, "main", 5), self.store.get("reader", ALICE))
        self.assertFalse(self.store.release(older))
        self.assertTrue(self.store.release(later))
        self.assertEqual(SavedProgress(ALICE, "other-part", 2), self.store.get("reader", ALICE))

    def test_failed_restriction_rolls_back_its_revision_and_permission_together(self) -> None:
        self.store.release(self.store.declare("reader", SavedProgress(ALICE, "main", 5)))
        before = self.store.snapshot("reader", ALICE)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.declare("reader", SavedProgress(ALICE, "main", 0))

        self.assertEqual(before, self.store.snapshot("reader", ALICE))

    def test_existing_database_keeps_saved_permissions_when_revisions_are_added(self) -> None:
        path = self.path.with_name("legacy.sqlite3")
        with sqlite3.connect(path) as conn:
            conn.execute(
                "CREATE TABLE reading_progress (account_id TEXT NOT NULL, work_id TEXT NOT NULL,"
                " part_id TEXT NOT NULL, chapter_max INTEGER NOT NULL CHECK (chapter_max >= 1),"
                " updated_at TEXT NOT NULL, PRIMARY KEY (account_id, work_id))"
            )
            conn.execute("INSERT INTO reading_progress VALUES ('reader', 'pg11', 'main', 5, 'legacy')")
        store = ReadingProgressStore(path)

        self.assertEqual(SavedProgress(ALICE, "main", 5), store.get("reader", ALICE))
        self.assertEqual(0, store.snapshot("reader", ALICE).revision)
        declared = store.declare("reader", SavedProgress(ALICE, "main", 2))
        self.assertGreater(declared.revision, 0)
        self.assertTrue(store.release(declared))
        self.assertEqual(2, ReadingProgressStore(path).get("reader", ALICE).chapter_max)


class SavedProgressResolutionTests(unittest.TestCase):
    session_id = "saved-progress-resolution"

    def tearDown(self) -> None:
        sessions.clear(self.session_id)

    def _apply(self, message: str, saved: ConfirmedReading | None):
        request = ChatRequest(session_id=self.session_id, message=message)
        return chat_turn._apply_saved_progress(
            request, chat_turn.resolve_reading_context(request), saved,
        )

    def _resolve(self, message: str, saved: ConfirmedReading | None):
        return self._apply(message, saved)[0]

    def _select_alice(self) -> None:
        sessions.set_book_selection(self.session_id, sessions.BookSelection(
            book_id=ALICE, book_title="Alice's Adventures in Wonderland", source="reader_stated",
        ))

    def test_active_book_uses_saved_chapter(self) -> None:
        sessions.set_book_selection(self.session_id, sessions.BookSelection(
            book_id=ALICE, book_title="Alice's Adventures in Wonderland", source="reader_stated",
        ))
        resolution = self._resolve(RETURNING, _saved(2))

        self.assertEqual("confirmed", resolution.status)
        self.assertEqual(2, resolution.chapter_max)
        self.assertEqual("reader_confirmed", resolution.boundary_source)
        self.assertEqual("saved_progress", resolution.boundary_authorization_basis)

    def test_applied_saved_progress_is_staged_as_the_sessions_progress(self) -> None:
        self._select_alice()
        _, pending = self._apply(RETURNING, _saved(2))

        self.assertIsNotNone(pending)
        self.assertIsNone(pending.expected)
        self.assertEqual((ALICE, "main", 2), (
            pending.declared.work_id, pending.declared.part_id, pending.declared.chapter_max,
        ))

    def test_this_sessions_progress_for_the_book_outranks_saved_progress(self) -> None:
        self._select_alice()
        version = chat_turn.librarian_service.version_for(ALICE)
        for chapter_max in (4, None):
            with self.subTest(chapter_max=chapter_max):
                sessions.set_reading_progress(
                    self.session_id, sessions.ReadingProgress(ALICE, version, "main", chapter_max),
                )
                resolution, pending = self._apply(RETURNING, _saved(2))

                self.assertNotEqual("saved_progress", resolution.boundary_authorization_basis)
                self.assertIsNone(pending)

    def test_unreadable_progress_talk_withholds_saved_progress(self) -> None:
        self._select_alice()
        resolution, pending = self._apply(
            "Wait, I'm not that far in Alice's Adventures in Wonderland.", _saved(9),
        )

        self.assertNotEqual("saved_progress", resolution.boundary_authorization_basis)
        self.assertIsNone(pending)

    def test_saved_progress_never_selects_a_book(self) -> None:
        resolution = self._resolve(
            "I felt out of place at work today.", _saved(2),
        )

        self.assertEqual("unknown", resolution.status)
        self.assertIsNone(resolution.chapter_max)

    def test_another_books_progress_does_not_apply(self) -> None:
        sessions.set_book_selection(self.session_id, sessions.BookSelection(book_id=ALICE))
        resolution = self._resolve(RETURNING, _saved(2, work_id="pg84"))

        self.assertNotEqual("confirmed", resolution.status)

    def test_a_declaration_in_this_message_outranks_saved_progress(self) -> None:
        resolution = self._resolve(DECLARATION, _saved(9))

        self.assertEqual(2, resolution.chapter_max)
        self.assertEqual("explicit_progress", resolution.boundary_authorization_basis)

    def test_saved_chapter_beyond_the_registered_book_is_not_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ReadingProgressStore(Path(directory) / "r.sqlite3")
            store.release(store.declare("reader", SavedProgress(ALICE, "main", 999)))
            store.release(store.declare("reader", SavedProgress("unregistered-work", "main", 1)))
            self.assertEqual({}, chat_turn._saved_readings(store.list_snapshots("reader")))
            store.release(store.declare("reader", SavedProgress(ALICE, "main", 3)))
            self.assertEqual(
                {ALICE: _saved(3)}, chat_turn._saved_readings(store.list_snapshots("reader")),
            )

    def test_only_explicit_chapter_progress_is_recorded(self) -> None:
        declared = chat_turn.resolve_reading_context(
            ChatRequest(session_id=self.session_id, message=DECLARATION)
        )
        self.assertEqual(
            SavedProgress(ALICE, "main", 2), chat_turn._saved_progress_to_record(declared),
        )
        sessions.set_book_selection(self.session_id, sessions.BookSelection(book_id=ALICE))
        restored = self._resolve(RETURNING, _saved(2))
        self.assertIsNone(chat_turn._saved_progress_to_record(restored))


class SavedProgressRoutingTests(unittest.IsolatedAsyncioTestCase):
    session_id = "saved-progress-routing"

    def tearDown(self) -> None:
        sessions.clear(self.session_id)

    async def test_routing_a_named_book_binds_its_saved_chapter(self) -> None:
        tokens = (
            turn_context.set_confirmed_reading(None),
            turn_context.set_saved_readings({ALICE: _saved(2)}),
            turn_context.set_session_id(self.session_id),
        )
        try:
            routed = await routing.route_reader_message(BOOK_QUESTION)
            bound = turn_context.confirmed_reading()
        finally:
            turn_context.reset_session_id(tokens[2])
            turn_context.reset_saved_readings(tokens[1])
            turn_context.reset_confirmed_reading(tokens[0])

        self.assertEqual(("routed", ALICE, 2), (routed.kind, routed.work_id, routed.max_chapter_inclusive))
        self.assertEqual(_saved(2), bound)
        self.assertEqual(ALICE, sessions.book_selection(self.session_id).book_id)


class CaptureDefaultTests(unittest.TestCase):
    def test_stored_policy_outranks_the_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            account = AccountContext("capture-default")
            interactive = MemoryPolicyService(Path(directory), capture_enabled_by_default=True)
            self.assertTrue(interactive.capture_enabled(account))
            self.assertFalse(MemoryPolicyService(Path(directory)).capture_enabled(account))

            interactive.set_capture_enabled(account, False)
            self.assertFalse(interactive.capture_enabled(account))


class ProgressAcrossConversationsTests(unittest.IsolatedAsyncioTestCase):
    sessions_used = ("progress-day-one", "progress-day-two", "progress-other-reader")
    RETRACTION = "Wait, I haven't finished chapter 2 yet."

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.service = MemoryPolicyService(Path(directory.name) / "memories")
        self.store = ReadingProgressStore(Path(directory.name) / "r.sqlite3")
        patcher = patch.object(
            chat_turn, "assess_emotional_boundary",
            return_value=EmotionalBoundaryAssessment(decision="continue_reflection"),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        for session_id in self.sessions_used:
            sessions.clear(session_id)

    async def _turn(self, session_id: str, message: str, account: str):
        return await chat_turn.run_chat_turn(
            ChatRequest(session_id=session_id, message=message),
            self.service, AccountContext(account), progress_store=self.store,
        )

    async def test_a_new_conversation_keeps_the_readers_chapter(self) -> None:
        ROUTE_RESULTS.clear()
        with muse_chat_agent.override(model=FunctionModel(_muse)):
            with provenance_agent.override(model=FunctionModel(_provenance)):
                first = await self._turn("progress-day-one", DECLARATION, "reader")
                second = await self._turn("progress-day-two", BOOK_QUESTION, "reader")

        self.assertEqual("muse_candidate", first.inspection.release.release_source)
        self.assertEqual(SavedProgress(ALICE, "main", 2), self.store.get("reader", ALICE))
        self.assertEqual("muse_candidate", second.inspection.release.release_source)
        self.assertEqual(
            [("routed", ALICE, 2)],
            [(r["kind"], r["work_id"], r["max_chapter_inclusive"]) for r in ROUTE_RESULTS],
        )
        self.assertEqual(ALICE, sessions.book_selection("progress-day-two").book_id)
        alice = {"work_id": ALICE, "title": "Alice's Adventures in Wonderland", "part_id": "main", "chapter_max": 2}
        # Inspect shows both stores. Routing grants the saved chapter for one turn
        # without writing the new conversation's slot.
        self.assertEqual({"session": alice, "saved": [alice]}, first.inspection.reading_state.model_dump())
        self.assertEqual({"session": None, "saved": [alice]}, second.inspection.reading_state.model_dump())

    async def test_a_withdrawn_chapter_is_not_restored_in_a_new_conversation(self) -> None:
        ROUTE_RESULTS.clear()
        with muse_chat_agent.override(model=FunctionModel(_muse)):
            with provenance_agent.override(model=FunctionModel(_provenance)):
                await self._turn("progress-day-one", DECLARATION, "reader")
                await self._turn("progress-day-one", self.RETRACTION, "reader")
                ROUTE_RESULTS.clear()
                second = await self._turn("progress-day-two", BOOK_QUESTION, "reader")

        self.assertIsNone(self.store.get("reader", ALICE))
        self.assertEqual([], second.inspection.reading_state.model_dump()["saved"])
        self.assertFalse([r for r in ROUTE_RESULTS if r.get("max_chapter_inclusive") is not None])

    async def test_another_account_does_not_inherit_progress(self) -> None:
        self.store.release(self.store.declare("reader", SavedProgress(ALICE, "main", 2)))
        tokens = (
            turn_context.set_confirmed_reading(None),
            turn_context.set_saved_readings(
                chat_turn._saved_readings(self.store.list_snapshots("other")),
            ),
        )
        try:
            self.assertIsNone(turn_context.saved_reading(ALICE))
        finally:
            turn_context.reset_saved_readings(tokens[1])
            turn_context.reset_confirmed_reading(tokens[0])

    async def test_trusted_connection_setup_does_not_mutate_account_or_session_progress(self) -> None:
        self.store.release(self.store.declare("reader", SavedProgress(ALICE, "main", 5)))
        before = self.store.snapshot("reader", ALICE)
        scopes = tuple(ReleaseScope(
            work_id=work_id, book_version_id=chat_turn.librarian_service.version_for(work_id), chapter_max=chapter,
        ) for work_id, chapter in ((ALICE, 2), ("pg500", 4)))
        with patch.object(chat_turn, "reflection_reply", AsyncMock(return_value=ReflectionRelease(
            reply="A reflection.", release_source="muse_candidate",
        ))):
            await chat_turn.run_chat_turn(
                ChatRequest(
                    session_id=self.sessions_used[0],
                    message="Relate chapter 2 of Alice's Adventures in Wonderland to my memory.",
                ), self.service, AccountContext("reader"), progress_store=self.store,
                connection_book_scopes=scopes,
            )

        self.assertEqual(before, self.store.snapshot("reader", ALICE))
        self.assertIsNone(sessions.reading_progress_for(self.sessions_used[0], ALICE))

    async def test_ordinary_scene_reflections_without_progress_do_not_advance_revision(self) -> None:
        for message in (
            "The Mad Tea-Party in Alice's Adventures in Wonderland makes me think about belonging.",
            "The pool of tears in Alice's Adventures in Wonderland reminds me of feeling overwhelmed.",
            "The rabbit hole in Alice's Adventures in Wonderland reminds me of starting something new.",
        ):
            with self.subTest(message=message), patch.object(
                chat_turn, "reflection_reply", AsyncMock(return_value=ReflectionRelease(
                    reply="A reflection.", release_source="muse_candidate",
                )),
            ):
                before = self.store.snapshot("reader", ALICE)
                await self._turn(self.sessions_used[0], message, "reader")
                self.assertEqual(before, self.store.snapshot("reader", ALICE))
                self.assertIsNone(sessions.reading_progress_for(self.sessions_used[0], ALICE))
                sessions.clear(self.sessions_used[0])


if __name__ == "__main__":
    unittest.main()


class ShowMemoriesTests(unittest.TestCase):
    def test_resolves_an_inspect_memory_id_to_its_text(self) -> None:
        import contextlib
        import io
        import sys

        from apps.backend import show_memories
        from src.linger.services.memory import AutomaticMemoryCandidate

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = MemoryPolicyService(root / "memories", capture_enabled_by_default=True)
            saved = service.save_automatic(AccountContext("user:dev-check"), AutomaticMemoryCandidate(
                text="I reread letters when I feel far from home.",
                source_event_id="fixture-letters",
                review_allows_capture=True,
                contains_sensitive_content=False,
            )).record
            output = io.StringIO()
            with (
                patch.object(show_memories, "REPO_ROOT", root),
                patch.object(sys, "argv", ["show_memories", "dev-check", saved.memory_id, "mem_missing"]),
                contextlib.redirect_stdout(output),
            ):
                show_memories.main()

        self.assertIn(saved.memory_id, output.getvalue())
        self.assertIn("I reread letters when I feel far from home.", output.getvalue())
        self.assertIn("Not found for dev-check: mem_missing", output.getvalue())


class CrossBookComparisonTests(unittest.IsolatedAsyncioTestCase):
    """A connection request spans every book the reader confirmed, each at its own ceiling."""

    session_id = "cross-book-comparison"

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.service = MemoryPolicyService(Path(directory.name) / "memories")
        self.store = ReadingProgressStore(Path(directory.name) / "r.sqlite3")
        for patcher in (
            patch.object(chat_turn, "assess_emotional_boundary",
                         return_value=EmotionalBoundaryAssessment(decision="continue_reflection")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        sessions.clear(self.session_id)

    async def _turn(self, message: str, needs: TurnNeeds):
        async def triage(*_args, **_kwargs):
            return needs

        with patch.object(chat_turn, "triage_turn", triage), \
                muse_chat_agent.override(model=FunctionModel(_muse)), \
                provenance_agent.override(model=FunctionModel(_provenance)):
            return await chat_turn.run_chat_turn(
                ChatRequest(session_id=self.session_id, message=message),
                self.service, AccountContext("reader"), progress_store=self.store,
            )

    async def test_connection_request_compares_every_saved_book_at_its_own_ceiling(self) -> None:
        self.store.release(self.store.declare("reader", SavedProgress(ALICE, "main", 5)))
        self.store.release(self.store.declare("reader", SavedProgress("pg500", "main", 4)))

        response = await self._turn(
            "Alice and Pinocchio both keep being told who they should be. Is there a connection?",
            TurnNeeds(book_content="yes", memory="source_comparison"),
        )

        muse_turn = response.inspection.muse_turn
        self.assertIsNone(muse_turn["reading_context"])
        self.assertEqual(
            {(ALICE, 5), ("pg500", 4)},
            {(scope["work_id"], scope["chapter_max"]) for scope in muse_turn["connection_book_scopes"]},
        )
        self.assertEqual("find_connection", response.inspection.tool_exposure["pinned_intent"])
        self.assertEqual("muse_candidate", response.inspection.release.release_source)

    async def test_a_declaration_this_turn_replaces_that_books_saved_ceiling(self) -> None:
        self.store.release(self.store.declare("reader", SavedProgress(ALICE, "main", 2)))
        self.store.release(self.store.declare("reader", SavedProgress("pg500", "main", 4)))

        response = await self._turn(
            "I've finished chapter 5 of Alice's Adventures in Wonderland. Does it connect to Pinocchio?",
            TurnNeeds(book_content="yes", memory="source_comparison"),
        )

        scopes = {scope["work_id"]: scope["chapter_max"] for scope in response.inspection.muse_turn["connection_book_scopes"]}
        self.assertEqual({ALICE: 5, "pg500": 4}, scopes)
        self.assertEqual(5, self.store.get("reader", ALICE).chapter_max)

    async def test_ordinary_questions_and_single_books_keep_the_focused_path(self) -> None:
        self.store.release(self.store.declare("reader", SavedProgress(ALICE, "main", 5)))
        single = await self._turn(
            "Does this connect to anything?", TurnNeeds(book_content="yes", memory="source_comparison"),
        )
        self.assertEqual([], single.inspection.muse_turn["connection_book_scopes"])

        self.store.release(self.store.declare("reader", SavedProgress("pg500", "main", 4)))
        sessions.clear(self.session_id)
        ordinary = await self._turn(
            "I've finished chapter 5 of Alice's Adventures in Wonderland.",
            TurnNeeds(book_content="no", memory="none"),
        )
        self.assertEqual([], ordinary.inspection.muse_turn["connection_book_scopes"])
        self.assertEqual(5, ordinary.inspection.muse_turn["reading_context"]["chapter_max"])
