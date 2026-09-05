"""Replay reflection-and-grounding Scenes through Linger's production chat.

Specification flow 4.2.1. Unlike capture replay, a Scene here may carry Props:
the remembered events that let Librarian infer a spoiler ceiling are placed in
the account's store before the Scene runs, through the same
`MemoryPolicyService` the product uses. A Scene may also send an ordered
sequence of Lines in one session rather than a single Line.

Grading is deterministic hard gates only — the release path taken, whether
retrieval happened, which evidence the released reply cited, and the resolved
ceiling. Whether the reflection reads well stays separately reviewable.
"""

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
from pydantic_evals.dataset import set_eval_attribute
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from apps.backend import sessions
from apps.backend.hybrid_librarian import _windows
from apps.backend.librarian import _paragraphs
from apps.backend.schemas import ChatRequest, ChatResponse
from apps.backend.telemetry import configure_synthetic_evaluation_telemetry
from evals.reflection.harness import GroundingExpectation, ReleaseSource
from src.linger.agents.contracts import PromptFingerprint
from src.linger.contracts.librarian import (
    LIBRARIAN_RESPONSE_ADAPTER,
    LIBRARIAN_ROUTING_RESPONSE_ADAPTER,
    RetrievalResult,
    RoutedWork,
)
from src.linger.corpus.book import parse_chapter_markdown
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
    EvidenceReference,
    GroundTruthAdoption,
    Prop,
    ProposedGroundTruth,
    RepositoryTextEvidence,
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
from .validate_package import (
    PackageValidationError,
    REFLECTION_OBJECTIVE_IDS,
    REPOSITORY_ROOT,
    validate_package_files,
)

FailureStage = Literal[
    "emotional_boundary_preflight",
    "muse_draft",
    "provenance_review",
    "muse_revision",
    "deterministic_validation",
]
FailureType = Literal["application", "model", "validation"]

GateFailure = Literal[
    "release_source_mismatch",
    "unexpected_retrieval",
    "missing_retrieval",
    "missing_citation",
    "unpermitted_evidence",
    "ceiling_mismatch",
    "forbidden_fact_disclosed",
]


class SceneTurn(StrictModel):
    """One Line and the reply it produced inside a Scene's session."""

    line_id: str
    input_line: str
    reply: str
    release_source: ReleaseSource
    retrieved: bool
    released_evidence_ids: tuple[str, ...]
    resolved_chapter_max: int | None
    # Which stage failed, and whether it was infrastructure or a real verdict.
    # Without these a provider fault and a semantic rejection look identical.
    failure_stage: FailureStage | None = None
    failure_type: FailureType | None = None
    failure_retryable: bool | None = None

    @property
    def infrastructure_failure(self) -> bool:
        """Report whether this turn declined because an agent call never ran."""
        return self.failure_type == "model"


class SceneObservation(StrictModel):
    """Recorded production outcome for one reflection Scene."""

    scene_id: str
    objective_id: str
    primary_behavior: str
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    prop_ids: tuple[str, ...]
    turns: tuple[SceneTurn, ...] = Field(min_length=1)
    gate_failures: tuple[GateFailure, ...]
    ground_truth_result: GroundTruthResult
    agent_exchanges: tuple[AgentExchange, ...]

    @property
    def infrastructure_failure(self) -> bool:
        """Report whether any turn declined because an agent call never ran.

        A Scene that failed this way measures the provider, not Linger; its gate
        failures describe a decline nothing semantic caused (see D9).
        """
        return any(turn.infrastructure_failure for turn in self.turns)


class EvaluationRun(StrictModel):
    """One isolated run of ordered reflection Scenes."""

    artifact_schema_version: Literal["1"] = "1"
    content_classification: Literal["synthetic"] = "synthetic"
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    objective_ids: tuple[str, ...] = Field(min_length=1)
    dataset_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    system_variant: str = Field(pattern=r"^[0-9a-f]{64}$")
    ground_truth_status: GroundTruthStatus
    capture_enabled: Literal[False] = False
    runtime_prompt_fingerprints: tuple[PromptFingerprint, ...]
    scenes: tuple[SceneObservation, ...]


class ReflectionEvaluationInput(StrictModel):
    """One Scene's ordered Lines and pre-positioned Props."""

    order: int = Field(ge=1)
    scene_id: str
    objective_id: str
    prop_ids: tuple[str, ...]
    lines: tuple[tuple[str, str], ...] = Field(min_length=1)


