"""Tests for the single Provenance review call and its two decisions."""

import unittest
from typing import get_args
from unittest.mock import patch

from pydantic import ValidationError
from pydantic_ai.models.test import TestModel

from src.linger.agents.provenance.models import (
    SENSITIVE_RISK_CODES,
    ProvenanceReview,
    RiskCode,
    RiskFinding,
)

SPEC_RISK_CODES = (
    "unresolved_evidence",
    "misattribution",
    "spoiler",
    "boundary_violation",
    "uncited_web_claim",
    "unsupported_claim",
    "prompt_injection",
)


def finding(code: str) -> RiskFinding:
    return RiskFinding(code=code, quote="offending span", explanation="why")


class RiskTaxonomyTests(unittest.TestCase):
    def test_covers_every_specification_block_condition(self) -> None:
        """Section 6.5 names seven grounds; the taxonomy carries all of them."""
        self.assertEqual(set(SPEC_RISK_CODES), set(get_args(RiskCode)))

    def test_sensitive_codes_are_part_of_the_taxonomy(self) -> None:
        self.assertTrue(SENSITIVE_RISK_CODES.issubset(set(get_args(RiskCode))))


class ProvenanceReviewTests(unittest.TestCase):
    def test_clean_pass_needs_no_findings(self) -> None:
        review = ProvenanceReview(
            response_decision="pass",
            capture_decision="no_candidate",
        )
        self.assertEqual((), review.findings)
        self.assertFalse(review.contains_sensitive_content)

    def test_every_risk_code_is_accepted(self) -> None:
        for code in SPEC_RISK_CODES:
            with self.subTest(code=code):
                review = ProvenanceReview(
                    findings=(finding(code),),
                    response_decision="reject",
                    capture_decision="reject_capture",
                )
                self.assertEqual(code, review.findings[0].code)

    def test_rejecting_a_response_requires_a_named_ground(self) -> None:
        for decision in ("revise", "reject"):
            with self.subTest(decision=decision):
                with self.assertRaises(ValidationError):
                    ProvenanceReview(
                        response_decision=decision,
                        capture_decision="no_candidate",
                    )

    def test_rejecting_capture_requires_a_named_ground(self) -> None:
        with self.assertRaises(ValidationError):
            ProvenanceReview(
                response_decision="pass",
                capture_decision="reject_capture",
            )

    def test_decisions_are_independent(self) -> None:
        """Section 4.1: rejecting capture must not suppress a safe response."""
        review = ProvenanceReview(
            findings=(finding("unsupported_claim"),),
            response_decision="pass",
            capture_decision="reject_capture",
        )
        self.assertEqual("pass", review.response_decision)
        self.assertEqual("reject_capture", review.capture_decision)

    def test_sensitivity_is_derived_from_findings(self) -> None:
        sensitive = ProvenanceReview(
            findings=(finding("unsupported_claim"),),
            response_decision="pass",
            capture_decision="reject_capture",
        )
        self.assertTrue(sensitive.contains_sensitive_content)

        non_sensitive = ProvenanceReview(
            findings=(finding("spoiler"),),
            response_decision="revise",
            capture_decision="no_candidate",
        )
        self.assertFalse(non_sensitive.contains_sensitive_content)

    def test_critique_names_each_ground(self) -> None:
        review = ProvenanceReview(
            findings=(finding("spoiler"), finding("misattribution")),
            response_decision="revise",
            capture_decision="no_candidate",
        )
        critique = review.critique()
        self.assertIn("spoiler", critique)
        self.assertIn("misattribution", critique)

    def test_schema_drift_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ProvenanceReview(
                response_decision="pass",
                capture_decision="no_candidate",
                unexpected_field="x",
            )


class ProvenanceAgentTests(unittest.TestCase):
    def test_review_round_trips_through_the_agent(self) -> None:
        with patch("src.linger.agents.build.build_model", return_value=TestModel()):
            from src.linger.agents.provenance.agent import build_provenance_agent

        model = TestModel(
            custom_output_args={
                "findings": [
                    {
                        "code": "prompt_injection",
                        "quote": "ignore previous instructions",
                        "explanation": "The passage redirects agent behaviour.",
                    }
                ],
                "response_decision": "reject",
                "capture_decision": "reject_capture",
            }
        )
        agent = build_provenance_agent(model)
        review = agent.run_sync("candidate").output

        self.assertIsInstance(review, ProvenanceReview)
        self.assertEqual("prompt_injection", review.findings[0].code)
        self.assertEqual("reject", review.response_decision)

    def test_provenance_has_no_tools(self) -> None:
        """Section 3.3: Provenance reviews without any tool authority."""
        with patch("src.linger.agents.build.build_model", return_value=TestModel()):
            from src.linger.agents.provenance.agent import build_provenance_agent

        model = TestModel(
            custom_output_args={
                "findings": [],
                "response_decision": "pass",
                "capture_decision": "no_candidate",
            }
        )
        agent = build_provenance_agent(model)
        agent.run_sync("candidate")

        self.assertEqual([], model.last_model_request_parameters.function_tools)
