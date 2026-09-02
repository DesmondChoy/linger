"""Tests for the curation-specific, no-tool Provenance contract."""

import unittest
from unittest.mock import patch

from pydantic import ValidationError
from pydantic_ai.models.test import TestModel

from src.linger.agents.provenance.curation_models import (
    CurationFinding,
    CurationProvenanceReview,
    CurationReviewInput,
    CurationSourceEvidence,
)
from src.linger.agents.sculptor.models import CurationProposal, DuplicateLink


def review_input() -> CurationReviewInput:
    source_ids = ("memory-1", "memory-2")
    return CurationReviewInput(
        proposal_digest="a" * 64,
        proposal=CurationProposal(
            kind="curation_proposal",
            action=DuplicateLink(
                action="link_duplicates",
                source_memory_ids=source_ids,
            ),
        ),
        sources=tuple(
            CurationSourceEvidence(
                memory_id=memory_id,
                text="The same durable memory.",
                record_sha256=str(index) * 64,
            )
            for index, memory_id in enumerate(source_ids, start=1)
        ),
    )


class CurationProvenanceContractTests(unittest.TestCase):
    def test_allow_is_bound_to_the_exact_proposal_digest(self) -> None:
        review = CurationProvenanceReview(
            proposal_digest="a" * 64,
            decision="allow",
        )
        review_input().validate_review(review)

        mismatched = review.model_copy(
            update={"proposal_digest": "b" * 64}
        )
        with self.assertRaisesRegex(ValueError, "different curation proposal"):
            review_input().validate_review(mismatched)

    def test_blocked_decisions_require_scoped_findings(self) -> None:
        with self.assertRaises(ValidationError):
            CurationProvenanceReview(
                proposal_digest="a" * 64,
                decision="reject",
            )
        with self.assertRaises(ValidationError):
            CurationProvenanceReview(
                proposal_digest="a" * 64,
                decision="allow",
                findings=(
                    CurationFinding(
                        code="incorrect_duplicate",
                        source_memory_ids=("memory-1",),
                        explanation="The records differ.",
                    ),
                ),
            )

    def test_findings_cannot_reference_sources_outside_the_input(self) -> None:
        review = CurationProvenanceReview(
            proposal_digest="a" * 64,
            decision="reject",
            findings=(
                CurationFinding(
                    code="incorrect_duplicate",
                    source_memory_ids=("memory-outside-scope",),
                    explanation="Unknown source.",
                ),
            ),
        )
        with self.assertRaisesRegex(ValueError, "unknown source"):
            review_input().validate_review(review)

    def test_agent_has_typed_output_and_no_tools(self) -> None:
        with patch("src.linger.agents.build.build_model", return_value=TestModel()):
            from src.linger.agents.provenance.curation import (
                build_curation_provenance_agent,
            )

        model = TestModel(
            custom_output_args=CurationProvenanceReview(
                proposal_digest="a" * 64,
                decision="allow",
            )
        )
        agent = build_curation_provenance_agent(model)
        result = agent.run_sync(review_input().model_dump_json())

        self.assertEqual("allow", result.output.decision)
        parameters = model.last_model_request_parameters
        self.assertIsNotNone(parameters)
        assert parameters is not None
        self.assertEqual([], parameters.function_tools)


if __name__ == "__main__":
    unittest.main()