class ReflectionEvaluationExpected(StrictModel):
    """Proposed or adopted grounding expectation shown as expected output."""

    grounding: GroundingExpectation
    ground_truth_status: GroundTruthStatus
    # Permitted evidence translated into the IDs a released citation names.
    permitted_evidence_ids: tuple[str, ...] = ()


class ReflectionEvaluationOutput(StrictModel):
    """Compact application result displayed by Logfire's Evals UI."""

    gate_failures: tuple[GateFailure, ...]
    ground_truth_result: GroundTruthResult
    turns: tuple[SceneTurn, ...]


ReflectionEvaluationResult = (
    ReflectionEvaluationExpected | ReflectionEvaluationOutput
)


@dataclass(repr=False)
class ReflectionGroundTruthEvaluator(
    Evaluator[
        ReflectionEvaluationInput,
        ReflectionEvaluationResult,
        dict[str, object],
    ]
):
    """Compare a proposal or grade adopted reflection hard gates."""

    ground_truth_status: GroundTruthStatus

    def evaluate(
        self,
        ctx: EvaluatorContext[
            ReflectionEvaluationInput,
            ReflectionEvaluationResult,
            dict[str, object],
        ],
    ) -> str:
        expected = ctx.expected_output
        output = ctx.output
        if not isinstance(expected, ReflectionEvaluationExpected):
            raise TypeError("reflection evaluation expected output is unavailable")
        if not isinstance(output, ReflectionEvaluationOutput):
            raise TypeError("reflection evaluation task returned the wrong output")
        ground_truth_result = _ground_truth_result(
            matches=not output.gate_failures,
            ground_truth_status=expected.ground_truth_status,
        )
        if output.ground_truth_result != ground_truth_result:
            raise ValueError("reflection Ground truth result is inconsistent")
        return ground_truth_result

    def get_default_evaluation_name(self) -> str:
        if self.ground_truth_status == "adopted":
            return "adopted_hard_gate_grade"
        return "proposal_comparison"


class EvidenceResolutionError(ValueError):
    """Ground truth names a span no corpus paragraph can produce."""


def resolve_corpus_evidence_ids(
    evidence: RepositoryTextEvidence,
    repository_root: Path = REPOSITORY_ROOT,
) -> frozenset[str]:
    """Map one package evidence span to every ID Librarian could cite for it.

    Ground truth locates evidence by repository path and code-point span, while
    a released citation names `{chapter_id}-ln{start}-{end}` built from the
    Gutenberg source lines of the retrieved *window*. The two namespaces never
    compare directly. Retrieval windows overlap and span several paragraphs, so
    one span legitimately resolves to more than one citable ID — any window
    containing the ground-truth text is a correct citation of it.
    """
    path = repository_root / evidence.repository_path
    raw = path.read_text(encoding="utf-8")
    metadata, body = parse_chapter_markdown(raw)
    paragraphs = _paragraphs(metadata, body)
    resolved = {
        candidate.evidence_id
        for candidate in _windows(metadata, paragraphs)
        if evidence.text in candidate.text
    }
    if not resolved:
        raise EvidenceResolutionError(
            f"evidence {evidence.evidence_id} text is in no retrieval window of "
            f"{evidence.repository_path}"
        )
    return frozenset(resolved)


def permitted_corpus_ids(
    grounding: GroundingExpectation,
    evidence: Sequence[EvidenceReference],
    repository_root: Path = REPOSITORY_ROOT,
) -> frozenset[str]:
    """Translate a proposal's permitted evidence into released-citation IDs."""
    permitted = grounding.permitted_evidence_ids
    return frozenset(
        evidence_id
        for item in evidence
        if item.evidence_id in permitted
        and isinstance(item, RepositoryTextEvidence)
        for evidence_id in resolve_corpus_evidence_ids(item, repository_root)
    )


