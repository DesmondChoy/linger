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
from typing import Any, Protocol


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


def active_evaluation_transcript_sink() -> EvaluationTranscriptSink | None:
    """Return the case-scoped sink, if a synthetic runner bound one."""

    return _ACTIVE_SINK.get()


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
