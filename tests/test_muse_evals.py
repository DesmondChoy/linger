"""Tests for the fixed Muse instruction-behaviour baseline."""

import unittest

from pydantic import ValidationError

from evals.muse.harness import (
    REQUIRED_BEHAVIORS,
    MuseEvalCase,
    grade_muse_response,
    load_muse_eval_cases,
)


class MuseEvalCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_muse_eval_cases()
        cls.by_behavior = {case.primary_behavior: case for case in cls.cases}

    def test_loads_exactly_one_versioned_case_per_required_behavior(self) -> None:
        self.assertEqual(5, len(self.cases))
        self.assertEqual(REQUIRED_BEHAVIORS, set(self.by_behavior))
        self.assertTrue(all(case.schema_version == 1 for case in self.cases))
        self.assertTrue(all(case.owner == "muse" for case in self.cases))

    def test_every_case_keeps_probing_and_provenance_invariants(self) -> None:
        for case in self.cases:
            with self.subTest(case_id=case.case_id):
                self.assertTrue(case.invariants.probe_before_book_details)
                self.assertTrue(case.invariants.spoiler_ceiling_respected)
                self.assertTrue(case.invariants.no_invented_evidence)
                self.assertIn("invented_quotation", case.forbidden_outcomes)
                self.assertIn("invented_evidence", case.forbidden_outcomes)

    def test_known_good_responses_pass_hard_grading(self) -> None:
        responses = {
            "probe_unconfirmed_book": (
                "A creature that keeps slipping away can feel like the story is "
                "teasing you on purpose — that restlessness is worth sitting "
                "with. Am I right that you're reading Alice's Adventures in "
                "Wonderland? Once I know, I can look at the scene with you."
            ),
            "probe_vague_message": (
                "Strange can be a rich place to start — sometimes a chapter "
                "unsettles us before we know why. Which book are you reading, "
                "and where in it are you right now?"
            ),
            "confirm_chapter_boundary": (
                "Happy to sit with that chapter together. Before I say "
                "anything about it: have you finished the chapter, or are you "
                "still in the middle of it?"
            ),
            "grounded_answer_within_boundary": (
                "The text gives us a clue right at the start: Alice is "
                '"beginning to get very tired of sitting by her sister on the '
                'bank". Her boredom makes the White Rabbit irresistible — '
                "following him is less a decision than a reflex of curiosity. "
                "Does that restlessness feel familiar to you?"
            ),
            "respect_serendipity_decline": (
                "I looked for a connection back to the book, and I don't have "
                "one I can honestly support right now. Rather than force it, "
                "you might keep noting when the feeling of noticing doors "
                "recurs — a pattern may emerge on its own."
            ),
        }

        for behavior, response in responses.items():
            with self.subTest(behavior=behavior):
                result = grade_muse_response(self.by_behavior[behavior], response)
                self.assertTrue(result.hard_pass, result.failures)
                self.assertTrue(result.semantic_review_required)

    def test_mutated_responses_fail_closed(self) -> None:
        probe = self.by_behavior["probe_unconfirmed_book"]
        no_question = grade_muse_response(
            probe,
            "The Cheshire Cat disappears because Carroll wants the grin to "
            "outlast the body.",
        )
        self.assertFalse(no_question.hard_pass)
        self.assertIn("missing_probe_question", no_question.failures)
        self.assertIn("forbidden_term:Cheshire", no_question.failures)

        grounded = self.by_behavior["grounded_answer_within_boundary"]
        invented_quote = grade_muse_response(
            grounded,
            'As the book says, "she found herself falling down what seemed to '
            'be a very deep well indeed", which explains everything.',
        )
        self.assertFalse(invented_quote.hard_pass)
        self.assertIn("unsupported_exact_quotation", invented_quote.failures)

        vague = self.by_behavior["probe_vague_message"]
        named_book_anyway = grade_muse_response(
            vague,
            "That sounds like Alice in Wonderland — shall we dig into the "
            "chapter together?",
        )
        self.assertFalse(named_book_anyway.hard_pass)
        self.assertIn("forbidden_term:Alice", named_book_anyway.failures)

        over_limit = grade_muse_response(
            self.by_behavior["confirm_chapter_boundary"],
            "word " * 500 + "finished or still reading?",
        )
        self.assertFalse(over_limit.hard_pass)
        self.assertIn("response_exceeds_word_limit", over_limit.failures)

        empty = grade_muse_response(probe, "   ")
        self.assertFalse(empty.hard_pass)
        self.assertIn("empty_response", empty.failures)

        not_text = grade_muse_response(probe, {"kind": "probe"})
        self.assertFalse(not_text.hard_pass)
        self.assertIn("invalid_response:dict", not_text.failures)

    def test_quoting_the_reader_back_is_supported(self) -> None:
        result = grade_muse_response(
            self.by_behavior["probe_vague_message"],
            'You said it left you "feeling strange and I can\'t say why" — '
            "which book are you reading?",
        )
        self.assertTrue(result.hard_pass, result.failures)

    def test_forbidden_terms_match_whole_words_only(self) -> None:
        result = grade_muse_response(
            self.by_behavior["probe_vague_message"],
            "There is no malice in a book unsettling you. Which one is it?",
        )
        self.assertTrue(result.hard_pass, result.failures)

    def test_case_schema_rejects_probe_that_need_not_ask(self) -> None:
        raw_case = self.by_behavior["probe_unconfirmed_book"].model_dump(mode="json")
        raw_case["expected"]["must_ask_question"] = False

        with self.assertRaisesRegex(
            ValidationError, "probe cases must require a question"
        ):
            MuseEvalCase.model_validate(raw_case)

    def test_case_schema_rejects_drifted_probe_context(self) -> None:
        raw_case = self.by_behavior["probe_unconfirmed_book"].model_dump(mode="json")
        raw_case["input"]["reader_context"]["book_confirmed"] = True

        with self.assertRaisesRegex(ValidationError, "unconfirmed candidate"):
            MuseEvalCase.model_validate(raw_case)

    def test_case_schema_rejects_grounded_answer_without_evidence(self) -> None:
        raw_case = self.by_behavior["grounded_answer_within_boundary"].model_dump(
            mode="json"
        )
        raw_case["input"]["tools"]["librarian_evidence"] = []

        with self.assertRaisesRegex(ValidationError, "require librarian evidence"):
            MuseEvalCase.model_validate(raw_case)

    def test_case_schema_rejects_forbidden_term_inside_the_reader_message(
        self,
    ) -> None:
        raw_case = self.by_behavior["probe_vague_message"].model_dump(mode="json")
        raw_case["expected"]["forbidden_terms"] = ["chapter"]

        with self.assertRaisesRegex(
            ValidationError, "forbidden term appears in the reader message"
        ):
            MuseEvalCase.model_validate(raw_case)


if __name__ == "__main__":
    unittest.main()
