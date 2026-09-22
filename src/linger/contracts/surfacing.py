"""Typed application hand-off from memory surfacing to Muse."""

from typing import Self

from pydantic import Field, model_validator

from src.linger.agents.contracts import StrictModel
from src.linger.contracts.connection_evidence import MemoryConnectionEvidence


class MemorySurfacingHandoff(StrictModel):
    """One validated suggestion and the exact memories supporting it."""

    suggestion: str = Field(min_length=1, max_length=8_000)
    source_memory_ids: tuple[str, ...] = Field(min_length=1, max_length=12)
    sources: tuple[MemoryConnectionEvidence, ...] = Field(
        min_length=1,
        max_length=12,
    )

    @model_validator(mode="after")
    def require_exact_unique_sources(self) -> Self:
        source_ids = tuple(source.evidence_id for source in self.sources)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("surfacing sources must be unique")
        if source_ids != self.source_memory_ids:
            raise ValueError("surfacing sources must match the selected IDs in order")
        return self
