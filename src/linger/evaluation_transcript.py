"""Explicit, evaluation-only hook for recording content-bearing agent exchanges.

Production requests never bind a sink, so prompts, messages, tool payloads, and
model outputs remain outside operational telemetry. Synthetic evaluation
runners may bind one sink around a case and write the resulting transcript to
their own reviewed artifact.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Protocol, Literal
from dataclasses import dataclass


class EvaluationTranscriptSink(Protocol):
    """Receives one agent exchange without exporting it to Logfire."""

    def begin_agent_exchange(
        self,
        *,
        role: str,
        stage: str,
        input_origin: str,
        output_receiver: str,
        input_contract: str,
        output_contract: str,
        prompt_template_id: str,
        prompt_version: str,
        prompt_digest: str,
        input_prompt: str,
        message_history: Sequence[Any],
        trace_id: str,
        span_id: str,
    ) -> object:
        """Reserve the exchange's invocation-order position."""

    def complete_agent_exchange(
        self,
        handle: object,
        *,
        result: Any | None,
        status: str,
        failure_code: str | None,
    ) -> None:
        """Attach the model result or fixed failure outcome."""


_ACTIVE_SINK: ContextVar[EvaluationTranscriptSink | None] = ContextVar(
    "linger_evaluation_transcript_sink",
    default=None,
)
_ACTIVE_CORRELATION_ID: ContextVar[str | None] = ContextVar(
    "linger_evaluation_correlation_id",
    default=None,
)


def active_evaluation_transcript_sink() -> EvaluationTranscriptSink | None:
    """Return the case-scoped sink, if a synthetic runner bound one."""

    return _ACTIVE_SINK.get()


def active_evaluation_correlation_id() -> str | None:
    """Return the evaluation-only request correlation, when one is bound."""

    return _ACTIVE_CORRELATION_ID.get()


@contextmanager
def bind_evaluation_transcript_sink(
    sink: EvaluationTranscriptSink,
) -> Iterator[None]:
    """Enable content recording only for the enclosed synthetic evaluation."""

    token = _ACTIVE_SINK.set(sink)
    try:
        yield
    finally:
        _ACTIVE_SINK.reset(token)


@contextmanager
def bind_evaluation_correlation_id(correlation_id: str) -> Iterator[None]:
    """Correlate nested evaluation exchanges without changing their prompts."""

    if not correlation_id:
        raise ValueError("evaluation correlation ID must not be empty")
    token = _ACTIVE_CORRELATION_ID.set(correlation_id)
    try:
        yield
    finally:
        _ACTIVE_CORRELATION_ID.reset(token)


@dataclass(frozen=True)
class ConnectionEvaluationEvent:
    """Immutable, opt-in private observations; never application API fields."""

    kind: Literal["query", "search", "discovery", "release"]
    status: str
    operation: str | None = None
    source: str | None = None
    query: str | None = None
    evidence_json: tuple[str, ...] = ()
    decision_json: str | None = None
    release_source: str | None = None
    failure_stage: str | None = None
    failure_code: str | None = None
    provenance_verdicts: tuple[str, ...] = ()
    released_evidence_ids: tuple[str, ...] = ()


def record_connection_event(event: ConnectionEvaluationEvent) -> None:
    """Send a private observation only to an explicitly bound compatible sink."""
    sink = active_evaluation_transcript_sink()
    callback = getattr(sink, "record_connection_event", None)
    if callback is not None:
        callback(event)
