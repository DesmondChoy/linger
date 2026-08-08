"""FastAPI entry point for the Linger chat prototype."""

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import sessions
from src.linger.agents.muse.agent import muse_chat_agent
from .config import get_settings
from .schemas import ChatRequest, ChatResponse

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


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        result = await muse_chat_agent.run(
            request.message,
            message_history=sessions.history(request.session_id),
        )
    except Exception:
        logger.exception("Agent run failed")
        raise HTTPException(status_code=502, detail="The model call failed. Try again.")

    sessions.append(request.session_id, result.new_messages())
    return ChatResponse(reply=result.output)


@app.delete("/api/sessions/{session_id}", status_code=204)
async def reset_session(session_id: str) -> None:
    sessions.clear(session_id)
