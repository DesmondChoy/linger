"""Bounded Librarian and Exa tools for Serendipity discovery."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Any
from urllib.parse import unquote, urlsplit

from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import AbstractToolset, ToolsetTool, WrapperToolset
from pydantic_ai_harness.exa import ExaSearch

from apps.backend.librarian import Librarian
from src.linger.agents.serendipity.models import (
    ConnectionDiscoveryInput,
    ConnectionEvidence,
    InternalSearchResult,
    MemoryConnectionEvidence,
    MemorySearchResult,
    SearchSourceKind,
    WebConnectionEvidence,
)
from src.linger.contracts.curation import CuratedMemory
from src.linger.contracts.privacy import contains_personal_data_or_secret
from src.linger.contracts.session import ReaderStatement
from src.linger.corpus import registry
from src.linger.evaluation_transcript import ConnectionEvaluationEvent, record_connection_event
from src.linger.orchestration.book_evidence import retrieve_book_evidence
from src.linger.orchestration.evidence_strength import StrengthJudge
from src.linger.orchestration.progress_context import emit_progress

MAX_RESULTS_PER_SOURCE = 5
MAX_WEB_QUERY_CHARS = 500
TOKEN = re.compile(r"[^\W_]+(?:[’'-][^\W_]+)*", re.UNICODE)
PUBLIC_URL_TOKEN = re.compile(r"(?<![\w/:?&#=+.%~-])https?://[^\s<>\"`]+")
# At or below this length, treat every word of the reader's text as private.
SHORT_PRIVATE_TEXT_TOKENS = 8
# Consecutive reader words that count as copied wording rather than shared topic.
COPIED_PHRASE_TOKENS = 3


def _normalised_tokens(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", text)
    return tuple(token.casefold() for token in TOKEN.findall(normalized))


def _phrases(tokens: tuple[str, ...], size: int) -> set[tuple[str, ...]]:
    return {tokens[index : index + size] for index in range(len(tokens) - size + 1)}


def _without_exact_public_url(text: str, url: str) -> str:
    """Exclude a complete reader-supplied locator, preserving surrounding text."""
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password
        ):
            return text
    except ValueError:
        return text

    def omit_locator(match: re.Match[str]) -> str:
        token = match.group()
        locator = token
        while locator:
            if locator == url:
                return " " + token[len(locator):]
            # A final sentence mark or unmatched link bracket is outside the URL.
            closing = {")": "(", "]": "[", "}": "{"}.get(locator[-1])
            if locator[-1] in ".,;:!?'”’" or (
                closing is not None and locator.count(locator[-1]) > locator.count(closing)
            ):
                locator = locator[:-1]
            else:
                break
        return token

    return PUBLIC_URL_TOKEN.sub(omit_locator, text)


def _query_copies_reader_terms(
    query: str, source: str, *, page_url: str | None = None,
) -> bool:
    """Refuse a query that carries the reader's own wording to a public search.

    How private a single shared word is depends on how much the reader wrote.
    "Li and I divorced" is four words and all of it is private, so reusing any
    of them names a real person. A long message about a book is mostly public,
    and refusing every shared word there blocked every usable query over
    ordinary vocabulary such as "why" or "error". So short text is protected
    word by word, and longer text is protected against runs of consecutive
    words, which is how copied phrasing actually escapes. A query shorter than
    that run must not reproduce the reader's wording in full either.

    For a page open, only its exact locator in reader context is excluded;
    surrounding wording remains private. Memory callers never exclude locators.
    """
    if page_url is not None:
        source = _without_exact_public_url(source, page_url)
    query_tokens = _normalised_tokens(query)
    source_tokens = _normalised_tokens(source)
    if not query_tokens or not source_tokens:
        return False
    if len(source_tokens) <= SHORT_PRIVATE_TEXT_TOKENS:
        query_terms = {token for token in query_tokens if len(token) > 1}
        source_terms = {token for token in source_tokens if len(token) > 1}
        return bool(query_terms & source_terms)
    size = min(COPIED_PHRASE_TOKENS, len(query_tokens))
    if len(source_tokens) < size:
        return False
    return bool(_phrases(query_tokens, size) & _phrases(source_tokens, size))


@dataclass(frozen=True)
class SearchTrace:
    """Content-free outcome of one bounded search operation during the run."""

    source: SearchSourceKind
    outcome: str
    operation: str


_SEARCH_STAGES = {
    "search_memories": "memory_search",
    "search_librarian": "book_corpus_search",
    "web_search": "web_search",
    "get_page": "get_page",
}
_SEARCH_RECEIVERS: dict[SearchSourceKind, str] = {
    "memory": "Application",
    "book_corpus": "Librarian",
    "web": "Exa",
}


def _emit_search_progress(
    source: SearchSourceKind,
    operation: str,
    outcome: str,
) -> None:
    """Report one completed Serendipity search as content-free progress."""
    emit_progress(
        "Serendipity",
        _SEARCH_STAGES.get(operation, "processing"),
        "complete" if outcome == "evidence_found"
        else "declined" if outcome == "no_evidence"
        else "failed",
        f"Serendipity searched {source}.",
        input_origin="Serendipity",
        output_receiver=_SEARCH_RECEIVERS.get(source, "Application"),
    )


@dataclass
class SerendipityDependencies:
    """Trusted services and mutable evidence ledger hidden from the model."""

    task: ConnectionDiscoveryInput
    librarian: Librarian
    memories: tuple[CuratedMemory, ...] = ()
    strength_judge: StrengthJudge | None = None
    prior_reader_statements: tuple[ReaderStatement, ...] = ()
    evidence: dict[str, ConnectionEvidence] = field(default_factory=dict)
    searches: list[SearchTrace] = field(default_factory=list)
    web_leads: set[str] = field(default_factory=set)
    opened_web_evidence: dict[str, WebConnectionEvidence] = field(default_factory=dict)

    def record(
        self,
        source: SearchSourceKind,
        operation: str,
        outcome: str,
        evidence: tuple[ConnectionEvidence, ...],
    ) -> None:
        for item in evidence:
            existing = self.evidence.get(item.evidence_id)
            if existing is not None and existing != item:
                raise ValueError("a run evidence ID resolved to conflicting records")
            self.evidence[item.evidence_id] = item
        self.searches.append(
            SearchTrace(source=source, operation=operation, outcome=outcome)
        )
        _emit_search_progress(source, operation, outcome)
        record_connection_event(ConnectionEvaluationEvent(
            kind="search", status=outcome, source=source, operation=operation,
            evidence_json=tuple(item.model_dump_json() for item in evidence),
        ))

    def record_search(
        self,
        source: SearchSourceKind,
        operation: str,
        outcome: str,
    ) -> None:
        """Record a search that does not itself yield citable evidence."""
        self.searches.append(
            SearchTrace(source=source, operation=operation, outcome=outcome)
        )
        _emit_search_progress(source, operation, outcome)
        record_connection_event(ConnectionEvaluationEvent(
            kind="search", status=outcome, source=source, operation=operation,
        ))


def search_memories(
    ctx: RunContext[SerendipityDependencies],
    query: str,
    max_results_per_source: int = MAX_RESULTS_PER_SOURCE,
) -> MemorySearchResult:
    """Search only the application's account-scoped curated retrieval view."""
    if not query.strip():
        raise ModelRetry("Memory search requires a non-empty query.")
    if "memory" not in ctx.deps.task.scope.allowed_sources:
        raise ModelRetry("Memory search was not granted for this request.")
    query_terms = set(_normalised_tokens(query))
    ranked = sorted(
        (
            (len(query_terms & set(_normalised_tokens(record.text))), record)
            for record in ctx.deps.memories
        ),
        key=lambda item: (-item[0], item[1].memory_id),
    )
    limit = max(1, min(max_results_per_source, MAX_RESULTS_PER_SOURCE))
    evidence = tuple(
        MemoryConnectionEvidence(
            evidence_id=record.memory_id,
            excerpt=record.text,
        )
        for overlap, record in ranked[:limit]
        if overlap > 0
    )
    outcome = "evidence_found" if evidence else "no_evidence"
    ctx.deps.record("memory", "search_memories", outcome, evidence)
    return MemorySearchResult(outcome=outcome, evidence=evidence)


