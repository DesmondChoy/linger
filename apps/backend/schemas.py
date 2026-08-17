"""Request and response bodies for the application API."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.linger.agents.provenance.models import RiskCode


class RequestBody(BaseModel):
    """Reject unexpected authority-bearing or stale request fields."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ChatRequest(RequestBody):
    session_id: str = Field(min_length=1, max_length=200)
    turn_id: str | None = Field(default=None, min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=8000)


class ReleaseInspection(BaseModel):
    """Content-free metadata describing the application release decision."""

    model_config = ConfigDict(extra="forbid")

    release_source: Literal["muse_candidate", "application_safe_decline"]
    provenance_verdicts: tuple[Literal["pass", "revise", "reject"], ...]
    finding_codes: tuple[RiskCode, ...]
    revision_count: int = Field(ge=0, le=1)
    failure_stage: Literal["muse_draft", "provenance_review", "muse_revision"] | None


class TurnInspection(BaseModel):
    """Read-only record of the contracts used for one released response."""

    muse_turn: dict[str, Any]
    context_resolution: dict[str, Any]
    traces: list[dict[str, str]]
    connection_brief: dict[str, Any] | None = None
    librarian_request: dict[str, Any] | None = None
    evidence_bundle: dict[str, Any] | None = None
    connection_proposal: dict[str, Any] | None = None
    prompt: str
    release: ReleaseInspection | None = None


class ChatResponse(BaseModel):
    reply: str
    inspection: TurnInspection


class MemoryWriteRequest(RequestBody):
    text: str = Field(min_length=1, max_length=8000)
    operation_id: UUID


class CapturePreferenceRequest(RequestBody):
    enabled: bool


class CapturePreferenceResponse(BaseModel):
    enabled: bool


class MemoryResponse(BaseModel):
    memory_id: str
    text: str
    capture_type: Literal["explicit", "automatic", "correction"]
    evidence_ids: list[str]
    created_at: str
    updated_at: str


class MemorySaveResponse(BaseModel):
    memory: MemoryResponse
    created: bool


class MemoryStateResponse(BaseModel):
    capture_enabled: bool
    memories: list[MemoryResponse]
