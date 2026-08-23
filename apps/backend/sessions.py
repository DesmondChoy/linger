"""In-process conversation history.

Sessions live only in this process: restarting the server clears every
conversation. 

NOTE(kay): That is deliberate for the prototype. Swapping in Redis or a
database means changing this module and nothing else.
"""

from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

_sessions: dict[str, list[ModelMessage]] = {}
_book_selections: dict[str, "BookSelection"] = {}
_reading_candidates: dict[str, "ReadingCandidate"] = {}


class BookSelection(BaseModel):
    book_id: str
    book_title: str | None = None


class ReadingCandidate(BookSelection):
    """A scene-derived candidate awaiting the reader's progress confirmation."""

    chapter: int = Field(ge=1)


@dataclass(frozen=True)
class ReadingStateSnapshot:
    """Reading state to restore when a turn fails before release."""

    book_selection: BookSelection | None
    reading_candidate: ReadingCandidate | None


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
    _book_selections.pop(session_id, None)
    _reading_candidates.pop(session_id, None)
    return _sessions.pop(session_id, None) is not None


def snapshot_reading_state(session_id: str) -> ReadingStateSnapshot:
    """Capture the state that prompt assembly may tentatively change."""
    return ReadingStateSnapshot(
        book_selection=_book_selections.get(session_id),
        reading_candidate=_reading_candidates.get(session_id),
    )


def restore_reading_state(session_id: str, snapshot: ReadingStateSnapshot) -> None:
    """Roll back tentative reading state after a failed turn."""
    _book_selections.pop(session_id, None)
    _reading_candidates.pop(session_id, None)
    if snapshot.book_selection is not None:
        _book_selections[session_id] = snapshot.book_selection
    if snapshot.reading_candidate is not None:
        _reading_candidates[session_id] = snapshot.reading_candidate


def book_selection(session_id: str) -> BookSelection | None:
    return _book_selections.get(session_id)


def set_book_selection(session_id: str, selection: BookSelection) -> None:
    _book_selections[session_id] = selection


def reading_candidate(session_id: str) -> ReadingCandidate | None:
    return _reading_candidates.get(session_id)


def set_reading_candidate(session_id: str, candidate: ReadingCandidate) -> None:
    _reading_candidates[session_id] = candidate


def clear_reading_candidate(session_id: str) -> None:
    _reading_candidates.pop(session_id, None)
