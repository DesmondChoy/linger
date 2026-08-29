"""Replay bounded-curation Props through Linger's production Sculptor boundary."""

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
from evals.sculptor.harness import (
    CurationExpectation,
    GradeResult,
    grade_curation_expectation,
)
from src.linger.agents.contracts import PromptFingerprint
from src.linger.agents.sculptor.models import (
    AccountScopedMemories,
    CuratableMemory,
    SculptorResponse,
)
from src.linger.agents.sculptor.prompt import (
    PROMPT_FINGERPRINT as SCULPTOR_PROMPT_FINGERPRINT,
)
from src.linger.evaluation_transcript import bind_evaluation_transcript_sink
from src.linger.orchestration.curation import propose_curation

from .adoption import (
    GroundTruthAdoptionError,
    validate_ground_truth_adoption_files,
)
from .models import (
    GroundTruthAdoption,
    ProposedGroundTruth,
    StrictModel,
    SyntheticBackstory,
)
from .replay import (
    GroundTruthResult,
    GroundTruthStatus,
    RUNTIME_PROMPT_FINGERPRINTS,
    _ground_truth_result,
    evaluation_agents,
)
from .transcript import AgentExchange, SceneTranscriptRecorder
from .validate_package import PackageValidationError, validate_package_files

CURATION_OBJECTIVE_ID = "bounded_memory_curation"
OBJECTIVE_COMPONENTS = (
    "src.linger.agents.sculptor.models.AccountScopedMemories",
    "src.linger.agents.sculptor.models.SculptorResponse",
    "evals.sculptor.harness.CurationExpectation",
    "evals.sculptor.harness.grade_curation_expectation:v1",
)

CurationHandler = Callable[[AccountScopedMemories], Awaitable[SculptorResponse]]


class EvaluationIdentity(StrictModel):
    """Content-derived identity with one documented comparison purpose."""

    purpose: Literal["full_deployment_lineage", "objective_execution_comparison"]
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    configured_model: str
    prompt_fingerprints: tuple[PromptFingerprint, ...]
    component_contracts: tuple[str, ...]


class CurationEvaluationIdentities(StrictModel):
    full_deployment: EvaluationIdentity
    objective_execution: EvaluationIdentity


class SourceHash(StrictModel):
    memory_id: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CurationSceneObservation(StrictModel):
    """Complete durable observation for one bounded Sculptor call."""

    scene_id: str
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    input_memories: tuple[CuratableMemory, ...]
    expected: CurationExpectation
    response: SculptorResponse
    ground_truth_result: GroundTruthResult
    grade: GradeResult
    source_hashes_before: tuple[SourceHash, ...]
    source_hashes_after: tuple[SourceHash, ...]
    source_immutable: Literal[True]
    agent_exchanges: tuple[AgentExchange, ...]


class CurationEvaluationRun(StrictModel):
    """One provider-backed run of ordered bounded-curation Scenes."""

    artifact_schema_version: Literal["1"] = "1"
    content_classification: Literal["synthetic"] = "synthetic"
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    objective_id: Literal["bounded_memory_curation"]
    dataset_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    ground_truth_status: GroundTruthStatus
    identities: CurationEvaluationIdentities
    runtime_prompt_fingerprints: tuple[PromptFingerprint, ...]
    scenes: tuple[CurationSceneObservation, ...]


class CurationEvaluationInput(StrictModel):
    order: int = Field(ge=1)
    scene_id: str
    memories: tuple[CuratableMemory, ...]


class CurationEvaluationExpected(StrictModel):
    curation: CurationExpectation
    ground_truth_status: GroundTruthStatus


class CurationEvaluationOutput(StrictModel):
    response: SculptorResponse
    ground_truth_result: GroundTruthResult
    hard_failures: tuple[str, ...]
    semantic_review_required: bool
    semantic_criteria: tuple[str, ...]
    forbidden_semantic_claims: tuple[str, ...]
    source_immutable: Literal[True]


CurationEvaluationResult = CurationEvaluationExpected | CurationEvaluationOutput


@dataclass(repr=False)
class CurationGroundTruthEvaluator(
    Evaluator[
        CurationEvaluationInput,
        CurationEvaluationResult,
        dict[str, object],
    ]
):
    """Compare a proposal or grade adopted bounded-curation hard gates."""

    ground_truth_status: GroundTruthStatus

    def evaluate(
        self,
        ctx: EvaluatorContext[
            CurationEvaluationInput,
            CurationEvaluationResult,
            dict[str, object],
        ],
    ) -> str:
        output = ctx.output
        if not isinstance(output, CurationEvaluationOutput):
            raise TypeError("curation evaluation task returned the wrong output")
        ground_truth_result = _ground_truth_result(
            matches=not output.hard_failures,
            ground_truth_status=self.ground_truth_status,
        )
        if output.ground_truth_result != ground_truth_result:
            raise ValueError("curation Ground truth result is inconsistent")
        return ground_truth_result

    def get_default_evaluation_name(self) -> str:
        if self.ground_truth_status == "adopted":
            return "adopted_hard_gate_grade"
        return "proposal_comparison"


