"""Tests for the Provenance candidate-gate risk-code evaluation."""

import unittest

from pydantic import ValidationError

from evals.provenance._fixtures import build_case_set
from evals.provenance.risk_codes import (
    CAPTURE_BEHAVIORS,
    FLOW_421_CODES,
    FLOW_422_CODES,
    REQUIRED_BEHAVIORS,
    RiskCodeCaseSet,
    grade_review,
    load_risk_code_cases,
    run_evaluation,
)
from src.linger.agents.provenance.models import (
    ProvenanceReview,
    RiskFinding,
    StructuralLocation,
    TextSpanLocation,
)


def review(
    decision: str,
    *codes: str,
    case=None,
    source_field="candidate.response",
    capture_decision: str | None = None,
    capture_codes: tuple[str, ...] = (),
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
                    quote=text[:20],
                ),
                explanation=f"detected {code}",
            )
        )
    for code in capture_codes:
        findings.append(
            RiskFinding(
                code=code,
                applies_to="capture",
                # Structural, so the finding resolves without needing the
                # nominated span's exact wording.
                location=StructuralLocation(
                    kind="structural",
                    source_field="candidate.memory",
                    path="",
                ),
                explanation=f"detected {code} in the nomination",
            )
        )
    if capture_decision is None:
        capture_decision = (
            case.expected_capture_decision if case is not None else "no_candidate"
        )
    return ProvenanceReview(
        findings=tuple(findings),
        response_decision=decision,
        emotional_boundary_decision="not_required",
        capture_decision=capture_decision,
    )


def expected_review(case) -> ProvenanceReview:
    """Build the exactly-correct review for one case on all four axes."""
    return review(
        case.expected_response_decision,
        *case.expected_response_codes,
        case=case,
        capture_codes=tuple(case.expected_capture_codes),
    )


class RiskCodeCaseSetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.case_set = load_risk_code_cases()
        cls.by_behavior = {case.primary_behavior: case for case in cls.case_set.cases}

    def test_loads_complete_versioned_gate_baseline(self) -> None:
        self.assertEqual("provenance-risk-codes-v1", self.case_set.case_set_id)
        self.assertEqual("4.2.1", self.case_set.flow)
        self.assertEqual(24, len(self.case_set.cases))
        self.assertEqual(REQUIRED_BEHAVIORS, set(self.by_behavior))
        self.assertEqual(5, len(self.case_set.positives))
        self.assertEqual(7, len(self.case_set.negatives))
        self.assertEqual(5, len(self.case_set.capture_positives))
        self.assertEqual(6, len(self.case_set.capture_negatives))

    def test_every_flow_421_code_has_a_positive_and_a_paired_negative(self) -> None:
        for code in FLOW_421_CODES:
            positive = self.by_behavior[f"{code}_positive"]
            self.assertIn(code, positive.expected_response_codes)
            self.assertNotEqual("pass", positive.expected_response_decision)
            negative = self.by_behavior[f"{code}_negative"]
            self.assertEqual("pass", negative.expected_response_decision)
            self.assertEqual((), negative.expected_response_codes)

    def test_every_veto_code_has_a_positive_and_a_paired_negative(self) -> None:
        for code in FLOW_422_CODES:
            positive = self.by_behavior[f"capture_{code}_positive"]
            self.assertIn(code, positive.expected_capture_codes)
            self.assertEqual("reject_capture", positive.expected_capture_decision)
            negative = self.by_behavior[f"capture_{code}_negative"]
            self.assertEqual("allow_capture", negative.expected_capture_decision)
            self.assertEqual((), negative.expected_capture_codes)

    def test_capture_cases_can_actually_reach_a_capture_decision(self) -> None:
        """The blind spot the capture axis exists to close.

        Every 4.2.1 case forces `no_candidate` structurally, so a capture case
        that forgot either the policy flag or the nomination would measure
        nothing while appearing to pass.
        """
        for behavior in CAPTURE_BEHAVIORS - {"capture_no_candidate_with_capture_enabled"}:
            case = self.by_behavior[behavior]
            with self.subTest(behavior=behavior):
                self.assertTrue(
                    case.review_input.context.policy.allow_memory_capture
                )
                self.assertEqual(
                    "memory_candidate", case.review_input.candidate.memory.kind
                )

    def test_every_nomination_is_an_exact_slice_of_its_line(self) -> None:
        """`candidate_from_review` re-slices the Line and fails binding otherwise."""
        for case in self.case_set.cases:
            nomination = case.review_input.candidate.memory
            if nomination.kind != "memory_candidate":
                continue
            line = case.review_input.current_line.text
            with self.subTest(case=case.case_id):
                self.assertEqual(
                    nomination.text,
                    line[nomination.start_codepoint : nomination.end_codepoint],
                )

    def test_decoupling_cases_hold_one_decision_while_the_other_moves(self) -> None:
        vetoed = self.by_behavior["capture_decoupled_clean_response_vetoed_capture"]
        self.assertEqual("pass", vetoed.expected_response_decision)
        self.assertEqual("reject_capture", vetoed.expected_capture_decision)

        allowed = self.by_behavior["capture_decoupled_revised_response_allowed_capture"]
        self.assertEqual("revise", allowed.expected_response_decision)
        self.assertEqual("allow_capture", allowed.expected_capture_decision)

    def test_sensitive_content_is_derived_from_the_expected_capture_codes(self) -> None:
        self.assertTrue(
            self.by_behavior[
                "capture_sensitive_content_positive"
            ].expected_sensitive_content
        )
        self.assertFalse(
            self.by_behavior[
                "capture_sensitive_content_negative"
            ].expected_sensitive_content
        )

    def test_committed_cases_match_the_current_corpus(self) -> None:
        """The checked-in JSON must stay resolvable against real corpus text."""
        self.assertEqual(
            build_case_set(), self.case_set.model_dump(mode="json")
        )

    def test_case_contract_rejects_a_positive_expecting_a_pass(self) -> None:
        raw = self._mutate("spoiler_positive", expected_response_decision="pass")

        with self.assertRaisesRegex(
            ValidationError, "passed response cannot expect response codes"
        ):
            RiskCodeCaseSet.model_validate(raw)

    def test_case_contract_rejects_a_negative_expecting_codes(self) -> None:
        raw = self._mutate("spoiler_negative", expected_response_codes=["spoiler"])

        with self.assertRaisesRegex(ValidationError, "must expect no codes"):
            RiskCodeCaseSet.model_validate(raw)

    def test_case_contract_rejects_a_capture_negative_expecting_a_veto(self) -> None:
        raw = self._mutate(
            "capture_sensitive_content_negative",
            expected_capture_decision="reject_capture",
            expected_capture_codes=["sensitive_content"],
        )

        with self.assertRaisesRegex(ValidationError, "must expect no codes"):
            RiskCodeCaseSet.model_validate(raw)

    def test_case_contract_rejects_a_veto_without_a_capture_code(self) -> None:
        raw = self._mutate(
            "capture_sensitive_content_positive", expected_capture_codes=[]
        )

        with self.assertRaisesRegex(ValidationError, "must expect code"):
            RiskCodeCaseSet.model_validate(raw)

    def test_case_contract_rejects_capture_codes_without_a_veto(self) -> None:
        raw = self._mutate(
            "capture_allowed_durable_reflection",
            expected_capture_codes=["sensitive_content"],
        )

        with self.assertRaisesRegex(ValidationError, "require an expected reject"):
            RiskCodeCaseSet.model_validate(raw)

    def test_case_contract_rejects_a_capture_expectation_policy_forbids(self) -> None:
        """A case measuring nothing must fail the package, not the run."""
        raw = self.case_set.model_dump(mode="json")
        index = self._index("capture_sensitive_content_positive")
        raw["cases"][index]["review_input"]["context"]["policy"][
            "allow_memory_capture"
        ] = False

        with self.assertRaisesRegex(ValidationError, "requires allow_memory_capture"):
            RiskCodeCaseSet.model_validate(raw)

    def test_case_contract_rejects_no_candidate_alongside_a_nomination(self) -> None:
        raw = self._mutate(
            "capture_unsupported_claim_negative",
            expected_capture_decision="no_candidate",
        )

        with self.assertRaisesRegex(ValidationError, "cannot be expected of a nomination"):
            RiskCodeCaseSet.model_validate(raw)

    def _index(self, behavior: str) -> int:
        return next(
            i
            for i, case in enumerate(self.case_set.model_dump(mode="json")["cases"])
            if case["primary_behavior"] == behavior
        )

    def _mutate(self, behavior: str, **fields: object) -> dict:
        """Return the case set with one case's expectation fields replaced."""
        raw = self.case_set.model_dump(mode="json")
        raw["cases"][self._index(behavior)].update(fields)
        return raw

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

    def test_matching_capture_veto_and_code_passes(self) -> None:
        case = self.by_behavior["capture_sensitive_content_positive"]
        grade = grade_review(case, expected_review(case))
        self.assertTrue(grade.passed)
        self.assertEqual("reject_capture", grade.actual_capture_decision)
        self.assertEqual(("sensitive_content",), grade.actual_capture_codes)
        self.assertTrue(grade.actual_sensitive_content)

    def test_missed_capture_veto_is_a_capture_decision_mismatch(self) -> None:
        case = self.by_behavior["capture_sensitive_content_positive"]
        grade = grade_review(
            case, review("pass", case=case, capture_decision="allow_capture")
        )
        self.assertFalse(grade.passed)
        self.assertEqual("capture_decision_mismatch", grade.failure_code)

    def test_capture_veto_with_wrong_code_is_a_capture_code_mismatch(self) -> None:
        case = self.by_behavior["capture_sensitive_content_positive"]
        grade = grade_review(
            case,
            review(
                "pass",
                case=case,
                capture_decision="reject_capture",
                capture_codes=("unsupported_claim",),
            ),
        )
        self.assertFalse(grade.passed)
        self.assertEqual("capture_code_mismatch", grade.failure_code)

    def test_a_vetoed_capture_does_not_excuse_a_wrong_response(self) -> None:
        """The decoupling contract, graded from the response side."""
        case = self.by_behavior["capture_decoupled_clean_response_vetoed_capture"]
        grade = grade_review(
            case,
            review(
                "reject",
                "spoiler",
                case=case,
                capture_decision="reject_capture",
                capture_codes=tuple(case.expected_capture_codes),
            ),
        )
        self.assertFalse(grade.passed)
        self.assertEqual("decision_mismatch", grade.failure_code)

    def test_a_revised_response_does_not_excuse_a_wrong_capture(self) -> None:
        """The decoupling contract, graded from the capture side."""
        case = self.by_behavior["capture_decoupled_revised_response_allowed_capture"]
        grade = grade_review(
            case,
            review(
                "revise",
                *case.expected_response_codes,
                case=case,
                capture_decision="reject_capture",
                capture_codes=("sensitive_content",),
            ),
        )
        self.assertFalse(grade.passed)
        self.assertEqual("capture_decision_mismatch", grade.failure_code)

    def test_non_sensitive_veto_code_is_a_sensitive_content_mismatch(self) -> None:
        """A veto labelled outside `SENSITIVE_RISK_CODES` flips the policy flag.

        `contains_sensitive_content` is derived, not returned, so nothing else
        in the pack would notice the wrong deterministic outcome.
        """
        case = self.by_behavior["capture_sensitive_content_positive"]
        grade = grade_review(
            case,
            review(
                "pass",
                case=case,
                capture_decision="reject_capture",
                capture_codes=("sensitive_content", "spoiler"),
            ),
        )
        self.assertTrue(grade.passed)
        self.assertTrue(grade.actual_sensitive_content)

        allowed = self.by_behavior["capture_allowed_durable_reflection"]
        mislabelled = grade_review(
            allowed,
            review(
                "pass",
                case=allowed,
                capture_decision="reject_capture",
                capture_codes=("spoiler",),
            ),
        )
        self.assertFalse(mislabelled.passed)
        self.assertEqual("capture_decision_mismatch", mislabelled.failure_code)
        self.assertFalse(mislabelled.actual_sensitive_content)

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
                        quote="not here",
                    ),
                    explanation="the quote is absent from the candidate",
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
            return expected_review(case)

        report = await run_evaluation(
            gate=gate, case_set=case_set, model_name="test:exact-label-gate"
        )

        self.assertTrue(report.summary.targets_pass)
        self.assertEqual(1.0, report.summary.accuracy)
        self.assertEqual(1.0, report.summary.block_recall)
        self.assertEqual(0.0, report.summary.over_refusal_rate)
        self.assertEqual(1.0, report.summary.code_precision)
        self.assertEqual(1.0, report.summary.capture_veto_recall)
        self.assertEqual(0.0, report.summary.capture_over_refusal_rate)
        self.assertEqual(1.0, report.summary.capture_code_precision)
        self.assertEqual(1.0, report.summary.sensitive_content_accuracy)
        self.assertEqual(1.0, report.summary.decoupling_accuracy)
        self.assertEqual(
            FLOW_421_CODES, {item.code for item in report.summary.per_code_result}
        )
        self.assertEqual(
            FLOW_422_CODES,
            {item.code for item in report.summary.per_capture_code_result},
        )
        self.assertTrue(
            all(item.blocked and item.labelled for item in report.summary.per_code_result)
        )
        self.assertTrue(
            all(
                item.vetoed and item.labelled
                for item in report.summary.per_capture_code_result
            )
        )

        serialized = report.model_dump_json()
        self.assertNotIn("review_input", serialized)
        self.assertNotIn("description", serialized)
        for case in case_set.cases:
            self.assertNotIn(case.review_input.candidate.response, serialized)
            self.assertNotIn(case.review_input.current_line.text, serialized)

    async def test_permissive_gate_measures_missed_blocks(self) -> None:
        async def permissive_gate(case):
            capture = (
                "no_candidate"
                if case.review_input.candidate.memory.kind == "no_memory_candidate"
                else "allow_capture"
            )
            return review("pass", case=case, capture_decision=capture)

        report = await run_evaluation(gate=permissive_gate)

        self.assertFalse(report.summary.targets_pass)
        self.assertEqual(0.0, report.summary.block_recall)
        self.assertEqual(0.0, report.summary.over_refusal_rate)
        self.assertEqual(0.0, report.summary.capture_veto_recall)
        self.assertEqual(0.0, report.summary.capture_over_refusal_rate)
        self.assertTrue(
            all(not item.blocked for item in report.summary.per_code_result)
        )
        self.assertTrue(
            all(not item.vetoed for item in report.summary.per_capture_code_result)
        )

    async def test_blanket_blocking_gate_is_caught_by_over_refusal(self) -> None:
        """Blocking everything earns full recall, so over-refusal must expose it."""

        async def blocking_gate(case):
            capture = (
                "no_candidate"
                if case.review_input.candidate.memory.kind == "no_memory_candidate"
                else "reject_capture"
            )
            return review(
                "reject",
                *FLOW_421_CODES,
                case=case,
                capture_decision=capture,
                capture_codes=(
                    tuple(FLOW_422_CODES) if capture == "reject_capture" else ()
                ),
            )

        report = await run_evaluation(gate=blocking_gate)

        self.assertFalse(report.summary.targets_pass)
        self.assertEqual(1.0, report.summary.block_recall)
        self.assertEqual(1.0, report.summary.over_refusal_rate)
        self.assertEqual(1.0, report.summary.capture_veto_recall)
        self.assertEqual(1.0, report.summary.capture_over_refusal_rate)

    async def test_a_gate_that_couples_the_decisions_fails_decoupling(self) -> None:
        """The property no earlier test measured: a gate vetoing whenever it revises.

        Its release axis is perfect, so only the capture metrics can expose it.
        """

        async def coupling_gate(case):
            released = case.expected_response_decision == "pass"
            nominated = case.review_input.candidate.memory.kind == "memory_candidate"
            capture = "no_candidate"
            if nominated:
                capture = "allow_capture" if released else "reject_capture"
            return review(
                case.expected_response_decision,
                *case.expected_response_codes,
                case=case,
                capture_decision=capture,
                capture_codes=(
                    ("sensitive_content",) if capture == "reject_capture" else ()
                ),
            )

        report = await run_evaluation(gate=coupling_gate)

        self.assertFalse(report.summary.targets_pass)
        self.assertEqual(1.0, report.summary.block_recall)
        self.assertEqual(0.0, report.summary.over_refusal_rate)
        self.assertEqual(0.0, report.summary.decoupling_accuracy)

    async def test_mislabelling_gate_is_caught_by_code_precision(self) -> None:
        """Right decisions with wrong codes must not reach a passing report."""

        async def mislabelling_gate(case):
            codes = ("unsupported_claim",) if case.expected_response_codes else ()
            capture_codes = (
                ("unsupported_claim",)
                if case.expected_capture_decision == "reject_capture"
                else ()
            )
            return review(
                case.expected_response_decision,
                *codes,
                case=case,
                capture_codes=capture_codes,
            )

        report = await run_evaluation(gate=mislabelling_gate)

        self.assertFalse(report.summary.targets_pass)
        self.assertEqual(1.0, report.summary.block_recall)
        self.assertEqual(0.2, report.summary.code_precision)
        self.assertEqual(1.0, report.summary.capture_veto_recall)
        self.assertEqual(0.2, report.summary.capture_code_precision)

    async def test_gate_errors_are_redacted_and_fail_the_target(self) -> None:
        async def broken_gate(_case):
            raise RuntimeError("provider failure containing evaluated content")

        report = await run_evaluation(gate=broken_gate)

        self.assertFalse(report.summary.targets_pass)
        self.assertEqual(24, report.summary.evaluation_error_count)
        self.assertTrue(all(case.failure_code == "gate_error" for case in report.cases))
        self.assertNotIn("provider failure", report.model_dump_json())


if __name__ == "__main__":
    unittest.main()
