"""Application-owned chat-turn workflow for Linger."""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from time import perf_counter
from uuid import uuid4

import logfire
from opentelemetry.trace import format_trace_id

from src.linger.agents.muse.agent import muse_chat_agent
from src.linger.agents.provenance.agent import provenance_agent
from src.linger.agents.provenance.emotional import emotional_boundary_agent
from src.linger.contracts.emotional import EmotionalContentPolicy
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.contracts.turn import ConfirmedReading, ReleaseScope
from src.linger.orchestration.connection import web_reach_permitted
from src.linger.orchestration.emotional import (
    EmotionalBoundaryValidationError,
    assess_emotional_boundary,
)
from src.linger.orchestration.grounding import librarian_service
from src.linger.orchestration.inspection_context import (
    ConnectionRunInspection,
    begin_connection_inspection,
    connection_inspections,
    reset_connection_inspection,
)
from src.linger.orchestration.reflection import (
    ReflectionRelease,
    emotional_boundary_release,
    emotional_preflight_safe_decline,
    reflection_reply,
)
from src.linger.orchestration.turn_context import (
    reset_active_memories,
    reset_confirmed_reading,
    reset_reader_message,
    reset_session_id,
    reset_turn_evidence,
    set_active_memories,
    set_confirmed_reading,
    set_reader_message,
    set_session_id,
    set_turn_evidence,
)
from src.linger.services.memory import (
    AccountContext,
    MemoryConflictError,
    MemoryPolicyError,
    MemoryPolicyService,
    MemoryRecord,
    MemoryServiceError,
)

from . import sessions
from .config import get_settings
from .contracts import (
    ContextResolution,
    MuseDraftInput,
    MuseTurn,
    ReadingContext,
    TurnPolicy,
)
from .logger import ROOT_NAME
from .schemas import (
    CaptureInspection,
    ChatRequest,
    ChatResponse,
    ConnectionDeclineInspection,
    MemoryCaptureNotice,
    ReleaseInspection,
    TraceReference,
    TurnInspection,
)
from .telemetry import record_failure, set_span_attrs

logger = logging.getLogger(f"{ROOT_NAME}.backend")

settings = get_settings()

CHAPTER_PATTERN = re.compile(r"\b(?:chapter|ch\.?)\s*[:#]?\s*([1-9]\d*)\b", re.IGNORECASE)
TITLE_PREFIX_PATTERN = re.compile(r"\b(?:i(?:'m| am)\s+)?(?:reading|read)\s+(?P<title>.+)$", re.IGNORECASE)
TITLE_END_PATTERN = re.compile(
    r"\s*(?:,|;|\band\s+i(?:'m| am| have|'ve|’ve)\s+(?:read|finished|through|up to|at|on))\b",
    re.IGNORECASE,
)
COMPLETION_PATTERN = re.compile(
    r"\b(?:i(?:'ve|’ve| have)\s+(?:now\s+)?(?:finished|completed|read\s+through|got\s+through)|"
    r"i(?:'m| am)\s+(?:now\s+)?done\s+with)\b",
    re.IGNORECASE,
)
IN_PROGRESS_PATTERN = re.compile(
    r"\b(?:still\s+(?:in|reading)|not\s+(?:yet\s+)?(?:finished|completed|done)|"
    r"(?:have|has|had)\s+not\s+(?:finished|completed)|"
    r"(?:haven['’]?t|hasn['’]?t|hadn['’]?t)\s+(?:finished|completed)|"
    r"in\s+the\s+middle|partway\s+through)\b",
    re.IGNORECASE,
)
AFFIRMATION_PATTERN = re.compile(
    r"^\s*(?:yes|yeah|yep|correct|that(?:'s| is)\s+right)\b",
    re.IGNORECASE,
)


def _title_before_chapter(message: str, chapter_start: int) -> str | None:
    title_match = TITLE_PREFIX_PATTERN.search(message[:chapter_start])
    if title_match is None:
        return None
    title = TITLE_END_PATTERN.split(title_match.group("title"), maxsplit=1)[0].strip(" \"'“”.,:;")
    return title or None


