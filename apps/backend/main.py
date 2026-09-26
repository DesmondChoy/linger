"""FastAPI transport adapter for the Linger chat application."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import asdict
from time import perf_counter
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Configure the exporter before application-owned spans can be created.
from .telemetry import configure_telemetry, record_failure, set_span_attrs

configure_telemetry()

import logfire  # noqa: E402  (import order is load-bearing, see above)

from src.linger.services.memory import MemoryPolicyService  # noqa: E402

from . import sessions  # noqa: E402
from .auth import AccountDependency, router as auth_router  # noqa: E402
from .chat_turn import ChatTurnError, run_chat_turn  # noqa: E402
from .config import REPO_ROOT, get_settings  # noqa: E402
from .logger import configure_logging  # noqa: E402
from src.linger.orchestration.progress_context import (  # noqa: E402
    ProgressEvent,
    begin_progress,
    reset_progress,
)
from .library import router as library_router  # noqa: E402
from .rate_limit import enforce_chat_rate_limit  # noqa: E402
from .schemas import ChatRequest, ChatResponse  # noqa: E402
from .transcripts import TranscriptStore, TranscriptTurn  # noqa: E402

configure_logging()

settings = get_settings()
app = FastAPI(title="Linger Chat API")
app.include_router(library_router)
app.include_router(auth_router)
memory_service = MemoryPolicyService(REPO_ROOT / "memories")
transcript_store = TranscriptStore(REPO_ROOT / "data" / "transcripts.sqlite3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


def get_memory_service() -> MemoryPolicyService:
    """Return the application-owned memory service."""
    return memory_service


MemoryServiceDependency = Annotated[MemoryPolicyService, Depends(get_memory_service)]

_UNKNOWN_SESSION = "This conversation is not available."
# Replies the reader actually saw; declines and boundary replies are not kept.
_TRANSCRIBED_RELEASES = {"muse_candidate", "application_clarification"}


def _claim_session(session_id: str, account_id: str) -> bool:
    """Bind a session to one account, including sessions saved before a restart."""
    if transcript_store.owner_of(session_id) not in (None, account_id):
        return False
    if not sessions.claim(session_id, account_id):
        return False
    if not sessions.history(session_id):
        saved = transcript_store.load(account_id, session_id)
        sessions.restore_history(
            session_id,
            [(turn.user_message, turn.assistant_message) for turn in saved],
        )
    return True


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": settings.linger_model}


async def _run_turn(
    request: ChatRequest,
    service: MemoryServiceDependency,
    context: AccountDependency,
) -> ChatResponse:
    """Map the HTTP request onto one application-owned chat turn."""
    if not _claim_session(request.session_id, context.account_id):
        raise HTTPException(status_code=404, detail=_UNKNOWN_SESSION)
    cancelled: asyncio.CancelledError | None = None
    failure: ChatTurnError | None = None
    response: ChatResponse | None = None
    with logfire.span(
        "chat.request",
        **{
            "http.route": "/api/chat",
            "http.request.method": "POST",
            "status": "started",
        },
    ) as span:
        try:
            response = await run_chat_turn(request, service, context)
        except asyncio.CancelledError as exc:
            cancelled = exc
            record_failure(
                span,
                stage="http_request",
                code="request_cancelled",
                retryable=False,
                failure_type="application",
            )
            set_span_attrs(
                span,
                {
                    "http.response.status_code": 499,
                    "request.outcome": "cancelled",
                },
            )
        except ChatTurnError as exc:
            failure = exc
            record_failure(
                span,
                stage="http_request",
                code="chat_turn_failed",
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
            assert response.inspection.release is not None
            release = response.inspection.release
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
                    "release.source": release.release_source,
                    "release.boundary_origin": release.boundary_origin,
                },
            )

    if cancelled is not None:
        raise cancelled
    if failure is not None:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "The model call failed. Try again.",
                "trace": failure.trace.model_dump(mode="json"),
            },
        ) from None
    assert response is not None
    return response


def _save_turn(
    request: ChatRequest,
    response: ChatResponse,
    context: AccountDependency,
    progress: list[dict[str, object]],
) -> None:
    """Keep a released turn, and what Inspect showed for it, in the reader's history."""
    release = response.inspection.release
    if release is None or release.release_source not in _TRANSCRIBED_RELEASES:
        return
    transcript_store.append_turn(
        context.account_id,
        request.session_id,
        response.inspection.muse_turn["turn_id"],
        request.message,
        response.reply,
        details={"response": response.model_dump(mode="json"), "progress": progress},
    )


