"""Safety boundary tests for user-visible progress metadata."""

import asyncio
from types import SimpleNamespace

import pytest

from apps.backend.telemetry import run_agent_traced

from src.linger.orchestration.progress_context import (
    ProgressEvent,
    begin_progress,
    emit_progress,
    reset_progress,
)


def test_progress_discards_caller_prose() -> None:
    events: list[ProgressEvent] = []
    token = begin_progress(events.append)
    try:
        emit_progress(
            "Serendipity",
            "web_search",
            "running",
            "PRIVATE_QUERY_OR_DRAFT_CONTENT",
            input_origin="Serendipity",
            output_receiver="Exa",
        )
    finally:
        reset_progress(token)

    assert events == [
        ProgressEvent(
            agent="Serendipity",
            stage="web_search",
            status="running",
            detail="Public-web search is in progress.",
            input_origin="Serendipity",
            output_receiver="Exa",
        )
    ]


def test_progress_collapses_unknown_metadata_to_generic_values() -> None:
    events: list[ProgressEvent] = []
    token = begin_progress(events.append)
    try:
        emit_progress(
            "PRIVATE_AGENT_VALUE",
            "PRIVATE_STAGE_VALUE",
            "complete",
            "PRIVATE_DETAIL_VALUE",
            input_origin="PRIVATE_ORIGIN_VALUE",
            output_receiver="PRIVATE_RECEIVER_VALUE",
        )
    finally:
        reset_progress(token)

    assert events == [
        ProgressEvent(
            agent="Application",
            stage="processing",
            status="complete",
            detail="Application processing completed.",
            input_origin="Application",
            output_receiver="Application",
        )
    ]


def test_progress_outside_a_request_context_is_discarded() -> None:
    # No emitter is installed, so instrumentation must be a no-op rather than
    # raising or leaking into an unrelated request's stream.
    emit_progress("Muse", "draft", "running", "detail")


def test_emitter_is_restored_after_a_request_completes() -> None:
    outer: list[ProgressEvent] = []
    inner: list[ProgressEvent] = []

    outer_token = begin_progress(outer.append)
    inner_token = begin_progress(inner.append)
    emit_progress("Muse", "draft", "running", "detail")
    reset_progress(inner_token)
    emit_progress("Provenance", "review", "complete", "detail")
    reset_progress(outer_token)

    assert [event.agent for event in inner] == ["Muse"]
    assert [event.agent for event in outer] == ["Provenance"]


class _StubAgent:
    """Minimal stand-in for a Pydantic AI agent run."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def run(self, prompt: str, **kwargs: object) -> object:
        if self.error is not None:
            raise self.error
        return SimpleNamespace(output="result", usage=lambda: None)


TRACED_KWARGS = {
    "span_name": "agent.muse",
    "role": "Muse",
    "stage": "draft",
    "input_contract": "MuseDraftInput",
    "output_contract": "MuseCandidate",
    "prompt_template_id": "muse",
    "prompt_digest": "digest",
    "failure_code": "muse_draft_failed",
}


def test_a_traced_agent_run_brackets_its_stage_with_progress() -> None:
    events: list[ProgressEvent] = []
    token = begin_progress(events.append)
    try:
        asyncio.run(
            run_agent_traced(_StubAgent(), "PRIVATE_PROMPT", **TRACED_KWARGS)
        )
    finally:
        reset_progress(token)

    assert [(event.agent, event.stage, event.status) for event in events] == [
        ("Muse", "draft", "running"),
        ("Muse", "draft", "complete"),
    ]
    assert all("PRIVATE_PROMPT" not in event.detail for event in events)


def test_a_failed_traced_agent_run_reports_a_failed_stage() -> None:
    events: list[ProgressEvent] = []
    token = begin_progress(events.append)
    try:
        with pytest.raises(RuntimeError):
            asyncio.run(
                run_agent_traced(
                    _StubAgent(RuntimeError("PRIVATE_PROVIDER_FAILURE")),
                    "PRIVATE_PROMPT",
                    **TRACED_KWARGS,
                )
            )
    finally:
        reset_progress(token)

    assert [event.status for event in events] == ["running", "failed"]
    assert all("PRIVATE_PROVIDER_FAILURE" not in event.detail for event in events)
