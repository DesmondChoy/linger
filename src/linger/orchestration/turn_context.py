"""Request-scoped turn context, readable inside tools invoked during `muse.run(...)`."""

from __future__ import annotations

import contextvars

from src.linger.contracts.turn import ConfirmedReading

_confirmed_reading: contextvars.ContextVar[ConfirmedReading | None] = contextvars.ContextVar(
    "confirmed_reading", default=None
)
_reader_message: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "reader_message", default=None
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
