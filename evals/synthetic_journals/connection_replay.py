"""Replay independently adopted connection and restraint Scenes through chat."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, Protocol
from uuid import uuid4

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from src.linger.agents.contracts import PromptFingerprint
from apps.backend import sessions
from apps.backend.schemas import ChatRequest, ChatResponse
from apps.backend.telemetry import configure_synthetic_evaluation_telemetry
from src.linger.contracts.turn import ReleaseScope
from src.linger.evaluation_transcript import (
    ConnectionEvaluationEvent,
    bind_evaluation_transcript_sink,
)
from src.linger.services.memory import AccountContext, AutomaticMemoryCandidate, MemoryPolicyService

from .adoption import validate_ground_truth_adoption, validate_ground_truth_adoption_files
from .connection_contract import ValidatedConnectionScene, compile_connection_replay_plan
from .models import (
    GroundTruthAdoption, GroundTruthProposal, PropEvidence, ProposedGroundTruth,
    PublicSourceEvidence, StrictModel, SyntheticBackstory,
)
from .replay import RUNTIME_PROMPT_FINGERPRINTS, RUNTIME_SYSTEM_VARIANT, evaluation_agents
from .transcript import AgentExchange, SceneTranscriptRecorder
from evals.serendipity.objective_replay import STAGES, StageResult


class ConnectionChatHandler(Protocol):
    async def __call__(
        self, request: ChatRequest, service: MemoryPolicyService, account: AccountContext,
        *, initial_reading: ReleaseScope | None, public_source_urls: tuple[str, ...] | None,
    ) -> ChatResponse: ...


class ProposalGrade(StrictModel):
    proposal_id: str
    objective_id: str
    failures: tuple[str, ...]
    stages: tuple[StageResult, ...]
    first_failure_stage: str | None
    semantic_review_required: Literal[True] = True
    acceptable_responses: tuple[str, ...]
    expected_outcomes: tuple[str, ...]
    prohibited_outcomes: tuple[str, ...]
    required_public_claims: tuple[str, ...]


class ConnectionSceneObservation(StrictModel):
    scene_id: str
    line_id: str
    reply: str
    release_source: str
    released_evidence_ids: tuple[str, ...]
    events: tuple[ConnectionEvaluationEvent, ...]
    agent_exchanges: tuple[AgentExchange, ...]
    grades: tuple[ProposalGrade, ...]
    hard_gate_pass: bool
    semantic_review_required: Literal[True] = True


class ConnectionEvaluationRun(StrictModel):
    artifact_schema_version: Literal["1"] = "1"
    content_classification: Literal["synthetic"] = "synthetic"
    ground_truth_status: Literal["adopted"] = "adopted"
    run_id: str
    objective_ids: tuple[str, ...]
    dataset_version: str
    system_variant: str
    runtime_prompt_fingerprints: tuple[PromptFingerprint, ...]
    scenes: tuple[ConnectionSceneObservation, ...]


class AdoptedConnectionEvaluator(Evaluator[str, ConnectionSceneObservation, dict]):
    def evaluate(self, ctx: EvaluatorContext[str, ConnectionSceneObservation, dict]) -> bool:
        return ctx.output.hard_gate_pass

    def get_default_evaluation_name(self) -> str:
        return "adopted_hard_gate_grade"


def _evidence_ledger(events: Sequence[ConnectionEvaluationEvent]) -> dict[str, dict]:
    ledger: dict[str, dict] = {}
    for event in events:
        for serialized in event.evidence_json:
            record = json.loads(serialized)
            evidence_id = record["evidence_id"]
            if evidence_id in ledger and ledger[evidence_id] != record:
                raise ValueError("observed evidence ID changed within one Scene")
            ledger[evidence_id] = record
    return ledger


def _runtime_ids(
    scene: ValidatedConnectionScene, proposal: GroundTruthProposal,
    prop_ids: dict[str, str], ledger: dict[str, dict],
) -> tuple[dict[str, set[str]], list[str]]:
    """Resolve adopted source handles against the exact observed source text."""
    mapped: dict[str, set[str]] = {}
    failures: list[str] = []
    public = {
        source.source_id: source for source in scene.source_setup.public_sources
    } if scene.source_setup else {}
    for evidence in proposal.evidence:
        ids: set[str] = set()
        if isinstance(evidence, PropEvidence):
            record_id = prop_ids[evidence.prop_id]
            prop = next(item for item in scene.props if item.prop_id == evidence.prop_id)
            record = ledger.get(record_id)
            if record is not None and record.get("source_kind") == "memory" and record.get("excerpt") == prop.source_text:
                ids.add(record_id)
        elif isinstance(evidence, PublicSourceEvidence):
            source = public[evidence.source_id]
            record = ledger.get(source.url)
            if record is not None and record.get("source_kind") == "web":
                excerpt = record.get("excerpt", "")
                if excerpt and excerpt in source.text and evidence.text in excerpt:
                    ids.add(source.url)
                else:
                    failures.append("public_source_changed_or_unresolved")
        else:
            for expected in scene.evidence_by_id[evidence.evidence_id].accepted_runtime_records:
                record = ledger.get(expected.evidence_id)
                if record is not None and all((
                    record.get("source_kind") == "book_corpus",
                    record.get("excerpt") == expected.text,
                    record.get("work_id") == expected.work_id,
                    record.get("book_version_id") == expected.book_version_id,
                    record.get("chapter") == expected.chapter_number,
                    record.get("chapter_id") == expected.chapter_id,
                    record.get("source_sha256") == expected.source_sha256,
                    record.get("location") == expected.location,
                    tuple(record.get("source_lines", ())) == expected.source_lines,
                )):
                    ids.add(expected.evidence_id)
        mapped[evidence.evidence_id] = ids
    return mapped, failures


def _stage_failures(failures: list[str], failure_stage: str | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for failure in failures:
        if failure in {"missing_connection_decision", "unexpected_exploration"}:
            stage = "invocation"
        elif failure in {"retrieval_failure", "invalid_evidence_observation", "public_source_changed_or_unresolved", "required_source_not_inspected", "missing_source_inspection", "private_query_disclosure"}:
            stage = "retrieval"
        elif failure in {"discovery_failure", "connection_decision_mismatch", "invalid_connection_proposal", "unpermitted_selected_evidence"}:
            stage = "serendipity_selection"
        elif failure.startswith("missing_required_citation"):
            stage = "muse_presentation"
        elif failure == "missing_review_approval":
            stage = "provenance_review"
        elif failure == "provider_failure":
            stage = "provenance_review" if failure_stage in {"provenance_review", "emotional_boundary_preflight"} else "muse_presentation"
        else:
            stage = "deterministic_release"
        result.setdefault(stage, failure)
    return result


def grade_connection_scene(
    scene: ValidatedConnectionScene, response: ChatResponse,
    events: Sequence[ConnectionEvaluationEvent], prop_ids: dict[str, str],
) -> tuple[ProposalGrade, ...]:
    """Check observed hard gates; leave the meaning of the reply for review."""
    common: list[str] = []
    release = response.inspection.release
    discoveries = [event for event in events if event.kind == "discovery"]
    searches = [event for event in events if event.kind == "search"]
    final = discoveries[-1] if discoveries else None
    if not any(event.kind == "release" for event in events):
        common.append("missing_release_observation")
    if release is None:
        common.append("missing_release")
    elif release.failure_type == "model":
        common.append("provider_failure")
    if any(event.failure_code or event.status == "retrieval_unavailable" for event in searches):
        common.append("retrieval_failure")
    if any(event.failure_code or event.status == "failed" for event in discoveries):
        common.append("discovery_failure")
    try:
        ledger = _evidence_ledger(events)
    except (ValueError, KeyError, TypeError):
        common.append("invalid_evidence_observation")
        ledger = {}
    release_events = [event for event in events if event.kind == "release"]
    cited = set(release_events[-1].released_evidence_ids if release_events else ())
    if release_events and release is not None and release_events[-1].release_source != release.release_source:
        common.append("inconsistent_release_observation")
    # A sent query must satisfy the same privacy boundary even if a future
    # adapter accidentally bypasses the production pre-send guard.
    from src.linger.agents.serendipity.tools import _query_contains_private_data, _query_copies_reader_terms
    private_texts = [scene.line.text, *(prop.source_text for prop in scene.props)]
    if any(
        event.kind == "query" and event.status == "sent" and event.query is not None
        and (_query_contains_private_data(event.query) or any(
            _query_copies_reader_terms(event.query, text) for text in private_texts
        )) for event in events
    ):
        common.append("private_query_disclosure")
    grades: list[ProposalGrade] = []
    for proposal in scene.proposals:
        expectation = proposal.connection
        if expectation is None:
            raise ValueError("compiled connection expectation is missing")
        failures = list(common)
        decision = expectation.decision
        if decision == "not_requested":
            if discoveries or searches or response.inspection.librarian_grounding:
                failures.append("unexpected_exploration")
        elif final is None:
            failures.append("missing_connection_decision")
        elif final.status not in ({"proposal", "decline"} if decision == "restraint" else {decision}):
            failures.append("connection_decision_mismatch")
        if decision != "not_requested" and not searches:
            failures.append("missing_source_inspection")
        if release is not None:
            if release.release_source == "muse_candidate":
                if not release.provenance_verdicts or release.provenance_verdicts[-1] != "pass":
                    failures.append("missing_review_approval")
            elif decision != "restraint" or release.release_source != "application_safe_decline":
                failures.append("unexpected_release_source")
            elif release.failure_stage == "deterministic_validation":
                failures.append("invalid_evidence_release")
        mapped, evidence_failures = _runtime_ids(scene, proposal, prop_ids, ledger)
        failures.extend(evidence_failures)
        if decision != "not_requested" and any(not ids for ids in mapped.values()):
            failures.append("required_source_not_inspected")
        permitted = set().union(*(mapped[item] for item in expectation.permitted_evidence_ids))
        if cited - permitted:
            failures.append("unpermitted_citation")
        for evidence_id in expectation.required_evidence_ids:
            if not (mapped[evidence_id] & cited):
                failures.append(f"missing_required_citation:{evidence_id}")
        if final is not None and final.status == "proposal":
            try:
                from src.linger.agents.serendipity.models import SERENDIPITY_RESPONSE_ADAPTER, ConnectionProposal
                selected = SERENDIPITY_RESPONSE_ADAPTER.validate_json(final.decision_json or "null")
                if not isinstance(selected, ConnectionProposal):
                    raise ValueError("expected a proposal")
                if not set(selected.selected_candidate.evidence_ids) <= permitted:
                    failures.append("unpermitted_selected_evidence")
            except ValueError:
                failures.append("invalid_connection_proposal")
        stage_failures = _stage_failures(failures, release.failure_stage if release else None)
        first_failure = next((stage for stage in STAGES if stage in stage_failures), None)
        stages = tuple(StageResult(
            stage=stage,
            status=("failed" if stage == first_failure else "not_reached" if first_failure and STAGES.index(stage) > STAGES.index(first_failure) else "passed"),
            reason_code=stage_failures.get(stage),
        ) for stage in STAGES)
        grades.append(ProposalGrade(
            proposal_id=proposal.proposal_id, objective_id=proposal.objective_id,
            failures=tuple(dict.fromkeys(failures)), stages=stages, first_failure_stage=first_failure,
            acceptable_responses=expectation.acceptable_responses,
            expected_outcomes=proposal.expected_outcomes,
            prohibited_outcomes=proposal.prohibited_outcomes,
            required_public_claims=expectation.required_public_claims,
        ))
    return tuple(grades)


async def replay_connection_scenes(
    backstory: SyntheticBackstory, ground_truth: ProposedGroundTruth, *,
    adoption: GroundTruthAdoption, ground_truth_bytes: bytes, backstory_bytes: bytes,
    chat_handler: ConnectionChatHandler | None = None,
) -> ConnectionEvaluationRun:
    if (ProposedGroundTruth.model_validate_json(ground_truth_bytes) != ground_truth
        or SyntheticBackstory.model_validate_json(backstory_bytes) != backstory
        or hashlib.sha256(backstory_bytes).hexdigest() != ground_truth.backstory_sha256):
        raise ValueError("replay objects do not match the independently adopted package bytes")
    validate_ground_truth_adoption(ground_truth, adoption, ground_truth_bytes=ground_truth_bytes)
    plan = compile_connection_replay_plan(backstory, ground_truth)
    if chat_handler is None:
        from apps.backend.chat_turn import run_chat_turn
        chat_handler = run_chat_turn
        configure_synthetic_evaluation_telemetry(evaluation_agents())
    handler = chat_handler
    run_id = uuid4().hex
    account = AccountContext(f"synthetic-connection:{backstory.backstory.evaluation_account_id}:{run_id}")
    observations: list[ConnectionSceneObservation] = []
    by_id = {item.scene.scene_id: item for item in plan.scenes}
    with tempfile.TemporaryDirectory(prefix="linger-connection-eval-") as directory:
        async def execute(scene_id: str) -> ConnectionSceneObservation:
            scene = by_id[scene_id]
            if scene.scene.order != len(observations) + 1:
                raise RuntimeError("connection Scenes executed out of order")
            service = MemoryPolicyService(Path(directory) / str(scene.scene.order))
            prop_ids: dict[str, str] = {}
            service.set_capture_enabled(account, True)
            try:
                for prop in scene.props:
                    saved = service.save_automatic(account, AutomaticMemoryCandidate(
                        text=prop.source_text, source_event_id=f"prop:{prop.prop_id}",
                        review_allows_capture=True, contains_sensitive_content=False,
                    ))
                    prop_ids[prop.prop_id] = saved.record.memory_id
            finally:
                service.set_capture_enabled(account, False)
            before = tuple(service.list_active(account))
            setup = scene.source_setup
            scope = setup.book_scope if setup else None
            reading = ReleaseScope(
                work_id=scope.work_id, book_version_id=scope.book_version_id,
                chapter_max=scope.safe_ceiling_chapter,
            ) if scope else None
            urls = tuple(source.url for source in setup.public_sources) if setup else ()
            recorder = SceneTranscriptRecorder()
            session_id = f"{run_id}:{scene.scene.order}"
            try:
                with bind_evaluation_transcript_sink(recorder):
                    response = await handler(
                        ChatRequest(session_id=session_id, turn_id=f"{run_id}:{scene.line.line_id}", message=scene.line.text),
                        service, account, initial_reading=reading, public_source_urls=urls,
                    )
            finally:
                sessions.clear(session_id)
            if tuple(service.list_active(account)) != before or service.capture_enabled(account):
                raise RuntimeError("connection replay changed its source snapshot or capture policy")
            grades = grade_connection_scene(scene, response, recorder.connection_events, prop_ids)
            release = response.inspection.release
            observation = ConnectionSceneObservation(
                scene_id=scene_id, line_id=scene.line.line_id, reply=response.reply,
                release_source=release.release_source if release else "unavailable",
                released_evidence_ids=next((event.released_evidence_ids for event in reversed(recorder.connection_events) if event.kind == "release"), ()),
                events=recorder.connection_events, agent_exchanges=recorder.exchanges,
                grades=grades, hard_gate_pass=not any(grade.failures for grade in grades),
            )
            observations.append(observation)
            return observation
        dataset = Dataset(
            name="connection_and_restraint", cases=[
                Case(name=item.scene.scene_id, inputs=item.scene.scene_id) for item in plan.scenes
            ], evaluators=[AdoptedConnectionEvaluator()],
        )
        report = await dataset.evaluate(
            execute, name=f"connection-and-restraint-{run_id[:8]}",
            task_name="connection_and_restraint_workflow", max_concurrency=1, progress=False,
            metadata={"content_classification": "synthetic", "dataset_version": adoption.adopted_ground_truth_identity},
        )
        if report.failures or len(observations) != len(plan.scenes):
            raise RuntimeError("connection evaluation did not complete every Scene")
    return ConnectionEvaluationRun(
        run_id=run_id, objective_ids=backstory.objective_ids,
        dataset_version=adoption.adopted_ground_truth_identity, system_variant=RUNTIME_SYSTEM_VARIANT,
        runtime_prompt_fingerprints=RUNTIME_PROMPT_FINGERPRINTS,
        scenes=tuple(observations),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backstory", type=Path)
    parser.add_argument("ground_truth", type=Path)
    parser.add_argument("--adoption", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    backstory, truth, adoption = validate_ground_truth_adoption_files(args.backstory, args.ground_truth, args.adoption)
    if set(backstory.objective_ids) == {"weak_evidence_safe_decline"} and all(item.grounding is not None for item in truth.proposals):
        from .reflection_replay import replay_reflection_scenes
        run = asyncio.run(replay_reflection_scenes(backstory, truth, adoption=adoption))
    else:
        run = asyncio.run(replay_connection_scenes(
            backstory, truth, adoption=adoption, ground_truth_bytes=args.ground_truth.read_bytes(), backstory_bytes=args.backstory.read_bytes(),
        ))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(run.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"CONNECTION_REPLAY_OUTPUT={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
