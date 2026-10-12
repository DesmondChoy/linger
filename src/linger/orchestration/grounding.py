"""Application-owned orchestration around the Librarian tool."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import logfire

from apps.backend import sessions
from apps.backend.config import get_settings
from apps.backend.contracts import BookScope
from apps.backend.librarian import Librarian
from apps.backend.hybrid_librarian import HybridLibrarian
from apps.backend.telemetry import record_failure, set_span_attrs
from src.linger.agents.librarian.models import (
    BookRequestPlan,
    EvidenceStrengthDecision,
    LibrarianBookRequestInput,
)
from src.linger.orchestration.book_evidence import (
    EvidenceJudgementError,
    evidence_record_from_item,
    judge_records,
    plan_or_fallback,
    retrieve_book_evidence,
)
from src.linger.contracts.librarian import (
    AccessScope,
    ClarificationRequest,
    EvidenceRecord,
    ExpectedAnswer,
    LibrarianRequest,
    LibrarianResponse,
    PassageScope,
    RetrievalFailure,
    RetrievalOptions,
    RetrievalResult,
    SearchedScope,
    StatedAnswer,
)
from src.linger.corpus.registry import BookClarification
from src.linger.orchestration.evidence_strength import (
    StrengthJudge,
    list_stated_answers,
)
from src.linger.orchestration.turn_context import (
    add_turn_evidence,
    add_turn_stated_answers,
    confirmed_reading,
    passage_grant,
    routing_context,
    reader_message,
    reader_statements,
    session_id,
)

MAX_FINAL_EVIDENCE = 5

librarian_service = HybridLibrarian()


class BookVersionOutOfScope(ValueError):
    """Raised when a requested book version escapes the application's access scope."""


def _clamp_max_final_evidence(value: int) -> int:
    return max(1, min(value, MAX_FINAL_EVIDENCE))


