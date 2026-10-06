"""Replay bounded curation and cross-source connection Scenes in one evaluation."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from apps.backend.telemetry import configure_synthetic_evaluation_telemetry
from src.linger.agents.contracts import PromptFingerprint
from src.linger.services.memory import AccountContext, MemoryPolicyService

from .adoption import validate_ground_truth_adoption, validate_ground_truth_adoption_files
from .connection_contract import CONNECTION_CURATION_OBJECTIVE_IDS, compile_connection_replay_plan
from .connection_replay import ConnectionChatHandler, ConnectionSceneObservation, replay_connection_scene
from .curation_replay import (
    CURATION_OBJECTIVE_ID, CurationEvaluationIdentities, CurationHandler,
    CurationSceneObservation, build_curation_identities, curation_scene_input,
    replay_curation_scene,
)
from .evaluation_link import emit_evaluation_link
from .models import GroundTruthAdoption, ProposedGroundTruth, StrictModel, SyntheticBackstory
from .replay import RUNTIME_PROMPT_FINGERPRINTS, RUNTIME_SYSTEM_VARIANT, evaluation_agents
from .validate_scenario import validate_scenario

EVALUATION_NAME = "bounded_curation_and_cross_source_connection"


class SceneExecutionError(StrictModel):
    code: Literal["scene_execution_failed"] = "scene_execution_failed"
    error_type: str


class FailedSceneObservation(StrictModel):
    scene_id: str
    objective_id: str
    execution_error: SceneExecutionError
    hard_gate_pass: Literal[False] = False
    hard_failures: tuple[Literal["execution_failure"], ...] = ("execution_failure",)
    ground_truth_result: Literal["fails_hard_gates"] = "fails_hard_gates"


CombinedObservation = CurationSceneObservation | ConnectionSceneObservation | FailedSceneObservation


class ConnectionCurationEvaluationRun(StrictModel):
    """One run retaining the complete Scenario's adopted identity and Scene order."""

    artifact_schema_version: Literal["1"] = "1"
    public_source_mode: Literal["adopted_snapshot", "injected"]
    content_classification: Literal["synthetic"] = "synthetic"
    ground_truth_status: Literal["adopted"] = "adopted"
    run_id: str
    objective_ids: tuple[str, ...]
    backstory_sha256: str
    proposed_ground_truth_sha256: str
    dataset_version: str
    system_variant: str
    curation_identities: CurationEvaluationIdentities
    runtime_prompt_fingerprints: tuple[PromptFingerprint, ...]
    selected_scene_ids: tuple[str, ...] = ()
    scenes: tuple[CombinedObservation, ...]


class AdoptedConnectionCurationEvaluator(Evaluator[str, CombinedObservation, dict]):
    def evaluate(self, ctx: EvaluatorContext[str, CombinedObservation, dict]) -> bool:
        if isinstance(ctx.output, CurationSceneObservation):
            return ctx.output.grade.hard_pass
        return ctx.output.hard_gate_pass

    def get_default_evaluation_name(self) -> str:
        return "adopted_hard_gate_grade"