def prepare_librarian_search(
    ctx: RunContext[SerendipityDependencies],
    definition: ToolDefinition,
) -> ToolDefinition:
    """Name only the trusted book grants available for this discovery run."""
    work_ids = dict.fromkeys(scope.work_id for scope in ctx.deps.task.scope.book_scopes)
    if not work_ids:
        return definition
    books = [
        f"- {registry.CORPORA[work_id].book.title if work_id in registry.CORPORA else work_id}: {work_id}"
        for work_id in work_ids
    ]
    return replace(definition, description=(definition.description or "") + (
        "\n\nAvailable book titles and work_ids (permission only; select named books "
        "or plausible sources for reader-requested discovery):\n" + "\n".join(books)
    ))


async def search_librarian(
    ctx: RunContext[SerendipityDependencies],
    max_results_per_source: int = MAX_RESULTS_PER_SOURCE,
    work_ids: tuple[str, ...] | None = None,
) -> InternalSearchResult:
    """Find book support for the application-supplied reader cue.

    Librarian identifies the requested book material from the original cue and
    prior reader statements before searching the permitted scope. The caller
    cannot replace the reader's question. For named-book requests, select those
    books. When the reader asks to discover a textual connection without naming
    books, select plausible sources; the whole granted library may be explored.
    work_ids selects a nonempty, unique subset of the available book IDs. It is
    required when multiple books are available; permission does not request a survey.
    max_results_per_source limits the selected records, not reading permission.
    """
    if "book_corpus" not in ctx.deps.task.scope.allowed_sources:
        raise ModelRetry("Book-corpus search was not granted for this request.")

    book_scopes = ctx.deps.task.scope.book_scopes
    granted_work_ids = {scope.work_id for scope in book_scopes}
    if work_ids is None:
        if len(granted_work_ids) > 1:
            raise ModelRetry("Select books with work_ids when multiple books are available.")
    else:
        if not work_ids or len(work_ids) != len(set(work_ids)):
            raise ModelRetry("work_ids must contain a nonempty selection of unique book IDs.")
        if not set(work_ids).issubset(granted_work_ids):
            raise ModelRetry("work_ids must contain only the book IDs granted for this request.")
        book_scopes = tuple(scope for scope in book_scopes if scope.work_id in work_ids)

    limit = max(1, min(max_results_per_source, MAX_RESULTS_PER_SOURCE))
    try:
        result = await retrieve_book_evidence(
            ctx.deps.task.cue,
            book_scopes=book_scopes,
            max_results=limit,
            purpose="connection_discovery",
            librarian=ctx.deps.librarian,
            strength_judge=ctx.deps.strength_judge,
            prior_reader_statements=ctx.deps.prior_reader_statements,
        )
    except Exception:
        ctx.deps.record_search(
            "book_corpus",
            "search_librarian",
            "retrieval_unavailable",
        )
        return InternalSearchResult(
            outcome="retrieval_unavailable",
            judgement=None,
        )

    book_items = result.items
    ctx.deps.record(
        "book_corpus",
        "search_librarian",
        "evidence_found" if book_items else "no_evidence",
        book_items,
    )
    return InternalSearchResult(
        outcome="evidence_found" if book_items else "no_evidence",
        evidence=book_items,
        judgement=result.judgement,
    )


