"""Request-local, content-free progress events for long-running chat turns."""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Literal


ProgressStatus = Literal["running", "complete", "declined", "failed"]

SAFE_AGENTS = frozenset(
    {
        "Router",
        "Muse",
        "Librarian",
        "Serendipity",
        "Exa",
        "Provenance",
        "Sculptor",
        "Memory & Policy",
    }
)
SAFE_STAGE_LABELS = {
    "context_resolution": "Source permission and context resolution",
    "draft": "Muse candidate generation",
    "revision": "Muse candidate revision",
    "review": "Provenance release review",
    "search_rank_select": "Serendipity search and comparison",
    "validate_connection": "Connection scope validation",
    "connection_decision": "Serendipity decision handoff",
    "reuse_connection_decision": "Request-scoped Serendipity decision reuse",
    "authorised_memory_search": "Authorised-memory search",
    "book_corpus_search": "Spoiler-bounded book search",
    "web_search": "Exa public-web search",
    "get_page": "Exa source-page retrieval",
    "judge_evidence": "Librarian evidence review",
    "propose_curation": "Memory curation proposal",
    "automatic_capture": "Automatic-memory policy check",
}


@dataclass(frozen=True)
class ProgressEvent:
    """One safe UI update; prompts, excerpts, and model drafts are excluded."""

    agent: str
    stage: str
    status: ProgressStatus
    detail: str


ProgressEmitter = Callable[[ProgressEvent], None]
_emitter: ContextVar[ProgressEmitter | None] = ContextVar(
    "chat_progress_emitter",
    default=None,
)


def begin_progress(emitter: ProgressEmitter) -> Token[ProgressEmitter | None]:
    """Install an emitter for the current asynchronous request context."""
    return _emitter.set(emitter)


def emit_progress(
    agent: str,
    stage: str,
    status: ProgressStatus,
    _detail: str,
) -> None:
    """Publish allowlisted metadata while discarding all caller-supplied prose.

    Callers retain a descriptive argument for readable local code, but it can
    never cross the stream boundary. Unknown agent and stage names collapse to
    generic values so future instrumentation cannot accidentally expose prompt,
    evidence, draft, URL, query, or review content through metadata fields.
    """
    emitter = _emitter.get()
    if emitter is not None:
        safe_agent = agent if agent in SAFE_AGENTS else "Application"
        safe_stage = stage if stage in SAFE_STAGE_LABELS else "processing"
        label = SAFE_STAGE_LABELS.get(safe_stage, "Application processing")
        suffix = {
            "running": "is in progress.",
            "complete": "completed.",
            "declined": "returned no releasable result.",
            "failed": "could not complete safely.",
        }[status]
        emitter(
            ProgressEvent(
                agent=safe_agent,
                stage=safe_stage,
                status=status,
                detail=f"{label} {suffix}",
            )
        )


def reset_progress(token: Token[ProgressEmitter | None]) -> None:
    """Restore the previous request context."""
    _emitter.reset(token)