def _title_without_chapter(message: str) -> str | None:
    title_match = TITLE_PREFIX_PATTERN.search(message)
    if title_match is None:
        return None
    title = TITLE_END_PATTERN.split(title_match.group("title"), maxsplit=1)[0].strip(
        " \"'“”.,:;"
    )
    return title or None


def _candidate_confirmed(message: str, candidate: sessions.ReadingCandidate) -> bool:
    lowered = message.lower()
    aliases = [candidate.book_id.replace("-", " ")]
    if candidate.book_title:
        aliases.append(candidate.book_title.lower())
    return bool(
        AFFIRMATION_PATTERN.search(message)
        or any(alias in lowered for alias in aliases)
        or "wonderland" in lowered and candidate.book_id == "pg11"
    )


def _work_id_for_title(title: str) -> str:
    """Resolve known titles to stable corpus IDs; keep unknown books as slugs."""
    words = set(re.findall(r"[a-z0-9]+", title.lower()))
    if "alice" in words and "wonderland" in words:
        return "pg11"
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def resolve_reading_context(request: ChatRequest) -> ContextResolution:
    """Resolve reading context from explicit reader declarations only.

    Regexes validate direct declarations. Librarian routing no longer runs
    here: Muse decides when a request depends on a book and calls the
    `librarian_route` tool during its own turn, inside the validated
    Provenance and release pipeline.
    """
    candidate = sessions.reading_candidate(request.session_id)
    selection = sessions.book_selection(request.session_id)
    in_progress = IN_PROGRESS_PATTERN.search(request.message) is not None
    completed = COMPLETION_PATTERN.search(request.message) is not None and not in_progress

    candidate_confirmed = bool(
        candidate and _candidate_confirmed(request.message, candidate)
    )
    if candidate and candidate_confirmed:
        selection = sessions.BookSelection(book_id=candidate.book_id, book_title=candidate.book_title)
        sessions.set_book_selection(request.session_id, selection)

    chapter_match = CHAPTER_PATTERN.search(request.message)
    explicit_title = (
        _title_before_chapter(request.message, chapter_match.start())
        if chapter_match
        else _title_without_chapter(request.message)
    )
    if explicit_title:
        book_id = _work_id_for_title(explicit_title)
        selection = sessions.BookSelection(book_id=book_id, book_title=explicit_title)
        sessions.set_book_selection(request.session_id, selection)

    if completed and chapter_match and selection:
        chapter = int(chapter_match.group(1))
        if candidate and selection.book_id == candidate.book_id:
            sessions.clear_reading_candidate(request.session_id)
        return ContextResolution(
            status="confirmed",
            work_id=selection.book_id,
            work_title=selection.book_title,
            book_version_id=librarian_service.version_for(selection.book_id),
            chapter_max=chapter,
            boundary_source="reader_confirmed",
            boundary_authorization_basis="explicit_progress",
            explanation="The reader explicitly confirmed this completed chapter in the current message.",
        )

    if (
        chapter_match is None
        and candidate
        and selection
        and selection.book_id == candidate.book_id
        and (completed or candidate_confirmed)
    ):
        sessions.clear_reading_candidate(request.session_id)
        return ContextResolution(
            status="confirmed",
            work_id=candidate.book_id,
            work_title=candidate.book_title,
            book_version_id=librarian_service.version_for(candidate.book_id),
            chapter_max=candidate.chapter,
            boundary_source="reader_confirmed",
            boundary_authorization_basis="explicit_progress",
            explanation="The reader confirmed the candidate book and completed scene in the current message.",
        )

    if selection:
        return ContextResolution(
            status="inferred",
            work_id=selection.book_id,
            work_title=selection.book_title,
            book_version_id=librarian_service.version_for(selection.book_id),
            explanation="The active book is known, but this request has no validated spoiler boundary yet.",
        )

    return ContextResolution(
        status="unknown",
        explanation=(
            "No confirmed book or reading boundary yet; Muse will call "
            "librarian_route during its own turn if the request appears to "
            "depend on a specific book."
        ),
    )


