"""One reusable, no-tool Agent for Provenance's selected review skill."""

from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.models import Model
from pydantic_ai.output import OutputContext

from src.linger.agents.build import build_model
from src.linger.agents.provenance.models import ProvenanceReview
from src.linger.agents.provenance.review_context import review_input
from src.linger.agents.provenance.review_validation import validate_provenance_review
from src.linger.agents.provenance.skills import SHARED_INSTRUCTIONS


class CandidateReviewValidation(AbstractCapability[None]):
    """Repair input-bound review defects inside the selected output budget."""

    async def after_output_validate(
        self, ctx: RunContext[None], *, output_context: OutputContext, output: Any,
    ) -> Any:
        if not isinstance(output, ProvenanceReview):
            return output
        if review_input() is None and not isinstance(ctx.prompt, str):
            raise ValueError("Candidate review requires the typed current review input")
        return validate_provenance_review(ctx, output)


def build_provenance_agent(model: Model | None = None) -> Agent[None, Any]:
    """Build the role once; typed task entry points select each run's contract."""
    return Agent[None, Any](
        model if model is not None else build_model(),
        name="Provenance",
        instructions=SHARED_INSTRUCTIONS,
        capabilities=[CandidateReviewValidation()],
    )


provenance_agent = build_provenance_agent()
