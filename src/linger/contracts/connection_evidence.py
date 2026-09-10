"""Frozen source records shared by discovery and independent release review."""

from typing import Annotated, Literal

from pydantic import Field

from src.linger.agents.contracts import StrictModel


class WebConnectionEvidence(StrictModel):
    """One retrievable public-web record returned by Exa."""

    source_kind: Literal["web"] = "web"
    evidence_id: str = Field(min_length=1, max_length=2_000)
    title: str = Field(min_length=1, max_length=500)
    excerpt: str = Field(min_length=1, max_length=8_000)
    trust_level: Literal["external"] = "external"


class MemoryConnectionEvidence(StrictModel):
    """One active record authorized by the account-scoped memory service."""

    source_kind: Literal["memory"] = "memory"
    evidence_id: str = Field(min_length=1, max_length=200)
    excerpt: str = Field(min_length=1, max_length=8_000)
    trust_level: Literal["account_scoped"] = "account_scoped"



ConnectionSourceEvidence = Annotated[
    MemoryConnectionEvidence | WebConnectionEvidence,
    Field(discriminator="source_kind"),
]
