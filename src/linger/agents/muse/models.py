"""Typed Muse output used by the application release boundary."""

from typing import Literal

from pydantic import Field

from src.linger.agents.contracts import StrictModel


class EvidenceUse(StrictModel):
    """One book-corpus record Muse declares as support for its reply."""

    source_kind: Literal["book_corpus"]
    evidence_id: str = Field(min_length=1, max_length=200)
    source_location: str = Field(min_length=1, max_length=500)
    exact_quote: str | None = Field(default=None, min_length=1, max_length=2_000)


class MuseCandidate(StrictModel):
    """A complete visible reply plus untrusted evidence declarations."""

    reply: str = Field(min_length=1, max_length=20_000)
    evidence_uses: tuple[EvidenceUse, ...] = ()
