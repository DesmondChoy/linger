"""In-process conversation history.

Sessions live only in this process: restarting the server clears every
conversation. 

NOTE(kay): That is deliberate for the prototype. Swapping in Redis or a
database means changing this module and nothing else.
"""

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

_sessions: dict[str, list[ModelMessage]] = {}


def history(session_id: str) -> list[ModelMessage]:
    return _sessions.get(session_id, [])


def append_turn(session_id: str, user_message: str, assistant_message: str) -> None:
    """Store exactly the user-visible turn, never an unreleased candidate."""
    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content=user_message)]),
        ModelResponse(parts=[TextPart(content=assistant_message)]),
    ]
    _sessions.setdefault(session_id, []).extend(messages)


def clear(session_id: str) -> bool:
    """Drop a session's history. Returns whether anything was there."""
    return _sessions.pop(session_id, None) is not None
