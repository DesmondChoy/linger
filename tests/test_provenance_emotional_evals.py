"""Tests for the Provenance emotional-boundary semantic evaluation."""

import unittest

from pydantic import ValidationError

from evals.provenance.emotional_boundary import (
    REQUIRED_BEHAVIORS,
    EmotionalBoundaryCaseSet,
    grade_emotional_boundary_decision,
    load_emotional_boundary_cases,
    run_evaluation,
)
from src.linger.contracts.emotional import EmotionalBoundaryAssessment


class EmotionalBoundaryEvalCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.case_set = load_emotional_boundary_cases()
        cls.by_behavior = {
            case.primary_behavior: case for case in cls.case_set.cases
        }

    def test_loads_complete_versioned_semantic_baseline(self) -> None:
        self.assertEqual("provenance-emotional-boundary-v1", self.case_set.case_set_id)
        self.assertEqual(1, self.case_set.schema_version)
        self.assertEqual(8, len(self.case_set.cases))
        self.assertEqual(REQUIRED_BEHAVIORS, set(self.by_behavior))
        self.assertTrue(all(case.schema_version == 1 for case in self.case_set.cases))
        self.assertTrue(all(case.owner == "provenance" for case in self.case_set.cases))

    def test_baseline_covers_policy_boundaries_and_instruction_attacks(self) -> None:
        expected = {
            "clear_first_person_distress": "apply_boundary",
            "inability_to_cope": "apply_boundary",
            "ordinary_frustration": "continue_reflection",
            "literary_content": "continue_reflection",
            "quoted_content": "continue_reflection",
            "third_person_concern": "continue_reflection",
            "embedded_instruction_negative": "continue_reflection",
            "embedded_instruction_positive": "apply_boundary",
        }
        self.assertEqual(
            expected,
            {
                behavior: case.expected_decision
                for behavior, case in self.by_behavior.items()
            },
        )

    def test_case_contract_rejects_inverted_expected_decision(self) -> None:
        raw = self.case_set.model_dump(mode="json")
        raw["cases"][0]["expected_decision"] = "continue_reflection"

        with self.assertRaisesRegex(ValidationError, "must expect decision"):
            EmotionalBoundaryCaseSet.model_validate(raw)

    def test_case_set_rejects_missing_required_behavior(self) -> None:
        raw = self.case_set.model_dump(mode="json")
        raw["cases"] = raw["cases"][:-1]

        with self.assertRaises(ValidationError):
            EmotionalBoundaryCaseSet.model_validate(raw)

    def test_grading_is_exact_and_fails_closed(self) -> None:
        positive = self.by_behavior["clear_first_person_distress"]
        self.assertTrue(
            grade_emotional_boundary_decision(
                positive,
                EmotionalBoundaryAssessment(decision="apply_boundary"),
            ).passed
        )

        mismatch = grade_emotional_boundary_decision(
            positive,
            EmotionalBoundaryAssessment(decision="continue_reflection"),
        )
        self.assertFalse(mismatch.passed)
        self.assertEqual("decision_mismatch", mismatch.failure_code)

        invalid = grade_emotional_boundary_decision(positive, {"decision": "maybe"})
        self.assertFalse(invalid.passed)
        self.assertIsNone(invalid.actual_decision)
        self.assertEqual("invalid_assessment", invalid.failure_code)


class EmotionalBoundaryEvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_known_labels_pass_and_report_contains_metadata_only(self) -> None:
        case_set = load_emotional_boundary_cases()
        decisions = {
            case.current_line: case.expected_decision for case in case_set.cases
        }

        async def classifier(current_line: str) -> EmotionalBoundaryAssessment:
            return EmotionalBoundaryAssessment(decision=decisions[current_line])

        report = await run_evaluation(
            classifier=classifier,
            case_set=case_set,
            model_name="test:exact-label-classifier",
        )

        self.assertTrue(report.summary.targets_pass)
        self.assertEqual(1.0, report.summary.accuracy)
        self.assertEqual(0, report.summary.false_negative_count)
        self.assertEqual(0, report.summary.false_positive_count)
        self.assertEqual(0.0, report.summary.boundary_miss_rate)
        self.assertEqual(0.0, report.summary.over_refusal_rate)

        serialized = report.model_dump_json()
        self.assertNotIn("current_line", serialized)
        self.assertNotIn("description", serialized)
        for case in case_set.cases:
            self.assertNotIn(case.current_line, serialized)
        self.assertEqual(
            {
                "case_id",
                "primary_behavior",
                "expected_decision",
                "actual_decision",
                "passed",
                "failure_code",
                "error_type",
                "latency_ms",
            },
            set(report.cases[0].model_dump()),
        )

    async def test_mismatches_measure_safety_misses_and_over_refusal(self) -> None:
        case_set = load_emotional_boundary_cases()

        async def inverted_classifier(current_line: str) -> EmotionalBoundaryAssessment:
            case = next(
                case for case in case_set.cases if case.current_line == current_line
            )
            decision = (
                "continue_reflection"
                if case.expected_decision == "apply_boundary"
                else "apply_boundary"
            )
            return EmotionalBoundaryAssessment(decision=decision)

        report = await run_evaluation(
            classifier=inverted_classifier,
            case_set=case_set,
        )

        self.assertFalse(report.summary.targets_pass)
        self.assertEqual(0.0, report.summary.accuracy)
        self.assertEqual(3, report.summary.false_negative_count)
        self.assertEqual(5, report.summary.false_positive_count)
        self.assertEqual(1.0, report.summary.boundary_miss_rate)
        self.assertEqual(1.0, report.summary.over_refusal_rate)

    async def test_classifier_errors_are_redacted_and_fail_the_target(self) -> None:
        async def broken_classifier(_current_line: str) -> object:
            raise RuntimeError("provider failure containing evaluated content")

        report = await run_evaluation(classifier=broken_classifier)

        self.assertFalse(report.summary.targets_pass)
        self.assertEqual(8, report.summary.evaluation_error_count)
        self.assertTrue(
            all(case.failure_code == "classifier_error" for case in report.cases)
        )
        self.assertTrue(all(case.error_type == "RuntimeError" for case in report.cases))
        self.assertNotIn("provider failure", report.model_dump_json())


if __name__ == "__main__":
    unittest.main()
