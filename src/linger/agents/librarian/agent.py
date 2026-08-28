"""Librarian's independent, set-level evidence-strength judge."""

from pydantic_ai import Agent

from src.linger.agents.build import build_model
from src.linger.agents.librarian.boundary_prompt import INSTRUCTIONS as BOUNDARY_INSTRUCTIONS
from src.linger.agents.librarian.models import (
    BoundaryInferenceDecision,
    EvidenceStrengthDecision,
)
from src.linger.agents.librarian.prompt import INSTRUCTIONS


librarian_strength_agent: Agent[None, EvidenceStrengthDecision] = Agent(
    build_model(),
    name="Librarian",
    output_type=EvidenceStrengthDecision,
    instructions=INSTRUCTIONS,
)


librarian_boundary_agent: Agent[None, BoundaryInferenceDecision] = Agent(
    build_model(),
    name="Librarian",
    output_type=BoundaryInferenceDecision,
    instructions=BOUNDARY_INSTRUCTIONS,
)
