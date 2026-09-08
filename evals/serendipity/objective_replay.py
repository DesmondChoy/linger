"""Production replay and stage reporting for cross-source tentative connection."""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, NamedTuple
from uuid import uuid4

from fastapi import HTTPException
from pydantic import Field
from pydantic_evals import Case, Dataset

from apps.backend import sessions
from apps.backend.main import chat
from apps.backend.schemas import ChatRequest, ChatResponse
from apps.backend.telemetry import configure_synthetic_evaluation_telemetry
from src.linger.agents.contracts import StrictModel
from src.linger.orchestration.query_observation import (
    begin_web_query_observation,
    reset_web_query_observation,
    web_query_observations,
)
from src.linger.services.memory import (
    AccountContext,
    AutomaticMemoryCandidate,
    MemoryPolicyService,
)

from evals.synthetic_journals.replay import evaluation_agents
from evals.synthetic_journals.adoption import (
    GroundTruthAdoptionError,
    validate_ground_truth_adoption_files,
)
from evals.synthetic_journals.models import (
    GroundTruthAdoption,
    Prop,
    ProposedGroundTruth,
    SyntheticBackstory,
)
from evals.synthetic_journals.validate_package import (
    PackageValidationError,
    validate_package_files,
)

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
    # Exact private wording an adopted package forbids in an outbound query.
    # The runtime never receives it; only the grader compares it.
    forbidden_query_texts: tuple[str, ...] = ()


class StageResult(StrictModel):
    stage: StageName
    status: StageStatus
    reason_code: str | None = None


class ObservedWebQuery(StrictModel):
    """One public-web query this replay saw Serendipity attempt."""

    query: str
    verdict: Literal["issued", "blocked"]


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
    web_queries: tuple[ObservedWebQuery, ...] = ()


ChatHandler = Callable[[ChatRequest], Awaitable[ChatResponse]]
PackageChatHandler = Callable[
    [ChatRequest, MemoryPolicyService, AccountContext], Awaitable[ChatResponse]
]


class SemanticReviewItems(StrictModel):
    """Adopted expectations no deterministic check can settle.

    Tentative framing and the realism of a public claim are review judgments,
    so the replay carries them into its report instead of scoring them. A
    semantic judgment never overrides a failed hard gate.
    """

    require_tentative: bool
    public_claims: tuple[str, ...] = ()


class CrossSourceSceneReport(StrictModel):
    scene_id: str
    line_id: str
    seeded_prop_ids: tuple[str, ...]
    replay: CrossSourceReplayReport
    semantic_review: SemanticReviewItems
    ground_truth_result: Literal[
        "matches_proposal",
        "differs_from_proposal",
        "passes_hard_gates",
        "fails_hard_gates",
    ]


class CrossSourcePackageReport(StrictModel):
    schema_version: Literal[1] = 1
    run_id: str
    objective_id: Literal["cross_source_tentative_connection"] = OBJECTIVE_ID
    generated_at: datetime
    ground_truth_status: Literal["proposed", "adopted"]
    dataset_version: str
    scenes: tuple[CrossSourceSceneReport, ...]


class _SceneCase(NamedTuple):
    """One Scene's replay input, setup data, and review-only expectations."""

    case: CrossSourceReplayCase
    prop_ids: tuple[str, ...]
    semantic_review: SemanticReviewItems


