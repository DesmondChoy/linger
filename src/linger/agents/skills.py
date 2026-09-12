"""Immutable bindings for application-selected agent tasks.

This module reads packaged instructions and describes run configuration. Typed
role entry points own invocation, context projection, and domain validation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any, Generic, TypeVar

from pydantic import TypeAdapter
from pydantic_ai import AgentRetries
from pydantic_ai.output import OutputSpec

from src.linger.agents.contracts import PromptFingerprint

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


def load_instructions(package: str, resource: str) -> str:
    """Read trusted package data without consulting the working directory."""
    return files(package).joinpath(resource).read_text(encoding="utf-8").strip()


@dataclass(frozen=True)
class RuntimeSkill(Generic[InputT, OutputT]):
    """One assigned task, its effective instructions, and its model contract."""

    role: str
    name: str
    shared_instructions: str
    instructions: str
    input_type: type[InputT]
    output_type: OutputSpec[OutputT]
    # Registered output validators require the agent's fixed output contract.
    override_output: bool = True
    tools: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    validators: tuple[str, ...] = ()
    output_retries: int = 1
    tool_retries: int = 1

    @property
    def skill_id(self) -> str:
        return f"{self.role.lower()}.{self.name}"

    @property
    def effective_instructions(self) -> str:
        return f"{self.shared_instructions}\n{self.instructions}"

    def run_options(self) -> dict[str, Any]:
        """Return fresh per-run options; never mutate a reusable Agent."""
        retries: AgentRetries = {
            "output": self.output_retries,
            "tools": self.tool_retries,
        }
        options: dict[str, Any] = {
            "instructions": self.instructions,
            "retries": retries,
            "metadata": {"linger_skill": self.skill_id},
        }
        if self.override_output:
            options["output_type"] = self.output_type
        return options

    def fingerprint(
        self,
        *,
        template_id: str | None = None,
        input_type: Any = None,
        version: str = "1",
    ) -> PromptFingerprint:
        """Identify shared and selected policy, schemas, and execution limits."""
        output = self.output_type
        if isinstance(output, (list, tuple)):
            from functools import reduce
            from operator import or_

            output = reduce(or_, output)
        artifact = {
            "skill": self.skill_id,
            "instructions": self.effective_instructions,
            "input_schema": TypeAdapter(input_type or self.input_type).json_schema(),
            "output_schema": TypeAdapter(output).json_schema(),
            "tools": self.tools,
            "capabilities": self.capabilities,
            "validators": self.validators,
            "output_retries": self.output_retries,
            "tool_retries": self.tool_retries,
        }
        digest = hashlib.sha256(
            json.dumps(artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            .encode("utf-8")
        ).hexdigest()
        return PromptFingerprint(
            template_id=template_id or self.skill_id,
            version=version,
            digest=digest,
        )
