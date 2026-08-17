"""Application-owned orchestration around the Serendipity tool."""

from __future__ import annotations

import re
from typing import Callable

import logfire

from apps.backend.config import REPO_ROOT, get_settings
from apps.backend.contracts import (
    BookScope,
    ConnectionBrief,
    ConnectionDecline,
    ConnectionResult,
    EvidenceBundle,
    LibrarianRequest,
)
from apps.backend.librarian import Librarian
from apps.backend.serendipity import discover
from apps.backend.telemetry import (
    brief_attrs,
    evidence_attrs,
    failure_attrs,
    librarian_request_attrs,
    record_failure,
    set_span_attrs,
)
from src.linger.orchestration.turn_context import confirmed_reading
from src.linger.services.memory import AccountContext, MemoryPolicyService

Explorer = Callable[[ConnectionBrief, EvidenceBundle], ConnectionResult]

MIN_PRIVATE_WORDS = 1
VERBATIM_WINDOW = 6

memory_service = MemoryPolicyService(REPO_ROOT / "memories")
# Connection discovery deliberately needs diversified passages from multiple
# chapters. Its retrieval strategy is evaluated separately from Librarian's
# selected exact-question grounding path.
librarian_service = Librarian()


def _insufficient_evidence(safe_next_step: str) -> ConnectionDecline:
    return ConnectionDecline(reason="insufficient_evidence", safe_next_step=safe_next_step)


def web_reach_permitted() -> bool:
    """Whether this deployment is configured to let Muse reach the open web."""
    return getattr(get_settings(), "linger_web_search_enabled", None) is True


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _repeats_private_memory(cue: str) -> bool:
    """Detect a cue that reproduces a run of stored private-memory tokens verbatim.

    Reading the store must fail closed: an unreadable store cannot prove the
    cue is safe, so any read failure is treated as a match.
    """
    account = AccountContext(account_id=get_settings().linger_account_id)
    try:
        records = memory_service.list_active(account)
    except Exception:
        # Fail closed, but leave a trace: an unreadable memory store silently
        # blocking every cue is otherwise indistinguishable from a genuine match.
        logfire.warn(
            "memory store unreadable; treating cue as unsafe",
            **failure_attrs(
                stage="memory_read",
                code="memory_store_unavailable",
                retryable=True,
                failure_type="storage",
            ),
        )
        return True

    cue_tokens = _tokens(cue)
    for record in records:
        memory_tokens = _tokens(record.text)
        if len(memory_tokens) < MIN_PRIVATE_WORDS:
            continue
        window = min(VERBATIM_WINDOW, len(memory_tokens))
        for start in range(len(memory_tokens) - window + 1):
            run = memory_tokens[start : start + window]
            for cue_start in range(len(cue_tokens) - window + 1):
                if cue_tokens[cue_start : cue_start + window] == run:
                    return True
    return False


def build_brief(cue: str) -> ConnectionBrief:
    """Mint what Muse may not author: the reader-confirmed book scope."""
    reading = confirmed_reading()
    if reading is None:
        return ConnectionBrief(cue=cue, allowed_sources={"book_corpus"})
    return ConnectionBrief(
        cue=cue,
        book_id=reading.work_id,
        chapter_max=reading.chapter_max,
        allowed_sources={"book_corpus"},
    )


async def connection_proposal(
    brief: ConnectionBrief, *, explorer: Explorer = discover
) -> ConnectionResult:
    """Resolve the reader-confirmed ceiling and dispatch to the shipped Serendipity.

    Exactly one reader-confirmed ceiling governs the turn: the brief is clamped
    to it before retrieval, and that same clamped ceiling is what is retrieved
    and handed to the explorer, so a caller cannot widen scope past what the
    reader confirmed by pairing a wide brief with a separately-scoped retrieval.
    """
    if web_reach_permitted():
        return ConnectionDecline(
            reason="unsupported_cue",
            safe_next_step="Web-sourced connections are not available; Linger only reasons over the book you are reading.",
        )

    if _repeats_private_memory(brief.cue):
        return ConnectionDecline(
            reason="unsupported_cue",
            safe_next_step="Try rephrasing that in your own words rather than quoting a saved reflection directly.",
        )

    reading = confirmed_reading()
    if reading is None:
        return _insufficient_evidence(
            "Which book and chapter have you reached? Linger needs a confirmed reading position before it can propose connections."
        )

    ceiling = min(brief.chapter_max, reading.chapter_max) if brief.chapter_max is not None else reading.chapter_max
    clamped_brief = brief.model_copy(
        update={"book_id": reading.work_id, "chapter_max": ceiling, "allowed_sources": {"book_corpus"}}
    )

    book_version_id = librarian_service.version_for(reading.work_id)
    if book_version_id is None:
        return _insufficient_evidence(
            "This book does not have a registered evidence corpus yet."
        )

    request = LibrarianRequest(
        query=clamped_brief.cue,
        book_scopes=[
            BookScope(
                work_id=reading.work_id,
                book_version_id=book_version_id,
                chapter_max=ceiling,
            )
        ],
    )
    with logfire.span("serendipity.connection", **brief_attrs(clamped_brief)) as span:
        span.set_attribute("scope.book_version_id", book_version_id)
        retrieval_failed = False
        bundle: EvidenceBundle | None = None
        with logfire.span(
            "librarian.retrieve", **librarian_request_attrs(request)
        ) as retrieval_span:
            try:
                bundle = librarian_service.retrieve(request)
            except Exception:
                retrieval_failed = True
                record_failure(
                    retrieval_span,
                    stage="librarian_retrieve",
                    code="retrieval_unavailable",
                    retryable=True,
                    failure_type="retrieval",
                )
            else:
                set_span_attrs(
                    retrieval_span,
                    {
                        "status": "success",
                        "tool.status": "success",
                        "retrieval.outcome": (
                            "evidence_found" if bundle.items else "no_evidence"
                        ),
                        **evidence_attrs(bundle),
                    },
                )
        if retrieval_failed or bundle is None:
            record_failure(
                span,
                stage="librarian_retrieve",
                code="retrieval_unavailable",
                retryable=True,
                failure_type="retrieval",
            )
            span.set_attribute("tool.status", "failure")
            return _insufficient_evidence("Evidence retrieval was unavailable; try again shortly.")

        set_span_attrs(span, evidence_attrs(bundle))
        try:
            result = explorer(clamped_brief, bundle)
        except Exception:
            record_failure(
                span,
                stage="serendipity_explore",
                code="connection_exploration_failed",
                retryable=False,
                failure_type="application",
            )
            span.set_attribute("tool.status", "failure")
            return _insufficient_evidence("The connection could not be safely explored from the available evidence.")

        set_span_attrs(
            span,
            {
                "status": "success" if result.status == "proposal" else "decline",
                "tool.status": "success" if result.status == "proposal" else "decline",
                "retrieval.outcome": result.status,
            },
        )
        return result
