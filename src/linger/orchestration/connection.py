"""Application-owned grants and validation around Serendipity search."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import logfire
from exa_py import AsyncExa
from pydantic import ValidationError
from pydantic_ai import UsageLimits

from apps.backend.config import get_settings
from apps.backend.contracts import BookScope, ConnectionBrief, EvidenceItem
from apps.backend.librarian import Librarian
from apps.backend.telemetry import (
    connection_scope_attrs,
    record_failure,
    run_agent_traced,
    set_span_attrs,
)
from src.linger.agents.serendipity.agent import serendipity_agent
from src.linger.agents.serendipity.models import (
    SERENDIPITY_RESPONSE_ADAPTER,
    ConnectionDecline,
    ConnectionDiscoveryInput,
    ConnectionEvidence,
    ConnectionExplorationResult,
    ConnectionProposal,
    ConnectionScope,
    DeclineReason,
    SerendipityResponse,
)
from src.linger.agents.serendipity.tools import (
    GuardedExaSearch,
    SearchTrace,
    SerendipityDependencies,
)
from src.linger.orchestration.grounding import (
    evidence_record_from_item,
    librarian_service,
)
from src.linger.orchestration.inspection_context import (
    ConnectionRunInspection,
    cache_connection_result,
    cached_connection_result,
    record_connection_inspection,
)
from src.linger.orchestration.turn_context import add_turn_evidence, confirmed_reading


@dataclass(frozen=True)
class ExplorationResult:
    """One agent decision plus the application-owned evidence/search ledger."""

    response: SerendipityResponse
    evidence: tuple[ConnectionEvidence, ...]
    searches: tuple[SearchTrace, ...]


Explorer = Callable[[ConnectionDiscoveryInput], Awaitable[ExplorationResult]]
SERENDIPITY_REQUEST_LIMIT = 8
SERENDIPITY_TOOL_CALL_LIMIT = 6


class InvalidConnectionResponse(ValueError):
    """Raised when Serendipity escapes its grants or search results."""


def _decline(reason: DeclineReason, safe_next_step: str) -> ConnectionDecline:
    return ConnectionDecline(reason=reason, safe_next_step=safe_next_step)


def web_reach_permitted() -> bool:
    """Whether application policy and credentials permit Exa for this run."""
    settings = get_settings()
    key = settings.exa_api_key
    return (
        settings.linger_web_search_enabled
        and key is not None
        and bool(key.get_secret_value().strip())
    )


def _build_task(
    brief: ConnectionBrief,
    *,
    librarian: Librarian,
) -> ConnectionDiscoveryInput:
    """Clamp a brief to current application grants without retrieving evidence."""
    reading = confirmed_reading()
    allowed_sources: list[str] = []
    book_scopes: tuple[BookScope, ...] = ()

    if reading is not None:
        book_version_id = librarian.version_for(reading.work_id)
        if book_version_id is not None:
            allowed_sources.append("book_corpus")
            book_scopes = (
                BookScope(
                    work_id=reading.work_id,
                    book_version_id=book_version_id,
                    chapter_max=reading.chapter_max,
                ),
            )

    if web_reach_permitted():
        allowed_sources.append("web")

    return ConnectionDiscoveryInput(
        cue=brief.cue,
        intent=brief.intent,
        presentation=(
            "direct" if brief.intent == "get_recommendation" else "ask_before_showing"
        ),
        scope=ConnectionScope(
            allowed_sources=tuple(allowed_sources),
            book_scopes=book_scopes,
        ),
    )


def _web_capability() -> GuardedExaSearch:
    settings = get_settings()
    key = settings.exa_api_key
    if key is None or not key.get_secret_value().strip():
        raise RuntimeError("EXA_API_KEY is required when web search is enabled")
    return GuardedExaSearch(
        num_results=5,
        max_text_chars=8_000,
        include_deep_search=False,
        client=AsyncExa(api_key=key.get_secret_value().strip()),
        guidance=(
            "Use web_search only for a public connection that could materially "
            "deepen the current cue. Read promising pages with get_page. Never "
            "put private memory wording or identifying reader details in a query."
        ),
    )


async def _agent_explorer(
    task: ConnectionDiscoveryInput,
    *,
    librarian: Librarian,
) -> ExplorationResult:
    """Let Serendipity choose bounded Librarian and optional Exa searches."""
    deps = SerendipityDependencies(
        task=task,
        librarian=librarian,
    )
    capabilities = [_web_capability()] if "web" in task.scope.allowed_sources else []
    result = await run_agent_traced(
        serendipity_agent,
        task.model_dump_json(),
        span_name="serendipity.discovery",
        role="Serendipity",
        stage="search_rank_select",
        prompt_template_id="serendipity.search-rank-select",
        failure_code="serendipity_model_failed",
        retryable=False,
        deps=deps,
        capabilities=capabilities,
        usage_limits=UsageLimits(
            request_limit=SERENDIPITY_REQUEST_LIMIT,
            tool_calls_limit=SERENDIPITY_TOOL_CALL_LIMIT,
        ),
    )
    try:
        response = SERENDIPITY_RESPONSE_ADAPTER.validate_python(result.output)
    except ValidationError:
        raise InvalidConnectionResponse("Serendipity returned malformed output") from None
    return ExplorationResult(
        response=response,
        evidence=tuple(deps.evidence.values()),
        searches=tuple(deps.searches),
    )


def _evidence_is_in_scope(
    evidence: ConnectionEvidence,
    task: ConnectionDiscoveryInput,
) -> bool:
    if evidence.source_kind not in task.scope.allowed_sources:
        return False
    if not isinstance(evidence, EvidenceItem):
        return True
    ceilings = {
        (scope.work_id, scope.book_version_id): scope.chapter_max
        for scope in task.scope.book_scopes
    }
    ceiling = ceilings.get((evidence.work_id, evidence.book_version_id))
    return ceiling is not None and evidence.chapter <= ceiling


def _validate_response(
    run: ExplorationResult,
    task: ConnectionDiscoveryInput,
) -> SerendipityResponse:
    """Validate search provenance, shortlist citations, and winner flags."""
    evidence = {item.evidence_id: item for item in run.evidence}
    if len(evidence) != len(run.evidence):
        raise InvalidConnectionResponse("search tools returned duplicate evidence IDs")
    if any(not _evidence_is_in_scope(item, task) for item in run.evidence):
        raise InvalidConnectionResponse("search evidence exceeded its trusted grant")

    response = run.response
    if isinstance(response, ConnectionDecline):
        return _decline(
            response.reason,
            "No connection cleared the current evidence and safety checks.",
        )
    candidates = response.shortlist
    cited_ids = {
        evidence_id
        for candidate in candidates
        for evidence_id in candidate.evidence_ids
    }
    unknown_ids = cited_ids - set(evidence)
    if unknown_ids:
        raise InvalidConnectionResponse(
            f"Serendipity referenced unknown evidence: {sorted(unknown_ids)}"
        )
    if response.presentation != task.presentation:
        raise InvalidConnectionResponse("Serendipity changed the presentation policy")

    if not run.searches:
        raise InvalidConnectionResponse(
            "Serendipity proposed without searching a permitted source"
        )

    winner_kinds = {
        evidence[evidence_id].source_kind
        for evidence_id in response.selected_candidate.evidence_ids
    }
    flags = set(response.policy_flags)
    if ("web" in winner_kinds) != ("contains_web_claim" in flags):
        raise InvalidConnectionResponse(
            "Serendipity's web flag does not match the selected evidence"
        )
    return response


def _book_search_outcomes(searches: tuple[SearchTrace, ...]) -> tuple[str, ...]:
    return tuple(
        search.outcome for search in searches if search.source == "book_corpus"
    )


async def connection_exploration(
    brief: ConnectionBrief,
    *,
    explorer: Explorer | None = None,
    librarian: Librarian = librarian_service,
) -> ConnectionExplorationResult:
    """Run discovery and return its validated decision with exact evidence."""
    cached = cached_connection_result()
    if cached is not None:
        cached_intent, cached_result = cached
        if cached_intent == brief.intent:
            return cached_result
        return ConnectionExplorationResult(
            decision=_decline(
                "retrieval_unavailable",
                "A different connection request already ran for this turn.",
            )
        )

    task = _build_task(brief, librarian=librarian)
    cancelled = False
    with logfire.span(
        "serendipity.connection", **connection_scope_attrs(task)
    ) as span:
        span.set_attribute("search.allowed_sources", list(task.scope.allowed_sources))
        run: ExplorationResult | None = None
        try:
            if not task.scope.allowed_sources:
                run = ExplorationResult(
                    response=_decline(
                        "no_permitted_evidence",
                        "Confirm a book or enable bounded public-web search first.",
                    ),
                    evidence=(),
                    searches=(),
                )
            elif explorer is not None:
                run = await explorer(task)
            else:
                run = await _agent_explorer(task, librarian=librarian)
            result = _validate_response(run, task)
            selected_evidence_ids = (
                set(result.selected_candidate.evidence_ids)
                if isinstance(result, ConnectionProposal)
                else set()
            )
            selected_evidence = tuple(
                item
                for item in run.evidence
                if item.evidence_id in selected_evidence_ids
            )
            add_turn_evidence(
                evidence_record_from_item(item)
                for item in selected_evidence
                if isinstance(item, EvidenceItem)
            )
        except asyncio.CancelledError:
            cancelled = True
            record_failure(
                span,
                stage="serendipity_discovery",
                code="request_cancelled",
                retryable=False,
                failure_type="application",
            )
            span.set_attribute("tool.status", "failure")
        except Exception:
            record_failure(
                span,
                stage="serendipity_discovery",
                code="connection_discovery_failed",
                retryable=False,
                failure_type="application",
            )
            span.set_attribute("tool.status", "failure")
            result = _decline(
                "retrieval_unavailable",
                "The permitted sources could not be searched and compared safely.",
            )
            record_connection_inspection(
                ConnectionRunInspection(
                    status="decline",
                    reason=result.reason,
                    book_search_outcomes=_book_search_outcomes(
                        run.searches if run else ()
                    ),
                    failure_code="connection_discovery_failed",
                )
            )
            exploration_result = ConnectionExplorationResult(decision=result)
            cache_connection_result(brief.intent, exploration_result)
            return exploration_result

        if not cancelled:
            set_span_attrs(
                span,
                {
                    "status": "success" if result.status == "proposal" else "decline",
                    "tool.status": "success" if result.status == "proposal" else "decline",
                    "retrieval.outcome": result.status,
                    "retrieval.item_count": len(run.evidence),
                    "search.source_kinds": sorted(
                        {search.source for search in run.searches}
                    ),
                    "serendipity.shortlist_size": (
                        len(result.shortlist)
                        if isinstance(result, ConnectionProposal)
                        else 0
                    ),
                },
            )
            record_connection_inspection(
                ConnectionRunInspection(
                    status=result.status,
                    reason=(
                        result.reason if isinstance(result, ConnectionDecline) else None
                    ),
                    book_search_outcomes=_book_search_outcomes(run.searches),
                )
            )
            exploration_result = ConnectionExplorationResult(
                decision=result,
                evidence=selected_evidence,
            )
            cache_connection_result(brief.intent, exploration_result)
            return exploration_result

    raise asyncio.CancelledError
