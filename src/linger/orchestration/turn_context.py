"""Request-scoped turn context, readable inside tools invoked during `muse.run(...)`."""

from __future__ import annotations

import contextvars
from collections.abc import Iterable, Mapping
from types import MappingProxyType

from src.linger.contracts.librarian import EvidenceRecord
from src.linger.contracts.turn import ConfirmedReading

_confirmed_reading: contextvars.ContextVar[ConfirmedReading | None] = contextvars.ContextVar(
    "confirmed_reading", default=None
)
_reader_message: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "reader_message", default=None
)
_EMPTY_EVIDENCE: Mapping[str, EvidenceRecord] = MappingProxyType({})
_turn_evidence: contextvars.ContextVar[dict[str, EvidenceRecord] | None] = (
    contextvars.ContextVar("turn_evidence", default=None)
)


def set_confirmed_reading(value: ConfirmedReading | None) -> contextvars.Token:
    return _confirmed_reading.set(value)


def confirmed_reading() -> ConfirmedReading | None:
    return _confirmed_reading.get()


def reset_confirmed_reading(token: contextvars.Token) -> None:
    _confirmed_reading.reset(token)


def set_reader_message(value: str) -> contextvars.Token:
    """Bind the application-owned current reader message for Muse tools."""
    return _reader_message.set(value)


def reader_message() -> str | None:
    return _reader_message.get()


def reset_reader_message(token: contextvars.Token) -> None:
    _reader_message.reset(token)


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
