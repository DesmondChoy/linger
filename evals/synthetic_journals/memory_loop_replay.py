"""Replay recall Lines before and after cumulative production curation rounds."""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from opentelemetry.trace import format_trace_id, get_current_span
from pydantic import Field
from pydantic_ai.exceptions import AgentRunError
from pydantic_evals import Case, Dataset
from pydantic_evals.dataset import set_eval_attribute
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from apps.backend import sessions
from apps.backend.schemas import ChatRequest
from apps.backend.telemetry import configure_synthetic_evaluation_telemetry
from src.linger.agents.contracts import PromptFingerprint
from src.linger.contracts.curation import CuratedMemory
from src.linger.evaluation_transcript import (
    ConnectionEvaluationEvent,
    bind_evaluation_transcript_sink,
)
from src.linger.orchestration.curation import CurationLoopError, run_curation_loop
from src.linger.services.memory import (
    AccountContext,
    MemoryPolicyService,
    MemoryRecord,
    MemoryServiceError,
)

from .adoption import GroundTruthAdoptionError, validate_ground_truth_adoption_files
from .connection_replay import _evidence_ledger, lookup_failures
from .evaluation_link import emit_evaluation_link
from .models import (
    CurationRecallLoop,
    GroundTruthAdoption,
    Prop,
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
from .replay_support import MEMORY_LOOP_RUN_CONFIGURATION_ID
from .retrieval_replay import (
    NORMAL_RELEASE_SOURCE,
    RETRIEVAL_OBJECTIVE_ID,
    SceneRole,
    _retrieval_scene,
    _RetrievalScene,
    _seed_props,
)
from .transcript import AgentExchange, SceneTranscriptRecorder
from .validate_scenario import (
    DEFAULT_RUN_CONFIGURATION_DIRECTORY,
    ScenarioValidationError,
    load_run_configurations,
    validate_scenario_files,
)

EVALUATION_NAME = "memory_curation_recall_loop"

CurationRoundStatus = Literal[
    "no_change",
    "provenance_revise",
    "provenance_reject",
    "applied",
    "failed",
]


class RetrievalViewItem(StrictModel):
    """One item Serendipity can search after a curation round."""

    kind: Literal["original", "derived_summary", "topic_group"]
    source_prop_ids: tuple[str, ...]
    text: str | None = None


class CurationRoundObservation(StrictModel):
    """One production curation round over the whole Prop bank."""

    repetition: int = Field(ge=1)
    round: int = Field(ge=1)
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    status: CurationRoundStatus
    action: str | None = None
    source_prop_ids: tuple[str, ...] = ()
    provenance_decision: str | None = None
    failure: str | None = None
    retrieval_view: tuple[RetrievalViewItem, ...]
    agent_exchanges: tuple[AgentExchange, ...]


class DerivedCitation(StrictModel):
    """Generated curation text that recall returned, with its source Props."""

    kind: Literal["derived_summary", "topic_group"]
    text: str
    source_prop_ids: tuple[str, ...]


class RecallGrade(StrictModel):
    """One recall Line observed in one repetition after some curation rounds."""

    repetition: int = Field(ge=1)
    curation_rounds: int = Field(ge=0)
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    retrieved_prop_ids: tuple[str, ...]
    cited_prop_ids: tuple[str, ...]
    retrieved_derived: tuple[DerivedCitation, ...]
    cited_derived: tuple[DerivedCitation, ...]
    release_source: str
    reply: str
    hard_failures: tuple[str, ...]
    ground_truth_result: GroundTruthResult
    events: tuple[ConnectionEvaluationEvent, ...]
    agent_exchanges: tuple[AgentExchange, ...]
    semantic_review_required: Literal[True] = True


class MemoryLoopSceneObservation(StrictModel):
    """Every arm and repetition of one recall Scene."""

    scene_id: str
    line_id: str
    input_line: str
    role: SceneRole
    relevant_prop_ids: tuple[str, ...]
    distractor_prop_ids: tuple[str, ...]
    grades: tuple[RecallGrade, ...]


class ArmComparison(StrictModel):
    """How often one Scene passed its hard gates after a number of rounds."""

    scene_id: str
    curation_rounds: int = Field(ge=0)
    passed: int = Field(ge=0)
    repetitions: int = Field(ge=1)


class MemoryLoopEvaluationInput(StrictModel):
    """One recall Line in one arm, shown as a native evaluation input."""

    order: int = Field(ge=1)
    repetition: int = Field(ge=1)
    curation_rounds: int = Field(ge=0)
    scene_id: str
    line_id: str
    line: str


class MemoryLoopEvaluationExpected(StrictModel):
    """Proposed Prop relevance kept outside every production input."""

    role: SceneRole
    relevant_prop_ids: tuple[str, ...]
    distractor_prop_ids: tuple[str, ...]
    ground_truth_status: GroundTruthStatus


class MemoryLoopEvaluationOutput(StrictModel):
    """Compact recall result displayed by Logfire's Evals UI."""

    ground_truth_result: GroundTruthResult
    hard_failures: tuple[str, ...]
    retrieved_prop_ids: tuple[str, ...]
    cited_prop_ids: tuple[str, ...]
    cited_derived: tuple[DerivedCitation, ...]
    release_source: str
    reply: str
    semantic_review_required: Literal[True] = True


class MemoryLoopRun(StrictModel):
    """Recall on raw Props and after each cumulative curation round."""

    artifact_schema_version: Literal["1"] = "1"
    content_classification: Literal["synthetic"] = "synthetic"
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    objective_ids: tuple[str, ...]
    run_configuration_id: str
    curation_rounds: int = Field(ge=1)
    repetitions: int = Field(ge=1)
    backstory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposed_ground_truth_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    dataset_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    system_variant: str = Field(pattern=r"^[0-9a-f]{64}$")
    ground_truth_status: GroundTruthStatus
    capture_enabled: Literal[False] = False
    runtime_prompt_fingerprints: tuple[PromptFingerprint, ...]
    curation: tuple[CurationRoundObservation, ...]
    scenes: tuple[MemoryLoopSceneObservation, ...]
    comparison: tuple[ArmComparison, ...]


MemoryLoopResult = MemoryLoopEvaluationExpected | MemoryLoopEvaluationOutput


@dataclass(repr=False)
class MemoryLoopGroundTruthEvaluator(
    Evaluator[MemoryLoopEvaluationInput, MemoryLoopResult, dict[str, object]]
):
    """Expose each recall observation's own hard-gate grade."""

    ground_truth_status: GroundTruthStatus

    def evaluate(
        self,
        ctx: EvaluatorContext[
            MemoryLoopEvaluationInput, MemoryLoopResult, dict[str, object]
        ],
    ) -> str:
        output = ctx.output
        if not isinstance(output, MemoryLoopEvaluationOutput):
            raise TypeError("memory loop evaluation output has the wrong type")
        result = _ground_truth_result(
            matches=not output.hard_failures,
            ground_truth_status=self.ground_truth_status,
        )
        if output.ground_truth_result != result:
            raise ValueError("memory loop Ground truth result is inconsistent")
        return result

    def get_default_evaluation_name(self) -> str:
        return (
            "adopted_hard_gate_grade"
            if self.ground_truth_status == "adopted"
            else "proposal_comparison"
        )


@dataclass(frozen=True)
class ResolvedEvidence:
    """Observed evidence IDs resolved against the current retrieval view."""

    direct_prop_ids: tuple[str, ...]
    derived: tuple[DerivedCitation, ...]
    unknown_ids: tuple[str, ...]

    def prop_ids(self) -> frozenset[str]:
        """Every Prop this evidence rests on, directly or as a derived source."""

        return frozenset(self.direct_prop_ids).union(
            *(item.source_prop_ids for item in self.derived)
        )


def _retrievable_copy(prop_id: str, canonical_of: dict[str, str]) -> str:
    """Follow retrieval tombstones from a hidden Prop to its retrievable copy."""

    seen = {prop_id}
    while (canonical := canonical_of.get(prop_id)) is not None and canonical not in seen:
        seen.add(canonical)
        prop_id = canonical
    return prop_id


def _resolve_evidence(
    evidence_ids: Sequence[str],
    *,
    view: dict[str, CuratedMemory],
    prop_by_memory: dict[str, str],
) -> ResolvedEvidence:
    direct: list[str] = []
    derived: list[DerivedCitation] = []
    unknown: list[str] = []
    for evidence_id in dict.fromkeys(evidence_ids):
        item = view.get(evidence_id)
        if item is None:
            unknown.append(evidence_id)
        elif item.kind == "original":
            direct.append(prop_by_memory[item.memory_id])
        else:
            derived.append(
                DerivedCitation(
                    kind=item.kind,
                    text=item.text,
                    source_prop_ids=tuple(
                        prop_by_memory[memory_id]
                        for memory_id in item.source_memory_ids
                    ),
                )
            )
    return ResolvedEvidence(tuple(direct), tuple(derived), tuple(unknown))


def grade_recall_evidence(
    *,
    relevant_prop_ids: Sequence[str],
    distractor_prop_ids: Sequence[str],
    retrieved: ResolvedEvidence,
    cited: ResolvedEvidence,
    canonical_of: dict[str, str],
) -> tuple[str, ...]:
    """Grade citations identically for raw and curated memories.

    Evidence is first reduced to the Props it rests on: a derived record
    counts as each of its sources, whether relevant or not. A relevant Prop
    hidden by a retrieval tombstone is satisfied by its retrievable copy, and
    that copy is then not a distractor.
    """

    failures: list[str] = []
    retrieved_ids, cited_ids = retrieved.prop_ids(), cited.prop_ids()
    copies = {
        prop_id: _retrievable_copy(prop_id, canonical_of)
        for prop_id in relevant_prop_ids
    }
    if any(
        prop_id not in retrieved_ids and copy not in retrieved_ids
        for prop_id, copy in copies.items()
    ):
        failures.append("relevant_prop_not_retrieved")
    if any(
        prop_id not in cited_ids and copy not in cited_ids
        for prop_id, copy in copies.items()
    ):
        failures.append("relevant_prop_not_cited")
    if cited_ids.intersection(distractor_prop_ids) - set(copies.values()):
        failures.append("distractor_prop_cited")
    if cited.unknown_ids:
        failures.append("unknown_evidence_cited")
    return tuple(failures)


class _DatedMemoryService(MemoryPolicyService):
    """Report each Prop's own recording time instead of its seeding time."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.recorded: dict[str, datetime | None] = {}

    def recorded_at(self, record: MemoryRecord) -> datetime | None:
        return self.recorded.get(record.memory_id)


@dataclass
class _Repetition:
    """One isolated store that accumulates curation rounds."""

    number: int
    service: MemoryPolicyService
    account: AccountContext
    memory_ids: dict[str, str]
    rounds_done: int = 0
    prop_by_memory: dict[str, str] = field(init=False)

    def __post_init__(self) -> None:
        self.prop_by_memory = {
            memory_id: prop_id for prop_id, memory_id in self.memory_ids.items()
        }

    def canonical_of(self) -> dict[str, str]:
        state = self.service.existing_curation(
            self.account, tuple(self.memory_ids.values())
        )
        return {
            self.prop_by_memory[item.memory_id]: self.prop_by_memory[
                item.canonical_memory_id
            ]
            for item in state.tombstones
            if item.canonical_memory_id is not None
        }

    def view(self) -> dict[str, CuratedMemory]:
        return {
            item.memory_id: item
            for item in self.service.list_for_retrieval(self.account)
        }


def _seed_repetition(
    number: int,
    props: Sequence[Prop],
    *,
    root: Path,
    account_id: str,
) -> _Repetition:
    """Seed identical, dated Props into a fresh store for one repetition."""

    account = AccountContext(account_id)
    service = _DatedMemoryService(root / f"repetition-{number}")
    memory_ids = _seed_props(props, service=service, account=account)
    service.recorded = {memory_ids[prop.prop_id]: prop.recorded_at for prop in props}
    return _Repetition(
        number=number, service=service, account=account, memory_ids=memory_ids
    )


async def _run_curation_round(
    repetition: _Repetition,
    *,
    curation_agents: dict[str, Any],
) -> CurationRoundObservation:
    """Run one production curation round and record every outcome."""

    recorder = SceneTranscriptRecorder()
    status: CurationRoundStatus = "failed"
    action: str | None = None
    source_prop_ids: tuple[str, ...] = ()
    decision: str | None = None
    failure: str | None = None
    try:
        with bind_evaluation_transcript_sink(recorder):
            loop = await run_curation_loop(
                repetition.account,
                tuple(repetition.memory_ids.values()),
                service=repetition.service,
                **curation_agents,
            )
    except (CurationLoopError, MemoryServiceError, AgentRunError) as error:
        # A failed round is a reported outcome of the experiment, not a crash.
        failure = getattr(error, "code", None) or getattr(error, "reason", None)
        failure = str(failure or type(error).__name__)
    else:
        status = loop.status
        if loop.provenance_review is not None:
            decision = loop.provenance_review.decision
        if loop.sculptor_response.kind == "curation_proposal":
            proposed = loop.sculptor_response.action
            action = proposed.action
            source_prop_ids = tuple(
                repetition.prop_by_memory[memory_id]
                for memory_id in proposed.source_memory_ids
            )
    repetition.rounds_done += 1
    return CurationRoundObservation(
        repetition=repetition.number,
        round=repetition.rounds_done,
        trace_id=format_trace_id(get_current_span().get_span_context().trace_id),
        status=status,
        action=action,
        source_prop_ids=source_prop_ids,
        provenance_decision=decision,
        failure=failure,
        retrieval_view=tuple(
            RetrievalViewItem(
                kind=item.kind,
                source_prop_ids=tuple(
                    repetition.prop_by_memory[memory_id]
                    for memory_id in item.source_memory_ids
                ),
                text=None if item.kind == "original" else item.text,
            )
            for item in repetition.view().values()
        ),
        agent_exchanges=recorder.exchanges,
    )


async def _recall_line(
    scene: _RetrievalScene,
    repetition: _Repetition,
    *,
    run_id: str,
    handler: ChatTurnHandler,
    ground_truth_status: GroundTruthStatus,
) -> RecallGrade:
    """Send one held-out Line in a fresh session and grade its evidence."""

    service, account = repetition.service, repetition.account
    before = {record.memory_id: record for record in service.list_active(account)}
    view = repetition.view()
    recorder = SceneTranscriptRecorder()
    session_id = (
        f"synthetic-eval:{run_id}:repetition:{repetition.number}"
        f":rounds:{repetition.rounds_done}:scene:{scene.scene_id}"
    )
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
            [
                event
                for event in events
                if event.kind == "search" and event.source == "memory"
            ]
        )
    except (ValueError, KeyError, TypeError):
        failures.append("invalid_evidence_observation")
        ledger = {}
    release_events = [event for event in events if event.kind == "release"]
    retrieved = _resolve_evidence(
        tuple(ledger), view=view, prop_by_memory=repetition.prop_by_memory
    )
    cited = _resolve_evidence(
        release_events[-1].released_evidence_ids if release_events else (),
        view=view,
        prop_by_memory=repetition.prop_by_memory,
    )
    release = response.inspection.release
    release_source = release.release_source if release else "unavailable"

    if not release_events:
        failures.append("missing_release_observation")
    if release_source != NORMAL_RELEASE_SOURCE:
        failures.append("unexpected_release_source")
    failures.extend(lookup_failures(response, events))
    failures.extend(
        grade_recall_evidence(
            relevant_prop_ids=scene.relevant_prop_ids,
            distractor_prop_ids=scene.distractor_prop_ids,
            retrieved=retrieved,
            cited=cited,
            canonical_of=repetition.canonical_of(),
        )
    )
    if any(after.get(memory_id) != record for memory_id, record in before.items()):
        failures.append("props_changed")
    if set(after) - set(before):
        failures.append("unexpected_memory_writes")
    if service.capture_enabled(account):
        failures.append("capture_enabled_after_scene")

    hard_failures = tuple(failures)
    ground_truth_result = _ground_truth_result(
        matches=not hard_failures,
        ground_truth_status=ground_truth_status,
    )
    set_eval_attribute("repetition", repetition.number)
    set_eval_attribute("curation_rounds", repetition.rounds_done)
    set_eval_attribute("ground_truth_result", ground_truth_result)
    set_eval_attribute("release_source", release_source)
    set_eval_attribute("hard_failures", list(hard_failures))
    return RecallGrade(
        repetition=repetition.number,
        curation_rounds=repetition.rounds_done,
        trace_id=format_trace_id(get_current_span().get_span_context().trace_id),
        retrieved_prop_ids=retrieved.direct_prop_ids,
        cited_prop_ids=cited.direct_prop_ids,
        retrieved_derived=retrieved.derived,
        cited_derived=cited.derived,
        release_source=release_source,
        reply=response.reply,
        hard_failures=hard_failures,
        ground_truth_result=ground_truth_result,
        events=events,
        agent_exchanges=recorder.exchanges,
    )


def _loop_settings() -> CurationRecallLoop:
    configuration = load_run_configurations(DEFAULT_RUN_CONFIGURATION_DIRECTORY).get(
        MEMORY_LOOP_RUN_CONFIGURATION_ID
    )
    if configuration is None or configuration.curation_recall_loop is None:
        raise ValueError(
            f"run configuration {MEMORY_LOOP_RUN_CONFIGURATION_ID} is not available"
        )
    return configuration.curation_recall_loop


def _loop_scenes(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
) -> tuple[_RetrievalScene, ...]:
    """Return the recall Scenes of a memory-loop Scenario over one Prop bank."""

    if backstory.objective_ids != (RETRIEVAL_OBJECTIVE_ID,):
        raise ValueError(
            "memory loop replay requires longitudinal_memory_retrieval alone"
        )
    if backstory.run_configuration_ids != (MEMORY_LOOP_RUN_CONFIGURATION_ID,):
        raise ValueError(
            "memory loop replay requires only the "
            f"{MEMORY_LOOP_RUN_CONFIGURATION_ID} run configuration"
        )
    if backstory.offline_inputs or backstory.source_setups:
        raise ValueError("memory loop replay accepts Lines and Props only")
    scenes = tuple(
        _retrieval_scene(backstory, ground_truth, scene)
        for scene in sorted(backstory.scenes, key=lambda item: item.order)
    )
    bank = {prop.prop_id for prop in scenes[0].props}
    if any({prop.prop_id for prop in scene.props} != bank for scene in scenes):
        raise ValueError("memory loop replay requires one shared Prop bank")
    return scenes


async def replay_memory_loop(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    *,
    adoption: GroundTruthAdoption | None = None,
    chat_handler: ChatTurnHandler | None = None,
    sculptor: Any | None = None,
    provenance: Any | None = None,
    settings: CurationRecallLoop | None = None,
) -> MemoryLoopRun:
    """Run a validated Scenario through every arm of every repetition.

    Each repetition seeds identical Props into its own store, sends every Line,
    then alternates one production curation round with every Line again.
    Curation receives the Props and its own earlier decisions, never a Line.
    """

    scenes = _loop_scenes(backstory, ground_truth)
    props = scenes[0].props
    loop_settings = settings or _loop_settings()

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
    curation_agents = {
        name: agent
        for name, agent in (("sculptor", sculptor), ("provenance", provenance))
        if agent is not None
    }

    run_id = uuid4().hex
    cases: list[
        Case[MemoryLoopEvaluationInput, MemoryLoopResult, dict[str, object]]
    ] = []
    for repetition_number in range(1, loop_settings.repetitions + 1):
        for rounds in range(loop_settings.curation_rounds + 1):
            for scene in scenes:
                cases.append(
                    Case(
                        name=(
                            f"{scene.scene_id}--repetition-{repetition_number}"
                            f"--rounds-{rounds}"
                        ),
                        inputs=MemoryLoopEvaluationInput(
                            order=len(cases) + 1,
                            repetition=repetition_number,
                            curation_rounds=rounds,
                            scene_id=scene.scene_id,
                            line_id=scene.line_id,
                            line=scene.line,
                        ),
                        expected_output=MemoryLoopEvaluationExpected(
                            role=scene.role,
                            relevant_prop_ids=scene.relevant_prop_ids,
                            distractor_prop_ids=scene.distractor_prop_ids,
                            ground_truth_status=status,
                        ),
                        metadata={
                            "objective_id": RETRIEVAL_OBJECTIVE_ID,
                            "repetition": repetition_number,
                            "curation_rounds": rounds,
                            "ground_truth_status": status,
                        },
                    )
                )

    scenes_by_id = {scene.scene_id: scene for scene in scenes}
    grades: dict[str, list[RecallGrade]] = {scene.scene_id: [] for scene in scenes}
    curation: list[CurationRoundObservation] = []
    completed = 0
    with tempfile.TemporaryDirectory(prefix="linger-memory-loop-") as directory:
        root = Path(directory)
        current: _Repetition | None = None

        async def evaluate_case(
            inputs: MemoryLoopEvaluationInput,
        ) -> MemoryLoopEvaluationOutput:
            nonlocal completed, current
            if inputs.order != completed + 1:
                raise RuntimeError("memory loop cases did not execute in order")
            if current is None or current.number != inputs.repetition:
                current = _seed_repetition(
                    inputs.repetition,
                    props,
                    root=root,
                    account_id=(
                        f"synthetic-eval:{backstory.backstory.evaluation_account_id}"
                        f":{run_id}"
                    ),
                )
            while current.rounds_done < inputs.curation_rounds:
                curation.append(
                    await _run_curation_round(
                        current, curation_agents=curation_agents
                    )
                )
            grade = await _recall_line(
                scenes_by_id[inputs.scene_id],
                current,
                run_id=run_id,
                handler=handler,
                ground_truth_status=status,
            )
            grades[inputs.scene_id].append(grade)
            completed += 1
            return MemoryLoopEvaluationOutput(
                ground_truth_result=grade.ground_truth_result,
                hard_failures=grade.hard_failures,
                retrieved_prop_ids=grade.retrieved_prop_ids,
                cited_prop_ids=grade.cited_prop_ids,
                cited_derived=grade.cited_derived,
                release_source=grade.release_source,
                reply=grade.reply,
            )

        dataset = Dataset(
            name=EVALUATION_NAME,
            cases=cases,
            evaluators=[MemoryLoopGroundTruthEvaluator(ground_truth_status=status)],
        )
        report = await dataset.evaluate(
            evaluate_case,
            name=f"{EVALUATION_NAME}-{run_id[:8]}",
            task_name="memory_curation_recall_loop_workflow",
            max_concurrency=1,
            progress=False,
            metadata={
                "content_classification": "synthetic",
                "objective_ids": backstory.objective_ids,
                "run_configuration_id": MEMORY_LOOP_RUN_CONFIGURATION_ID,
                "curation_rounds": loop_settings.curation_rounds,
                "repetitions": loop_settings.repetitions,
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
        if completed != len(cases):
            raise RuntimeError("memory loop evaluation did not produce every case")

    return MemoryLoopRun(
        run_id=run_id,
        trace_id=report.trace_id or "0" * 32,
        objective_ids=backstory.objective_ids,
        run_configuration_id=MEMORY_LOOP_RUN_CONFIGURATION_ID,
        curation_rounds=loop_settings.curation_rounds,
        repetitions=loop_settings.repetitions,
        backstory_sha256=ground_truth.backstory_sha256,
        proposed_ground_truth_sha256=(
            adoption.proposed_ground_truth_sha256 if adoption else None
        ),
        dataset_version=dataset_version,
        system_variant=RUNTIME_SYSTEM_VARIANT,
        ground_truth_status=status,
        runtime_prompt_fingerprints=RUNTIME_PROMPT_FINGERPRINTS,
        curation=tuple(curation),
        scenes=tuple(
            MemoryLoopSceneObservation(
                scene_id=scene.scene_id,
                line_id=scene.line_id,
                input_line=scene.line,
                role=scene.role,
                relevant_prop_ids=scene.relevant_prop_ids,
                distractor_prop_ids=scene.distractor_prop_ids,
                grades=tuple(grades[scene.scene_id]),
            )
            for scene in scenes
        ),
        comparison=tuple(
            ArmComparison(
                scene_id=scene.scene_id,
                curation_rounds=rounds,
                passed=sum(
                    not grade.hard_failures
                    for grade in grades[scene.scene_id]
                    if grade.curation_rounds == rounds
                ),
                repetitions=loop_settings.repetitions,
            )
            for scene in scenes
            for rounds in range(loop_settings.curation_rounds + 1)
        ),
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
            replay_memory_loop(backstory, ground_truth, adoption=adoption)
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