def _package_cases(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
) -> tuple[_SceneCase, ...]:
    """Project validated cross-source Scenes into replay inputs.

    The returned Prop IDs are setup data for the replay shell. Only the Line
    crosses the production chat boundary; the forbidden wording and review
    items stay with the grader and the report.
    """

    if backstory.objective_ids != (OBJECTIVE_ID,):
        raise ValueError("cross-source replay requires only its selected Objective")
    if backstory.run_configuration_ids:
        raise ValueError("cross-source replay accepts no run configuration")
    proposals = {
        proposal.scene_id: proposal
        for proposal in ground_truth.proposals
        if proposal.objective_id == OBJECTIVE_ID
    }
    lines = {line.line_id: line for line in backstory.lines}
    cases = []
    for scene in sorted(backstory.scenes, key=lambda item: item.order):
        proposal = proposals.get(scene.scene_id)
        if proposal is None or proposal.connection is None:
            raise ValueError(f"Scene {scene.scene_id} lacks typed connection Ground truth")
        if len(scene.line_ids) != 1:
            raise ValueError(f"Scene {scene.scene_id} requires exactly one Line")
        line = lines[scene.line_ids[0]]
        expectation = proposal.connection
        cases.append(
            _SceneCase(
                case=CrossSourceReplayCase(
                    schema_version=1,
                    case_id=f"cross-source-{scene.scene_id}-v1",
                    objective_id=OBJECTIVE_ID,
                    messages=(line.text,),
                    expected_decision=expectation.expected_decision,
                    forbidden_query_texts=tuple(
                        dict.fromkeys(
                            span.text
                            for span in expectation.forbidden_web_query_spans
                        )
                    ),
                ),
                prop_ids=scene.prop_ids,
                semantic_review=SemanticReviewItems(
                    require_tentative=expectation.require_tentative,
                    public_claims=tuple(
                        claim.claim for claim in expectation.public_claims
                    ),
                ),
            )
        )
    return tuple(cases)


def _trace_status(response: ChatResponse, agent: str) -> str | None:
    for trace in response.inspection.traces:
        if trace.get("agent") == agent:
            return trace.get("status")
    return None


def _leaked_private_wording(
    case: CrossSourceReplayCase,
    web_queries: Sequence[ObservedWebQuery],
) -> bool:
    """Detect adopted private wording in a query that actually left the system.

    A blocked query is the runtime privacy gate working, not a leak, so only
    issued queries count.
    """

    issued = [
        observed.query.casefold()
        for observed in web_queries
        if observed.verdict == "issued"
    ]
    return any(
        forbidden.casefold() in query
        for forbidden in case.forbidden_query_texts
        for query in issued
    )


