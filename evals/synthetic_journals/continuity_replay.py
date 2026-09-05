"""Replay session-continuity Scenes through Linger's production chat boundary."""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self
from uuid import uuid4

import logfire
from opentelemetry.trace import format_span_id, format_trace_id, get_current_span
from pydantic import Field, model_validator
from pydantic_evals import Case, Dataset
from pydantic_evals.dataset import set_eval_attribute
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from apps.backend import sessions
from apps.backend.schemas import CaptureInspection, ChatRequest, ChatResponse
from apps.backend.telemetry import configure_synthetic_evaluation_telemetry
from src.linger.agents.contracts import PromptFingerprint
from src.linger.contracts.turn import ReleaseSource
from src.linger.evaluation_transcript import bind_evaluation_transcript_sink
from src.linger.services.memory import AccountContext, MemoryPolicyService

from .adoption import (
    GroundTruthAdoptionError,
    validate_ground_truth_adoption_files,
)
from .models import (
    GroundTruthAdoption,
    Line,
    ProposedGroundTruth,
    StrictModel,
    SyntheticBackstory,
)
from .replay import (
    RUNTIME_PROMPT_FINGERPRINTS,
    RUNTIME_SYSTEM_VARIANT,
    ChatTurnHandler,
    GroundTruthResult,
    GroundTruthStatus,
    _ground_truth_result,
    _production_chat_turn_handler,
    evaluation_agents,
)
from .transcript import AgentExchange, SceneTranscriptRecorder
from .validate_package import PackageValidationError, validate_package_files

CONTINUITY_OBJECTIVE_ID = "session_scoped_conversation_continuity"
MESSAGES_PER_EXCHANGE = 2

SceneRole = Literal["continuity", "comparison"]
ContinuityGroundTruthResult = GroundTruthResult | Literal["not_applicable"]


class TurnObservation(StrictModel):
    """Recorded production outcome for one Line inside one persisted session."""

    line_id: str
    order: int = Field(ge=1)
    input_line: str
    reply: str
    release_source: ReleaseSource
    boundary_origin: Literal["preflight", "candidate_review"] | None
    store_messages_before: int = Field(ge=0)
    store_messages_appended: int = Field(ge=0)
    prior_evidence_rehydrated: int = Field(ge=0)
    context_resolution_status: Literal["confirmed", "inferred", "unknown"]
    exchange_sequence_first: int | None = Field(default=None, ge=1)
    exchange_sequence_last: int | None = Field(default=None, ge=1)
    capture: CaptureInspection
    span_id: str = Field(pattern=r"^[0-9a-f]{16}$")

    @model_validator(mode="after")
    def validate_boundary_origin(self) -> Self:
        is_boundary = self.release_source == "application_emotional_boundary"
        if is_boundary != (self.boundary_origin is not None):
            raise ValueError(
                "boundary_origin is required only for an emotional-boundary release"
            )
        return self

    @model_validator(mode="after")
    def validate_exchange_range(self) -> Self:
        first = self.exchange_sequence_first
        last = self.exchange_sequence_last
        if (first is None) != (last is None):
            raise ValueError("an exchange range needs both bounds or neither")
        if first is not None and last is not None and last < first:
            raise ValueError("exchange_sequence_last precedes exchange_sequence_first")
        return self


class ContinuitySceneObservation(StrictModel):
    """Complete durable observation for one Scene and its ordered Lines."""

    scene_id: str
    role: SceneRole
    paired_scene_id: str | None
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    turns: tuple[TurnObservation, ...] = Field(min_length=1)
    session_turn_release_sources: tuple[ReleaseSource, ...]
    ground_truth_result: ContinuityGroundTruthResult
    structural_findings: tuple[str, ...]
    agent_exchanges: tuple[AgentExchange, ...]

    @model_validator(mode="after")
    def validate_pairing(self) -> Self:
        is_comparison = self.role == "comparison"
        if is_comparison != (self.paired_scene_id is not None):
            raise ValueError(
                "paired_scene_id is required only for a comparison Scene"
            )
        return self


