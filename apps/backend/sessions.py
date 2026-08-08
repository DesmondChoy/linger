"""In-process conversation history.

Sessions live only in this process: restarting the server clears every
conversation. 

NOTE(kay): That is deliberate for the prototype. Swapping in Redis or a
database means changing this module and nothing else.
"""

from pydantic_ai.messages import ModelMessage

_sessions: dict[str, list[ModelMessage]] = {}


def history(session_id: str) -> list[ModelMessage]:
    return _sessions.get(session_id, [])


def append(session_id: str, messages: list[ModelMessage]) -> None:
    _sessions.setdefault(session_id, []).extend(messages)


def clear(session_id: str) -> bool:
    """Drop a session's history. Returns whether anything was there."""
    return _sessions.pop(session_id, None) is not None
