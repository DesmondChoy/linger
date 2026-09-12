"""Request-scoped, reader-confirmed turn context. Muse cannot author this."""

from __future__ import annotations

from typing import Literal

from src.linger.contracts.reading import ReadingScope

ReleaseSource = Literal[
    "muse_candidate",
    "application_clarification",
    "application_emotional_boundary",
    "application_safe_decline",
]


class ConfirmedReading(ReadingScope):
    """The reader-confirmed boundary, owned by the application. Muse cannot forge it."""

    work_id: str  # stable corpus work identifier (e.g. "pg11")


class ReleaseScope(ReadingScope):
    """Trusted book revision and spoiler ceiling for one release decision."""

    work_id: str
    book_version_id: str
