"""Request and response bodies for the application API."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RequestBody(BaseModel):
    """Reject unexpected authority-bearing or stale request fields."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ChatRequest(RequestBody):
    session_id: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=8000)


class ChatResponse(BaseModel):
    reply: str


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
