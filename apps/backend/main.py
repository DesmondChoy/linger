"""FastAPI entry point for the Linger chat prototype."""

import json
import logging
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

# Configure the exporter before application-owned spans can be created.
from .telemetry import configure_telemetry, record_failure, set_span_attrs

configure_telemetry()

import logfire  # noqa: E402  (import order is load-bearing, see above)

from src.linger.agents.muse.agent import muse_chat_agent  # noqa: E402
from src.linger.agents.provenance.agent import provenance_agent  # noqa: E402
from src.linger.contracts.turn import ConfirmedReading, ReleaseScope
from src.linger.orchestration.reflection import ReflectionRelease, reflection_reply
from src.linger.orchestration.turn_context import reset_confirmed_reading, set_confirmed_reading
from src.linger.services.memory import (
    AccountContext,
    MemoryConflictError,
    MemoryNotFoundError,
    MemoryPolicyError,
    MemoryPolicyService,
    MemoryRecord,
    MemoryServiceError,
    MemoryStorageError,
)

from . import sessions
from .config import REPO_ROOT, get_settings
from .contracts import (
    ContextResolution,
    MuseTurn,
    ReadingContext,
    TurnPolicy,
)
from .hybrid_librarian import HybridLibrarian
from .logger import ROOT_NAME, configure_logging
from .schemas import (
    CapturePreferenceRequest,
    CapturePreferenceResponse,
    CaptureInspection,
    ChatRequest,
    ChatResponse,
    MemoryCaptureNotice,
    MemoryResponse,
    MemorySaveResponse,
    MemoryStateResponse,
    MemoryWriteRequest,
    ReleaseInspection,
    TurnInspection,
)

configure_logging()
logger = logging.getLogger(f"{ROOT_NAME}.backend")

settings = get_settings()
app = FastAPI(title="Linger Chat API")
memory_service = MemoryPolicyService(REPO_ROOT / "memories")
memory_context = AccountContext(settings.linger_account_id)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)

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
librarian = HybridLibrarian()


def _title_before_chapter(message: str, chapter_start: int) -> str | None:
    title_match = TITLE_PREFIX_PATTERN.search(message[:chapter_start])
    if title_match is None:
        return None
    title = TITLE_END_PATTERN.split(title_match.group("title"), maxsplit=1)[0].strip(" \"'“”.,:;")
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


def _inferred_context(message: str) -> tuple[str, str, int] | None:
    text = message.lower()
    if "caterpillar" in text:
        return ("pg11", "Alice's Adventures in Wonderland", 5)
    if "ada" in text or "mabel" in text:
        return ("pg11", "Alice's Adventures in Wonderland", 2)
    if any(cue in text for cue in ("milk", "apples")) and any(cue in text for cue in ("pigs", "animal farm", "equality", "power")):
        return ("animal-farm", "Animal Farm", 3)
    return None


