"""Application entry point for Serendipity's offline review of its own failures."""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from apps.backend.telemetry import run_agent_traced
from src.linger.agents.serendipity.agent import serendipity_agent
from src.linger.agents.serendipity.self_review_models import (
    SelfReviewInput,
    SkillCorrection,
    correction_errors,
)
from src.linger.agents.serendipity.skills import SELF_REVIEW

SELF_REVIEW_FINGERPRINT = SELF_REVIEW.fingerprint(template_id="serendipity.self-review")
# Offline review thinks harder than production discovery, as Sculptor's research does.
SELF_REVIEW_SETTINGS = OpenAIResponsesModelSettings(openai_reasoning_effort="high")


class InvalidSelfReview(ValueError):
    """Serendipity's correction breaks the application's contract after its retries."""


async def propose_skill_correction(
    task: SelfReviewInput, *, agent: Agent[Any, Any] = serendipity_agent,
) -> SkillCorrection:
    """Run the self-review skill without discovery dependencies, so no tool is offered."""
    result = await run_agent_traced(
        agent,
        task.model_dump_json(),
        span_name="serendipity.self_review",
        role="Serendipity",
        stage="self_review",
        input_contract="src.linger.agents.serendipity.self_review_models.SelfReviewInput",
        output_contract="src.linger.agents.serendipity.self_review_models.SkillCorrection",
        prompt_template_id=SELF_REVIEW_FINGERPRINT.template_id,
        prompt_digest=SELF_REVIEW_FINGERPRINT.digest,
        failure_code="serendipity_self_review_failed",
        retryable=False,
        model_settings=SELF_REVIEW_SETTINGS,
        deps=None,
        **SELF_REVIEW.run_options(),
    )
    correction = SkillCorrection.model_validate(result.output.model_dump())
    if errors := correction_errors(correction, task):
        raise InvalidSelfReview("; ".join(errors))
    return correction
