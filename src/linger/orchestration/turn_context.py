"""Request-scoped turn context, readable inside tools invoked during `muse.run(...)`."""

from __future__ import annotations

import contextvars
from collections.abc import Iterable, Mapping
from types import MappingProxyType

from src.linger.contracts.curation import CuratedMemory
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.contracts.turn import ConfirmedReading

_confirmed_reading: contextvars.ContextVar[list[ConfirmedReading | None] | None] = (
    contextvars.ContextVar("confirmed_reading", default=None)
)
_reader_message: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "reader_message", default=None
)
_active_memories: contextvars.ContextVar[tuple[CuratedMemory, ...]] = contextvars.ContextVar(
    "active_memories", default=()
)
_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "session_id", default=None
)
_EMPTY_EVIDENCE: Mapping[str, EvidenceRecord] = MappingProxyType({})
_turn_evidence: contextvars.ContextVar[dict[str, EvidenceRecord] | None] = (
    contextvars.ContextVar("turn_evidence", default=None)
)
def set_confirmed_reading(value: ConfirmedReading | None) -> contextvars.Token:
    """Bind a fresh, single-slot cell as this turn's confirmed reading.

    A plain `ContextVar.set()` inside one tool call is only visible in that
    call's own copied context, not to a sibling tool call pydantic-ai may run
    as a separate asyncio Task. Binding a mutable one-item list here, and
    mutating its slot in place from `bind_confirmed_reading`, makes a
    mid-turn update visible everywhere the same cell reference is held.
    """
    return _confirmed_reading.set([value])


def confirmed_reading() -> ConfirmedReading | None:
    cell = _confirmed_reading.get()
    return cell[0] if cell is not None else None


def bind_confirmed_reading(value: ConfirmedReading) -> None:
    """Mutate the current turn's confirmed-reading cell in place.

    Used by application-side tool orchestration (never Muse's text) to grant
    the same authority `_infer_request_boundary` used to grant, mid-turn. A
    no-op outside an active turn (no cell bound yet).
    """
    cell = _confirmed_reading.get()
    if cell is not None:
        cell[0] = value


def reset_confirmed_reading(token: contextvars.Token) -> None:
    _confirmed_reading.reset(token)


def set_reader_message(value: str) -> contextvars.Token:
    """Bind the application-owned current reader message for Muse tools."""
    return _reader_message.set(value)


def reader_message() -> str | None:
    return _reader_message.get()


def reset_reader_message(token: contextvars.Token) -> None:
    _reader_message.reset(token)


def set_active_memories(value: tuple[CuratedMemory, ...]) -> contextvars.Token:
    """Bind the curated account-scoped retrieval view for this turn's tools."""
    return _active_memories.set(value)


def active_memories() -> tuple[CuratedMemory, ...]:
    return _active_memories.get()


def reset_active_memories(token: contextvars.Token) -> None:
    _active_memories.reset(token)


def set_session_id(value: str) -> contextvars.Token:
    """Bind the application-owned session ID so a routing tool can persist state."""
    return _session_id.set(value)


def session_id() -> str | None:
    return _session_id.get()


def reset_session_id(token: contextvars.Token) -> None:
    _session_id.reset(token)


def _evidence_index(records: Iterable[EvidenceRecord]) -> Mapping[str, EvidenceRecord]:
    evidence: dict[str, EvidenceRecord] = {}
    for record in records:
        existing = evidence.get(record.evidence_id)
        if existing is not None and existing != record:
            raise ValueError("a turn evidence ID resolved to conflicting records")
        evidence[record.evidence_id] = record
    return MappingProxyType(evidence)


def set_turn_evidence(
    records: Iterable[EvidenceRecord],
) -> contextvars.Token[dict[str, EvidenceRecord] | None]:
    """Start one isolated evidence ledger for the current turn."""
    return _turn_evidence.set(dict(_evidence_index(records)))


def turn_evidence() -> Mapping[str, EvidenceRecord]:
    """Return the current turn's read-only canonical evidence index."""
    current = _turn_evidence.get()
    return MappingProxyType(dict(current)) if current is not None else _EMPTY_EVIDENCE


def add_turn_evidence(records: Iterable[EvidenceRecord]) -> None:
    """Add frozen records to the request ledger shared with nested tool tasks."""
    current = _turn_evidence.get()
    if current is None:
        return
    incoming = _evidence_index(records)
    for evidence_id, record in incoming.items():
        existing = current.get(evidence_id)
        if existing is not None and existing != record:
            raise ValueError("a turn evidence ID resolved to conflicting records")
    current.update(incoming)


def reset_turn_evidence(
    token: contextvars.Token[dict[str, EvidenceRecord] | None],
) -> None:
    """Restore the previous evidence index after the request finishes."""
    _turn_evidence.reset(token)
