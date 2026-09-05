"""Librarian request/response contracts."""

from __future__ import annotations

from collections.abc import Sequence
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
    chapter_id: str
    chapter_number: int = Field(ge=1)
    location: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_lines: tuple[int, int]
    text: str


class BoundarySupportLocation(StrictModel):
    """Content-free location supporting one inferred spoiler ceiling."""

    evidence_id: str
    chapter_number: int = Field(ge=1)
    location: str


class BoundaryCandidate(StrictModel):
    """Validated request-scoped ceiling; full-work passage text is excluded."""

    kind: Literal["candidate"]
    work_id: str
    book_version_id: str
    max_chapter_inclusive: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)
    authorization_basis: Literal["memory_supported"]
    supporting_memory_ids: tuple[str, ...] = Field(min_length=1)
    supporting_locations: tuple[BoundarySupportLocation, ...] = Field(min_length=1)


class BoundaryUncertain(StrictModel):
    """A safe request for clarification when inference cannot set a ceiling."""

    kind: Literal["uncertain"]
    work_id: str
    book_version_id: str
    reason_code: Literal[
        "insufficient_context",
        "conflicting_context",
        "low_confidence",
        "progress_unverified",
        "inference_unavailable",
    ]
    confidence: float | None = Field(default=None, ge=0, le=1)
    authorization_basis: Literal["memory_supported", "line_only"] | None = None
    supporting_memory_ids: tuple[str, ...] = ()
    candidate_chapter: int | None = Field(default=None, ge=1)
    supporting_locations: tuple[BoundarySupportLocation, ...] = ()
    clarification_question: str

    @model_validator(mode="after")
    def _candidate_fields_are_complete(self) -> "BoundaryUncertain":
        if self.candidate_chapter is None:
            if (
                self.authorization_basis is not None
                or self.supporting_memory_ids
                or self.supporting_locations
            ):
                raise ValueError("uncertain result without a candidate cannot cite support")
        else:
            if (
                self.confidence is None
                or self.authorization_basis is None
                or not self.supporting_locations
            ):
                raise ValueError("uncertain candidate requires confidence, basis, and support")
            if self.authorization_basis == "memory_supported":
                if not self.supporting_memory_ids:
                    raise ValueError(
                        "memory-supported candidate requires supporting memory IDs"
                    )
            elif self.supporting_memory_ids:
                raise ValueError("line-only candidate cannot cite supporting memories")
        return self


BoundaryInferenceResult = BoundaryCandidate | BoundaryUncertain


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


class RoutedWork(StrictModel):
    """A confidently identified work with a resolved, request-scoped boundary."""

    kind: Literal["routed"]
    request_id: str
    work_id: str
    book_version_id: str
    title: str
    routing_confidence: float = Field(ge=0, le=1)
    max_chapter_inclusive: int = Field(ge=1)
    boundary_confidence: float = Field(ge=0, le=1)


class NoMatch(StrictModel):
    """No book intent was evident in the message; Muse should keep reflecting."""

    kind: Literal["no_match"]
    request_id: str


LibrarianRoutingResponse = RoutedWork | ClarificationRequest | NoMatch
LIBRARIAN_ROUTING_RESPONSE_ADAPTER = TypeAdapter(
    Annotated[LibrarianRoutingResponse, Field(discriminator="kind")]
)


def effective_route_response(
    responses: Sequence[LibrarianRoutingResponse],
) -> LibrarianRoutingResponse | None:
    """Reduce ordered route calls using the application release precedence.

    Any clarification prevents a routed result from granting release scope. When
    no clarification exists, the first routed result is authoritative. A no-match
    is useful only when no stronger response exists.
    """

    clarification = next(
        (
            response
            for response in responses
            if isinstance(response, ClarificationRequest)
        ),
        None,
    )
    if clarification is not None:
        return clarification
    routed = next(
        (response for response in responses if isinstance(response, RoutedWork)),
        None,
    )
    if routed is not None:
        return routed
    return next(
        (response for response in responses if isinstance(response, NoMatch)),
        None,
    )
