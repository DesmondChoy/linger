"""Bounded Librarian and Exa tools for Serendipity discovery."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn
from pydantic_ai.toolsets import AbstractToolset, ToolsetTool, WrapperToolset
from pydantic_ai_harness.exa import ExaSearch
from pydantic_ai_harness.guardrails.detectors import (
    redact_personal_data,
    redact_secrets,
)

from apps.backend.contracts import BookScope, EvidenceItem, LibrarianRequest
from apps.backend.librarian import Librarian
from src.linger.agents.serendipity.models import (
    ConnectionDiscoveryInput,
    ConnectionEvidence,
    InternalSearchResult,
    SearchSourceKind,
    WebConnectionEvidence,
)

MAX_RESULTS_PER_SOURCE = 5
MAX_WEB_QUERY_CHARS = 500
TOKEN = re.compile(r"[^\W_]+(?:[’'-][^\W_]+)*", re.UNICODE)


def _normalised_tokens(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", text)
    return tuple(token.casefold() for token in TOKEN.findall(normalized))


def _query_copies_reader_terms(query: str, cue: str) -> bool:
    """Require the model to generalise the cue before external search."""
    query_terms = {token for token in _normalised_tokens(query) if len(token) > 1}
    cue_terms = {token for token in _normalised_tokens(cue) if len(token) > 1}
    return bool(query_terms & cue_terms)


def _query_contains_private_data(query: str) -> bool:
    """Use maintained detectors for shaped personal data and credentials."""
    return any(
        detector(query).action != "allow"
        for detector in (redact_personal_data, redact_secrets)
    )


@dataclass(frozen=True)
class SearchTrace:
    """Content-free outcome of one bounded search operation during the run."""

    source: SearchSourceKind
    outcome: str


@dataclass
class SerendipityDependencies:
    """Trusted services and mutable evidence ledger hidden from the model."""

    task: ConnectionDiscoveryInput
    librarian: Librarian
    evidence: dict[str, ConnectionEvidence] = field(default_factory=dict)
    searches: list[SearchTrace] = field(default_factory=list)
    web_leads: set[str] = field(default_factory=set)

    def record(
        self,
        source: SearchSourceKind,
        outcome: str,
        evidence: tuple[ConnectionEvidence, ...],
    ) -> None:
        for item in evidence:
            existing = self.evidence.get(item.evidence_id)
            if existing is not None and existing != item:
                raise ValueError("a run evidence ID resolved to conflicting records")
            self.evidence[item.evidence_id] = item
        self.searches.append(SearchTrace(source=source, outcome=outcome))

    def record_search(
        self,
        source: SearchSourceKind,
        outcome: str,
    ) -> None:
        """Record a search that does not itself yield citable evidence."""
        self.searches.append(SearchTrace(source=source, outcome=outcome))


def search_librarian(
    ctx: RunContext[SerendipityDependencies],
    query: str,
    max_results_per_source: int = MAX_RESULTS_PER_SOURCE,
) -> InternalSearchResult:
    """Search the permitted book scope through Librarian.

    Args:
        query: A concise search query derived from the current connection cue.
        max_results_per_source: Maximum records returned by each source.

    Returns:
        Several eligible book records, or a bounded no-evidence or
        retrieval-failure result.
    """
    if not query.strip():
        raise ModelRetry("Librarian search requires a non-empty query.")
    if "book_corpus" not in ctx.deps.task.scope.allowed_sources:
        raise ModelRetry("Book-corpus search was not granted for this request.")

    limit = max(1, min(max_results_per_source, MAX_RESULTS_PER_SOURCE))
    try:
        request = LibrarianRequest(
            query=query,
            book_scopes=list(ctx.deps.task.scope.book_scopes),
            max_results=limit,
            purpose="connection_discovery",
        )
        bundle = ctx.deps.librarian.retrieve(request)
    except Exception:
        ctx.deps.record_search(
            "book_corpus",
            "retrieval_unavailable",
        )
        return InternalSearchResult(
            outcome="retrieval_unavailable",
        )

    book_items: tuple[EvidenceItem, ...] = tuple(bundle.items)
    ctx.deps.record(
        "book_corpus",
        "evidence_found" if book_items else "no_evidence",
        book_items,
    )
    return InternalSearchResult(
        outcome="evidence_found" if book_items else "no_evidence",
        evidence=book_items,
    )


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
            query = str(tool_args.get("query", "")).strip()
            if not query or len(query) > MAX_WEB_QUERY_CHARS:
                raise ModelRetry(
                    "Use one concise, non-empty public-web query of at most "
                    f"{MAX_WEB_QUERY_CHARS} characters."
                )
            if _query_contains_private_data(query) or _query_copies_reader_terms(
                query, ctx.deps.task.cue
            ):
                raise ModelRetry(
                    "Rewrite the web query using only a general, non-identifying "
                    "concept; do not copy the reader's wording or personal data."
                )
        elif name == "get_page":
            requested_url = str(tool_args.get("url", "")).strip()
            if requested_url not in ctx.deps.web_leads:
                raise ModelRetry(
                    "get_page may open only an exact URL returned by web_search "
                    "during this Serendipity run."
                )

        try:
            result = await super().call_tool(name, tool_args, ctx, tool)
        except Exception:
            ctx.deps.record_search(
                "web",
                "retrieval_unavailable",
            )
            raise
        if not isinstance(result, ToolReturn):
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
            if (
                not isinstance(url, str)
                or not url.startswith(("http://", "https://"))
                or len(url) > 2_000
            ):
                continue
            if name == "get_page" and url not in ctx.deps.web_leads:
                continue
            raw_title = raw_source.get("title")
            title = raw_title if isinstance(raw_title, str) and raw_title else url
            title = title[:500]
            evidence.append(
                WebConnectionEvidence(
                    evidence_id=url,
                    title=title,
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
            )
        else:
            ctx.deps.web_leads.update(item.evidence_id for item in web_evidence)
            ctx.deps.record_search(
                "web",
                outcome,
            )
        return result


class GuardedExaSearch(ExaSearch):
    """The maintained Exa capability with Linger-specific boundary checks."""

    def get_toolset(self) -> AbstractToolset[SerendipityDependencies]:
        return GuardedExaToolset(super().get_toolset())
