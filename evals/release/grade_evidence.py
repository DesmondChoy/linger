"""Validate the native grades used by memory-loop and composed curation runners."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from pydantic import TypeAdapter

from evals.synthetic_journals.replay_support import MEMORY_LOOP_RUN_CONFIGURATION_ID
from evals.synthetic_journals.validate_scenario import (
    DEFAULT_RUN_CONFIGURATION_DIRECTORY, load_run_configurations,
)
from src.linger.agents.provenance.curation_models import CurationProvenanceReview, CurationReviewInput
from src.linger.agents.sculptor.models import CurationMemory, ExistingCuration, SCULPTOR_RESPONSE_ADAPTER

_PASS = "passes_hard_gates"
_FAIL = "fails_hard_gates"
_CURATION = "bounded_memory_curation"
_RETRIEVAL = "longitudinal_memory_retrieval"
_CONNECTION = "cross_source_tentative_connection"


def _result_matches(result: str, failures: tuple[str, ...], passed: bool | None = None) -> None:
    if result != (_FAIL if failures else _PASS) or (passed is not None and passed != (not failures)):
        raise ValueError("Recorded adopted outcome disagrees with its failure evidence.")


def _complete_exchanges(exchanges) -> None:
    if not exchanges:
        raise ValueError("Required execution transcripts are missing.")
    for item in exchanges:
        if item.status == "success":
            valid = not any((
                item.failure_code, item.failure_category, item.provider_status_code,
                item.provider_error_kind,
            )) and item.output is not None
        else:
            valid = (
                item.status in {"failure", "cancelled"}
                and bool(item.failure_code) and bool(item.failure_category)
                and item.failure_code != "incomplete_agent_exchange"
                and (item.status == "cancelled") == (item.failure_category == "cancelled")
            )
        if not valid:
            raise ValueError("Required execution transcript has no consistent terminal outcome.")


def _curation_review(status: str, decision: str | None, exchanges, *, response=None, input_memories=None):
    sculptors = [item for item in exchanges if item.role == "Sculptor"]
    reviewers = [item for item in exchanges if item.role == "Provenance"]
    if (
        len(sculptors) != 1 or sculptors[0].stage != "curation"
        or sculptors[0].input_contract != "src.linger.agents.sculptor.models.AccountScopedMemories"
        or len(sculptors) + len(reviewers) != len(exchanges)
        or any(
            (item.role, tool.tool_name) not in {
                ("Sculptor", "final_result_CurationProposal"),
                ("Sculptor", "final_result_NoCurationProposal"),
            }
            or tool.outcome not in ({"success"} if item.status == "success" else {None, "success", "failed"})
            for item in (*sculptors, *reviewers) for tool in item.tool_exchanges
        )
    ):
        raise ValueError("Curation lacks its exact no-tool Sculptor execution.")
    payload = json.loads(sculptors[0].input_prompt)
    if not isinstance(payload, dict) or set(payload) - {"memories", "existing_curation"}:
        raise ValueError("Curation Sculptor input is not its recorded memory batch.")
    memories = TypeAdapter(tuple[CurationMemory, ...]).validate_json(json.dumps(payload.get("memories")))
    existing = ExistingCuration.model_validate_json(json.dumps(payload.get("existing_curation", {})))
    by_id = {item.memory_id: item for item in memories}
    if (
        not 2 <= len(memories) <= 12 or len(by_id) != len(memories)
        or existing.referenced_memory_ids() - by_id.keys()
        or (input_memories is not None and (memories != input_memories or existing != ExistingCuration()))
    ):
        raise ValueError("Curation Sculptor input or output differs from the observed source batch and proposal.")
    if sculptors[0].status != "success":
        if status != "failed" or decision is not None or reviewers or response is not None:
            raise ValueError("Failed Sculptor execution cannot authorize a curation outcome.")
        return None, memories, None
    actual_response = SCULPTOR_RESPONSE_ADAPTER.validate_json(json.dumps(sculptors[0].output))
    if response is not None and actual_response != response:
        raise ValueError("Curation Sculptor output differs from the observed proposal.")
    if status == "failed":
        if decision is not None or len(reviewers) > 1 or (reviewers and reviewers[0].status == "success"):
            raise ValueError("Failed curation lacks a recorded failure before application.")
        if not reviewers:
            return actual_response, memories, None
    else:
        expected = {
            "no_change": "not_reviewed", "provenance_revise": "revise",
            "provenance_reject": "reject", "applied": "allow",
        }.get(status)
        if expected is None or (decision or "not_reviewed") != expected:
            raise ValueError("Curation application and approval evidence disagree.")
        if expected == "not_reviewed":
            if reviewers or actual_response.kind != "no_curation_proposal":
                raise ValueError("Unreviewed curation unexpectedly contains a proposal or review.")
            return actual_response, memories, None
    if (
        len(reviewers) != 1 or reviewers[0].stage != "curation_review"
        or reviewers[0].input_contract != "src.linger.agents.provenance.curation_models.CurationReviewInput"
    ):
        raise ValueError("Curation has no exact recorded Provenance review.")
    review_input = CurationReviewInput.model_validate_json(reviewers[0].input_prompt)
    if (
        review_input.proposal != actual_response
        or any(
            source.memory_id not in by_id or source.text != by_id[source.memory_id].text
            or source.recorded_at != by_id[source.memory_id].recorded_at
            for source in review_input.sources
        )
    ):
        raise ValueError("Curation review is not bound to the exact observed proposal and source memories.")
    if status == "failed":
        return actual_response, memories, review_input
    if reviewers[0].status != "success":
        raise ValueError("Applied or reviewed curation requires a completed Provenance decision.")
    review = CurationProvenanceReview.model_validate_json(json.dumps(reviewers[0].output))
    review_input.validate_review(review)
    if review.decision != expected:
        raise ValueError("Curation application and approval evidence disagree.")
    return actual_response, memories, review_input


def _memory_loop(artifact: dict, scene: dict, planned: dict, backstory: dict, proposals: list[dict]) -> None:
    from evals.synthetic_journals.memory_loop_replay import (
        CurationRoundObservation, MemoryLoopSceneObservation,
    )

    configuration = load_run_configurations(DEFAULT_RUN_CONFIGURATION_DIRECTORY)[MEMORY_LOOP_RUN_CONFIGURATION_ID]
    settings = configuration.curation_recall_loop
    if (
        settings is None or planned["objective_ids"] != [_RETRIEVAL]
        or backstory.get("run_configuration_ids") != [MEMORY_LOOP_RUN_CONFIGURATION_ID]
        or artifact.get("run_configuration_id") != MEMORY_LOOP_RUN_CONFIGURATION_ID
        or type(artifact.get("repetitions")) is not int or artifact["repetitions"] != settings.repetitions
        or type(artifact.get("curation_rounds")) is not int or artifact["curation_rounds"] != settings.curation_rounds
        or artifact.get("capture_enabled") is not False
        or len(proposals) != 1 or proposals[0]["objective_id"] != _RETRIEVAL
    ):
        raise ValueError("Memory-loop configuration differs from the adopted run setup.")
    observed = MemoryLoopSceneObservation.model_validate_json(json.dumps(scene))
    line = next((item for item in backstory["lines"] if item["line_id"] == observed.line_id), None)
    relevant = {item["prop_id"] for item in proposals[0]["prop_relevance"] if item["relevance"] == "relevant"}
    distractors = {item["prop_id"] for item in proposals[0]["prop_relevance"] if item["relevance"] == "distractor"}
    if (
        line is None or planned["line_ids"] != [observed.line_id] or observed.input_line != line["text"]
        or set(observed.relevant_prop_ids) != relevant or set(observed.distractor_prop_ids) != distractors
        or len(observed.relevant_prop_ids) != len(relevant) or len(observed.distractor_prop_ids) != len(distractors)
        or observed.role != ("target" if relevant else "comparison")
        or relevant | distractors != set(planned["prop_ids"])
    ):
        raise ValueError("Memory-loop Line or adopted Prop judgments changed.")
    expected = {(repeat, rounds) for repeat in range(1, settings.repetitions + 1) for rounds in range(settings.curation_rounds + 1)}
    actual = [(grade.repetition, grade.curation_rounds) for grade in observed.grades]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError("Memory-loop omitted, duplicated, or invented a repetition/round judgment.")
    for grade in observed.grades:
        _result_matches(grade.ground_truth_result, grade.hard_failures)
        _complete_exchanges(grade.agent_exchanges)
        if not any(event.kind == "release" for event in grade.events):
            raise ValueError("Memory-loop recall omitted release observations.")
    raw_rounds = artifact.get("curation")
    if not isinstance(raw_rounds, list):
        raise ValueError("Memory-loop curation observations are missing.")
    rounds = [CurationRoundObservation.model_validate_json(json.dumps(item)) for item in raw_rounds]
    actual_rounds = [(item.repetition, item.round) for item in rounds]
    if len(actual_rounds) != len(set(actual_rounds)) or set(actual_rounds) != {item for item in expected if item[1] > 0}:
        raise ValueError("Memory-loop curation rounds are incomplete or duplicated.")
    bank = set(planned["prop_ids"])
    trusted_memories = {
        item["prop_id"]: CurationMemory.model_validate_json(json.dumps({
            "memory_id": item["prop_id"], "text": item["source_text"], "recorded_at": item.get("recorded_at"),
        }))
        for item in backstory["props"] if item["prop_id"] in bank
    }
    trusted_content = Counter((item.text, item.recorded_at) for item in trusted_memories.values())
    seeded_batches = {}
    approved_derived = {}
    previous_views = {}
    for observation in sorted(rounds, key=lambda item: (item.repetition, item.round)):
        _complete_exchanges(observation.agent_exchanges)
        failed = observation.status == "failed"
        if failed != bool(observation.failure):
            raise ValueError("Memory-loop curation failure outcome is incomplete or inconsistent.")
        response, memories, _ = _curation_review(observation.status, observation.provenance_decision, observation.agent_exchanges)
        if (
            Counter((item.text, item.recorded_at) for item in memories) != trusted_content
            or seeded_batches.setdefault(observation.repetition, memories) != memories
        ):
            raise ValueError("Memory-loop Sculptor batch differs from the trusted immutable Prop bank.")
        if set(observation.source_prop_ids) - bank or any(
            not item.source_prop_ids or set(item.source_prop_ids) - bank
            for item in observation.retrieval_view
        ):
            raise ValueError("Memory-loop curation refers to unauthorized source Props.")
        view = Counter((item.kind, item.source_prop_ids, item.text) for item in observation.retrieval_view)
        if failed:
            previous = previous_views.get(
                observation.repetition, Counter(("original", (identity,), None) for identity in bank),
            )
            if observation.action is not None or observation.source_prop_ids or view != previous:
                raise ValueError("Failed curation changed retrieval state or invents an applied action.")
        elif response.kind == "no_curation_proposal":
            if observation.action is not None or observation.source_prop_ids:
                raise ValueError("Memory-loop no-change observation invents an action.")
        else:
            by_id = {item.memory_id: item for item in memories}
            sources = [by_id[identity] for identity in response.action.source_memory_ids]
            expected_sources = [trusted_memories[identity] for identity in observation.source_prop_ids]
            if observation.action != response.action.action or Counter((item.text, item.recorded_at) for item in sources) != Counter((item.text, item.recorded_at) for item in expected_sources):
                raise ValueError("Memory-loop action differs from the reviewed Sculptor proposal.")
            derived_fields = {
                "update_derived_summary": ("derived_summary", "summary"),
                "assign_topic_group": ("topic_group", "topic_label"),
            }.get(response.action.action)
            if observation.status == "applied" and derived_fields:
                kind, text_field = derived_fields
                approved_derived.setdefault(observation.repetition, set()).add((
                    kind, tuple(sorted(observation.source_prop_ids)), getattr(response.action, text_field),
                ))
        if any(
            (item.kind == "original" and (item.text is not None or len(item.source_prop_ids) != 1))
            or (item.kind != "original" and (item.kind, tuple(sorted(item.source_prop_ids)), item.text)
                not in approved_derived.get(observation.repetition, set()))
            for item in observation.retrieval_view
        ):
            raise ValueError("Memory-loop retrieval projection has no matching applied reviewed action.")
        previous_views[observation.repetition] = view


def _curation(scene: dict, planned: dict, backstory: dict, proposals: list[dict]) -> None:
    from evals.sculptor.harness import CurationExpectation
    from evals.synthetic_journals.curation_replay import CurationSceneObservation

    if len(proposals) != 1 or proposals[0]["objective_id"] != _CURATION or not proposals[0].get("curation"):
        raise ValueError("Curation Scene lacks exactly one adopted curation judgment.")
    observed = CurationSceneObservation.model_validate_json(json.dumps(scene))
    expected = CurationExpectation.model_validate_json(json.dumps(proposals[0]["curation"]))
    if observed.expected != expected:
        raise ValueError("Recorded curation expectation differs from adopted Ground truth.")
    _result_matches(observed.ground_truth_result, observed.grade.failures, observed.grade.hard_pass)
    _complete_exchanges(observed.agent_exchanges)
    props = {item["prop_id"]: item["source_text"] for item in backstory["props"] if item["prop_id"] in planned["prop_ids"]}
    memories = {item.memory_id: item.text for item in observed.input_memories}
    hashes = {identity: hashlib.sha256(text.encode()).hexdigest() for identity, text in props.items()}
    if (
        memories != props or len(memories) != len(observed.input_memories)
        or scene.get("source_immutable") is not True
        or any(
            len(items) != len(hashes) or {item.memory_id: item.sha256 for item in items} != hashes
            for items in (observed.source_hashes_before, observed.source_hashes_after)
        )
    ):
        raise ValueError("Curation source identity or immutability is unproven.")
    outcome = observed.actual_outcome
    if (
        outcome.status != observed.curation_status or outcome.provenance_decision is None
        or outcome.application_created is None or outcome.audit_verified is None
        or outcome.retrieval_memory_ids is None
        or (observed.curation_status == "no_change") != (observed.response.kind == "no_curation_proposal")
        or (observed.curation_status == "applied" and outcome.audit_verified is not True)
        or (observed.curation_status != "applied" and (outcome.application_created or outcome.audit_verified))
    ):
        raise ValueError("Curation actual application and audit evidence is incomplete or inconsistent.")
    _, _, review_input = _curation_review(
        observed.curation_status, outcome.provenance_decision, observed.agent_exchanges,
        response=observed.response, input_memories=observed.input_memories,
    )
    if observed.response.kind == "curation_proposal" and set(observed.response.action.source_memory_ids) - props.keys():
        raise ValueError("Curation proposed an unauthorized source memory.")
    permitted_retrieval = set(props)
    if review_input is not None and observed.curation_status == "applied":
        prefix = {"update_derived_summary": "summary", "assign_topic_group": "topic"}.get(observed.response.action.action)
        if prefix:
            permitted_retrieval.add(f"{prefix}_{review_input.proposal_digest}")
    if set(outcome.retrieval_memory_ids) - permitted_retrieval or len(set(outcome.retrieval_memory_ids)) != len(outcome.retrieval_memory_ids):
        raise ValueError("Curation retrieval includes an unapproved original or derived memory identity.")


def _connection(scene: dict, proposals: list[dict]) -> None:
    from evals.synthetic_journals.connection_replay import ConnectionSceneObservation

    observed = ConnectionSceneObservation.model_validate_json(json.dumps(scene))
    expected = {item["proposal_id"]: item["objective_id"] for item in proposals}
    actual = {item.proposal_id: item.objective_id for item in observed.grades}
    if not expected or actual != expected or len(actual) != len(observed.grades):
        raise ValueError("Connection Scene omitted, duplicated, or invented an adopted judgment.")
    if observed.hard_gate_pass != (not any(item.failures for item in observed.grades)):
        raise ValueError("Connection Scene outcome disagrees with its failure evidence.")
    _complete_exchanges(observed.agent_exchanges)


def validate_special_scene_grade(
    artifact: dict[str, Any], scene: dict[str, Any], planned_scene: dict[str, Any],
    backstory: dict[str, Any], truth: dict[str, Any], runner: str,
) -> bool:
    """Handle only supported native schemas; ordinary replay grades remain with the caller."""
    name = runner.removeprefix("evals.synthetic_journals.")
    objectives = planned_scene["objective_ids"]
    proposals = [item for item in truth["proposals"] if item["scene_id"] == planned_scene["scene_id"]]
    if name == "memory_loop_replay":
        _memory_loop(artifact, scene, planned_scene, backstory, proposals)
    elif name in {"curation_replay", "capture_curation_replay", "connection_curation_replay"} and objectives == [_CURATION]:
        _curation(scene, planned_scene, backstory, proposals)
    elif name == "connection_curation_replay" and objectives == [_CONNECTION]:
        _connection(scene, proposals)
    else:
        return False
    return True