class ContinuityEvaluationRun(StrictModel):
    """One isolated run of ordered session-continuity Scenes."""

    artifact_schema_version: Literal["1"] = "1"
    content_classification: Literal["synthetic"] = "synthetic"
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    objective_id: Literal["session_scoped_conversation_continuity"]
    dataset_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    system_variant: str = Field(pattern=r"^[0-9a-f]{64}$")
    ground_truth_status: GroundTruthStatus
    capture_enabled: Literal[False]
    runtime_prompt_fingerprints: tuple[PromptFingerprint, ...]
    scenes: tuple[ContinuitySceneObservation, ...]
    final_active_memory_ids: tuple[str, ...]


class ContinuityEvaluationInput(StrictModel):
    """Ordered Scene Lines shown as one native Logfire evaluation case input."""

    order: int = Field(ge=1)
    scene_id: str
    role: SceneRole
    lines: tuple[str, ...] = Field(min_length=1)


class ContinuityEvaluationExpected(StrictModel):
    """Proposal-backed Scene role and session boundary shown as expected output."""

    role: SceneRole
    paired_scene_id: str | None
    ground_truth_status: GroundTruthStatus


class ContinuityEvaluationOutput(StrictModel):
    """Compact session-state result displayed by Logfire's Evals UI."""

    role: SceneRole
    session_boundary_held: bool | None
    ground_truth_result: ContinuityGroundTruthResult
    structural_findings: tuple[str, ...]
    session_turn_release_sources: tuple[ReleaseSource, ...]
    replies: tuple[str, ...]


ContinuityEvaluationResult = ContinuityEvaluationExpected | ContinuityEvaluationOutput


@dataclass(frozen=True)
class _ContinuityScene:
    """One guarded Scene with its resolved role and ordered Lines."""

    scene_id: str
    order: int
    role: SceneRole
    paired_scene_id: str | None
    lines: tuple[Line, ...]


@dataclass(repr=False)
class ContinuityStructuralEvaluator(
    Evaluator[
        ContinuityEvaluationInput,
        ContinuityEvaluationResult,
        dict[str, object],
    ]
):
    """Grade the proposal-backed session boundary and label session invariants."""

    ground_truth_status: GroundTruthStatus

    def evaluate(
        self,
        ctx: EvaluatorContext[
            ContinuityEvaluationInput,
            ContinuityEvaluationResult,
            dict[str, object],
        ],
    ) -> dict[str, str | EvaluationReason]:
        output = ctx.output
        if not isinstance(output, ContinuityEvaluationOutput):
            raise TypeError("continuity evaluation task returned the wrong output")
        if output.role == "comparison":
            if output.session_boundary_held is None:
                raise ValueError("comparison Scene reported no session boundary")
            result: ContinuityGroundTruthResult = _ground_truth_result(
                matches=output.session_boundary_held,
                ground_truth_status=self.ground_truth_status,
            )
        else:
            result = "not_applicable"
        if output.ground_truth_result != result:
            raise ValueError("continuity Ground truth result is inconsistent")
        findings = output.structural_findings
        return {
            self.get_default_evaluation_name(): result,
            "session_state_invariants": EvaluationReason(
                value="deviated" if findings else "held",
                reason=", ".join(findings) or None,
            ),
        }

    def get_default_evaluation_name(self) -> str:
        if self.ground_truth_status == "adopted":
            return "adopted_hard_gate_grade"
        return "proposal_comparison"


