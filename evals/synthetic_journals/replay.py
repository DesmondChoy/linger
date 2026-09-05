"""Replay capture-only Scenes through Linger's production chat boundary."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import tempfile
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Self
from uuid import uuid4

import logfire
from opentelemetry.trace import format_trace_id, get_current_span
from pydantic import Field, model_validator
from pydantic_evals import Case, Dataset
from pydantic_evals.dataset import set_eval_attribute
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from apps.backend import sessions
from apps.backend.schemas import CaptureInspection, ChatRequest, ChatResponse
from apps.backend.telemetry import configure_synthetic_evaluation_telemetry
from src.linger.agents.contracts import PromptFingerprint
from src.linger.agents.librarian.prompt import (
    PROMPT_FINGERPRINT as LIBRARIAN_PROMPT_FINGERPRINT,
)
from src.linger.agents.librarian.boundary_prompt import (
    PROMPT_FINGERPRINT as LIBRARIAN_BOUNDARY_PROMPT_FINGERPRINT,
)
from src.linger.agents.muse.prompt import (
    DRAFT_PROMPT_FINGERPRINT,
    REVISION_PROMPT_FINGERPRINT,
)
from src.linger.agents.provenance.emotional_prompt import (
    EMOTIONAL_BOUNDARY_PROMPT_FINGERPRINT,
)
from src.linger.agents.provenance.prompt import (
    PROMPT_FINGERPRINT as PROVENANCE_PROMPT_FINGERPRINT,
)
from src.linger.agents.provenance.curation_prompt import (
    PROMPT_FINGERPRINT as CURATION_PROVENANCE_PROMPT_FINGERPRINT,
)
from src.linger.agents.sculptor.prompt import (
    PROMPT_FINGERPRINT as SCULPTOR_PROMPT_FINGERPRINT,
)
from src.linger.agents.serendipity.prompt import (
    PROMPT_FINGERPRINT as SERENDIPITY_PROMPT_FINGERPRINT,
)
from src.linger.contracts.turn import ReleaseSource
from src.linger.evaluation_transcript import bind_evaluation_transcript_sink
from src.linger.services.memory import AccountContext, MemoryPolicyService

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
from .transcript import AgentExchange, SceneTranscriptRecorder
from .validate_package import PackageValidationError, validate_package_files

CAPTURE_OBJECTIVE_ID = "reviewed_automatic_memory_capture"

RUNTIME_PROMPT_FINGERPRINTS = (
    LIBRARIAN_BOUNDARY_PROMPT_FINGERPRINT,
    LIBRARIAN_PROMPT_FINGERPRINT,
    DRAFT_PROMPT_FINGERPRINT,
    REVISION_PROMPT_FINGERPRINT,
    EMOTIONAL_BOUNDARY_PROMPT_FINGERPRINT,
    PROVENANCE_PROMPT_FINGERPRINT,
    CURATION_PROVENANCE_PROMPT_FINGERPRINT,
    SCULPTOR_PROMPT_FINGERPRINT,
    SERENDIPITY_PROMPT_FINGERPRINT,
)
RUNTIME_SYSTEM_VARIANT = hashlib.sha256(
    json.dumps(
        [item.model_dump(mode="json") for item in RUNTIME_PROMPT_FINGERPRINTS],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()

ChatTurnHandler = Callable[
    [ChatRequest, MemoryPolicyService, AccountContext],
    Awaitable[ChatResponse],
]
GroundTruthStatus = Literal["proposed", "adopted"]
GroundTruthResult = Literal[
    "matches_proposal",
    "differs_from_proposal",
    "passes_hard_gates",
    "fails_hard_gates",
]


class SceneObservation(StrictModel):
    """Recorded production outcome for one Scene and its single Line."""

    scene_id: str
    line_id: str
    input_line: str
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    expected_capture_label: Literal["candidate", "no_candidate"]
    actual_capture_label: Literal["candidate", "no_candidate", "unavailable"]
    ground_truth_result: GroundTruthResult
    agent_exchanges: tuple[AgentExchange, ...]
    reply: str
    release_source: ReleaseSource
    boundary_origin: Literal["preflight", "candidate_review"] | None
    capture: CaptureInspection
    memory_id: str | None
    stored_text: str | None

    @model_validator(mode="after")
    def validate_boundary_origin(self) -> Self:
        is_boundary = self.release_source == "application_emotional_boundary"
        if is_boundary != (self.boundary_origin is not None):
            raise ValueError(
                "boundary_origin is required only for an emotional-boundary release"
            )
        return self


class EvaluationRun(StrictModel):
    """One isolated run of ordered capture-only Scenes."""

    artifact_schema_version: Literal["1"] = "1"
    content_classification: Literal["synthetic"] = "synthetic"
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    objective_id: Literal["reviewed_automatic_memory_capture"]
    dataset_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    system_variant: str = Field(pattern=r"^[0-9a-f]{64}$")
    ground_truth_status: GroundTruthStatus
    capture_enabled: Literal[True]
    runtime_prompt_fingerprints: tuple[PromptFingerprint, ...]
    scenes: tuple[SceneObservation, ...]
    final_active_memory_ids: tuple[str, ...]


class CaptureEvaluationInput(StrictModel):
    """Synthetic backstory shown as one native Logfire evaluation case input."""

    order: int = Field(ge=1)
    scene_id: str
    line_id: str
    line: str


class CaptureEvaluationExpected(StrictModel):
    """Proposed or human-adopted capture label shown as expected output."""

    capture_label: Literal["candidate", "no_candidate"]
    ground_truth_status: GroundTruthStatus


class CaptureEvaluationOutput(StrictModel):
    """Compact application result displayed by Logfire's Evals UI."""

    actual_capture_label: Literal["candidate", "no_candidate", "unavailable"]
    ground_truth_result: GroundTruthResult
    reply: str
    release_source: ReleaseSource
    capture: CaptureInspection


