"""Replay grounded-reflection and spoiler-boundary Scenes through production chat."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

import logfire
from opentelemetry.trace import format_trace_id, get_current_span
from pydantic import Field
from pydantic_evals import Case, Dataset
from pydantic_evals.dataset import set_eval_attribute
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from apps.backend import sessions
from apps.backend.contracts import ContextResolution
from apps.backend.schemas import CaptureInspection, ChatRequest, ChatResponse
from apps.backend.telemetry import configure_synthetic_evaluation_telemetry
from src.linger.agents.contracts import PromptFingerprint
from src.linger.contracts.librarian import (
    LIBRARIAN_RESPONSE_ADAPTER,
    ClarificationRequest,
    EvidenceRecord,
    RetrievalFailure,
    RetrievalResult,
)
from src.linger.evaluation_transcript import bind_evaluation_transcript_sink
from src.linger.services.memory import (
    AccountContext,
    AutomaticMemoryCandidate,
    MemoryPolicyService,
)

from .adoption import (
    GroundTruthAdoptionError,
    validate_ground_truth_adoption_files,
)
from .models import (
    GroundTruthAdoption,
    GroundTruthProposal,
    Prop,
    ProposedGroundTruth,
    RepositoryTextEvidence,
    StrictModel,
    SyntheticBackstory,
)
from .replay import (
    ChatTurnHandler,
    GroundTruthResult,
    GroundTruthStatus,
    RUNTIME_PROMPT_FINGERPRINTS,
    RUNTIME_SYSTEM_VARIANT,
    _ground_truth_result,
    _production_chat_turn_handler,
    evaluation_agents,
)
from .transcript import AgentExchange, SceneTranscriptRecorder
from .validate_package import PackageValidationError, validate_package_files

GROUNDED_OBJECTIVE_ID = "grounded_book_reflection"
SPOILER_OBJECTIVE_ID = "spoiler_boundary_clarification"
BOOK_OBJECTIVE_IDS = (GROUNDED_OBJECTIVE_ID, SPOILER_OBJECTIVE_ID)
BOOK_DATASET_NAME = "grounded_book_reflection+spoiler_boundary_clarification"


class BookPropInput(StrictModel):
    prop_id: str
    source_text: str


class SeededProp(StrictModel):
    prop_id: str
    memory_id: str
    source_text: str


class RuntimeEvidenceObservation(StrictModel):
    evidence_id: str
    chapter_number: int = Field(ge=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_lines: tuple[int, int]
    text: str


class GroundingObservation(StrictModel):
    response_kind: Literal["clarification", "result", "failure"]
    call_outcome: str | None
    retrieval_outcome: Literal["evidence_found", "no_evidence"] | None = None
    searched_max_chapter: int | None = Field(default=None, ge=0)
    evidence: tuple[RuntimeEvidenceObservation, ...] = ()
    clarification_question: str | None = None
    failure_code: str | None = None


class ObjectiveGrade(StrictModel):
    objective_id: Literal[
        "grounded_book_reflection",
        "spoiler_boundary_clarification",
    ]
    hard_pass: bool
    failures: tuple[str, ...]


class BookSceneObservation(StrictModel):
    scene_id: str
    line_id: str
    input_line: str
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    seeded_props: tuple[SeededProp, ...]
    context_resolution: ContextResolution
    boundary_decision: Literal["infer", "clarify", "not_applicable"]
    boundary_handoff_content_free: bool
    boundary_support_evidence: tuple[RuntimeEvidenceObservation, ...]
    grounding_calls: tuple[GroundingObservation, ...]
    released_evidence_ids: tuple[str, ...]
    reply: str
    release_source: Literal[
        "muse_candidate",
        "application_emotional_boundary",
        "application_safe_decline",
    ]
    provenance_verdicts: tuple[Literal["pass", "revise", "reject"], ...]
    capture: CaptureInspection
    agent_exchanges: tuple[AgentExchange, ...]
    grades: tuple[ObjectiveGrade, ...]
    ground_truth_result: GroundTruthResult


class BookEvaluationRun(StrictModel):
    artifact_schema_version: Literal["1"] = "1"
    content_classification: Literal["synthetic"] = "synthetic"
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    objective_ids: tuple[
        Literal["grounded_book_reflection"],
        Literal["spoiler_boundary_clarification"],
    ]
    dataset_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    system_variant: str = Field(pattern=r"^[0-9a-f]{64}$")
    ground_truth_status: GroundTruthStatus
    runtime_prompt_fingerprints: tuple[PromptFingerprint, ...]
    scenes: tuple[BookSceneObservation, ...]


class BookEvaluationInput(StrictModel):
    order: int = Field(ge=1)
    scene_id: str
    line_id: str
    line: str
    props: tuple[BookPropInput, ...]


class BookEvaluationExpected(StrictModel):
    proposals: tuple[GroundTruthProposal, ...]
    ground_truth_status: GroundTruthStatus


class BookEvaluationOutput(StrictModel):
    grades: tuple[ObjectiveGrade, ...]
    ground_truth_result: GroundTruthResult
    boundary_decision: Literal["infer", "clarify", "not_applicable"]
    released_evidence_ids: tuple[str, ...]
    reply: str
    release_source: Literal[
        "muse_candidate",
        "application_emotional_boundary",
        "application_safe_decline",
    ]


BookEvaluationResult = BookEvaluationExpected | BookEvaluationOutput


@dataclass(frozen=True)
class _BookSceneCase:
    order: int
    scene_id: str
    line_id: str
    line: str
    props: tuple[Prop, ...]
    proposals: tuple[GroundTruthProposal, ...]


@dataclass(repr=False)
class BookGroundTruthEvaluator(
    Evaluator[BookEvaluationInput, BookEvaluationResult, dict[str, object]]
):
    """Compare proposed labels or grade the same checks after adoption."""

    ground_truth_status: GroundTruthStatus

    def evaluate(
        self,
        ctx: EvaluatorContext[
            BookEvaluationInput,
            BookEvaluationResult,
            dict[str, object],
        ],
    ) -> str:
        output = ctx.output
        if not isinstance(output, BookEvaluationOutput):
            raise TypeError("book evaluation task returned the wrong output")
        result = _ground_truth_result(
            matches=all(grade.hard_pass for grade in output.grades),
            ground_truth_status=self.ground_truth_status,
        )
        if output.ground_truth_result != result:
            raise ValueError("book Ground truth result is inconsistent")
        return result

    def get_default_evaluation_name(self) -> str:
        if self.ground_truth_status == "adopted":
            return "adopted_hard_gate_grade"
        return "proposal_comparison"


async def replay_book_scenes(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    *,
    adoption: GroundTruthAdoption | None = None,
    chat_handler: ChatTurnHandler | None = None,
) -> BookEvaluationRun:
    """Run the approved three-Scene book package through production chat."""

    scene_cases = _book_scene_cases(backstory, ground_truth)
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
    cases = [
        Case(
            name=scene.scene_id,
            inputs=BookEvaluationInput(
                order=scene.order,
                scene_id=scene.scene_id,
                line_id=scene.line_id,
                line=scene.line,
                props=tuple(
                    BookPropInput(prop_id=prop.prop_id, source_text=prop.source_text)
                    for prop in scene.props
                ),
            ),
            expected_output=BookEvaluationExpected(
                proposals=scene.proposals,
                ground_truth_status=ground_truth_status,
            ),
            metadata={
                "objective_ids": [proposal.objective_id for proposal in scene.proposals],
                "scene_order": scene.order,
                "ground_truth_status": ground_truth_status,
            },
        )
        for scene in scene_cases
    ]
    observations: list[BookSceneObservation] = []

    with tempfile.TemporaryDirectory(prefix="linger-synthetic-book-eval-") as directory:
        root = Path(directory)

        async def evaluate_scene(inputs: BookEvaluationInput) -> BookEvaluationOutput:
            expected_order = len(observations) + 1
            if inputs.order != expected_order:
                raise RuntimeError(
                    "synthetic book cases did not execute in Scene order"
                )
            scene = scene_cases[inputs.order - 1]
            if scene.scene_id != inputs.scene_id:
                raise RuntimeError("synthetic book Scene identity changed")
            service = MemoryPolicyService(root / f"{inputs.order:02d}-{inputs.scene_id}")
            observation = await _replay_book_scene(
                scene,
                run_id=run_id,
                handler=handler,
                service=service,
                account=account,
                ground_truth_status=ground_truth_status,
            )
            observations.append(observation)
            return BookEvaluationOutput(
                grades=observation.grades,
                ground_truth_result=observation.ground_truth_result,
                boundary_decision=observation.boundary_decision,
                released_evidence_ids=observation.released_evidence_ids,
                reply=observation.reply,
                release_source=observation.release_source,
            )

        dataset = Dataset(
            name=BOOK_DATASET_NAME,
            cases=cases,
            evaluators=[
                BookGroundTruthEvaluator(ground_truth_status=ground_truth_status)
            ],
        )
        report = await dataset.evaluate(
            evaluate_scene,
            name=f"book-reflection-spoiler-{run_id[:8]}",
            task_name="book_reflection_spoiler_workflow",
            max_concurrency=1,
            progress=False,
            metadata={
                "content_classification": "synthetic",
                "objective_ids": list(BOOK_OBJECTIVE_IDS),
                "run_id": run_id,
                "dataset_version": dataset_version,
                "system_variant": RUNTIME_SYSTEM_VARIANT,
                "ground_truth_status": ground_truth_status,
                "ground_truth_evaluation": evaluation_name,
            },
        )
        if report.failures:
            failed_cases = [failure.name for failure in report.failures]
            raise RuntimeError(f"synthetic book cases failed: {failed_cases}")
        if len(observations) != len(cases):
            raise RuntimeError("synthetic book evaluation missed a Scene")

    return BookEvaluationRun(
        run_id=run_id,
        trace_id=report.trace_id or "0" * 32,
        objective_ids=BOOK_OBJECTIVE_IDS,
        dataset_version=dataset_version,
        system_variant=RUNTIME_SYSTEM_VARIANT,
        ground_truth_status=ground_truth_status,
        runtime_prompt_fingerprints=RUNTIME_PROMPT_FINGERPRINTS,
        scenes=tuple(observations),
    )


async def _replay_book_scene(
    scene: _BookSceneCase,
    *,
    run_id: str,
    handler: ChatTurnHandler,
    service: MemoryPolicyService,
    account: AccountContext,
    ground_truth_status: GroundTruthStatus,
) -> BookSceneObservation:
    seeded = _seed_props(scene, run_id=run_id, service=service, account=account)
    if service.capture_enabled(account):
        raise RuntimeError("book replay must disable automatic capture before chat")

    recorder = SceneTranscriptRecorder()
    session_id = f"synthetic-eval:{run_id}:session:{uuid4().hex}"
    turn_id = f"synthetic-eval:{run_id}:turn:{uuid4().hex}"
    request = ChatRequest(
        session_id=session_id,
        turn_id=turn_id,
        message=scene.line,
    )
    try:
        with bind_evaluation_transcript_sink(recorder):
            response = await handler(request, service, account)
        turn_records = sessions.turn_records(session_id)
        if len(turn_records) != 1 or turn_records[0].turn_id != turn_id:
            raise RuntimeError(
                f"Scene {scene.scene_id} did not produce one production turn audit"
            )
        released_evidence_ids = turn_records[0].evidence_ids
    finally:
        sessions.clear(session_id)

    active = service.list_active(account)
    seeded_memory_ids = {item.memory_id for item in seeded}
    if {record.memory_id for record in active} != seeded_memory_ids:
        raise RuntimeError(
            f"Scene {scene.scene_id} changed the pre-positioned Prop bank"
        )

    release = response.inspection.release
    if release is None:
        raise RuntimeError(f"Scene {scene.scene_id} has no release inspection")
    context = ContextResolution.model_validate(
        response.inspection.context_resolution
    )
    grounding = _grounding_observations(response)
    exchanges = recorder.exchanges
    boundary_decision = _boundary_decision(context)
    content_free = _boundary_handoff_is_content_free(
        boundary_decision,
        context,
        exchanges,
    )
    boundary_support = _boundary_support_observations(context, exchanges)

    provisional = BookSceneObservation(
        scene_id=scene.scene_id,
        line_id=scene.line_id,
        input_line=scene.line,
        trace_id=format_trace_id(get_current_span().get_span_context().trace_id),
        seeded_props=seeded,
        context_resolution=context,
        boundary_decision=boundary_decision,
        boundary_handoff_content_free=content_free,
        boundary_support_evidence=boundary_support,
        grounding_calls=grounding,
        released_evidence_ids=released_evidence_ids,
        reply=response.reply,
        release_source=release.release_source,
        provenance_verdicts=release.provenance_verdicts,
        capture=release.capture,
        agent_exchanges=exchanges,
        grades=(),
        ground_truth_result=_ground_truth_result(
            matches=False,
            ground_truth_status=ground_truth_status,
        ),
    )
    grades = tuple(
        _grade_proposal(proposal, provisional)
        for proposal in scene.proposals
    )
    result = _ground_truth_result(
        matches=all(grade.hard_pass for grade in grades),
        ground_truth_status=ground_truth_status,
    )
    set_eval_attribute("ground_truth_result", result)
    set_eval_attribute("boundary_decision", boundary_decision)
    set_eval_attribute("release_source", release.release_source)
    return provisional.model_copy(
        update={"grades": grades, "ground_truth_result": result}
    )


def _seed_props(
    scene: _BookSceneCase,
    *,
    run_id: str,
    service: MemoryPolicyService,
    account: AccountContext,
) -> tuple[SeededProp, ...]:
    service.set_capture_enabled(account, True)
    seeded = []
    for prop in scene.props:
        result = service.save_automatic(
            account,
            AutomaticMemoryCandidate(
                text=prop.source_text,
                source_event_id=(
                    f"synthetic-prop:{run_id}:{scene.scene_id}:{prop.prop_id}"
                ),
                review_allows_capture=True,
                contains_sensitive_content=False,
            ),
        )
        if not result.created:
            raise RuntimeError(f"Prop {prop.prop_id} was not freshly seeded")
        seeded.append(
            SeededProp(
                prop_id=prop.prop_id,
                memory_id=result.record.memory_id,
                source_text=result.record.text,
            )
        )
    service.set_capture_enabled(account, False)
    return tuple(seeded)


def _grounding_observations(
    response: ChatResponse,
) -> tuple[GroundingObservation, ...]:
    observations = []
    for call in response.inspection.librarian_grounding:
        parsed = LIBRARIAN_RESPONSE_ADAPTER.validate_python(call.get("response"))
        outcome = call.get("outcome")
        call_outcome = outcome if isinstance(outcome, str) else None
        if isinstance(parsed, RetrievalResult):
            observations.append(
                GroundingObservation(
                    response_kind="result",
                    call_outcome=call_outcome,
                    retrieval_outcome=parsed.outcome,
                    searched_max_chapter=parsed.searched_scope.max_chapter_inclusive,
                    evidence=tuple(
                        _runtime_evidence(item) for item in parsed.evidence
                    ),
                )
            )
        elif isinstance(parsed, ClarificationRequest):
            observations.append(
                GroundingObservation(
                    response_kind="clarification",
                    call_outcome=call_outcome,
                    clarification_question=parsed.question,
                )
            )
        elif isinstance(parsed, RetrievalFailure):
            observations.append(
                GroundingObservation(
                    response_kind="failure",
                    call_outcome=call_outcome,
                    failure_code=parsed.error_code,
                )
            )
    return tuple(observations)


def _runtime_evidence(item: EvidenceRecord) -> RuntimeEvidenceObservation:
    return RuntimeEvidenceObservation(
        evidence_id=item.evidence_id,
        chapter_number=item.chapter_number,
        source_sha256=item.source_sha256,
        source_lines=item.source_lines,
        text=item.text,
    )


def _boundary_support_observations(
    context: ContextResolution,
    exchanges: tuple[AgentExchange, ...],
) -> tuple[RuntimeEvidenceObservation, ...]:
    supporting_ids = {
        item.evidence_id for item in context.boundary_supporting_locations
    }
    if not supporting_ids:
        return ()
    boundary_exchanges = tuple(
        exchange
        for exchange in exchanges
        if exchange.role == "Librarian" and exchange.stage == "boundary_inference"
    )
    if len(boundary_exchanges) != 1:
        return ()
    try:
        payload = json.loads(boundary_exchanges[0].input_prompt)
        candidates = tuple(
            EvidenceRecord.model_validate(item)
            for item in payload["full_work_candidates"]
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return ()
    return tuple(
        _runtime_evidence(item)
        for item in candidates
        if item.evidence_id in supporting_ids
    )


def _boundary_decision(
    context: ContextResolution,
) -> Literal["infer", "clarify", "not_applicable"]:
    if context.boundary_source == "librarian_inferred":
        return "infer"
    if context.status == "inferred" and context.clarification_question is not None:
        return "clarify"
    return "not_applicable"


def _boundary_handoff_is_content_free(
    decision: Literal["infer", "clarify", "not_applicable"],
    context: ContextResolution,
    exchanges: tuple[AgentExchange, ...],
) -> bool:
    boundary_exchanges = tuple(
        exchange
        for exchange in exchanges
        if exchange.role == "Librarian" and exchange.stage == "boundary_inference"
    )
    if decision == "not_applicable":
        return not boundary_exchanges
    if len(boundary_exchanges) != 1:
        return False
    output = boundary_exchanges[0].output
    allowed_output_fields = {
        "outcome",
        "work_id",
        "book_version_id",
        "chapter_number",
        "confidence",
        "authorization_basis",
        "supporting_memory_ids",
        "supporting_evidence_ids",
        "reason_code",
    }
    if not isinstance(output, dict) or set(output) - allowed_output_fields:
        return False
    serialized_context = context.model_dump(mode="json")
    locations = (
        serialized_context.get("boundary_supporting_locations", [])
        or serialized_context.get("candidate_supporting_locations", [])
    )
    return all(
        isinstance(location, dict)
        and set(location) <= {"evidence_id", "chapter_number", "location"}
        for location in locations
    )


def _grade_proposal(
    proposal: GroundTruthProposal,
    observation: BookSceneObservation,
) -> ObjectiveGrade:
    failures = []
    if observation.release_source != "muse_candidate":
        failures.append("response_not_released_from_muse_candidate")
    if (
        not observation.provenance_verdicts
        or observation.provenance_verdicts[-1] != "pass"
    ):
        failures.append("provenance_did_not_pass_release")
    if observation.capture.storage == "committed":
        failures.append("unexpected_runtime_memory_capture")

    if proposal.objective_id == GROUNDED_OBJECTIVE_ID:
        expected = proposal.grounded_book_reflection
        if expected is None:  # pragma: no cover - package validator invariant
            raise RuntimeError("grounded proposal lacks typed expectation")
        actual_retrieved = {
            item.evidence_id
            for call in observation.grounding_calls
            for item in call.evidence
        }
        actual_evidence = tuple(
            item for call in observation.grounding_calls for item in call.evidence
        )
        released = set(observation.released_evidence_ids)
        evidence = _repository_evidence(proposal)
        permitted = tuple(
            evidence[evidence_id]
            for evidence_id in expected.permitted_evidence_ids
        )
        permitted_runtime_ids = {
            item.evidence_id
            for item in actual_evidence
            if any(_evidence_matches(reference, item) for reference in permitted)
        }
        if expected.retrieval == "required":
            if not any(
                call.response_kind == "result"
                and call.retrieval_outcome == "evidence_found"
                and call.evidence
                for call in observation.grounding_calls
            ):
                failures.append("required_grounding_evidence_not_retrieved")
            if not released:
                failures.append("grounded_response_released_no_evidence")
            if actual_retrieved - permitted_runtime_ids:
                failures.append("retrieval_used_unpermitted_evidence")
            if released - permitted_runtime_ids:
                failures.append("response_cited_unpermitted_evidence")
            if released and not (released & permitted_runtime_ids):
                failures.append("response_cited_no_permitted_evidence")
            for evidence_id in expected.exact_quotation_evidence_ids:
                item = evidence[evidence_id]
                if (
                    not any(
                        runtime.evidence_id in released
                        and _evidence_matches(item, runtime)
                        for runtime in actual_evidence
                    )
                    or item.text not in observation.reply
                ):
                    failures.append(
                        f"exact_quotation_missing_or_unreleased:{evidence_id}"
                    )
        else:
            if observation.boundary_decision != "not_applicable":
                failures.append("non_factual_reflection_triggered_boundary_inference")
            if not observation.boundary_handoff_content_free:
                failures.append("non_factual_reflection_used_boundary_inference")
            if observation.grounding_calls or released:
                failures.append("non_factual_reflection_used_book_evidence")
    elif proposal.objective_id == SPOILER_OBJECTIVE_ID:
        expected = proposal.spoiler_boundary
        if expected is None:  # pragma: no cover - package validator invariant
            raise RuntimeError("spoiler proposal lacks typed expectation")
        if {item.prop_id for item in observation.seeded_props} != set(
            expected.authorised_prop_ids
        ):
            failures.append("scene_prop_bank_differs_from_authorised_props")
        if observation.boundary_decision != expected.decision:
            failures.append("boundary_decision_differs_from_ground_truth")
        if not observation.boundary_handoff_content_free:
            failures.append("boundary_handoff_not_content_free")
        context = observation.context_resolution
        evidence = _repository_evidence(proposal)
        if expected.decision == "infer":
            safe_ceiling = expected.safe_ceiling_chapter
            if safe_ceiling is None:  # pragma: no cover - model invariant
                raise RuntimeError("inferred boundary lacks a safe ceiling")
            if context.chapter_max != safe_ceiling:
                failures.append("inferred_ceiling_differs_from_ground_truth")
            actual_support = {
                item.evidence_id for item in context.boundary_supporting_locations
            }
            expected_support = tuple(
                evidence[evidence_id]
                for evidence_id in expected.supporting_evidence_ids
            )
            observed_support_ids = {
                item.evidence_id for item in observation.boundary_support_evidence
            }
            if (
                actual_support != observed_support_ids
                or not _evidence_sets_match(
                    expected_support,
                    observation.boundary_support_evidence,
                )
            ):
                failures.append("boundary_support_differs_from_ground_truth")
            for call in observation.grounding_calls:
                if (
                    call.searched_max_chapter is not None
                    and call.searched_max_chapter > safe_ceiling
                ):
                    failures.append("retrieval_exceeded_safe_ceiling")
                if any(
                    item.chapter_number > safe_ceiling
                    for item in call.evidence
                ):
                    failures.append("evidence_exceeded_safe_ceiling")
        else:
            if context.chapter_max is not None or context.boundary_source is not None:
                failures.append("clarification_scene_granted_retrieval_scope")
            if context.clarification_question is None:
                failures.append("clarification_question_missing")
            elif observation.reply != context.clarification_question:
                failures.append("released_reply_differs_from_clarification")
            if observation.grounding_calls or observation.released_evidence_ids:
                failures.append("clarification_scene_retrieved_evidence")

        forbidden_evidence = tuple(
            evidence[evidence_id]
            for evidence_id in expected.forbidden_later_evidence_ids
        )
        observed_evidence = observation.boundary_support_evidence + tuple(
            item
            for call in observation.grounding_calls
            for item in call.evidence
        )
        if any(
            _evidence_matches(reference, actual)
            for reference in forbidden_evidence
            for actual in observed_evidence
        ):
            failures.append("forbidden_later_evidence_used")
        if any(
            evidence[evidence_id].text in observation.reply
            for evidence_id in expected.forbidden_later_evidence_ids
        ):
            failures.append("forbidden_later_fact_disclosed")
    else:  # pragma: no cover - topology validation rejects this earlier
        raise RuntimeError(f"unsupported book Objective {proposal.objective_id}")

    return ObjectiveGrade(
        objective_id=proposal.objective_id,
        hard_pass=not failures,
        failures=tuple(failures),
    )


def _repository_evidence(
    proposal: GroundTruthProposal,
) -> dict[str, RepositoryTextEvidence]:
    return {
        item.evidence_id: item
        for item in proposal.evidence
        if isinstance(item, RepositoryTextEvidence)
    }


def _evidence_matches(
    expected: RepositoryTextEvidence,
    actual: RuntimeEvidenceObservation,
) -> bool:
    return expected.text in actual.text


def _evidence_sets_match(
    expected: tuple[RepositoryTextEvidence, ...],
    actual: tuple[RuntimeEvidenceObservation, ...],
) -> bool:
    return bool(expected) and bool(actual) and all(
        any(_evidence_matches(reference, item) for item in actual)
        for reference in expected
    ) and all(
        any(_evidence_matches(reference, item) for reference in expected)
        for item in actual
    )


def _book_scene_cases(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
) -> tuple[_BookSceneCase, ...]:
    if backstory.objective_ids != BOOK_OBJECTIVE_IDS:
        raise ValueError(
            "book replay requires grounded_book_reflection followed by "
            "spoiler_boundary_clarification"
        )
    if backstory.run_configuration_ids:
        raise ValueError("book replay accepts no run configuration")
    if backstory.offline_inputs:
        raise ValueError("book replay accepts Lines, not offline inputs")
    if len(backstory.props) != 1:
        raise ValueError("book replay requires exactly one Prop")
    if len(backstory.scenes) != 3:
        raise ValueError("book replay requires exactly three Scenes")

    scenes_by_objectives = {
        frozenset(scene.objective_ids): scene for scene in backstory.scenes
    }
    required_sets = {
        frozenset(BOOK_OBJECTIVE_IDS),
        frozenset((GROUNDED_OBJECTIVE_ID,)),
        frozenset((SPOILER_OBJECTIVE_ID,)),
    }
    if set(scenes_by_objectives) != required_sets:
        raise ValueError(
            "book replay requires one combined, one grounded comparison, and "
            "one spoiler comparison Scene"
        )
    combined = scenes_by_objectives[frozenset(BOOK_OBJECTIVE_IDS)]
    grounded_comparison = scenes_by_objectives[frozenset((GROUNDED_OBJECTIVE_ID,))]
    spoiler_comparison = scenes_by_objectives[frozenset((SPOILER_OBJECTIVE_ID,))]

    proposals = {
        (proposal.scene_id, proposal.objective_id): proposal
        for proposal in ground_truth.proposals
    }
    combined_grounded = proposals[(combined.scene_id, GROUNDED_OBJECTIVE_ID)]
    combined_spoiler = proposals[(combined.scene_id, SPOILER_OBJECTIVE_ID)]
    comparison_grounded = proposals[
        (grounded_comparison.scene_id, GROUNDED_OBJECTIVE_ID)
    ]
    comparison_spoiler = proposals[
        (spoiler_comparison.scene_id, SPOILER_OBJECTIVE_ID)
    ]
    expected_pairings = (
        (combined_grounded, grounded_comparison.scene_id),
        (comparison_grounded, combined.scene_id),
        (combined_spoiler, spoiler_comparison.scene_id),
        (comparison_spoiler, combined.scene_id),
    )
    for proposal, paired_scene_id in expected_pairings:
        if (
            proposal.pairing is None
            or proposal.pairing.paired_scene_id != paired_scene_id
        ):
            raise ValueError(
                f"proposal {proposal.proposal_id} lacks the required Scene pairing"
            )
        if (
            proposal.capture is not None
            or proposal.curation is not None
            or proposal.prop_relevance
        ):
            raise ValueError(
                f"book proposal {proposal.proposal_id} contains unrelated Ground truth"
            )

    if (
        combined_grounded.grounded_book_reflection is None
        or combined_grounded.grounded_book_reflection.retrieval != "required"
        or comparison_grounded.grounded_book_reflection is None
        or comparison_grounded.grounded_book_reflection.retrieval != "not_required"
        or combined_spoiler.spoiler_boundary is None
        or combined_spoiler.spoiler_boundary.decision != "infer"
        or comparison_spoiler.spoiler_boundary is None
        or comparison_spoiler.spoiler_boundary.decision != "clarify"
    ):
        raise ValueError("book replay Ground truth does not match the three-Scene design")

    props = {prop.prop_id: prop for prop in backstory.props}
    lines = {line.line_id: line for line in backstory.lines}
    cases = []
    for scene in sorted(backstory.scenes, key=lambda item: item.order):
        if not scene.fresh_session:
            raise ValueError(f"Scene {scene.scene_id} must use a fresh session")
        if scene.offline_input_ids or len(scene.line_ids) != 1:
            raise ValueError(
                f"Scene {scene.scene_id} must contain exactly one Line and no offline input"
            )
        line = lines[scene.line_ids[0]]
        if line.order != 1:
            raise ValueError(f"Scene {scene.scene_id} Line must have order 1")
        scene_props = tuple(props[prop_id] for prop_id in scene.prop_ids)
        for prop in scene_props:
            lifecycle = next(
                item for item in prop.lifecycle if item.scene_id == scene.scene_id
            )
            if lifecycle.state != "active":
                raise ValueError(
                    f"Scene {scene.scene_id} Prop {prop.prop_id} is not active"
                )
        if scene.scene_id == grounded_comparison.scene_id and scene_props:
            raise ValueError("grounded comparison Scene must have no Prop")
        if scene.scene_id != grounded_comparison.scene_id and len(scene_props) != 1:
            raise ValueError("both spoiler-boundary Scenes require the single Prop")
        scene_proposals = tuple(
            proposals[(scene.scene_id, objective_id)]
            for objective_id in scene.objective_ids
        )
        cases.append(
            _BookSceneCase(
                order=scene.order,
                scene_id=scene.scene_id,
                line_id=line.line_id,
                line=line.text,
                props=scene_props,
                proposals=scene_proposals,
            )
        )
    return tuple(cases)


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
            replay_book_scenes(
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
