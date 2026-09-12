"""Request-local, content-free progress events for long-running chat turns."""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Literal

ProgressStatus = Literal["running", "complete", "declined", "failed"]

SAFE_AGENTS = frozenset(
    {
        "Application",
        "Muse",
        "Provenance",
        "Librarian",
        "Serendipity",
        "Sculptor",
        "Exa",
    }
)

# Every stage a reader may see. Names outside this map collapse to "processing"
# so new instrumentation cannot leak a stage label that describes content.
SAFE_STAGE_LABELS = {
    "emotional_boundary_preflight": "Emotional boundary preflight",
    "boundary_inference": "Spoiler boundary inference",
    "draft": "Muse candidate generation",
    "revision": "Muse candidate revision",
    "review": "Provenance release review",
    "search_rank_select": "Serendipity search and comparison",
    "evidence_strength": "Librarian evidence review",
    "curation": "Memory curation proposal",
    "curation_review": "Memory curation review",
    "surfacing": "Memory surfacing",
    "memory_search": "Authorised-memory search",
    "book_corpus_search": "Spoiler-bounded book search",
    "web_search": "Public-web search",
    "get_page": "Public source-page retrieval",
}

_STATUS_SUFFIX = {
    "running": "is in progress.",
    "complete": "completed.",
    "declined": "returned no releasable result.",
    "failed": "could not complete safely.",
}


@dataclass(frozen=True)
class ProgressEvent:
    """One safe UI update; prompts, excerpts, and model drafts are excluded."""

    agent: str
    stage: str
    status: ProgressStatus
    detail: str
    input_origin: str
    output_receiver: str


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
    _detail: str = "",
    *,
    input_origin: str = "Application",
    output_receiver: str = "Application",
) -> None:
    """Publish allowlisted metadata while discarding all caller-supplied prose.

    Callers retain a descriptive argument for readable local code, but it can
    never cross the stream boundary. Unknown agent and stage names collapse to
    generic values so future instrumentation cannot accidentally expose prompt,
    evidence, draft, URL, query, or review content through metadata fields.
    """
    emitter = _emitter.get()
    if emitter is None:
        return
    safe_agent = agent if agent in SAFE_AGENTS else "Application"
    safe_stage = stage if stage in SAFE_STAGE_LABELS else "processing"
    label = SAFE_STAGE_LABELS.get(safe_stage, "Application processing")
    emitter(
        ProgressEvent(
            agent=safe_agent,
            stage=safe_stage,
            status=status,
            detail=f"{label} {_STATUS_SUFFIX[status]}",
            input_origin=(
                input_origin if input_origin in SAFE_AGENTS else "Application"
            ),
            output_receiver=(
                output_receiver if output_receiver in SAFE_AGENTS else "Application"
            ),
        )
    )


def reset_progress(token: Token[ProgressEmitter | None]) -> None:
    """Restore the previous request context."""
    _emitter.reset(token)