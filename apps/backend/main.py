"""FastAPI entry point for the Linger chat prototype."""

import logging
import re
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from src.linger.agents.muse.agent import muse_chat_agent
from src.linger.agents.provenance.agent import provenance_agent
from src.linger.orchestration.reflection import reflection_reply
from src.linger.services.memory import (
    AccountContext,
    MemoryConflictError,
    MemoryNotFoundError,
    MemoryPolicyService,
    MemoryRecord,
    MemoryServiceError,
    MemoryStorageError,
)

from . import sessions
from .config import REPO_ROOT, get_settings
from .contracts import BookScope, ConnectionBrief, ConnectionProposal, LibrarianRequest, MuseTurn, ReadingContext, TurnPolicy
from .librarian import Librarian
from .logger import ROOT_NAME, configure_logging
from .schemas import (
    CapturePreferenceRequest,
    CapturePreferenceResponse,
    ChatRequest,
    ChatResponse,
    MemoryResponse,
    MemorySaveResponse,
    MemoryStateResponse,
    MemoryWriteRequest,
    TurnInspection,
)
from .serendipity import discover

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
    r"\b(?:finished|completed|read\s+through|got\s+through|done\s+with|done)\b",
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
CONNECTION_TRIGGERS = ("why", "feel", "identity", "who", "change", "rule", "authority", "power", "equal", "equality", "connect", "pattern")
librarian = Librarian()


def update_book_context(request: ChatRequest) -> sessions.BookContext | None:
    """Record a spoiler boundary only when the reader says a chapter is complete.

    This domain helper is intentionally independent of the upstream chat API;
    the streaming reading-companion integration will call it separately.
    """
    previous = sessions.book_context(request.session_id)
    candidate = sessions.reading_candidate(request.session_id)
    selection = sessions.book_selection(request.session_id)
    lowered = request.message.lower()
    in_progress = IN_PROGRESS_PATTERN.search(request.message) is not None
    completed = COMPLETION_PATTERN.search(request.message) is not None and not in_progress
    candidate_name_mentioned = bool(
        candidate
        and re.search(rf"\b{re.escape(candidate.book_id.split('-')[0])}\b", lowered)
    )
    if candidate and selection is None and (
        AFFIRMATION_PATTERN.search(request.message)
        or candidate_name_mentioned
        or "wonderland" in lowered and candidate.book_id.startswith("alice")
    ):
        sessions.set_book_selection(
            request.session_id,
            sessions.BookSelection(book_id=candidate.book_id, book_title=candidate.book_title),
        )
        selection = sessions.book_selection(request.session_id)
    chapter_match = CHAPTER_PATTERN.search(request.message)
    if chapter_match is None and candidate and selection and selection.book_id == candidate.book_id:
        if in_progress:
            return previous
        if completed:
            context = sessions.BookContext(
                book_id=candidate.book_id,
                book_title=candidate.book_title,
                chapter_max=candidate.chapter,
            )
            sessions.set_book_context(request.session_id, context)
            sessions.clear_reading_candidate(request.session_id)
            return context
    if chapter_match is None or not completed:
        if chapter_match:
            title_match = TITLE_PREFIX_PATTERN.search(request.message[: chapter_match.start()])
            if title_match:
                title = TITLE_END_PATTERN.split(title_match.group("title"), maxsplit=1)[0].strip(" \"'“”.,:;")
                if title:
                    sessions.set_book_selection(
                        request.session_id,
                        sessions.BookSelection(
                            book_id=re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-"), book_title=title,
                        ),
                    )
        return previous
    chapter = int(chapter_match.group(1))
    title_match = TITLE_PREFIX_PATTERN.search(request.message[: chapter_match.start()])
    if title_match:
        title = TITLE_END_PATTERN.split(title_match.group("title"), maxsplit=1)[0].strip(" \"'“”.,:;")
        if not title:
            return previous
        book_id = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        sessions.set_book_selection(request.session_id, sessions.BookSelection(book_id=book_id, book_title=title))
        context = sessions.BookContext(book_id=book_id, book_title=title, chapter_max=chapter)
    elif previous:
        context = previous.model_copy(update={"chapter_max": chapter})
    else:
        return None
    sessions.set_book_context(request.session_id, context)
    return context


