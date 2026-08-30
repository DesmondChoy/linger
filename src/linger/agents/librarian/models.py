"""Typed output from Librarian's evidence-strength judgment."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from src.linger.contracts.base import StrictModel


class EvidenceStrengthDecision(StrictModel):
    """A set-level answerability judgment, independent of retrieval scores."""

    evidence_strength: Literal["sufficient", "weak", "none"]
    strength_reason: str = Field(min_length=1, max_length=2_000)
    relevant_evidence_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _fields_match_strength(self) -> "EvidenceStrengthDecision":
        if self.evidence_strength == "none" and self.relevant_evidence_ids:
            raise ValueError("none strength cannot cite relevant evidence")
        if self.evidence_strength != "none" and not self.relevant_evidence_ids:
            raise ValueError("sufficient or weak strength must cite relevant evidence")
        if self.evidence_strength == "weak" and not self.limitations:
            raise ValueError("weak strength must explain at least one limitation")
        return self


class BoundaryInferenceDecision(StrictModel):
    """Private full-work judgment before the application grants retrieval."""

    outcome: Literal["candidate", "uncertain"]
    work_id: str | None = None
    book_version_id: str | None = None
    chapter_number: int | None = Field(default=None, ge=1)
    confidence: float = Field(ge=0, le=1)
    authorization_basis: Literal["memory_supported", "line_only"] | None = None
    supporting_memory_ids: tuple[str, ...] = ()
    supporting_evidence_ids: tuple[str, ...] = ()
    reason_code: Literal[
        "insufficient_context",
        "conflicting_context",
        "low_confidence",
    ] | None = None

    @model_validator(mode="after")
    def _fields_match_outcome(self) -> "BoundaryInferenceDecision":
        candidate_fields = (
            self.work_id,
            self.book_version_id,
            self.chapter_number,
        )
        if self.outcome == "candidate":
            if any(value is None for value in candidate_fields):
                raise ValueError("candidate outcome requires work, version, and chapter")
            if not self.supporting_evidence_ids:
                raise ValueError("candidate outcome requires supporting evidence IDs")
            if self.authorization_basis is None:
                raise ValueError("candidate outcome requires an authorization basis")
            if self.authorization_basis == "memory_supported":
                if not self.supporting_memory_ids:
                    raise ValueError(
                        "memory-supported candidate requires supporting memory IDs"
                    )
            elif self.supporting_memory_ids:
                raise ValueError("line-only candidate cannot cite supporting memories")
            if self.reason_code is not None:
                raise ValueError("candidate outcome cannot declare an uncertainty reason")
        else:
            if (
                any(value is not None for value in candidate_fields)
                or self.authorization_basis is not None
                or self.supporting_memory_ids
                or self.supporting_evidence_ids
            ):
                raise ValueError("uncertain outcome cannot declare a candidate boundary")
            if self.reason_code is None:
                raise ValueError("uncertain outcome requires a reason code")
        return self
