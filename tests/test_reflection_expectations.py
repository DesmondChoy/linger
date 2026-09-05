"""Tests for the reflection-and-grounding Ground truth expectation contract."""

import unittest

from pydantic import ValidationError

from evals.reflection.harness import (
    GroundedRelease,
    GroundingExpectation,
    UngroundedRelease,
)
from evals.synthetic_journals.models import GroundTruthProposal


def grounded(
    *evidence_ids: str, chapter_max: int = 6
) -> GroundingExpectation:
    return GroundingExpectation(
        primary_behavior="grounded_reflection",
        expected=GroundedRelease(
            kind="grounded_release",
            permitted_evidence_ids=evidence_ids or ("ev-1",),
            chapter_max=chapter_max,
        ),
    )


def proposal(**overrides: object) -> GroundTruthProposal:
    payload: dict[str, object] = {
        "proposal_id": "gt-1",
        "scene_id": "s1",
        "objective_id": "weak_evidence_safe_decline",
        "expected_outcomes": ("releases a grounded reflection",),
        "prohibited_outcomes": ("cites unresolvable evidence",),
    }
    payload.update(overrides)
    return GroundTruthProposal.model_validate(payload)


class GroundingExpectationTests(unittest.TestCase):
    def test_grounded_reflection_reports_its_release_contract(self) -> None:
        expectation = grounded("ev-1", "ev-2")
        self.assertTrue(expectation.retrieval_required)
        self.assertEqual("muse_candidate", expectation.release_source)
        self.assertEqual({"ev-1", "ev-2"}, set(expectation.permitted_evidence_ids))

    def test_non_grounded_reflection_requires_no_retrieval_or_evidence(self) -> None:
        expectation = GroundingExpectation(
            primary_behavior="non_grounded_reflection",
            expected=UngroundedRelease(kind="ungrounded_release"),
        )
        self.assertFalse(expectation.retrieval_required)
        self.assertEqual("muse_candidate", expectation.release_source)
        self.assertEqual(frozenset(), expectation.permitted_evidence_ids)

    def test_weak_evidence_decline_expects_the_application_path(self) -> None:
        expectation = GroundingExpectation.model_validate(
            {
                "primary_behavior": "weak_evidence_decline",
                "expected": {"kind": "safe_decline"},
            }
        )
        self.assertFalse(expectation.retrieval_required)
        self.assertEqual("application_safe_decline", expectation.release_source)

    def test_clarification_releases_through_muse_without_retrieval(self) -> None:
        expectation = GroundingExpectation.model_validate(
            {
                "primary_behavior": "bounded_clarification",
                "expected": {"kind": "clarification_release"},
            }
        )
        self.assertFalse(expectation.retrieval_required)
        self.assertEqual("muse_candidate", expectation.release_source)

    def test_behavior_and_expected_release_must_agree(self) -> None:
        """A Scene cannot claim no retrieval while naming permitted evidence."""
        with self.assertRaisesRegex(ValidationError, "requires expected.kind"):
            GroundingExpectation.model_validate(
                {
                    "primary_behavior": "non_grounded_reflection",
                    "expected": {
                        "kind": "grounded_release",
                        "permitted_evidence_ids": ["ev-1"],
                        "chapter_max": 6,
                    },
                }
            )

    def test_grounded_release_requires_at_least_one_permitted_record(self) -> None:
        with self.assertRaises(ValidationError):
            GroundedRelease(
                kind="grounded_release",
                permitted_evidence_ids=(),
                chapter_max=6,
            )

    def test_duplicate_permitted_evidence_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must be unique"):
            GroundedRelease(
                kind="grounded_release",
                permitted_evidence_ids=("ev-1", "ev-1"),
                chapter_max=6,
            )

    def test_unknown_expected_kind_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            GroundingExpectation.model_validate(
                {
                    "primary_behavior": "grounded_reflection",
                    "expected": {"kind": "released"},
                }
            )


class GroundTruthProposalGroundingTests(unittest.TestCase):
    def test_proposal_without_grounding_is_unchanged(self) -> None:
        self.assertIsNone(proposal().grounding)

    def test_permitted_evidence_must_be_declared_by_the_proposal(self) -> None:
        """A permitted citation the package never declares cannot be graded."""
        with self.assertRaisesRegex(ValidationError, "absent from the proposal"):
            proposal(grounding=grounded("ev-missing"))

    def test_permitted_evidence_resolves_against_declared_evidence(self) -> None:
        subject = proposal(
            evidence=(
                {
                    "kind": "repository_text",
                    "evidence_id": "ev-1",
                    "repository_path": "data/corpus/alice-in-wonderland/x.md",
                    "source_sha256": "a" * 64,
                    "start_codepoint": 0,
                    "end_codepoint": 12,
                    "text": "Alice hopes",
                },
            ),
            grounding=grounded("ev-1"),
        )
        self.assertEqual({"ev-1"}, set(subject.grounding.permitted_evidence_ids))

    def test_ungrounded_expectation_needs_no_declared_evidence(self) -> None:
        subject = proposal(
            grounding=GroundingExpectation(
                primary_behavior="non_grounded_reflection",
                expected=UngroundedRelease(kind="ungrounded_release"),
            )
        )
        self.assertFalse(subject.grounding.retrieval_required)

    def test_grounding_survives_a_json_round_trip(self) -> None:
        subject = proposal(
            evidence=(
                {
                    "kind": "prop",
                    "evidence_id": "ev-1",
                    "prop_id": "prop-1",
                },
            ),
            grounding=grounded("ev-1"),
        )
        restored = GroundTruthProposal.model_validate_json(
            subject.model_dump_json()
        )
        self.assertEqual(subject, restored)


if __name__ == "__main__":
    unittest.main()
