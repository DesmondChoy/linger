"""Application-owned validation for offline Sculptor surfacing proposals."""

from pydantic_ai import Agent

from apps.backend.telemetry import run_agent_traced
from src.linger.agents.sculptor.surfacing_agent import surfacing_agent
from src.linger.agents.sculptor.surfacing_models import (
    InvalidSurfacingProposal as InvalidSurfacingProposal,
)
from src.linger.agents.sculptor.surfacing_models import (
    SurfacingDecision,
    SurfacingInput,
    validate_surfacing_decision,
)
from src.linger.agents.sculptor.surfacing_prompt import PROMPT_FINGERPRINT


async def propose_surfacing(
    input: SurfacingInput,
    *,
    agent: Agent[None, SurfacingDecision] = surfacing_agent,
) -> SurfacingDecision:
    """Obtain one decision without exposing account identity or granting tools."""
    result = await run_agent_traced(
        agent,
        input.model_dump_json(exclude={"account_scope"}),
        span_name="sculptor.surfacing",
        role="Sculptor",
        stage="surfacing",
        input_contract="src.linger.agents.sculptor.surfacing_models.SurfacingInput",
        output_contract="src.linger.agents.sculptor.surfacing_models.SurfacingDecision",
        prompt_template_id=PROMPT_FINGERPRINT.template_id,
        prompt_version=PROMPT_FINGERPRINT.version,
        prompt_digest=PROMPT_FINGERPRINT.digest,
        failure_code="sculptor_surfacing_model_failed",
        retryable=False,
    )
    return validate_surfacing_decision(input, result.output)
