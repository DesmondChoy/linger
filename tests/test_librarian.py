"""Regression tests for canonical, spoiler-bounded Librarian retrieval."""

import unittest
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from apps.backend.contracts import BookScope, LibrarianRequest
from apps.backend.librarian import CorpusScopeError, Librarian
from src.linger.corpus.registry import BookClarification
from src.linger.corpus.alice import BOOK, BOOK_VERSION_ID, WORK_ID
from corpus_fixtures import fake_registration


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
        # "alice" alone is only one distinct cue (below threshold); pair it
        # with a second genuine catalog cue to justify metadata-only routing.
        decision = self.librarian.route_work(
            "Why does Alice trust the White Rabbit near the riverbank?",
            (BOOK_VERSION_ID,),
        )

        self.assertIsNotNone(decision)
        assert decision is not None
        scope = decision.scope
        self.assertEqual(WORK_ID, scope.work_id)
        self.assertEqual(BOOK_VERSION_ID, scope.book_version_id)
        self.assertEqual(12, scope.max_chapter)
        self.assertGreaterEqual(decision.confidence, 0.6)
        self.assertEqual("distinctive_cue", decision.basis)

    def test_explicit_title_mention_routes_with_full_confidence(self) -> None:
        decision = self.librarian.route_work(
            "Can we talk about Alice's Adventures in Wonderland today?",
            (BOOK_VERSION_ID,),
        )

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(WORK_ID, decision.scope.work_id)
        self.assertEqual(1.0, decision.confidence)
        self.assertEqual("resolved_book_identity", decision.basis)

    def test_registered_aliases_route_with_full_confidence(self) -> None:
        for alias in ("Alice in Wonderland", "ALICE IN WONDERLAND"):
            with self.subTest(alias=alias):
                decision = self.librarian.route_work(
                    f"What does {alias} say about identity?", (BOOK_VERSION_ID,)
                )
                self.assertIsNotNone(decision)
                assert decision is not None
                self.assertEqual(WORK_ID, decision.scope.work_id)
                self.assertEqual(1.0, decision.confidence)

    def test_broad_or_unknown_names_do_not_select_alice(self) -> None:
        for message in (
            "Wonderland",
            "I read Winter Wonderland yesterday.",
            "The snow turned our street into a winter wonderland.",
        ):
            with self.subTest(message=message):
                result = self.librarian.route_work(message, (BOOK_VERSION_ID,))
                self.assertIsInstance(result, BookClarification)

    def test_full_title_beats_an_alias_embedded_in_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = fake_registration(root, work_id="first", catalog={
                "title": "The Orchard Notebook",
                "chapters": [{"chapter_number": 1}],
            })
            second = replace(fake_registration(root, work_id="second", catalog={
                "title": "A Different Garden",
                "chapters": [{"chapter_number": 1, "characters": ["Quendra"]}],
            }), aliases=("orchard",))
            with patch("src.linger.corpus.registry.CORPORA", {"first": first, "second": second}):
                result = self.librarian.route_work(
                    "The Orchard Notebook reminds me of Quendra.",
                    (first.book.book_version_id, second.book.book_version_id),
                )
            self.assertIsNotNone(result)
            self.assertEqual("first", result.scope.work_id)

    def test_shared_alias_and_multiple_named_books_do_not_choose_by_cue_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = replace(fake_registration(root, work_id="first", catalog={
                "title": "The Orchard Notebook",
                "chapters": [{"chapter_number": 1}],
            }), aliases=("the notebook",))
            second = replace(fake_registration(root, work_id="second", catalog={
                "title": "The Garden Notebook",
                "chapters": [{"chapter_number": 1, "characters": ["Quendra"]}],
            }), aliases=("the notebook",))
            with patch("src.linger.corpus.registry.CORPORA", {"first": first, "second": second}):
                for message in (
                    "The notebook reminds me of Quendra.",
                    "Compare The Orchard Notebook and The Garden Notebook with Quendra.",
                ):
                    with self.subTest(message=message):
                        result = self.librarian.route_work(
                            message, (first.book.book_version_id, second.book.book_version_id)
                        )
                        self.assertIsInstance(result, BookClarification)

    def test_aliases_respect_word_boundaries_and_revision_grants(self) -> None:
        self.assertIsNone(
            self.librarian.route_work("Wonderlandish scenery", (BOOK_VERSION_ID,))
        )
        self.assertIsNone(self.librarian.route_work("Alice in Wonderland", ()))

    def test_lone_generic_catalog_word_in_reflection_does_not_route(self) -> None:
        decision = self.librarian.route_work(
            "My afternoon in the garden while journaling about my grandmother "
            "was calming.",
            (BOOK_VERSION_ID,),
        )

        self.assertIsNone(decision)

    def test_incidental_cue_fragments_in_reflection_do_not_route(self) -> None:
        # Live replay regression: one incidental catalog cue ("garden") plus
        # ordinary words from cue phrases must not accumulate confidence.
        decision = self.librarian.route_work(
            "I signed up for a plot in the community garden this spring, and "
            "I keep going back and forth about whether I'm taking on more "
            "than I can keep up with this season.",
            (BOOK_VERSION_ID,),
        )

        self.assertIsNone(decision)

    def test_word_boundary_prevents_substring_false_positive(self) -> None:
        # "alice" inside "Malice", "pigeon" inside "pigeonholing" must not match.
        decision = self.librarian.route_work(
            "Malice and pigeonholing at work today.",
            (BOOK_VERSION_ID,),
        )

        self.assertIsNone(decision)

    def test_nested_cue_is_not_double_counted(self) -> None:
        # "garden" and "rose garden" both match; only the maximal cue counts,
        # leaving one distinct multi-word cue, below threshold.
        decision = self.librarian.route_work(
            "my grandmother tends her rose garden",
            (BOOK_VERSION_ID,),
        )

        self.assertIsNone(decision)

    def test_generic_single_word_cues_do_not_route(self) -> None:
        # cook/eggs/baby are catalog cues but also common English words
        # (GENERIC_CUE_WORDS); none of them may count toward confidence.
        decision = self.librarian.route_work(
            "The kitchen cook made eggs for the baby.",
            (BOOK_VERSION_ID,),
        )

        self.assertIsNone(decision)

    def test_lone_generic_single_word_cue_does_not_route(self) -> None:
        decision = self.librarian.route_work(
            "The cook was busy today.",
            (BOOK_VERSION_ID,),
        )

        self.assertIsNone(decision)

    def test_distinctive_bare_single_word_names_route(self) -> None:
        # Unlike generic words, two distinctive single-word character names
        # (not in GENERIC_CUE_WORDS) must still clear the threshold.
        decision = self.librarian.route_work(
            "Why does the Dormouse annoy the Hatter?",
            (BOOK_VERSION_ID,),
        )

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertGreaterEqual(decision.confidence, 0.6)

    def test_distinctive_multi_word_character_scene_routes(self) -> None:
        decision = self.librarian.route_work(
            "What does the Dormouse say to the Hatter at the tea party?",
            (BOOK_VERSION_ID,),
        )

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertGreaterEqual(decision.confidence, 0.6)

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
            fake_a = fake_registration(tmp_path, work_id="alpha-book", catalog=catalog)
            fake_b = fake_registration(tmp_path, work_id="beta-book", catalog=catalog)
            with patch(
                "src.linger.corpus.registry.CORPORA",
                {
                    fake_a.book.work_id: fake_a,
                    fake_b.book.work_id: fake_b,
                },
            ):
                decision = self.librarian.route_work(
                    "Why does Zorblatt trust Quendra so much?",
                    (fake_a.book.book_version_id, fake_b.book.book_version_id),
                )

        self.assertIsInstance(decision, BookClarification)
        self.assertEqual(
            {"alpha-book", "beta-book"},
            {item.book.work_id for item in decision.candidates},
        )

    def test_metadata_generates_strong_candidate_for_distinctive_cue(self) -> None:
        candidates = self.librarian.work_candidates(
            "Why does the Cheshire Cat keep disappearing?",
            (BOOK_VERSION_ID,),
        )

        self.assertEqual(1, len(candidates))
        self.assertEqual("strong", candidates[0].strength)
        self.assertEqual(WORK_ID, candidates[0].scope.work_id)
        self.assertEqual(BOOK_VERSION_ID, candidates[0].scope.book_version_id)
        self.assertEqual(12, candidates[0].scope.max_chapter)

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

    def test_metadata_does_not_generate_an_unrelated_candidate(self) -> None:
        unrelated_lines = (
            "Repair the spaceship engine",
            "Sketching by hand helps me slow down and think clearly.",
            "My desk feels oddly quiet with the fan switched off.",
        )

        for line in unrelated_lines:
            with self.subTest(line=line):
                self.assertFalse(
                    any(
                        candidate.strength == "strong"
                        for candidate in self.librarian.work_candidates(
                            line,
                            (BOOK_VERSION_ID,),
                        )
                    )
                )

    def test_common_catalog_words_are_weak_candidates_only(self) -> None:
        for line in (
            "My friend Alice is stressed about work.",
            "What should I cook for dinner?",
            "A mouse ran through the kitchen.",
            "I saw a caterpillar outside.",
            "Alice, Alice, Alice.",
            "Alice saw a mouse.",
            "Wonderland: Alice and the Caterpillar.",
        ):
            with self.subTest(line=line):
                candidates = self.librarian.work_candidates(
                    line,
                    (BOOK_VERSION_ID,),
                )
                self.assertTrue(candidates)
                self.assertTrue(
                    all(candidate.strength == "weak" for candidate in candidates)
                )

    def test_separate_story_cues_select_non_alice_memory_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registration = fake_registration(
                Path(directory), work_id="other-book", catalog={
                    "chapters": [{
                        "chapter_number": 1,
                        "characters": ["Zorblatt", "Quendra"],
                    }],
                },
            )
            with patch("src.linger.corpus.registry.CORPORA", {"other-book": registration}):
                candidates = self.librarian.work_candidates(
                    "Zorblatt spoke to Quendra.", (registration.book.book_version_id,),
                )
                self.assertEqual(1, len(candidates))
                self.assertEqual("strong", candidates[0].strength)
                self.assertEqual("other-book", candidates[0].scope.work_id)
                self.assertEqual((), self.librarian.work_candidates(
                    "Zorblatt spoke to Quendra.", (BOOK_VERSION_ID,),
                ))

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