def resolve_reading_context(request: ChatRequest) -> ContextResolution:
    """Accept only an explicit current-turn completion as a retrieval boundary.

    Regexes validate the reader's direct declaration. They never infer progress,
    and no chapter ceiling is carried into a later request.
    """
    candidate = sessions.reading_candidate(request.session_id)
    selection = sessions.book_selection(request.session_id)
    in_progress = IN_PROGRESS_PATTERN.search(request.message) is not None
    completed = COMPLETION_PATTERN.search(request.message) is not None and not in_progress

    if candidate and _candidate_confirmed(request.message, candidate):
        selection = sessions.BookSelection(book_id=candidate.book_id, book_title=candidate.book_title)
        sessions.set_book_selection(request.session_id, selection)

    chapter_match = CHAPTER_PATTERN.search(request.message)
    explicit_title = _title_before_chapter(request.message, chapter_match.start()) if chapter_match else None
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
            chapter_max=chapter,
            boundary_source="reader_confirmed",
            explanation="The reader explicitly confirmed this completed chapter in the current message.",
        )

    if completed and chapter_match is None and candidate and selection and selection.book_id == candidate.book_id:
        sessions.clear_reading_candidate(request.session_id)
        return ContextResolution(
            status="confirmed",
            work_id=candidate.book_id,
            work_title=candidate.book_title,
            chapter_max=candidate.chapter,
            boundary_source="reader_confirmed",
            explanation="The reader confirmed the candidate book and completed scene in the current message.",
        )

    inferred = _inferred_context(request.message) if explicit_title is None else None
    if inferred:
        sessions.set_reading_candidate(
            request.session_id,
            sessions.ReadingCandidate(book_id=inferred[0], book_title=inferred[1], chapter=inferred[2]),
        )
        return ContextResolution(
            status="inferred",
            work_id=inferred[0],
            work_title=inferred[1],
            chapter_max=inferred[2],
            boundary_source="inferred_from_question",
            explanation="A possible book and scene were detected, but neither is a retrieval boundary.",
        )

    if selection:
        return ContextResolution(
            status="confirmed",
            work_id=selection.book_id,
            work_title=selection.book_title,
            explanation="The reader confirmed the book, but not a completed chapter in this request.",
        )

    return ContextResolution(
        status="unknown",
        explanation="No book or safe reading boundary was established for this request.",
    )


def _inspection_for(
    request: ChatRequest,
    *,
    allow_memory_capture: bool,
) -> tuple[TurnInspection, str, dict[str, object]]:
    """Build the request-scoped Muse input and Provenance policy context."""
    resolution = resolve_reading_context(request)
    context = (
        ReadingContext(work_id=resolution.work_id, chapter_max=resolution.chapter_max)
        if resolution.status == "confirmed" and resolution.work_id and resolution.chapter_max
        else None
    )
    turn_id = request.turn_id or str(uuid4())
    muse_turn = MuseTurn(
        turn_id=turn_id,
        user_message=request.message,
        reading_context=context,
        policy=TurnPolicy(
            spoiler_ceiling=context.chapter_max if context else None,
            allow_retrieval=context is not None and librarian.has_corpus(context.work_id),
            allow_connection=context is not None and librarian.has_corpus(context.work_id),
            allow_memory_capture=allow_memory_capture,
        ),
    )
    traces = [{
        "agent": "Router",
        "status": "complete" if context else "waiting",
        "detail": resolution.explanation,
    }]
    brief_data = request_data = evidence_data = proposal_data = None
    traces.extend([
        {"agent": "Librarian", "status": "not_wired", "detail": "Retrieval is delegated to Muse, which decides whether to call it. The router no longer observes this."},
        {"agent": "Serendipity", "status": "not_wired", "detail": "Connection discovery is delegated to Muse. The router no longer observes this."},
    ])

    muse_payload = {
        "muse_turn": muse_turn.model_dump(mode="json"),
        "context_resolution": resolution.model_dump(mode="json"),
        "connection_proposal": proposal_data,
        "supporting_evidence": evidence_data,
    }
    muse_input = json.dumps(muse_payload, ensure_ascii=False)
    review_context: dict[str, object] = {
        "policy_constraints": muse_turn.policy.model_dump(mode="json"),
        "reading_context": context.model_dump(mode="json") if context else None,
        "connection_proposal": proposal_data,
        "cited_evidence": evidence_data,
    }
    traces.append({"agent": "Muse", "status": "running", "detail": "Drafting a candidate response."})
    return TurnInspection(
        muse_turn=muse_turn.model_dump(mode="json"),
        context_resolution=resolution.model_dump(mode="json"),
        traces=traces,
        connection_brief=brief_data,
        librarian_request=request_data,
        evidence_bundle=evidence_data,
        connection_proposal=proposal_data,
        prompt=muse_input,
    ), muse_input, review_context


def get_memory_service() -> MemoryPolicyService:
    """Return the application-owned memory service."""
    return memory_service


def get_memory_context() -> AccountContext:
    """Derive account scope from trusted server configuration."""
    return memory_context


MemoryServiceDependency = Annotated[MemoryPolicyService, Depends(get_memory_service)]
MemoryContextDependency = Annotated[AccountContext, Depends(get_memory_context)]


