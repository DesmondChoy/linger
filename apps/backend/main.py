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

# Configure the exporter before application-owned spans can be created.
from .telemetry import configure_telemetry, record_failure, set_span_attrs

configure_telemetry()

import logfire  # noqa: E402  (import order is load-bearing, see above)

from src.linger.services.memory import (  # noqa: E402
    AccountContext,
    MemoryPolicyService,
)

from . import sessions  # noqa: E402
from .chat_turn import ChatTurnError, run_chat_turn  # noqa: E402
from .config import REPO_ROOT, get_settings  # noqa: E402
from .logger import configure_logging  # noqa: E402
from src.linger.orchestration.progress_context import (  # noqa: E402
    ProgressEvent,
    begin_progress,
    reset_progress,
)
from .library import router as library_router  # noqa: E402
from .schemas import ChatRequest, ChatResponse  # noqa: E402

configure_logging()

settings = get_settings()
app = FastAPI(title="Linger Chat API")
app.include_router(library_router)
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


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": settings.linger_model}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    service: MemoryServiceDependency,
    context: MemoryContextDependency,
) -> ChatResponse:
    """Map the HTTP request onto one application-owned chat turn."""
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


@app.post("/api/chat/stream")
async def chat_stream(
    request: ChatRequest,
    service: MemoryServiceDependency,
    context: MemoryContextDependency,
) -> StreamingResponse:
    """Stream content-free progress, then the same atomic ChatResponse."""

    async def events() -> AsyncIterator[str]:
        queue: asyncio.Queue[tuple[str, dict[str, object]]] = asyncio.Queue()
        stream_started = perf_counter()
        sequence = 0

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
                response = await chat(request, service, context)
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


@app.delete("/api/sessions/{session_id}", status_code=204)
async def reset_session(session_id: str) -> None:
    sessions.clear(session_id)
