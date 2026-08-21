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
    """A reader cue plus the source kinds orchestration may search for it."""

    cue: str = Field(min_length=1, max_length=2000)
    book_id: str | None = None
    chapter_max: int | None = Field(default=None, ge=1)
    intent: Literal["find_connection", "get_recommendation"] = "find_connection"
    allowed_sources: set[
        Literal["authorised_memory", "book_corpus", "web"]
    ] = {"authorised_memory"}


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


class EvidenceBundle(BaseModel):
    items: list[EvidenceItem]
    retrieval_note: str


class MemoryEvidenceItem(BaseModel):
    """One active account-owned memory returned by Librarian."""

    evidence_id: str
    excerpt: str
    capture_type: Literal["explicit", "automatic", "correction"]
    recorded_at: str
    relevance: float = Field(ge=0, le=1)
