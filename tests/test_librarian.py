"""Regression tests for canonical, spoiler-bounded Librarian retrieval."""

import unittest
from pathlib import Path
from unittest.mock import patch

from apps.backend.contracts import BookScope, LibrarianRequest
from apps.backend.librarian import CorpusScopeError, Librarian
from src.linger.corpus.alice import BOOK, BOOK_VERSION_ID, WORK_ID


def request(
    query: str,
    *,
    chapter_max: int = 5,
    threshold: float = 0.5,
) -> LibrarianRequest:
    return LibrarianRequest(
        query=query,
        book_scopes=[
            BookScope(
                work_id=WORK_ID,
                book_version_id=BOOK_VERSION_ID,
                chapter_max=chapter_max,
            )
        ],
        retrieval_score_threshold=threshold,
    )


class LibrarianTests(unittest.TestCase):
    def setUp(self) -> None:
        self.librarian = Librarian()

    def test_unrelated_query_returns_no_evidence_without_fallback(self) -> None:
        bundle = self.librarian.retrieve(request("zyxwvu qqqqq"))
        self.assertEqual([], bundle.items)

    def test_threshold_is_applied(self) -> None:
        baseline = self.librarian.retrieve(request("growing caterpillar", threshold=0.5))
        strict = self.librarian.retrieve(request("growing caterpillar", threshold=0.9))
        self.assertTrue(baseline.items)
        self.assertEqual([], strict.items)

    def test_evidence_id_resolves_to_exact_canonical_source_lines(self) -> None:
        bundle = self.librarian.retrieve(request("explain myself caterpillar"))
        item = next(item for item in bundle.items if item.chapter == 5)
        source_lines = BOOK.default_source.read_text(encoding="utf-8").splitlines()
        start, end = item.source_lines

        self.assertEqual("\n".join(source_lines[start - 1 : end]), item.excerpt)
        self.assertEqual(
            f"{item.chapter_id}-ln{start:04d}-{end:04d}",
            item.evidence_id,
        )
        self.assertEqual(BOOK.source_sha256, item.source_sha256)

    def test_chapter_above_ceiling_is_never_opened(self) -> None:
        opened: list[Path] = []
        original = Path.read_text

        def recording_read(path: Path, *args, **kwargs):
            opened.append(path)
            return original(path, *args, **kwargs)

        with patch.object(Path, "read_text", autospec=True, side_effect=recording_read):
            bundle = self.librarian.retrieve(request("caterpillar", chapter_max=4))

        self.assertTrue(all(item.chapter <= 4 for item in bundle.items))
        self.assertFalse(any("05-advice-from-a-caterpillar" in str(path) for path in opened))

    def test_work_and_revision_must_be_a_registered_pair(self) -> None:
        invalid = LibrarianRequest(
            query="identity",
            book_scopes=[
                BookScope(
                    work_id="animal-farm",
                    book_version_id=BOOK_VERSION_ID,
                    chapter_max=3,
                )
            ],
        )

        with self.assertRaises(CorpusScopeError):
            self.librarian.retrieve(invalid)


if __name__ == "__main__":
    unittest.main()