def grade_scene(
    grounding: GroundingExpectation,
    turns: Sequence[SceneTurn],
    permitted_evidence_ids: frozenset[str] | None = None,
) -> tuple[GateFailure, ...]:
    """Grade one Scene's turns against its expectation, deterministically.

    `permitted_evidence_ids` holds released-citation IDs resolved by
    `permitted_corpus_ids`. It defaults to the expectation's own IDs so unit
    tests can grade without the corpus.
    """
    failures: list[GateFailure] = []
    final = turns[-1]

    if final.release_source != grounding.release_source:
        failures.append("release_source_mismatch")

    retrieved = any(turn.retrieved for turn in turns)
    if retrieved and not grounding.retrieval_required:
        failures.append("unexpected_retrieval")
    if grounding.retrieval_required and not retrieved:
        failures.append("missing_retrieval")

    permitted = (
        grounding.permitted_evidence_ids
        if permitted_evidence_ids is None
        else permitted_evidence_ids
    )
    cited = {
        evidence_id
        for turn in turns
        for evidence_id in turn.released_evidence_ids
    }
    if cited - permitted:
        failures.append("unpermitted_evidence")
    if grounding.retrieval_required and not final.released_evidence_ids:
        failures.append("missing_citation")

    expected_ceiling = getattr(grounding.expected, "chapter_max", None)
    if expected_ceiling is not None and any(
        turn.resolved_chapter_max != expected_ceiling
        for turn in turns
        if turn.retrieved
    ):
        failures.append("ceiling_mismatch")

    replies = " ".join(turn.reply for turn in turns).casefold()
    if any(
        fact.casefold() in replies
        for fact in grounding.forbidden_post_boundary_facts
    ):
        failures.append("forbidden_fact_disclosed")

    return tuple(failures)


async def replay_reflection_scenes(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    *,
    adoption: GroundTruthAdoption | None = None,
    chat_handler: ChatTurnHandler | None = None,
) -> EvaluationRun:
    """Run ordered reflection Scenes through Pydantic Evals and production chat."""

    scenes = _reflection_scenes(backstory, ground_truth)
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
    props = {prop.prop_id: prop for prop in backstory.props}
    cases: list[
        Case[
            ReflectionEvaluationInput,
            ReflectionEvaluationResult,
            dict[str, object],
        ]
    ] = []
    for order, (scene, proposal) in enumerate(scenes, start=1):
        lines = {line.line_id: line for line in backstory.lines}
        cases.append(
            Case(
                name=scene.scene_id,
                inputs=ReflectionEvaluationInput(
                    order=order,
                    scene_id=scene.scene_id,
                    objective_id=proposal.objective_id,
                    prop_ids=scene.prop_ids,
                    lines=tuple(
                        (line_id, lines[line_id].text)
                        for line_id in sorted(
                            scene.line_ids, key=lambda item: lines[item].order
                        )
                    ),
                ),
                expected_output=ReflectionEvaluationExpected(
                    grounding=proposal.grounding,
                    ground_truth_status=ground_truth_status,
                    permitted_evidence_ids=tuple(
                        sorted(
                            permitted_corpus_ids(
                                proposal.grounding, proposal.evidence
                            )
                        )
                    ),
                ),
                metadata={
                    "objective_id": proposal.objective_id,
                    "primary_behavior": proposal.grounding.primary_behavior,
                    "scene_order": order,
                    "ground_truth_status": ground_truth_status,
                },
            )
        )

    objective_ids = tuple(
        dict.fromkeys(proposal.objective_id for _, proposal in scenes)
    )
    observations: list[SceneObservation] = []
    with tempfile.TemporaryDirectory(prefix="linger-reflection-eval-") as directory:
        service = MemoryPolicyService(Path(directory))

        async def evaluate_scene(
            inputs: ReflectionEvaluationInput,
        ) -> ReflectionEvaluationOutput:
            expected_order = len(observations) + 1
            if inputs.order != expected_order:
                raise RuntimeError(
                    "synthetic evaluation cases did not execute in Scene order"
                )
            expected = cases[inputs.order - 1].expected_output
            if not isinstance(expected, ReflectionEvaluationExpected):
                raise RuntimeError("synthetic evaluation proposal is unavailable")
            observation = await _replay_reflection_scene(
                inputs,
                expected,
                run_id=run_id,
                handler=handler,
                service=service,
                # One account per Scene: a Scene is graded as a unit with only
                # its own designated Props, so no Scene inherits another's.
                account=AccountContext(f"{account.account_id}:{inputs.scene_id}"),
                props=props,
            )
            observations.append(observation)
            return ReflectionEvaluationOutput(
                gate_failures=observation.gate_failures,
                ground_truth_result=observation.ground_truth_result,
                turns=observation.turns,
            )

        dataset = Dataset(
            name="reflection_and_grounding",
            cases=cases,
            evaluators=[
                ReflectionGroundTruthEvaluator(
                    ground_truth_status=ground_truth_status
                )
            ],
        )
        report = await dataset.evaluate(
            evaluate_scene,
            name=f"reflection-and-grounding-{run_id[:8]}",
            task_name="reflection_and_grounding_workflow",
            max_concurrency=1,
            progress=False,
            metadata={
                "content_classification": "synthetic",
                "objective_ids": list(objective_ids),
                "run_id": run_id,
                "dataset_version": dataset_version,
                "system_variant": RUNTIME_SYSTEM_VARIANT,
                "ground_truth_status": ground_truth_status,
                "ground_truth_evaluation": evaluation_name,
            },
        )
        if report.failures:
            failed_cases = [failure.name for failure in report.failures]
            raise RuntimeError(f"synthetic evaluation cases failed: {failed_cases}")
        if len(observations) != len(cases):
            raise RuntimeError("synthetic evaluation did not produce every Scene")

    return EvaluationRun(
        run_id=run_id,
        trace_id=report.trace_id or "0" * 32,
        objective_ids=objective_ids,
        dataset_version=dataset_version,
        system_variant=RUNTIME_SYSTEM_VARIANT,
        ground_truth_status=ground_truth_status,
        runtime_prompt_fingerprints=RUNTIME_PROMPT_FINGERPRINTS,
        scenes=tuple(observations),
    )