def _memory_response(record: MemoryRecord) -> MemoryResponse:
    return MemoryResponse(
        memory_id=record.memory_id,
        text=record.text,
        capture_type=record.capture_type,
        evidence_ids=list(record.evidence_ids),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


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


def _memory_http_error(error: MemoryServiceError) -> HTTPException:
    if isinstance(error, MemoryNotFoundError):
        return HTTPException(status_code=404, detail="Memory not found.")
    if isinstance(error, MemoryConflictError):
        return HTTPException(
            status_code=409,
            detail="This memory operation conflicts with an earlier request.",
        )
    if isinstance(error, MemoryStorageError):
        logger.error(
            "Memory storage failed failure_stage=memory_storage "
            "failure_code=storage_unavailable retryable=true"
        )
        return HTTPException(status_code=500, detail="Memory storage is unavailable.")
    logger.error(
        "Memory operation failed failure_stage=memory_operation "
        "failure_code=operation_failed retryable=false"
    )
    return HTTPException(status_code=400, detail="Memory operation failed.")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": settings.linger_model}


async def _run_chat_pipeline(
    request: ChatRequest,
    reading_state: sessions.ReadingStateSnapshot,
    service: MemoryPolicyService,
    account: AccountContext,
) -> tuple[TurnInspection, ReflectionRelease, AutomaticCaptureExecution]:
    """Run the agent pipeline without adding request content to telemetry."""
    inspection, muse_input, review_context = _inspection_for(
        request,
        allow_memory_capture=service.capture_enabled(account),
    )
    context = inspection.muse_turn.get("reading_context")
    book_version_id = librarian.version_for(context["work_id"]) if context else None
    release_scope = (
        ReleaseScope(
            work_id=context["work_id"],
            book_version_id=book_version_id,
            chapter_max=context["chapter_max"],
        )
        if context and book_version_id
        else None
    )
    token = set_confirmed_reading(
        ConfirmedReading(work_id=context["work_id"], chapter_max=context["chapter_max"])
        if context
        else None
    )
    try:
        release: ReflectionRelease = await reflection_reply(
            muse_input,
            sessions.history(request.session_id),
            muse=muse_chat_agent,
            provenance=provenance_agent,
            review_context=review_context,
            release_scope=release_scope,
            capture_source_text=request.message,
            source_event_id=inspection.muse_turn["turn_id"],
        )
    finally:
        reset_confirmed_reading(token)
    if release.release_source == "application_safe_decline":
        sessions.restore_reading_state(request.session_id, reading_state)
    capture = _commit_automatic_capture(release, service, account)
    sessions.append_turn(request.session_id, request.message, release.reply)
    return inspection, release, capture


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    service: MemoryServiceDependency,
    context: MemoryContextDependency,
) -> ChatResponse:
    """Run the complete output gate before releasing or storing a reply."""
    started = perf_counter()
    reading_state = sessions.snapshot_reading_state(request.session_id)
    failure: Exception | None = None
    inspection: TurnInspection | None = None
    release: ReflectionRelease | None = None
    capture: AutomaticCaptureExecution | None = None
    with logfire.span(
        "chat.request",
        **{
            "http.route": "/api/chat",
            "http.request.method": "POST",
            "status": "started",
        },
    ) as span:
        try:
            inspection, release, capture = await _run_chat_pipeline(
                request,
                reading_state,
                service,
                context,
            )
        except Exception as exc:
            failure = exc
            sessions.restore_reading_state(request.session_id, reading_state)
            record_failure(
                span,
                stage="chat_request",
                code="agent_pipeline_failed",
                retryable=True,
                failure_type="application",
            )
            set_span_attrs(
                span,
                {
                    "http.response.status_code": 502,
                    "request.outcome": "failed",
                },
            )
        else:
            set_span_attrs(
                span,
                {
                    "status": "success",
                    "http.response.status_code": 200,
                    "request.outcome": (
                        "declined"
                        if release.release_source == "application_safe_decline"
                        else "completed"
                    ),
                },
            )

    if failure is not None:
        logger.error(
            "Agent run failed elapsed=%.2fs failure_stage=chat_request "
            "failure_code=agent_pipeline_failed retryable=true",
            perf_counter() - started,
        )
        raise HTTPException(
            status_code=502,
            detail="The model call failed. Try again.",
        ) from None

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
    else:
        inspection.traces[-1] = {
            "agent": "Muse",
            "status": "declined",
            "detail": "No Muse candidate was released; the application supplied its safe decline.",
        }
        if release.failure_stage == "deterministic_validation":
            provenance_status = "complete"
            provenance_detail = (
                f"Recorded review path: {verdict_path}; deterministic release "
                "validation failed closed."
            )
        else:
            if release.failure_stage == "provenance_review":
                provenance_status = "failed"
                provenance_detail = "Provenance review failed; no candidate was released."
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
                    if capture.inspection.storage == "refused"
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
        MemoryCaptureNotice(memory_id=capture.record.memory_id)
        if capture.record is not None and capture.inspection.storage == "committed"
        else None
    )
    return ChatResponse(
        reply=release.reply,
        inspection=inspection,
        memory_capture=notice,
    )


