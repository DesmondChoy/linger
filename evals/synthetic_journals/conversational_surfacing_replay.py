"""Replay the versioned ordered 4.2.5 conversational contract."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field

from apps.backend import sessions
from apps.backend.schemas import ChatRequest, ChatResponse
from src.linger.agents.contracts import PromptFingerprint
from src.linger.evaluation_transcript import bind_evaluation_transcript_sink
from src.linger.services.memory import (
    AccountContext,
    AutomaticMemoryCandidate,
    MemoryPolicyService,
    memory_record_sha256,
)

from .adoption import GroundTruthAdoptionError, validate_ground_truth_adoption_files
from .conversational_surfacing_contract import (
    CompiledConversationalScene,
    ConversationalContractError,
    compile_conversational_scenes,
)
from .models import (
    ConversationalSourceReference,
    GroundTruthAdoption,
    ProposedGroundTruth,
    StrictModel,
    SyntheticBackstory,
)
from .replay import (
    GroundTruthStatus,
    RUNTIME_PROMPT_FINGERPRINTS,
    RUNTIME_SYSTEM_VARIANT,
    _production_chat_turn_handler,
)
from .transcript import AgentExchange, SceneTranscriptRecorder
from .validate_scenario import ScenarioValidationError, validate_scenario_files


CONVERSATIONAL_OBJECTIVE_ID = "proactive_memory_surfacing"
class ConversationalSceneObservation(StrictModel):
    """Content-safe outcome carried from one ordered Scene to the next."""

    scene_id: str
    kind: Literal["capture", "surfacing"]
    line_id: str
    line: str
    created_memory_ids: tuple[str, ...]
    active_memory_ids: tuple[str, ...]
    curation_status: str | None
    surfacing_decision: Literal["surface_now", "defer", "do_not_surface"] | None
    surfacing_source_ids: tuple[str, ...]
    release_source: str
    hard_failures: tuple[str, ...]
    ground_truth_result: Literal[
        "matches_proposal", "differs_from_proposal", "passes_hard_gates", "fails_hard_gates"
    ]
    agent_exchanges: tuple[AgentExchange, ...] = ()


class ConversationalEvaluationRun(StrictModel):
    """One ordered production replay with observed runtime dependencies."""

    artifact_schema_version: Literal["1"] = "1"
    content_classification: Literal["synthetic"] = "synthetic"
    scenario_contract: Literal["conversational_v1"] = "conversational_v1"
    objective_id: Literal["proactive_memory_surfacing"] = CONVERSATIONAL_OBJECTIVE_ID
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    dataset_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    ground_truth_status: GroundTruthStatus
    runtime_prompt_fingerprints: tuple[PromptFingerprint, ...] = ()
    scenes: tuple[ConversationalSceneObservation, ...]
    final_active_memory_ids: tuple[str, ...]


async def replay_conversational_scenes(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    *,
    adoption: GroundTruthAdoption | None = None,
    chat_handler=None,
    configured_model: str | None = None,
) -> ConversationalEvaluationRun:
    """Run ordered Lines against one isolated account and carry real state."""

    compiled = compile_conversational_scenes(backstory, ground_truth)
    if configured_model is not None and chat_handler is None:
        raise ValueError("configured_model requires an injected chat handler")
    status: GroundTruthStatus = (
        adoption.ground_truth_status
        if adoption is not None
        else ground_truth.ground_truth_status
    )
    run_id = uuid4().hex
    account = AccountContext(
        f"synthetic-eval:{backstory.backstory.evaluation_account_id}:{run_id}"
    )
    handler = chat_handler or _production_chat_turn_handler()
    prop_records: dict[str, str] = {}
    observations: list[ConversationalSceneObservation] = []

    with tempfile.TemporaryDirectory(prefix="linger-conversational-eval-") as directory:
        service = MemoryPolicyService(Path(directory))
        service.set_capture_enabled(account, True)
        first_scene = compiled[0].scene.scene_id
        first_props = {
            prop.prop_id: prop
            for prop in backstory.props
            if any(
                item.scene_id == first_scene and item.state == "active"
                for item in prop.lifecycle
            )
        }
        for prop_id, prop in first_props.items():
            record = service.save_automatic(
                account,
                AutomaticMemoryCandidate(
                    text=prop.source_text,
                    source_event_id=f"synthetic-prop:{prop_id}",
                    review_allows_capture=True,
                    contains_sensitive_content=False,
                ),
            ).record
            prop_records[prop_id] = record.memory_id

        for item in compiled:
            before = {
                record.memory_id: memory_record_sha256(record)
                for record in service.list_active(account)
            }
            session_id = f"synthetic-eval:{run_id}:session:{uuid4().hex}"
            turn_id = f"synthetic-eval:{run_id}:turn:{uuid4().hex}"
            recorder = SceneTranscriptRecorder()
            try:
                with bind_evaluation_transcript_sink(recorder):
                    response: ChatResponse = await handler(
                        ChatRequest(
                            session_id=session_id,
                            turn_id=turn_id,
                            message=item.line.text,
                        ),
                        service,
                        account,
                    )
            finally:
                sessions.clear(session_id)
            after_records = tuple(service.list_active(account))
            after = {
                record.memory_id: memory_record_sha256(record)
                for record in after_records
            }
            created_ids = tuple(sorted(set(after) - set(before)))
            surfacing_decision, surfacing_sources = _observed_surfacing(recorder.exchanges)
            failures = _grade_scene(
                item,
                response,
                created_ids=created_ids,
                surfacing_decision=surfacing_decision,
                surfacing_sources=surfacing_sources,
                prop_records=prop_records,
                captured_ids=created_ids,
                active_ids=tuple(record.memory_id for record in after_records),
                released_evidence_ids=(
                    response.inspection.release.released_evidence_ids
                    if response.inspection.release is not None
                    else ()
                ),
            )
            result = (
                "passes_hard_gates" if status == "adopted" else "matches_proposal"
            ) if not failures else (
                "fails_hard_gates" if status == "adopted" else "differs_from_proposal"
            )
            observations.append(
                ConversationalSceneObservation(
                    scene_id=item.scene.scene_id,
                    kind=item.workflow.kind,
                    line_id=item.line.line_id,
                    line=item.line.text,
                    created_memory_ids=created_ids,
                    active_memory_ids=tuple(record.memory_id for record in after_records),
                    curation_status=response.inspection.release.capture.curation_status
                    if response.inspection.release is not None else None,
                    surfacing_decision=surfacing_decision,
                    surfacing_source_ids=surfacing_sources,
                    release_source=response.inspection.release.release_source
                    if response.inspection.release is not None else "missing",
                    hard_failures=tuple(failures),
                    ground_truth_result=result,
                    agent_exchanges=recorder.exchanges,
                )
            )
        final_ids = tuple(record.memory_id for record in service.list_active(account))

    return ConversationalEvaluationRun(
        run_id=run_id,
        dataset_version=(
            adoption.adopted_ground_truth_identity
            if adoption is not None
            else ground_truth.backstory_sha256
        ),
        ground_truth_status=status,
        runtime_prompt_fingerprints=RUNTIME_PROMPT_FINGERPRINTS,
        scenes=tuple(observations),
        final_active_memory_ids=final_ids,
    )


def _observed_surfacing(
    exchanges: tuple[AgentExchange, ...],
) -> tuple[Literal["surface_now", "defer", "do_not_surface"] | None, tuple[str, ...]]:
    candidates = [
        exchange for exchange in exchanges
        if exchange.role == "Sculptor" and exchange.stage == "surfacing"
        and exchange.status == "success"
    ]
    if not candidates:
        return None, ()
    try:
        payload = json.loads(candidates[-1].output)
        return payload["decision"], tuple(payload.get("source_memory_ids", ()))
    except (TypeError, ValueError, KeyError):
        return None, ()


def _resolved_reference(
    reference: ConversationalSourceReference,
    *,
    prop_records: dict[str, str],
    captured_ids: tuple[str, ...],
    active_ids: tuple[str, ...],
    released_evidence_ids: tuple[str, ...] = (),
) -> str | None:
    if reference.kind == "source_prop":
        return prop_records.get(reference.reference)
    if reference.kind == "captured_memory":
        return captured_ids[0] if reference.reference.endswith("new-memory") and captured_ids else None
    if reference.kind == "curated_memory":
        return (
            released_evidence_ids[0]
            if reference.reference.endswith("retrieval-view") and released_evidence_ids
            else None
        )
    return None


def _grade_scene(
    item: CompiledConversationalScene,
    response: ChatResponse,
    *,
    created_ids: tuple[str, ...],
    surfacing_decision: str | None,
    surfacing_sources: tuple[str, ...],
    prop_records: dict[str, str],
    captured_ids: tuple[str, ...],
    active_ids: tuple[str, ...],
    released_evidence_ids: tuple[str, ...],
) -> list[str]:
    failures: list[str] = []
    release = response.inspection.release
    if release is None:
        return ["missing_release_inspection"]
    if item.expectation.kind == "capture":
        expected = item.expectation
        if release.capture.curation_status != expected.curation_status:
            failures.append("curation_status_mismatch")
        if expected.capture.provenance_decision != release.capture.provenance_decision:
            failures.append("capture_provenance_decision_mismatch")
        wanted = expected.capture.nomination.kind
        if release.capture.nomination != {
            "capture_candidate": "candidate",
            "no_candidate": "no_candidate",
            "unavailable": "unavailable",
        }[wanted]:
            failures.append("capture_nomination_mismatch")
        if any(
            _resolved_reference(
                reference,
                prop_records=prop_records,
                captured_ids=captured_ids,
                active_ids=active_ids,
                released_evidence_ids=released_evidence_ids,
            ) is None
            for reference in expected.curation_source_references
        ):
            failures.append("unresolved_capture_sources")
    else:
        expected = item.expectation
        if surfacing_decision != expected.decision:
            failures.append("surfacing_decision_mismatch")
        required = {
            _resolved_reference(
                reference,
                prop_records=prop_records,
                captured_ids=captured_ids,
                active_ids=active_ids,
                released_evidence_ids=released_evidence_ids,
            )
            for reference in expected.required_source_references
        } - {None}
        if not required <= set(surfacing_sources):
            failures.append("missing_required_surfacing_sources")
        allowed = {
            resolved
            for reference in expected.allowed_source_references
            if (
                resolved := _resolved_reference(
                    reference,
                    prop_records=prop_records,
                    captured_ids=captured_ids,
                    active_ids=active_ids,
                    released_evidence_ids=released_evidence_ids,
                )
            ) is not None
        }
        if not set(surfacing_sources) <= allowed:
            failures.append("unexpected_surfacing_sources")
        expected_release = {
            "released": "muse_candidate",
            "safe_decline": "application_safe_decline",
            "clarification": "application_clarification",
        }[expected.release]
        if release.release_source != expected_release:
            failures.append("release_source_mismatch")
    return failures


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
            replay_conversational_scenes(backstory, ground_truth, adoption=adoption)
        )
        rendered = result.model_dump_json(indent=2) + "\n"
        if args.output is None:
            print(rendered, end="")
        else:
            args.output.write_text(rendered, encoding="utf-8")
    except (OSError, GroundTruthAdoptionError, ScenarioValidationError, ConversationalContractError, RuntimeError, ValueError) as error:
        print(f"EVALUATION_RUN_ERROR={error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