def prepare_reflection_turn(
    request: ChatRequest,
    *,
    allow_memory_capture: bool,
    prior_evidence: tuple[EvidenceRecord, ...] = (),
    resolution: ContextResolution | None = None,
) -> tuple[TurnInspection, str, dict[str, object]]:
    """Build the request-scoped Muse input and Provenance policy context."""
    resolution = resolution or resolve_reading_context(request)
    context = (
        ReadingContext(
            work_id=resolution.work_id,
            chapter_max=resolution.chapter_max,
            boundary_source=resolution.boundary_source,
        )
        if resolution.status == "confirmed" and resolution.work_id and resolution.chapter_max
        else None
    )
    turn_id = request.turn_id or str(uuid4())
    book_connection_permitted = (
        context is not None and librarian_service.has_corpus(context.work_id)
    )
    muse_turn = MuseTurn(
        turn_id=turn_id,
        user_message=request.message,
        reading_context=context,
        policy=TurnPolicy(
            spoiler_ceiling=context.chapter_max if context else None,
            allow_retrieval=book_connection_permitted,
            allow_connection=book_connection_permitted or web_reach_permitted(),
            allow_memory_capture=allow_memory_capture,
        ),
    )
    traces = [{
        "agent": "Router",
        "status": "complete",
        "detail": resolution.explanation,
    }]
    traces.extend([
        {"agent": "Librarian", "status": "waiting", "detail": "Waiting to see whether Muse requests bounded retrieval."},
        {"agent": "Serendipity", "status": "waiting", "detail": "Waiting to see whether Muse requests connection discovery."},
    ])

    muse_payload = MuseDraftInput(
        mode="draft",
        muse_turn=muse_turn,
        context_resolution=resolution,
        prior_evidence=prior_evidence,
    )
    inspection_prompt = json.dumps(
        muse_payload.model_dump(mode="json", exclude={"prior_evidence"}),
        ensure_ascii=False,
    )
    muse_input = muse_payload.model_dump_json()
    review_context: dict[str, object] = {
        "policy_constraints": muse_turn.policy.model_dump(mode="json"),
        "reading_context": context.model_dump(mode="json") if context else None,
    }
    traces.append({"agent": "Muse", "status": "running", "detail": "Drafting a candidate response."})
    return TurnInspection(
        muse_turn=muse_turn.model_dump(mode="json"),
        context_resolution=resolution.model_dump(mode="json"),
        traces=traces,
        # Re-resolved passages are supplied to Muse but not duplicated into the
        # developer-only Inspect diagnostics.
        prompt=inspection_prompt,
    ), muse_input, review_context


@dataclass(frozen=True)
class AutomaticCaptureExecution:
    """Internal storage outcome; candidate text never enters inspection."""

    inspection: CaptureInspection
    record: MemoryRecord | None = None


