"""FastAPI entry point for the Linger chat prototype."""

import json
import logging
from collections.abc import AsyncIterator
from time import perf_counter

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import sessions
from src.linger.agents.muse.agent import muse_chat_agent
from .config import get_settings
from .logger import ROOT_NAME, configure_logging
from .schemas import ChatRequest

configure_logging()
logger = logging.getLogger(f"{ROOT_NAME}.backend")

settings = get_settings()
app = FastAPI(title="Linger Chat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": settings.linger_model}


def _event(name: str, data: str) -> str:
    """Encode one SSE event. `data` is JSON so newlines survive the framing."""
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


async def _stream_reply(request: ChatRequest) -> AsyncIterator[str]:
    """Yield the reply as SSE deltas, then record the turn in the session.

    Once the first byte is sent the status code is already committed, so a
    failure mid-stream can only be reported as an `error` event and rendered
    by the client. History is appended inside the context manager, after the
    stream is exhausted, because `new_messages()` is only complete there. A
    failed run appends nothing, leaving the session as it was before.
    """
    started = perf_counter()
    try:
        async with muse_chat_agent.run_stream(
            request.message,
            message_history=sessions.history(request.session_id),
        ) as result:
            async for delta in result.stream_text(delta=True):
                yield _event("delta", delta)
            sessions.append(request.session_id, result.new_messages())
    except Exception:
        # Metadata only: message text stays out of the log (specification §8.1).
        logger.exception(
            "Agent run failed session=%s elapsed=%.2fs",
            request.session_id,
            perf_counter() - started,
        )
        yield _event("error", "The model call failed. Try again.")
    else:
        logger.info(
            "Agent run completed session=%s elapsed=%.2fs turns=%d",
            request.session_id,
            perf_counter() - started,
            len(sessions.history(request.session_id)),
        )


@app.post("/api/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream_reply(request),
        media_type="text/event-stream",
        # Stops a reverse proxy from buffering the stream into one response.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.delete("/api/sessions/{session_id}", status_code=204)
async def reset_session(session_id: str) -> None:
    sessions.clear(session_id)
