"""Replay longitudinal-retrieval Scenes, alone or with session-continuity Scenes."""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

from opentelemetry.trace import format_trace_id, get_current_span
from pydantic import Field
from pydantic_evals import Case, Dataset
from pydantic_evals.dataset import set_eval_attribute
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from apps.backend import sessions
from apps.backend.schemas import ChatRequest
from apps.backend.telemetry import configure_synthetic_evaluation_telemetry
from src.linger.agents.contracts import PromptFingerprint
from src.linger.evaluation_transcript import (
    ConnectionEvaluationEvent,
    bind_evaluation_transcript_sink,
)
from src.linger.services.memory import (
    AccountContext,
    AutomaticMemoryCandidate,
    MemoryPolicyService,
)

from .adoption import GroundTruthAdoptionError, validate_ground_truth_adoption_files
from .connection_replay import _evidence_ledger, lookup_failures
from .continuity_replay import (
    CONTINUITY_OBJECTIVE_ID,
    ContinuityEvaluationExpected,
    ContinuityEvaluationInput,
    ContinuityEvaluationOutput,
    ContinuitySceneObservation,
    _ContinuityScene,
    _continuity_scenes_from,
    _replay_continuity_scene,
    _session_boundary_held,
)
from .evaluation_link import emit_evaluation_link
from .models import (
    GroundTruthAdoption,
    Prop,
    ProposedGroundTruth,
    Scene,
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
from .validate_scenario import ScenarioValidationError, validate_scenario_files

RETRIEVAL_OBJECTIVE_ID = "longitudinal_memory_retrieval"
RETRIEVAL_RUN_CONFIGURATION_ID = "longitudinal-memory-retrieval-10-to-1"
EVALUATION_NAME = "longitudinal_memory_retrieval"
NORMAL_RELEASE_SOURCE = "muse_candidate"

SceneRole = Literal["target", "comparison"]
RetrievalGroundTruthResult = GroundTruthResult | Literal["not_applicable"]


class RetrievalEvaluationInput(StrictModel):
    """One retrieval Scene's single Line shown as a native evaluation input."""

    order: int = Field(ge=1)
    scene_id: str
    line_id: str
    line: str


class RetrievalEvaluationExpected(StrictModel):
    """Proposed Prop relevance kept outside every production input."""

    role: SceneRole
    relevant_prop_ids: tuple[str, ...]
    distractor_prop_ids: tuple[str, ...]
    ground_truth_status: GroundTruthStatus


class RetrievalEvaluationOutput(StrictModel):
    """Compact retrieval result displayed by Logfire's Evals UI."""

    role: SceneRole
    ground_truth_result: RetrievalGroundTruthResult
    hard_failures: tuple[str, ...]
    retrieved_prop_ids: tuple[str, ...]
    cited_prop_ids: tuple[str, ...]
    uncited_retrieved_distractor_prop_ids: tuple[str, ...]
    release_source: str
    reply: str
    semantic_review_required: Literal[True] = True


class RetrievalSceneObservation(StrictModel):
    """Complete durable observation for one retrieval Scene and its Line."""

    scene_id: str
    line_id: str
    input_line: str
    role: SceneRole
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    relevant_prop_ids: tuple[str, ...]
    distractor_prop_ids: tuple[str, ...]
    retrieved_prop_ids: tuple[str, ...]
    cited_prop_ids: tuple[str, ...]
    uncited_retrieved_distractor_prop_ids: tuple[str, ...]
    release_source: str
    reply: str
    hard_failures: tuple[str, ...]
    ground_truth_result: RetrievalGroundTruthResult
    events: tuple[ConnectionEvaluationEvent, ...]
    agent_exchanges: tuple[AgentExchange, ...]
    semantic_review_required: Literal[True] = True


CombinedInput = ContinuityEvaluationInput | RetrievalEvaluationInput
CombinedExpected = ContinuityEvaluationExpected | RetrievalEvaluationExpected
CombinedOutput = ContinuityEvaluationOutput | RetrievalEvaluationOutput
CombinedResult = CombinedExpected | CombinedOutput
CombinedObservation = ContinuitySceneObservation | RetrievalSceneObservation


class RetrievalEvaluationRun(StrictModel):
    """One isolated run of ordered retrieval and optional continuity Scenes."""

    artifact_schema_version: Literal["1"] = "1"
    content_classification: Literal["synthetic"] = "synthetic"
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    objective_ids: tuple[str, ...]
    backstory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposed_ground_truth_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    dataset_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    system_variant: str = Field(pattern=r"^[0-9a-f]{64}$")
    ground_truth_status: GroundTruthStatus
    capture_enabled: Literal[False] = False
    runtime_prompt_fingerprints: tuple[PromptFingerprint, ...]
    scenes: tuple[CombinedObservation, ...]


@dataclass(repr=False)
class RetrievalGroundTruthEvaluator(
    Evaluator[CombinedInput, CombinedResult, dict[str, object]]
):
    """Expose each Scene's own grade without broadening either Objective."""

    ground_truth_status: GroundTruthStatus

    def evaluate(
        self, ctx: EvaluatorContext[CombinedInput, CombinedResult, dict[str, object]]
    ) -> str:
        output = ctx.output
        if isinstance(output, ContinuityEvaluationOutput):
            result: RetrievalGroundTruthResult = (
                _ground_truth_result(
                    matches=bool(output.session_boundary_held),
                    ground_truth_status=self.ground_truth_status,
                )
                if output.role == "comparison"
                else "not_applicable"
            )
        elif isinstance(output, RetrievalEvaluationOutput):
            result = _ground_truth_result(
                matches=not output.hard_failures,
                ground_truth_status=self.ground_truth_status,
            )
        else:
            raise TypeError("combined evaluation output does not match its Objective")
        if output.ground_truth_result != result:
            raise ValueError("combined Ground truth result is inconsistent")
        return result

    def get_default_evaluation_name(self) -> str:
        return (
            "adopted_hard_gate_grade"
            if self.ground_truth_status == "adopted"
            else "proposal_comparison"
        )


@dataclass(frozen=True)
class _RetrievalScene:
    """One guarded retrieval Scene with its Props and proposed relevance."""

    scene_id: str
    order: int
    line_id: str
    line: str
    role: SceneRole
    props: tuple[Prop, ...]
    relevant_prop_ids: tuple[str, ...]
    distractor_prop_ids: tuple[str, ...]


async def replay_retrieval_scenes(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    *,
    adoption: GroundTruthAdoption | None = None,
    chat_handler: ChatTurnHandler | None = None,
) -> RetrievalEvaluationRun:
    """Run a validated Scenario, dispatching each Scene by its own Objective."""

    selected = set(backstory.objective_ids)
    if selected not in (
        {RETRIEVAL_OBJECTIVE_ID},
        {RETRIEVAL_OBJECTIVE_ID, CONTINUITY_OBJECTIVE_ID},
    ):
        raise ValueError(
            "longitudinal retrieval replay requires longitudinal_memory_retrieval "
            "alone or with session_scoped_conversation_continuity"
        )
    if backstory.offline_inputs or backstory.source_setups:
        raise ValueError("longitudinal retrieval replay accepts Lines and Props only")
    if RETRIEVAL_RUN_CONFIGURATION_ID not in backstory.run_configuration_ids:
        raise ValueError(
            "longitudinal retrieval replay requires the "
            f"{RETRIEVAL_RUN_CONFIGURATION_ID} run configuration"
        )

    ordered = sorted(backstory.scenes, key=lambda item: item.order)
    continuity_scenes = [
        scene for scene in ordered if scene.objective_ids == (CONTINUITY_OBJECTIVE_ID,)
    ]
    retrieval_scenes = {
        scene.scene_id: _retrieval_scene(backstory, ground_truth, scene)
        for scene in ordered
        if scene.objective_ids == (RETRIEVAL_OBJECTIVE_ID,)
    }
    if len(continuity_scenes) + len(retrieval_scenes) != len(ordered):
        raise ValueError(
            "every Scene must select exactly one retrieval or continuity Objective"
        )
    compiled: dict[str, _ContinuityScene] = {}
    if continuity_scenes:
        compiled = {
            scene.scene_id: scene
            for scene in _continuity_scenes_from(
                continuity_scenes, backstory, ground_truth
            )
        }

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
    if chat_handler is None:
        handler = _production_chat_turn_handler()
        configure_synthetic_evaluation_telemetry(evaluation_agents())
    else:
        handler = chat_handler

    run_id = uuid4().hex
    account = AccountContext(
        f"synthetic-eval:{backstory.backstory.evaluation_account_id}:{run_id}"
    )
    cases: list[Case[CombinedInput, CombinedResult, dict[str, object]]] = []
    continuity_by_order: dict[int, _ContinuityScene] = {}
    retrieval_by_order: dict[int, _RetrievalScene] = {}
    for order, scene in enumerate(ordered, start=1):
        inputs: CombinedInput
        expected: CombinedExpected
        if scene.scene_id in compiled:
            continuity = dataclasses.replace(compiled[scene.scene_id], order=order)
            continuity_by_order[order] = continuity
            inputs = ContinuityEvaluationInput(
                order=order,
                scene_id=scene.scene_id,
                role=continuity.role,
                lines=tuple(line.text for line in continuity.lines),
            )
            expected = ContinuityEvaluationExpected(
                role=continuity.role,
                paired_scene_id=continuity.paired_scene_id,
                ground_truth_status=status,
            )
        else:
            retrieval = dataclasses.replace(
                retrieval_scenes[scene.scene_id], order=order
            )
            retrieval_by_order[order] = retrieval
            inputs = RetrievalEvaluationInput(
                order=order,
                scene_id=scene.scene_id,
                line_id=retrieval.line_id,
                line=retrieval.line,
            )
            expected = RetrievalEvaluationExpected(
                role=retrieval.role,
                relevant_prop_ids=retrieval.relevant_prop_ids,
                distractor_prop_ids=retrieval.distractor_prop_ids,
                ground_truth_status=status,
            )
        cases.append(
            Case(
                name=scene.scene_id,
                inputs=inputs,
                expected_output=expected,
                metadata={
                    "objective_id": scene.objective_ids[0],
                    "scene_order": order,
                    "ground_truth_status": status,
                },
            )
        )

    observations: list[CombinedObservation] = []
    with tempfile.TemporaryDirectory(prefix="linger-synthetic-eval-") as directory:
        root = Path(directory)
        continuity_service = MemoryPolicyService(root / "continuity")

        async def evaluate_scene(inputs: CombinedInput) -> CombinedOutput:
            if inputs.order != len(observations) + 1:
                raise RuntimeError(
                    "synthetic evaluation cases did not execute in Scene order"
                )
            case = cases[inputs.order - 1]
            if inputs.scene_id != case.name:
                raise RuntimeError("synthetic evaluation Scene identity changed")
            expected = case.expected_output
            if isinstance(inputs, ContinuityEvaluationInput) and isinstance(
                expected, ContinuityEvaluationExpected
            ):
                continuity = await _replay_continuity_scene(
                    continuity_by_order[inputs.order],
                    expected,
                    run_id=run_id,
                    handler=handler,
                    service=continuity_service,
                    account=account,
                )
                observations.append(continuity)
                return ContinuityEvaluationOutput(
                    role=continuity.role,
                    session_boundary_held=_session_boundary_held(
                        continuity.role,
                        continuity.turns,
                        continuity.session_turn_release_sources,
                    ),
                    ground_truth_result=continuity.ground_truth_result,
                    structural_findings=continuity.structural_findings,
                    session_turn_release_sources=(
                        continuity.session_turn_release_sources
                    ),
                    replies=tuple(turn.reply for turn in continuity.turns),
                )
            if isinstance(inputs, RetrievalEvaluationInput) and isinstance(
                expected, RetrievalEvaluationExpected
            ):
                retrieval = await _replay_retrieval_scene(
                    retrieval_by_order[inputs.order],
                    expected,
                    run_id=run_id,
                    handler=handler,
                    service=MemoryPolicyService(root / f"retrieval-{inputs.order}"),
                    account=account,
                )
                observations.append(retrieval)
                return RetrievalEvaluationOutput(
                    role=retrieval.role,
                    ground_truth_result=retrieval.ground_truth_result,
                    hard_failures=retrieval.hard_failures,
                    retrieved_prop_ids=retrieval.retrieved_prop_ids,
                    cited_prop_ids=retrieval.cited_prop_ids,
                    uncited_retrieved_distractor_prop_ids=(
                        retrieval.uncited_retrieved_distractor_prop_ids
                    ),
                    release_source=retrieval.release_source,
                    reply=retrieval.reply,
                )
            raise TypeError("synthetic Scene expectation does not match its input")

        dataset = Dataset(
            name=EVALUATION_NAME,
            cases=cases,
            evaluators=[RetrievalGroundTruthEvaluator(ground_truth_status=status)],
        )
        report = await dataset.evaluate(
            evaluate_scene,
            name=f"{EVALUATION_NAME}-{run_id[:8]}",
            task_name="longitudinal_memory_retrieval_workflow",
            max_concurrency=1,
            progress=False,
            metadata={
                "content_classification": "synthetic",
                "objective_ids": backstory.objective_ids,
                "run_id": run_id,
                "dataset_version": dataset_version,
                "system_variant": RUNTIME_SYSTEM_VARIANT,
                "ground_truth_status": status,
                "ground_truth_evaluation": dataset.evaluators[
                    0
                ].get_default_evaluation_name(),
            },
        )
        emit_evaluation_link(report, dataset_name=dataset.name)
        if report.failures:
            failed_cases = [failure.name for failure in report.failures]
            raise RuntimeError(f"synthetic evaluation cases failed: {failed_cases}")
        if len(observations) != len(cases):
            raise RuntimeError("synthetic evaluation did not produce every Scene")
        if tuple(continuity_service.list_active(account)):
            raise RuntimeError(
                "continuity replay committed memories while capture was disabled"
            )

    return RetrievalEvaluationRun(
        run_id=run_id,
        trace_id=report.trace_id or "0" * 32,
        objective_ids=backstory.objective_ids,
        backstory_sha256=ground_truth.backstory_sha256,
        proposed_ground_truth_sha256=(
            adoption.proposed_ground_truth_sha256 if adoption else None
        ),
        dataset_version=dataset_version,
        system_variant=RUNTIME_SYSTEM_VARIANT,
        ground_truth_status=status,
        runtime_prompt_fingerprints=RUNTIME_PROMPT_FINGERPRINTS,
        scenes=tuple(observations),
    )


def _retrieval_scene(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    scene: Scene,
) -> _RetrievalScene:
    """Compile one isolated retrieval Scene without passing its labels to chat."""

    if not scene.fresh_session:
        raise ValueError(f"Scene {scene.scene_id} must use a fresh session")
    if scene.offline_input_ids:
        raise ValueError(f"Scene {scene.scene_id} cannot use offline inputs")
    if len(scene.line_ids) != 1:
        raise ValueError(f"Scene {scene.scene_id} must contain exactly one Line")
    props = {prop.prop_id: prop for prop in backstory.props}
    scene_props = tuple(props[prop_id] for prop_id in scene.prop_ids)
    for prop in scene_props:
        state = next(
            item.state for item in prop.lifecycle if item.scene_id == scene.scene_id
        )
        if state != "active":
            raise ValueError(
                f"Scene {scene.scene_id} requires Prop {prop.prop_id} to be active"
            )
    if not scene_props:
        raise ValueError(f"Scene {scene.scene_id} requires at least one active Prop")
    proposals = [
        proposal
        for proposal in ground_truth.proposals
        if proposal.scene_id == scene.scene_id
        and proposal.objective_id == RETRIEVAL_OBJECTIVE_ID
    ]
    if len(proposals) != 1:
        raise ValueError(f"Scene {scene.scene_id} lacks typed retrieval Ground truth")
    relevance = {item.prop_id: item.relevance for item in proposals[0].prop_relevance}
    if set(relevance) != set(scene.prop_ids):
        raise ValueError(
            f"Scene {scene.scene_id} requires one Prop relevance judgment per Prop"
        )
    relevant = tuple(
        prop.prop_id for prop in scene_props if relevance[prop.prop_id] == "relevant"
    )
    lines = {line.line_id: line for line in backstory.lines}
    line = lines[scene.line_ids[0]]
    return _RetrievalScene(
        scene_id=scene.scene_id,
        order=scene.order,
        line_id=line.line_id,
        line=line.text,
        role="target" if relevant else "comparison",
        props=scene_props,
        relevant_prop_ids=relevant,
        distractor_prop_ids=tuple(
            prop.prop_id for prop in scene_props if prop.prop_id not in relevant
        ),
    )


async def _replay_retrieval_scene(
    scene: _RetrievalScene,
    expected: RetrievalEvaluationExpected,
    *,
    run_id: str,
    handler: ChatTurnHandler,
    service: MemoryPolicyService,
    account: AccountContext,
) -> RetrievalSceneObservation:
    memory_ids: dict[str, str] = {}
    service.set_capture_enabled(account, True)
    try:
        for prop in scene.props:
            saved = service.save_automatic(
                account,
                AutomaticMemoryCandidate(
                    text=prop.source_text,
                    source_event_id=f"prop:{prop.prop_id}",
                    review_allows_capture=True,
                    contains_sensitive_content=False,
                ),
            )
            memory_ids[prop.prop_id] = saved.record.memory_id
    finally:
        service.set_capture_enabled(account, False)

    before = {record.memory_id: record for record in service.list_active(account)}
    recorder = SceneTranscriptRecorder()
    session_id = f"synthetic-eval:{run_id}:scene:{scene.scene_id}"
    request = ChatRequest(
        session_id=session_id,
        turn_id=f"synthetic-eval:{run_id}:turn:{uuid4().hex}",
        message=scene.line,
    )
    try:
        with bind_evaluation_transcript_sink(recorder):
            response = await handler(request, service, account)
    finally:
        sessions.clear(session_id)

    after = {record.memory_id: record for record in service.list_active(account)}
    events = recorder.connection_events
    failures: list[str] = []
    try:
        ledger = _evidence_ledger(
            [event for event in events if event.kind == "search" and event.source == "memory"]
        )
    except (ValueError, KeyError, TypeError):
        failures.append("invalid_evidence_observation")
        ledger = {}
    release_events = [event for event in events if event.kind == "release"]
    cited_ids = set(release_events[-1].released_evidence_ids) if release_events else set()
    retrieved = tuple(
        prop.prop_id for prop in scene.props if memory_ids[prop.prop_id] in ledger
    )
    cited = tuple(
        prop.prop_id for prop in scene.props if memory_ids[prop.prop_id] in cited_ids
    )
    release = response.inspection.release
    release_source = release.release_source if release else "unavailable"

    if not release_events:
        failures.append("missing_release_observation")
    if release_source != NORMAL_RELEASE_SOURCE:
        failures.append("unexpected_release_source")
    failures.extend(lookup_failures(response, events))
    if any(prop_id not in retrieved for prop_id in expected.relevant_prop_ids):
        failures.append("relevant_prop_not_retrieved")
    if any(prop_id not in cited for prop_id in expected.relevant_prop_ids):
        failures.append("relevant_prop_not_cited")
    if any(prop_id in expected.distractor_prop_ids for prop_id in cited):
        failures.append("distractor_prop_cited")
    if any(after.get(memory_id) != record for memory_id, record in before.items()):
        failures.append("props_changed")
    if set(after) - set(before):
        failures.append("unexpected_memory_writes")
    if service.capture_enabled(account):
        failures.append("capture_enabled_after_scene")

    hard_failures = tuple(failures)
    ground_truth_result = _ground_truth_result(
        matches=not hard_failures,
        ground_truth_status=expected.ground_truth_status,
    )
    set_eval_attribute("scene_role", scene.role)
    set_eval_attribute("ground_truth_result", ground_truth_result)
    set_eval_attribute("release_source", release_source)
    set_eval_attribute("hard_failures", list(hard_failures))
    return RetrievalSceneObservation(
        scene_id=scene.scene_id,
        line_id=scene.line_id,
        input_line=scene.line,
        role=scene.role,
        trace_id=format_trace_id(get_current_span().get_span_context().trace_id),
        relevant_prop_ids=expected.relevant_prop_ids,
        distractor_prop_ids=expected.distractor_prop_ids,
        retrieved_prop_ids=retrieved,
        cited_prop_ids=cited,
        uncited_retrieved_distractor_prop_ids=tuple(
            prop_id
            for prop_id in retrieved
            if prop_id in expected.distractor_prop_ids and prop_id not in cited
        ),
        release_source=release_source,
        reply=response.reply,
        hard_failures=hard_failures,
        ground_truth_result=ground_truth_result,
        events=events,
        agent_exchanges=recorder.exchanges,
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
            backstory, ground_truth = validate_scenario_files(
                args.backstory, args.ground_truth
            )
            adoption = None
        else:
            backstory, ground_truth, adoption = validate_ground_truth_adoption_files(
                args.backstory, args.ground_truth, args.adoption
            )
        result = asyncio.run(
            replay_retrieval_scenes(backstory, ground_truth, adoption=adoption)
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
