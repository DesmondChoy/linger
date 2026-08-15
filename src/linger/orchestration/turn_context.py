"""Request-scoped turn context, readable inside tools invoked during `muse.run(...)`."""

from __future__ import annotations

import contextvars

from src.linger.contracts.turn import ConfirmedReading

_confirmed_reading: contextvars.ContextVar[ConfirmedReading | None] = contextvars.ContextVar(
    "confirmed_reading", default=None
)


def set_confirmed_reading(value: ConfirmedReading) -> contextvars.Token:
    return _confirmed_reading.set(value)


def confirmed_reading() -> ConfirmedReading | None:
    return _confirmed_reading.get()


def reset_confirmed_reading(token: contextvars.Token) -> None:
    _confirmed_reading.reset(token)
