"""Exercise shipped book activation through Chat and canonical retrieval."""

import asyncio
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from apps.backend.config import Settings
from apps.backend.contracts import BookScope, LibrarianRequest
from apps.backend.librarian import Librarian
from src.linger.corpus.animal_farm import BOOK as ANIMAL_FARM
from src.linger.corpus.pinocchio import BOOK as PINOCCHIO
from src.linger.corpus.registry import BookClarification, CORPORA
from src.linger.orchestration.grounding import (
    BookVersionOutOfScope,
    build_request,
    evidence_record_from_item,
    grounding_evidence,
)

with patch.dict(os.environ, {"LINGER_MODEL": "google:gemini-2.5-flash", "GOOGLE_API_KEY": "test-key"}):
    from apps.backend import chat_turn, sessions
    from apps.backend.schemas import ChatRequest


class BookActivationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(_env_file=None, linger_model="google:gemini-2.5-flash")
        self.librarian = Librarian()
        self.addCleanup(sessions.clear, "activation-test")

    def test_chat_and_librarian_share_enabled_titles_aliases_and_ids(self) -> None:
        for book, names, chapter_count in (
            (ANIMAL_FARM, (ANIMAL_FARM.title, ANIMAL_FARM.work_id), 10),
            (PINOCCHIO, (PINOCCHIO.title, "Pinocchio", PINOCCHIO.work_id), 36),
        ):
            for name in names:
                with self.subTest(name=name), patch.object(chat_turn, "settings", self.settings):
                    sessions.clear("activation-test")
                    context = chat_turn.resolve_reading_context(ChatRequest(
                        session_id="activation-test", message=name,
                    ))
                    self.assertEqual(book.work_id, context.work_id)
                    self.assertIsNone(context.chapter_max)
                    context = chat_turn.resolve_reading_context(ChatRequest(
                        session_id="activation-test", message=f"I've finished Chapter 1 of {name}.",
                    ))
                    self.assertEqual(book.work_id, context.work_id)
                    self.assertEqual(book.book_version_id, context.book_version_id)
                    self.assertEqual(1, context.chapter_max)
                    route = self.librarian.route_work(name, self.settings.allowed_book_version_ids)
                    self.assertEqual(book.work_id, route.scope.work_id)
                    self.assertEqual(book.book_version_id, route.scope.book_version_id)
                    self.assertEqual(chapter_count, route.scope.max_chapter)

    def test_new_books_retrieve_canonical_evidence_without_opening_later_chapters(self) -> None:
        for book, query in ((ANIMAL_FARM, "Major dream animals"), (PINOCCHIO, "Master Cherry wood")):
            with self.subTest(book=book.title):
                opened = []
                read_text = Path.read_text

                def recording_read(path, *args, **kwargs):
                    opened.append(path)
                    return read_text(path, *args, **kwargs)

                with patch.object(Path, "read_text", autospec=True, side_effect=recording_read):
                    bundle = self.librarian.retrieve(LibrarianRequest(
                        query=query,
                        book_scopes=[BookScope(work_id=book.work_id, book_version_id=book.book_version_id, chapter_max=1)],
                    ))
                    self.assertTrue(bundle.items)
                    for item in bundle.items:
                        self.assertEqual(book.work_id, item.work_id)
                        self.assertEqual(book.book_version_id, item.book_version_id)
                        self.assertEqual(1, item.chapter)
                        self.assertEqual(evidence_record_from_item(item), self.librarian.fetch_by_id(item.evidence_id))
                chapter_files = {path for path in opened if path.suffix == ".md"}
                self.assertEqual({next((book.default_output / "chapters").glob("01-*.md"))}, chapter_files)

    def test_access_override_disables_registered_books_before_reading(self) -> None:
        restricted = self.settings.model_copy(update={"allowed_book_version_ids": ("pg11-v01b38ea4",)})
        for book in (ANIMAL_FARM, PINOCCHIO):
            with (
                self.subTest(book=book.title),
                patch.object(chat_turn, "settings", restricted),
                patch("src.linger.orchestration.grounding.get_settings", return_value=restricted),
                patch.object(Path, "read_text", side_effect=AssertionError("denied corpus was opened")),
            ):
                context = chat_turn.resolve_reading_context(ChatRequest(
                    session_id="activation-test", message=f"I've finished Chapter 1 of {book.title}.",
                ))
                self.assertIsNone(context.work_id)
                self.assertIsNone(context.chapter_max)
                self.assertIsInstance(self.librarian.route_work(book.title, restricted.allowed_book_version_ids), BookClarification)
                request = build_request("query", book.work_id, book.book_version_id, None)
                with self.assertRaises(BookVersionOutOfScope):
                    asyncio.run(grounding_evidence(request, librarian=self.librarian))

    def test_section_corpora_remain_unregistered_and_ungranted(self) -> None:
        from src.linger.corpus.douglass import BOOK as DOUGLASS
        from src.linger.corpus.story_of_my_life import BOOK as STORY_OF_MY_LIFE

        for book in (DOUGLASS, STORY_OF_MY_LIFE):
            with self.subTest(book=book.title):
                self.assertNotIn(book.work_id, CORPORA)
                self.assertNotIn(book.book_version_id, self.settings.allowed_book_version_ids)
