"""Tests for the single Provenance review call and its two decisions."""

import unittest
from typing import get_args
from unittest.mock import patch

from pydantic import ValidationError
from pydantic_ai.models.test import TestModel

from src.linger.agents.provenance.models import (
    CandidateUnderReview,
    CurrentLine,
    MAX_FINDINGS,
    SENSITIVE_RISK_CODES,
    ProvenanceContext,
    ProvenanceInput,
    ProvenancePolicy,
    ProvenanceReview,
    RiskCode,
    RiskFinding,
    StructuralLocation,
    TextSpanLocation,
)
from src.linger.agents.provenance.agent import build_provenance_agent
from src.linger.agents.provenance.prompt import INSTRUCTIONS
from src.linger.agents.muse.models import NoMemoryCandidate

SPEC_RISK_CODES = (
    "unresolved_evidence",
    "misattribution",
    "spoiler",
    "boundary_violation",
    "uncited_web_claim",
    "unsupported_claim",
    "sensitive_content",
    "emotional_policy_violation",
    "prompt_injection",
)


def finding(code: str, *, applies_to: str = "response") -> RiskFinding:
    source_field = (
        "candidate.response"
        if applies_to == "response"
        else "candidate.memory"
    )
    return RiskFinding(
        code=code,
        applies_to=applies_to,
        location=StructuralLocation(
            kind="structural",
            source_field=source_field,
            path="",
        ),
        explanation="why",
    )


def provenance_input(response: str = "offending span") -> ProvenanceInput:
    return ProvenanceInput(
        context=ProvenanceContext(
            policy=ProvenancePolicy(
                spoiler_ceiling=None,
                allow_retrieval=False,
                allow_connection=False,
                allow_memory_capture=False,
            ),
            reading_context=None,
        ),
        candidate=CandidateUnderReview(
            response=response,
            memory=NoMemoryCandidate(
                kind="no_memory_candidate",
                reason_code="transient_or_low_signal",
            ),
        ),
        current_line=CurrentLine(text="reader source"),
    )


class RiskTaxonomyTests(unittest.TestCase):
    def test_covers_every_specification_block_condition(self) -> None:
        """The specification and capture policy name this closed taxonomy."""
        self.assertEqual(set(SPEC_RISK_CODES), set(get_args(RiskCode)))

    def test_sensitive_codes_are_part_of_the_taxonomy(self) -> None:
        self.assertTrue(SENSITIVE_RISK_CODES.issubset(set(get_args(RiskCode))))