async def replay_continuity_scenes(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    *,
    adoption: GroundTruthAdoption | None = None,
    chat_handler: ChatTurnHandler | None = None,
) -> ContinuityEvaluationRun:
    """Run ordered continuity Scenes through Pydantic Evals and production chat."""

    scenes = _continuity_scenes(backstory, ground_truth)
    ground_truth_status: GroundTruthStatus = (
        adoption.ground_truth_status
        if adoption is not None
        else ground_truth.ground_truth_status
    )
    dataset_version = (
        adoption.adopted_ground_truth_identity
        if adoption is not None
        else ground_truth.backstory_sha256
    )
    evaluation_name = (
        "adopted_hard_gate_grade"
        if ground_truth_status == "adopted"
        else "proposal_comparison"
    )
    if chat_handler is None:
        handler = _production_chat_turn_handler()
        configure_synthetic_evaluation_telemetry(evaluation_agents())
    else:
        handler = chat_handler

    run_id = uuid4().hex
    account = AccountContext(
        f"synthetic-eval:{backstory.backstory.evaluation_account_id}:{run_id}"
    )
    cases: list[
        Case[
            ContinuityEvaluationInput,
            ContinuityEvaluationResult,
            dict[str, object],
        ]
    ] = []
    for scene in scenes:
        cases.append(
            Case(
                name=scene.scene_id,
                inputs=ContinuityEvaluationInput(
                    order=scene.order,
                    scene_id=scene.scene_id,
                    role=scene.role,
                    lines=tuple(line.text for line in scene.lines),
                ),
                expected_output=ContinuityEvaluationExpected(
                    role=scene.role,
                    paired_scene_id=scene.paired_scene_id,
                    ground_truth_status=ground_truth_status,
                ),
                metadata={
                    "objective_id": CONTINUITY_OBJECTIVE_ID,
                    "scene_order": scene.order,
                    "scene_role": scene.role,
                    "line_count": len(scene.lines),
                    "ground_truth_status": ground_truth_status,
                },
            )
        )

    observations: list[ContinuitySceneObservation] = []
    with tempfile.TemporaryDirectory(prefix="linger-synthetic-eval-") as directory:
        service = MemoryPolicyService(Path(directory))
        if service.capture_enabled(
            account
        ):  # pragma: no cover - fresh store invariant
            raise RuntimeError(
                "isolated evaluation account unexpectedly has capture enabled"
            )

        async def evaluate_scene(
            inputs: ContinuityEvaluationInput,
        ) -> ContinuityEvaluationOutput:
            expected_order = len(observations) + 1
            if inputs.order != expected_order:
                raise RuntimeError(
                    "synthetic evaluation cases did not execute in Scene order"
                )
            expected = cases[inputs.order - 1].expected_output
            if not isinstance(expected, ContinuityEvaluationExpected):
                raise RuntimeError("synthetic evaluation proposal is unavailable")
            observation = await _replay_continuity_scene(
                scenes[inputs.order - 1],
                expected,
                run_id=run_id,
                handler=handler,
                service=service,
                account=account,
            )
            observations.append(observation)
            return ContinuityEvaluationOutput(
                role=observation.role,
                session_boundary_held=_session_boundary_held(
                    observation.role,
                    observation.turns,
                    observation.session_turn_release_sources,
                ),
                ground_truth_result=observation.ground_truth_result,
                structural_findings=observation.structural_findings,
                session_turn_release_sources=(
                    observation.session_turn_release_sources
                ),
                replies=tuple(turn.reply for turn in observation.turns),
            )

        dataset = Dataset(
            name=CONTINUITY_OBJECTIVE_ID,
            cases=cases,
            evaluators=[
                ContinuityStructuralEvaluator(
                    ground_truth_status=ground_truth_status
                )
            ],
        )
        report = await dataset.evaluate(
            evaluate_scene,
            name=f"{CONTINUITY_OBJECTIVE_ID}-{run_id[:8]}",
            task_name="session_continuity_workflow",
            max_concurrency=1,
            progress=False,
            metadata={
                "content_classification": "synthetic",
                "objective_id": CONTINUITY_OBJECTIVE_ID,
                "run_id": run_id,
                "dataset_version": dataset_version,
                "system_variant": RUNTIME_SYSTEM_VARIANT,
                "ground_truth_status": ground_truth_status,
                "ground_truth_evaluation": evaluation_name,
            },
        )
        if report.failures:
            failed_cases = [failure.name for failure in report.failures]
            raise RuntimeError(f"synthetic continuity cases failed: {failed_cases}")
        if len(observations) != len(cases):
            raise RuntimeError("synthetic continuity evaluation missed a Scene")

        active_ids = tuple(record.memory_id for record in service.list_active(account))

    if active_ids:
        raise RuntimeError(
            "continuity replay committed memories while capture was disabled"
        )

    return ContinuityEvaluationRun(
        run_id=run_id,
        trace_id=report.trace_id or "0" * 32,
        objective_id=CONTINUITY_OBJECTIVE_ID,
        dataset_version=dataset_version,
        system_variant=RUNTIME_SYSTEM_VARIANT,
        ground_truth_status=ground_truth_status,
        capture_enabled=False,
        runtime_prompt_fingerprints=RUNTIME_PROMPT_FINGERPRINTS,
        scenes=tuple(observations),
        final_active_memory_ids=active_ids,
    )


