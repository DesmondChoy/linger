"""Replay isolated capture and bounded-curation Scenes in one ordered evaluation."""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from apps.backend.telemetry import configure_synthetic_evaluation_telemetry
from src.linger.agents.contracts import PromptFingerprint
from src.linger.agents.sculptor.models import AccountScopedMemories
from src.linger.services.memory import AccountContext, MemoryPolicyService

from .adoption import GroundTruthAdoptionError, validate_ground_truth_adoption_files
from .curation_replay import (
    CURATION_OBJECTIVE_ID,
    CurationEvaluationExpected,
    CurationEvaluationIdentities,
    CurationEvaluationInput,
    CurationEvaluationOutput,
    CurationHandler,
    CurationSceneObservation,
    build_curation_identities,
    curation_scene_input,
    replay_curation_scene,
)
from .evaluation_link import emit_evaluation_link
from .models import (
    GroundTruthAdoption,
    ProposedGroundTruth,
    StrictModel,
    SyntheticBackstory,
)
from .replay import (
    CAPTURE_OBJECTIVE_ID,
    RUNTIME_PROMPT_FINGERPRINTS,
    RUNTIME_SYSTEM_VARIANT,
    CaptureEvaluationExpected,
    CaptureEvaluationInput,
    CaptureEvaluationOutput,
    ChatTurnHandler,
    GroundTruthStatus,
    SceneObservation,
    _ground_truth_result,
    _production_chat_turn_handler,
    capture_scene_expectation,
    capture_scene_input,
    evaluation_agents,
    replay_capture_scene,
)
from .validate_scenario import ScenarioValidationError, validate_scenario_files

OBJECTIVE_IDS = (CAPTURE_OBJECTIVE_ID, CURATION_OBJECTIVE_ID)
EVALUATION_NAME = "reviewed_capture_and_bounded_curation"
CombinedInput = CaptureEvaluationInput | CurationEvaluationInput
CombinedExpected = CaptureEvaluationExpected | CurationEvaluationExpected
CombinedOutput = CaptureEvaluationOutput | CurationEvaluationOutput
CombinedResult = CombinedExpected | CombinedOutput
CombinedObservation = SceneObservation | CurationSceneObservation


class CaptureCurationEvaluationRun(StrictModel):
    """A single artifact retaining the original Scenario and adopted label identity."""

    artifact_schema_version: Literal["1"] = "1"
    content_classification: Literal["synthetic"] = "synthetic"
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    objective_ids: tuple[str, str]
    backstory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposed_ground_truth_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    dataset_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    system_variant: str = Field(pattern=r"^[0-9a-f]{64}$")
    ground_truth_status: GroundTruthStatus
    capture_enabled: Literal[True]
    curation_identities: CurationEvaluationIdentities
    runtime_prompt_fingerprints: tuple[PromptFingerprint, ...]
    scenes: tuple[CombinedObservation, ...]
    final_active_memory_ids: tuple[str, ...]


@dataclass(repr=False)
class CaptureCurationGroundTruthEvaluator(
    Evaluator[CombinedInput, CombinedResult, dict[str, object]]
):
    """Expose each handler's existing grade without broadening either endpoint."""

    ground_truth_status: GroundTruthStatus

    def evaluate(
        self, ctx: EvaluatorContext[CombinedInput, CombinedResult, dict[str, object]]
    ) -> str:
        expected, output = ctx.expected_output, ctx.output
        if not (
            isinstance(expected, CaptureEvaluationExpected)
            and isinstance(output, CaptureEvaluationOutput)
            or isinstance(expected, CurationEvaluationExpected)
            and isinstance(output, CurationEvaluationOutput)
        ):
            raise TypeError("combined evaluation output does not match its Objective")
        result = _ground_truth_result(
            matches=not output.hard_failures,
            ground_truth_status=self.ground_truth_status,
        )
        if output.ground_truth_result != result:
            raise ValueError("combined Ground truth result is inconsistent")
        return result

    def get_default_evaluation_name(self) -> str:
        return (
            "adopted_hard_gate_grade"
            if self.ground_truth_status == "adopted"
            else "proposal_comparison"
        )


