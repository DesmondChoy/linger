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
