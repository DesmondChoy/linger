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

    def test_fetch_by_id_reconstructs_exact_canonical_evidence(self) -> None:
        expected = next(
            item
            for item in self.librarian.retrieve(request("explain myself caterpillar")).items
            if item.chapter == 5
        )

        record = self.librarian.fetch_by_id(expected.evidence_id)

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(expected.evidence_id, record.evidence_id)
        self.assertEqual(expected.work_id, record.work_id)
        self.assertEqual(expected.book_version_id, record.book_version_id)
        self.assertEqual(expected.chapter_id, record.chapter_id)
        self.assertEqual(expected.chapter, record.chapter_number)
        self.assertEqual(expected.location, record.location)
        self.assertEqual(expected.source_sha256, record.source_sha256)
        self.assertEqual(expected.source_lines, record.source_lines)
        self.assertEqual(expected.excerpt, record.text)

    def test_fetch_by_id_opens_only_the_matching_chapter(self) -> None:
        opened: list[Path] = []
        original = Path.read_text

        def recording_read(path: Path, *args, **kwargs):
            opened.append(path)
            return original(path, *args, **kwargs)

        with patch.object(Path, "read_text", autospec=True, side_effect=recording_read):
            record = self.librarian.fetch_by_id(
                "pg11-v01b38ea4-ch05-ln0974-0975"
            )

        self.assertIsNotNone(record)
        chapter_paths = [path for path in opened if path.suffix == ".md"]
        self.assertEqual(1, len(chapter_paths))
        self.assertIn("05-advice-from-a-caterpillar", str(chapter_paths[0]))

    def test_fetch_by_id_rejects_noncanonical_or_unresolvable_ranges(self) -> None:
        cases = (
            "not-an-evidence-id",
            "pg11-v01b38ea4-ch99-ln0001-0002",
            "pg11-v01b38ea4-ch05-ln974-0975",
            "pg11-v01b38ea4-ch05-ln0975-0975",
            "pg11-v01b38ea4-ch05-ln0975-0974",
        )

        for evidence_id in cases:
            with self.subTest(evidence_id=evidence_id):
                self.assertIsNone(self.librarian.fetch_by_id(evidence_id))

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
