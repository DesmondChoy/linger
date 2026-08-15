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
    from apps.backend.main import _inspection_for, resolve_reading_context
    from apps.backend.schemas import ChatRequest


class BookContextTests(unittest.TestCase):
    def tearDown(self) -> None:
        sessions.clear("context-test")

    def test_context_requires_an_explicit_chapter(self) -> None:
        context = resolve_reading_context(
            ChatRequest(session_id="context-test", turn_id="turn-1", message="I am reading The Left Hand of Darkness")
        )
        self.assertIsNone(context.chapter_max)

    def test_book_and_chapter_without_completion_do_not_grant_the_whole_chapter(self) -> None:
        first = resolve_reading_context(
            ChatRequest(
                session_id="context-test",
                turn_id="turn-1",
                message="I am reading The Left Hand of Darkness, chapter 5.",
            )
        )
        next_turn = resolve_reading_context(
            ChatRequest(session_id="context-test", turn_id="turn-2", message="Why does Estraven feel distant?")
        )
        self.assertIsNone(first.chapter_max)
        self.assertIsNone(next_turn.chapter_max)
        selection = sessions.book_selection("context-test")
        assert selection is not None
        self.assertEqual(selection.book_id, "the-left-hand-of-darkness")

    def test_existing_context_can_be_advanced_without_repeating_the_title(self) -> None:
        first = resolve_reading_context(
            ChatRequest(session_id="context-test", turn_id="turn-1", message="I'm reading Dune and I've finished Chapter 2.")
        )
        context = resolve_reading_context(
            ChatRequest(session_id="context-test", turn_id="turn-2", message="I've now finished Chapter 3.")
        )
        self.assertEqual(first.chapter_max, 2)
        self.assertEqual(context.work_title, "Dune")
        self.assertEqual(context.chapter_max, 3)

    def test_completion_can_confirm_the_previous_scene_candidate(self) -> None:
        sessions.set_reading_candidate(
            "context-test",
            sessions.ReadingCandidate(
                book_id="alice-adventures-in-wonderland",
                book_title="Alice's Adventures in Wonderland",
                chapter=5,
            ),
        )
        sessions.set_book_selection(
            "context-test",
            sessions.BookSelection(
                book_id="alice-adventures-in-wonderland",
                book_title="Alice's Adventures in Wonderland",
            ),
        )
        context = resolve_reading_context(
            ChatRequest(session_id="context-test", turn_id="turn-1", message="I'm done with the chapter")
        )
        self.assertEqual(context.work_id, "alice-adventures-in-wonderland")
        self.assertEqual(context.chapter_max, 5)

    def test_candidate_does_not_set_progress_without_book_confirmation(self) -> None:
        sessions.set_reading_candidate(
            "context-test",
            sessions.ReadingCandidate(book_id="alice-adventures-in-wonderland", chapter=5),
        )
        context = resolve_reading_context(
            ChatRequest(session_id="context-test", turn_id="turn-1", message="I'm done with the chapter")
        )
        self.assertIsNone(context.chapter_max)

    def test_negated_completion_keeps_candidate_unconfirmed(self) -> None:
        sessions.set_reading_candidate(
            "context-test",
            sessions.ReadingCandidate(book_id="alice-wonderland", chapter=5),
        )
        sessions.set_book_selection(
            "context-test",
            sessions.BookSelection(book_id="alice-wonderland"),
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
                message="I am reading Animal Farm and I have finished Chapter 3.",
            )
        )
        next_turn = resolve_reading_context(
            ChatRequest(session_id="context-test", message="Why does power feel unstable?")
        )

        self.assertEqual(first.chapter_max, 3)
        self.assertEqual(next_turn.work_id, "animal-farm")
        self.assertIsNone(next_turn.chapter_max)

    def test_new_scene_candidate_replaces_stale_book_assumption(self) -> None:
        resolve_reading_context(
            ChatRequest(
                session_id="context-test",
                message="I am reading Animal Farm and I have finished Chapter 3.",
            )
        )
        inspection, _, review_context = _inspection_for(
            ChatRequest(session_id="context-test", message="Why does the Caterpillar ask who Alice is?")
        )

        self.assertEqual("inferred", inspection.context_resolution["status"])
        self.assertEqual("alice-adventures-in-wonderland", inspection.context_resolution["work_id"])
        self.assertIsNone(inspection.muse_turn["reading_context"])
        self.assertFalse(inspection.muse_turn["policy"]["allow_retrieval"])
        self.assertIsNone(review_context["reading_context"])


if __name__ == "__main__":
    unittest.main()
