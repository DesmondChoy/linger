"""Independent, no-tool Provenance gate for Sculptor proposals."""

from pydantic_ai import Agent
from pydantic_ai.models import Model

from src.linger.agents.build import build_model
from src.linger.agents.provenance.curation_models import CurationProvenanceReview
from src.linger.agents.provenance.curation_prompt import INSTRUCTIONS


def build_curation_provenance_agent(
    model: Model | None = None,
) -> Agent[None, CurationProvenanceReview]:
    """Build the read-only curation reviewer with a typed verdict."""

    return Agent[None, CurationProvenanceReview](
        model if model is not None else build_model(),
        name="Provenance",
        output_type=CurationProvenanceReview,
        instructions=INSTRUCTIONS,
    )


curation_provenance_agent = build_curation_provenance_agent()
