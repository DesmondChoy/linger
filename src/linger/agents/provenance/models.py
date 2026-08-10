"""Typed Provenance hand-off contracts."""

from typing import Literal

from pydantic import BaseModel, Field


class ProvenanceVerdict(BaseModel):
    decision: Literal["pass", "revise", "reject"]
    critique: str = Field(default="", max_length=2_000)
