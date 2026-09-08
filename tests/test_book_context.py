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
    from apps.backend import sessions
    from apps.backend.chat_turn import (
        prepare_reflection_turn,
        resolve_reading_context,
    )
    from apps.backend.schemas import ChatRequest


class BookContextTests(unittest.TestCase):
    def tearDown(self) -> None:
        sessions.clear("context-test")

    def test_context_requires_an_explicit_chapter(self) -> None:
        context = resolve_reading_context(
            ChatRequest(session_id="context-test", turn_id="turn-1", message="I am reading The Left Hand of Darkness")
        )
        self.assertIsNone(context.chapter_max)

    def test_unknown_book_does_not_invent_identity_or_reuse_previous_progress(self) -> None:
        sessions.set_book_selection(
            "context-test", sessions.BookSelection(book_id="pg11")
        )
        sessions.set_pending_clarification(
            "context-test",
            sessions.PendingClarification(book_id="pg11", reason_code="insufficient_context"),
        )
        context = resolve_reading_context(ChatRequest(
            session_id="context-test",
            message="I'm reading Winter Wonderland and I've finished Chapter 3.",
        ))
        self.assertIsNone(context.work_id)
        self.assertIsNone(context.chapter_max)
        self.assertIsNone(sessions.book_selection("context-test"))
        follow_up = resolve_reading_context(ChatRequest(
            session_id="context-test", message="Chapter 2"
        ))
        self.assertIsNone(follow_up.work_id)
        self.assertIsNone(follow_up.chapter_max)

    def test_pending_question_for_an_unavailable_book_cannot_grant_progress(self) -> None:
        sessions.set_pending_clarification(
            "context-test",
            sessions.PendingClarification(book_id="unavailable", reason_code="insufficient_context"),
        )
        context = resolve_reading_context(ChatRequest(
            session_id="context-test", message="Chapter 2"
        ))
        self.assertIsNone(context.chapter_max)
        self.assertIsNone(sessions.pending_clarification("context-test"))

    def test_full_title_answer_selects_identity_without_confirming_progress(self) -> None:
        context = resolve_reading_context(ChatRequest(
            session_id="context-test", message="Alice's Adventures in Wonderland."
        ))
        self.assertEqual("pg11", context.work_id)
        self.assertIsNone(context.chapter_max)

    def test_candidate_for_an_unavailable_book_cannot_be_confirmed(self) -> None:
        sessions.set_reading_candidate(
            "context-test", sessions.ReadingCandidate(book_id="unavailable", chapter=5)
        )
        context = resolve_reading_context(ChatRequest(session_id="context-test", message="Yes."))
        self.assertIsNone(context.work_id)
        self.assertIsNone(context.chapter_max)
        self.assertIsNone(sessions.reading_candidate("context-test"))

    def test_read_through_is_progress_not_a_new_book_title(self) -> None:
        sessions.set_book_selection("context-test", sessions.BookSelection(book_id="pg11"))
        context = resolve_reading_context(ChatRequest(
            session_id="context-test", message="I've read through Chapter 3."
        ))
        self.assertEqual("pg11", context.work_id)
        self.assertEqual(3, context.chapter_max)

    def test_registered_non_alice_book_uses_stable_identity(self) -> None:
        from dataclasses import replace
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from corpus_fixtures import fake_registration
        from apps.backend import chat_turn

        with TemporaryDirectory() as directory:
            registration = replace(fake_registration(Path(directory), work_id="pg999", catalog={
                "title": "The Orchard Notebook",
                "chapters": [{"chapter_number": 1}, {"chapter_number": 2}],
            }), aliases=("orchard notebook",))
            with (
                patch("src.linger.corpus.registry.CORPORA", {"pg999": registration}),
                patch.object(chat_turn.settings, "allowed_book_version_ids", (registration.book.book_version_id,)),
            ):
                context = resolve_reading_context(ChatRequest(
                    session_id="context-test",
                    message="I'm reading Orchard Notebook and I've finished Chapter 2.",
                ))
            self.assertEqual("pg999", context.work_id)
            self.assertEqual(registration.book.book_version_id, context.book_version_id)
            self.assertEqual(2, context.chapter_max)

    def test_title_after_chapter_does_not_inherit_the_previous_book(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from corpus_fixtures import fake_registration
        from apps.backend import chat_turn
        from src.linger.corpus import registry

        with TemporaryDirectory() as directory:
            registration = fake_registration(Path(directory), work_id="pg999", catalog={
                "title": "The Orchard Notebook",
                "chapters": [{"chapter_number": 1}, {"chapter_number": 2}],
            })
            with (
                patch.object(registry, "CORPORA", {**registry.CORPORA, "pg999": registration}),
                patch.object(chat_turn.settings, "allowed_book_version_ids", (
                    *chat_turn.settings.allowed_book_version_ids, registration.book.book_version_id,
                )),
            ):
                for title, expected_work in (
                    ("The Orchard Notebook", "pg999"),
                    ("Winter Wonderland", None),
                ):
                    with self.subTest(title=title):
                        sessions.set_book_selection(
                            "context-test", sessions.BookSelection(book_id="pg11")
                        )
                        context = resolve_reading_context(ChatRequest(
                            session_id="context-test",
                            message=f"I've finished Chapter 2 of {title}.",
                        ))
                        self.assertEqual(expected_work, context.work_id)
                        self.assertEqual(2 if expected_work else None, context.chapter_max)

    def test_cold_start_explicit_progress_needs_no_memories(self) -> None:
        context = resolve_reading_context(
            ChatRequest(
                session_id="context-test",
                message="I'm reading Alice's Adventures in Wonderland, and I've finished Chapter 6.",
            )
        )

        self.assertEqual("confirmed", context.status)
        self.assertEqual(6, context.chapter_max)
        self.assertEqual("reader_confirmed", context.boundary_source)
        self.assertEqual("explicit_progress", context.boundary_authorization_basis)

    def test_common_catalog_words_do_not_select_alice(self) -> None:
        for index, message in enumerate(
            (
                "My friend Alice is stressed about work.",
                "What should I cook for dinner?",
                "A mouse ran through the kitchen.",
            ),
            start=1,
        ):
            with self.subTest(message=message):
                context = resolve_reading_context(
                    ChatRequest(
                        session_id=f"context-common-{index}",
                        message=message,
                    )
                )
                self.assertEqual("unknown", context.status)
                self.assertIsNone(context.work_id)
                self.assertIsNone(context.clarification_question)
                sessions.clear(f"context-common-{index}")

    def test_book_and_chapter_without_completion_do_not_grant_the_whole_chapter(self) -> None:
        first = resolve_reading_context(
            ChatRequest(
                session_id="context-test",
                turn_id="turn-1",
                message="I am reading Alice in Wonderland, chapter 5.",
            )
        )
        next_turn = resolve_reading_context(
            ChatRequest(session_id="context-test", turn_id="turn-2", message="Why does Alice feel distant?")
        )
        self.assertIsNone(first.chapter_max)
        self.assertIsNone(next_turn.chapter_max)
        selection = sessions.book_selection("context-test")
        assert selection is not None
        self.assertEqual(selection.book_id, "pg11")

    def test_existing_context_can_be_advanced_without_repeating_the_title(self) -> None:
        first = resolve_reading_context(
            ChatRequest(session_id="context-test", turn_id="turn-1", message="I'm reading Alice in Wonderland and I've finished Chapter 2.")
        )
        context = resolve_reading_context(
            ChatRequest(session_id="context-test", turn_id="turn-2", message="I've now finished Chapter 3.")
        )
        self.assertEqual(first.chapter_max, 2)
        self.assertEqual("explicit_progress", first.boundary_authorization_basis)
        self.assertEqual(context.work_title, "Alice's Adventures in Wonderland")
        self.assertEqual(context.chapter_max, 3)
        self.assertEqual("explicit_progress", context.boundary_authorization_basis)

    def test_active_book_preserves_an_indirect_follow_up(self) -> None:
        sessions.set_book_selection(
            "context-test",
            sessions.BookSelection(
                book_id="pg11",
                book_title="Alice's Adventures in Wonderland",
            ),
        )

        context = resolve_reading_context(
            ChatRequest(session_id="context-test", message="Why did she do that?")
        )

        self.assertEqual("inferred", context.status)
        self.assertEqual("pg11", context.work_id)
        self.assertIsNone(context.chapter_max)

    def test_completion_can_confirm_the_previous_scene_candidate(self) -> None:
        sessions.set_reading_candidate(
            "context-test",
            sessions.ReadingCandidate(
                book_id="pg11",
                book_title="Alice's Adventures in Wonderland",
                chapter=5,
            ),
        )
        sessions.set_book_selection(
            "context-test",
            sessions.BookSelection(
                book_id="pg11",
                book_title="Alice's Adventures in Wonderland",
            ),
        )
        context = resolve_reading_context(
            ChatRequest(session_id="context-test", turn_id="turn-1", message="I'm done with the chapter")
        )
        self.assertEqual(context.work_id, "pg11")
        self.assertEqual(context.chapter_max, 5)

    def test_candidate_does_not_set_progress_without_book_confirmation(self) -> None:
        sessions.set_reading_candidate(
            "context-test",
            sessions.ReadingCandidate(book_id="pg11", chapter=5),
        )
        context = resolve_reading_context(
            ChatRequest(session_id="context-test", turn_id="turn-1", message="I'm done with the chapter")
        )
        self.assertIsNone(context.chapter_max)

    def test_negated_completion_keeps_candidate_unconfirmed(self) -> None:
        sessions.set_reading_candidate(
            "context-test",
            sessions.ReadingCandidate(book_id="pg11", chapter=5),
        )
        sessions.set_book_selection(
            "context-test",
            sessions.BookSelection(book_id="pg11"),
        )

        context = resolve_reading_context(
            ChatRequest(session_id="context-test", message="I'm not finished with the chapter.")
        )

        self.assertIsNone(context.chapter_max)
        self.assertIsNotNone(sessions.reading_candidate("context-test"))

    def test_negated_explicit_chapter_does_not_set_progress(self) -> None:
        context = resolve_reading_context(
            ChatRequest(
                session_id="context-test",
                message="I'm reading Animal Farm and haven't finished Chapter 3.",
            )
        )

        self.assertIsNone(context.chapter_max)

    def test_book_name_or_negated_affirmation_does_not_confirm_candidate_progress(self) -> None:
        for message in (
            "Alice in Wonderland.",
            "I'm still reading Alice in Wonderland.",
            "Yes, but I haven't finished the chapter.",
        ):
            with self.subTest(message=message):
                sessions.set_reading_candidate(
                    "context-test", sessions.ReadingCandidate(book_id="pg11", chapter=5)
                )
                sessions.set_book_selection(
                    "context-test", sessions.BookSelection(book_id="pg11")
                )
                context = resolve_reading_context(
                    ChatRequest(session_id="context-test", message=message)
                )
                self.assertIsNone(context.chapter_max)

    def test_affirmation_confirms_a_presented_chapter_candidate(self) -> None:
        sessions.set_reading_candidate(
            "context-test", sessions.ReadingCandidate(book_id="pg11", chapter=5)
        )
        sessions.set_book_selection(
            "context-test", sessions.BookSelection(book_id="pg11")
        )
        context = resolve_reading_context(
            ChatRequest(session_id="context-test", message="Yes.")
        )
        self.assertEqual(5, context.chapter_max)

    def test_non_reader_completion_language_does_not_set_progress(self) -> None:
        sessions.set_book_selection(
            "context-test",
            sessions.BookSelection(book_id="animal-farm", book_title="Animal Farm"),
        )

        context = resolve_reading_context(
            ChatRequest(session_id="context-test", message="The argument is finished in Chapter 4.")
        )

        self.assertIsNone(context.chapter_max)

    def test_previous_boundary_is_not_reused_for_a_later_request(self) -> None:
        first = resolve_reading_context(
            ChatRequest(
                session_id="context-test",
                message="I am reading Alice in Wonderland and I have finished Chapter 3.",
            )
        )
        next_turn = resolve_reading_context(
            ChatRequest(session_id="context-test", message="Why does power feel unstable?")
        )

        self.assertEqual(first.chapter_max, 3)
        self.assertEqual(next_turn.work_id, "pg11")
        self.assertIsNone(next_turn.chapter_max)

    def test_a_new_catalog_cue_does_not_override_the_active_book_pre_muse(self) -> None:
        # Librarian routing no longer runs pre-Muse: a later message about a
        # different book's characters does not override the session's active
        # selection here. Whether Muse routes to the new book instead is its
        # own tool decision, covered by tests/test_librarian_routing.py.
        resolve_reading_context(
            ChatRequest(
                session_id="context-test",
                message="I am reading Alice in Wonderland and I have finished Chapter 3.",
            )
        )
        inspection, _, review_context = prepare_reflection_turn(
            ChatRequest(
                session_id="context-test",
                message="Why does Jay Gatsby keep waiting?",
            ),
            allow_memory_capture=False,
        )

        self.assertEqual("inferred", inspection.context_resolution["status"])
        self.assertEqual("pg11", inspection.context_resolution["work_id"])
        self.assertIsNone(inspection.muse_turn["reading_context"])
        self.assertFalse(inspection.muse_turn["policy"]["allow_retrieval"])
        self.assertFalse(inspection.muse_turn["policy"]["allow_connection"])
        self.assertIsNone(review_context["reading_context"])

    def test_reflection_without_a_source_does_not_grant_connection_search(self) -> None:
        inspection, _, review_context = prepare_reflection_turn(
            ChatRequest(
                session_id="context-test",
                message=(
                    "I rushed to fill the silence again today. Does that connect "
                    "to anything I have noticed before?"
                ),
            ),
            allow_memory_capture=False,
        )

        self.assertIsNone(inspection.muse_turn["reading_context"])
        self.assertFalse(inspection.muse_turn["policy"]["allow_retrieval"])
        self.assertFalse(inspection.muse_turn["policy"]["allow_connection"])
        self.assertEqual("complete", inspection.traces[0]["status"])
        self.assertIsNone(review_context["reading_context"])

    def test_bare_chapter_answers_a_pending_clarification(self) -> None:
        for message in ("chapter 2", "Chapter 2."):
            with self.subTest(message=message):
                sessions.set_book_selection(
                    "context-test",
                    sessions.BookSelection(book_id="pg11", book_title="Alice's Adventures in Wonderland"),
                )
                sessions.set_pending_clarification(
                    "context-test",
                    sessions.PendingClarification(
                        book_id="pg11",
                        book_title="Alice's Adventures in Wonderland",
                        reason_code="insufficient_context",
                    ),
                )
                context = resolve_reading_context(
                    ChatRequest(session_id="context-test", turn_id="turn-1", message=message)
                )
                self.assertEqual("confirmed", context.status)
                self.assertEqual("pg11", context.work_id)
                self.assertEqual(2, context.chapter_max)
                self.assertEqual("reader_confirmed", context.boundary_source)
                self.assertEqual("explicit_progress", context.boundary_authorization_basis)
                self.assertIsNone(sessions.pending_clarification("context-test"))
                sessions.clear("context-test")

    def test_bare_chapter_without_a_pending_clarification_stays_inferred(self) -> None:
        sessions.set_book_selection(
            "context-test",
            sessions.BookSelection(book_id="pg11", book_title="Alice's Adventures in Wonderland"),
        )
        context = resolve_reading_context(
            ChatRequest(session_id="context-test", turn_id="turn-1", message="chapter 2")
        )
        self.assertEqual("inferred", context.status)
        self.assertIsNone(context.chapter_max)

    def test_non_answer_chapter_mentions_keep_the_clarification_pending(self) -> None:
        for message in (
            "I'm still in chapter 2",
            "I'm on chapter 3",
            "I'm reading chapter 3",
            "I just started chapter 4",
            "maybe chapter 20?",
        ):
            with self.subTest(message=message):
                sessions.set_book_selection(
                    "context-test",
                    sessions.BookSelection(book_id="pg11", book_title="Alice's Adventures in Wonderland"),
                )
                sessions.set_pending_clarification(
                    "context-test",
                    sessions.PendingClarification(
                        book_id="pg11",
                        book_title="Alice's Adventures in Wonderland",
                        reason_code="insufficient_context",
                    ),
                )
                context = resolve_reading_context(
                    ChatRequest(session_id="context-test", turn_id="turn-1", message=message)
                )
                self.assertEqual("inferred", context.status)
                self.assertIsNone(context.chapter_max)
                self.assertIsNotNone(sessions.pending_clarification("context-test"))
                sessions.clear("context-test")

    def test_a_chapter_free_message_keeps_the_clarification_pending(self) -> None:
        sessions.set_book_selection(
            "context-test",
            sessions.BookSelection(book_id="pg11", book_title="Alice's Adventures in Wonderland"),
        )
        sessions.set_pending_clarification(
            "context-test",
            sessions.PendingClarification(
                book_id="pg11",
                book_title="Alice's Adventures in Wonderland",
                reason_code="insufficient_context",
            ),
        )
        context = resolve_reading_context(
            ChatRequest(session_id="context-test", turn_id="turn-1", message="what do you mean?")
        )
        self.assertEqual("inferred", context.status)
        self.assertIsNone(context.chapter_max)
        self.assertIsNotNone(sessions.pending_clarification("context-test"))

    def test_pending_clarification_for_a_different_book_is_not_consumed(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from corpus_fixtures import fake_registration
        from apps.backend import chat_turn
        from src.linger.corpus import registry

        with TemporaryDirectory() as directory:
            other = fake_registration(Path(directory), work_id="animal-farm", catalog={
                "title": "Animal Farm", "chapters": [{"chapter_number": 1}],
            })
            with (
                patch.object(registry, "CORPORA", {**registry.CORPORA, "animal-farm": other}),
                patch.object(chat_turn.settings, "allowed_book_version_ids", (
                    *chat_turn.settings.allowed_book_version_ids, other.book.book_version_id,
                )),
            ):
                sessions.set_book_selection(
                    "context-test",
                    sessions.BookSelection(book_id="animal-farm", book_title="Animal Farm"),
                )
                sessions.set_pending_clarification(
                    "context-test",
                    sessions.PendingClarification(
                        book_id="pg11",
                        book_title="Alice's Adventures in Wonderland",
                        reason_code="insufficient_context",
                    ),
                )
                context = resolve_reading_context(
                    ChatRequest(session_id="context-test", turn_id="turn-1", message="chapter 2")
                )
        self.assertEqual("inferred", context.status)
        self.assertEqual("animal-farm", context.work_id)
        self.assertIsNone(context.chapter_max)
        self.assertIsNotNone(sessions.pending_clarification("context-test"))

    def test_completed_chapter_confirmation_clears_a_pending_clarification(self) -> None:
        sessions.set_book_selection(
            "context-test",
            sessions.BookSelection(book_id="pg11", book_title="Alice's Adventures in Wonderland"),
        )
        sessions.set_pending_clarification(
            "context-test",
            sessions.PendingClarification(
                book_id="pg11",
                book_title="Alice's Adventures in Wonderland",
                reason_code="insufficient_context",
            ),
        )
        context = resolve_reading_context(
            ChatRequest(session_id="context-test", turn_id="turn-1", message="I've finished chapter 2")
        )
        self.assertEqual("confirmed", context.status)
        self.assertIsNone(sessions.pending_clarification("context-test"))

    def test_candidate_completion_clears_a_pending_clarification(self) -> None:
        sessions.set_reading_candidate(
            "context-test",
            sessions.ReadingCandidate(
                book_id="pg11",
                book_title="Alice's Adventures in Wonderland",
                chapter=5,
            ),
        )
        sessions.set_book_selection(
            "context-test",
            sessions.BookSelection(book_id="pg11", book_title="Alice's Adventures in Wonderland"),
        )
        sessions.set_pending_clarification(
            "context-test",
            sessions.PendingClarification(
                book_id="pg11",
                book_title="Alice's Adventures in Wonderland",
                reason_code="insufficient_context",
            ),
        )
        context = resolve_reading_context(
            ChatRequest(session_id="context-test", turn_id="turn-1", message="I'm done with the chapter")
        )
        self.assertEqual("confirmed", context.status)
        self.assertIsNone(sessions.pending_clarification("context-test"))

    def test_pending_clarification_answer_overrides_a_stale_candidate(self) -> None:
        sessions.set_book_selection(
            "context-test",
            sessions.BookSelection(book_id="pg11", book_title="Alice's Adventures in Wonderland"),
        )
        sessions.set_reading_candidate(
            "context-test",
            sessions.ReadingCandidate(book_id="pg11", book_title="Alice's Adventures in Wonderland", chapter=5),
        )
        sessions.set_pending_clarification(
            "context-test",
            sessions.PendingClarification(
                book_id="pg11",
                book_title="Alice's Adventures in Wonderland",
                reason_code="low_confidence",
            ),
        )
        context = resolve_reading_context(
            ChatRequest(session_id="context-test", turn_id="turn-1", message="Chapter 2")
        )
        self.assertEqual("confirmed", context.status)
        self.assertEqual(2, context.chapter_max)
        self.assertIsNone(sessions.reading_candidate("context-test"))
        self.assertIsNone(sessions.pending_clarification("context-test"))


if __name__ == "__main__":
    unittest.main()
