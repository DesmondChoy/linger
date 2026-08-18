"""Replay frozen journal datasets through Linger's production chat boundary."""

from __future__ import annotations

import argparse
import asyncio
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal

from apps.backend import sessions
from apps.backend.schemas import CaptureInspection, ChatRequest, ChatResponse
from src.linger.services.memory import (
    AccountContext,
    MemoryPolicyService,
    MemoryServiceError,
)

from .contracts import (
    CorrectMemoryEvent,
    DeleteMemoryEvent,
    EntryAnnotation,
    ExplicitSaveEvent,
    JournalEntry,
    JournalNoteEvent,
    ReplayEvent,
    StrictModel,
    SyntheticJournalDataset,
    load_dataset,
)

ChatHandler = Callable[
    [ChatRequest, MemoryPolicyService, AccountContext],
    Awaitable[ChatResponse],
]


class ReplayEventResult(StrictModel):
    event_id: str
    kind: Literal["journal_note", "explicit_save", "correct_memory", "delete_memory"]
    entry_id: str | None
    reply: str | None
    capture: CaptureInspection | None
    memory_id: str | None
    hard_pass: bool
    failures: tuple[str, ...]


class ReplayReport(StrictModel):
    schema_version: Literal[1]
    dataset_id: str
    persona_id: str
    event_results: tuple[ReplayEventResult, ...]
    hard_pass: bool
    failures: tuple[str, ...]
    final_active_memory_ids: tuple[str, ...]


async def replay_dataset(
    dataset: SyntheticJournalDataset,
    *,
    chat_handler: ChatHandler | None = None,
    memory_service: MemoryPolicyService | None = None,
) -> ReplayReport:
    """Replay one frozen dataset; annotations remain grader-only throughout."""
    if dataset.manifest.approval.status != "frozen":
        raise ValueError("evaluation replay requires a frozen, human-reviewed dataset")

    temporary: tempfile.TemporaryDirectory[str] | None = None
    if memory_service is None:
        temporary = tempfile.TemporaryDirectory(prefix="linger-synthetic-memory-")
        memory_service = MemoryPolicyService(Path(temporary.name))
    handler = chat_handler or _production_chat
    account = AccountContext(f"synthetic-eval:{dataset.manifest.dataset_id}")
    memory_service.set_capture_enabled(account, dataset.manifest.replay.capture_enabled)

    entries = {entry.entry_id: entry for entry in dataset.journal_entries.entries}
    annotations = {item.entry_id: item for item in dataset.annotations.entries}
    memory_by_event: dict[str, str] = {}
    results: list[ReplayEventResult] = []
    try:
        for event in dataset.manifest.replay.events:
            result = await _replay_event(
                event,
                dataset=dataset,
                entries=entries,
                annotations=annotations,
                memory_by_event=memory_by_event,
                handler=handler,
                service=memory_service,
                account=account,
            )
            results.append(result)
            if result.memory_id is not None:
                memory_by_event[event.event_id] = result.memory_id
        failures = tuple(
            f"{result.event_id}:{failure}"
            for result in results
            for failure in result.failures
        )
        active_ids = tuple(
            record.memory_id for record in memory_service.list_active(account)
        )
        return ReplayReport(
            schema_version=1,
            dataset_id=dataset.manifest.dataset_id,
            persona_id=dataset.manifest.persona_id,
            event_results=tuple(results),
            hard_pass=not failures,
            failures=failures,
            final_active_memory_ids=active_ids,
        )
    finally:
        if temporary is not None:
            temporary.cleanup()


