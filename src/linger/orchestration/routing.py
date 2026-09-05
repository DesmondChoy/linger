"""Application-owned orchestration for Muse-initiated Librarian routing."""

from __future__ import annotations

from uuid import uuid4

import logfire

from apps.backend import sessions
from apps.backend.config import get_settings
from apps.backend.librarian import Librarian, RegisteredCorpusScope
from src.linger.contracts.librarian import (
    BoundaryUncertain,
    ClarificationRequest,
    ExpectedAnswer,
    LibrarianRoutingResponse,
    NoMatch,
    RoutedWork,
)
from src.linger.contracts.turn import ConfirmedReading
from src.linger.orchestration.boundary import infer_spoiler_boundary
from src.linger.orchestration.grounding import librarian_service
from src.linger.orchestration.turn_context import (
    active_memories,
    bind_confirmed_reading,
    confirmed_reading,
    session_id,
)


async def route_reader_message(
    message: str,
    *,
    librarian: Librarian = librarian_service,
) -> LibrarianRoutingResponse:
    """Identify a confirmed work and boundary from the reader's message, or ask.

    Grants no retrieval or write authority: a routed result only names the
    work and a validated chapter ceiling for `librarian_search` to use.
    """
    with logfire.span(
        "librarian.route",
        **{"tool.name": "librarian_route", "status": "started"},
    ) as span:
        settings = get_settings()
        decision = librarian.route_work(message, settings.allowed_book_version_ids)
        if decision is None:
            span.set_attribute("tool.status", "no_match")
            return NoMatch(kind="no_match")

        scope = decision.scope
        boundary = await infer_spoiler_boundary(
            message,
            work_id=scope.work_id,
            book_version_id=scope.book_version_id,
            memories=active_memories(),
            librarian=librarian,
        )
        if isinstance(boundary, BoundaryUncertain):
            span.set_attribute("tool.status", "clarification")
            _persist_uncertain_candidate(scope, boundary)
            return ClarificationRequest(
                kind="clarification",
                request_id=f"routereq_{uuid4().hex}",
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
            work_id=scope.work_id,
            book_version_id=scope.book_version_id,
            title=scope.title,
            routing_confidence=decision.confidence,
            max_chapter_inclusive=reported_ceiling,
            boundary_confidence=boundary.confidence,
        )


def _persist_uncertain_candidate(
    scope: RegisteredCorpusScope, boundary: BoundaryUncertain
) -> None:
    """Remember only the chapter explicitly presented by a memory-backed question."""
    current_session = session_id()
    if current_session is None:
        return
    sessions.set_book_selection(
        current_session,
        sessions.BookSelection(book_id=scope.work_id, book_title=scope.title),
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
