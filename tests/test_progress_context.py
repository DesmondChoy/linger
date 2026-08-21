"""Safety boundary tests for user-visible progress metadata."""

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
            "Exa",
            "web_search",
            "running",
            "PRIVATE_QUERY_OR_DRAFT_CONTENT",
        )
    finally:
        reset_progress(token)

    assert events == [
        ProgressEvent(
            agent="Exa",
            stage="web_search",
            status="running",
            detail="Exa public-web search is in progress.",
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
        )
    finally:
        reset_progress(token)

    assert events == [
        ProgressEvent(
            agent="Application",
            stage="processing",
            status="complete",
            detail="Application processing completed.",
        )
    ]
