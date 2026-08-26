"""Build and validate independent human adoption of proposed Ground truth."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from .models import (
    AdoptedProposalDecision,
    GroundTruthAdoption,
    HumanGroundTruthReviewer,
    ProposedGroundTruth,
    SyntheticBackstory,
)
from .validate_package import PackageValidationError, validate_package_files


class GroundTruthAdoptionError(ValueError):
    """One or more adoption authority checks failed."""

    def __init__(self, failures: list[str]) -> None:
        self.failures = tuple(failures)
        super().__init__("; ".join(failures))


def proposed_ground_truth_sha256(ground_truth_bytes: bytes) -> str:
    return hashlib.sha256(ground_truth_bytes).hexdigest()


def adopted_ground_truth_identity(
    *,
    backstory_sha256: str,
    proposed_sha256: str,
    decisions: tuple[AdoptedProposalDecision, ...],
) -> str:
    """Identify the adopted answer key without reviewer- or time-dependent data."""

    document = {
        "backstory_sha256": backstory_sha256,
        "proposed_ground_truth_sha256": proposed_sha256,
        "decisions": [
            decision.model_dump(mode="json") for decision in decisions
        ],
    }
    return hashlib.sha256(
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def build_ground_truth_adoption(
    ground_truth: ProposedGroundTruth,
    ground_truth_bytes: bytes,
    *,
    reviewer_id: str,
    reviewed_at: datetime | None = None,
) -> GroundTruthAdoption:
    """Adopt every proposal in one already-reviewed proposed Ground truth file."""

    reviewer = HumanGroundTruthReviewer(reviewer_id=reviewer_id)
    decisions = tuple(
        AdoptedProposalDecision(
            proposal_id=proposal.proposal_id,
            scene_id=proposal.scene_id,
            objective_id=proposal.objective_id,
        )
        for proposal in ground_truth.proposals
    )
    proposed_sha256 = proposed_ground_truth_sha256(ground_truth_bytes)
    adoption = GroundTruthAdoption(
        backstory_sha256=ground_truth.backstory_sha256,
        proposed_ground_truth_sha256=proposed_sha256,
        reviewer=reviewer,
        reviewed_at=reviewed_at or datetime.now().astimezone(),
        decisions=decisions,
        adopted_ground_truth_identity=adopted_ground_truth_identity(
            backstory_sha256=ground_truth.backstory_sha256,
            proposed_sha256=proposed_sha256,
            decisions=decisions,
        ),
    )
    validate_ground_truth_adoption(
        ground_truth,
        adoption,
        ground_truth_bytes=ground_truth_bytes,
    )
    return adoption


def validate_ground_truth_adoption(
    ground_truth: ProposedGroundTruth,
    adoption: GroundTruthAdoption,
    *,
    ground_truth_bytes: bytes,
) -> None:
    """Fail closed unless an adoption covers the exact complete proposal file."""

    failures: list[str] = []
    if adoption.backstory_sha256 != ground_truth.backstory_sha256:
        failures.append("adoption backstory_sha256 does not match Ground truth")

    proposed_sha256 = proposed_ground_truth_sha256(ground_truth_bytes)
    if adoption.proposed_ground_truth_sha256 != proposed_sha256:
        failures.append(
            "adoption proposed_ground_truth_sha256 does not match exact file bytes"
        )

    expected = {
        (proposal.proposal_id, proposal.scene_id, proposal.objective_id)
        for proposal in ground_truth.proposals
    }
    actual = {
        (decision.proposal_id, decision.scene_id, decision.objective_id)
        for decision in adoption.decisions
    }
    if actual != expected or len(adoption.decisions) != len(expected):
        failures.append("adoption decisions must cover every proposal exactly once")

    expected_identity = adopted_ground_truth_identity(
        backstory_sha256=ground_truth.backstory_sha256,
        proposed_sha256=proposed_sha256,
        decisions=adoption.decisions,
    )
    if adoption.adopted_ground_truth_identity != expected_identity:
        failures.append("adopted_ground_truth_identity is invalid")

    if failures:
        raise GroundTruthAdoptionError(failures)


def validate_ground_truth_adoption_files(
    backstory_path: Path,
    ground_truth_path: Path,
    adoption_path: Path,
) -> tuple[SyntheticBackstory, ProposedGroundTruth, GroundTruthAdoption]:
    """Load and validate one package plus its exact independent adoption."""

    backstory, ground_truth = validate_package_files(
        backstory_path,
        ground_truth_path,
    )
    ground_truth_bytes = ground_truth_path.read_bytes()
    try:
        adoption = GroundTruthAdoption.model_validate_json(adoption_path.read_bytes())
    except ValidationError as error:
        failure = (
            "invalid Ground truth adoption: "
            f"{error.error_count()} validation error(s)"
        )
        raise GroundTruthAdoptionError(
            [failure]
        ) from error
    validate_ground_truth_adoption(
        ground_truth,
        adoption,
        ground_truth_bytes=ground_truth_bytes,
    )
    return backstory, ground_truth, adoption


__all__ = [
    "GroundTruthAdoptionError",
    "PackageValidationError",
    "adopted_ground_truth_identity",
    "build_ground_truth_adoption",
    "proposed_ground_truth_sha256",
    "validate_ground_truth_adoption",
    "validate_ground_truth_adoption_files",
]
