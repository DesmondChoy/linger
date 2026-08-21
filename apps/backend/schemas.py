"""Request and response bodies for the application API."""

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

from src.linger.agents.provenance.models import RiskCode


class RequestBody(BaseModel):
    """Reject unexpected authority-bearing or stale request fields."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ChatRequest(RequestBody):
    session_id: str = Field(min_length=1, max_length=200)
    turn_id: str | None = Field(default=None, min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=8000)


class CaptureInspection(BaseModel):
    """Content-free outcome for the three automatic-capture stages."""

    model_config = ConfigDict(extra="forbid")

    nomination: Literal["candidate", "no_candidate", "unavailable"]
    provenance_decision: Literal[
        "allow_capture", "reject_capture", "no_candidate"
    ] | None
    binding: Literal["exact", "not_applicable", "invalid"]
    storage: Literal["committed", "refused", "not_applicable"]
    reason_code: str | None


class ReleaseInspection(BaseModel):
    """Content-free metadata describing the application release decision."""

    model_config = ConfigDict(extra="forbid")

    release_source: Literal["muse_candidate", "application_safe_decline"]
    provenance_verdicts: tuple[Literal["pass", "revise", "reject"], ...]
    finding_codes: tuple[RiskCode, ...]
    revision_count: int = Field(ge=0, le=1)
    failure_stage: Literal[
        "muse_draft",
        "provenance_review",
        "muse_revision",
        "deterministic_validation",
    ] | None
    capture: CaptureInspection


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


class MemoryCaptureNotice(BaseModel):
    """Application-authored disclosure for one committed automatic capture."""

    notice: Literal["Saved to your memories."] = "Saved to your memories."


class ChatResponse(BaseModel):
    reply: str
    inspection: TurnInspection
    memory_capture: MemoryCaptureNotice | None = None
