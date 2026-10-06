"""Application-owned validation for offline Sculptor chapter-cue revisions."""

from typing import Any

from pydantic_ai import Agent

from apps.backend.telemetry import run_agent_traced
from src.linger.agents.sculptor.agent import sculptor_agent
from src.linger.agents.sculptor.chapter_cue_models import (
    ChapterCueRevision,
    ChapterCueRevisionInput,
    InvalidChapterCueRevision,
    task_errors,
)
from src.linger.agents.sculptor.skills import CHAPTER_CUES

PROMPT_FINGERPRINT = CHAPTER_CUES.fingerprint(template_id="sculptor.chapter_cues")


async def propose_chapter_cues(
    task: ChapterCueRevisionInput,
    *,
    agent: Agent[None, Any] = sculptor_agent,
) -> ChapterCueRevision:
    """Return revised cues for every chapter; a human approves before search reads them."""
    result = await run_agent_traced(
        agent,
        task.model_dump_json(),
        span_name="sculptor.chapter_cues",
        role="Sculptor",
        stage="chapter_cues",
        input_contract="src.linger.agents.sculptor.chapter_cue_models.ChapterCueRevisionInput",
        output_contract="src.linger.agents.sculptor.chapter_cue_models.ChapterCueRevision",
        prompt_template_id=PROMPT_FINGERPRINT.template_id,
        prompt_digest=PROMPT_FINGERPRINT.digest,
        failure_code="sculptor_chapter_cues_model_failed",
        retryable=False,
        **CHAPTER_CUES.run_options(),
    )
    revision = ChapterCueRevision.model_validate(result.output.model_dump())
    errors = task_errors(revision, task)
    if errors:
        raise InvalidChapterCueRevision("; ".join(errors))
    return revision
