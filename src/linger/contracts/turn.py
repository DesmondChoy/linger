"""Request-scoped, reader-confirmed turn context. Muse cannot author this."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from src.linger.contracts.base import StrictModel

ReleaseSource = Literal[
    "muse_candidate",
    "application_clarification",
    "application_emotional_boundary",
    "application_safe_decline",
]


class ConfirmedReading(StrictModel):
    """The reader-confirmed boundary, owned by the application. Muse cannot forge it."""

    work_id: str  # stable corpus work identifier (e.g. "pg11")
    chapter_max: int = Field(ge=1)


class ReleaseScope(StrictModel):
    """Trusted book revision and spoiler ceiling for one release decision."""

    work_id: str
    book_version_id: str
    chapter_max: int = Field(ge=1)
