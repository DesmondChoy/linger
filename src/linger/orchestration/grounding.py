"""Application-owned orchestration around the Librarian tool."""

from __future__ import annotations

from uuid import uuid4

from apps.backend.config import get_settings
from apps.backend.contracts import BookScope
from apps.backend.contracts import LibrarianRequest as ShippedLibrarianRequest
from apps.backend.librarian import CORPORA, Librarian
from src.linger.contracts.librarian import (
    AccessScope,
    ClarificationRequest,
    EvidenceRecord,
    ExpectedAnswer,
    LibrarianRequest,
    LibrarianResponse,
    RetrievalFailure,
    RetrievalOptions,
    RetrievalResult,
    SearchedScope,
)
from src.linger.contracts.reading import ReadingBoundary
from src.linger.orchestration.turn_context import confirmed_reading

MAX_FINAL_EVIDENCE = 5

librarian_service = Librarian()


class BookVersionOutOfScope(ValueError):
    """Raised when a requested book version escapes the application's access scope."""


def _clamp_max_final_evidence(value: int) -> int:
    return max(1, min(value, MAX_FINAL_EVIDENCE))


def _same_work(declared: str, confirmed: str) -> bool:
    """Compare book identity, not slug spelling.

    The confirmed slug is derived from however the reader typed the title, so
    the same book reaches us as `alice-s-adventures-in-wonderland` or
    `alice-adventures-in-wonderland`. Both resolve to one corpus, and this
    check exists to catch Muse discussing a different *book* — retrieval is
    scoped by the confirmed slug either way, so Muse's spelling grants nothing.
    """
    if declared == confirmed:
        return True
    declared_corpus = CORPORA.get(declared)
    return declared_corpus is not None and declared_corpus is CORPORA.get(confirmed)


def build_request(
    query: str,
    work_id: str,
    book_version_id: str,
    reading_boundary: ReadingBoundary | None,
    max_final_evidence: int = MAX_FINAL_EVIDENCE,
) -> LibrarianRequest:
    """Mint what Muse may not author: the request id and the trusted access scope."""
    settings = get_settings()
    return LibrarianRequest(
        request_id=f"libreq_{uuid4().hex}",
        query=query,
        work_id=work_id,
        book_version_id=book_version_id,
        reading_boundary=reading_boundary,
        access_scope=AccessScope(allowed_book_version_ids=settings.allowed_book_version_ids),
        options=RetrievalOptions(max_final_evidence=_clamp_max_final_evidence(max_final_evidence)),
    )


def _clarification(
    request_id: str, reason_code: str, question: str, expected_answer: ExpectedAnswer
) -> ClarificationRequest:
    return ClarificationRequest(
        kind="clarification",
        request_id=request_id,
        clarification_id=f"clarify_{uuid4().hex}",
        reason_code=reason_code,
        question=question,
        expected_answer=expected_answer,
    )


async def grounding_evidence(
    request: LibrarianRequest, *, librarian: Librarian = librarian_service
) -> LibrarianResponse:
    """Resolve the reader-confirmed ceiling and dispatch to the shipped Librarian.

    Fails closed: an authority violation raises, ambiguity returns a
    clarification without dispatching, and a retriever failure degrades to a
    typed `RetrievalFailure` rather than collapsing the turn.
    """
    if request.book_version_id not in request.access_scope.allowed_book_version_ids:
        raise BookVersionOutOfScope(
            f"{request.book_version_id!r} is not in the allowed access scope"
        )

    reading = confirmed_reading()
    if reading is None:
        return _clarification(
            request.request_id,
            "reading_boundary_unconfirmed",
            "What book and chapter have you confirmed reading so far?",
            ExpectedAnswer(type="free_text"),
        )

    if not _same_work(request.work_id, reading.work_id):
        return _clarification(
            request.request_id,
            "work_not_confirmed",
            "Which book are we discussing right now?",
            ExpectedAnswer(type="free_text"),
        )

    if request.reading_boundary is None:
        return _clarification(
            request.request_id,
            "current_chapter_state_ambiguous",
            "Have you completed that chapter, or are you still partway through it?",
            ExpectedAnswer(type="one_of", values=("completed", "started")),
        )

    boundary: ReadingBoundary = request.reading_boundary
    declared = boundary.chapter_number - 1 if boundary.chapter_state == "started" else boundary.chapter_number
    ceiling = min(declared, reading.chapter_max)

    searched_scope = SearchedScope(
        work_id=reading.work_id,
        book_version_id=request.book_version_id,
        max_chapter_inclusive=max(ceiling, 0),
    )

    if ceiling <= 0:
        result = RetrievalResult(
            kind="result",
            request_id=request.request_id,
            outcome="no_evidence",
            evidence_strength="none",
            strength_reason="No chapters have been confirmed as read yet.",
            searched_scope=searched_scope,
            evidence=(),
            limitations=(),
        )
        return result

    shipped_request = ShippedLibrarianRequest(
        query=request.query,
        book_scopes=[BookScope(book_id=reading.work_id, chapter_max=ceiling)],
    )

    try:
        bundle = librarian.retrieve(shipped_request)
    except Exception:
        failure = RetrievalFailure(
            kind="failure",
            request_id=request.request_id,
            error_code="retrieval_unavailable",
            retryable=True,
        )
        return failure

    records = [
        EvidenceRecord(
            evidence_id=item.evidence_id,
            work_id=reading.work_id,
            book_version_id=request.book_version_id,
            chapter_number=item.chapter,
            location=item.location,
            text=item.excerpt,
        )
        for item in bundle.items
        if item.chapter is not None and item.chapter <= ceiling
    ]
    records = records[: request.options.max_final_evidence]

    if records:
        result = RetrievalResult(
            kind="result",
            request_id=request.request_id,
            outcome="evidence_found",
            evidence_strength="weak",
            strength_reason="Passages were retrieved but not independently judged for sufficiency.",
            searched_scope=searched_scope,
            evidence=tuple(records),
            limitations=("Evidence strength was not independently judged.",),
        )
    else:
        result = RetrievalResult(
            kind="result",
            request_id=request.request_id,
            outcome="no_evidence",
            evidence_strength="none",
            strength_reason="No matching passages were found within the confirmed boundary.",
            searched_scope=searched_scope,
            evidence=(),
            limitations=(),
        )

    return result