async def _replay_continuity_scene(
    scene: _ContinuityScene,
    expected: ContinuityEvaluationExpected,
    *,
    run_id: str,
    handler: ChatTurnHandler,
    service: MemoryPolicyService,
    account: AccountContext,
) -> ContinuitySceneObservation:
    if tuple(service.list_active(account)):
        raise RuntimeError(
            f"Scene {scene.scene_id} began with a non-empty durable memory store"
        )
    recorder = SceneTranscriptRecorder()
    session_id = f"synthetic-eval:{run_id}:scene:{scene.scene_id}"
    turns: list[TurnObservation] = []
    try:
        with bind_evaluation_transcript_sink(recorder):
            for line in scene.lines:
                request = ChatRequest(
                    session_id=session_id,
                    turn_id=f"synthetic-eval:{run_id}:turn:{uuid4().hex}",
                    message=line.text,
                )
                store_before = len(sessions.history(session_id))
                exchanges_before = len(recorder.exchanges)
                response = await handler(request, service, account)
                store_after = len(sessions.history(session_id))
                turns.append(
                    _turn_observation(
                        scene.scene_id,
                        line,
                        response,
                        store_before=store_before,
                        store_after=store_after,
                        exchanges_before=exchanges_before,
                        recorder=recorder,
                    )
                )
        records = sessions.turn_records(session_id)
    finally:
        sessions.clear(session_id)

    release_sources = tuple(record.release_source for record in records)
    findings = _structural_findings(tuple(turns), release_sources, recorder.exchanges)
    boundary_held = _session_boundary_held(
        scene.role, tuple(turns), release_sources
    )
    if boundary_held is None:
        ground_truth_result: ContinuityGroundTruthResult = "not_applicable"
    else:
        ground_truth_result = _ground_truth_result(
            matches=boundary_held,
            ground_truth_status=expected.ground_truth_status,
        )
    set_eval_attribute("scene_role", scene.role)
    set_eval_attribute("ground_truth_result", ground_truth_result)
    set_eval_attribute("structural_findings", list(findings))
    set_eval_attribute("turn_count", len(turns))
    trace_id = format_trace_id(get_current_span().get_span_context().trace_id)
    return ContinuitySceneObservation(
        scene_id=scene.scene_id,
        role=scene.role,
        paired_scene_id=scene.paired_scene_id,
        trace_id=trace_id,
        turns=tuple(turns),
        session_turn_release_sources=release_sources,
        ground_truth_result=ground_truth_result,
        structural_findings=findings,
        agent_exchanges=recorder.exchanges,
    )


