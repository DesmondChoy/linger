"""Application-owned invocation of the emotional-boundary preflight."""

import json

from pydantic_ai import Agent

from apps.backend.telemetry import emotional_boundary_attrs, run_agent_traced
from src.linger.agents.provenance.emotional_prompt import (
    EMOTIONAL_BOUNDARY_PROMPT_FINGERPRINT,
)
from src.linger.contracts.emotional import (
    EmotionalBoundaryAssessment,
    EmotionalBoundaryInput,
    EmotionalContentPolicy,
)


class EmotionalBoundaryValidationError(ValueError):
    """Raised when the preflight result violates its application contract."""


async def assess_emotional_boundary(
    current_line: str,
    policy: EmotionalContentPolicy,
    *,
    provenance: Agent[None, EmotionalBoundaryAssessment],
) -> EmotionalBoundaryAssessment:
    """Classify one Line before Muse or any Muse-accessible tool can run."""
    preflight_input = EmotionalBoundaryInput(
        current_line=current_line,
        policy=policy,
    )
    result = await run_agent_traced(
        provenance,
        json.dumps(preflight_input.model_dump(mode="json"), ensure_ascii=False),
        span_name="provenance.emotional_boundary",
        role="Provenance",
        stage="emotional_boundary_preflight",
        input_contract="src.linger.contracts.emotional.EmotionalBoundaryInput",
        output_contract=(
            "src.linger.contracts.emotional.EmotionalBoundaryAssessment"
        ),
        prompt_template_id=EMOTIONAL_BOUNDARY_PROMPT_FINGERPRINT.template_id,
        prompt_version=EMOTIONAL_BOUNDARY_PROMPT_FINGERPRINT.version,
        prompt_digest=EMOTIONAL_BOUNDARY_PROMPT_FINGERPRINT.digest,
        failure_code="emotional_boundary_preflight_failed",
        result_attrs=lambda run_result: emotional_boundary_attrs(run_result.output),
    )
    try:
        return EmotionalBoundaryAssessment.model_validate(result.output)
    except Exception:
        raise EmotionalBoundaryValidationError(
            "Emotional boundary output is invalid"
        ) from None
