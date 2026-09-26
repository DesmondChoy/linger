"""Search-and-rank Serendipity agent over bounded Librarian and Exa tools."""

from pydantic_ai import Agent, ModelRetry, RunContext, Tool
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.models import Model

from src.linger.agents.build import build_model
from src.linger.agents.serendipity.models import (
    ConnectionDecline,
    ConnectionProposal,
    MemoryRecall,
    SerendipityResponse,
    SourceBundle,
)
from src.linger.agents.serendipity.skills import SHARED_INSTRUCTIONS
from src.linger.agents.serendipity.tools import (
    SerendipityDependencies,
    prepare_librarian_search,
    search_librarian,
    search_memories,
)


def _prepare_memory_search(
    ctx: RunContext[SerendipityDependencies],
    definition: ToolDefinition,
) -> ToolDefinition | None:
    """Expose memory search only when application code granted active records."""
    return definition if "memory" in ctx.deps.task.scope.allowed_sources else None


def _validate_bundle(
    ctx: RunContext[SerendipityDependencies], output: SourceBundle,
) -> SourceBundle:
    """Keep every Librarian-judged passage and opened page; cite only this run's records."""
    unknown_ids = sorted(set(output.evidence_ids) - set(ctx.deps.evidence))
    if unknown_ids:
        urls = [evidence_id for evidence_id in unknown_ids if evidence_id.startswith(("http://", "https://"))]
        if urls and "web" in ctx.deps.task.scope.allowed_sources:
            raise ModelRetry(
                "A web_search result is only a lead. Open each named page with get_page "
                f"before gathering it: {urls}. Then cite only evidence IDs recorded by get_page."
            )
        raise ModelRetry(
            "Every gathered evidence_id must exactly match evidence returned by a "
            f"search tool in this run. Remove or replace these unresolved IDs: {unknown_ids}."
        )
    omitted_books = sorted(
        evidence_id for evidence_id, item in ctx.deps.evidence.items()
        if item.source_kind == "book_corpus" and evidence_id not in output.evidence_ids
    )
    if omitted_books:
        raise ModelRetry(
            "Librarian already judged these book passages relevant to the sources the "
            f"reader named. Include every one of them in evidence_ids: {omitted_books}."
        )
    omitted_pages = sorted(set(ctx.deps.opened_web_evidence) - set(output.evidence_ids))
    if omitted_pages:
        raise ModelRetry(
            "You opened these pages for the public texts the reader named. An opened "
            f"page's evidence ID is its exact URL; include each one in evidence_ids: {omitted_pages}."
        )
    return output


def validate_serendipity_output(
    ctx: RunContext[SerendipityDependencies],
    output: SerendipityResponse,
) -> SerendipityResponse:
    """Retry results that mismatch the task, its evidence, or the winner's flags."""
    scope = ctx.deps.task.scope
    if scope.search_all_granted_books and not any(
        search.source == "book_corpus" for search in ctx.deps.searches
    ):
        raise ModelRetry(
            "The reader asked about their reading without naming books. Call "
            "search_librarian before answering; it searches every granted book."
        )
    if isinstance(output, ConnectionDecline):
        return output
    expected = {"recall_memory": MemoryRecall, "gather_sources": SourceBundle}.get(
        ctx.deps.task.intent, ConnectionProposal
    )
    if not isinstance(output, expected):
        raise ModelRetry(
            "A recall_memory task returns a recall or a decline; a gather_sources "
            "task returns a bundle or a decline; every other intent returns a "
            "proposal or a decline."
        )
    if isinstance(output, SourceBundle):
        return _validate_bundle(ctx, output)
    if isinstance(output, MemoryRecall):
        returned_ids = {
            item.evidence_id
            for item in ctx.deps.evidence.values()
            if item.source_kind == "memory"
        }
        unreturned_ids = sorted(set(output.evidence_ids) - returned_ids)
        if unreturned_ids:
            raise ModelRetry(
                "Every recalled evidence_id must exactly match a memory returned "
                "by search_memories in this run. Remove or replace these "
                f"unresolved IDs: {unreturned_ids}."
            )
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
    if scope.search_all_granted_books:
        winner_ids = set(output.selected_candidate.evidence_ids)
        if not any(ctx.deps.evidence[evidence_id].source_kind == "book_corpus" for evidence_id in winner_ids):
            books = sorted(
                evidence_id for evidence_id, item in ctx.deps.evidence.items()
                if item.source_kind == "book_corpus"
            )
            raise ModelRetry(
                "The reader asked whether anything they have read speaks to their question, "
                "so the selected candidate must cite a book passage that addresses the question "
                f"they actually ask. Librarian judged these passages relevant to it: {books}. "
                "Build the winning candidate on the one that speaks to that question, keeping "
                "the other sources the reader referred to."
                if books else
                "The reader asked whether anything they have read speaks to their question, but "
                "no book passage was returned, so no candidate can answer it. Decline."
            )
        omitted_pages = sorted(
            (set(ctx.deps.opened_web_evidence) & set(scope.web_source_urls or ())) - winner_ids
        )
        if omitted_pages:
            raise ModelRetry(
                "The selected candidate must also cite the public text the reader referred "
                f"to, whose opened page's evidence ID is its exact URL: {omitted_pages}."
            )
    winner_has_web = any(
        ctx.deps.evidence[evidence_id].source_kind == "web"
        for evidence_id in output.selected_candidate.evidence_ids
    )
    if winner_has_web != ("contains_web_claim" in output.policy_flags):
        action = "Include" if winner_has_web else "Remove"
        raise ModelRetry(
            f"{action} contains_web_claim in policy_flags to match the selected "
            "candidate's evidence. Evidence used only by another shortlisted "
            "candidate does not determine this flag."
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
        output_type=[ConnectionProposal, ConnectionDecline, MemoryRecall, SourceBundle],
        instructions=SHARED_INSTRUCTIONS,
        tools=[
            Tool(search_librarian, max_retries=1, prepare=prepare_librarian_search),
            Tool(search_memories, max_retries=1, prepare=_prepare_memory_search),
        ],
        retries=2,
    )
    agent.output_validator(validate_serendipity_output)
    return agent


serendipity_agent = build_serendipity_agent()
