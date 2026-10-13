"""Deterministic checks for the versioned Librarian retrieval benchmark."""

import unittest

from evals.librarian.benchmark import (
    BOOK,
    STRATEGIES,
    BenchmarkCase,
    Hit,
    _citation_resolves,
    _dedupe_overlaps,
    load_cases,
    load_windows,
    measure,
    select_strategy,
)


# Replies saved from five live `pigeon-serpent` runs. A human read runs 1, 2 and
# 4 as stating both reasons, run 3 as omitting Alice's admission, and run 5 as
# a decline.
PIGEON_REPLIES = {
    "run1": (
        "In Chapter 5, the Pigeon is on guard against serpents because it fears "
        "they’ll get at its eggs, and Alice’s unusually long neck makes it mistake "
        "her for one. When Alice says she’s a little girl, the Pigeon rejects that "
        "because it has never seen a girl with a neck like hers; then, when she "
        "admits girls eat eggs too, it uses that to insist girls must be a kind of "
        "serpent as well. The joke is that the Pigeon bends every answer to fit its "
        "suspicion."
    ),
    "run2": (
        "In Chapter 5, the Pigeon mistakes Alice for a serpent because her long neck "
        "fits its idea of what a serpent looks like, and it suspects she wants to "
        "eat its eggs. When Alice admits she has tasted eggs, the Pigeon treats that "
        "as proof: “if they do, why then\nthey’re a kind of serpent, that’s all I "
        "can say.” Its reasoning is comic but circular: it has already decided what "
        "Alice is, then turns her answer into confirmation."
    ),
    "run3": (
        "In Chapter 5, the Pigeon reads Alice’s unusually long neck as proof that "
        "she’s a serpent. It’s also on constant watch for serpents because they "
        "threaten its eggs, so it treats Alice as the danger it expects to find. The "
        "Pigeon’s conclusion comes from its own suspicion, not from Alice actually "
        "being a serpent."
    ),
    "run4": (
        "In Chapter 5, the Pigeon sees Alice’s unusually long neck and suspects she "
        "is after its eggs. When Alice points out that girls eat eggs too, the "
        "Pigeon reasons that egg-eating makes someone serpent-like. Its accusation "
        "reflects its suspicion and protectiveness toward its eggs, not Alice "
        "actually being a serpent."
    ),
    "run5": (
        "I couldn’t verify that against the sources I can use, so I’d rather not "
        "guess. If you ask again with the passage in mind, I’ll take another look."
    ),
}


class LibrarianBenchmarkFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_cases()
        cls.windows = load_windows()
        cls.source_lines = BOOK.default_source.read_text(encoding="utf-8").splitlines()

    def test_query_set_is_versioned_and_covers_all_evidence_strengths(self) -> None:
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

    def test_required_ranges_are_relevant_and_within_boundary(self) -> None:
        for case in self.cases.cases:
            with self.subTest(case_id=case.case_id):
                self.assertTrue(
                    all(gold in case.relevant_ranges for group in case.recall_groups for gold in group)
                )
                self.assertTrue(
                    all(
                        chapter <= case.chapter_max
                        for group in case.recall_groups for chapter, _, _ in group
                    )
                )

    def test_identity_theme_accepts_either_specific_chapter_five_dialogue(self) -> None:
        case = next(case for case in self.cases.cases if case.case_id == "identity-theme")
        self.assertEqual("How do Alice's changing size and uncertain identity reinforce each other?", case.query)
        self.assertEqual(5, case.chapter_max)
        self.assertEqual("sufficient", case.expected_strength)
        for gold in ((5, 979, 981), (5, 1026, 1027)):
            with self.subTest(anchor=gold):
                measured = measure(case, [self.canonical_hit(*gold)], self.source_lines)
                self.assertEqual(1.0, measured.recall)
                self.assertEqual(1.0, measured.precision)
                self.assertTrue(measured.citations_resolve)

    def test_identity_theme_counts_both_alternatives_as_one_required_fact(self) -> None:
        case = next(case for case in self.cases.cases if case.case_id == "identity-theme")
        hits = [self.canonical_hit(5, 966, 981), self.canonical_hit(5, 1026, 1032)]
        self.assertEqual(1.0, measure(case, hits, self.source_lines).recall)

    def test_identity_theme_rejects_remarks_inside_the_gold_passage(self) -> None:
        from apps.backend.librarian import Librarian

        case = next(case for case in self.cases.cases if case.case_id == "identity-theme")
        for line in (977, 1029):
            with self.subTest(line=line):
                record = Librarian().fetch_by_id(f"{BOOK.book_version_id}-ch05-ln{line:04d}-{line:04d}")
                hit = Hit(record.evidence_id, record.chapter_number, record.source_lines, record.text, 1.0)
                measured = measure(case, [hit], self.source_lines)
                self.assertTrue(measured.citations_resolve)
                self.assertEqual(0.0, measured.recall)
                self.assertEqual(0.0, measured.precision)

    def test_retrieval_measurement_does_not_depend_on_expected_strength(self) -> None:
        case = next(case for case in self.cases.cases if case.case_id == "identity-theme")
        hits = [self.canonical_hit(4, 762, 770)]
        weak = case.model_copy(update={"expected_strength": "weak"})
        self.assertEqual(measure(case, hits, self.source_lines), measure(weak, hits, self.source_lines))

    def test_partial_or_wrong_chapter_coverage_cannot_satisfy_a_fact(self) -> None:
        case = BenchmarkCase(
            case_id="complete-span", query="Why is Alice confused?", chapter_max=5,
            expected_strength="sufficient", relevant_ranges=((5, 979, 981),),
        )
        for span in ((5, 978, 980), (5, 980, 982), (4, 978, 982)):
            with self.subTest(span=span):
                result = measure(case, [self.canonical_hit(*span)], self.source_lines)
                self.assertEqual((0.0, 0.0), (result.recall, result.precision))
        for span in ((5, 979, 981), (5, 978, 982)):
            with self.subTest(span=span):
                result = measure(case, [self.canonical_hit(*span)], self.source_lines)
                self.assertEqual((1.0, 1.0), (result.recall, result.precision))

    def test_required_groups_keep_independent_facts_required(self) -> None:
        case = BenchmarkCase(
            case_id="joint-facts", query="Compare two events", chapter_max=5,
            expected_strength="sufficient",
            relevant_ranges=((5, 966, 981), (5, 1026, 1032), (2, 327, 360)),
            required_range_groups=(((5, 966, 981), (5, 1026, 1032)), ((2, 327, 360),)),
        )
        self.assertEqual(0.5, case.evidence_recall([(5, 966, 981), (5, 1026, 1032)]))
        self.assertEqual(1.0, case.evidence_recall([(5, 1026, 1032), (2, 327, 360)]))
        self.assertEqual(0.0, case.evidence_recall([]))

    def test_required_groups_reject_empty_duplicate_unlisted_and_future_ranges(self) -> None:
        for groups in [(), ((),), (((5, 966, 981), (5, 966, 981)),),
                       (((5, 966, 981),), ((5, 966, 981),)),
                       (((5, 1026, 1032),),), (((6, 1370, 1380),),)]:
            with self.subTest(groups=groups), self.assertRaises(ValueError):
                BenchmarkCase(
                    case_id="invalid-groups", query="Question", chapter_max=5,
                    expected_strength="sufficient", relevant_ranges=((5, 966, 981),),
                    required_range_groups=groups,
                )

    def test_each_fact_is_required_when_no_alternatives_are_declared(self) -> None:
        case = BenchmarkCase(
            case_id="two-facts", query="Compare the two events", chapter_max=5,
            expected_strength="sufficient", relevant_ranges=((5, 979, 981), (5, 1026, 1027)),
        )
        self.assertEqual(0.5, case.evidence_recall([(5, 979, 981)]))
        self.assertEqual(1.0, case.evidence_recall([(5, 979, 981), (5, 1026, 1027)]))

    def test_pigeon_reasons_accept_one_complete_passage_or_two_separate_passages(self) -> None:
        case = next(case for case in self.cases.cases if case.case_id == "pigeon-serpent")
        self.assertEqual(1.0, case.evidence_recall([(5, 1208, 1212)]))
        self.assertEqual(1.0, case.evidence_recall([(5, 1162, 1169), (5, 1214, 1216)]))
        self.assertEqual(0.5, case.evidence_recall([(5, 1162, 1169)]))

    def test_pigeon_case_requires_the_reply_to_state_both_reasons(self) -> None:
        case = next(case for case in self.cases.cases if case.case_id == "pigeon-serpent")
        self.assertEqual(
            ["long-neck", "egg-eating-admission"],
            [fact.fact_id for fact in case.required_facts],
        )
        for other in self.cases.cases:
            if other.case_id != "pigeon-serpent":
                self.assertEqual((), other.required_facts, other.case_id)

    def test_pigeon_reply_facts_grade_the_saved_live_replies(self) -> None:
        case = next(case for case in self.cases.cases if case.case_id == "pigeon-serpent")
        for name in ("run1", "run2", "run4"):
            with self.subTest(reply=name):
                self.assertEqual((), case.missing_reply_facts(PIGEON_REPLIES[name]))
                self.assertEqual(1.0, case.reply_fact_recall(PIGEON_REPLIES[name]))
        self.assertEqual(
            ("egg-eating-admission",), case.missing_reply_facts(PIGEON_REPLIES["run3"])
        )
        self.assertEqual(0.5, case.reply_fact_recall(PIGEON_REPLIES["run3"]))
        self.assertEqual(
            ("long-neck", "egg-eating-admission"),
            case.missing_reply_facts(PIGEON_REPLIES["run5"]),
        )
        self.assertEqual(0.0, case.reply_fact_recall(PIGEON_REPLIES["run5"]))

    def test_egg_admission_is_about_alice_or_girls_eating_eggs(self) -> None:
        case = next(case for case in self.cases.cases if case.case_id == "pigeon-serpent")
        stated = [
            "Alice concedes that little girls eat eggs quite as much as serpents do.",
            "she has tasted eggs",
            "She’s tasted eggs, she admits.",
            "She's tasted eggs, she admits.",
            "Alice replies: “I _have_ tasted eggs, certainly”.",
            "The Pigeon is on the lookout for serpents because it fears they’ll eat "
            "its eggs; when Alice says she has eaten eggs too, it treats that as further proof.",
            "It suspects she wants to eat its eggs. Then Alice admits to eating eggs herself.",
            "It also suspects Alice wants eggs; when she admits she has tasted them, "
            "the Pigeon treats that as further proof.",
            "The Pigeon asks about eggs, and Alice says girls eat them too.",
            "Because both little girls and serpents eat eggs, it decides they must be a kind of serpent.",
            "It reasons that serpents and little girls eat eggs alike.",
            "The Pigeon argues that if little girls eat eggs too, they must be a kind of serpent.",
        ]
        unstated = [
            "It suspects she wants to eat its eggs.",
            "The Pigeon sees Alice’s long neck and believes she wants to eat eggs.",
            "Alice has a long neck. The Pigeon asks whether she has tasted eggs.",
            "The Pigeon asks if she has ever tasted an egg.",
            "Neither girls nor serpents eat eggs, Alice claims; girls and serpents never eat eggs.",
            "The Pigeon fears serpents will eat its eggs.",
            "It is hatching its eggs and on the look-out for serpents night and day.",
            "Alice says she is a little girl but the Pigeon knows serpents eat eggs.",
            "Alice insists she has never tasted eggs.",
            "Alice says she doesn’t eat eggs.",
            "Serpents threaten its eggs, and she fears they will eat them.",
            "The Pigeon guards its eggs because it thinks she will eat them.",
            "",
        ]
        for reply in stated:
            with self.subTest(stated=reply):
                self.assertNotIn("egg-eating-admission", case.missing_reply_facts(reply))
        for reply in unstated:
            with self.subTest(unstated=reply):
                self.assertIn("egg-eating-admission", case.missing_reply_facts(reply))

    def test_any_pattern_states_a_fact_and_matching_ignores_case(self) -> None:
        case = BenchmarkCase(
            case_id="facts", query="Question", chapter_max=5,
            expected_strength="sufficient", relevant_ranges=((5, 979, 981),),
            required_facts=(
                {"fact_id": "size", "patterns": [r"\bgrew\b", r"\bshrank\b"]},
                {"fact_id": "confusion", "patterns": [r"\bconfus\w+"]},
            ),
        )
        self.assertEqual((), case.missing_reply_facts("Alice SHRANK and was Confused."))
        self.assertEqual(("confusion",), case.missing_reply_facts("Alice grew."))
        self.assertEqual(0.5, case.reply_fact_recall("Alice grew."))
        self.assertEqual(("size", "confusion"), case.missing_reply_facts("Nothing here."))

    def test_cases_without_required_facts_have_no_reply_fact_grade(self) -> None:
        case = next(case for case in self.cases.cases if case.case_id == "father-william")
        self.assertEqual((), case.required_facts)
        self.assertEqual((), case.missing_reply_facts("Any reply at all."))
        self.assertIsNone(case.reply_fact_recall("Any reply at all."))

    def test_required_facts_reject_invalid_empty_and_duplicate_declarations(self) -> None:
        for facts in [
            ({"fact_id": "a", "patterns": ["(unclosed"]},),
            ({"fact_id": "a", "patterns": []},),
            ({"fact_id": "a", "patterns": [""]},),
            ({"fact_id": "", "patterns": ["x"]},),
            ({"fact_id": "a", "patterns": ["x"]}, {"fact_id": "a", "patterns": ["y"]}),
        ]:
            with self.subTest(facts=facts), self.assertRaises(ValueError):
                BenchmarkCase(
                    case_id="invalid-facts", query="Question", chapter_max=5,
                    expected_strength="sufficient", relevant_ranges=((5, 966, 981),),
                    required_facts=facts,
                )

    def test_identity_theme_optional_or_unrelated_passages_cannot_replace_dialogue(self) -> None:
        case = next(case for case in self.cases.cases if case.case_id == "identity-theme")
        for gold in [(2, 327, 360), (4, 762, 770), (5, 1040, 1050)]:
            with self.subTest(passage=gold):
                measured = measure(case, [self.canonical_hit(*gold)], self.source_lines)
                self.assertEqual(0.0, measured.recall)

    def test_identity_theme_still_penalizes_irrelevance_and_spoiler_overflow(self) -> None:
        case = next(case for case in self.cases.cases if case.case_id == "identity-theme")
        hits = [self.canonical_hit(5, 966, 981), self.canonical_hit(3, 553, 560)]
        measured = measure(case, hits, self.source_lines)
        self.assertEqual(0.5, measured.precision)
        self.assertFalse(measured.forbidden_exposure)
        future = self.canonical_hit(6, 1370, 1380)
        self.assertTrue(measure(case, hits + [future], self.source_lines).forbidden_exposure)

    def canonical_hit(self, chapter: int, start: int, end: int) -> Hit:
        return Hit("canonical-test", chapter, (start, end), "\n".join(self.source_lines[start - 1:end]), 1.0)

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
