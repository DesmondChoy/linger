"""Typed hand-offs for the reflection and connection pipeline."""

from typing import Literal

from pydantic import BaseModel, Field


class ReadingContext(BaseModel):
    work_id: str
    chapter_max: int = Field(ge=1)
    boundary_source: Literal["reader_confirmed"] = "reader_confirmed"


class ContextResolution(BaseModel):
    """What the router knows before it creates the spoiler-safe MuseTurn."""

    status: Literal["confirmed", "inferred", "unknown"]
    work_id: str | None = None
    work_title: str | None = None
    chapter_max: int | None = Field(default=None, ge=1)
    boundary_source: Literal["reader_confirmed", "inferred_from_question"] | None = None
    explanation: str


class TurnPolicy(BaseModel):
    spoiler_ceiling: int | None = Field(default=None, ge=1)
    allow_retrieval: bool
    allow_connection: bool
    allow_memory_capture: bool = False


class MuseTurn(BaseModel):
    """Fixed per-turn contract from the router to Muse."""

    turn_id: str
    user_message: str
    reading_context: ReadingContext | None
    policy: TurnPolicy


class ConnectionBrief(BaseModel):
    """The minimum context orchestration gives Serendipity for one bounded search."""

    cue: str = Field(min_length=1, max_length=2000)
    book_id: str | None = None
    chapter_max: int | None = Field(default=None, ge=1)
    intent: Literal["find_connection", "get_recommendation"] = "find_connection"
    allowed_sources: set[Literal["book_corpus"]] = {"book_corpus"}


class BookScope(BaseModel):
    """One corpus and its reader-confirmed spoiler boundary."""

    book_id: str
    chapter_max: int = Field(ge=1)


class LibrarianRequest(BaseModel):
    """Serendipity's bounded retrieval request to Librarian."""

    query: str = Field(min_length=1, max_length=2000)
    book_scopes: list[BookScope] = []
    purpose: Literal["connection_discovery"] = "connection_discovery"


class EvidenceItem(BaseModel):
    evidence_id: str
    source_title: str
    location: str
    chapter: int | None = None
    excerpt: str
    relevance: float = Field(ge=0, le=1)
    source_kind: Literal["book_corpus"] = "book_corpus"


class EvidenceBundle(BaseModel):
    items: list[EvidenceItem]
    retrieval_note: str


class CulturalSuggestion(BaseModel):
    kind: Literal["song"]
    title: str
    creator: str
    source_url: str
    rationale: str


class ConnectionProposal(BaseModel):
    status: Literal["proposal"] = "proposal"
    tentative_claim: str
    evidence_ids: list[str]
    interpretation: str
    uncertainty: Literal["low", "medium", "high"]
    suggested_follow_up: str
    cultural_suggestion: CulturalSuggestion | None = None


class ConnectionDecline(BaseModel):
    status: Literal["decline"] = "decline"
    reason: Literal["insufficient_evidence", "spoiler_boundary", "unsupported_cue"]
    safe_next_step: str


ConnectionResult = ConnectionProposal | ConnectionDecline