def build_curation_identities(
    *,
    configured_model: str | None = None,
    full_prompt_fingerprints: tuple[PromptFingerprint, ...] | None = None,
    objective_prompt_fingerprints: tuple[PromptFingerprint, ...] | None = None,
) -> CurationEvaluationIdentities:
    """Build lineage and comparison identities with distinct prompt scopes."""

    model = configured_model or get_settings().linger_model
    full_prompts = full_prompt_fingerprints or RUNTIME_PROMPT_FINGERPRINTS
    objective_prompts = objective_prompt_fingerprints or (
        SCULPTOR_PROMPT_FINGERPRINT,
    )
    return CurationEvaluationIdentities(
        full_deployment=_identity(
            purpose="full_deployment_lineage",
            configured_model=model,
            prompt_fingerprints=full_prompts,
            component_contracts=(),
        ),
        objective_execution=_identity(
            purpose="objective_execution_comparison",
            configured_model=model,
            prompt_fingerprints=objective_prompts,
            component_contracts=OBJECTIVE_COMPONENTS,
        ),
    )


def _identity(
    *,
    purpose: Literal[
        "full_deployment_lineage", "objective_execution_comparison"
    ],
    configured_model: str,
    prompt_fingerprints: tuple[PromptFingerprint, ...],
    component_contracts: tuple[str, ...],
) -> EvaluationIdentity:
    document = {
        "purpose": purpose,
        "configured_model": configured_model,
        "prompt_fingerprints": [
            item.model_dump(mode="json") for item in prompt_fingerprints
        ],
        "component_contracts": component_contracts,
    }
    digest = hashlib.sha256(
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return EvaluationIdentity(
        purpose=purpose,
        digest=digest,
        configured_model=configured_model,
        prompt_fingerprints=prompt_fingerprints,
        component_contracts=component_contracts,
    )


async def replay_curation_scenes(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    *,
    adoption: GroundTruthAdoption | None = None,
    curation_handler: CurationHandler | None = None,
    configured_model: str | None = None,
) -> CurationEvaluationRun:
    """Run validated synthetic Props through production ``propose_curation``."""

    scene_inputs = _curation_scene_inputs(backstory, ground_truth)
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
    if curation_handler is None:
        if configured_model is not None:
            raise ValueError(
                "configured_model may only label an injected evaluation handler"
            )
        handler = propose_curation
        configure_synthetic_evaluation_telemetry(evaluation_agents())
    else:
        handler = curation_handler

    run_id = uuid4().hex
    identities = build_curation_identities(configured_model=configured_model)
    cases: list[
        Case[
            CurationEvaluationInput,
            CurationEvaluationResult,
            dict[str, object],
        ]
    ] = []
    for order, (scene_id, batch, expectation) in enumerate(scene_inputs, start=1):
        cases.append(
            Case(
                name=scene_id,
                inputs=CurationEvaluationInput(
                    order=order,
                    scene_id=scene_id,
                    memories=batch.memories,
                ),
                expected_output=CurationEvaluationExpected(
                    curation=expectation,
                    ground_truth_status=ground_truth_status,
                ),
                metadata={
                    "objective_id": CURATION_OBJECTIVE_ID,
                    "scene_order": order,
                    "ground_truth_status": ground_truth_status,
                },
            )
        )

    observations: list[CurationSceneObservation] = []

    async def evaluate_scene(
        inputs: CurationEvaluationInput,
    ) -> CurationEvaluationOutput:
        expected_order = len(observations) + 1
        if inputs.order != expected_order:
            raise RuntimeError(
                "synthetic evaluation cases did not execute in Scene order"
            )
        scene_id, batch, expectation = scene_inputs[inputs.order - 1]
        if scene_id != inputs.scene_id:
            raise RuntimeError("synthetic curation Scene identity changed")
        observation = await _replay_curation_scene(
            scene_id,
            batch,
            expectation,
            handler=handler,
            ground_truth_status=ground_truth_status,
        )
        observations.append(observation)
        return CurationEvaluationOutput(
            response=observation.response,
            ground_truth_result=observation.ground_truth_result,
            hard_failures=observation.grade.failures,
            semantic_review_required=observation.grade.semantic_review_required,
            semantic_criteria=observation.grade.semantic_criteria,
            forbidden_semantic_claims=observation.grade.forbidden_semantic_claims,
            source_immutable=True,
        )

    dataset = Dataset(
        name=CURATION_OBJECTIVE_ID,
        cases=cases,
        evaluators=[
            CurationGroundTruthEvaluator(
                ground_truth_status=ground_truth_status
            )
        ],
    )
    report = await dataset.evaluate(
        evaluate_scene,
        name=f"{CURATION_OBJECTIVE_ID}-{run_id[:8]}",
        task_name="bounded_memory_curation_workflow",
        max_concurrency=1,
        progress=False,
        metadata={
            "content_classification": "synthetic",
            "objective_id": CURATION_OBJECTIVE_ID,
            "run_id": run_id,
            "dataset_version": dataset_version,
            "full_deployment_identity": identities.full_deployment.digest,
            "objective_execution_identity": identities.objective_execution.digest,
            "ground_truth_status": ground_truth_status,
            "ground_truth_evaluation": evaluation_name,
        },
    )
    if report.failures:
        failed_cases = [failure.name for failure in report.failures]
        raise RuntimeError(f"synthetic curation cases failed: {failed_cases}")
    if len(observations) != len(cases):
        raise RuntimeError("synthetic curation evaluation missed a Scene")

    return CurationEvaluationRun(
        run_id=run_id,
        trace_id=report.trace_id or "0" * 32,
        objective_id=CURATION_OBJECTIVE_ID,
        dataset_version=dataset_version,
        ground_truth_status=ground_truth_status,
        identities=identities,
        runtime_prompt_fingerprints=RUNTIME_PROMPT_FINGERPRINTS,
        scenes=tuple(observations),
    )


async def _replay_curation_scene(
    scene_id: str,
    batch: AccountScopedMemories,
    expectation: CurationExpectation,
    *,
    handler: CurationHandler,
    ground_truth_status: GroundTruthStatus,
) -> CurationSceneObservation:
    recorder = SceneTranscriptRecorder()
    before = _source_hashes(batch)
    with bind_evaluation_transcript_sink(recorder):
        response = await handler(batch)
    after = _source_hashes(batch)
    if after != before:
        raise RuntimeError(f"Scene {scene_id} changed supplied source content")

    grade = grade_curation_expectation(
        expectation,
        tuple(memory.memory_id for memory in batch.memories),
        response,
    )
    ground_truth_result = _ground_truth_result(
        matches=grade.hard_pass,
        ground_truth_status=ground_truth_status,
    )
    set_eval_attribute("ground_truth_result", ground_truth_result)
    set_eval_attribute("response_kind", response.kind)
    set_eval_attribute("source_immutable", True)
    trace_id = format_trace_id(get_current_span().get_span_context().trace_id)
    return CurationSceneObservation(
        scene_id=scene_id,
        trace_id=trace_id,
        input_memories=batch.memories,
        expected=expectation,
        response=response,
        ground_truth_result=ground_truth_result,
        grade=grade,
        source_hashes_before=before,
        source_hashes_after=after,
        source_immutable=True,
        agent_exchanges=recorder.exchanges,
    )


def _source_hashes(batch: AccountScopedMemories) -> tuple[SourceHash, ...]:
    return tuple(
        SourceHash(
            memory_id=memory.memory_id,
            sha256=hashlib.sha256(memory.text.encode("utf-8")).hexdigest(),
        )
        for memory in batch.memories
    )


def _curation_scene_inputs(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
) -> tuple[tuple[str, AccountScopedMemories, CurationExpectation], ...]:
    if backstory.objective_ids != (CURATION_OBJECTIVE_ID,):
        raise ValueError("curation replay requires only bounded_memory_curation")
    if backstory.run_configuration_ids:
        raise ValueError("bounded curation replay accepts no run configuration")
    if backstory.lines or backstory.offline_inputs:
        raise ValueError("bounded curation replay accepts Props only")

    props = {prop.prop_id: prop for prop in backstory.props}
    proposals = {
        proposal.scene_id: proposal for proposal in ground_truth.proposals
    }
    inputs = []
    for scene in sorted(backstory.scenes, key=lambda item: item.order):
        if scene.objective_ids != (CURATION_OBJECTIVE_ID,):
            raise ValueError(
                f"Scene {scene.scene_id} must select only bounded_memory_curation"
            )
        if not scene.fresh_session:
            raise ValueError(f"Scene {scene.scene_id} must be isolated")
        if scene.line_ids or scene.offline_input_ids:
            raise ValueError(f"Scene {scene.scene_id} accepts Props only")
        if not 2 <= len(scene.prop_ids) <= 12:
            raise ValueError(f"Scene {scene.scene_id} requires 2-12 Props")

        memories = []
        for prop_id in scene.prop_ids:
            prop = props[prop_id]
            lifecycle = next(
                item for item in prop.lifecycle if item.scene_id == scene.scene_id
            )
            if lifecycle.state != "active":
                raise ValueError(
                    f"Scene {scene.scene_id} Prop {prop_id} is not active"
                )
            memories.append(
                CuratableMemory(memory_id=prop.prop_id, text=prop.source_text)
            )

        proposal = proposals.get(scene.scene_id)
        if proposal is None or proposal.curation is None:
            raise ValueError(
                f"Scene {scene.scene_id} lacks typed curation Ground truth"
            )
        inputs.append(
            (
                scene.scene_id,
                AccountScopedMemories(
                    account_scope=backstory.backstory.evaluation_account_id,
                    memories=tuple(memories),
                ),
                proposal.curation,
            )
        )
    return tuple(inputs)


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
            replay_curation_scenes(
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
