"""Content identities for agent instructions and contracts."""

from __future__ import annotations

from pydantic import Field

from src.linger.contracts import base


class PromptFingerprint(base.StrictModel):
    """Content identity for one static prompt template and its contracts."""

    template_id: str = Field(min_length=1)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