@app.post(
    "/api/chat",
    response_model=ChatResponse,
    dependencies=[Depends(enforce_chat_rate_limit)],
)
async def chat(
    request: ChatRequest,
    service: MemoryServiceDependency,
    context: AccountDependency,
) -> ChatResponse:
    response = await _run_turn(request, service, context)
    _save_turn(request, response, context, progress=[])
    return response


def _sse(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _error_payload(detail: object) -> dict[str, object]:
    """Reuse the atomic endpoint's error contract, including any trace."""
    if isinstance(detail, dict):
        return {
            "detail": detail.get("message", "The request failed."),
            "trace": detail.get("trace"),
        }
    if isinstance(detail, str):
        return {"detail": detail, "trace": None}
    return {"detail": "The request failed.", "trace": None}


@app.post(
    "/api/chat/stream",
    dependencies=[Depends(enforce_chat_rate_limit)],
)
async def chat_stream(
    request: ChatRequest,
    service: MemoryServiceDependency,
    context: AccountDependency,
) -> StreamingResponse:
    """Stream content-free progress, then the same atomic ChatResponse."""

    async def events() -> AsyncIterator[str]:
        queue: asyncio.Queue[tuple[str, dict[str, object]]] = asyncio.Queue()
        stream_started = perf_counter()
        sequence = 0
        observed: list[dict[str, object]] = []

        def enqueue_progress(progress: ProgressEvent) -> None:
            nonlocal sequence
            sequence += 1
            payload: dict[str, object] = dict(asdict(progress))
            payload.update(
                {
                    "sequence": sequence,
                    "elapsed_ms": round((perf_counter() - stream_started) * 1_000),
                }
            )
            observed.append(payload)
            queue.put_nowait(("progress", payload))

        def publish(progress: ProgressEvent) -> None:
            # Synchronous tools may execute in a worker thread. Preserve event
            # ordering by handing their metadata back to this request's loop.
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None
            if current_loop is loop:
                enqueue_progress(progress)
            else:
                loop.call_soon_threadsafe(enqueue_progress, progress)

        async def run() -> None:
            token = begin_progress(publish)
            try:
                response = await _run_turn(request, service, context)
                _save_turn(request, response, context, progress=observed)
            except asyncio.CancelledError:
                raise
            except HTTPException as exc:
                queue.put_nowait(("error", _error_payload(exc.detail)))
            except Exception:
                queue.put_nowait(
                    ("error", {"detail": "The model call failed. Try again.", "trace": None})
                )
            else:
                queue.put_nowait(("result", response.model_dump(mode="json")))
            finally:
                reset_progress(token)
                queue.put_nowait(("done", {}))

        loop = asyncio.get_running_loop()
        task = asyncio.create_task(run())
        try:
            while True:
                try:
                    event, payload = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if event == "done":
                    break
                yield _sse(event, payload)
        finally:
            if not task.done():
                task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


class Conversation(BaseModel):
    session_id: str
    created_at: str
    turns: list[TranscriptTurn]


@app.get("/api/history")
def history(context: AccountDependency) -> list[Conversation]:
    """Every saved conversation of the signed-in reader, oldest first."""
    return [
        Conversation(
            session_id=summary.session_id,
            created_at=summary.created_at,
            turns=transcript_store.load(context.account_id, summary.session_id),
        )
        for summary in reversed(transcript_store.list_sessions(context.account_id))
    ]


@app.delete("/api/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, context: AccountDependency) -> None:
    """Forget a conversation: its live state and its saved transcript."""
    if sessions.owner(session_id) not in (None, context.account_id):
        raise HTTPException(status_code=404, detail=_UNKNOWN_SESSION)
    if transcript_store.owner_of(session_id) not in (None, context.account_id):
        raise HTTPException(status_code=404, detail=_UNKNOWN_SESSION)
    sessions.clear(session_id)
    transcript_store.delete(context.account_id, session_id)