async def replay_connection_curation_scenes(
    backstory: SyntheticBackstory, ground_truth: ProposedGroundTruth, *,
    adoption: GroundTruthAdoption, ground_truth_bytes: bytes, backstory_bytes: bytes,
    chat_handler: ConnectionChatHandler | None = None,
    curation_handler: CurationHandler | None = None,
    configured_model: str | None = None,
    scene_ids: Sequence[str] | None = None,
) -> ConnectionCurationEvaluationRun:
    """Dispatch each Scene under one account, with independent source snapshots.

    Production curation passes no injected handler so the application invokes
    both Sculptor and Provenance. The adopted expectations stay evaluator-only.
    """
    if set(backstory.objective_ids) != CONNECTION_CURATION_OBJECTIVE_IDS:
        raise ValueError("combined replay requires bounded_memory_curation and cross_source_tentative_connection")
    if backstory.run_configuration_ids or backstory.offline_inputs:
        raise ValueError("combined replay accepts curation Props and connection Lines only")
    if configured_model is not None and (chat_handler is None or curation_handler is None):
        raise ValueError("configured_model requires both injected evaluation handlers")
    if (ProposedGroundTruth.model_validate_json(ground_truth_bytes) != ground_truth
        or SyntheticBackstory.model_validate_json(backstory_bytes) != backstory):
        raise ValueError("replay objects do not match the independently adopted scenario bytes")
    validate_ground_truth_adoption(ground_truth, adoption, ground_truth_bytes=ground_truth_bytes)
    validate_scenario(backstory, ground_truth, backstory_bytes=backstory_bytes, run_configurations={})
    plan = compile_connection_replay_plan(backstory, ground_truth)
    connections = {item.scene.scene_id: item for item in plan.scenes}
    ordered = sorted(backstory.scenes, key=lambda item: item.order)
    all_scenes = tuple(ordered)
    if scene_ids is not None:
        requested = set(scene_ids)
        if not requested or len(requested) != len(scene_ids):
            raise ValueError("Scene selection must be non-empty and contain no duplicates")
        unknown = requested - {scene.scene_id for scene in ordered}
        if unknown:
            raise ValueError(f"Unknown Scenes: {', '.join(sorted(unknown))}")
        ordered = [scene for scene in ordered if scene.scene_id in requested]
    selected_scene_ids = tuple(scene.scene_id for scene in ordered)
    by_id = {scene.scene_id: scene for scene in ordered}
    run_id = uuid4().hex
    account = AccountContext(f"synthetic-eval:{backstory.backstory.evaluation_account_id}:{run_id}")
    curations = {
        scene.scene_id: curation_scene_input(backstory, ground_truth, scene, account_scope=account.account_id)
        for scene in all_scenes if scene.objective_ids == (CURATION_OBJECTIVE_ID,)
    }
    production_chat = chat_handler is None
    if production_chat or curation_handler is None:
        configure_synthetic_evaluation_telemetry(evaluation_agents())
    if chat_handler is None:
        from apps.backend.chat_turn import run_chat_turn
        chat_handler = run_chat_turn
    handler = chat_handler
    identities = build_curation_identities(configured_model=configured_model)
    observations: list[CombinedObservation] = []
    with tempfile.TemporaryDirectory(prefix="linger-connection-curation-eval-") as directory:
        async def execute(scene_id: str) -> CombinedObservation:
            scene = by_id[scene_id]
            if scene_id != selected_scene_ids[len(observations)]:
                raise RuntimeError("combined evaluation Scenes executed out of order")
            observation: CombinedObservation
            try:
                if scene_id in curations:
                    _, batch, expectation = curations[scene_id]
                    observation = await replay_curation_scene(
                        scene_id, batch, expectation, handler=curation_handler,
                        ground_truth_status="adopted",
                    )
                else:
                    service = MemoryPolicyService(Path(directory) / str(scene.order))
                    observation = await replay_connection_scene(
                        connections[scene_id], run_id=run_id, handler=handler,
                        service=service, account=account,
                    )
            except Exception as error:
                # Preserve all independent cases without copying provider error
                # messages, which may contain request content or credentials.
                observation = FailedSceneObservation(
                    scene_id=scene_id, objective_id=scene.objective_ids[0],
                    execution_error=SceneExecutionError(error_type=type(error).__name__),
                )
            observations.append(observation)
            return observation

        dataset = Dataset(
            name=EVALUATION_NAME,
            cases=[Case(name=scene.scene_id, inputs=scene.scene_id, metadata={
                "objective_id": scene.objective_ids[0], "scene_order": scene.order,
            }) for scene in ordered],
            evaluators=[AdoptedConnectionCurationEvaluator()],
        )
        report = await dataset.evaluate(
            execute, name=f"connection-curation-{run_id[:8]}",
            task_name=EVALUATION_NAME, max_concurrency=1, progress=False,
            metadata={
                "content_classification": "synthetic", "run_id": run_id,
                "objective_ids": list(backstory.objective_ids),
                "backstory_sha256": ground_truth.backstory_sha256,
                "dataset_version": adoption.adopted_ground_truth_identity,
                "selected_scene_ids": list(selected_scene_ids),
                "scenario_scene_count": len(all_scenes),
            },
        )
        emit_evaluation_link(report, dataset_name=dataset.name)
        if report.failures or len(observations) != len(ordered):
            raise RuntimeError("combined evaluation did not complete every Scene")
    return ConnectionCurationEvaluationRun(
        public_source_mode="adopted_snapshot" if production_chat else "injected",
        run_id=run_id, objective_ids=backstory.objective_ids,
        backstory_sha256=ground_truth.backstory_sha256,
        proposed_ground_truth_sha256=hashlib.sha256(ground_truth_bytes).hexdigest(),
        dataset_version=adoption.adopted_ground_truth_identity,
        system_variant=RUNTIME_SYSTEM_VARIANT, curation_identities=identities,
        runtime_prompt_fingerprints=RUNTIME_PROMPT_FINGERPRINTS,
        selected_scene_ids=selected_scene_ids,
        scenes=tuple(observations),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backstory", type=Path)
    parser.add_argument("ground_truth", type=Path)
    parser.add_argument("--adoption", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenes", nargs="+", help="Scene IDs to execute in original Scenario order")
    args = parser.parse_args(argv)
    backstory, truth, adoption = validate_ground_truth_adoption_files(args.backstory, args.ground_truth, args.adoption)
    run = asyncio.run(replay_connection_curation_scenes(
        backstory, truth, adoption=adoption,
        ground_truth_bytes=args.ground_truth.read_bytes(), backstory_bytes=args.backstory.read_bytes(),
        scene_ids=args.scenes,
    ))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(run.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"CONNECTION_CURATION_REPLAY_OUTPUT={args.output}")
    return 1 if any(isinstance(scene, FailedSceneObservation) for scene in run.scenes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