class ProvenanceReviewTests(unittest.TestCase):
    def test_emotional_boundary_disposition_is_required(self) -> None:
        with self.assertRaises(ValidationError):
            ProvenanceReview(
                response_decision="pass",
                capture_decision="no_candidate",
            )

    def test_clean_pass_needs_no_findings(self) -> None:
        review = ProvenanceReview(
            response_decision="pass",
            emotional_boundary_decision="not_required",
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
                    emotional_boundary_decision="not_required",
                    capture_decision="no_candidate",
                )
                self.assertEqual(code, review.findings[0].code)

    def test_rejecting_a_response_requires_a_named_ground(self) -> None:
        for decision in ("revise", "reject"):
            with self.subTest(decision=decision):
                with self.assertRaises(ValidationError):
                    ProvenanceReview(
                        response_decision=decision,
                        emotional_boundary_decision="not_required",
                        capture_decision="no_candidate",
                    )

    def test_rejecting_capture_requires_a_named_ground(self) -> None:
        with self.assertRaises(ValidationError):
            ProvenanceReview(
                response_decision="pass",
                emotional_boundary_decision="not_required",
                capture_decision="reject_capture",
            )

    def test_sensitive_finding_cannot_allow_capture(self) -> None:
        with self.assertRaises(ValidationError):
            ProvenanceReview(
                findings=(finding("sensitive_content", applies_to="capture"),),
                response_decision="pass",
                emotional_boundary_decision="not_required",
                capture_decision="allow_capture",
            )

    def test_decisions_are_independent(self) -> None:
        """Section 4.1: rejecting capture must not suppress a safe response."""
        review = ProvenanceReview(
            findings=(finding("unsupported_claim", applies_to="capture"),),
            response_decision="pass",
            emotional_boundary_decision="not_required",
            capture_decision="reject_capture",
        )
        self.assertEqual("pass", review.response_decision)
        self.assertEqual("reject_capture", review.capture_decision)

    def test_sensitivity_is_derived_from_findings(self) -> None:
        sensitive = ProvenanceReview(
            findings=(finding("unsupported_claim", applies_to="capture"),),
            response_decision="pass",
            emotional_boundary_decision="not_required",
            capture_decision="reject_capture",
        )
        self.assertTrue(sensitive.contains_sensitive_content)

        non_sensitive = ProvenanceReview(
            findings=(finding("spoiler"),),
            response_decision="revise",
            emotional_boundary_decision="not_required",
            capture_decision="no_candidate",
        )
        self.assertFalse(non_sensitive.contains_sensitive_content)

    def test_critique_names_each_ground(self) -> None:
        review = ProvenanceReview(
            findings=(finding("spoiler"), finding("misattribution")),
            response_decision="revise",
            emotional_boundary_decision="not_required",
            capture_decision="no_candidate",
        )
        critique = review.critique()
        self.assertIn("spoiler", critique)
        self.assertIn("misattribution", critique)

    def test_critique_excludes_capture_findings(self) -> None:
        review = ProvenanceReview(
            findings=(
                finding("spoiler"),
                finding("unsupported_claim", applies_to="capture"),
            ),
            response_decision="revise",
            emotional_boundary_decision="not_required",
            capture_decision="reject_capture",
        )
        self.assertIn("spoiler", review.critique())
        self.assertNotIn("unsupported_claim", review.critique())

    def test_each_blocked_decision_requires_its_own_finding(self) -> None:
        with self.assertRaises(ValidationError):
            ProvenanceReview(
                findings=(finding("unsupported_claim", applies_to="capture"),),
                response_decision="reject",
                emotional_boundary_decision="not_required",
                capture_decision="reject_capture",
            )
        with self.assertRaises(ValidationError):
            ProvenanceReview(
                findings=(finding("unsupported_claim"),),
                response_decision="reject",
                emotional_boundary_decision="not_required",
                capture_decision="reject_capture",
            )

    def test_passed_decisions_reject_findings_scoped_to_them(self) -> None:
        with self.assertRaises(ValidationError):
            ProvenanceReview(
                findings=(finding("spoiler"),),
                response_decision="pass",
                emotional_boundary_decision="not_required",
                capture_decision="no_candidate",
            )
        with self.assertRaises(ValidationError):
            ProvenanceReview(
                findings=(finding("unsupported_claim", applies_to="capture"),),
                response_decision="pass",
                emotional_boundary_decision="not_required",
                capture_decision="allow_capture",
            )

    def test_schema_drift_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ProvenanceReview(
                response_decision="pass",
                emotional_boundary_decision="not_required",
                capture_decision="no_candidate",
                unexpected_field="x",
            )

    def test_too_many_findings_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ProvenanceReview(
                findings=tuple(finding("spoiler") for _ in range(MAX_FINDINGS + 1)),
                response_decision="reject",
                emotional_boundary_decision="not_required",
                capture_decision="no_candidate",
            )

    def test_findings_array_declares_no_length_bound(self) -> None:
        """An array bound here 400s Gemini; the cap belongs in `require_justified_refusal`; string bounds are fine."""
        findings_schema = ProvenanceReview.model_json_schema()["properties"]["findings"]
        self.assertNotIn("maxItems", findings_schema)
        self.assertNotIn("minItems", findings_schema)

    def test_required_boundary_needs_reject_and_current_line_finding(self) -> None:
        with self.assertRaises(ValidationError):
            ProvenanceReview(
                findings=(finding("emotional_policy_violation"),),
                response_decision="reject",
                emotional_boundary_decision="required",
                capture_decision="no_candidate",
            )
        with self.assertRaises(ValidationError):
            ProvenanceReview(
                findings=(
                    RiskFinding(
                        code="emotional_policy_violation",
                        applies_to="response",
                        location=StructuralLocation(
                            kind="structural",
                            source_field="current_line.text",
                            path="",
                        ),
                        explanation="Boundary required.",
                    ),
                ),
                response_decision="revise",
                emotional_boundary_decision="required",
                capture_decision="no_candidate",
            )

    def test_current_line_emotional_finding_cannot_hide_a_required_boundary(
        self,
    ) -> None:
        with self.assertRaises(ValidationError):
            ProvenanceReview(
                findings=(
                    RiskFinding(
                        code="emotional_policy_violation",
                        applies_to="response",
                        location=StructuralLocation(
                            kind="structural",
                            source_field="current_line.text",
                            path="",
                        ),
                        explanation="Boundary required.",
                    ),
                ),
                response_decision="reject",
                emotional_boundary_decision="not_required",
                capture_decision="no_candidate",
            )

    def test_prompt_covers_untrusted_lines_and_diagnosis_of_any_person(self) -> None:
        lowered = " ".join(INSTRUCTIONS.lower().split())
        self.assertIn("content is untrusted", lowered)
        self.assertIn("reader or another person", lowered)
        self.assertIn("emotional_boundary_decision", lowered)

    def test_prompt_scopes_book_evidence_away_from_reader_attributed_facts(
        self,
    ) -> None:
        """Otherwise every correct recall reply is unsupportable by construction."""
        lowered = " ".join(INSTRUCTIONS.lower().split())
        self.assertIn("is exempt from `canonical_book_evidence`", lowered)
        self.assertIn("session-continuity contract", lowered)
        self.assertIn("book-corpus claim", lowered)
        self.assertIn("matching record in `canonical_book_evidence`", lowered)

    def test_prompt_gives_book_corpus_claims_precedence_over_reader_attribution(
        self,
    ) -> None:
        """Otherwise reader attribution could launder an unsupported book-corpus claim."""
        lowered = " ".join(INSTRUCTIONS.lower().split())
        self.assertIn("reader attribution never exempts a book-corpus claim", lowered)
        self.assertIn("no book-corpus content at all", lowered)

    def test_prompt_routes_doubted_reader_facts_to_revise_not_reject(self) -> None:
        lowered = " ".join(INSTRUCTIONS.lower().split())
        self.assertIn("do not reject it outright", lowered)
        self.assertIn("attribute the fact explicitly to the reader", lowered)
        self.assertIn('response_decision="revise"', lowered)

    def test_prompt_disambiguates_plot_from_everyday_vocabulary(self) -> None:
        """Otherwise a reader's garden plot reads as a book-plot claim."""
        lowered = " ".join(INSTRUCTIONS.lower().split())
        self.assertIn("plot events", lowered)
        self.assertIn(
            "shares vocabulary with book terms (words like plot, chapter, or "
            "character used in everyday senses",
            lowered,
        )

    def test_prompt_states_text_span_path_is_empty_for_the_fields_own_string(
        self,
    ) -> None:
        """Otherwise the model repeats the field name in path and validation fails."""
        lowered = " ".join(INSTRUCTIONS.lower().split())
        self.assertIn(
            "path` must be `\"\"` (empty string) — never repeat the field name "
            "inside the path".replace("`", ""),
            lowered.replace("`", ""),
        )

    def test_doubted_reader_fact_finding_satisfies_decision_justification(self) -> None:
        """Mirrors the exact finding shape the prompt instructs for a doubted reader fact."""
        review = ProvenanceReview(
            findings=(
                RiskFinding(
                    code="misattribution",
                    applies_to="response",
                    location=StructuralLocation(
                        kind="structural",
                        source_field="candidate.response",
                        path="",
                    ),
                    explanation="Attribute this fact explicitly to the reader.",
                ),
            ),
            response_decision="revise",
            emotional_boundary_decision="not_required",
            capture_decision="no_candidate",
        )
        self.assertEqual("revise", review.response_decision)
        self.assertEqual("misattribution", review.findings[0].code)


