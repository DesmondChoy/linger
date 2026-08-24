"""No-tool Provenance agent for Linger's emotional-content boundary."""

from pydantic_ai import Agent
from pydantic_ai.models import Model

from src.linger.agents.build import build_model
from src.linger.agents.provenance.emotional_prompt import INSTRUCTIONS
from src.linger.contracts.emotional import EmotionalBoundaryAssessment


def build_emotional_boundary_agent(
    model: Model | None = None,
) -> Agent[None, EmotionalBoundaryAssessment]:
    """Build the independent preflight with typed output and no tools."""
    return Agent[None, EmotionalBoundaryAssessment](
        model if model is not None else build_model(),
        output_type=EmotionalBoundaryAssessment,
        instructions=INSTRUCTIONS,
    )


emotional_boundary_agent = build_emotional_boundary_agent()