def _turn_observation(
    scene_id: str,
    line: Line,
    response: ChatResponse,
    *,
    store_before: int,
    store_after: int,
    exchanges_before: int,
    recorder: SceneTranscriptRecorder,
) -> TurnObservation:
    release = response.inspection.release
    if release is None:
        raise RuntimeError(
            "production chat returned no release inspection for "
            f"Scene {scene_id} Line {line.line_id}"
        )
    exchanges_after = len(recorder.exchanges)
    produced_exchange = exchanges_after > exchanges_before
    span_id = format_span_id(get_current_span().get_span_context().span_id)
    return TurnObservation(
        line_id=line.line_id,
        order=line.order,
        input_line=line.text,
        reply=response.reply,
        release_source=release.release_source,
        boundary_origin=release.boundary_origin,
        store_messages_before=store_before,
        store_messages_appended=store_after - store_before,
        prior_evidence_rehydrated=response.inspection.prior_evidence_count,
        context_resolution_status=response.inspection.context_resolution.get(
            "status", "unknown"
        ),
        exchange_sequence_first=exchanges_before + 1 if produced_exchange else None,
        exchange_sequence_last=exchanges_after if produced_exchange else None,
        capture=release.capture,
        span_id=span_id,
    )


def _structural_findings(
    turns: tuple[TurnObservation, ...],
    release_sources: tuple[ReleaseSource, ...],
    agent_exchanges: tuple[AgentExchange, ...],
) -> tuple[str, ...]:
    """Report session-contract deviations without touching the Ground-truth grade."""

    findings: list[str] = []
    expected_before = 0
    for turn in turns:
        released = turn.release_source in {"muse_candidate", "application_clarification"}
        expected_appended = MESSAGES_PER_EXCHANGE if released else 0
        if not released:
            findings.append(f"unreleased_turn:{turn.line_id}")
        if (
            turn.store_messages_appended != expected_appended
            or turn.store_messages_before != expected_before
        ):
            findings.append(f"history_thread_broken:{turn.line_id}")
        turn_routed_agent_engaged = turn.exchange_sequence_first is not None and any(
            exchange.role in {"Librarian", "Serendipity"}
            for exchange in agent_exchanges
            if turn.exchange_sequence_first
            <= exchange.sequence
            <= turn.exchange_sequence_last
        )
        if turn_routed_agent_engaged and turn.context_resolution_status != "unknown":
            findings.append(f"routed_agent_engaged:{turn.line_id}")
        expected_before += turn.store_messages_appended
    if release_sources != tuple(turn.release_source for turn in turns):
        findings.append("turn_record_mismatch")
    return tuple(findings)


def _session_boundary_held(
    role: SceneRole,
    turns: tuple[TurnObservation, ...],
    release_sources: tuple[ReleaseSource, ...],
) -> bool | None:
    """Defensive assertion against a rehydration regression, not a cross-scene leak detector."""

    if role != "comparison":
        return None
    return (
        turns[0].store_messages_before == 0
        and turns[0].prior_evidence_rehydrated == 0
        and len(release_sources) == 1
    )


def _continuity_scenes(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
) -> tuple[_ContinuityScene, ...]:
    if backstory.objective_ids != (CONTINUITY_OBJECTIVE_ID,):
        raise ValueError(
            "continuity replay requires only session_scoped_conversation_continuity"
        )
    if backstory.run_configuration_ids:
        raise ValueError("continuity replay accepts no run configuration")
    if backstory.props or backstory.offline_inputs:
        raise ValueError("continuity replay does not accept Props or offline inputs")

    lines = {line.line_id: line for line in backstory.lines}
    ordered = sorted(backstory.scenes, key=lambda item: item.order)
    scene_lines: dict[str, tuple[Line, ...]] = {}
    for scene in ordered:
        if scene.objective_ids != (CONTINUITY_OBJECTIVE_ID,):
            raise ValueError(
                f"Scene {scene.scene_id} must select only "
                "session_scoped_conversation_continuity"
            )
        if not scene.fresh_session:
            raise ValueError(f"Scene {scene.scene_id} must use a fresh session")
        if scene.prop_ids or scene.offline_input_ids:
            raise ValueError(
                f"Scene {scene.scene_id} cannot use Props or offline inputs"
            )
        if not scene.line_ids:
            raise ValueError(f"Scene {scene.scene_id} requires at least one Line")
        scene_lines[scene.scene_id] = tuple(
            lines[line_id] for line_id in scene.line_ids
        )

    roles = _scene_roles(ground_truth, scene_lines)
    return tuple(
        _ContinuityScene(
            scene_id=scene.scene_id,
            order=order,
            role=roles[scene.scene_id][0],
            paired_scene_id=roles[scene.scene_id][1],
            lines=scene_lines[scene.scene_id],
        )
        for order, scene in enumerate(ordered, start=1)
    )


