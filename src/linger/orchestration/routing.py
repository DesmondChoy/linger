"""Application-owned orchestration for Muse-initiated Librarian routing."""

from __future__ import annotations

from uuid import uuid4

import logfire

from apps.backend import sessions
from apps.backend.config import get_settings
from apps.backend.librarian import (
    ROUTING_CONFIDENCE_THRESHOLD,
    Librarian,
    RegisteredCorpusScope,
    RoutingDecision,
)
from src.linger.contracts.librarian import (
    BoundaryPassages,
    BoundaryUncertain,
    ClarificationRequest,
    ExpectedAnswer,
    LibrarianRoutingResponse,
    NoMatch,
    RoutedWork,
    RoutedPassages,
)
from src.linger.contracts.turn import ConfirmedReading
from src.linger.corpus.registry import BookClarification
from src.linger.evaluation_transcript import bind_evaluation_correlation_id
from src.linger.orchestration.boundary import infer_spoiler_boundary
from src.linger.orchestration.grounding import librarian_service
from src.linger.orchestration.turn_context import (
    active_memories,
    bind_confirmed_reading,
    bind_passage_grant,
    confirmed_reading,
    reader_statements,
    routing_context,
    session_id,
)


async def route_reader_message(
    message: str,
    *,
    librarian: Librarian = librarian_service,
) -> LibrarianRoutingResponse:
    """Route the fixed reader input once, including concurrent Muse calls."""
    context = routing_context()
    if context is None:
        return await _route_reader_message(message, librarian=librarian)
    async with context.lock:
        if context.response is None:
            context.response = await _route_reader_message(message, librarian=librarian)
        return context.response


async def _route_reader_message(
    message: str, *, librarian: Librarian,
) -> LibrarianRoutingResponse:
    """Identify a work and chapter or exact-passage permission, or ask."""
    request_id = f"routereq_{uuid4().hex}"
    with logfire.span(
        "librarian.route",
        **{"tool.name": "librarian_route", "status": "started"},
    ) as span:
        settings = get_settings()
        decision = librarian.route_work(message, settings.allowed_book_version_ids)
        if decision is None:
            decision = _session_selection(message, librarian, settings.allowed_book_version_ids)
        if decision is None:
            span.set_attribute("tool.status", "no_match")
            return NoMatch(kind="no_match", request_id=request_id)
        if isinstance(decision, BookClarification):
            span.set_attribute("tool.status", "clarification")
            current_session = session_id()
            if current_session is not None:
                sessions.clear_book_selection(current_session)
            return ClarificationRequest(
                kind="clarification",
                request_id=request_id,
                clarification_id=f"clarify_{uuid4().hex}",
                reason_code="book_identity_unresolved",
                question=decision.question,
                expected_answer=ExpectedAnswer(type="free_text"),
            )

        scope = decision.scope
        span.set_attribute("routing.selection_basis", decision.basis)
        with bind_evaluation_correlation_id(request_id):
            boundary = await infer_spoiler_boundary(
                message,
                work_id=scope.work_id,
                book_version_id=scope.book_version_id,
                memories=active_memories(),
                prior_reader_statements=reader_statements(),
                librarian=librarian,
            )
        if isinstance(boundary, BoundaryPassages):
            existing = confirmed_reading()
            if existing is not None:
                # Explicit chapter progress remains the authority. Do not add
                # a second permission or silently cross that stated boundary.
                if any(
                    record.work_id != existing.work_id
                    or record.chapter_number > existing.chapter_max
                    for record in boundary.grant.records
                ):
                    boundary = BoundaryUncertain(
                        kind="uncertain", work_id=scope.work_id,
                        book_version_id=scope.book_version_id,
                        reason_code="conflicting_context",
                        clarification_question="Have you read the passage you are asking about, or are you still earlier in the book?",
                    )
                else:
                    return RoutedWork(
                        kind="routed", request_id=request_id, work_id=scope.work_id,
                        book_version_id=scope.book_version_id, title=scope.title,
                        routing_confidence=decision.confidence,
                        max_chapter_inclusive=existing.chapter_max,
                        boundary_confidence=boundary.confidence,
                        selection_basis=decision.basis,
                    )
            else:
                bind_passage_grant(boundary.grant)
                current_session = session_id()
                if current_session is not None:
                    sessions.set_book_selection(
                        current_session,
                        sessions.BookSelection(book_id=scope.work_id, book_title=scope.title),
                    )
                    sessions.clear_pending_clarification(current_session)
                    sessions.clear_reading_candidate(current_session)
                span.set_attribute("tool.status", "routed")
                return RoutedPassages(
                    **boundary.grant.scope.model_dump(), request_id=request_id,
                    title=scope.title, routing_confidence=decision.confidence,
                    boundary_confidence=boundary.confidence,
                    selection_basis=decision.basis,
                )
        if isinstance(boundary, BoundaryUncertain):
            span.set_attribute("tool.status", "clarification")
            _persist_uncertain_candidate(scope, boundary)
            return ClarificationRequest(
                kind="clarification",
                request_id=request_id,
                clarification_id=f"clarify_{uuid4().hex}",
                reason_code=boundary.reason_code,
                question=boundary.clarification_question,
                expected_answer=ExpectedAnswer(type="free_text"),
            )

        span.set_attribute("tool.status", "routed")
        existing = confirmed_reading()
        if existing is None:
            # Grant the same application-side authority
            # `_infer_request_boundary` used to grant under
            # boundary_source="librarian_inferred": Librarian's own validated
            # inference sets the ceiling for the rest of this turn, so a
            # same-turn `librarian_search` call is not blocked on
            # `confirmed_reading()`. Muse's text never sets this itself.
            bind_confirmed_reading(
                ConfirmedReading(work_id=scope.work_id, chapter_max=boundary.max_chapter_inclusive)
            )
            current_session = session_id()
            if current_session is not None:
                sessions.set_book_selection(
                    current_session,
                    sessions.BookSelection(book_id=scope.work_id, book_title=scope.title),
                )
            reported_ceiling = boundary.max_chapter_inclusive
        else:
            # A reader-confirmed boundary already governs this turn — mirrors
            # `_infer_request_boundary`'s old early return on
            # `status == "confirmed"`. A routed inferred ceiling must never
            # widen or replace it, nor silently switch the session's active
            # book while one is reader-confirmed.
            reported_ceiling = (
                min(existing.chapter_max, boundary.max_chapter_inclusive)
                if existing.work_id == scope.work_id
                else boundary.max_chapter_inclusive
            )
        return RoutedWork(
            kind="routed",
            request_id=request_id,
            work_id=scope.work_id,
            book_version_id=scope.book_version_id,
            title=scope.title,
            routing_confidence=decision.confidence,
            max_chapter_inclusive=reported_ceiling,
            boundary_confidence=boundary.confidence,
            selection_basis=decision.basis,
        )


