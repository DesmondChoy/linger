"""Contract and grading tests for the curation Provenance risk pack."""

import unittest

from evals.provenance.curation_risk_codes import (
    CURATION_CODES,
    build_case_set,
    grade_review,
)
from src.linger.agents.provenance.curation_models import (
    CurationFinding,
    CurationProvenanceReview,
)


class CurationRiskCodeEvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.case_set = build_case_set()
        cls.by_behavior = {case.primary_behavior: case for case in cls.case_set.cases}

    def test_pack_has_a_positive_and_near_miss_for_every_code(self) -> None:
        self.assertEqual(12, len(self.case_set.cases))
        self.assertEqual(
            {f"{code}_{suffix}" for code in CURATION_CODES for suffix in ("positive", "negative")},
            set(self.by_behavior),
        )

    def test_positive_cases_require_their_named_finding(self) -> None:
        for code in CURATION_CODES:
            case = self.by_behavior[f"{code}_positive"]
            finding = CurationFinding(
                code=code,
                source_memory_ids=tuple(source.memory_id for source in case.review_input.sources),
                explanation=f"Detected {code}.",
            )
            review = CurationProvenanceReview(
                proposal_digest=case.review_input.proposal_digest,
                decision=(
                    "reject"
                    if code
                    in {
                        "incorrect_duplicate",
                        "incoherent_topic",
                        "unsafe_tombstone",
                        "invalid_restore",
                        "prompt_injection",
                    }
                    else "revise"
                ),
                findings=(finding,),
            )
            self.assertTrue(grade_review(case, review).passed, code)

    def test_positive_case_with_wrong_code_fails(self) -> None:
        case = self.by_behavior["unsafe_tombstone_positive"]
        review = CurationProvenanceReview(
            proposal_digest=case.review_input.proposal_digest,
            decision="revise",
            findings=(
                CurationFinding(
                    code="incorrect_duplicate",
                    source_memory_ids=tuple(source.memory_id for source in case.review_input.sources),
                    explanation="Wrong code.",
                ),
            ),
        )
        grade = grade_review(case, review)
        self.assertFalse(grade.passed)
        self.assertEqual("code_mismatch", grade.failure_code)

    def test_near_miss_requires_a_clean_allow(self) -> None:
        case = self.by_behavior["incoherent_topic_negative"]
        review = CurationProvenanceReview(
            proposal_digest=case.review_input.proposal_digest,
            decision="allow",
        )
        self.assertTrue(grade_review(case, review).passed)


if __name__ == "__main__":
    unittest.main()
