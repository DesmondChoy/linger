"""Real-corpus checks for narrowing private windows into exact paragraphs."""

import unittest
from unittest.mock import patch

from apps.backend.hybrid_librarian import HybridLibrarian
from apps.backend.librarian import CorpusScopeError, Librarian
from src.linger.corpus.alice import BOOK


class CandidateParagraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.librarian = Librarian()
        self.window = self.librarian.fetch_by_id("pg11-v01b38ea4-ch05-ln0960-1016")
        self.quote = self.librarian.fetch_by_id("pg11-v01b38ea4-ch05-ln0974-0975")
        assert self.window is not None and self.quote is not None

    def test_narrows_window_into_canonical_single_paragraphs(self) -> None:
        paragraphs = self.librarian.candidate_paragraphs((self.window,))

        self.assertGreater(len(paragraphs), 1)
        self.assertIn(self.quote, paragraphs)
        self.assertNotIn(self.window, paragraphs)
        self.assertEqual(self.window.text, "\n\n".join(item.text for item in paragraphs))
        source = BOOK.default_source.read_text(encoding="utf-8").splitlines()
        for item in paragraphs:
            with self.subTest(evidence_id=item.evidence_id):
                self.assertNotIn("\n\n", item.text)
                self.assertGreaterEqual(item.source_lines[0], self.window.source_lines[0])
                self.assertLessEqual(item.source_lines[1], self.window.source_lines[1])
                self.assertEqual(
                    "\n".join(source[item.source_lines[0] - 1 : item.source_lines[1]]),
                    item.text,
                )
                self.assertEqual(item, self.librarian.fetch_by_id(item.evidence_id))

    def test_single_paragraph_does_not_expand_to_neighbors(self) -> None:
        self.assertEqual((self.quote,), self.librarian.candidate_paragraphs((self.quote,)))

    def test_overlapping_candidates_deduplicate_in_first_seen_order(self) -> None:
        paragraphs = self.librarian.candidate_paragraphs((self.window,))
        self.assertEqual(
            (self.quote,) + tuple(item for item in paragraphs if item != self.quote),
            self.librarian.candidate_paragraphs((self.quote, self.window, self.window)),
        )

    def test_forged_candidate_fields_fail_closed(self) -> None:
        for update in (
            {"text": self.window.text + " invented text"},
            {"work_id": "different-work"},
            {"book_version_id": "different-revision"},
            {"source_sha256": "0" * 64},
            {"source_lines": (960, 1017)},
            {"chapter_number": 4},
            {"chapter_id": "different-chapter"},
            {"location": "different-location"},
            {"evidence_id": "invalid"},
            {"evidence_id": "pg11-v01b38ea4-ch05-ln0961-1016"},
        ):
            with self.subTest(update=update):
                with self.assertRaises(CorpusScopeError):
                    self.librarian.candidate_paragraphs((self.window.model_copy(update=update),))

    def test_empty_candidates_return_no_paragraphs(self) -> None:
        self.assertEqual((), self.librarian.candidate_paragraphs(()))

    def test_hybrid_inherits_narrowing_without_retrieval_models(self) -> None:
        librarian = HybridLibrarian()
        with (
            patch.object(librarian, "retrieve", side_effect=AssertionError("searched")),
            patch.object(librarian, "_embedding_model", side_effect=AssertionError("embedded")),
            patch.object(librarian, "_reranker_model", side_effect=AssertionError("reranked")),
        ):
            self.assertEqual((self.quote,), librarian.candidate_paragraphs((self.quote,)))