def _commit_automatic_capture(
    release: ReflectionRelease,
    service: MemoryPolicyService,
    context: AccountContext,
) -> AutomaticCaptureExecution:
    """Apply deterministic policy without changing the response decision."""
    decision = release.capture_decision
    nomination = release.capture_nomination or "unavailable"
    if release.release_source == "application_emotional_boundary":
        preflight = release.boundary_origin == "preflight"
        return AutomaticCaptureExecution(
            inspection=CaptureInspection(
                nomination="unavailable" if preflight else nomination,
                provenance_decision=None if preflight else decision,
                binding="not_applicable",
                storage="suppressed",
                reason_code="emotional_boundary_capture_suppressed",
            )
        )
    if release.capture_failure is not None:
        return AutomaticCaptureExecution(
            inspection=CaptureInspection(
                nomination=nomination,
                provenance_decision=decision,
                binding="invalid",
                storage="refused",
                reason_code=release.capture_failure,
            )
        )
    candidate = release.automatic_capture_candidate
    if candidate is None:
        return AutomaticCaptureExecution(
            inspection=CaptureInspection(
                nomination=nomination,
                provenance_decision=decision,
                binding="not_applicable",
                storage="not_applicable",
                reason_code="not_applicable" if decision == "no_candidate" else None,
            )
        )
    if release.release_source == "application_safe_decline":
        return AutomaticCaptureExecution(
            inspection=CaptureInspection(
                nomination=nomination,
                provenance_decision=decision,
                binding="exact",
                storage="suppressed",
                reason_code="safe_decline_capture_suppressed",
            )
        )
    try:
        result = service.save_automatic(context, candidate)
    except MemoryPolicyError as error:
        return AutomaticCaptureExecution(
            inspection=CaptureInspection(
                nomination="candidate",
                provenance_decision=decision,
                binding="exact",
                storage="refused",
                reason_code=error.reason,
            )
        )
    except MemoryConflictError:
        return AutomaticCaptureExecution(
            inspection=CaptureInspection(
                nomination="candidate",
                provenance_decision=decision,
                binding="exact",
                storage="refused",
                reason_code="source_event_conflict",
            )
        )
    except MemoryServiceError:
        return AutomaticCaptureExecution(
            inspection=CaptureInspection(
                nomination="candidate",
                provenance_decision=decision,
                binding="exact",
                storage="refused",
                reason_code="storage_unavailable",
            )
        )
    return AutomaticCaptureExecution(
        inspection=CaptureInspection(
            nomination="candidate",
            provenance_decision=decision,
            binding="exact",
            storage="committed",
            reason_code=None if result.created else "idempotent_replay",
        ),
        record=result.record,
    )


def _replace_trace(
    inspection: TurnInspection,
    agent: str,
    *,
    status: str,
    detail: str,
) -> None:
    """Replace one preallocated agent trace with fixed application metadata."""
    for index, trace in enumerate(inspection.traces):
        if trace.get("agent") == agent:
            inspection.traces[index] = {
                "agent": agent,
                "status": status,
                "detail": detail,
            }
            return


def _apply_connection_inspection(
    inspection: TurnInspection,
    run: ConnectionRunInspection,
) -> tuple[str, ...]:
    """Project one nested Serendipity run as fixed metadata only."""
    book_outcomes = run.book_search_outcomes

    if run.status != "proposal":
        inspection.connection_decline = ConnectionDeclineInspection(
            reason=run.reason or "retrieval_unavailable",
            failure_code=(
                "connection_discovery_failed" if run.failure_code else None
            ),
        )
        _replace_trace(
            inspection,
            "Serendipity",
            status="failed" if run.failure_code else "declined",
            detail=(
                "Connection discovery failed closed; no diagnostic content was exposed."
                if run.failure_code
                else "Serendipity returned a typed decline; no diagnostic content was exposed."
            ),
        )
        return book_outcomes

    _replace_trace(
        inspection,
        "Serendipity",
        status="complete",
        detail=(
            "Serendipity returned a validated proposal; release still depends "
            "on the shared evidence and Provenance gates."
        ),
    )
    return book_outcomes


def _mark_connection_skipped(inspection: TurnInspection) -> None:
    _replace_trace(
        inspection,
        "Serendipity",
        status="skipped",
        detail="Muse did not call serendipity_explore for this turn.",
    )


