"""Search-and-rank Serendipity agent over bounded Librarian and Exa tools."""

from pydantic_ai import Agent, ModelRetry, RunContext, Tool
from pydantic_ai.models import Model

from src.linger.agents.build import build_model
from src.linger.agents.serendipity.models import (
    ConnectionDecline,
    ConnectionProposal,
    SerendipityResponse,
)
from src.linger.agents.serendipity.prompt import INSTRUCTIONS
from src.linger.agents.serendipity.tools import (
    SerendipityDependencies,
    search_librarian,
)


def validate_serendipity_output(
    ctx: RunContext[SerendipityDependencies],
    output: SerendipityResponse,
) -> SerendipityResponse:
    """Retry proposals that cite leads instead of retrieved run evidence."""
    if isinstance(output, ConnectionDecline):
        return output
    cited_ids = {
        evidence_id
        for candidate in output.shortlist
        for evidence_id in candidate.evidence_ids
    }
    unknown_ids = cited_ids - set(ctx.deps.evidence)
    if unknown_ids:
        urls = sorted(
            evidence_id
            for evidence_id in unknown_ids
            if evidence_id.startswith(("http://", "https://"))
        )
        if urls and "web" in ctx.deps.task.scope.allowed_sources:
            raise ModelRetry(
                "A web_search result is only a lead. Before citing these URLs, "
                f"open each selected page with get_page: {urls}. Then return a "
                "shortlist citing only evidence IDs recorded by get_page."
            )
        raise ModelRetry(
            "Every shortlisted evidence_id must exactly match evidence returned "
            "by a search tool in this run. Remove or replace these unresolved "
            f"IDs: {sorted(unknown_ids)}."
        )
    return output


def build_serendipity_agent(
    model: Model | None = None,
) -> Agent[SerendipityDependencies, SerendipityResponse]:
    """Build Serendipity with bounded internal search and typed outputs."""
    agent = Agent[SerendipityDependencies, SerendipityResponse](
        model if model is not None else build_model(),
        name="Serendipity",
        deps_type=SerendipityDependencies,
        output_type=[ConnectionProposal, ConnectionDecline],
        instructions=INSTRUCTIONS,
        tools=[Tool(search_librarian, max_retries=1)],
        retries=2,
    )
    agent.output_validator(validate_serendipity_output)
    return agent


serendipity_agent = build_serendipity_agent()