CaptureEvaluationResult = CaptureEvaluationExpected | CaptureEvaluationOutput


@dataclass(repr=False)
class CaptureGroundTruthEvaluator(
    Evaluator[
        CaptureEvaluationInput,
        CaptureEvaluationResult,
        dict[str, object],
    ]
):
    """Compare a proposal or grade an independently adopted capture label."""

    ground_truth_status: GroundTruthStatus

    def evaluate(
        self,
        ctx: EvaluatorContext[
            CaptureEvaluationInput,
            CaptureEvaluationResult,
            dict[str, object],
        ],
    ) -> str:
        expected = ctx.expected_output
        output = ctx.output
        if not isinstance(expected, CaptureEvaluationExpected):
            raise TypeError("capture evaluation expected output is unavailable")
        if not isinstance(output, CaptureEvaluationOutput):
            raise TypeError("capture evaluation task returned the wrong output")
        ground_truth_result = _ground_truth_result(
            matches=output.actual_capture_label == expected.capture_label,
            ground_truth_status=expected.ground_truth_status,
        )
        if output.ground_truth_result != ground_truth_result:
            raise ValueError("capture Ground truth result is inconsistent")
        return ground_truth_result

    def get_default_evaluation_name(self) -> str:
        if self.ground_truth_status == "adopted":
            return "adopted_hard_gate_grade"
        return "proposal_comparison"


def _ground_truth_result(
    *,
    matches: bool,
    ground_truth_status: GroundTruthStatus,
) -> GroundTruthResult:
    if ground_truth_status == "adopted":
        return "passes_hard_gates" if matches else "fails_hard_gates"
    return "matches_proposal" if matches else "differs_from_proposal"


