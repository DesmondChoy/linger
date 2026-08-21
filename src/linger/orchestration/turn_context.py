"""Request-scoped turn context, readable inside tools invoked during `muse.run(...)`."""

from __future__ import annotations

import contextvars

from src.linger.contracts.turn import ConfirmedReading

_confirmed_reading: contextvars.ContextVar[ConfirmedReading | None] = contextvars.ContextVar(
    "confirmed_reading", default=None
)
_synthetic_reader_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "synthetic_reader_id", default=None
)


def set_confirmed_reading(value: ConfirmedReading) -> contextvars.Token:
    return _confirmed_reading.set(value)


def confirmed_reading() -> ConfirmedReading | None:
    return _confirmed_reading.get()


def reset_confirmed_reading(token: contextvars.Token) -> None:
    _confirmed_reading.reset(token)


def set_synthetic_reader_id(value: str | None) -> contextvars.Token:
    """Expose one server-validated demo profile during a request only."""
    return _synthetic_reader_id.set(value)


def synthetic_reader_id() -> str | None:
    return _synthetic_reader_id.get()


def reset_synthetic_reader_id(token: contextvars.Token) -> None:
    _synthetic_reader_id.reset(token)