async def replay_capture_curation_scenes(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    *,
    adoption: GroundTruthAdoption | None = None,
    chat_handler: ChatTurnHandler | None = None,
    curation_handler: CurationHandler | None = None,
    configured_model: str | None = None,
) -> CaptureCurationEvaluationRun:
    """Run a validated Scenario without projecting or rewriting its source files.

    Capture Scenes share one temporary account store across fresh conversations.
    Curation Scenes inspect only their designated immutable Props under the same
    account; curation Scenes use the reviewed ``run_curation_loop`` endpoint.
    An injected ``configured_model`` labels the shared model used by both
    injected handlers.
    """

    if len(backstory.objective_ids) != 2 or set(backstory.objective_ids) != set(OBJECTIVE_IDS):
        raise ValueError(
            "combined replay requires reviewed_automatic_memory_capture "
            "and bounded_memory_curation"
        )
    if backstory.offline_inputs or backstory.source_setups:
        raise ValueError("combined replay accepts capture Lines and curation Props only")
    if configured_model is not None and (chat_handler is None or curation_handler is None):
        raise ValueError("configured_model requires both injected evaluation handlers")

    status: GroundTruthStatus = (
        adoption.ground_truth_status
        if adoption is not None
        else ground_truth.ground_truth_status
    )
    dataset_version = (
        adoption.adopted_ground_truth_identity
        if adoption is not None
        else ground_truth.backstory_sha256
    )
    run_id = uuid4().hex
    account = AccountContext(
        f"synthetic-eval:{backstory.backstory.evaluation_account_id}:{run_id}"
    )
    cases: list[Case[CombinedInput, CombinedResult, dict[str, object]]] = []
    curation_batches: dict[str, AccountScopedMemories] = {}
    for scene in sorted(backstory.scenes, key=lambda item: item.order):
        inputs: CombinedInput
        expected: CombinedExpected
        if scene.objective_ids == (CAPTURE_OBJECTIVE_ID,):
            inputs = capture_scene_input(backstory, scene)
            expected = capture_scene_expectation(inputs, ground_truth, status)
        elif scene.objective_ids == (CURATION_OBJECTIVE_ID,):
            _, batch, expectation = curation_scene_input(
                backstory, ground_truth, scene, account_scope=account.account_id
            )
            curation_batches[scene.scene_id] = batch
            inputs = CurationEvaluationInput(
                order=scene.order, scene_id=scene.scene_id, memories=batch.memories
            )
            expected = CurationEvaluationExpected(
                curation=expectation, ground_truth_status=status
            )
        else:
            raise ValueError(
                f"Scene {scene.scene_id} must select exactly one capture or curation Objective"
            )
        cases.append(
            Case(
                name=scene.scene_id,
                inputs=inputs,
                expected_output=expected,
                metadata={
                    "objective_id": scene.objective_ids[0],
                    "scene_order": scene.order,
                    "ground_truth_status": status,
                },
            )
        )

    if chat_handler is None or curation_handler is None:
        configure_synthetic_evaluation_telemetry(evaluation_agents())
    chat = chat_handler or _production_chat_turn_handler()
    identities = build_curation_identities(configured_model=configured_model)
    observations: list[CombinedObservation] = []
    with tempfile.TemporaryDirectory(prefix="linger-synthetic-eval-") as directory:
        service = MemoryPolicyService(Path(directory))
        service.set_capture_enabled(account, True)

        async def evaluate_scene(inputs: CombinedInput) -> CombinedOutput:
            if inputs.order != len(observations) + 1:
                raise RuntimeError("synthetic evaluation cases did not execute in Scene order")
            case = cases[inputs.order - 1]
            if inputs.scene_id != case.name:
                raise RuntimeError("synthetic evaluation Scene identity changed")
            expected = case.expected_output
            if isinstance(inputs, CaptureEvaluationInput) and isinstance(
                expected, CaptureEvaluationExpected
            ):
                capture = await replay_capture_scene(
                    inputs,
                    expected,
                    run_id=run_id,
                    handler=chat,
                    service=service,
                    account=account,
                )
                observations.append(capture)
                return CaptureEvaluationOutput(
                    actual_capture_label=capture.actual_capture_label,
                    ground_truth_result=capture.ground_truth_result,
                    hard_failures=capture.hard_failures,
                    reply=capture.reply,
                    release_source=capture.release_source,
                    capture=capture.capture,
                )
            if isinstance(inputs, CurationEvaluationInput) and isinstance(
                expected, CurationEvaluationExpected
            ):
                curation = await replay_curation_scene(
                    inputs.scene_id,
                    curation_batches[inputs.scene_id],
                    expected.curation,
                    handler=curation_handler,
                    ground_truth_status=status,
                    use_production_provenance=curation_handler is None,
                )
                observations.append(curation)
                return CurationEvaluationOutput(
                    response=curation.response,
                    ground_truth_result=curation.ground_truth_result,
                    hard_failures=curation.grade.failures,
                    semantic_review_required=curation.grade.semantic_review_required,
                    semantic_criteria=curation.grade.semantic_criteria,
                    forbidden_semantic_claims=curation.grade.forbidden_semantic_claims,
                    source_immutable=True,
                )
            raise TypeError("synthetic Scene expectation does not match its input")

        dataset = Dataset(
            name=EVALUATION_NAME,
            cases=cases,
            evaluators=[CaptureCurationGroundTruthEvaluator(ground_truth_status=status)],
        )
        report = await dataset.evaluate(
            evaluate_scene,
            name=f"{EVALUATION_NAME}-{run_id[:8]}",
            task_name="capture_and_bounded_curation_workflow",
            max_concurrency=1,
            progress=False,
            metadata={
                "content_classification": "synthetic",
                "objective_ids": backstory.objective_ids,
                "run_id": run_id,
                "dataset_version": dataset_version,
                "system_variant": RUNTIME_SYSTEM_VARIANT,
                "full_deployment_identity": identities.full_deployment.digest,
                "curation_objective_execution_identity": identities.objective_execution.digest,
                "ground_truth_status": status,
                "ground_truth_evaluation": dataset.evaluators[0].get_default_evaluation_name(),
            },
        )
        emit_evaluation_link(report, dataset_name=dataset.name)
        if report.failures:
            failed_cases = [failure.name for failure in report.failures]
            raise RuntimeError(f"synthetic evaluation cases failed: {failed_cases}")
        if len(observations) != len(cases):
            raise RuntimeError("synthetic evaluation did not produce every Scene")
        active_ids = tuple(record.memory_id for record in service.list_active(account))

    return CaptureCurationEvaluationRun(
        run_id=run_id,
        trace_id=report.trace_id or "0" * 32,
        objective_ids=(backstory.objective_ids[0], backstory.objective_ids[1]),
        backstory_sha256=ground_truth.backstory_sha256,
        proposed_ground_truth_sha256=adoption.proposed_ground_truth_sha256 if adoption else None,
        dataset_version=dataset_version,
        system_variant=RUNTIME_SYSTEM_VARIANT,
        ground_truth_status=status,
        capture_enabled=True,
        curation_identities=identities,
        runtime_prompt_fingerprints=RUNTIME_PROMPT_FINGERPRINTS,
        scenes=tuple(observations),
        final_active_memory_ids=active_ids,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backstory", type=Path)
    parser.add_argument("ground_truth", type=Path)
    parser.add_argument("--adoption", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.adoption is None:
            backstory, ground_truth = validate_scenario_files(args.backstory, args.ground_truth)
            adoption = None
        else:
            backstory, ground_truth, adoption = validate_ground_truth_adoption_files(
                args.backstory, args.ground_truth, args.adoption
            )
        result = asyncio.run(
            replay_capture_curation_scenes(backstory, ground_truth, adoption=adoption)
        )
        rendered = result.model_dump_json(indent=2) + "\n"
        if args.output is None:
            print(rendered, end="")
        else:
            args.output.write_text(rendered, encoding="utf-8")
    except (
        OSError,
        GroundTruthAdoptionError,
        ScenarioValidationError,
        RuntimeError,
        ValueError,
    ) as error:
        print(f"EVALUATION_RUN_ERROR={error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