async def replay_capture_scenes(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    *,
    adoption: GroundTruthAdoption | None = None,
    chat_handler: ChatTurnHandler | None = None,
) -> EvaluationRun:
    """Run ordered synthetic cases through Pydantic Evals and production chat."""

    scene_lines = _capture_scene_lines(backstory)
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
    proposals = {proposal.scene_id: proposal for proposal in ground_truth.proposals}
    cases: list[
        Case[
            CaptureEvaluationInput,
            CaptureEvaluationResult,
            dict[str, object],
        ]
    ] = []
    for order, (scene_id, line_id, line_text) in enumerate(scene_lines, start=1):
        proposal = proposals[scene_id]
        if proposal.capture is None:  # pragma: no cover - validator invariant
            raise RuntimeError(f"Scene {scene_id} has no capture proposal")
        expected_label: Literal["candidate", "no_candidate"] = (
            "candidate"
            if proposal.capture.kind == "capture_candidate"
            else "no_candidate"
        )
        cases.append(
            Case(
                name=scene_id,
                inputs=CaptureEvaluationInput(
                    order=order,
                    scene_id=scene_id,
                    line_id=line_id,
                    line=line_text,
                ),
                expected_output=CaptureEvaluationExpected(
                    capture_label=expected_label,
                    ground_truth_status=ground_truth_status,
                ),
                metadata={
                    "objective_id": CAPTURE_OBJECTIVE_ID,
                    "line_id": line_id,
                    "scene_order": order,
                    "ground_truth_status": ground_truth_status,
                },
            )
        )

    observations: list[SceneObservation] = []
    with tempfile.TemporaryDirectory(prefix="linger-synthetic-eval-") as directory:
        service = MemoryPolicyService(Path(directory))
        if service.capture_enabled(
            account
        ):  # pragma: no cover - fresh store invariant
            raise RuntimeError(
                "isolated evaluation account unexpectedly has capture enabled"
            )
        service.set_capture_enabled(account, True)

        async def evaluate_scene(
            inputs: CaptureEvaluationInput,
        ) -> CaptureEvaluationOutput:
            expected_order = len(observations) + 1
            if inputs.order != expected_order:
                raise RuntimeError(
                    "synthetic evaluation cases did not execute in Scene order"
                )
            expected = cases[inputs.order - 1].expected_output
            if not isinstance(expected, CaptureEvaluationExpected):
                raise RuntimeError("synthetic evaluation proposal is unavailable")
            observation = await _replay_capture_scene(
                inputs,
                expected,
                run_id=run_id,
                handler=handler,
                service=service,
                account=account,
            )
            observations.append(observation)
            return CaptureEvaluationOutput(
                actual_capture_label=observation.actual_capture_label,
                ground_truth_result=observation.ground_truth_result,
                reply=observation.reply,
                release_source=observation.release_source,
                capture=observation.capture,
            )

        dataset = Dataset(
            name=CAPTURE_OBJECTIVE_ID,
            cases=cases,
            evaluators=[
                CaptureGroundTruthEvaluator(
                    ground_truth_status=ground_truth_status
                )
            ],
        )
        report = await dataset.evaluate(
            evaluate_scene,
            name=f"{CAPTURE_OBJECTIVE_ID}-{run_id[:8]}",
            task_name="memory_capture_workflow",
            max_concurrency=1,
            progress=False,
            metadata={
                "content_classification": "synthetic",
                "objective_id": CAPTURE_OBJECTIVE_ID,
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

        active_ids = tuple(record.memory_id for record in service.list_active(account))

    return EvaluationRun(
        run_id=run_id,
        trace_id=report.trace_id or "0" * 32,
        objective_id=CAPTURE_OBJECTIVE_ID,
        dataset_version=dataset_version,
        system_variant=RUNTIME_SYSTEM_VARIANT,
        ground_truth_status=ground_truth_status,
        capture_enabled=True,
        runtime_prompt_fingerprints=RUNTIME_PROMPT_FINGERPRINTS,
        scenes=tuple(observations),
        final_active_memory_ids=active_ids,
    )


async def _replay_capture_scene(
    inputs: CaptureEvaluationInput,
    expected: CaptureEvaluationExpected,
    *,
    run_id: str,
    handler: ChatTurnHandler,
    service: MemoryPolicyService,
    account: AccountContext,
) -> SceneObservation:
    recorder = SceneTranscriptRecorder()
    session_id = f"synthetic-eval:{run_id}:session:{uuid4().hex}"
    turn_id = f"synthetic-eval:{run_id}:turn:{uuid4().hex}"
    request = ChatRequest(
        session_id=session_id,
        turn_id=turn_id,
        message=inputs.line,
    )
    try:
        with bind_evaluation_transcript_sink(recorder):
            response = await handler(request, service, account)
    finally:
        sessions.clear(session_id)

    release = response.inspection.release
    if release is None:
        raise RuntimeError(
            "production chat returned no release inspection for "
            f"Scene {inputs.scene_id}"
        )
    matching_records = tuple(
        record
        for record in service.list_active(account)
        if record.source_event_id == turn_id
    )
    if len(matching_records) > 1:
        raise RuntimeError(f"Scene {inputs.scene_id} created multiple memories")
    record = matching_records[0] if matching_records else None
    committed = release.capture.storage == "committed"
    if committed != (record is not None):
        raise RuntimeError(
            f"Scene {inputs.scene_id} capture inspection disagrees with storage"
        )
    actual_label = release.capture.nomination
    ground_truth_result = _ground_truth_result(
        matches=actual_label == expected.capture_label,
        ground_truth_status=expected.ground_truth_status,
    )
    set_eval_attribute("actual_capture_label", actual_label)
    set_eval_attribute(
        "ground_truth_result",
        ground_truth_result,
    )
    set_eval_attribute("release_source", release.release_source)
    set_eval_attribute("capture_storage", release.capture.storage)
    trace_id = format_trace_id(get_current_span().get_span_context().trace_id)
    return SceneObservation(
        scene_id=inputs.scene_id,
        line_id=inputs.line_id,
        input_line=inputs.line,
        trace_id=trace_id,
        expected_capture_label=expected.capture_label,
        actual_capture_label=actual_label,
        ground_truth_result=ground_truth_result,
        agent_exchanges=recorder.exchanges,
        reply=response.reply,
        release_source=release.release_source,
        boundary_origin=release.boundary_origin,
        capture=release.capture,
        memory_id=record.memory_id if record else None,
        stored_text=record.text if record else None,
    )


def _capture_scene_lines(
    backstory: SyntheticBackstory,
) -> tuple[tuple[str, str, str], ...]:
    if backstory.objective_ids != (CAPTURE_OBJECTIVE_ID,):
        raise ValueError(
            "capture replay requires only reviewed_automatic_memory_capture"
        )
    if backstory.props or backstory.offline_inputs:
        raise ValueError("capture replay does not accept Props or offline inputs")

    lines = {line.line_id: line for line in backstory.lines}
    scene_lines: list[tuple[str, str, str]] = []
    for scene in sorted(backstory.scenes, key=lambda item: item.order):
        if not scene.fresh_session:
            raise ValueError(f"Scene {scene.scene_id} must use a fresh session")
        if scene.prop_ids or scene.offline_input_ids:
            raise ValueError(
                f"Scene {scene.scene_id} cannot use Props or offline inputs"
            )
        if len(scene.line_ids) != 1:
            raise ValueError(f"Scene {scene.scene_id} must contain exactly one Line")
        line_id = scene.line_ids[0]
        line = lines[line_id]
        if line.order != 1:
            raise ValueError(f"Scene {scene.scene_id} Line must have order 1")
        scene_lines.append((scene.scene_id, line_id, line.text))
    return tuple(scene_lines)


def _production_chat_turn_handler() -> ChatTurnHandler:
    """Import the transport-independent production chat boundary."""

    from apps.backend.chat_turn import run_chat_turn

    return run_chat_turn


def evaluation_agents() -> tuple[Any, ...]:
    """Return every named Pydantic AI agent available to synthetic workflows."""

    from src.linger.agents.librarian.agent import (
        librarian_boundary_agent,
        librarian_strength_agent,
    )
    from src.linger.agents.muse.agent import muse_chat_agent
    from src.linger.agents.provenance.agent import provenance_agent
    from src.linger.agents.provenance.emotional import emotional_boundary_agent
    from src.linger.agents.sculptor.agent import sculptor_agent
    from src.linger.agents.serendipity.agent import serendipity_agent

    return (
        muse_chat_agent,
        provenance_agent,
        emotional_boundary_agent,
        librarian_boundary_agent,
        librarian_strength_agent,
        serendipity_agent,
        sculptor_agent,
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
            replay_capture_scenes(
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