def _persist_uncertain_candidate(
    scope: RegisteredCorpusScope, boundary: BoundaryUncertain
) -> None:
    """Remember the question and only a chapter it explicitly asks to confirm."""
    current_session = session_id()
    if current_session is None:
        return
    sessions.set_book_selection(
        current_session,
        sessions.BookSelection(book_id=scope.work_id, book_title=scope.title),
    )
    sessions.set_pending_clarification(
        current_session,
        sessions.PendingClarification(
            book_id=scope.work_id,
            book_title=scope.title,
            reason_code=boundary.reason_code,
        ),
    )
    if (
        boundary.authorization_basis != "memory_supported"
        or boundary.candidate_chapter is None
    ):
        sessions.clear_reading_candidate(current_session)
        return
    sessions.set_reading_candidate(
        current_session,
        sessions.ReadingCandidate(
            book_id=scope.work_id,
            book_title=scope.title,
            chapter=boundary.candidate_chapter,
        ),
    )


def _session_selection(
    message: str, librarian: Librarian, allowed_book_version_ids: tuple[str, ...]
) -> RoutingDecision | None:
    """Route a bare follow-up to the session's active book when nothing contradicts it."""
    current_session = session_id()
    selection = sessions.book_selection(current_session) if current_session is not None else None
    if selection is None:
        return None
    book_version_id = librarian.version_for(selection.book_id)
    if book_version_id not in allowed_book_version_ids:
        return None
    if any(
        candidate.strength == "strong" and candidate.scope.work_id != selection.book_id
        for candidate in librarian.work_candidates(message, allowed_book_version_ids)
    ):
        return None
    scope = librarian.registered_scope(selection.book_id, book_version_id)
    if scope is None:
        return None
    return RoutingDecision(
        scope=scope, confidence=ROUTING_CONFIDENCE_THRESHOLD, basis="session_selection"
    )
