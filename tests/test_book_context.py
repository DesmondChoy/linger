import unittest

from apps.backend import sessions
from apps.backend.main import update_book_context
from apps.backend.schemas import ChatRequest


class BookContextTests(unittest.TestCase):
    def tearDown(self) -> None:
        sessions.clear("context-test")

    def test_context_requires_an_explicit_chapter(self) -> None:
        context = update_book_context(
            ChatRequest(session_id="context-test", turn_id="turn-1", message="I am reading The Left Hand of Darkness")
        )
        self.assertIsNone(context)

    def test_book_and_chapter_without_completion_do_not_grant_the_whole_chapter(self) -> None:
        first = update_book_context(
            ChatRequest(
                session_id="context-test",
                turn_id="turn-1",
                message="I am reading The Left Hand of Darkness, chapter 5.",
            )
        )
        next_turn = update_book_context(
            ChatRequest(session_id="context-test", turn_id="turn-2", message="Why does Estraven feel distant?")
        )
        self.assertIsNone(first)
        self.assertIsNone(next_turn)
        selection = sessions.book_selection("context-test")
        assert selection is not None
        self.assertEqual(selection.book_id, "the-left-hand-of-darkness")

    def test_existing_context_can_be_advanced_without_repeating_the_title(self) -> None:
        update_book_context(
            ChatRequest(session_id="context-test", turn_id="turn-1", message="I'm reading Dune and I've finished Chapter 2.")
        )
        context = update_book_context(
            ChatRequest(session_id="context-test", turn_id="turn-2", message="I've now finished Chapter 3.")
        )
        assert context is not None
        self.assertEqual(context.book_title, "Dune")
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
        context = update_book_context(
            ChatRequest(session_id="context-test", turn_id="turn-1", message="I'm done with the chapter")
        )
        assert context is not None
        self.assertEqual(context.book_id, "alice-adventures-in-wonderland")
        self.assertEqual(context.chapter_max, 5)

    def test_candidate_does_not_set_progress_without_book_confirmation(self) -> None:
        sessions.set_reading_candidate(
            "context-test",
            sessions.ReadingCandidate(book_id="alice-adventures-in-wonderland", chapter=5),
        )
        context = update_book_context(
            ChatRequest(session_id="context-test", turn_id="turn-1", message="I'm done with the chapter")
        )
        self.assertIsNone(context)


if __name__ == "__main__":
    unittest.main()
