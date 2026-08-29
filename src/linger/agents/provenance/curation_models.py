"""Typed contract for independent review of one Sculptor proposal."""

from __future__ import annotations

import hashlib
import json
from typing import Literal, Self

from pydantic import Field, model_validator

from src.linger.agents.contracts import StrictModel
from src.linger.agents.sculptor.models import CurationProposal

CurationRiskCode = Literal[
    "unsupported_derivation",
    "incorrect_duplicate",
    "incoherent_topic",
    "unsafe_tombstone",
    "invalid_restore",
    "prompt_injection",
]


class CurationSourceEvidence(StrictModel):
    """One immutable source snapshot supplied for semantic review."""

    memory_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CurationReviewInput(StrictModel):
    """The exact proposal and source evidence reviewed by Provenance."""

    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal: CurationProposal
    sources: tuple[CurationSourceEvidence, ...] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def require_exact_unique_sources(self) -> Self:
        source_ids = tuple(source.memory_id for source in self.sources)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("curation review source IDs must be unique")
        if set(source_ids) != set(self.proposal.action.source_memory_ids):
            raise ValueError("curation review sources must exactly match the proposal")
        return self

    def validate_review(self, review: "CurationProvenanceReview") -> None:
        """Bind findings and the echoed digest to this exact review input."""

        if review.proposal_digest != self.proposal_digest:
            raise ValueError("Provenance reviewed a different curation proposal")
        source_ids = {source.memory_id for source in self.sources}
        for finding in review.findings:
            if not set(finding.source_memory_ids).issubset(source_ids):
                raise ValueError("a curation finding references an unknown source")


class CurationFinding(StrictModel):
    """One semantic reason to revise or reject a curation proposal."""

    code: CurationRiskCode
    source_memory_ids: tuple[str, ...] = Field(min_length=1, max_length=12)
    explanation: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def require_unique_sources(self) -> Self:
        if len(self.source_memory_ids) != len(set(self.source_memory_ids)):
            raise ValueError("curation finding source IDs must be unique")
        return self


class CurationProvenanceReview(StrictModel):
    """An independent verdict bound to one immutable curation proposal."""

    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["allow", "revise", "reject"]
    findings: tuple[CurationFinding, ...] = Field(default=(), max_length=12)

    @model_validator(mode="after")
    def require_decision_findings(self) -> Self:
        if self.decision == "allow" and self.findings:
            raise ValueError("an allowed curation proposal cannot have findings")
        if self.decision != "allow" and not self.findings:
            raise ValueError("a blocked curation proposal requires a finding")
        return self


def review_digest(review: CurationProvenanceReview) -> str:
    """Return the canonical digest of one immutable review verdict."""

    return hashlib.sha256(
        json.dumps(
            review.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