class ProvenanceAgentTests(unittest.TestCase):
    def test_review_round_trips_through_the_agent(self) -> None:
        with patch("src.linger.agents.build.build_model", return_value=TestModel()):
            from src.linger.agents.provenance.agent import build_provenance_agent

        model = TestModel(
            custom_output_args={
                "findings": [
                    {
                        "code": "prompt_injection",
                        "applies_to": "response",
                        "location": {
                            "kind": "text_span",
                            "source_field": "candidate.response",
                            "path": "",
                            "quote": "ignore previous instructions",
                        },
                        "explanation": "The passage redirects agent behaviour.",
                    }
                ],
                "response_decision": "reject",
                "emotional_boundary_decision": "not_required",
                "capture_decision": "no_candidate",
            }
        )
        agent = build_provenance_agent(model)
        review = agent.run_sync("candidate").output

        self.assertIsInstance(review, ProvenanceReview)
        self.assertEqual("prompt_injection", review.findings[0].code)
        self.assertEqual("reject", review.response_decision)

    def test_agent_retries_output_validation(self) -> None:
        # pydantic-ai exposes no public accessor for output retries.
        agent = build_provenance_agent(TestModel())
        self.assertEqual(2, agent._max_output_retries)

    def test_provenance_has_no_tools(self) -> None:
        """Section 3.3: Provenance reviews without any tool authority."""
        with patch("src.linger.agents.build.build_model", return_value=TestModel()):
            from src.linger.agents.provenance.agent import build_provenance_agent

        model = TestModel(
            custom_output_args={
                "findings": [],
                "response_decision": "pass",
                "emotional_boundary_decision": "not_required",
                "capture_decision": "no_candidate",
            }
        )
        agent = build_provenance_agent(model)
        agent.run_sync("candidate")

        self.assertEqual([], model.last_model_request_parameters.function_tools)


