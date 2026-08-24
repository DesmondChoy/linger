"""Librarian's independent, set-level evidence-strength judge."""

from pydantic_ai import Agent

from src.linger.agents.build import build_model
from src.linger.agents.librarian.models import EvidenceStrengthDecision
from src.linger.agents.librarian.prompt import INSTRUCTIONS


librarian_strength_agent: Agent[None, EvidenceStrengthDecision] = Agent(
    build_model(),
    name="Librarian",
    output_type=EvidenceStrengthDecision,
    instructions=INSTRUCTIONS,
)