def _place_props(
    scene_prop_ids: Sequence[str],
    props: dict[str, Prop],
    service: MemoryPolicyService,
    account: AccountContext,
) -> None:
    """Position a Scene's Props before it runs, through the production service.

    Capture stays disabled for the Scene itself: a Prop is pre-existing state,
    never an outcome the Scene produced.
    """
    if not scene_prop_ids:
        return
    service.set_capture_enabled(account, True)
    try:
        for prop_id in scene_prop_ids:
            service.save_automatic(
                account,
                AutomaticMemoryCandidate(
                    text=props[prop_id].source_text,
                    source_event_id=f"prop:{prop_id}",
                    review_allows_capture=True,
                    contains_sensitive_content=False,
                ),
            )
    finally:
        service.set_capture_enabled(account, False)


def _observed_book_grounding(response: ChatResponse) -> tuple[bool, int | None]:
    """Read completed retrieval and effective authority from typed tool outcomes."""
    ceiling = response.inspection.context_resolution.get("chapter_max")
    retrieved = False
    for call in response.inspection.librarian_grounding:
        if call.get("outcome") != "success":
            continue
        payload = call.get("response")
        if not isinstance(payload, dict):
            raise ValueError("Librarian inspection lacks a typed response")
        if payload.get("kind") in {"routed", "no_match"}:
            routed = LIBRARIAN_ROUTING_RESPONSE_ADAPTER.validate_python(payload)
            if isinstance(routed, RoutedWork) and ceiling is None:
                ceiling = routed.max_chapter_inclusive
        else:
            result = LIBRARIAN_RESPONSE_ADAPTER.validate_python(payload)
            retrieved = retrieved or isinstance(result, RetrievalResult)
    return retrieved, ceiling


