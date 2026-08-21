"""Bounded Librarian and Exa tools for Serendipity discovery."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn
from pydantic_ai.toolsets import AbstractToolset, ToolsetTool, WrapperToolset
from pydantic_ai_harness.exa import ExaSearch

from apps.backend.contracts import BookScope, LibrarianRequest
from apps.backend.librarian import Librarian
from src.linger.agents.serendipity.models import (
    BookConnectionEvidence,
    ConnectionDiscoveryInput,
    ConnectionEvidence,
    InternalSearchResult,
    InternalSourceKind,
    MemoryConnectionEvidence,
    SearchSourceKind,
    WebConnectionEvidence,
)
from src.linger.services.memory import AccountContext, MemoryPolicyService
from src.linger.orchestration.progress_context import emit_progress
from src.linger.synthetic_readers import (
    synthetic_memory_evidence,
    synthetic_memory_texts,
)

MAX_RESULTS_PER_SOURCE = 5
PRIVATE_QUERY_WINDOW = 6
TOKEN = re.compile(r"[^\W_]+(?:[’'-][^\W_]+)*", re.UNICODE)


@dataclass(frozen=True)
class SearchTrace:
    """Inspectable record of one bounded search operation during the run."""

    source: SearchSourceKind
    outcome: str
    evidence_ids: tuple[str, ...]
    tool: str = "search_librarian"
    request: dict[str, object] = field(default_factory=dict)


@dataclass
class SerendipityDependencies:
    """Trusted services and mutable evidence ledger hidden from the model."""

    task: ConnectionDiscoveryInput
    librarian: Librarian
    memory_service: MemoryPolicyService
    account: AccountContext
    synthetic_reader_id: str | None = None
    evidence: dict[str, ConnectionEvidence] = field(default_factory=dict)
    searches: list[SearchTrace] = field(default_factory=list)

    def record(
        self,
        source: SearchSourceKind,
        outcome: str,
        evidence: tuple[ConnectionEvidence, ...],
        *,
        tool: str,
        request: dict[str, object],
    ) -> None:
        for item in evidence:
            existing = self.evidence.get(item.evidence_id)
            if existing is not None and existing != item:
                raise ValueError("a run evidence ID resolved to conflicting records")
            self.evidence[item.evidence_id] = item
        self.searches.append(
            SearchTrace(
                source=source,
                outcome=outcome,
                evidence_ids=tuple(item.evidence_id for item in evidence),
                tool=tool,
                request=request,
            )
        )

    def record_search(
        self,
        source: SearchSourceKind,
        outcome: str,
        evidence_ids: tuple[str, ...] = (),
        *,
        tool: str,
        request: dict[str, object],
    ) -> None:
        """Record a search that does not itself yield citable evidence."""
        self.searches.append(
            SearchTrace(
                source=source,
                outcome=outcome,
                evidence_ids=evidence_ids,
                tool=tool,
                request=request,
            )
        )


def _book_evidence(bundle: Any) -> tuple[BookConnectionEvidence, ...]:
    return tuple(
        BookConnectionEvidence(
            evidence_id=item.evidence_id,
            source_title=item.source_title,
            work_id=item.work_id,
            book_version_id=item.book_version_id,
            chapter=item.chapter,
            location=item.location,
            source_sha256=item.source_sha256,
            source_lines=item.source_lines,
            excerpt=item.excerpt,
        )
        for item in bundle.items
    )


def _memory_evidence(records: Any) -> tuple[MemoryConnectionEvidence, ...]:
    return tuple(
        MemoryConnectionEvidence(
            evidence_id=record.evidence_id,
            excerpt=record.excerpt,
            capture_type=record.capture_type,
            recorded_at=record.recorded_at,
        )
        for record in records
    )


def search_librarian(
    ctx: RunContext[SerendipityDependencies],
    query: str,
    sources: tuple[InternalSourceKind, ...],
    max_results_per_source: int = MAX_RESULTS_PER_SOURCE,
) -> InternalSearchResult:
    """Search permitted books and authorised memories through Librarian.

    Args:
        query: A concise search query derived from the current connection cue.
        sources: One or both internal sources to search.
        max_results_per_source: Maximum records returned by each source.

    Returns:
        Several eligible book and memory records, or a bounded no-evidence or
        partial-failure result.
    """
    if not query.strip():
        raise ModelRetry("Librarian search requires a non-empty query.")
    if not sources or len(sources) != len(set(sources)):
        raise ModelRetry("Choose one or more unique Librarian sources.")

    permitted = set(ctx.deps.task.scope.allowed_sources)
    forbidden = set(sources) - permitted
    if forbidden:
        raise ModelRetry(
            f"These internal sources were not granted: {sorted(forbidden)}"
        )

    limit = max(1, min(max_results_per_source, MAX_RESULTS_PER_SOURCE))
    evidence: list[ConnectionEvidence] = []
    unavailable: list[InternalSourceKind] = []

    if "authorised_memory" in sources:
        emit_progress(
            "Librarian",
            "authorised_memory_search",
            "running",
            "Librarian is searching authorised memories.",
        )
        try:
            records = list(ctx.deps.librarian.retrieve_memories(
                query,
                memory_service=ctx.deps.memory_service,
                account=ctx.deps.account,
                max_results=limit,
            ))
            if ctx.deps.synthetic_reader_id is not None:
                records.extend(
                    synthetic_memory_evidence(
                        ctx.deps.synthetic_reader_id,
                        query,
                        limit=limit,
                    )
                )
            records.sort(
                key=lambda record: (
                    record.relevance,
                    record.recorded_at,
                    record.evidence_id,
                ),
                reverse=True,
            )
        except Exception:
            unavailable.append("authorised_memory")
            emit_progress(
                "Librarian",
                "authorised_memory_search",
                "failed",
                "The authorised-memory search was unavailable.",
            )
        else:
            memory_items = _memory_evidence(records[:limit])
            evidence.extend(memory_items)
            ctx.deps.record(
                "authorised_memory",
                "evidence_found" if memory_items else "no_evidence",
                memory_items,
                tool="search_librarian",
                request={
                    "query": query,
                    "sources": list(sources),
                    "max_results_per_source": limit,
                },
            )
            emit_progress(
                "Librarian",
                "authorised_memory_search",
                "complete",
                f"Librarian returned {len(memory_items)} authorised memory records.",
            )

    if "book_corpus" in sources:
        emit_progress(
            "Librarian",
            "book_corpus_search",
            "running",
            "Librarian is searching the spoiler-bounded book corpus.",
        )
        try:
            request = LibrarianRequest(
                query=query,
                book_scopes=[
                    BookScope(
                        work_id=scope.work_id,
                        book_version_id=scope.book_version_id,
                        chapter_max=scope.chapter_max,
                    )
                    for scope in ctx.deps.task.scope.book_scopes
                ],
                max_results=limit,
            )
            bundle = ctx.deps.librarian.retrieve(request)
        except Exception:
            unavailable.append("book_corpus")
            emit_progress(
                "Librarian",
                "book_corpus_search",
                "failed",
                "The bounded book-corpus search was unavailable.",
            )
        else:
            book_items = _book_evidence(bundle)
            evidence.extend(book_items)
            ctx.deps.record(
                "book_corpus",
                "evidence_found" if book_items else "no_evidence",
                book_items,
                tool="search_librarian",
                request={
                    "query": query,
                    "sources": list(sources),
                    "max_results_per_source": limit,
                },
            )
            emit_progress(
                "Librarian",
                "book_corpus_search",
                "complete",
                f"Librarian returned {len(book_items)} spoiler-safe book records.",
            )

    if unavailable:
        outcome = "partial_failure"
    elif evidence:
        outcome = "evidence_found"
    else:
        outcome = "no_evidence"
    return InternalSearchResult(
        query=query,
        searched_sources=sources,
        outcome=outcome,
        evidence=tuple(evidence),
        unavailable_sources=tuple(unavailable),
    )


def _normalised_tokens(text: str) -> tuple[str, ...]:
    return tuple(token.casefold() for token in TOKEN.findall(text))


def _query_copies_private_memory(
    query: str,
    deps: SerendipityDependencies,
) -> bool:
    query_tokens = _normalised_tokens(query)
    if not query_tokens:
        return False
    query_text = " ".join(query_tokens)
    try:
        records = deps.memory_service.list_active(deps.account)
    except Exception:
        return True

    private_texts = [record.text for record in records]
    if deps.synthetic_reader_id is not None:
        try:
            private_texts.extend(synthetic_memory_texts(deps.synthetic_reader_id))
        except Exception:
            return True

    for private_text in private_texts:
        memory_tokens = _normalised_tokens(private_text)
        if len(memory_tokens) >= 3 and " ".join(memory_tokens) in query_text:
            return True
        if len(memory_tokens) < PRIVATE_QUERY_WINDOW:
            continue
        windows = (
            memory_tokens[start : start + PRIVATE_QUERY_WINDOW]
            for start in range(len(memory_tokens) - PRIVATE_QUERY_WINDOW + 1)
        )
        if any(" ".join(window) in query_text for window in windows):
            return True
    return False


@dataclass
class GuardedExaToolset(WrapperToolset[SerendipityDependencies]):
    """Wrap maintained Exa tools with Linger's privacy gate and evidence ledger."""

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[SerendipityDependencies],
        tool: ToolsetTool[SerendipityDependencies],
    ) -> Any:
        if "web" not in ctx.deps.task.scope.allowed_sources:
            raise ModelRetry("Public-web search was not granted for this request.")
        if name == "web_search":
            query = str(tool_args.get("query", ""))
            if _query_copies_private_memory(query, ctx.deps):
                raise ModelRetry(
                    "That web query contains private memory wording. Search using "
                    "only a general, non-identifying concept from the current cue."
                )

        emit_progress(
            "Exa",
            name,
            "running",
            (
                "Exa is searching the public web for candidate sources."
                if name == "web_search"
                else "Exa is opening a candidate page for citable evidence."
            ),
        )
        try:
            result = await super().call_tool(name, tool_args, ctx, tool)
        except Exception:
            emit_progress(
                "Exa",
                name,
                "failed",
                "The public-web operation could not be completed.",
            )
            raise
        if not isinstance(result, ToolReturn):
            emit_progress(
                "Exa",
                name,
                "complete",
                "Exa completed the public-web operation.",
            )
            return result
        metadata = result.metadata if isinstance(result.metadata, dict) else {}
        raw_sources = metadata.get("sources", [])
        if not isinstance(raw_sources, list):
            raw_sources = []
        excerpt = str(result.return_value)[:8_000]
        evidence: list[ConnectionEvidence] = []
        for raw_source in raw_sources:
            if not isinstance(raw_source, dict):
                continue
            url = raw_source.get("url")
            if not isinstance(url, str) or not url or len(url) > 2_000:
                continue
            raw_title = raw_source.get("title")
            title = raw_title if isinstance(raw_title, str) and raw_title else url
            title = title[:500]
            evidence.append(
                WebConnectionEvidence(
                    evidence_id=url,
                    title=title,
                    url=url,
                    excerpt=excerpt,
                )
            )
        web_evidence = tuple(evidence)
        outcome = "evidence_found" if web_evidence else "no_evidence"
        if name == "get_page":
            # A search result is a lead, not sufficient evidence. Only a page
            # Serendipity actually opened enters the citable ledger.
            ctx.deps.record(
                "web",
                outcome,
                web_evidence,
                tool="get_page",
                request={"url": str(tool_args.get("url", ""))},
            )
        else:
            ctx.deps.record_search(
                "web",
                outcome,
                tuple(item.evidence_id for item in web_evidence),
                tool="web_search",
                request={"query": str(tool_args.get("query", ""))},
            )
        emit_progress(
            "Exa",
            name,
            "complete",
            (
                f"Exa returned {len(web_evidence)} candidate web leads."
                if name == "web_search"
                else f"Exa opened a page and returned {len(web_evidence)} citable records."
            ),
        )
        return result


class GuardedExaSearch(ExaSearch):
    """The maintained Exa capability with Linger-specific boundary checks."""

    def get_toolset(self) -> AbstractToolset[SerendipityDependencies]:
        return GuardedExaToolset(super().get_toolset())