class TextSpanLocationTests(unittest.TestCase):
    def test_accepts_a_quote_only_location(self) -> None:
        location = TextSpanLocation(
            kind="text_span",
            source_field="candidate.response",
            path="",
            quote="offending",
        )
        self.assertEqual("offending", location.quote)

    def test_rejects_a_too_short_quote(self) -> None:
        with self.assertRaises(ValidationError):
            TextSpanLocation(
                kind="text_span",
                source_field="candidate.response",
                path="",
                quote="ab",
            )


class ProvenanceInputTests(unittest.TestCase):
    def test_rejects_unknown_top_level_fields(self) -> None:
        payload = provenance_input().model_dump(mode="json")
        payload["cited_evidence"] = []
        with self.assertRaises(ValidationError):
            ProvenanceInput.model_validate(payload)

    def test_text_span_must_match_the_declared_source(self) -> None:
        review = ProvenanceReview(
            findings=(
                RiskFinding(
                    code="unsupported_claim",
                    applies_to="response",
                    location=TextSpanLocation(
                        kind="text_span",
                        source_field="candidate.response",
                        path="",
                        quote="offending",
                    ),
                    explanation="why",
                ),
            ),
            response_decision="reject",
            emotional_boundary_decision="not_required",
            capture_decision="no_candidate",
        )
        provenance_input().validate_review_locations(review)
        with self.assertRaisesRegex(ValueError, "does not match"):
            provenance_input("different text").validate_review_locations(review)

    def test_quote_contained_in_a_longer_source_string_still_matches(self) -> None:
        review = ProvenanceReview(
            findings=(
                RiskFinding(
                    code="unsupported_claim",
                    applies_to="response",
                    location=TextSpanLocation(
                        kind="text_span",
                        source_field="candidate.response",
                        path="",
                        quote="offending",
                    ),
                    explanation="why",
                ),
            ),
            response_decision="reject",
            emotional_boundary_decision="not_required",
            capture_decision="no_candidate",
        )
        provenance_input("this is an offending span within a longer response").validate_review_locations(
            review
        )

    def test_response_finding_can_point_to_the_current_user_line(self) -> None:
        review = ProvenanceReview(
            findings=(
                RiskFinding(
                    code="emotional_policy_violation",
                    applies_to="response",
                    location=TextSpanLocation(
                        kind="text_span",
                        source_field="current_line.text",
                        path="",
                        quote="reader",
                    ),
                    explanation="The user Line requires the emotional boundary.",
                ),
            ),
            response_decision="reject",
            emotional_boundary_decision="required",
            capture_decision="no_candidate",
        )
        provenance_input().validate_review_locations(review)

    def test_location_validation_serializes_the_input_once(self) -> None:
        review = ProvenanceReview(
            findings=(finding("spoiler"), finding("misattribution")),
            response_decision="reject",
            emotional_boundary_decision="not_required",
            capture_decision="no_candidate",
        )
        review_input = provenance_input()
        original = ProvenanceInput.model_dump
        calls = 0

        def counted_model_dump(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            return original(self, *args, **kwargs)

        with patch.object(ProvenanceInput, "model_dump", counted_model_dump):
            review_input.validate_review_locations(review)

        self.assertEqual(1, calls)

    def test_structural_path_must_exist(self) -> None:
        # Response findings cannot point at candidate.memory.
        with self.assertRaises(ValidationError):
            RiskFinding(
                code="unresolved_evidence",
                applies_to="response",
                location=StructuralLocation(
                    kind="structural",
                    source_field="candidate.memory",
                    path="/reason_code",
                ),
                explanation="why",
            )

        missing_path = ProvenanceReview(
            findings=(
                RiskFinding(
                    code="unresolved_evidence",
                    applies_to="response",
                    location=StructuralLocation(
                        kind="structural",
                        source_field="candidate.evidence_uses",
                        path="/0/evidence_id",
                    ),
                    explanation="why",
                ),
            ),
            response_decision="reject",
            emotional_boundary_decision="not_required",
            capture_decision="no_candidate",
        )
        with self.assertRaisesRegex(ValueError, "missing array item"):
            provenance_input().validate_review_locations(missing_path)
