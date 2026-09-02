"""Independent semantic release gate for every Muse candidate."""

from pydantic_ai import Agent
from pydantic_ai.models import Model

from src.linger.agents.build import build_model
from src.linger.agents.provenance.models import ProvenanceReview
from src.linger.agents.provenance.prompt import INSTRUCTIONS


def build_provenance_agent(model: Model | None = None) -> Agent[None, ProvenanceReview]:
    """Build Provenance with the shared provider model and typed outputs."""
    return Agent[None, ProvenanceReview](
        model if model is not None else build_model(),
        name="Provenance",
        output_type=ProvenanceReview,
        instructions=INSTRUCTIONS,
        retries={"output": 2},
    )


provenance_agent = build_provenance_agent()
