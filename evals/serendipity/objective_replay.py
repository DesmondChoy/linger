"""Production replay and stage reporting for cross-source tentative connection."""

from __future__ import annotations

import argparse
import asyncio
import tempfile
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import Field
from pydantic_evals import Case, Dataset

from apps.backend import sessions
from apps.backend.main import chat
from apps.backend.schemas import ChatRequest, ChatResponse
from apps.backend.telemetry import configure_synthetic_evaluation_telemetry
from src.linger.agents.contracts import StrictModel
from src.linger.services.memory import (
    AccountContext,
    MemoryPolicyService,
)

from evals.synthetic_journals.replay import evaluation_agents

OBJECTIVE_ID = "cross_source_tentative_connection"
StageName = Literal[
    "invocation",
    "retrieval",
    "serendipity_selection",
    "muse_presentation",
    "provenance_review",
    "deterministic_release",
]
StageStatus = Literal["passed", "failed", "not_reached"]
STAGES: tuple[StageName, ...] = (
    "invocation",
    "retrieval",
    "serendipity_selection",
    "muse_presentation",
    "provenance_review",
    "deterministic_release",
)


class CrossSourceReplayCase(StrictModel):
    schema_version: Literal[1]
    case_id: str = Field(pattern=r"^cross-source-[a-z0-9-]+-v1$")
    objective_id: Literal["cross_source_tentative_connection"]
    messages: tuple[str, ...] = Field(min_length=1)
    expected_release_source: Literal["muse_candidate"] = "muse_candidate"
    expected_decision: Literal["proposal", "decline"] = "proposal"


class StageResult(StrictModel):
    stage: StageName
    status: StageStatus
    reason_code: str | None = None


class CrossSourceReplayReport(StrictModel):
    schema_version: Literal[1] = 1
    run_id: str
    case_id: str
    objective_id: Literal["cross_source_tentative_connection"] = OBJECTIVE_ID
    generated_at: datetime
    trace_id: str
    reply: str
    release_source: str
    stages: tuple[StageResult, ...]
    first_failure_stage: StageName | None
    objective_pass: bool


ChatHandler = Callable[[ChatRequest], Awaitable[ChatResponse]]


def _trace_status(response: ChatResponse, agent: str) -> str | None:
    for trace in response.inspection.traces:
        if trace.get("agent") == agent:
            return trace.get("status")
    return None


def grade_cross_source_response(
    case: CrossSourceReplayCase,
    response: ChatResponse,
    *,
    run_id: str,
) -> CrossSourceReplayReport:
    """Classify the first failed production stage from fixed inspection metadata."""
    release = response.inspection.release
    serendipity_status = _trace_status(response, "Serendipity")
    librarian_status = _trace_status(response, "Librarian")
    raw_checks: tuple[tuple[StageName, bool, str], ...] = (
        (
            "invocation",
            serendipity_status not in {None, "skipped"},
            "serendipity_not_invoked",
        ),
        (
            "retrieval",
            librarian_status == "complete" and serendipity_status != "failed",
            "required_retrieval_not_completed",
        ),
        (
            "serendipity_selection",
            serendipity_status == "complete"
            and (
                case.expected_decision == "proposal"
                or response.inspection.connection_decline is not None
            ),
            "serendipity_did_not_select_valid_proposal",
        ),
        (
            "muse_presentation",
            release is not None
            and release.failure_stage not in {"muse_draft", "muse_revision"},
            "muse_presentation_failed",
        ),
        (
            "provenance_review",
            release is not None
            and bool(release.provenance_verdicts)
            and release.failure_stage != "provenance_review",
            "provenance_review_failed",
        ),
        (
            "deterministic_release",
            release is not None
            and release.release_source == case.expected_release_source
            and release.failure_stage != "deterministic_validation",
            "expected_connection_not_released",
        ),
    )
    reached = True
    first_failure: StageName | None = None
    stages: list[StageResult] = []
    for stage, passed, reason in raw_checks:
        if not reached:
            stages.append(StageResult(stage=stage, status="not_reached"))
        elif passed:
            stages.append(StageResult(stage=stage, status="passed"))
        else:
            stages.append(StageResult(stage=stage, status="failed", reason_code=reason))
            first_failure = stage
            reached = False
    return CrossSourceReplayReport(
        run_id=run_id,
        case_id=case.case_id,
        generated_at=datetime.now(UTC),
        trace_id=response.trace.trace_id,
        reply=response.reply,
        release_source=release.release_source if release else "unavailable",
        stages=tuple(stages),
        first_failure_stage=first_failure,
        objective_pass=first_failure is None,
    )


async def _production_handler(
    service: MemoryPolicyService,
    account: AccountContext,
    request: ChatRequest,
) -> ChatResponse:
    try:
        return await chat(request, service, account)
    except HTTPException as error:
        raise RuntimeError("production chat failed during cross-source replay") from error


async def replay_case(
    case: CrossSourceReplayCase,
    *,
    handler: ChatHandler | None = None,
) -> CrossSourceReplayReport:
    """Replay one synthetic case through production chat or an injected handler."""
    run_id = uuid4().hex
    session_id = f"cross-source-eval:{run_id}"
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if handler is None:
        temporary = tempfile.TemporaryDirectory(prefix="linger-cross-source-")
        service = MemoryPolicyService(Path(temporary.name))
        account = AccountContext(f"cross-source-eval:{run_id}")

        async def active_handler(request: ChatRequest) -> ChatResponse:
            return await _production_handler(service, account, request)

        handler = active_handler
        configure_synthetic_evaluation_telemetry(evaluation_agents())
    response: ChatResponse | None = None
    try:
        for order, message in enumerate(case.messages, start=1):
            response = await handler(
                ChatRequest(
                    session_id=session_id,
                    turn_id=f"{case.case_id}:{order}",
                    message=message,
                )
            )
        assert response is not None
        return grade_cross_source_response(case, response, run_id=run_id)
    finally:
        sessions.clear(session_id)
        if temporary is not None:
            temporary.cleanup()


async def run_replay(
    case_path: Path,
    *,
    handler: ChatHandler | None = None,
) -> CrossSourceReplayReport:
    case = CrossSourceReplayCase.model_validate_json(case_path.read_text(encoding="utf-8"))
    observed: CrossSourceReplayReport | None = None

    async def task(_case: CrossSourceReplayCase) -> CrossSourceReplayReport:
        nonlocal observed
        observed = await replay_case(_case, handler=handler)
        return observed

    dataset = Dataset(
        name=OBJECTIVE_ID,
        cases=[
            Case(
                name=case.case_id,
                inputs=case,
                metadata={
                    "objective_id": OBJECTIVE_ID,
                    "evaluation_scope": "production_objective_replay",
                },
            )
        ],
    )
    await dataset.evaluate(
        task,
        name=f"{OBJECTIVE_ID}-{uuid4().hex[:8]}",
        task_name="cross_source_production_replay",
        max_concurrency=1,
        progress=False,
        metadata={
            "content_classification": "synthetic",
            "objective_id": OBJECTIVE_ID,
            "stage_taxonomy": list(STAGES),
        },
    )
    assert observed is not None
    return observed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser


async def _main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    report = await run_replay(args.case)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    asyncio.run(_main())
