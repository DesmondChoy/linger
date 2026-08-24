"""Sculptor, the proposal-only memory-curation agent."""

from pydantic_ai import Agent
from pydantic_ai.models import Model

from src.linger.agents.build import build_model
from src.linger.agents.sculptor.models import (
    CurationProposal,
    NoCurationProposal,
    SculptorResponse,
)
from src.linger.agents.sculptor.prompt import INSTRUCTIONS


def build_sculptor_agent(model: Model | None = None) -> Agent[None, SculptorResponse]:
    """Build Sculptor with the shared provider model and typed outputs."""
    return Agent[None, SculptorResponse](
        model if model is not None else build_model(),
        name="Sculptor",
        output_type=[CurationProposal, NoCurationProposal],
        instructions=INSTRUCTIONS,
    )


sculptor_agent = build_sculptor_agent()
