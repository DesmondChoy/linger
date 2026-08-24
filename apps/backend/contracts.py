"""Typed hand-offs for the reflection and connection pipeline."""

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from src.linger.agents.contracts import StrictModel
from src.linger.agents.provenance.models import RiskFinding
from src.linger.contracts.emotional import EmotionalContentPolicy
from src.linger.contracts.librarian import EvidenceRecord


class ReadingContext(StrictModel):
    work_id: str
    chapter_max: int = Field(ge=1)
    boundary_source: Literal["reader_confirmed"] = "reader_confirmed"


class ContextResolution(StrictModel):
    """What the router knows before it creates the spoiler-safe MuseTurn."""

    status: Literal["confirmed", "inferred", "unknown"]
    work_id: str | None = None
    work_title: str | None = None
    chapter_max: int | None = Field(default=None, ge=1)
    boundary_source: Literal["reader_confirmed", "inferred_from_question"] | None = None
    explanation: str


class TurnPolicy(StrictModel):
    spoiler_ceiling: int | None = Field(default=None, ge=1)
    allow_retrieval: bool
    allow_connection: bool
    allow_memory_capture: bool = False
    emotional_content: EmotionalContentPolicy = Field(
        default_factory=EmotionalContentPolicy
    )


class MuseTurn(StrictModel):
    """Fixed per-turn contract from the router to Muse."""

    turn_id: str
    user_message: str
    reading_context: ReadingContext | None
    policy: TurnPolicy


class MuseDraftInput(StrictModel):
    """Complete application-owned envelope for one initial Muse draft."""

    mode: Literal["draft"]
    muse_turn: MuseTurn
    context_resolution: ContextResolution
    prior_evidence: tuple[EvidenceRecord, ...] = ()


class MuseRevisionReview(StrictModel):
    """Only response-scoped findings from the first Provenance review."""

    findings: tuple[RiskFinding, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_response_findings(self) -> Self:
        if any(finding.applies_to != "response" for finding in self.findings):
            raise ValueError("Muse revision guidance must be response-scoped")
        return self


class MuseRevisionInput(StrictModel):
    """Complete application-owned envelope for the single reviewed rewrite."""

    mode: Literal["revision"]
    muse_turn: MuseTurn
    context_resolution: ContextResolution
    prior_evidence: tuple[EvidenceRecord, ...] = ()
    review: MuseRevisionReview


class ConnectionBrief(BaseModel):
    """Muse's connection request before application-owned scope is attached."""

    cue: str = Field(min_length=1, max_length=8000)
    intent: Literal["find_connection", "get_recommendation"] = "find_connection"


class BookScope(BaseModel):
    """One immutable corpus revision and its reader-confirmed boundary."""

    work_id: str
    book_version_id: str
    chapter_max: int = Field(ge=1)


class LibrarianRequest(BaseModel):
    """Serendipity's bounded retrieval request to Librarian."""

    query: str = Field(min_length=1, max_length=2000)
    book_scopes: list[BookScope] = []
    retrieval_score_threshold: float = Field(default=0.5, ge=0, le=1)
    max_results: int = Field(default=5, ge=1, le=10)
    purpose: Literal["connection_discovery"] = "connection_discovery"


class EvidenceItem(BaseModel):
    evidence_id: str
    work_id: str
    book_version_id: str
    chapter_id: str
    source_title: str
    location: str
    chapter: int = Field(ge=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_lines: tuple[int, int]
    excerpt: str
    relevance: float = Field(ge=0, le=1)
    source_kind: Literal["book_corpus"] = "book_corpus"
    trust_level: Literal["canonical"] = "canonical"


class EvidenceBundle(BaseModel):
    items: list[EvidenceItem]
    retrieval_note: str
