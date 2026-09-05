"""Sculptor's no-tool agent for offline surfacing proposals."""

from pydantic_ai import Agent
from pydantic_ai.models import Model

from src.linger.agents.build import build_model
from src.linger.agents.sculptor.surfacing_models import (
    Defer,
    DoNotSurface,
    SurfaceNow,
    SurfacingDecision,
)
from src.linger.agents.sculptor.surfacing_prompt import INSTRUCTIONS


def build_surfacing_agent(model: Model | None = None) -> Agent[None, SurfacingDecision]:
    return Agent[None, SurfacingDecision](
        model if model is not None else build_model(),
        name="Sculptor",
        output_type=[SurfaceNow, Defer, DoNotSurface],
        instructions=INSTRUCTIONS,
    )


surfacing_agent = build_surfacing_agent()
