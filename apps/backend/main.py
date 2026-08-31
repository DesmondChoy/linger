"""FastAPI transport adapter for the Linger chat application."""

import asyncio
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

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
from .schemas import ChatRequest, ChatResponse  # noqa: E402

configure_logging()

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


@app.delete("/api/sessions/{session_id}", status_code=204)
async def reset_session(session_id: str) -> None:
    sessions.clear(session_id)
