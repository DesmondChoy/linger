"""Request-scoped, reader-confirmed turn context. Muse cannot author this."""

from __future__ import annotations

from pydantic import Field

from src.linger.contracts.base import StrictModel


class ConfirmedReading(StrictModel):
    """The reader-confirmed boundary, owned by the application. Muse cannot forge it."""

    work_id: str  # the shipped corpus key (e.g. "alice-adventures-in-wonderland")
    chapter_max: int = Field(ge=1)