async def _replay_event(
    event: ReplayEvent,
    *,
    dataset: SyntheticJournalDataset,
    entries: dict[str, JournalEntry],
    annotations: dict[str, EntryAnnotation],
    memory_by_event: dict[str, str],
    handler: ChatHandler,
    service: MemoryPolicyService,
    account: AccountContext,
) -> ReplayEventResult:
    if isinstance(event, JournalNoteEvent):
        entry = entries[event.entry_id]
        session_id = f"{dataset.manifest.dataset_id}:{event.event_id}"
        request = ChatRequest(
            session_id=session_id,
            turn_id=event.event_id,
            message=entry.text,
        )
        try:
            response = await handler(request, service, account)
        finally:
            sessions.clear(session_id)
        if response.inspection.release is None:
            raise ValueError("production chat returned no release inspection")
        capture = response.inspection.release.capture
        stored_text = None
        if response.memory_capture is not None:
            stored_text = service.get_active(
                account,
                response.memory_capture.memory_id,
            ).text
        failures = _grade_capture(
            annotations[event.entry_id],
            capture,
            stored_text=stored_text,
        )
        return ReplayEventResult(
            event_id=event.event_id,
            kind=event.kind,
            entry_id=event.entry_id,
            reply=response.reply,
            capture=capture,
            memory_id=(
                response.memory_capture.memory_id
                if response.memory_capture is not None
                else None
            ),
            hard_pass=not failures,
            failures=failures,
        )

    if isinstance(event, ExplicitSaveEvent):
        entry = entries[event.entry_id]
        text = entry.text[event.span.start_codepoint : event.span.end_codepoint]
        try:
            result = service.save_explicit(
                account,
                text=text,
                source_event_id=event.event_id,
            )
        except MemoryServiceError as error:
            return _control_result(event, failure=type(error).__name__)
        return _control_result(event, memory_id=result.record.memory_id)

    target_id = memory_by_event.get(event.target_event_id)
    if target_id is None:
        return _control_result(event, failure="target_memory_not_created")

    if isinstance(event, CorrectMemoryEvent):
        entry = entries[event.entry_id]
        text = entry.text[event.span.start_codepoint : event.span.end_codepoint]
        try:
            result = service.correct(
                account,
                target_id,
                text=text,
                source_event_id=event.event_id,
            )
        except MemoryServiceError as error:
            return _control_result(event, failure=type(error).__name__)
        return _control_result(event, memory_id=result.record.memory_id)

    assert isinstance(event, DeleteMemoryEvent)
    try:
        service.delete(account, target_id)
    except MemoryServiceError as error:
        return _control_result(event, failure=type(error).__name__)
    return _control_result(event)


def _control_result(
    event: ReplayEvent,
    *,
    memory_id: str | None = None,
    failure: str | None = None,
) -> ReplayEventResult:
    return ReplayEventResult(
        event_id=event.event_id,
        kind=event.kind,
        entry_id=getattr(event, "entry_id", None),
        reply=None,
        capture=None,
        memory_id=memory_id,
        hard_pass=failure is None,
        failures=(failure,) if failure else (),
    )


def _grade_capture(
    annotation: EntryAnnotation,
    observed: CaptureInspection,
    *,
    stored_text: str | None,
) -> tuple[str, ...]:
    expected = annotation.hard_expectations
    failures: list[str] = []
    nomination = expected.muse_nomination.outcome
    if nomination != "ambiguous" and observed.nomination != nomination:
        failures.append(
            f"muse_nomination:expected={nomination}:observed={observed.nomination}"
        )
    provenance = expected.provenance_capture.outcome
    if provenance != "ambiguous" and observed.provenance_decision != provenance:
        failures.append(
            "provenance_capture:"
            f"expected={provenance}:observed={observed.provenance_decision}"
        )
    storage = expected.memory_policy.outcome
    storage_map = {
        "commit": "committed",
        "refuse": "refused",
        "not_applicable": "not_applicable",
    }
    if storage != "ambiguous" and observed.storage != storage_map[storage]:
        failures.append(
            f"memory_policy:expected={storage_map[storage]}:observed={observed.storage}"
        )
    expected_reason = expected.memory_policy.reason_code
    if expected_reason is not None and observed.reason_code != expected_reason:
        failures.append(
            f"memory_reason:expected={expected_reason}:observed={observed.reason_code}"
        )
    if storage == "commit":
        allowed_texts = {
            span.text for span in expected.muse_nomination.candidate_spans
        }
        if stored_text not in allowed_texts:
            failures.append("stored_text:not_an_approved_exact_candidate_span")
    return tuple(failures)


async def _production_chat(
    request: ChatRequest,
    service: MemoryPolicyService,
    account: AccountContext,
) -> ChatResponse:
    from apps.backend.main import chat

    return await chat(request, service, account)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    dataset = load_dataset(args.dataset)
    report = asyncio.run(replay_dataset(dataset))
    rendered = report.model_dump_json(indent=2)
    if args.output is None:
        print(rendered)
    else:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    raise SystemExit(0 if report.hard_pass else 1)


if __name__ == "__main__":
    main()