def _private_web_input(
    text: str, deps: SerendipityDependencies, *, page_url: str | None = None,
) -> bool:
    reader_texts = (deps.task.cue, *(statement.text for statement in deps.prior_reader_statements))
    return (
        contains_personal_data_or_secret(text)
        or any(_query_copies_reader_terms(text, source, page_url=page_url) for source in reader_texts)
        or any(_query_copies_reader_terms(text, record.text) for record in deps.memories)
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
            if _private_web_input(query, ctx.deps):
                record_connection_event(ConnectionEvaluationEvent(
                    kind="query", status="blocked", source="web", operation=name,
                    query=query, failure_code="private_query",
                ))
                guidance = (
                    "Open the requested exact URL from scope.web_source_urls "
                    "with get_page, without adding the title or reader wording. "
                    "The URL must "
                    "still pass the privacy checks."
                    if ctx.deps.task.scope.web_source_urls
                    else "Rewrite the web query using only a general, non-identifying "
                    "concept; do not copy the reader's wording or personal data."
                )
                raise ModelRetry(guidance)
        elif name == "get_page":
            requested_url = str(tool_args.get("url", "")).strip()
            permitted_urls = ctx.deps.task.scope.web_source_urls
            if permitted_urls is not None and requested_url not in permitted_urls:
                raise ModelRetry("The page is outside this request's permitted public sources.")
            if any(_private_web_input(value, ctx.deps, page_url=requested_url) for value in (
                requested_url, unquote(requested_url),
            )):
                record_connection_event(ConnectionEvaluationEvent(
                    kind="query", status="blocked", source="web", operation=name,
                    query=requested_url, failure_code="private_query",
                ))
                raise ModelRetry("The requested page URL failed the privacy checks.")
            if permitted_urls is None and requested_url not in ctx.deps.web_leads:
                raise ModelRetry(
                    "Without an application-supplied public URL grant, get_page "
                    "may open only an exact URL returned by web_search during "
                    "this Serendipity run."
                )

        if name in {"web_search", "get_page"}:
            record_connection_event(ConnectionEvaluationEvent(
                kind="query", status="sent", source="web", operation=name,
                query=query if name == "web_search" else requested_url,
            ))
        try:
            result = await super().call_tool(name, tool_args, ctx, tool)
        except Exception:
            ctx.deps.record_search(
                "web",
                name,
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
            permitted_urls = ctx.deps.task.scope.web_source_urls
            if permitted_urls is not None and url not in permitted_urls:
                continue
            if name == "get_page" and url != requested_url:
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
            ctx.deps.opened_web_evidence.update(
                (item.evidence_id, item) for item in web_evidence
                if isinstance(item, WebConnectionEvidence)
            )
            ctx.deps.record(
                "web",
                name,
                outcome,
                web_evidence,
            )
        else:
            ctx.deps.web_leads.update(item.evidence_id for item in web_evidence)
            ctx.deps.record_search(
                "web",
                name,
                outcome,
            )
        return result


class GuardedExaSearch(ExaSearch):
    """The maintained Exa capability with Linger-specific boundary checks."""

    def get_toolset(self) -> AbstractToolset[SerendipityDependencies]:
        return GuardedExaToolset(super().get_toolset())
