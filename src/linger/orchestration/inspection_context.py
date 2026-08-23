"""Request-local diagnostics for nested Serendipity discovery runs."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Literal

from src.linger.agents.serendipity.models import (
    ConnectionIntent,
    ConnectionExplorationResult,
    DeclineReason,
)


@dataclass(frozen=True)
class ConnectionRunInspection:
    """Content-free outcome metadata for one nested discovery run."""

    status: Literal["proposal", "decline"]
    reason: DeclineReason | None
    book_search_outcomes: tuple[str, ...]
    failure_code: str | None = None


@dataclass
class ConnectionInspectionState:
    """One turn's serializable runs and reusable typed discovery result."""

    runs: list[ConnectionRunInspection]
    cached: tuple[ConnectionIntent, ConnectionExplorationResult] | None = None


_connection_state: ContextVar[ConnectionInspectionState | None] = ContextVar(
    "connection_run_inspections",
    default=None,
)


def begin_connection_inspection() -> Token[ConnectionInspectionState | None]:
    """Start an isolated collector for the current chat request."""
    return _connection_state.set(ConnectionInspectionState(runs=[]))


def record_connection_inspection(record: ConnectionRunInspection) -> None:
    """Append a nested run only when a chat request is collecting diagnostics."""
    state = _connection_state.get()
    if state is not None:
        state.runs.append(record)


def connection_inspections() -> tuple[ConnectionRunInspection, ...]:
    """Return the nested runs recorded in the current request context."""
    state = _connection_state.get()
    return tuple(state.runs if state is not None else ())


def cached_connection_result(
) -> tuple[ConnectionIntent, ConnectionExplorationResult] | None:
    """Return the first discovery decision for this request, when present."""
    state = _connection_state.get()
    return state.cached if state is not None else None


def cache_connection_result(
    intent: ConnectionIntent,
    result: ConnectionExplorationResult,
) -> None:
    """Retain exactly one typed result for repeated Muse tool calls this turn."""
    state = _connection_state.get()
    if state is not None and state.cached is None:
        state.cached = (intent, result)


def reset_connection_inspection(
    token: Token[ConnectionInspectionState | None],
) -> None:
    """Restore the previous collector after the request finishes."""
    _connection_state.reset(token)
