"""Application entry points for Sculptor's offline retrieval error analysis and research."""

from __future__ import annotations

from typing import Any

from exa_py import AsyncExa
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from apps.backend.config import get_settings
from apps.backend.telemetry import run_agent_traced
from src.linger.agents.sculptor.agent import sculptor_agent
from src.linger.agents.sculptor.research_models import (
    ErrorAnalysis,
    ErrorAnalysisInput,
    ResearchInput,
    ResearchSpecification,
    error_analysis_errors,
    specification_errors,
)
from src.linger.agents.sculptor.research_search import ResearchLedger, ResearchSearch
from src.linger.agents.sculptor.skills import RETRIEVAL_ERROR_ANALYSIS, RETRIEVAL_RESEARCH

ERROR_ANALYSIS_FINGERPRINT = RETRIEVAL_ERROR_ANALYSIS.fingerprint(template_id="sculptor.retrieval_error_analysis")
RESEARCH_FINGERPRINT = RETRIEVAL_RESEARCH.fingerprint(template_id="sculptor.retrieval_research")
# Owner decision: offline research thinks harder than production tasks.
RESEARCH_SETTINGS = OpenAIResponsesModelSettings(openai_reasoning_effort="high")
WEB_RESULTS = 5


class InvalidResearch(ValueError):
    """Sculptor's output breaks the application's contract after its retries."""


async def propose_error_analysis(
    task: ErrorAnalysisInput, *, agent: Agent[None, Any] = sculptor_agent,
) -> ErrorAnalysis:
    result = await run_agent_traced(
        agent,
        task.model_dump_json(),
        span_name="sculptor.retrieval_error_analysis",
        role="Sculptor",
        stage="retrieval_error_analysis",
        input_contract="src.linger.agents.sculptor.research_models.ErrorAnalysisInput",
        output_contract="src.linger.agents.sculptor.research_models.ErrorAnalysis",
        prompt_template_id=ERROR_ANALYSIS_FINGERPRINT.template_id,
        prompt_digest=ERROR_ANALYSIS_FINGERPRINT.digest,
        failure_code="sculptor_error_analysis_failed",
        retryable=False,
        model_settings=RESEARCH_SETTINGS,
        **RETRIEVAL_ERROR_ANALYSIS.run_options(),
    )
    analysis = ErrorAnalysis.model_validate(result.output.model_dump())
    if errors := error_analysis_errors(analysis, task):
        raise InvalidResearch("; ".join(errors))
    return analysis


def research_search(ledger: ResearchLedger) -> ResearchSearch:
    key = get_settings().exa_api_key
    if key is None or not key.get_secret_value().strip():
        raise RuntimeError("EXA_API_KEY is required for retrieval research")
    return ResearchSearch(
        num_results=WEB_RESULTS, max_text_chars=8_000, include_deep_search=False,
        client=AsyncExa(api_key=key.get_secret_value().strip()), guidance="", ledger=ledger,
    )


async def propose_research(
    task: ResearchInput, *, search: ResearchSearch, agent: Agent[None, Any] = sculptor_agent,
) -> ResearchSpecification:
    result = await run_agent_traced(
        agent,
        task.model_dump_json(),
        span_name="sculptor.retrieval_research",
        role="Sculptor",
        stage="retrieval_research",
        input_contract="src.linger.agents.sculptor.research_models.ResearchInput",
        output_contract="src.linger.agents.sculptor.research_models.ResearchSpecification",
        prompt_template_id=RESEARCH_FINGERPRINT.template_id,
        prompt_digest=RESEARCH_FINGERPRINT.digest,
        failure_code="sculptor_research_failed",
        retryable=False,
        model_settings=RESEARCH_SETTINGS,
        capabilities=[search],
        **RETRIEVAL_RESEARCH.run_options(),
    )
    specification = ResearchSpecification.model_validate(result.output.model_dump())
    if errors := specification_errors(specification, task, set(search.ledger.opened)):
        raise InvalidResearch("; ".join(errors))
    return specification
