"""Application-owned orchestration around the Serendipity tool."""

from __future__ import annotations

import re
from typing import Callable

from apps.backend.config import REPO_ROOT, get_settings
from apps.backend.contracts import (
    BookScope,
    ConnectionBrief,
    ConnectionDecline,
    ConnectionResult,
    EvidenceBundle,
    LibrarianRequest,
)
from apps.backend.serendipity import discover
from src.linger.orchestration.grounding import librarian_service
from src.linger.orchestration.turn_context import confirmed_reading
from src.linger.services.memory import AccountContext, MemoryPolicyService

Explorer = Callable[[ConnectionBrief, EvidenceBundle], ConnectionResult]

MIN_PRIVATE_WORDS = 3
VERBATIM_WINDOW = 6

memory_service = MemoryPolicyService(REPO_ROOT / "memories")


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

    request = LibrarianRequest(
        query=clamped_brief.cue, book_scopes=[BookScope(book_id=reading.work_id, chapter_max=ceiling)]
    )
    try:
        bundle = librarian_service.retrieve(request)
    except Exception:
        return _insufficient_evidence("Evidence retrieval was unavailable; try again shortly.")

    try:
        return explorer(clamped_brief, bundle)
    except Exception:
        return _insufficient_evidence("The connection could not be safely explored from the available evidence.")
