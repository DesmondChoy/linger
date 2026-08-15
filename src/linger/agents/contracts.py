"""Shared base for typed agent hand-off contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Reject schema drift and keep hand-off values immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)
