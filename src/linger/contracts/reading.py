"""Reading-position contract shared by Muse and Librarian."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from src.linger.contracts.base import StrictModel


class ReadingBoundary(StrictModel):
    """A reader's confirmed position, at chapter granularity."""

    chapter_number: int = Field(ge=1)
    chapter_state: Literal["started", "completed"]
