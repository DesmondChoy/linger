"""FastAPI entry point for the Linger chat prototype."""

import json
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import sessions
from src.linger.agents.muse.agent import muse_chat_agent
from .config import get_settings
from .schemas import ChatRequest

logger = logging.getLogger(__name__)

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
    try:
        async with muse_chat_agent.run_stream(
            request.message,
            message_history=sessions.history(request.session_id),
        ) as result:
            async for delta in result.stream_text(delta=True):
                yield _event("delta", delta)
            sessions.append(request.session_id, result.new_messages())
    except Exception:
        logger.exception("Agent run failed")
        yield _event("error", "The model call failed. Try again.")


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