def _inferred_context(message: str) -> tuple[str, str, int] | None:
    text = message.lower()
    if "caterpillar" in text:
        return ("alice-adventures-in-wonderland", "Alice's Adventures in Wonderland", 5)
    if "ada" in text or "mabel" in text:
        return ("alice-adventures-in-wonderland", "Alice's Adventures in Wonderland", 2)
    if any(cue in text for cue in ("milk", "apples")) and any(cue in text for cue in ("pigs", "animal farm", "equality", "power")):
        return ("animal-farm", "Animal Farm", 3)
    return None


def _inspection_for(request: ChatRequest) -> tuple[TurnInspection, str]:
    """Build bounded optional retrieval context before Muse and Provenance run."""
    confirmed = update_book_context(request)
    inferred = _inferred_context(request.message) if confirmed is None else None
    selection = sessions.book_selection(request.session_id)
    context = confirmed
    if context is None and inferred:
        sessions.set_reading_candidate(
            request.session_id,
            sessions.ReadingCandidate(book_id=inferred[0], book_title=inferred[1], chapter=inferred[2]),
        )
        resolution = {
            "status": "inferred", "work_id": inferred[0], "work_title": inferred[1],
            "chapter_max": inferred[2], "boundary_source": "inferred_from_question",
            "explanation": "A possible book and scene were detected, but neither is confirmed or used as reading progress.",
        }
    elif context:
        resolution = {
            "status": "confirmed", "work_id": context.book_id, "work_title": context.book_title,
            "chapter_max": context.chapter_max, "boundary_source": "reader_confirmed",
            "explanation": "The reader explicitly confirmed this completed chapter in chat.",
        }
    elif selection:
        resolution = {
            "status": "confirmed", "work_id": selection.book_id, "work_title": selection.book_title,
            "chapter_max": None, "boundary_source": None,
            "explanation": "The reader confirmed the book, but has not confirmed a completed chapter.",
        }
    else:
        resolution = {"status": "unknown", "work_id": None, "work_title": None, "chapter_max": None,
                      "boundary_source": None, "explanation": "No book or safe reading boundary was established."}

    turn_id = request.turn_id or str(uuid4())
    muse_turn = MuseTurn(
        turn_id=turn_id,
        user_message=request.message,
        reading_context=ReadingContext(
            work_id=context.book_id, chapter_max=context.chapter_max,
            boundary_source="reader_confirmed" if confirmed else "inferred_from_question",
        ) if context else None,
        policy=TurnPolicy(
            spoiler_ceiling=context.chapter_max if context else None,
            allow_retrieval=context is not None and librarian.has_corpus(context.book_id),
            allow_connection=context is not None and librarian.has_corpus(context.book_id),
        ),
    )
    traces = [{"agent": "Router", "status": "complete" if context else "waiting", "detail": resolution["explanation"]}]
    prompt = request.message
    if inferred and confirmed is None:
        prompt = (
            "A possible reading context was detected, but the reader has not confirmed the book. "
            "Do not use character names, plot details, quotations, chapter information, or facts from any book. "
            "Offer only a general reflection based on the reader's wording, then ask whether they mean "
            f"{inferred[1]}.\n\nUser message: {request.message}"
        )
    brief_data = request_data = evidence_data = proposal_data = None
    if context and librarian.has_corpus(context.book_id) and any(term in request.message.lower() for term in CONNECTION_TRIGGERS):
        brief = ConnectionBrief(cue=request.message, book_id=context.book_id, chapter_max=context.chapter_max)
        themes = (
            "power equal rule pigs milk"
            if context.book_id == "animal-farm"
            else "identity change rule authority growing myself"
        )
        retrieval = LibrarianRequest(
            query=f"{request.message} {themes}",
            book_scopes=[BookScope(book_id=context.book_id, chapter_max=context.chapter_max)],
        )
        evidence = librarian.retrieve(retrieval)
        connection = discover(brief, evidence)
        brief_data, request_data, evidence_data = (brief.model_dump(mode="json"), retrieval.model_dump(mode="json"), evidence.model_dump(mode="json"))
        traces.extend([
            {"agent": "Librarian", "status": "complete", "detail": f"Returned {len(evidence.items)} permitted passages."},
            {"agent": "Serendipity", "status": "complete" if isinstance(connection, ConnectionProposal) else "declined", "detail": "Returned a tentative connection." if isinstance(connection, ConnectionProposal) else connection.safe_next_step},
        ])
        if isinstance(connection, ConnectionProposal):
            proposal_data = connection.model_dump(mode="json")
            prompt += (
                "\n\nOPTIONAL GROUNDED THREAD FROM SERENDIPITY:\n"
                f"Tentative claim: {connection.tentative_claim}\nInterpretation: {connection.interpretation}\n"
                "Use this only if it helps answer the reader; present it as tentative."
            )
    else:
        traces.extend([
            {"agent": "Librarian", "status": "skipped", "detail": "No bounded connection search was requested for this turn."},
            {"agent": "Serendipity", "status": "skipped", "detail": "No bounded connection search was requested for this turn."},
        ])
    traces.append({"agent": "Muse", "status": "running", "detail": "Drafting a candidate response."})
    return TurnInspection(
        muse_turn=muse_turn.model_dump(mode="json"), context_resolution=resolution, traces=traces,
        connection_brief=brief_data, librarian_request=request_data, evidence_bundle=evidence_data,
        connection_proposal=proposal_data, prompt=prompt,
    ), prompt


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


