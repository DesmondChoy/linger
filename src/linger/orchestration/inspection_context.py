"""Request-local diagnostics for nested Serendipity discovery runs."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass

from src.linger.agents.serendipity.models import ConnectionExplorationResult


@dataclass(frozen=True)
class ConnectionRunInspection:
    """Serializable contracts and evidence from one nested discovery run."""

    brief: dict[str, object]
    task: dict[str, object]
    response: dict[str, object]
    searches: tuple[dict[str, object], ...]
    evidence: tuple[dict[str, object], ...]
    failure_code: str | None = None


@dataclass
class ConnectionInspectionState:
    """One turn's serializable runs and reusable typed discovery result."""

    runs: list[ConnectionRunInspection]
    result: ConnectionExplorationResult | None = None


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


def cached_connection_result() -> ConnectionExplorationResult | None:
    """Return the first discovery decision for this request, when present."""
    state = _connection_state.get()
    return state.result if state is not None else None


def cache_connection_result(result: ConnectionExplorationResult) -> None:
    """Retain exactly one typed result for repeated Muse tool calls this turn."""
    state = _connection_state.get()
    if state is not None and state.result is None:
        state.result = result


def reset_connection_inspection(
    token: Token[ConnectionInspectionState | None],
) -> None:
    """Restore the previous collector after the request finishes."""
    _connection_state.reset(token)
