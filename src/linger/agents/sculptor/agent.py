"""One reusable Sculptor Agent; application entry points select its skill."""

import json
from typing import Any

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.models import Model
from pydantic_ai.output import OutputContext

from src.linger.agents.build import build_model
from src.linger.agents.security import ProviderRequestPrivacyGuard
from src.linger.agents.sculptor.chapter_cue_models import (
    ChapterCueRevision,
    ChapterCueRevisionInput,
    task_errors,
)
from src.linger.agents.sculptor.research_models import (
    ErrorAnalysis,
    ErrorAnalysisInput,
    error_analysis_errors,
)
from src.linger.agents.sculptor.skills import SHARED_INSTRUCTIONS


class SculptorTaskValidation(AbstractCapability[None]):
    """Repair input-bound coverage errors within the chapter-cue and error-analysis runs."""

    async def after_output_validate(
        self, ctx: RunContext[None], *, output_context: OutputContext, output: Any,
    ) -> Any:
        if not isinstance(output, (ChapterCueRevision, ErrorAnalysis)):
            return output
        if not isinstance(ctx.prompt, str):
            raise ValueError("Sculptor output validation requires the typed task prompt")
        errors = (
            task_errors(output, ChapterCueRevisionInput.model_validate_json(ctx.prompt))
            if isinstance(output, ChapterCueRevision)
            else error_analysis_errors(output, ErrorAnalysisInput.model_validate_json(ctx.prompt))
        )
        if errors:
            raise ModelRetry(json.dumps({
                "error": "The output breaks the application's contract.",
                "errors": errors,
            }, ensure_ascii=False))
        return output


def build_sculptor_agent(model: Model | None = None) -> Agent[None, str]:
    """Build the role for production or injected-model tests and evaluations."""
    return Agent[None, str](
        model if model is not None else build_model(),
        name="Sculptor",
        instructions=SHARED_INSTRUCTIONS,
        capabilities=[SculptorTaskValidation(), ProviderRequestPrivacyGuard()],
    )


sculptor_agent = build_sculptor_agent()