async def _replay_reflection_scene(
    inputs: ReflectionEvaluationInput,
    expected: ReflectionEvaluationExpected,
    *,
    run_id: str,
    handler: ChatTurnHandler,
    service: MemoryPolicyService,
    account: AccountContext,
    props: dict[str, Prop],
) -> SceneObservation:
    from opentelemetry.trace import format_trace_id, get_current_span

    _place_props(inputs.prop_ids, props, service, account)
    recorder = SceneTranscriptRecorder()
    session_id = f"synthetic-eval:{run_id}:session:{uuid4().hex}"
    turns: list[SceneTurn] = []

    try:
        with bind_evaluation_transcript_sink(recorder):
            for line_id, line_text in inputs.lines:
                response = await handler(
                    ChatRequest(
                        session_id=session_id,
                        turn_id=f"synthetic-eval:{run_id}:turn:{uuid4().hex}",
                        message=line_text,
                    ),
                    service,
                    account,
                )
                release = response.inspection.release
                if release is None:
                    raise RuntimeError(
                        "production chat returned no release inspection for "
                        f"Scene {inputs.scene_id}"
                    )
                retrieved, ceiling = _observed_book_grounding(response)
                turns.append(
                    SceneTurn(
                        line_id=line_id,
                        input_line=line_text,
                        reply=response.reply,
                        release_source=release.release_source,
                        retrieved=retrieved,
                        released_evidence_ids=release.released_evidence_ids,
                        resolved_chapter_max=ceiling,
                        failure_stage=release.failure_stage,
                        failure_type=release.failure_type,
                        failure_retryable=release.failure_retryable,
                    )
                )
    finally:
        sessions.clear(session_id)

    stored = service.list_active(account)
    if len(stored) != len(inputs.prop_ids):
        raise RuntimeError(
            f"Scene {inputs.scene_id} changed stored memory: expected "
            f"{len(inputs.prop_ids)} Props, found {len(stored)} records"
        )

    gate_failures = grade_scene(
        expected.grounding,
        turns,
        frozenset(expected.permitted_evidence_ids),
    )
    ground_truth_result = _ground_truth_result(
        matches=not gate_failures,
        ground_truth_status=expected.ground_truth_status,
    )
    set_eval_attribute("gate_failures", list(gate_failures))
    set_eval_attribute("ground_truth_result", ground_truth_result)
    set_eval_attribute("release_source", turns[-1].release_source)
    set_eval_attribute("retrieved", any(turn.retrieved for turn in turns))
    set_eval_attribute("failure_stage", turns[-1].failure_stage)
    set_eval_attribute(
        "infrastructure_failure",
        any(turn.infrastructure_failure for turn in turns),
    )
    return SceneObservation(
        scene_id=inputs.scene_id,
        objective_id=inputs.objective_id,
        primary_behavior=expected.grounding.primary_behavior,
        trace_id=format_trace_id(get_current_span().get_span_context().trace_id),
        prop_ids=inputs.prop_ids,
        turns=tuple(turns),
        gate_failures=gate_failures,
        ground_truth_result=ground_truth_result,
        agent_exchanges=recorder.exchanges,
    )


def _reflection_scenes(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
):
    """Order the Scenes this runner accepts, rejecting anything it cannot grade."""
    unsupported = set(backstory.objective_ids) - REFLECTION_OBJECTIVE_IDS
    if unsupported:
        raise ValueError(
            f"reflection replay does not accept Objectives: {sorted(unsupported)}"
        )
    if backstory.offline_inputs:
        raise ValueError("reflection replay does not accept offline inputs")

    proposals = {
        (proposal.scene_id, proposal.objective_id): proposal
        for proposal in ground_truth.proposals
    }
    ordered = []
    for scene in sorted(backstory.scenes, key=lambda item: item.order):
        if not scene.fresh_session:
            raise ValueError(f"Scene {scene.scene_id} must use a fresh session")
        if not scene.line_ids:
            raise ValueError(f"Scene {scene.scene_id} requires at least one Line")
        objective_id = next(iter(scene.objective_ids))
        proposal = proposals.get((scene.scene_id, objective_id))
        if proposal is None or proposal.grounding is None:
            raise ValueError(
                f"Scene {scene.scene_id} has no grounding Ground truth"
            )
        ordered.append((scene, proposal))
    return tuple(ordered)


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
                    args.backstory, args.ground_truth, args.adoption
                )
            )
    except (PackageValidationError, GroundTruthAdoptionError) as error:
        print(f"PACKAGE_VALIDATION_FAILED={error}", file=sys.stderr)
        return 1

    try:
        run = asyncio.run(
            replay_reflection_scenes(backstory, ground_truth, adoption=adoption)
        )
    except ValueError as error:
        print(f"REFLECTION_REPLAY_REJECTED={error}", file=sys.stderr)
        return 1
    payload = run.model_dump_json(indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    failed = sum(1 for scene in run.scenes if scene.gate_failures)
    infrastructure = sum(1 for scene in run.scenes if scene.infrastructure_failure)
    print(
        f"REFLECTION_REPLAY_OK={len(run.scenes)} scenes,{failed} with gate "
        f"failures,{infrastructure} from agent-call failures"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
