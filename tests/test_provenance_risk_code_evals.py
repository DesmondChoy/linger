"""Tests for the Provenance candidate-gate risk-code evaluation."""

import unittest

from pydantic import ValidationError

from evals.provenance._fixtures import build_case_set
from evals.provenance.risk_codes import (
    FLOW_421_CODES,
    REQUIRED_BEHAVIORS,
    RiskCodeCaseSet,
    grade_review,
    load_risk_code_cases,
    run_evaluation,
)
from src.linger.agents.provenance.models import (
    ProvenanceReview,
    RiskFinding,
    TextSpanLocation,
)


def review(
    decision: str, *codes: str, case=None, source_field="candidate.response"
) -> ProvenanceReview:
    """Build a review whose findings resolve against the case being graded."""
    findings = []
    for code in codes:
        text = case.review_input.candidate.response if case else ""
        findings.append(
            RiskFinding(
                code=code,
                applies_to="response",
                location=TextSpanLocation(
                    kind="text_span",
                    source_field=source_field,
                    path="",
                    start_codepoint=0,
                    end_codepoint=len(text[:20]),
                    quote=text[:20],
                ),
                explanation=f"detected {code}",
            )
        )
    return ProvenanceReview(
        findings=tuple(findings),
        response_decision=decision,
        emotional_boundary_decision="not_required",
        capture_decision="no_candidate",
    )


class RiskCodeCaseSetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.case_set = load_risk_code_cases()
        cls.by_behavior = {case.primary_behavior: case for case in cls.case_set.cases}

    def test_loads_complete_versioned_gate_baseline(self) -> None:
        self.assertEqual("provenance-risk-codes-v1", self.case_set.case_set_id)
        self.assertEqual("4.2.1", self.case_set.flow)
        self.assertEqual(12, len(self.case_set.cases))
        self.assertEqual(REQUIRED_BEHAVIORS, set(self.by_behavior))
        self.assertEqual(5, len(self.case_set.positives))
        self.assertEqual(7, len(self.case_set.negatives))

    def test_every_flow_421_code_has_a_positive_and_a_paired_negative(self) -> None:
        for code in FLOW_421_CODES:
            positive = self.by_behavior[f"{code}_positive"]
            self.assertIn(code, positive.expected_codes)
            self.assertNotEqual("pass", positive.expected_response_decision)
            negative = self.by_behavior[f"{code}_negative"]
            self.assertEqual("pass", negative.expected_response_decision)
            self.assertEqual((), negative.expected_codes)

    def test_committed_cases_match_the_current_corpus(self) -> None:
        """The checked-in JSON must stay resolvable against real corpus text."""
        self.assertEqual(
            build_case_set(), self.case_set.model_dump(mode="json")
        )

    def test_case_contract_rejects_a_positive_expecting_a_pass(self) -> None:
        raw = self.case_set.model_dump(mode="json")
        index = next(
            i
            for i, case in enumerate(raw["cases"])
            if case["primary_behavior"] == "spoiler_positive"
        )
        raw["cases"][index]["expected_response_decision"] = "pass"

        with self.assertRaisesRegex(ValidationError, "must not expect a pass"):
            RiskCodeCaseSet.model_validate(raw)

    def test_case_contract_rejects_a_negative_expecting_codes(self) -> None:
        raw = self.case_set.model_dump(mode="json")
        index = next(
            i
            for i, case in enumerate(raw["cases"])
            if case["primary_behavior"] == "spoiler_negative"
        )
        raw["cases"][index]["expected_codes"] = ["spoiler"]

        with self.assertRaisesRegex(ValidationError, "must expect no codes"):
            RiskCodeCaseSet.model_validate(raw)

    def test_case_set_rejects_missing_required_behavior(self) -> None:
        raw = self.case_set.model_dump(mode="json")
        raw["cases"] = raw["cases"][:-1]

        with self.assertRaises(ValidationError):
            RiskCodeCaseSet.model_validate(raw)


class RiskCodeGradingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.by_behavior = {
            case.primary_behavior: case for case in load_risk_code_cases().cases
        }

    def test_matching_decision_and_code_passes(self) -> None:
        case = self.by_behavior["spoiler_positive"]
        grade = grade_review(case, review("reject", "spoiler", case=case))
        self.assertTrue(grade.passed)
        self.assertEqual(("spoiler",), grade.actual_codes)

    def test_wrong_decision_is_a_decision_mismatch(self) -> None:
        case = self.by_behavior["spoiler_positive"]
        grade = grade_review(case, review("pass", case=case))
        self.assertFalse(grade.passed)
        self.assertEqual("decision_mismatch", grade.failure_code)

    def test_right_decision_with_wrong_code_is_a_code_mismatch(self) -> None:
        """The blind spot this pack exists to close."""
        case = self.by_behavior["spoiler_positive"]
        grade = grade_review(case, review("reject", "unsupported_claim", case=case))
        self.assertFalse(grade.passed)
        self.assertEqual("code_mismatch", grade.failure_code)
        self.assertEqual(("unsupported_claim",), grade.actual_codes)

    def test_extra_correct_findings_still_pass(self) -> None:
        case = self.by_behavior["spoiler_positive"]
        grade = grade_review(
            case, review("reject", "spoiler", "unsupported_claim", case=case)
        )
        self.assertTrue(grade.passed)

    def test_unresolvable_finding_location_is_invalid(self) -> None:
        case = self.by_behavior["spoiler_positive"]
        unresolvable = ProvenanceReview(
            findings=(
                RiskFinding(
                    code="spoiler",
                    applies_to="response",
                    location=TextSpanLocation(
                        kind="text_span",
                        source_field="candidate.response",
                        path="",
                        start_codepoint=0,
                        end_codepoint=8,
                        quote="not here",
                    ),
                    explanation="offsets do not match the candidate",
                ),
            ),
            response_decision="reject",
            emotional_boundary_decision="not_required",
            capture_decision="no_candidate",
        )
        grade = grade_review(case, unresolvable)
        self.assertFalse(grade.passed)
        self.assertEqual("invalid_review", grade.failure_code)

    def test_malformed_output_fails_closed(self) -> None:
        case = self.by_behavior["spoiler_positive"]
        grade = grade_review(case, {"response_decision": "maybe"})
        self.assertFalse(grade.passed)
        self.assertIsNone(grade.actual_decision)
        self.assertEqual("invalid_review", grade.failure_code)


class RiskCodeEvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_expected_labels_pass_and_report_holds_metadata_only(self) -> None:
        case_set = load_risk_code_cases()

        async def gate(case):
            return review(
                case.expected_response_decision, *case.expected_codes, case=case
            )

        report = await run_evaluation(
            gate=gate, case_set=case_set, model_name="test:exact-label-gate"
        )

        self.assertTrue(report.summary.targets_pass)
        self.assertEqual(1.0, report.summary.accuracy)
        self.assertEqual(1.0, report.summary.block_recall)
        self.assertEqual(0.0, report.summary.over_refusal_rate)
        self.assertEqual(1.0, report.summary.code_precision)
        self.assertEqual(
            FLOW_421_CODES, {item.code for item in report.summary.per_code_result}
        )
        self.assertTrue(
            all(item.blocked and item.labelled for item in report.summary.per_code_result)
        )

        serialized = report.model_dump_json()
        self.assertNotIn("review_input", serialized)
        self.assertNotIn("description", serialized)
        for case in case_set.cases:
            self.assertNotIn(case.review_input.candidate.response, serialized)
            self.assertNotIn(case.review_input.current_line.text, serialized)

    async def test_permissive_gate_measures_missed_blocks(self) -> None:
        async def permissive_gate(case):
            return review("pass", case=case)

        report = await run_evaluation(gate=permissive_gate)

        self.assertFalse(report.summary.targets_pass)
        self.assertEqual(0.0, report.summary.block_recall)
        self.assertEqual(0.0, report.summary.over_refusal_rate)
        self.assertTrue(
            all(not item.blocked for item in report.summary.per_code_result)
        )

    async def test_blanket_blocking_gate_is_caught_by_over_refusal(self) -> None:
        """Blocking everything earns full recall, so over-refusal must expose it."""

        async def blocking_gate(case):
            return review("reject", *FLOW_421_CODES, case=case)

        report = await run_evaluation(gate=blocking_gate)

        self.assertFalse(report.summary.targets_pass)
        self.assertEqual(1.0, report.summary.block_recall)
        self.assertEqual(1.0, report.summary.over_refusal_rate)

    async def test_mislabelling_gate_is_caught_by_code_precision(self) -> None:
        """Right decisions with wrong codes must not reach a passing report."""

        async def mislabelling_gate(case):
            codes = ("unsupported_claim",) if case.expected_codes else ()
            return review(case.expected_response_decision, *codes, case=case)

        report = await run_evaluation(gate=mislabelling_gate)

        self.assertFalse(report.summary.targets_pass)
        self.assertEqual(1.0, report.summary.block_recall)
        self.assertEqual(0.2, report.summary.code_precision)

    async def test_gate_errors_are_redacted_and_fail_the_target(self) -> None:
        async def broken_gate(_case):
            raise RuntimeError("provider failure containing evaluated content")

        report = await run_evaluation(gate=broken_gate)

        self.assertFalse(report.summary.targets_pass)
        self.assertEqual(12, report.summary.evaluation_error_count)
        self.assertTrue(all(case.failure_code == "gate_error" for case in report.cases))
        self.assertNotIn("provider failure", report.model_dump_json())


if __name__ == "__main__":
    unittest.main()
