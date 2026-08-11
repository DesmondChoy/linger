"""FastAPI entry point for the Linger chat prototype."""

import logging
from time import perf_counter
from typing import Annotated

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
    try:
        reply = await reflection_reply(
            request.message,
            sessions.history(request.session_id),
            muse=muse_chat_agent,
            provenance=provenance_agent,
        )
        sessions.append_turn(request.session_id, request.message, reply)
    except Exception as exc:
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
    return ChatResponse(reply=reply)


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
