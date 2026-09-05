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

from src.linger.contracts.session import ReaderStatement
from src.linger.contracts.turn import ReleaseSource

_sessions: dict[str, list[ModelMessage]] = {}
_book_selections: dict[str, "BookSelection"] = {}
_reading_candidates: dict[str, "ReadingCandidate"] = {}
_pending_clarifications: dict[str, "PendingClarification"] = {}
_turn_records: dict[str, list["TurnRecord"]] = {}


class BookSelection(BaseModel):
    book_id: str
    book_title: str | None = None


class ReadingCandidate(BookSelection):
    """A scene-derived candidate awaiting the reader's progress confirmation."""

    chapter: int = Field(ge=1)


class PendingClarification(BookSelection):
    """A Librarian boundary question awaiting the reader's chapter answer."""

    reason_code: str


@dataclass(frozen=True)
class ReadingStateSnapshot:
    """Reading state to restore when a turn fails before release."""

    book_selection: BookSelection | None
    reading_candidate: ReadingCandidate | None
    pending_clarification: PendingClarification | None


@dataclass(frozen=True)
class TurnRecord:
    """Content-free evidence and review handles for one released turn."""

    turn_id: str
    release_source: ReleaseSource
    evidence_ids: tuple[str, ...]
    review_finding_codes: tuple[tuple[str, ...], ...]


def history(session_id: str) -> list[ModelMessage]:
    return _sessions.get(session_id, [])


def reader_statements(session_id: str) -> tuple[ReaderStatement, ...]:
    """Snapshot a bounded, contiguous suffix of original retained reader words."""
    retained = [
        part.content
        for message in history(session_id)
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart) and isinstance(part.content, str)
    ]
    selected: list[ReaderStatement] = []
    remaining_chars = 16_000
    for ordinal in range(len(retained), max(0, len(retained) - 8), -1):
        text = retained[ordinal - 1]
        if len(text) > remaining_chars:
            break
        selected.append(ReaderStatement(statement_id=f"reader-{ordinal}", text=text))
        remaining_chars -= len(text)
    return tuple(reversed(selected))


def append_turn(
    session_id: str,
    user_message: str,
    assistant_message: str,
    *,
    turn_id: str,
    release_source: ReleaseSource,
    evidence_ids: tuple[str, ...] = (),
    review_finding_codes: tuple[tuple[str, ...], ...] = (),
) -> None:
    """Store content-free evidence and review handles; store chat only if released."""
    if release_source in {"muse_candidate", "application_clarification"}:
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content=user_message)]),
            ModelResponse(parts=[TextPart(content=assistant_message)]),
        ]
        _sessions.setdefault(session_id, []).extend(messages)
    _turn_records.setdefault(session_id, []).append(
        TurnRecord(
            turn_id=turn_id,
            release_source=release_source,
            evidence_ids=tuple(dict.fromkeys(evidence_ids)),
            review_finding_codes=review_finding_codes,
        )
    )


def turn_records(session_id: str) -> tuple[TurnRecord, ...]:
    """Return content-free per-turn records for audit and evidence recovery."""
    return tuple(_turn_records.get(session_id, ()))


def released_evidence_ids(session_id: str) -> tuple[str, ...]:
    """Return exact evidence handles cited by successfully released Muse replies."""
    seen: dict[str, None] = {}
    for record in _turn_records.get(session_id, ()):
        if record.release_source != "muse_candidate":
            continue
        for evidence_id in record.evidence_ids:
            seen.setdefault(evidence_id, None)
    return tuple(seen)


def clear(session_id: str) -> bool:
    """Drop a session's messages, records, and evidence handles."""
    _book_selections.pop(session_id, None)
    _reading_candidates.pop(session_id, None)
    _pending_clarifications.pop(session_id, None)
    popped_records = _turn_records.pop(session_id, None)
    popped_history = _sessions.pop(session_id, None)
    return bool(popped_history or popped_records)


def snapshot_reading_state(session_id: str) -> ReadingStateSnapshot:
    """Capture the state that prompt assembly may tentatively change."""
    return ReadingStateSnapshot(
        book_selection=_book_selections.get(session_id),
        reading_candidate=_reading_candidates.get(session_id),
        pending_clarification=_pending_clarifications.get(session_id),
    )


def restore_reading_state(session_id: str, snapshot: ReadingStateSnapshot) -> None:
    """Roll back tentative reading state after a failed turn."""
    _book_selections.pop(session_id, None)
    _reading_candidates.pop(session_id, None)
    _pending_clarifications.pop(session_id, None)
    if snapshot.book_selection is not None:
        _book_selections[session_id] = snapshot.book_selection
    if snapshot.reading_candidate is not None:
        _reading_candidates[session_id] = snapshot.reading_candidate
    if snapshot.pending_clarification is not None:
        _pending_clarifications[session_id] = snapshot.pending_clarification


def book_selection(session_id: str) -> BookSelection | None:
    return _book_selections.get(session_id)


def set_book_selection(session_id: str, selection: BookSelection) -> None:
    pending = _pending_clarifications.get(session_id)
    if pending and pending.book_id != selection.book_id:
        _pending_clarifications.pop(session_id, None)
    _book_selections[session_id] = selection


def clear_book_selection(session_id: str) -> None:
    _book_selections.pop(session_id, None)
    _reading_candidates.pop(session_id, None)
    _pending_clarifications.pop(session_id, None)


def reading_candidate(session_id: str) -> ReadingCandidate | None:
    return _reading_candidates.get(session_id)


def set_reading_candidate(session_id: str, candidate: ReadingCandidate) -> None:
    _reading_candidates[session_id] = candidate


def clear_reading_candidate(session_id: str) -> None:
    _reading_candidates.pop(session_id, None)


def pending_clarification(session_id: str) -> PendingClarification | None:
    return _pending_clarifications.get(session_id)


def set_pending_clarification(session_id: str, pending: PendingClarification) -> None:
    _pending_clarifications[session_id] = pending


def clear_pending_clarification(session_id: str) -> None:
    _pending_clarifications.pop(session_id, None)
