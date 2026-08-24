"""Shared base for typed agent hand-off contracts."""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Reject schema drift and keep hand-off values immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class PromptFingerprint(StrictModel):
    """Versioned identity for one static prompt template and its contracts."""

    template_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def from_artifact(
        cls,
        *,
        template_id: str,
        version: str,
        instructions: str,
        input_contract: str,
        output_contract: str,
    ) -> "PromptFingerprint":
        """Hash only canonical instructions and static contract identities."""
        artifact = json.dumps(
            {
                "instructions": instructions,
                "input_contract": input_contract,
                "output_contract": output_contract,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return cls(
            template_id=template_id,
            version=version,
            digest=hashlib.sha256(artifact).hexdigest(),
        )
