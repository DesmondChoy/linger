"""Regression tests for canonical, spoiler-bounded Librarian retrieval."""

import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.backend.contracts import BookScope, LibrarianRequest
from apps.backend.librarian import CorpusRegistration, CorpusScopeError, Librarian
from src.linger.corpus.alice import BOOK, BOOK_VERSION_ID, WORK_ID
from src.linger.corpus.book import BookCorpus


def _fake_registration(tmp_path: Path, *, work_id: str, catalog: dict) -> CorpusRegistration:
    """Build a minimal registered corpus: only `catalog.json` is ever read by routing."""
    sha = hashlib.sha256(work_id.encode()).hexdigest()
    book_version_id = f"{work_id}-v{sha[:8]}"
    root = tmp_path / book_version_id
    root.mkdir()
    catalog = {**catalog, "work_id": work_id, "book_version_id": book_version_id}
    (root / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    book = BookCorpus(
        work_id=work_id,
        book_version_id=book_version_id,
        title=catalog.get("title", work_id),
        author="Test Author",
        source_path="fake.txt",
        source_sha256=sha,
        default_source=root / "source.txt",
        default_output=root,
        parse_source=lambda _path: (),
    )
    return CorpusRegistration(book=book, root=root)


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

    def test_metadata_routes_alice_cues_without_opening_story_text(self) -> None:
        decision = self.librarian.route_work(
            "Why does Alice keep struggling to explain who she is?",
            (BOOK_VERSION_ID,),
        )

        self.assertIsNotNone(decision)
        assert decision is not None
        scope = decision.scope
        self.assertEqual(WORK_ID, scope.work_id)
        self.assertEqual(BOOK_VERSION_ID, scope.book_version_id)
        self.assertEqual(12, scope.max_chapter)
        self.assertGreaterEqual(decision.confidence, 0.6)

    def test_explicit_title_mention_routes_with_full_confidence(self) -> None:
        decision = self.librarian.route_work(
            "Can we talk about Alice's Adventures in Wonderland today?",
            (BOOK_VERSION_ID,),
        )

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(WORK_ID, decision.scope.work_id)
        self.assertEqual(1.0, decision.confidence)

    def test_lone_generic_catalog_word_in_reflection_does_not_route(self) -> None:
        decision = self.librarian.route_work(
            "My afternoon in the garden while journaling about my grandmother "
            "was calming.",
            (BOOK_VERSION_ID,),
        )

        self.assertIsNone(decision)

    def test_bare_single_word_message_does_not_route(self) -> None:
        # Confidence must be length-independent: a one-word message carries the
        # same single incidental cue as a long one and must not route either.
        decision = self.librarian.route_work("garden", (BOOK_VERSION_ID,))

        self.assertIsNone(decision)

    def test_long_genuine_multi_cue_request_routes_despite_its_length(self) -> None:
        # A length-relative formula would dilute several genuine catalog cues
        # across a long message and reject it; an absolute-evidence formula
        # must still route it.
        decision = self.librarian.route_work(
            "I keep thinking about that scene where the caterpillar asks Alice "
            "who she is, and she cannot explain herself, and it reminded me of "
            "a much longer story I want to tell you about my own week and how "
            "confusing it has felt lately, but first: does the caterpillar ever "
            "explain why he keeps asking?",
            (BOOK_VERSION_ID,),
        )

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(WORK_ID, decision.scope.work_id)
        self.assertGreaterEqual(decision.confidence, 0.6)

    def test_equally_evidenced_works_are_ambiguous_not_alphabetical(self) -> None:
        import tempfile

        catalog = {
            "chapters": [
                {
                    "chapter_number": 1,
                    "characters": ["Zorblatt", "Quendra"],
                    "locations": [],
                    "retrieval_cues": [],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_a = _fake_registration(tmp_path, work_id="alpha-book", catalog=catalog)
            fake_b = _fake_registration(tmp_path, work_id="beta-book", catalog=catalog)
            with patch(
                "apps.backend.librarian.CORPORA",
                {
                    fake_a.book.work_id: fake_a,
                    fake_b.book.work_id: fake_b,
                },
            ):
                decision = self.librarian.route_work(
                    "Why does Zorblatt trust Quendra so much?",
                    (fake_a.book.book_version_id, fake_b.book.book_version_id),
                )

        # A tie in the full evidence signal (confidence and overlap) must be
        # ambiguous. Comparing only (scope, confidence) would instead sort
        # alphabetically by work_id and silently pick "alpha-book".
        self.assertIsNone(decision)

    def test_metadata_does_not_route_an_unrelated_line(self) -> None:
        unrelated_lines = (
            "Repair the spaceship engine",
            "Sketching by hand helps me slow down and think clearly.",
            "My desk feels oddly quiet with the fan switched off.",
        )

        for line in unrelated_lines:
            with self.subTest(line=line):
                self.assertIsNone(
                    self.librarian.route_work(line, (BOOK_VERSION_ID,))
                )

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
