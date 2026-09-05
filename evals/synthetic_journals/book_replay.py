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
from pydantic_ai.models import Model
from pydantic_evals import Case, Dataset
from pydantic_evals.dataset import set_eval_attribute
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from apps.backend import sessions
from apps.backend.contracts import ContextResolution
from apps.backend.schemas import CaptureInspection, ChatRequest, ChatResponse
from apps.backend.telemetry import configure_synthetic_evaluation_telemetry
from src.linger.agents.contracts import PromptFingerprint
from src.linger.agents.librarian.models import (
    BoundaryInferenceDecision,
    PassageInferenceDecision,
)
from src.linger.contracts.librarian import (
    LIBRARIAN_RESPONSE_ADAPTER,
    LIBRARIAN_ROUTING_RESPONSE_ADAPTER,
    effective_route_response,
    ClarificationRequest,
    EvidenceRecord,
    PassageScope,
    RetrievalFailure,
    RetrievalResult,
)
from src.linger.contracts.turn import ReleaseSource
from src.linger.evaluation_transcript import bind_evaluation_transcript_sink
from src.linger.services.memory import (
    AccountContext,
    AutomaticMemoryCandidate,
    MemoryPolicyService,
)

from .book_contract import BookReplayPlan, ValidatedBookScene, compile_book_replay_plan
from .book_evidence import ResolvedCorpusSpan
from .book_semantics import SpoilerSemanticResult, review_spoiler_semantics
from .adoption import (
    GroundTruthAdoptionError,
    validate_ground_truth_adoption_files,
    validate_ground_truth_adoption,
)
from .models import (
    LibrarianInferredBookScope,
    ReaderConfirmedBookScope,
    GroundTruthAdoption,
    GroundTruthProposal,
    ProposedGroundTruth,
    StrictModel,
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


RuntimeEvidenceObservation = EvidenceRecord


class GroundingObservation(StrictModel):
    response_kind: Literal["clarification", "result", "failure"]
    call_outcome: str | None
    retrieval_outcome: Literal["evidence_found", "no_evidence"] | None = None
    searched_max_chapter: int | None = Field(default=None, ge=0)
    searched_passage_ids: tuple[str, ...] = ()
    work_id: str | None = None
    book_version_id: str | None = None
    evidence: tuple[RuntimeEvidenceObservation, ...] = ()
    clarification_question: str | None = None
    failure_code: str | None = None


class ObjectiveGrade(StrictModel):
    proposal_id: str
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
    boundary_decision: Literal["infer", "passages", "clarify", "not_applicable"]
    # The ceiling `librarian_route` actually granted, and the question it asked
    # instead. Both are None when Muse never routed this Scene.
    routed_ceiling: int | None = None
    routed_passage_ids: tuple[str, ...] = ()
    routed_work_id: str | None = None
    routed_book_version_id: str | None = None
    route_called: bool = False
    boundary_support_memory_ids: tuple[str, ...] = ()
    routed_clarification_question: str | None = None
    boundary_handoff_content_free: bool
    boundary_support_evidence: tuple[RuntimeEvidenceObservation, ...]
    grounding_calls: tuple[GroundingObservation, ...]
    released_evidence_ids: tuple[str, ...]
    reply: str
    release_source: ReleaseSource
    provenance_verdicts: tuple[Literal["pass", "revise", "reject"], ...]
    capture: CaptureInspection
    agent_exchanges: tuple[AgentExchange, ...]
    grades: tuple[ObjectiveGrade, ...]
    semantic_spoiler_results: tuple[SpoilerSemanticResult, ...] = ()
    ground_truth_result: GroundTruthResult


class BookEvaluationRun(StrictModel):
    artifact_schema_version: Literal["1"] = "1"
    content_classification: Literal["synthetic"] = "synthetic"
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    objective_ids: tuple[
        Literal["grounded_book_reflection", "spoiler_boundary_clarification"], ...
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
    boundary_decision: Literal["infer", "passages", "clarify", "not_applicable"]
    released_evidence_ids: tuple[str, ...]
    reply: str
    release_source: ReleaseSource


BookEvaluationResult = BookEvaluationExpected | BookEvaluationOutput


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
    plan: BookReplayPlan,
    *,
    adoption: GroundTruthAdoption | None = None,
    chat_handler: ChatTurnHandler | None = None,
    ground_truth_bytes: bytes | None = None,
    run_semantic_review: bool = False,
    semantic_model: Model | None = None,
) -> BookEvaluationRun:
    """Run every proposal in one compiled book evaluation plan."""

    backstory, ground_truth = plan.backstory, plan.ground_truth
    if adoption is not None:
        if ground_truth_bytes is None:
            raise ValueError(
                "adopted replay requires the exact Ground truth file bytes"
            )
        parsed = ProposedGroundTruth.model_validate_json(ground_truth_bytes)
        if parsed != ground_truth:
            raise ValueError("Ground truth bytes differ from the compiled plan")
        validate_ground_truth_adoption(
            ground_truth, adoption, ground_truth_bytes=ground_truth_bytes
        )
    scene_cases = plan.scenes
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
            name=scene.scene.scene_id,
            inputs=BookEvaluationInput(
                order=scene.scene.order,
                scene_id=scene.scene.scene_id,
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
                "objective_ids": [
                    proposal.objective_id for proposal in scene.proposals
                ],
                "scene_order": scene.scene.order,
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
            if scene.scene.scene_id != inputs.scene_id:
                raise RuntimeError("synthetic book Scene identity changed")
            service = MemoryPolicyService(
                root / f"{inputs.order:02d}-{inputs.scene_id}"
            )
            observation = await _replay_book_scene(
                scene,
                run_id=run_id,
                handler=handler,
                service=service,
                account=account,
                ground_truth_status=ground_truth_status,
            )
            semantic = []
            for proposal in scene.proposals:
                if proposal.objective_id != SPOILER_OBJECTIVE_ID:
                    continue
                semantic.append(
                    await review_spoiler_semantics(
                        scene, proposal, observation.reply, model=semantic_model
                    )
                    if run_semantic_review
                    else SpoilerSemanticResult(
                        scene_id=scene.scene.scene_id,
                        proposal_id=proposal.proposal_id,
                    )
                )
            observation = observation.model_copy(
                update={"semantic_spoiler_results": tuple(semantic)}
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
                "objective_ids": list(backstory.objective_ids),
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
        objective_ids=tuple(backstory.objective_ids),
        dataset_version=dataset_version,
        system_variant=RUNTIME_SYSTEM_VARIANT,
        ground_truth_status=ground_truth_status,
        runtime_prompt_fingerprints=RUNTIME_PROMPT_FINGERPRINTS,
        scenes=tuple(observations),
    )


async def _replay_book_scene(
    scene: ValidatedBookScene,
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
                f"Scene {scene.scene.scene_id} did not produce one production turn audit"
            )
        released_evidence_ids = turn_records[0].evidence_ids
    finally:
        sessions.clear(session_id)

    active = service.list_active(account)
    seeded_memory_ids = {item.memory_id for item in seeded}
    if {record.memory_id for record in active} != seeded_memory_ids:
        raise RuntimeError(
            f"Scene {scene.scene.scene_id} changed the pre-positioned Prop bank"
        )

    release = response.inspection.release
    if release is None:
        raise RuntimeError(f"Scene {scene.scene.scene_id} has no release inspection")
    context = ContextResolution.model_validate(response.inspection.context_resolution)
    grounding = _grounding_observations(response)
    exchanges = recorder.exchanges
    routed = _route_outcome(response)
    boundary_decision = _boundary_decision(routed)
    content_free = _boundary_handoff_is_content_free(
        boundary_decision,
        routed,
        exchanges,
    )
    boundary_support = _boundary_support_observations(exchanges, routed)
    selected_boundary = _boundary_exchange(exchanges, routed)

    provisional = BookSceneObservation(
        scene_id=scene.scene.scene_id,
        line_id=scene.line_id,
        input_line=scene.line,
        trace_id=format_trace_id(get_current_span().get_span_context().trace_id),
        seeded_props=seeded,
        context_resolution=context,
        boundary_decision=boundary_decision,
        routed_work_id=routed.get("work_id") if routed else None,
        routed_book_version_id=routed.get("book_version_id") if routed else None,
        route_called=any(
            call.get("tool_name") == "librarian_route"
            for call in response.inspection.librarian_grounding
        ),
        boundary_support_memory_ids=(
            tuple(selected_boundary.output.get("supporting_memory_ids", ()))
            if selected_boundary and isinstance(selected_boundary.output, dict)
            else ()
        ),
        routed_ceiling=(
            routed.get("max_chapter_inclusive") if routed is not None else None
        ),
        routed_passage_ids=(
            tuple(routed["evidence_ids"])
            if routed is not None and routed.get("kind") == "passages"
            else ()
        ),
        routed_clarification_question=(
            routed.get("question") if routed is not None else None
        ),
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
        _grade_proposal(scene, proposal, provisional) for proposal in scene.proposals
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
    scene: ValidatedBookScene,
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
                    f"synthetic-prop:{run_id}:{scene.scene.scene_id}:{prop.prop_id}"
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
        outcome_payload = call.get("response")
        if call["tool_name"] != "librarian_search":
            continue
        parsed = LIBRARIAN_RESPONSE_ADAPTER.validate_python(outcome_payload)
        outcome = call.get("outcome")
        call_outcome = outcome if isinstance(outcome, str) else None
        if isinstance(parsed, RetrievalResult):
            scope = parsed.searched_scope
            observations.append(
                GroundingObservation(
                    response_kind="result",
                    call_outcome=call_outcome,
                    retrieval_outcome=parsed.outcome,
                    searched_max_chapter=(
                        None if isinstance(scope, PassageScope)
                        else scope.max_chapter_inclusive
                    ),
                    searched_passage_ids=(
                        scope.evidence_ids if isinstance(scope, PassageScope) else ()
                    ),
                    work_id=scope.work_id,
                    book_version_id=scope.book_version_id,
                    evidence=tuple(_runtime_evidence(item) for item in parsed.evidence),
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
    return item


def _boundary_exchange(exchanges, routed):
    if routed is None:
        return None
    matching = tuple(
        exchange
        for exchange in exchanges
        if exchange.role == "Librarian"
        and exchange.stage == "boundary_inference"
        and exchange.correlation_id == routed["request_id"]
    )
    return matching[0] if len(matching) == 1 else None


def _boundary_support_observations(
    exchanges: tuple[AgentExchange, ...],
    routed: dict[str, object] | None,
) -> tuple[RuntimeEvidenceObservation, ...]:
    """Resolve the evidence the inference judge cited to set the ceiling.

    The judge's decision names supporting evidence IDs; the records themselves
    stay in the private full-work candidate set it was given. Neither reaches
    `ContextResolution`, so both are read back off the boundary exchange.
    """
    exchange = _boundary_exchange(exchanges, routed)
    if exchange is None:
        return ()
    output = exchange.output
    if not isinstance(output, dict):
        return ()
    supporting_ids = set(output.get("supporting_evidence_ids") or ())
    if not supporting_ids:
        return ()
    try:
        payload = json.loads(exchange.input_prompt)
        candidates = tuple(
            EvidenceRecord.model_validate(item)
            for item in payload["full_work_candidates"]
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return ()
    selected = tuple(
        _runtime_evidence(item)
        for item in candidates
        if item.evidence_id in supporting_ids
    )
    if {item.evidence_id for item in selected} != supporting_ids:
        return ()
    return selected


def _route_outcome(response: ChatResponse) -> dict[str, object] | None:
    routes = [
        LIBRARIAN_ROUTING_RESPONSE_ADAPTER.validate_python(call["response"])
        for call in response.inspection.librarian_grounding
        if call["tool_name"] == "librarian_route"
    ]
    result = effective_route_response(routes)
    return result.model_dump(mode="json") if result is not None else None


def _boundary_decision(
    routed: dict[str, object] | None,
) -> Literal["infer", "passages", "clarify", "not_applicable"]:
    if routed is None:
        return "not_applicable"
    if routed.get("kind") == "routed":
        return "infer"
    if routed.get("kind") == "passages":
        return "passages"
    if routed.get("kind") == "clarification":
        return "clarify"
    return "not_applicable"


def _boundary_handoff_is_content_free(
    decision: Literal["infer", "passages", "clarify", "not_applicable"],
    routed: dict[str, object] | None,
    exchanges: tuple[AgentExchange, ...],
) -> bool:
    exchange = _boundary_exchange(exchanges, routed)
    if decision == "not_applicable":
        return exchange is None
    if exchange is None:
        return decision == "clarify"
    output = exchange.output
    if decision == "passages" or (
        isinstance(output, dict) and output.get("outcome") == "passages"
    ):
        try:
            parsed = PassageInferenceDecision.model_validate(output)
            if decision == "clarify":
                ClarificationRequest.model_validate(routed)
                return True
        except ValueError:
            return False
        if decision != "passages":
            return False
        allowed_fields = {
            "kind", "request_id", "work_id", "book_version_id", "title",
            "routing_confidence", "boundary_confidence", "evidence_ids",
        }
        return (
            routed is not None
            and not set(routed) - allowed_fields
            and parsed.work_id == routed["work_id"]
            and parsed.book_version_id == routed["book_version_id"]
            and parsed.passage_evidence_ids == tuple(routed["evidence_ids"])
        )
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
    try:
        parsed = BoundaryInferenceDecision.model_validate(output)
    except ValueError:
        return False
    if decision == "infer" and (
        parsed.outcome != "candidate"
        or parsed.work_id != routed["work_id"]
        or parsed.book_version_id != routed["book_version_id"]
        or parsed.chapter_number != routed["max_chapter_inclusive"]
    ):
        return False
    # The routed hand-off names the work and its ceiling by number and
    # confidence only. Any story text appearing here would be a leak.
    allowed_routed_fields = {
        "kind",
        "work_id",
        "book_version_id",
        "title",
        "routing_confidence",
        "max_chapter_inclusive",
        "boundary_confidence",
        "request_id",
        "clarification_id",
        "reason_code",
        "question",
        "expected_answer",
    }
    if routed is not None and set(routed) - allowed_routed_fields:
        return False
    return True


def _scope_failures(
    scene: ValidatedBookScene, observation: BookSceneObservation
) -> list[str]:
    if scene.facts is None:
        return []
    failures = []
    scope = scene.facts.scope
    ceiling = scene.safe_ceiling_chapter
    if isinstance(scope, ReaderConfirmedBookScope):
        context = observation.context_resolution
        if (
            context.boundary_source != "reader_confirmed"
            or context.work_id != scope.work_id
            or context.book_version_id != scope.book_version_id
            or context.chapter_max != ceiling
        ):
            failures.append("reader_confirmed_scope_differs_from_ground_truth")
    elif isinstance(scope, LibrarianInferredBookScope):
        if (
            observation.routed_work_id != scope.work_id
            or observation.routed_book_version_id != scope.book_version_id
            or observation.routed_ceiling != ceiling
            or observation.boundary_decision != "infer"
        ):
            failures.append("inferred_scope_differs_from_ground_truth")
        if not observation.boundary_handoff_content_free:
            failures.append("boundary_handoff_not_content_free")
        expected_memories = {
            item.memory_id
            for item in observation.seeded_props
            if item.prop_id in scope.authorised_prop_ids
        }
        if set(observation.boundary_support_memory_ids) != expected_memories:
            failures.append("boundary_memory_support_differs_from_authorised_props")
        support = tuple(
            scene.evidence_by_id[key] for key in scope.supporting_evidence_ids
        )
        if not _evidence_sets_match(support, observation.boundary_support_evidence):
            failures.append("boundary_support_differs_from_ground_truth")
    for call in observation.grounding_calls:
        if call.response_kind != "result":
            failures.append("grounding_call_did_not_return_evidence_result")
            continue
        if (
            call.work_id != scope.work_id
            or call.book_version_id != scope.book_version_id
        ):
            failures.append("retrieval_scope_identity_differs_from_ground_truth")
        if (
            ceiling is None
            or call.searched_max_chapter is None
            or call.searched_max_chapter > ceiling
        ):
            failures.append("retrieval_exceeded_safe_ceiling")
        if any(
            item.work_id != scope.work_id
            or item.book_version_id != scope.book_version_id
            or ceiling is None
            or item.chapter_number > ceiling
            for item in call.evidence
        ):
            failures.append("evidence_exceeded_safe_scope")
    return failures


def _grade_proposal(
    scene: ValidatedBookScene,
    proposal: GroundTruthProposal,
    observation: BookSceneObservation,
) -> ObjectiveGrade:
    if observation.boundary_decision == "passages" or any(
        call.searched_passage_ids for call in observation.grounding_calls
    ):
        return ObjectiveGrade(
            proposal_id=proposal.proposal_id,
            objective_id=proposal.objective_id,
            hard_pass=False,
            failures=("passage_scope_outside_chapter_objective",),
        )
    failures = _scope_failures(scene, observation)
    clarification_released = (
        observation.release_source == "application_clarification"
        and observation.boundary_decision == "clarify"
        and observation.reply == observation.routed_clarification_question
    )
    if observation.release_source != "muse_candidate" and not clarification_released:
        failures.append("response_not_released_from_allowed_source")
    if (
        not observation.provenance_verdicts
        or observation.provenance_verdicts[-1] != "pass"
    ):
        failures.append("provenance_did_not_pass_release")
    if observation.capture.storage == "committed":
        failures.append("unexpected_runtime_memory_capture")

    if proposal.objective_id == GROUNDED_OBJECTIVE_ID:
        expected = proposal.book_expectation
        if expected is None:  # pragma: no cover - package validator invariant
            raise RuntimeError("grounded proposal lacks typed expectation")
        actual_evidence = tuple(
            item for call in observation.grounding_calls for item in call.evidence
        )
        released = set(observation.released_evidence_ids)
        evidence = scene.evidence_by_id
        permitted = tuple(
            evidence[evidence_id] for evidence_id in expected.permitted_evidence_ids
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
            if any(
                not any(_evidence_matches(reference, item) for reference in permitted)
                for item in actual_evidence
            ):
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
                    or item.authored.text not in observation.reply
                ):
                    failures.append(
                        f"exact_quotation_missing_or_unreleased:{evidence_id}"
                    )
        else:
            if observation.route_called:
                failures.append("non_factual_reflection_triggered_boundary_inference")
            if not observation.boundary_handoff_content_free:
                failures.append("non_factual_reflection_used_boundary_inference")
            if observation.grounding_calls or released:
                failures.append("non_factual_reflection_used_book_evidence")
    elif proposal.objective_id == SPOILER_OBJECTIVE_ID:
        expected = proposal.book_expectation
        if expected is None:  # pragma: no cover - package validator invariant
            raise RuntimeError("spoiler proposal lacks typed expectation")
        scope = scene.facts.scope
        if not set(scope.authorised_prop_ids) <= {
            item.prop_id for item in observation.seeded_props
        }:
            failures.append("scene_prop_bank_differs_from_authorised_props")
        decision = (
            "infer" if isinstance(scope, LibrarianInferredBookScope) else "clarify"
        )
        if observation.boundary_decision != decision:
            failures.append("boundary_decision_differs_from_ground_truth")
        if not observation.boundary_handoff_content_free:
            failures.append("boundary_handoff_not_content_free")
        evidence = scene.evidence_by_id
        if decision == "infer":
            safe_ceiling = scene.safe_ceiling_chapter
            if safe_ceiling is None:  # pragma: no cover - model invariant
                raise RuntimeError("inferred boundary lacks a safe ceiling")
            if observation.routed_ceiling != safe_ceiling:
                failures.append("inferred_ceiling_differs_from_ground_truth")
            expected_support = tuple(
                evidence[evidence_id] for evidence_id in scope.supporting_evidence_ids
            )
            if not _evidence_sets_match(
                expected_support,
                observation.boundary_support_evidence,
            ):
                failures.append("boundary_support_differs_from_ground_truth")
            for call in observation.grounding_calls:
                if (
                    call.searched_max_chapter is not None
                    and call.searched_max_chapter > safe_ceiling
                ):
                    failures.append("retrieval_exceeded_safe_ceiling")
                if any(item.chapter_number > safe_ceiling for item in call.evidence):
                    failures.append("evidence_exceeded_safe_ceiling")
        else:
            if observation.routed_ceiling is not None:
                failures.append("clarification_scene_granted_retrieval_scope")
            question = observation.routed_clarification_question
            if question is None:
                failures.append("clarification_question_missing")
            elif observation.reply != question:
                failures.append("released_reply_differs_from_clarification")
            if observation.grounding_calls or observation.released_evidence_ids:
                failures.append("clarification_scene_retrieved_evidence")

        forbidden_evidence = tuple(
            evidence[evidence_id]
            for evidence_id in expected.forbidden_later_evidence_ids
        )
        observed_evidence = observation.boundary_support_evidence + tuple(
            item for call in observation.grounding_calls for item in call.evidence
        )
        if any(
            _evidence_matches(reference, actual)
            for reference in forbidden_evidence
            for actual in observed_evidence
        ):
            failures.append("forbidden_later_evidence_used")
        if any(
            evidence[evidence_id].authored.text.casefold()
            in observation.reply.casefold()
            for evidence_id in expected.forbidden_later_evidence_ids
        ):
            failures.append("forbidden_later_fact_disclosed")
    else:  # pragma: no cover - topology validation rejects this earlier
        raise RuntimeError(f"unsupported book Objective {proposal.objective_id}")

    return ObjectiveGrade(
        proposal_id=proposal.proposal_id,
        objective_id=proposal.objective_id,
        hard_pass=not failures,
        failures=tuple(dict.fromkeys(failures)),
    )


def _evidence_matches(
    expected: ResolvedCorpusSpan, actual: RuntimeEvidenceObservation
) -> bool:
    return actual in expected.accepted_runtime_records


def _evidence_sets_match(
    expected: tuple[ResolvedCorpusSpan, ...],
    actual: tuple[RuntimeEvidenceObservation, ...],
) -> bool:
    return (
        bool(expected)
        and bool(actual)
        and all(
            any(_evidence_matches(reference, item) for item in actual)
            for reference in expected
        )
        and all(
            any(_evidence_matches(reference, item) for reference in expected)
            for item in actual
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backstory", type=Path)
    parser.add_argument("ground_truth", type=Path)
    parser.add_argument("--adoption", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--semantic-review", action="store_true")
    args = parser.parse_args(argv)

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
        result = asyncio.run(
            replay_book_scenes(
                compile_book_replay_plan(backstory, ground_truth),
                adoption=adoption,
                ground_truth_bytes=args.ground_truth.read_bytes(),
                run_semantic_review=args.semantic_review,
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
