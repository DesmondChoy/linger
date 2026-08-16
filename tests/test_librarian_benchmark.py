"""Deterministic checks for the versioned Librarian retrieval benchmark."""

import unittest

from evals.librarian.benchmark import (
    BOOK,
    STRATEGIES,
    Hit,
    _citation_resolves,
    _dedupe_overlaps,
    load_cases,
    load_windows,
    select_strategy,
)


class LibrarianBenchmarkFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_cases()
        cls.windows = load_windows()
        cls.source_lines = BOOK.default_source.read_text(encoding="utf-8").splitlines()

    def test_query_set_is_versioned_and_covers_all_strengths(self) -> None:
        self.assertEqual(1, self.cases.schema_version)
        self.assertEqual(BOOK.book_version_id, self.cases.book_version_id)
        self.assertGreaterEqual(len(self.cases.cases), 10)
        self.assertEqual(
            {"sufficient", "weak", "none"},
            {case.expected_strength for case in self.cases.cases},
        )

    def test_gold_ranges_never_exceed_each_case_boundary(self) -> None:
        for case in self.cases.cases:
            with self.subTest(case_id=case.case_id):
                self.assertTrue(
                    all(chapter <= case.chapter_max for chapter, _, _ in case.relevant_ranges)
                )

    def test_windows_never_cross_chapters_and_resolve_exactly(self) -> None:
        self.assertTrue(self.windows)
        for window in self.windows:
            with self.subTest(evidence_id=window.evidence_id):
                hit = Hit(
                    window.evidence_id,
                    window.chapter,
                    window.source_lines,
                    window.text,
                    0.0,
                )
                self.assertTrue(_citation_resolves(hit, self.source_lines))
                self.assertIn(f"-ch{window.chapter:02d}-", window.evidence_id)


class StrategySelectionTests(unittest.TestCase):
    def metric(self, quality: float, latency: float, *, safety: bool = True) -> dict[str, float | bool]:
        return {
            "quality_score": quality,
            "p95_latency_ms": latency,
            "mean_evidence_tokens": 100.0,
            "monetary_cost_usd": 0.0,
            "safety_pass": safety,
            "citation_pass": True,
        }

    def test_safety_gate_beats_quality(self) -> None:
        metrics = {name: self.metric(0.5, 10.0) for name in STRATEGIES}
        metrics["semantic"] = self.metric(1.0, 1.0, safety=False)
        self.assertNotEqual("semantic", select_strategy(metrics))

    def test_latency_breaks_quality_equivalent_tie(self) -> None:
        metrics = {name: self.metric(0.5, 10.0) for name in STRATEGIES}
        metrics["bm25"] = self.metric(0.90, 4.0)
        metrics["hybrid"] = self.metric(0.89, 2.0)
        self.assertEqual("hybrid", select_strategy(metrics))


class OverlapDeduplicationTests(unittest.TestCase):
    @staticmethod
    def hit(evidence_id: str, chapter: int, start: int, end: int, score: float) -> Hit:
        return Hit(evidence_id, chapter, (start, end), evidence_id, score)

    def test_suppresses_strong_overlap_without_crossing_chapters(self) -> None:
        ranked = [
            self.hit("best", 1, 10, 30, 0.9),
            self.hit("duplicate", 1, 20, 35, 0.8),
            self.hit("distinct", 1, 40, 55, 0.7),
            self.hit("other-chapter", 2, 20, 35, 0.6),
        ]

        self.assertEqual(
            ["best", "distinct", "other-chapter"],
            [hit.evidence_id for hit in _dedupe_overlaps(ranked, 5)],
        )

    def test_respects_result_limit(self) -> None:
        ranked = [self.hit(str(index), 1, index * 10, index * 10 + 5, 1.0) for index in range(5)]
        self.assertEqual(2, len(_dedupe_overlaps(ranked, 2)))


if __name__ == "__main__":
    unittest.main()