def build_request(
    query: str,
    work_id: str,
    book_version_id: str,
    max_final_evidence: int = MAX_FINAL_EVIDENCE,
) -> LibrarianRequest:
    """Mint what Muse may not author: the request id and the trusted access scope."""
    settings = get_settings()
    return LibrarianRequest(
        request_id=f"libreq_{uuid4().hex}",
        query=query,
        work_id=work_id,
        book_version_id=book_version_id,
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


async def _grounding_evidence(
    request: LibrarianRequest,
    *,
    librarian: Librarian = librarian_service,
    strength_judge: StrengthJudge | None = None,
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

    if not librarian.supports_revision(request.work_id, request.book_version_id):
        raise BookVersionOutOfScope(
            f"{request.book_version_id!r} is not a registered revision of {request.work_id!r}"
        )

    route = routing_context()
    if route is not None and isinstance(route.response, ClarificationRequest):
        return route.response.model_copy(update={"request_id": request.request_id})

    reading = confirmed_reading()
    grant = passage_grant()
    if reading is None and grant is not None:
        if (
            request.work_id != grant.scope.work_id
            or request.book_version_id != grant.scope.book_version_id
        ):
            raise BookVersionOutOfScope("The request does not match the granted passages")
        try:
            records = [librarian.fetch_by_id(record.evidence_id) for record in grant.records]
        except Exception:
            return RetrievalFailure(
                kind="failure",
                request_id=request.request_id,
                error_code="retrieval_unavailable",
                retryable=True,
            )
        if tuple(records) != grant.records:
            return RetrievalFailure(
                kind="failure",
                request_id=request.request_id,
                error_code="canonical_evidence_mismatch",
                retryable=False,
            )
        return await _finish_retrieval(
            request,
            grant.records[: request.options.max_final_evidence],
            grant.scope,
            strength_judge,
        )

    if reading is None:
        current_session = session_id()
        if current_session is not None:
            decision = librarian.route_work(
                reader_message() or "", request.access_scope.allowed_book_version_ids
            )
            if isinstance(decision, BookClarification):
                sessions.clear_book_selection(current_session, cause="tool_uncertain")
                return _clarification(
                    request.request_id,
                    "book_identity_unresolved",
                    decision.question,
                    ExpectedAnswer(type="free_text"),
                )
            selection = sessions.book_selection(current_session)
            resolved_work_id = (
                decision.scope.work_id if decision is not None
                else selection.book_id if selection is not None else None
            )
            scope = librarian.registered_scope(request.work_id, request.book_version_id)
            if scope is None or resolved_work_id != scope.work_id:
                sessions.clear_book_selection(current_session, cause="out_of_scope")
                return _clarification(
                    request.request_id,
                    "book_identity_unresolved",
                    BookClarification().question,
                    ExpectedAnswer(type="free_text"),
                )
            sessions.set_book_selection(
                current_session,
                sessions.BookSelection(book_id=scope.work_id, book_title=scope.title),
            )
            sessions.clear_reading_candidate(current_session)
            sessions.set_pending_clarification(
                current_session,
                sessions.PendingClarification(
                    book_id=scope.work_id,
                    book_title=scope.title,
                    reason_code="reading_boundary_unconfirmed",
                )
            )
        return _clarification(
            request.request_id,
            "reading_boundary_unconfirmed",
            "What book and chapter have you confirmed reading so far?",
            ExpectedAnswer(type="free_text"),
        )

    if request.work_id != reading.work_id:
        return _clarification(
            request.request_id,
            "work_not_confirmed",
            "Which book are we discussing right now?",
            ExpectedAnswer(type="free_text"),
        )

    ceiling = reading.chapter_max
    unit_ids = reading.unit_ids
    searched_scope = SearchedScope(
        work_id=reading.work_id,
        book_version_id=request.book_version_id,
        max_chapter_inclusive=ceiling,
        part_id=reading.part_id,
        unit_ids=unit_ids,
    )

    try:
        judged = await retrieve_book_evidence(
            reader_message() if reader_message() is not None else request.query,
            book_scopes=(BookScope(
                work_id=reading.work_id,
                book_version_id=request.book_version_id,
                chapter_max=ceiling,
                part_id=reading.part_id, unit_ids=unit_ids,
            ),),
            retrieval_score_threshold=request.options.retrieval_score_threshold,
            max_results=request.options.max_final_evidence,
            librarian=librarian,
            strength_judge=strength_judge,
            prior_reader_statements=reader_statements(),
        )
    except EvidenceJudgementError:
        return RetrievalFailure(
            kind="failure",
            request_id=request.request_id,
            error_code="evidence_judgement_unavailable",
            retryable=True,
        )
    except Exception:
        failure = RetrievalFailure(
            kind="failure",
            request_id=request.request_id,
            error_code="retrieval_unavailable",
            retryable=True,
        )
        return failure

    records = tuple(evidence_record_from_item(item) for item in judged.items)
    return await _judged_result(
        request, records, searched_scope, judged.judgement,
        request_plan=judged.request_plan, original_request=judged.original_request,
    )


async def _finish_retrieval(
    request: LibrarianRequest,
    records: tuple[EvidenceRecord, ...],
    searched_scope: SearchedScope | PassageScope,
    strength_judge: StrengthJudge | None,
) -> LibrarianResponse:
    """Judge exact granted passages without broadening their retrieval scope."""
    plan = original = None
    if strength_judge is None:
        original = LibrarianBookRequestInput(
            current_line=reader_message() if reader_message() is not None else request.query,
            prior_reader_statements=reader_statements(),
        )
        plan = await plan_or_fallback(original)
    try:
        decision = await judge_records(
            request.query,
            records,
            strength_judge=strength_judge,
            max_evidence_records=request.options.max_final_evidence,
            request_plan=plan,
            original_request=original,
        )
    except EvidenceJudgementError:
        return RetrievalFailure(
            kind="failure",
            request_id=request.request_id,
            error_code="evidence_judgement_unavailable",
            retryable=True,
        )
    return await _judged_result(
        request, records, searched_scope, decision,
        request_plan=plan, original_request=original,
    )


async def _stated_answers(
    selected: tuple[EvidenceRecord, ...],
    request_plan: BookRequestPlan | None,
    original_request: LibrarianBookRequestInput | None,
) -> tuple[StatedAnswer, ...]:
    """List what the selected records state; this step can never fail a search."""
    if not selected or request_plan is None or original_request is None:
        return ()
    try:
        return await list_stated_answers(request_plan, selected, original_request=original_request)
    except Exception:
        logfire.warning("librarian.stated_answers_unavailable")
        return ()


async def _judged_result(
    request: LibrarianRequest,
    records: tuple[EvidenceRecord, ...],
    searched_scope: SearchedScope | PassageScope,
    decision: EvidenceStrengthDecision,
    *,
    request_plan: BookRequestPlan | None,
    original_request: LibrarianBookRequestInput | None,
) -> RetrievalResult:
    """Register only the judge's selected records for direct grounding."""
    selected_ids = set(decision.relevant_evidence_ids)
    selected_records = tuple(
        record for record in records if record.evidence_id in selected_ids
    )
    if decision.evidence_strength == "none":
        return RetrievalResult(
            kind="result",
            request_id=request.request_id,
            outcome="no_evidence",
            evidence_strength="none",
            strength_reason=decision.strength_reason,
            searched_scope=searched_scope,
            evidence=(),
            limitations=decision.limitations,
        )

    response = RetrievalResult(
        kind="result",
        request_id=request.request_id,
        outcome="evidence_found",
        evidence_strength=decision.evidence_strength,
        strength_reason=decision.strength_reason,
        searched_scope=searched_scope,
        evidence=selected_records,
        limitations=decision.limitations,
        stated_answers=await _stated_answers(selected_records, request_plan, original_request),
    )
    add_turn_evidence(response.evidence)
    add_turn_stated_answers(response.stated_answers)
    return response


async def grounding_evidence(
    request: LibrarianRequest,
    *,
    librarian: Librarian = librarian_service,
    strength_judge: StrengthJudge | None = None,
) -> LibrarianResponse:
    """Trace the Librarian tool using validated scope and fixed outcomes only."""
    cancelled = False
    caught: Exception | None = None
    response: LibrarianResponse | None = None
    with logfire.span(
        "librarian.search",
        **{
            "tool.name": "librarian_search",
            "tool.retry_count": 0,
            "status": "started",
        },
    ) as span:
        try:
            response = await _grounding_evidence(
                request,
                librarian=librarian,
                strength_judge=strength_judge,
            )
        except asyncio.CancelledError:
            cancelled = True
            record_failure(
                span,
                stage="librarian_search",
                code="request_cancelled",
                retryable=False,
                failure_type="application",
            )
            span.set_attribute("tool.status", "failure")
        except BookVersionOutOfScope as exc:
            caught = exc
            record_failure(
                span,
                stage="scope_validation",
                code="book_version_out_of_scope",
                retryable=False,
                failure_type="validation",
            )
            span.set_attribute("tool.status", "failure")
        except Exception as exc:
            caught = exc
            record_failure(
                span,
                stage="librarian_search",
                code="librarian_tool_failed",
                retryable=False,
                failure_type="application",
            )
            span.set_attribute("tool.status", "failure")
        else:
            if isinstance(response, RetrievalFailure):
                record_failure(
                    span,
                    stage="librarian_search",
                    code=response.error_code,
                    retryable=response.retryable,
                    failure_type="retrieval",
                )
                span.set_attribute("tool.status", "failure")
            elif isinstance(response, ClarificationRequest):
                set_span_attrs(
                    span,
                    {
                        "status": "decline",
                        "tool.status": "decline",
                        "retrieval.outcome": "clarification",
                    },
                )
            else:
                set_span_attrs(
                    span,
                    {
                        "status": "success",
                        "tool.status": "success",
                        "scope.work_id": response.searched_scope.work_id,
                        "scope.book_version_id": response.searched_scope.book_version_id,
                        **(
                            {"scope.chapter_max": response.searched_scope.max_chapter_inclusive}
                            if isinstance(response.searched_scope, SearchedScope)
                            else {"scope.kind": "passages"}
                        ),
                        "retrieval.item_count": len(response.evidence),
                        "retrieval.evidence_ids": [
                            record.evidence_id for record in response.evidence
                        ],
                        "retrieval.outcome": response.outcome,
                    },
                )

    if cancelled:
        raise asyncio.CancelledError
    if caught is not None:
        raise caught
    assert response is not None
    return response
