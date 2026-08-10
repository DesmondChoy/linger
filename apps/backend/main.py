"""FastAPI entry point for the Linger chat prototype."""

import logging
from time import perf_counter

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.linger.agents.muse.agent import muse_chat_agent
from src.linger.agents.provenance.agent import provenance_agent
from src.linger.orchestration.reflection import reflection_reply

from . import sessions
from .config import get_settings
from .logger import ROOT_NAME, configure_logging
from .schemas import ChatRequest, ChatResponse

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
