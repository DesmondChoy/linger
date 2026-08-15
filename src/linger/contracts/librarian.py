"""Librarian request/response contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, model_validator

from src.linger.contracts.base import StrictModel
from src.linger.contracts.reading import ReadingBoundary


class AccessScope(StrictModel):
    """Trusted access grant. Built by application code, never model output."""

    allowed_book_version_ids: tuple[str, ...] = Field(min_length=1)


class RetrievalOptions(StrictModel):
    """Tunable retrieval limits Muse may not lower or enlarge."""

    retrieval_score_threshold: float = Field(default=0.5, ge=0, le=1)
    max_final_evidence: int = Field(default=5, ge=1, le=10)


class LibrarianRequest(StrictModel):
    """Muse's question plus the trusted, validated scope to answer it in."""

    request_id: str
    query: str = Field(min_length=1, max_length=2000)
    work_id: str
    book_version_id: str
    reading_boundary: ReadingBoundary | None
    access_scope: AccessScope
    options: RetrievalOptions


class ExpectedAnswer(StrictModel):
    """The closed set of answers a clarification question accepts, or a free-text question."""

    type: Literal["one_of", "free_text"]
    values: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _values_match_type(self) -> "ExpectedAnswer":
        if self.type == "one_of" and not self.values:
            raise ValueError("values must be non-empty when type is 'one_of'")
        if self.type == "free_text" and self.values:
            raise ValueError("values must be empty when type is 'free_text'")
        return self


class ClarificationRequest(StrictModel):
    """A distinct response type: no search occurred, so no evidence exists."""

    kind: Literal["clarification"]
    request_id: str
    clarification_id: str
    reason_code: str
    question: str
    expected_answer: ExpectedAnswer


class SearchedScope(StrictModel):
    """The chapter boundary actually searched to produce a result."""

    work_id: str
    book_version_id: str
    max_chapter_inclusive: int = Field(ge=0)


class EvidenceRecord(StrictModel):
    """Evidence built from the shipped corpus without fabricating values."""

    evidence_id: str
    work_id: str
    book_version_id: str
    chapter_number: int = Field(ge=1)
    location: str
    text: str


class RetrievalResult(StrictModel):
    kind: Literal["result"]
    request_id: str
    outcome: Literal["evidence_found", "no_evidence"]
    evidence_strength: Literal["sufficient", "weak", "none"]
    strength_reason: str
    searched_scope: SearchedScope
    evidence: tuple[EvidenceRecord, ...] = ()
    limitations: tuple[str, ...] = ()


class RetrievalFailure(StrictModel):
    kind: Literal["failure"]
    request_id: str
    error_code: str
    retryable: bool


LibrarianResponse = ClarificationRequest | RetrievalResult | RetrievalFailure
LIBRARIAN_RESPONSE_ADAPTER = TypeAdapter(
    Annotated[LibrarianResponse, Field(discriminator="kind")]
)