def _memory_http_error(error: MemoryServiceError) -> HTTPException:
    if isinstance(error, MemoryNotFoundError):
        return HTTPException(status_code=404, detail="Memory not found.")
    if isinstance(error, MemoryConflictError):
        return HTTPException(
            status_code=409,
            detail="This memory operation conflicts with an earlier request.",
        )
    if isinstance(error, MemoryStorageError):
        logger.exception("Memory storage failed")
        return HTTPException(status_code=500, detail="Memory storage is unavailable.")
    logger.exception("Memory operation failed")
    return HTTPException(status_code=400, detail="Memory operation failed.")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": settings.linger_model}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Run the complete output gate before releasing or storing a reply."""
    started = perf_counter()
    reading_state = sessions.snapshot_reading_state(request.session_id)
    try:
        inspection, muse_input = _inspection_for(request)
        reply = await reflection_reply(
            muse_input,
            sessions.history(request.session_id),
            muse=muse_chat_agent,
            provenance=provenance_agent,
        )
        sessions.append_turn(request.session_id, request.message, reply)
    except Exception as exc:
        sessions.restore_reading_state(request.session_id, reading_state)
        logger.exception(
            "Agent run failed session=%s elapsed=%.2fs",
            request.session_id,
            perf_counter() - started,
        )
        raise HTTPException(
            status_code=502,
            detail="The model call failed. Try again.",
        ) from exc

    logger.info(
        "Agent run completed session=%s elapsed=%.2fs turns=%d",
        request.session_id,
        perf_counter() - started,
        len(sessions.history(request.session_id)),
    )
    inspection.traces[-1] = {"agent": "Muse", "status": "complete", "detail": "Candidate passed through Provenance and was released."}
    inspection.traces.append({"agent": "Provenance", "status": "complete", "detail": "Reviewed the response before release."})
    return ChatResponse(reply=reply, inspection=inspection)


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
        raise _memory_http_error(error) from error


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
        raise _memory_http_error(error) from error


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
        raise _memory_http_error(error) from error


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
        raise _memory_http_error(error) from error


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
        raise _memory_http_error(error) from error
