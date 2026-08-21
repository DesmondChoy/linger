"""Application-owned grants and validation around Serendipity search."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import uuid4

import logfire
from exa_py import AsyncExa
from pydantic import ValidationError

from apps.backend.config import REPO_ROOT, get_settings
from apps.backend.contracts import ConnectionBrief
from apps.backend.librarian import Librarian
from apps.backend.telemetry import (
    brief_attrs,
    record_failure,
    run_agent_traced,
    set_span_attrs,
)
from src.linger.agents.serendipity.agent import serendipity_agent
from src.linger.agents.serendipity.models import (
    SERENDIPITY_RESPONSE_ADAPTER,
    BookConnectionEvidence,
    BookEvidenceScope,
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
from src.linger.orchestration.turn_context import confirmed_reading, synthetic_reader_id
from src.linger.orchestration.inspection_context import (
    ConnectionRunInspection,
    cache_connection_result,
    cached_connection_result,
    record_connection_inspection,
)
from src.linger.orchestration.progress_context import emit_progress
from src.linger.services.memory import AccountContext, MemoryPolicyService

memory_service = MemoryPolicyService(REPO_ROOT / "memories")
librarian_service = Librarian()


@dataclass(frozen=True)
class ExplorationResult:
    """One agent decision plus the application-owned evidence/search ledger."""

    response: SerendipityResponse
    evidence: tuple[ConnectionEvidence, ...]
    searches: tuple[SearchTrace, ...]


Explorer = Callable[[ConnectionDiscoveryInput], Awaitable[ExplorationResult]]


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


def build_brief(cue: str) -> ConnectionBrief:
    """Attach application-owned source permissions to one Muse-supplied cue."""
    allowed_sources: set[str] = {"authorised_memory"}
    if web_reach_permitted():
        allowed_sources.add("web")

    reading = confirmed_reading()
    if reading is None:
        return ConnectionBrief(cue=cue, allowed_sources=allowed_sources)

    allowed_sources.add("book_corpus")
    return ConnectionBrief(
        cue=cue,
        book_id=reading.work_id,
        chapter_max=reading.chapter_max,
        allowed_sources=allowed_sources,
    )


def _build_task(brief: ConnectionBrief) -> ConnectionDiscoveryInput:
    """Clamp a brief to current application grants without retrieving evidence."""
    reading = confirmed_reading()
    allowed_sources: list[str] = ["authorised_memory"]
    book_scopes: tuple[BookEvidenceScope, ...] = ()

    if reading is not None:
        book_version_id = librarian_service.version_for(reading.work_id)
        if book_version_id is not None:
            ceiling = (
                min(brief.chapter_max, reading.chapter_max)
                if brief.chapter_max is not None
                else reading.chapter_max
            )
            allowed_sources.append("book_corpus")
            book_scopes = (
                BookEvidenceScope(
                    work_id=reading.work_id,
                    book_version_id=book_version_id,
                    chapter_max=ceiling,
                ),
            )

    if web_reach_permitted():
        allowed_sources.append("web")

    return ConnectionDiscoveryInput(
        request_id=f"serendipity-{uuid4().hex}",
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


async def _agent_explorer(task: ConnectionDiscoveryInput) -> ExplorationResult:
    """Let Serendipity choose bounded Librarian and optional Exa searches."""
    deps = SerendipityDependencies(
        task=task,
        librarian=librarian_service,
        memory_service=memory_service,
        account=AccountContext(account_id=get_settings().linger_account_id),
        synthetic_reader_id=synthetic_reader_id(),
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
    if not isinstance(evidence, BookConnectionEvidence):
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
    if isinstance(response, ConnectionDecline):
        return response
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
    if ("authorised_memory" in winner_kinds) != (
        "uses_authorised_memory" in flags
    ):
        raise InvalidConnectionResponse(
            "Serendipity's memory flag does not match the selected evidence"
        )
    if ("web" in winner_kinds) != ("contains_web_claim" in flags):
        raise InvalidConnectionResponse(
            "Serendipity's web flag does not match the selected evidence"
        )
    return response


async def connection_exploration(
    brief: ConnectionBrief,
    *,
    explorer: Explorer = _agent_explorer,
) -> ConnectionExplorationResult:
    """Run discovery and return its validated decision with exact evidence."""
    cached = cached_connection_result()
    if cached is not None:
        emit_progress(
            "Serendipity",
            "reuse_connection_decision",
            "complete",
            "The first request-scoped Serendipity decision is being reused.",
        )
        return cached

    task = _build_task(brief)
    traced_brief = brief.model_copy(
        update={
            "book_id": (
                task.scope.book_scopes[0].work_id
                if task.scope.book_scopes
                else None
            ),
            "chapter_max": (
                task.scope.book_scopes[0].chapter_max
                if task.scope.book_scopes
                else None
            ),
            "allowed_sources": set(task.scope.allowed_sources),
        }
    )

    with logfire.span("serendipity.connection", **brief_attrs(traced_brief)) as span:
        span.set_attribute("search.allowed_sources", list(task.scope.allowed_sources))
        run: ExplorationResult | None = None
        try:
            run = await explorer(task)
            emit_progress(
                "Serendipity",
                "validate_connection",
                "running",
                "The application is validating evidence scope and the selected connection.",
            )
            result = _validate_response(run, task)
        except Exception:
            emit_progress(
                "Serendipity",
                "validate_connection",
                "failed",
                "Connection validation failed closed.",
            )
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
                    brief=traced_brief.model_dump(mode="json"),
                    task=task.model_dump(mode="json"),
                    response=result.model_dump(mode="json"),
                    searches=tuple(
                        {
                            "source": search.source,
                            "tool": search.tool,
                            "request": search.request,
                            "outcome": search.outcome,
                            "evidence_ids": list(search.evidence_ids),
                        }
                        for search in (run.searches if run else ())
                    ),
                    evidence=tuple(
                        item.model_dump(mode="json")
                        for item in (run.evidence if run else ())
                    ),
                    failure_code="connection_discovery_failed",
                )
            )
            exploration_result = ConnectionExplorationResult(decision=result)
            cache_connection_result(exploration_result)
            return exploration_result

        emit_progress(
            "Serendipity",
            "connection_decision",
            "complete" if result.status == "proposal" else "declined",
            (
                "Serendipity returned one validated proposal to Muse."
                if result.status == "proposal"
                else "Serendipity returned a validated decline to Muse."
            ),
        )

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
                "serendipity.shortlist_size": len(result.shortlist),
            },
        )
        record_connection_inspection(
            ConnectionRunInspection(
                brief=traced_brief.model_dump(mode="json"),
                task=task.model_dump(mode="json"),
                response=result.model_dump(mode="json"),
                searches=tuple(
                    {
                        "source": search.source,
                        "tool": search.tool,
                        "request": search.request,
                        "outcome": search.outcome,
                        "evidence_ids": list(search.evidence_ids),
                    }
                    for search in run.searches
                ),
                evidence=tuple(
                    item.model_dump(mode="json") for item in run.evidence
                ),
            )
        )
        selected_evidence_ids = (
            set(result.selected_candidate.evidence_ids)
            if isinstance(result, ConnectionProposal)
            else set()
        )
        exploration_result = ConnectionExplorationResult(
            decision=result,
            evidence=tuple(
                item
                for item in run.evidence
                if item.evidence_id in selected_evidence_ids
            ),
        )
        cache_connection_result(exploration_result)
        return exploration_result


async def connection_proposal(
    brief: ConnectionBrief,
    *,
    explorer: Explorer = _agent_explorer,
) -> SerendipityResponse:
    """Return only the typed Serendipity decision for direct callers."""
    return (await connection_exploration(brief, explorer=explorer)).decision