@app.delete("/api/sessions/{session_id}", status_code=204)
async def reset_session(session_id: str) -> None:
    sessions.clear(session_id)


@app.get("/api/memories", response_model=MemoryStateResponse)
async def list_memories(
    service: MemoryServiceDependency,
    context: MemoryContextDependency,
) -> MemoryStateResponse:
    """Return this account's preference and active memory versions."""
    try:
        return MemoryStateResponse(
            capture_enabled=service.capture_enabled(context),
            memories=[_memory_response(record) for record in service.list_active(context)],
        )
    except MemoryServiceError as error:
        raise _memory_http_error(error) from None


@app.put(
    "/api/memory-capture-preference",
    response_model=CapturePreferenceResponse,
)
async def set_memory_capture_preference(
    request: CapturePreferenceRequest,
    service: MemoryServiceDependency,
    context: MemoryContextDependency,
) -> CapturePreferenceResponse:
    """Persist an explicit user opt-in or pause action without a model."""
    try:
        service.set_capture_enabled(context, request.enabled)
        return CapturePreferenceResponse(enabled=service.capture_enabled(context))
    except MemoryServiceError as error:
        raise _memory_http_error(error) from None


@app.post(
    "/api/memories",
    response_model=MemorySaveResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_memory(
    request: MemoryWriteRequest,
    service: MemoryServiceDependency,
    context: MemoryContextDependency,
) -> MemorySaveResponse:
    """Save words the user explicitly chose, bypassing every agent."""
    try:
        result = service.save_explicit(
            context,
            text=request.text,
            source_event_id=f"ui-save:{request.operation_id}",
        )
        return MemorySaveResponse(
            memory=_memory_response(result.record),
            created=result.created,
        )
    except MemoryServiceError as error:
        raise _memory_http_error(error) from None


@app.put(
    "/api/memories/{memory_id}",
    response_model=MemorySaveResponse,
    status_code=status.HTTP_201_CREATED,
)
async def correct_memory(
    memory_id: str,
    request: MemoryWriteRequest,
    service: MemoryServiceDependency,
    context: MemoryContextDependency,
) -> MemorySaveResponse:
    """Create a linked correction while preserving the original record."""
    try:
        result = service.correct(
            context,
            memory_id,
            text=request.text,
            source_event_id=f"ui-correction:{request.operation_id}",
        )
        return MemorySaveResponse(
            memory=_memory_response(result.record),
            created=result.created,
        )
    except MemoryServiceError as error:
        raise _memory_http_error(error) from None


@app.delete("/api/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: str,
    service: MemoryServiceDependency,
    context: MemoryContextDependency,
) -> None:
    """Delete every stored version in the selected memory family."""
    try:
        service.delete(context, memory_id)
    except MemoryServiceError as error:
        raise _memory_http_error(error) from None
