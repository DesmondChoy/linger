"""Only independently authorized boundary fidelity failures are quality failures."""

import json

import pytest

from evals.synthetic_journals.book_replay import _grade_proposal
from tests.test_synthetic_book_optional_support import (
    compile_documents,
    documents_with_optional,
)
from tests.test_synthetic_book_replay import replay_observed


def missing_anchor_scene():
    content, truth = documents_with_optional()
    scope = truth["book_scene_facts"][0]["scope"]
    scope["supporting_evidence_ids"] = ["support", "optional"]
    scope["optional_supporting_evidence_ids"] = []
    return compile_documents(content, truth).scenes[0]


def test_missing_adopted_anchor_is_quality_failure_when_actual_boundary_is_authorized(
    replay_observed,
):
    scene = missing_anchor_scene()
    observation = replay_observed[1].scenes[0]
    for proposal in scene.proposals:
        grade = _grade_proposal(scene, proposal, observation)
        assert not grade.hard_pass
        assert grade.failures == ("authorized_boundary_support_mismatch",)


def with_extra_support(observation, record):
    exchanges = list(observation.agent_exchanges)
    index = next(i for i, exchange in enumerate(exchanges) if exchange.stage == "boundary_inference")
    exchange = exchanges[index]
    request = json.loads(exchange.input_prompt)
    request["full_work_candidates"].append(record.model_dump(mode="json"))
    output = dict(exchange.output)
    output["supporting_evidence"] = [*output["supporting_evidence"], {
        "evidence_id": record.evidence_id, "source_excerpt": record.text,
    }]
    exchanges[index] = exchange.model_copy(update={
        "input_prompt": json.dumps(request), "output": output,
    })
    return observation.model_copy(update={
        "boundary_support_evidence": (*observation.boundary_support_evidence, record),
        "agent_exchanges": tuple(exchanges),
    })


def test_extra_canonical_anchor_within_authorized_boundary_remains_a_failed_judgment(
    replay_observed,
):
    scene = compile_documents(*documents_with_optional()).scenes[0]
    extra = scene.evidence_by_id["unlisted"].accepted_runtime_records[0]
    observation = with_extra_support(replay_observed[1].scenes[0], extra)
    for proposal in scene.proposals:
        grade = _grade_proposal(scene, proposal, observation)
        assert not grade.hard_pass
        assert grade.failures == ("authorized_boundary_support_mismatch",)


@pytest.mark.parametrize("mutation", [
    "missing_transcript", "failed_boundary", "wrong_work", "wrong_version",
    "wrong_ceiling", "empty_support", "forged_memory", "wrong_reader_line",
    "missing_event_proof", "unbound_excerpt", "route_scope_mismatch",
])
def test_incomplete_or_unauthorized_proof_keeps_the_blocking_classification(
    replay_observed, mutation,
):
    scene = missing_anchor_scene()
    observation = replay_observed[1].scenes[0]
    exchanges = list(observation.agent_exchanges)
    index = next(i for i, exchange in enumerate(exchanges) if exchange.stage == "boundary_inference")
    exchange = exchanges[index]
    output = json.loads(json.dumps(exchange.output))
    request = json.loads(exchange.input_prompt)
    if mutation == "missing_transcript":
        exchanges.pop(index)
    elif mutation == "failed_boundary":
        exchanges[index] = exchange.model_copy(update={"status": "failed", "failure_code": "model_error"})
    elif mutation in {"wrong_work", "wrong_version", "wrong_ceiling", "missing_event_proof", "unbound_excerpt"}:
        if mutation == "wrong_work":
            output["work_id"] = "other-work"
        elif mutation == "wrong_version":
            output["book_version_id"] = "other-version"
        elif mutation == "wrong_ceiling":
            output["chapter_number"] = 6
        elif mutation == "missing_event_proof":
            output.pop("event_resolution")
        else:
            output["supporting_evidence"][0]["source_excerpt"] = "invented source"
        exchanges[index] = exchange.model_copy(update={"output": output})
    elif mutation in {"forged_memory", "wrong_reader_line"}:
        if mutation == "forged_memory":
            request["relevant_memories"][0]["text"] = "an unauthorized memory"
        else:
            request["current_line"] = "a different reader request"
        exchanges[index] = exchange.model_copy(update={"input_prompt": json.dumps(request)})
    elif mutation == "empty_support":
        observation = observation.model_copy(update={"boundary_support_evidence": ()})
    else:
        observation = observation.model_copy(update={"routed_ceiling": 6})
    observation = observation.model_copy(update={"agent_exchanges": tuple(exchanges)})
    for proposal in scene.proposals:
        grade = _grade_proposal(scene, proposal, observation)
        assert not grade.hard_pass
        assert "boundary_support_differs_from_ground_truth" in grade.failures
        assert "authorized_boundary_support_mismatch" not in grade.failures


@pytest.mark.parametrize("mutation", ["forged_text", "later_chapter", "other_part", "wrong_identity"])
def test_matching_transcript_cannot_authorize_invalid_source_records(replay_observed, mutation):
    scene = compile_documents(*documents_with_optional()).scenes[0]
    extra = scene.evidence_by_id["unlisted"].accepted_runtime_records[0]
    if mutation == "forged_text":
        extra = extra.model_copy(update={"text": extra.text + " invented text"})
    elif mutation == "later_chapter":
        extra = scene.evidence_by_id["later"].accepted_runtime_records[0]
    elif mutation == "other_part":
        extra = extra.model_copy(update={"part_id": "preface"})
    else:
        extra = extra.model_copy(update={"work_id": "other-work"})
    observation = with_extra_support(replay_observed[1].scenes[0], extra)
    for proposal in scene.proposals:
        grade = _grade_proposal(scene, proposal, observation)
        assert not grade.hard_pass
        assert "boundary_support_differs_from_ground_truth" in grade.failures
        assert "authorized_boundary_support_mismatch" not in grade.failures


@pytest.mark.parametrize("mutation,blocking_failure", [
    ({"searched_max_chapter": 6}, "retrieval_exceeded_safe_ceiling"),
    ({"work_id": "other-work"}, "retrieval_scope_identity_differs_from_ground_truth"),
    ({"response_kind": "failure", "call_outcome": "failed"}, "grounding_call_did_not_return_evidence_result"),
])
def test_quality_classification_preserves_independent_scope_and_execution_failures(
    replay_observed, mutation, blocking_failure,
):
    scene = missing_anchor_scene()
    observation = replay_observed[1].scenes[0]
    observation = observation.model_copy(update={
        "grounding_calls": tuple(call.model_copy(update=mutation) for call in observation.grounding_calls),
    })
    for proposal in scene.proposals:
        grade = _grade_proposal(scene, proposal, observation)
        assert not grade.hard_pass
        assert "authorized_boundary_support_mismatch" in grade.failures
        assert blocking_failure in grade.failures
