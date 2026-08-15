"""Typed agent hand-offs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Reject unknown fields and forbid mutation after construction."""

    model_config = ConfigDict(extra="forbid", frozen=True)