def _scene_roles(
    ground_truth: ProposedGroundTruth,
    scene_lines: dict[str, tuple[Line, ...]],
) -> dict[str, tuple[SceneRole, str | None]]:
    """Derive Scene roles from pairing topology and Line counts, not direction."""

    edges: list[frozenset[str]] = []
    for proposal in ground_truth.proposals:
        if proposal.objective_id != CONTINUITY_OBJECTIVE_ID:
            continue
        if proposal.pairing is None:
            continue
        edge = frozenset({proposal.scene_id, proposal.pairing.paired_scene_id})
        if len(edge) != 2:
            raise ValueError(f"Scene {proposal.scene_id} cannot pair with itself")
        if edge not in edges:
            edges.append(edge)
    if not edges:
        raise ValueError("continuity replay requires at least one paired Scene")

    roles: dict[str, tuple[SceneRole, str | None]] = {}
    for edge in edges:
        first, second = sorted(edge)
        for scene_id in (first, second):
            if scene_id not in scene_lines:
                raise ValueError(f"pairing references unknown Scene {scene_id}")
            if scene_id in roles:
                raise ValueError(
                    f"Scene {scene_id} appears in more than one pairing edge"
                )
        if len(scene_lines[first]) == len(scene_lines[second]):
            raise ValueError(
                f"paired Scenes {first} and {second} must differ in Line count"
            )
        continuity_id, comparison_id = (
            (first, second)
            if len(scene_lines[first]) > len(scene_lines[second])
            else (second, first)
        )
        if len(scene_lines[comparison_id]) != 1:
            raise ValueError(
                f"comparison Scene {comparison_id} must contain exactly one Line"
            )
        if scene_lines[comparison_id][0].text != scene_lines[continuity_id][-1].text:
            raise ValueError(
                f"comparison Scene {comparison_id} Line must repeat the final Line "
                f"of Scene {continuity_id}"
            )
        roles[continuity_id] = ("continuity", None)
        roles[comparison_id] = ("comparison", continuity_id)

    for scene_id, scene_line in scene_lines.items():
        if scene_id in roles:
            continue
        if len(scene_line) == 1:
            raise ValueError(
                f"Scene {scene_id} has one Line without a paired comparison"
            )
        roles[scene_id] = ("continuity", None)
    return roles


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backstory", type=Path)
    parser.add_argument("ground_truth", type=Path)
    parser.add_argument("--adoption", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.adoption is None:
            backstory, ground_truth = validate_package_files(
                args.backstory, args.ground_truth
            )
            adoption = None
        else:
            backstory, ground_truth, adoption = (
                validate_ground_truth_adoption_files(
                    args.backstory,
                    args.ground_truth,
                    args.adoption,
                )
            )
        result = asyncio.run(
            replay_continuity_scenes(
                backstory,
                ground_truth,
                adoption=adoption,
            )
        )
        rendered = result.model_dump_json(indent=2) + "\n"
        if args.output is None:
            print(rendered, end="")
        else:
            args.output.write_text(rendered, encoding="utf-8")
        logfire.force_flush()
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