def _finalize_librarian_inspection(
    inspection: TurnInspection,
    release: ReflectionRelease,
    *,
    connection_book_outcomes: tuple[str, ...],
) -> None:
    """Surface successful direct grounding without leaking rejected content."""
    direct_calls = release.librarian_grounding_calls
    direct_kinds = tuple(
        response.get("kind")
        for call in direct_calls
        if isinstance((response := call.get("response")), dict)
    )
    connection_failed = "retrieval_unavailable" in connection_book_outcomes
    direct_failed = any(
        call.get("outcome") != "success" for call in direct_calls
    ) or "failure" in direct_kinds
    direct_clarified = "clarification" in direct_kinds
    direct_no_match = direct_kinds and all(kind == "no_match" for kind in direct_kinds)
    released = release.release_source == "muse_candidate"
    inspection.librarian_grounding = (
        list(direct_calls) if released else []
    )

    if not released and (connection_book_outcomes or direct_calls):
        status = "declined"
        detail = "Retrieval diagnostics were withheld because no Muse candidate was released."
    elif connection_failed or direct_failed:
        status = "failed"
        detail = "A Librarian call failed; no failed-retrieval content was exposed."
    elif connection_book_outcomes and direct_calls:
        status = "complete"
        detail = (
            "Librarian completed bounded connection retrieval and direct Muse "
            f"grounding ({len(direct_calls)} call(s))."
        )
    elif connection_book_outcomes:
        status = "complete"
        detail = "Librarian completed bounded book-corpus retrieval for Serendipity."
    elif direct_clarified:
        status = "declined"
        detail = "Librarian requested clarification instead of searching the corpus."
    elif direct_no_match:
        status = "complete"
        detail = "Muse asked Librarian to route this request; no book match was found."
    elif direct_calls:
        status = "complete"
        detail = f"Muse called Librarian directly {len(direct_calls)} time(s) for book grounding."
    else:
        status = "skipped"
        detail = "No Librarian retrieval was requested for this turn."

    _replace_trace(
        inspection,
        "Librarian",
        status=status,
        detail=detail,
    )


def _rehydrate_session_evidence(session_id: str) -> tuple[EvidenceRecord, ...]:
    """Resolve exact IDs cited by earlier released replies; never persist text."""
    records: dict[str, EvidenceRecord] = {}
    for evidence_id in sessions.released_evidence_ids(session_id):
        try:
            record = librarian_service.fetch_by_id(evidence_id)
        except Exception:
            continue
        if record is None:
            continue
        existing = records.get(record.evidence_id)
        if existing is not None and existing != record:
            raise ValueError("a released evidence ID resolved ambiguously")
        records[record.evidence_id] = record
    return tuple(records.values())


async def _run_chat_pipeline(
    request: ChatRequest,
    reading_state: sessions.ReadingStateSnapshot,
    service: MemoryPolicyService,
    account: AccountContext,
) -> tuple[TurnInspection, ReflectionRelease, AutomaticCaptureExecution]:
    """Run the agent pipeline without adding request content to telemetry."""
    prior_evidence = _rehydrate_session_evidence(request.session_id)
    resolution = resolve_reading_context(request)
    release: ReflectionRelease | None = None
    try:
        boundary = await assess_emotional_boundary(
            request.message,
            EmotionalContentPolicy(),
            provenance=emotional_boundary_agent,
        )
    except asyncio.CancelledError:
        raise
    except EmotionalBoundaryValidationError:
        release = emotional_preflight_safe_decline(
            failure_type="validation",
            retryable=False,
        )
    except Exception:
        release = emotional_preflight_safe_decline()
    else:
        if boundary.decision == "apply_boundary":
            release = emotional_boundary_release(origin="preflight")

    inspection, muse_input, review_context = prepare_reflection_turn(
        request,
        allow_memory_capture=service.capture_enabled(account),
        prior_evidence=prior_evidence,
        resolution=resolution,
    )

    context = inspection.muse_turn.get("reading_context")
    book_version_id = (
        librarian_service.version_for(context["work_id"]) if context else None
    )
    release_scope = (
        ReleaseScope(
            work_id=context["work_id"],
            book_version_id=book_version_id,
            chapter_max=context["chapter_max"],
        )
        if context and book_version_id
        else None
    )
    nested_connections: tuple[ConnectionRunInspection, ...] = ()
    if release is None:
        token = set_confirmed_reading(
            ConfirmedReading(
                work_id=context["work_id"], chapter_max=context["chapter_max"]
            )
            if context
            else None
        )
        evidence_token = set_turn_evidence(prior_evidence)
        reader_message_token = set_reader_message(request.message)
        session_id_token = set_session_id(request.session_id)
        try:
            active_memories = tuple(service.list_active(account))
        except MemoryServiceError:
            active_memories = ()
        memories_token = set_active_memories(active_memories)
        connection_token = begin_connection_inspection()
        try:
            release = await reflection_reply(
                muse_input,
                sessions.history(request.session_id),
                muse=muse_chat_agent,
                provenance=provenance_agent,
                review_context=review_context,
                release_scope=release_scope,
                previously_released_evidence_ids=frozenset(
                    record.evidence_id for record in prior_evidence
                ),
                capture_source_text=request.message,
                source_event_id=inspection.muse_turn["turn_id"],
            )
        finally:
            nested_connections = connection_inspections()
            reset_connection_inspection(connection_token)
            reset_active_memories(memories_token)
            reset_reader_message(reader_message_token)
            reset_session_id(session_id_token)
            reset_turn_evidence(evidence_token)
            reset_confirmed_reading(token)
    connection_book_outcomes: tuple[str, ...] = ()
    if nested_connections:
        connection_book_outcomes = _apply_connection_inspection(
            inspection,
            nested_connections[-1],
        )
    else:
        _mark_connection_skipped(inspection)
    _finalize_librarian_inspection(
        inspection,
        release,
        connection_book_outcomes=connection_book_outcomes,
    )
    if release.release_source != "muse_candidate":
        sessions.restore_reading_state(request.session_id, reading_state)
    capture = _commit_automatic_capture(release, service, account)
    sessions.append_turn(
        request.session_id,
        request.message,
        release.reply,
        turn_id=inspection.muse_turn["turn_id"],
        release_source=release.release_source,
        evidence_ids=release.evidence_ids,
        review_finding_codes=release.review_finding_codes,
    )
    return inspection, release, capture


