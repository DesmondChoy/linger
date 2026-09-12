"""One reusable Sculptor Agent; application entry points select its skill."""

from pydantic_ai import Agent
from pydantic_ai.models import Model

from src.linger.agents.build import build_model
from src.linger.agents.sculptor.skills import SHARED_INSTRUCTIONS


def build_sculptor_agent(model: Model | None = None) -> Agent[None, str]:
    """Build the role for production or injected-model tests and evaluations."""
    return Agent[None, str](
        model if model is not None else build_model(),
        name="Sculptor",
        instructions=SHARED_INSTRUCTIONS,
    )


sculptor_agent = build_sculptor_agent()
