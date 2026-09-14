"""One reusable, no-tool Agent for Provenance's selected review skill."""

from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models import Model

from src.linger.agents.build import build_model
from src.linger.agents.provenance.skills import SHARED_INSTRUCTIONS


def build_provenance_agent(model: Model | None = None) -> Agent[None, Any]:
    """Build the role once; typed task entry points select each run's contract."""
    return Agent[None, Any](
        model if model is not None else build_model(),
        name="Provenance",
        instructions=SHARED_INSTRUCTIONS,
    )


provenance_agent = build_provenance_agent()