class ChatTurnError(RuntimeError):
    """Stable application failure exposed to transport adapters."""

    def __init__(self, trace: TraceReference) -> None:
        super().__init__("chat turn failed")
        self.trace = trace


async def run_chat_turn(
    request: ChatRequest,
    service: MemoryPolicyService,
    account: AccountContext,
) -> ChatResponse:
    """Run one complete, transport-independent chat turn."""
    started = perf_counter()
    reading_state = sessions.snapshot_reading_state(request.session_id)
    cancelled = False
    failure: Exception | None = None
    inspection: TurnInspection | None = None
    release: ReflectionRelease | None = None
    capture: AutomaticCaptureExecution | None = None
    with logfire.span(
        "chat.turn",
        status="started",
    ) as span:
        span_context = span.get_span_context()
        trace = TraceReference(
            trace_id=format_trace_id(span_context.trace_id),
        )
        try:
            inspection, release, capture = await _run_chat_pipeline(
                request,
                reading_state,
                service,
                account,
            )
        except asyncio.CancelledError:
            cancelled = True
            sessions.restore_reading_state(request.session_id, reading_state)
            record_failure(
                span,
                stage="chat_turn",
                code="request_cancelled",
                retryable=False,
                failure_type="application",
            )
            set_span_attrs(
                span,
                {
                    "request.outcome": "cancelled",
                },
            )
        except Exception as exc:
            failure = exc
            sessions.restore_reading_state(request.session_id, reading_state)
            record_failure(
                span,
                stage="chat_turn",
                code="chat_turn_failed",
                retryable=True,
                failure_type="application",
            )
            set_span_attrs(
                span,
                {
                    "request.outcome": "failed",
                },
            )
        else:
            set_span_attrs(
                span,
                {
                    "status": "success",
                    "request.outcome": (
                        "declined"
                        if release.release_source == "application_safe_decline"
                        else "completed"
                    ),
                    "release.source": release.release_source,
                    "release.boundary_origin": release.boundary_origin,
                },
            )

    if cancelled:
        logger.info(
            "Agent run cancelled elapsed=%.2fs failure_stage=chat_turn "
            "failure_code=request_cancelled retryable=false",
            perf_counter() - started,
        )
        raise asyncio.CancelledError

    if failure is not None:
        logger.error(
            "Agent run failed elapsed=%.2fs failure_stage=chat_turn "
            "failure_code=chat_turn_failed retryable=true",
            perf_counter() - started,
        )
        raise ChatTurnError(trace) from None

    assert inspection is not None and release is not None and capture is not None

    logger.info(
        "Agent run completed elapsed=%.2fs release_source=%s "
        "provenance_path=%s findings=%s revisions=%d failure_stage=%s",
        perf_counter() - started,
        release.release_source,
        ",".join(release.provenance_verdicts) or "none",
        # Risk codes only. The matching critique text quotes rejected candidate
        # content and is intentionally absent from logs and API responses.
        ",".join(release.finding_codes) or "none",
        release.revision_count,
        release.failure_stage or "none",
    )
    inspection.release = ReleaseInspection(
        release_source=release.release_source,
        boundary_origin=release.boundary_origin,
        provenance_verdicts=release.provenance_verdicts,
        finding_codes=release.finding_codes,
        revision_count=release.revision_count,
        failure_stage=release.failure_stage,
        capture=capture.inspection,
    )
    verdict_path = " → ".join(release.provenance_verdicts)
    if release.release_source == "muse_candidate":
        inspection.traces[-1] = {
            "agent": "Muse",
            "status": "complete",
            "detail": (
                "Provenance and deterministic release validation approved the "
                "candidate that was released."
            ),
        }
        provenance_status = "complete"
        provenance_detail = f"Recorded review path: {verdict_path}."
    elif release.release_source == "application_emotional_boundary":
        if release.boundary_origin == "preflight":
            inspection.traces[-1] = {
                "agent": "Muse",
                "status": "skipped",
                "detail": (
                    "The emotional boundary was applied before Muse or its tools ran."
                ),
            }
            provenance_detail = (
                "The no-tool preflight required the application-owned emotional boundary."
            )
        else:
            inspection.traces[-1] = {
                "agent": "Muse",
                "status": "declined",
                "detail": (
                    "Muse ran, but its candidate was replaced by the fixed "
                    "application-owned emotional boundary."
                ),
            }
            provenance_detail = (
                "Candidate review caught a preflight miss and required the fixed "
                f"boundary; recorded review path: {verdict_path}."
            )
        provenance_status = "complete"
    else:
        inspection.traces[-1] = {
            "agent": "Muse",
            "status": (
                "skipped"
                if release.failure_stage == "emotional_boundary_preflight"
                else "declined"
            ),
            "detail": (
                "The emotional-boundary preflight failed closed before Muse ran."
                if release.failure_stage == "emotional_boundary_preflight"
                else "No Muse candidate was released; the application supplied its safe decline."
            ),
        }
        if release.failure_stage == "deterministic_validation":
            provenance_status = "complete"
            provenance_detail = (
                f"Recorded review path: {verdict_path}; deterministic release "
                "validation failed closed."
            )
        else:
            if release.failure_stage in {
                "emotional_boundary_preflight",
                "provenance_review",
            }:
                provenance_status = "failed"
                provenance_detail = (
                    "The emotional-boundary preflight failed; no candidate was produced."
                    if release.failure_stage == "emotional_boundary_preflight"
                    else "Provenance review failed; no candidate was released."
                )
            elif release.failure_stage:
                provenance_status = "declined"
                provenance_detail = (
                    f"Candidate production failed at {release.failure_stage}; no "
                    "candidate was released."
                )
            else:
                provenance_status = "declined"
                provenance_detail = (
                    f"Recorded review path: {verdict_path}; no Muse candidate was released."
                )
    inspection.traces.append({
        "agent": "Provenance",
        "status": provenance_status,
        "detail": provenance_detail,
    })
    inspection.traces.append(
        {
            "agent": "Memory & Policy",
            "status": (
                "complete"
                if capture.inspection.storage == "committed"
                else (
                    "declined"
                    if capture.inspection.storage in {"refused", "suppressed"}
                    else "not_run"
                )
            ),
            "detail": (
                "A reviewed candidate was committed by deterministic policy."
                if capture.inspection.storage == "committed"
                else (
                    f"No write occurred: {capture.inspection.reason_code}."
                    if capture.inspection.reason_code
                    else "No reviewed memory candidate reached storage."
                )
            ),
        }
    )
    notice = (
        MemoryCaptureNotice()
        if capture.record is not None and capture.inspection.storage == "committed"
        else None
    )
    return ChatResponse(
        reply=release.reply,
        inspection=inspection,
        trace=trace,
        memory_capture=notice,
    )
