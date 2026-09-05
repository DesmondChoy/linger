"""Replay proactive memory surfacing without retrieval, delivery, or scheduling."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import logfire
from opentelemetry.trace import format_trace_id, get_current_span
from pydantic import Field
from pydantic_evals import Case, Dataset
from pydantic_evals.dataset import set_eval_attribute
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from apps.backend.config import get_settings
from apps.backend.telemetry import configure_synthetic_evaluation_telemetry
from evals.sculptor.surfacing_harness import (
    SurfacingExpectation,
    SurfacingGrade,
    grade_surfacing_expectation,
)
from src.linger.agents.contracts import PromptFingerprint
from src.linger.agents.sculptor.surfacing_models import (
    InvalidSurfacingProposal,
    SurfacingDecision,
    SurfacingInput,
    validate_surfacing_decision,
)
from src.linger.agents.sculptor.surfacing_prompt import PROMPT_FINGERPRINT
from src.linger.evaluation_transcript import bind_evaluation_transcript_sink

from .adoption import (
    GroundTruthAdoptionError,
    validate_ground_truth_adoption,
    validate_ground_truth_adoption_files,
)
from .models import (
    GroundTruthAdoption,
    ProposedGroundTruth,
    StrictModel,
    SyntheticBackstory,
)
from .replay import (
    RUNTIME_PROMPT_FINGERPRINTS,
    GroundTruthResult,
    GroundTruthStatus,
    _ground_truth_result,
    evaluation_agents,
)
from .surfacing_contract import CompiledSurfacingScene, compile_surfacing_scenes
from .transcript import AgentExchange, SceneTranscriptRecorder
from .validate_package import PackageValidationError, validate_package_files

SURFACING_OBJECTIVE_ID = "proactive_memory_surfacing"
OBJECTIVE_COMPONENTS = (
    "src.linger.agents.sculptor.surfacing_models.SurfacingInput",
    "src.linger.agents.sculptor.surfacing_models.SurfacingDecision",
    "src.linger.orchestration.surfacing.validate_surfacing_decision:v1",
    "evals.sculptor.surfacing_harness.grade_surfacing_expectation:v1",
)
SurfacingHandler = Callable[[SurfacingInput], Awaitable[SurfacingDecision]]
DecisionKind = Literal["surface_now", "defer", "do_not_surface"]


class SurfacingEvaluationIdentity(StrictModel):
    purpose: Literal["full_deployment_lineage", "objective_execution_comparison"]
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    configured_model: str
    prompt_fingerprints: tuple[PromptFingerprint, ...]
    component_contracts: tuple[str, ...]


class SurfacingEvaluationIdentities(StrictModel):
    full_deployment: SurfacingEvaluationIdentity
    objective_execution: SurfacingEvaluationIdentity


class SourceHash(StrictModel):
    memory_id: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SceneExecutionError(StrictModel):
    error_type: str
    code: Literal["surfacing_model_failed", "invalid_surfacing_proposal"]
    message: Literal["Sculptor failed to produce a valid surfacing decision."] = (
        "Sculptor failed to produce a valid surfacing decision."
    )


class SurfacingSceneObservation(StrictModel):
    scene_id: str
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    input: SurfacingInput
    expected: SurfacingExpectation
    response: SurfacingDecision | None
    execution_error: SceneExecutionError | None
    ground_truth_result: GroundTruthResult
    grade: SurfacingGrade
    source_hashes_before: tuple[SourceHash, ...]
    source_hashes_after: tuple[SourceHash, ...]
    source_immutable: bool
    input_immutable: bool
    agent_exchanges: tuple[AgentExchange, ...]


class DecisionAccuracy(StrictModel):
    decision: DecisionKind
    total: int = Field(ge=0)
    correct: int = Field(ge=0)
    accuracy: float | None


class SurfacingMetrics(StrictModel):
    """Score emitted labels separately from hard gates and semantic usefulness.

    Schema-valid labels count even when source or time validation fails.
    Missing and malformed responses count as incorrect decisions.
    """

    scene_count: int = Field(ge=0)
    response_count: int = Field(ge=0)
    execution_failure_count: int = Field(ge=0)
    hard_gate_pass_count: int = Field(ge=0)
    hard_gate_pass_rate: float | None
    decision_correct_count: int = Field(ge=0)
    decision_accuracy: float | None
    class_decision_accuracy: tuple[DecisionAccuracy, ...]
    expected_surface_count: int = Field(ge=0)
    predicted_surface_count: int = Field(ge=0)
    correct_surface_count: int = Field(ge=0)
    surface_decision_precision: float | None
    surface_decision_recall: float | None
    semantic_review_required_count: int = Field(ge=0)
    semantic_quality_evaluated: Literal[False] = False


class SurfacingEvaluationRun(StrictModel):
    artifact_schema_version: Literal["1"] = "1"
    content_classification: Literal["synthetic"] = "synthetic"
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    objective_id: Literal["proactive_memory_surfacing"] = SURFACING_OBJECTIVE_ID
    dataset_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    backstory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposed_ground_truth_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    package_bytes_verified: bool
    ground_truth_status: GroundTruthStatus
    identities: SurfacingEvaluationIdentities
    scenes: tuple[SurfacingSceneObservation, ...]
    metrics: SurfacingMetrics


@dataclass(repr=False)
class SurfacingGroundTruthEvaluator(
    Evaluator[CompiledSurfacingScene, SurfacingSceneObservation, dict[str, object]]
):
    ground_truth_status: GroundTruthStatus

    def evaluate(
        self,
        ctx: EvaluatorContext[
            CompiledSurfacingScene, SurfacingSceneObservation, dict[str, object]
        ],
    ) -> str:
        return ctx.output.ground_truth_result

    def get_default_evaluation_name(self) -> str:
        return (
            "adopted_hard_gate_grade"
            if self.ground_truth_status == "adopted"
            else "proposal_comparison"
        )


def build_surfacing_identities(
    *,
    configured_model: str | None = None,
    full_prompt_fingerprints: tuple[PromptFingerprint, ...] | None = None,
    objective_prompt_fingerprints: tuple[PromptFingerprint, ...] | None = None,
) -> SurfacingEvaluationIdentities:
    model = configured_model or get_settings().linger_model
    full_prompts = full_prompt_fingerprints or (
        *RUNTIME_PROMPT_FINGERPRINTS,
        PROMPT_FINGERPRINT,
    )
    objective_prompts = objective_prompt_fingerprints or (PROMPT_FINGERPRINT,)

    def identity(
        purpose: Literal["full_deployment_lineage", "objective_execution_comparison"],
        prompts: tuple[PromptFingerprint, ...],
        components: tuple[str, ...],
    ) -> SurfacingEvaluationIdentity:
        document = {
            "purpose": purpose,
            "configured_model": model,
            "prompt_fingerprints": [item.model_dump(mode="json") for item in prompts],
            "component_contracts": components,
        }
        digest = hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return SurfacingEvaluationIdentity(
            purpose=purpose,
            digest=digest,
            configured_model=model,
            prompt_fingerprints=prompts,
            component_contracts=components,
        )

    return SurfacingEvaluationIdentities(
        full_deployment=identity("full_deployment_lineage", full_prompts, ()),
        objective_execution=identity(
            "objective_execution_comparison", objective_prompts, OBJECTIVE_COMPONENTS
        ),
    )


async def replay_surfacing_scenes(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    *,
    handler: SurfacingHandler | None = None,
    adoption: GroundTruthAdoption | None = None,
    backstory_bytes: bytes | None = None,
    ground_truth_bytes: bytes | None = None,
    configured_model: str | None = None,
) -> SurfacingEvaluationRun:
    """Run every Scene, retaining model failures in the evaluation denominator."""
    scene_inputs = compile_surfacing_scenes(backstory, ground_truth)
    package_bytes_verified = (
        backstory_bytes is not None and ground_truth_bytes is not None
    )
    if adoption is not None and not package_bytes_verified:
        raise ValueError(
            "adopted replay requires exact backstory_bytes and ground_truth_bytes"
        )
    if backstory_bytes is not None:
        if SyntheticBackstory.model_validate_json(backstory_bytes) != backstory:
            raise ValueError("Backstory bytes do not describe the supplied model")
        if hashlib.sha256(backstory_bytes).hexdigest() != ground_truth.backstory_sha256:
            raise ValueError(
                "Backstory bytes do not match Ground truth backstory_sha256"
            )
    if ground_truth_bytes is not None:
        if ProposedGroundTruth.model_validate_json(ground_truth_bytes) != ground_truth:
            raise ValueError("Ground truth bytes do not describe the supplied model")
    else:
        ground_truth_bytes = ground_truth.model_dump_json().encode("utf-8")
    if adoption is not None:
        validate_ground_truth_adoption(
            ground_truth, adoption, ground_truth_bytes=ground_truth_bytes
        )
    proposed_sha256 = hashlib.sha256(ground_truth_bytes).hexdigest()
    ground_truth_status: GroundTruthStatus = (
        adoption.ground_truth_status if adoption is not None else "proposed"
    )
    dataset_version = (
        adoption.adopted_ground_truth_identity
        if adoption is not None
        else hashlib.sha256(
            backstory.model_dump_json().encode("utf-8")
            + proposed_sha256.encode("ascii")
        ).hexdigest()
    )
    if handler is None:
        if configured_model is not None:
            raise ValueError("configured_model may only label an injected handler")
        handler, agents = _production_components()
        configure_synthetic_evaluation_telemetry(agents)

    run_id = uuid4().hex
    identities = build_surfacing_identities(configured_model=configured_model)
    observations: list[SurfacingSceneObservation] = []
    active_handler = handler

    async def evaluate_scene(
        scene: CompiledSurfacingScene,
    ) -> SurfacingSceneObservation:
        if scene.scene_id != scene_inputs[len(observations)].scene_id:
            raise RuntimeError("surfacing evaluation did not execute in Scene order")
        observation = await _replay_scene(
            scene, handler=active_handler, ground_truth_status=ground_truth_status
        )
        observations.append(observation)
        return observation

    dataset: Dataset[
        CompiledSurfacingScene, SurfacingSceneObservation, dict[str, object]
    ] = Dataset(
        name=SURFACING_OBJECTIVE_ID,
        cases=[
            Case(
                name=scene.scene_id,
                inputs=scene,
                metadata={
                    "scene_order": scene.order,
                    "case_kind": scene.expectation.case_kind,
                    "expected_decision": scene.expectation.decision,
                    "ground_truth_status": ground_truth_status,
                },
            )
            for scene in scene_inputs
        ],
        evaluators=[SurfacingGroundTruthEvaluator(ground_truth_status)],
    )
    report = await dataset.evaluate(
        evaluate_scene,
        name=f"{SURFACING_OBJECTIVE_ID}-{run_id[:8]}",
        task_name="proactive_memory_surfacing_workflow",
        max_concurrency=1,
        progress=False,
        metadata={
            "content_classification": "synthetic",
            "objective_id": SURFACING_OBJECTIVE_ID,
            "run_id": run_id,
            "dataset_version": dataset_version,
            "full_deployment_identity": identities.full_deployment.digest,
            "objective_execution_identity": identities.objective_execution.digest,
            "ground_truth_status": ground_truth_status,
            "semantic_quality_evaluated": False,
        },
    )
    if report.failures or len(observations) != len(scene_inputs):
        raise RuntimeError(
            "surfacing evaluation framework failed to record every Scene"
        )
    scenes = tuple(observations)
    return SurfacingEvaluationRun(
        run_id=run_id,
        trace_id=report.trace_id or "0" * 32,
        dataset_version=dataset_version,
        backstory_sha256=ground_truth.backstory_sha256,
        proposed_ground_truth_sha256=proposed_sha256,
        package_bytes_verified=package_bytes_verified,
        ground_truth_status=ground_truth_status,
        identities=identities,
        scenes=scenes,
        metrics=_metrics(scenes),
    )


async def _replay_scene(
    scene: CompiledSurfacingScene,
    *,
    handler: SurfacingHandler,
    ground_truth_status: GroundTruthStatus,
) -> SurfacingSceneObservation:
    original_input = scene.input.model_copy(deep=True)
    supplied_input = scene.input.model_copy(deep=True)
    recorder = SceneTranscriptRecorder()
    before = _source_hashes(original_input)
    response = None
    execution_error = None
    try:
        with bind_evaluation_transcript_sink(recorder):
            raw_response = await handler(supplied_input)
        response = validate_surfacing_decision(original_input, raw_response)
    except Exception as error:
        if response is None and isinstance(error, InvalidSurfacingProposal):
            response = error.proposal
        execution_error = SceneExecutionError(
            error_type=type(error).__name__,
            code=(
                "invalid_surfacing_proposal"
                if isinstance(error, InvalidSurfacingProposal)
                else "surfacing_model_failed"
            ),
        )
    after = _source_hashes(supplied_input)
    input_immutable = supplied_input == original_input
    grade = grade_surfacing_expectation(original_input, response, scene.expectation)
    failures = list(grade.hard_failures)
    if execution_error is not None:
        failures.append(f"execution_failed:{execution_error.error_type}")
    if not input_immutable:
        failures.append("supplied_input_changed")
    grade = grade.model_copy(update={"hard_failures": tuple(failures)})
    ground_truth_result = _ground_truth_result(
        matches=not failures, ground_truth_status=ground_truth_status
    )
    set_eval_attribute("ground_truth_result", ground_truth_result)
    set_eval_attribute("source_immutable", before == after)
    set_eval_attribute(
        "decision", response.decision if response else "execution_failed"
    )
    return SurfacingSceneObservation(
        scene_id=scene.scene_id,
        trace_id=format_trace_id(get_current_span().get_span_context().trace_id),
        input=original_input,
        expected=scene.expectation,
        response=response,
        execution_error=execution_error,
        ground_truth_result=ground_truth_result,
        grade=grade,
        source_hashes_before=before,
        source_hashes_after=after,
        source_immutable=before == after,
        input_immutable=input_immutable,
        agent_exchanges=recorder.exchanges,
    )


def _source_hashes(input: SurfacingInput) -> tuple[SourceHash, ...]:
    return tuple(
        SourceHash(
            memory_id=memory.memory_id,
            sha256=hashlib.sha256(memory.text.encode("utf-8")).hexdigest(),
        )
        for memory in input.memories
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _metrics(scenes: tuple[SurfacingSceneObservation, ...]) -> SurfacingMetrics:
    correct = sum(scene.grade.decision_match for scene in scenes)
    hard_pass = sum(not scene.grade.hard_failures for scene in scenes)
    expected_surface = sum(scene.expected.decision == "surface_now" for scene in scenes)
    predicted_surface = sum(
        scene.response is not None and scene.response.decision == "surface_now"
        for scene in scenes
    )
    correct_surface = sum(
        scene.expected.decision == "surface_now"
        and scene.response is not None
        and scene.response.decision == "surface_now"
        for scene in scenes
    )
    classes = []
    for decision in ("surface_now", "defer", "do_not_surface"):
        members = tuple(
            scene for scene in scenes if scene.expected.decision == decision
        )
        class_correct = sum(scene.grade.decision_match for scene in members)
        classes.append(
            DecisionAccuracy(
                decision=decision,
                total=len(members),
                correct=class_correct,
                accuracy=_ratio(class_correct, len(members)),
            )
        )
    return SurfacingMetrics(
        scene_count=len(scenes),
        response_count=sum(scene.response is not None for scene in scenes),
        execution_failure_count=sum(
            scene.execution_error is not None for scene in scenes
        ),
        hard_gate_pass_count=hard_pass,
        hard_gate_pass_rate=_ratio(hard_pass, len(scenes)),
        decision_correct_count=correct,
        decision_accuracy=_ratio(correct, len(scenes)),
        class_decision_accuracy=tuple(classes),
        expected_surface_count=expected_surface,
        predicted_surface_count=predicted_surface,
        correct_surface_count=correct_surface,
        surface_decision_precision=_ratio(correct_surface, predicted_surface),
        surface_decision_recall=_ratio(correct_surface, expected_surface),
        semantic_review_required_count=sum(
            scene.grade.semantic_review_required for scene in scenes
        ),
    )


def _production_components() -> tuple[SurfacingHandler, tuple[Any, ...]]:
    from src.linger.agents.sculptor.surfacing_agent import surfacing_agent
    from src.linger.orchestration.surfacing import propose_surfacing

    return propose_surfacing, (*evaluation_agents(), surfacing_agent)


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
            backstory, ground_truth, adoption = validate_ground_truth_adoption_files(
                args.backstory, args.ground_truth, args.adoption
            )
        result = asyncio.run(
            replay_surfacing_scenes(
                backstory,
                ground_truth,
                adoption=adoption,
                backstory_bytes=args.backstory.read_bytes(),
                ground_truth_bytes=args.ground_truth.read_bytes(),
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
        PackageValidationError,
        GroundTruthAdoptionError,
        RuntimeError,
        ValueError,
    ) as error:
        print(f"EVALUATION_RUN_ERROR={error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