def grade_cross_source_response(
    case: CrossSourceReplayCase,
    response: ChatResponse,
    *,
    run_id: str,
    web_queries: Sequence[ObservedWebQuery] = (),
) -> CrossSourceReplayReport:
    """Classify the first failed production stage from fixed inspection metadata."""
    release = response.inspection.release
    serendipity_status = _trace_status(response, "Serendipity")
    librarian_status = _trace_status(response, "Librarian")
    leaked = _leaked_private_wording(case, web_queries)
    retrieval_reason = (
        "private_wording_in_public_query"
        if leaked
        else "required_retrieval_not_completed"
    )
    raw_checks: tuple[tuple[StageName, bool, str], ...] = (
        (
            "invocation",
            serendipity_status not in {None, "skipped"},
            "serendipity_not_invoked",
        ),
        (
            "retrieval",
            librarian_status == "complete"
            and serendipity_status != "failed"
            and not leaked,
            retrieval_reason,
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
        web_queries=tuple(web_queries),
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


def _seed_scene_props(
    props: tuple[Prop, ...],
    *,
    run_id: str,
    scene_id: str,
    service: MemoryPolicyService,
    account: AccountContext,
) -> tuple[str, ...]:
    service.set_capture_enabled(account, True)
    try:
        seeded = []
        for prop in props:
            result = service.save_automatic(
                account,
                AutomaticMemoryCandidate(
                    text=prop.source_text,
                    source_event_id=(
                        f"synthetic-cross-source:{run_id}:{scene_id}:{prop.prop_id}"
                    ),
                    review_allows_capture=True,
                    contains_sensitive_content=False,
                ),
            )
            if not result.created:
                raise RuntimeError(f"Prop {prop.prop_id} was not freshly seeded")
            seeded.append(prop.prop_id)
        return tuple(seeded)
    finally:
        service.set_capture_enabled(account, False)


async def replay_cross_source_scenes(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    *,
    adoption: GroundTruthAdoption | None = None,
    chat_handler: PackageChatHandler | None = None,
) -> CrossSourcePackageReport:
    """Replay a reviewed cross-source package through isolated production chat."""

    cases = _package_cases(backstory, ground_truth)
    run_id = uuid4().hex
    account = AccountContext(
        f"synthetic-cross-source:{backstory.backstory.evaluation_account_id}:{run_id}"
    )
    ground_truth_status: Literal["proposed", "adopted"] = (
        adoption.ground_truth_status if adoption is not None else ground_truth.ground_truth_status
    )
    dataset_version = (
        adoption.adopted_ground_truth_identity
        if adoption is not None
        else ground_truth.backstory_sha256
    )
    if chat_handler is None:
        configure_synthetic_evaluation_telemetry(evaluation_agents())

        async def handler(
            request: ChatRequest,
            service: MemoryPolicyService,
            active_account: AccountContext,
        ) -> ChatResponse:
            return await _production_handler(service, active_account, request)
    else:
        handler = chat_handler

    props = {prop.prop_id: prop for prop in backstory.props}
    scene_by_case_id = {
        f"cross-source-{scene.scene_id}-v1": scene
        for scene in backstory.scenes
    }
    reports = []
    for case, prop_ids, semantic_review in cases:
        scene = scene_by_case_id[case.case_id]
        with tempfile.TemporaryDirectory(prefix="linger-cross-source-") as directory:
            service = MemoryPolicyService(Path(directory))
            scene_props = tuple(props[prop_id] for prop_id in prop_ids)
            seeded_prop_ids = _seed_scene_props(
                scene_props,
                run_id=run_id,
                scene_id=scene.scene_id,
                service=service,
                account=account,
            )
            response: ChatResponse | None = None
            session_id = f"synthetic-cross-source:{run_id}:{scene.scene_id}"
            observation_token = begin_web_query_observation()
            try:
                for order, message in enumerate(case.messages, start=1):
                    response = await handler(
                        ChatRequest(
                            session_id=session_id,
                            turn_id=f"{case.case_id}:{order}",
                            message=message,
                        ),
                        service,
                        account,
                    )
                if response is None:  # pragma: no cover - case model invariant
                    raise RuntimeError(f"Scene {scene.scene_id} has no Line")
                replay = grade_cross_source_response(
                    case,
                    response,
                    run_id=run_id,
                    web_queries=tuple(
                        ObservedWebQuery(query=observed.query, verdict=observed.verdict)
                        for observed in web_query_observations()
                    ),
                )
            finally:
                reset_web_query_observation(observation_token)
                sessions.clear(session_id)
            matches = replay.objective_pass
            ground_truth_result = (
                "passes_hard_gates"
                if ground_truth_status == "adopted" and matches
                else "fails_hard_gates"
                if ground_truth_status == "adopted"
                else "matches_proposal"
                if matches
                else "differs_from_proposal"
            )
            reports.append(
                CrossSourceSceneReport(
                    scene_id=scene.scene_id,
                    line_id=scene.line_ids[0],
                    seeded_prop_ids=seeded_prop_ids,
                    replay=replay,
                    semantic_review=semantic_review,
                    ground_truth_result=ground_truth_result,
                )
            )
    return CrossSourcePackageReport(
        run_id=run_id,
        generated_at=datetime.now(UTC),
        ground_truth_status=ground_truth_status,
        dataset_version=dataset_version,
        scenes=tuple(reports),
    )


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
    parser.add_argument("backstory", type=Path)
    parser.add_argument("ground_truth", type=Path)
    parser.add_argument("--adoption", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.adoption is None:
            backstory, ground_truth = validate_package_files(
                args.backstory, args.ground_truth
            )
            adoption = None
        else:
            backstory, ground_truth, adoption = validate_ground_truth_adoption_files(
                args.backstory,
                args.ground_truth,
                args.adoption,
            )
        report = asyncio.run(
            replay_cross_source_scenes(
                backstory,
                ground_truth,
                adoption=adoption,
            )
        )
        rendered = report.model_dump_json(indent=2) + "\n"
        if args.output is None:
            print(rendered, end="")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            print(args.output)
    except (
        OSError,
        GroundTruthAdoptionError,
        PackageValidationError,
        RuntimeError,
        ValueError,
    ) as error:
        print(f"EVALUATION_RUN_ERROR={error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
