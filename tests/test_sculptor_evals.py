"""Tests for the fixed Sculptor memory-curation baseline."""

import unittest

from pydantic import ValidationError

from evals.sculptor.harness import (
    REQUIRED_BEHAVIORS,
    SculptorEvalCase,
    grade_sculptor_response,
    load_sculptor_eval_cases,
)


class SculptorEvalCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_sculptor_eval_cases()
        cls.by_behavior = {case.primary_behavior: case for case in cls.cases}

    def test_loads_exactly_one_versioned_case_per_required_behavior(self) -> None:
        self.assertEqual(5, len(self.cases))
        self.assertEqual(REQUIRED_BEHAVIORS, set(self.by_behavior))
        self.assertTrue(all(case.schema_version == 1 for case in self.cases))
        self.assertTrue(all(case.owner == "sculptor" for case in self.cases))

    def test_every_case_preserves_originals_and_provenance(self) -> None:
        for case in self.cases:
            with self.subTest(case_id=case.case_id):
                self.assertTrue(case.invariants.originals_immutable)
                self.assertTrue(case.invariants.provenance_required)
                self.assertTrue(case.invariants.no_storage_authority)
                self.assertIn("delete_original", case.forbidden_outcomes)
                self.assertIn("rewrite_original", case.forbidden_outcomes)
                self.assertIn("reference_unknown_memory", case.forbidden_outcomes)

    def test_known_good_responses_pass_hard_grading(self) -> None:
        responses = {
            "exact_duplicate": {
                "kind": "curation_proposal",
                "action": {
                    "action": "link_duplicates",
                    "source_memory_ids": [
                        "mem-exact-bedtime-2",
                        "mem-exact-bedtime-1",
                    ],
                },
            },
            "paraphrased_duplicate": {
                "kind": "curation_proposal",
                "action": {
                    "action": "link_duplicates",
                    "source_memory_ids": ["mem-sketching-1", "mem-sketching-2"],
                },
            },
            "noisy_memory_summary": {
                "kind": "curation_proposal",
                "action": {
                    "action": "update_derived_summary",
                    "source_memory_ids": [
                        "mem-walk-fragment-1",
                        "mem-walk-fragment-2",
                        "mem-walk-fragment-3",
                    ],
                    "summary": (
                        "Walks after work, sometimes in rain and without headphones, "
                        "can help the user feel calmer and mentally clearer."
                    ),
                },
            },
            "related_topic_group": {
                "kind": "curation_proposal",
                "action": {
                    "action": "assign_topic_group",
                    "source_memory_ids": [
                        "mem-unwind-walk",
                        "mem-unwind-fiction",
                        "mem-unwind-tea",
                    ],
                    "topic_label": "Restorative transitions",
                },
            },
            "superficial_similarity_no_change": {
                "kind": "no_curation_proposal",
                "reason": "The shared words refer to unrelated people and contexts.",
            },
        }

        for behavior, response in responses.items():
            with self.subTest(behavior=behavior):
                result = grade_sculptor_response(self.by_behavior[behavior], response)
                self.assertTrue(result.hard_pass, result.failures)

        self.assertTrue(
            grade_sculptor_response(
                self.by_behavior["noisy_memory_summary"],
                responses["noisy_memory_summary"],
            ).semantic_review_required
        )
        self.assertTrue(
            grade_sculptor_response(
                self.by_behavior["related_topic_group"],
                responses["related_topic_group"],
            ).semantic_review_required
        )

    def test_mutated_responses_fail_closed(self) -> None:
        exact = self.by_behavior["exact_duplicate"]
        unknown_source = grade_sculptor_response(
            exact,
            {
                "kind": "curation_proposal",
                "action": {
                    "action": "link_duplicates",
                    "source_memory_ids": ["mem-exact-bedtime-1", "invented-memory"],
                },
            },
        )
        self.assertFalse(unknown_source.hard_pass)
        self.assertIn("source_memory_ids_mismatch", unknown_source.failures)
        self.assertIn("unknown_source_memory_id", unknown_source.failures)

        attempted_delete = grade_sculptor_response(
            exact,
            {
                "kind": "curation_proposal",
                "action": {
                    "action": "link_duplicates",
                    "source_memory_ids": [
                        "mem-exact-bedtime-1",
                        "mem-exact-bedtime-2",
                    ],
                    "deleted_memory_ids": ["mem-exact-bedtime-2"],
                },
            },
        )
        self.assertFalse(attempted_delete.hard_pass)
        self.assertTrue(attempted_delete.failures[0].startswith("invalid_response:"))

        false_merge = grade_sculptor_response(
            self.by_behavior["superficial_similarity_no_change"],
            {
                "kind": "curation_proposal",
                "action": {
                    "action": "link_duplicates",
                    "source_memory_ids": [
                        "mem-alice-book-identity",
                        "mem-alice-database-identity",
                    ],
                },
            },
        )
        self.assertFalse(false_merge.hard_pass)
        self.assertIn("expected_no_curation_proposal", false_merge.failures)

    def test_case_schema_rejects_unknown_expected_source(self) -> None:
        raw_case = self.by_behavior["exact_duplicate"].model_dump(mode="json")
        raw_case["expected"]["action"]["source_memory_ids"][1] = "invented-memory"

        with self.assertRaisesRegex(
            ValidationError, "expected source memory IDs are outside the input"
        ):
            SculptorEvalCase.model_validate(raw_case)


if __name__ == "__main__":
    unittest.main()
