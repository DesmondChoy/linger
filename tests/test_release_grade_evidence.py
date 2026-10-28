"""Release accepts complete native grades while rejecting missing or altered proof."""

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BUNDLES = {
    "memory_loop_replay": "supper-club-curation-then-recall--muse-serendipity-sculptor-provenance--2026-09-30",
    "curation_replay": "pottery-memory-curation--sculptor--2026-08-29",
    "capture_curation_replay": "reviewed-capture-and-bounded-curation--muse-sculptor-provenance--2026-09-21",
    "connection_curation_replay": "memory-curation-and-cross-source-connections--muse-librarian-serendipity-sculptor-provenance--2026-09-19",
}


def bundle(runner):
    evidence = json.loads((ROOT / "results" / BUNDLES[runner] / "result.json").read_text())["evidence"]
    return (
        evidence["evaluation"]["data"], evidence["inputs"]["backstory.json"]["data"],
        evidence["inputs"]["ground-truth.json"]["data"],
    )


def validate(artifact, scene, backstory, truth, runner):
    from evals.release.grade_evidence import validate_special_scene_grade

    planned = next(item for item in backstory["scenes"] if item["scene_id"] == scene["scene_id"])
    return validate_special_scene_grade(artifact, scene, planned, backstory, truth, f"evals.synthetic_journals.{runner}")


@pytest.mark.parametrize("runner", BUNDLES)
def test_retained_native_schema_preserves_all_recorded_judgments(runner):
    artifact, backstory, truth = bundle(runner)
    original = json.dumps(artifact, sort_keys=True)
    scenes = artifact["scenes"]
    handled = [validate(artifact, scene, backstory, truth, runner) for scene in scenes]

    assert any(handled)
    assert all(handled) if runner != "capture_curation_replay" else handled == [False] * 11 + [True] * 5
    assert json.dumps(artifact, sort_keys=True) == original


def failed_exchange(exchange, *, status="failure", category="provider_error"):
    exchange.update(
        status=status, failure_code="provider_request_failed", failure_category=category,
        output=None, model_messages=[], tool_exchanges=[], usage=None,
        provider_error_kind="connection" if category == "provider_error" else None,
    )


@pytest.mark.parametrize(("status", "category"), [
    ("failure", "provider_error"), ("failure", "unknown_error"), ("cancelled", "cancelled"),
])
def test_completed_native_connection_retains_recorded_agent_failure(status, category):
    artifact, backstory, truth = bundle("connection_curation_replay")
    scene = artifact["scenes"][5]
    exchange = next(item for item in scene["agent_exchanges"] if item["role"] == "Muse" and item["stage"] == "draft")
    failed_exchange(exchange, status=status, category=category)
    scene["grades"][0]["failures"] = ["runtime_model_failure"]
    scene["hard_gate_pass"] = False
    original = json.dumps(scene, sort_keys=True)

    assert validate(artifact, scene, backstory, truth, "connection_curation_replay")
    assert json.dumps(scene, sort_keys=True) == original


def test_native_projection_failure_retains_the_observed_agent_output():
    artifact, backstory, truth = bundle("connection_curation_replay")
    scene = artifact["scenes"][5]
    exchange = next(item for item in scene["agent_exchanges"] if item["role"] == "Muse" and item["stage"] == "draft")
    assert exchange["output"] is not None
    exchange.update(status="failure", failure_code="agent_result_projection_failed", failure_category="unknown_error")
    scene["grades"][0]["failures"] = ["runtime_application_failure"]
    scene["hard_gate_pass"] = False
    original = json.dumps(scene, sort_keys=True)

    assert validate(artifact, scene, backstory, truth, "connection_curation_replay")
    assert json.dumps(scene, sort_keys=True) == original


@pytest.mark.parametrize("mutation", [
    "empty", "unknown_status", "missing_code", "missing_category",
    "incomplete_exchange", "missing_release",
])
def test_native_failure_requires_complete_terminal_and_release_observations(mutation):
    artifact, backstory, truth = bundle("memory_loop_replay")
    scene = artifact["scenes"][1]
    grade = scene["grades"][0]
    exchange = grade["agent_exchanges"][0]
    failed_exchange(exchange)
    grade["hard_failures"] = ["runtime_model_failure"]
    grade["ground_truth_result"] = "fails_hard_gates"
    if mutation == "empty":
        grade["agent_exchanges"] = []
    elif mutation == "unknown_status":
        exchange["status"] = "pending"
    elif mutation == "missing_code":
        exchange["failure_code"] = None
    elif mutation == "missing_category":
        exchange["failure_category"] = None
    elif mutation == "incomplete_exchange":
        exchange["failure_code"] = "incomplete_agent_exchange"
    elif mutation == "missing_release":
        grade["events"] = [event for event in grade["events"] if event["kind"] != "release"]

    with pytest.raises(ValueError):
        validate(artifact, scene, backstory, truth, "memory_loop_replay")


def failed_round(artifact, stage, *, index=0):
    observation = artifact["curation"][index]
    if stage == "curation":
        observation["agent_exchanges"] = observation["agent_exchanges"][:1]
    failed_exchange(observation["agent_exchanges"][-1])
    observation.update(
        status="failed", failure="provider_request_failed", action=None,
        source_prop_ids=[], provenance_decision=None,
    )
    if index:
        observation["retrieval_view"] = json.loads(json.dumps(artifact["curation"][index - 1]["retrieval_view"]))
    return observation


@pytest.mark.parametrize("stage", ["curation", "curation_review"])
@pytest.mark.parametrize("index", [0, 2])
def test_failed_native_round_preserves_trusted_batch_and_unchanged_retrieval(stage, index):
    artifact, backstory, truth = bundle("memory_loop_replay")
    failed_round(artifact, stage, index=index)
    original = json.dumps(artifact, sort_keys=True)

    assert validate(artifact, artifact["scenes"][1], backstory, truth, "memory_loop_replay")
    assert json.dumps(artifact, sort_keys=True) == original


@pytest.mark.parametrize("mutation", [None, "changed_view", "changed_input"])
def test_generated_invalid_proposal_rejected_before_review_remains_a_recorded_outcome(mutation):
    artifact, backstory, truth = bundle("memory_loop_replay")
    observation = artifact["curation"][0]
    sculptor = observation["agent_exchanges"][0]
    observation.update(
        status="failed", failure="InvalidCurationProposal", action=None,
        source_prop_ids=[], provenance_decision=None, agent_exchanges=[sculptor],
    )
    sculptor["output"]["action"]["source_memory_ids"][0] = "unknown-generated-memory-id"
    for tool in sculptor["tool_exchanges"]:
        tool["arguments"] = json.dumps(sculptor["output"])
    for message in sculptor["model_messages"]:
        for part in message["parts"]:
            if part.get("part_kind") == "tool-call":
                part["args"] = json.dumps(sculptor["output"])
    if mutation == "changed_view":
        observation["retrieval_view"].pop()
    elif mutation == "changed_input":
        payload = json.loads(sculptor["input_prompt"])
        payload["memories"][0]["text"] = "Changed source content."
        sculptor["input_prompt"] = json.dumps(payload)

    if mutation is None:
        original = json.dumps(artifact, sort_keys=True)
        assert validate(artifact, artifact["scenes"][1], backstory, truth, "memory_loop_replay")
        assert json.dumps(artifact, sort_keys=True) == original
    else:
        with pytest.raises(ValueError):
            validate(artifact, artifact["scenes"][1], backstory, truth, "memory_loop_replay")


@pytest.mark.parametrize("mutation", [
    "missing_reason", "missing_transcript", "successful_agents", "invented_action",
    "invented_approval", "unknown_source", "changed_input", "unknown_review_source",
    "missing_original", "new_derivation",
])
def test_failed_round_cannot_bypass_source_storage_or_approval_evidence(mutation):
    artifact, backstory, truth = bundle("memory_loop_replay")
    observation = failed_round(artifact, "curation_review")
    if mutation == "missing_reason":
        observation["failure"] = None
    elif mutation == "missing_transcript":
        observation["agent_exchanges"] = []
    elif mutation == "successful_agents":
        observation["agent_exchanges"][-1] = bundle("memory_loop_replay")[0]["curation"][0]["agent_exchanges"][-1]
    elif mutation == "invented_action":
        observation["action"] = "update_derived_summary"
    elif mutation == "invented_approval":
        observation["provenance_decision"] = "allow"
    elif mutation == "unknown_source":
        observation["retrieval_view"][0]["source_prop_ids"] = ["another-account"]
    elif mutation == "changed_input":
        exchange = observation["agent_exchanges"][0]
        payload = json.loads(exchange["input_prompt"])
        payload["memories"][0]["text"] = "Another account's source."
        exchange["input_prompt"] = json.dumps(payload)
    elif mutation == "unknown_review_source":
        sculptor, reviewer = observation["agent_exchanges"]
        payload = json.loads(reviewer["input_prompt"])
        unknown = "another-account-memory"
        sculptor["output"]["action"]["source_memory_ids"][0] = unknown
        payload["proposal"]["action"]["source_memory_ids"][0] = unknown
        payload["sources"][0]["memory_id"] = unknown
        reviewer["input_prompt"] = json.dumps(payload)
    elif mutation == "missing_original":
        observation["retrieval_view"].pop()
    elif mutation == "new_derivation":
        observation["retrieval_view"].append({
            "kind": "derived_summary", "source_prop_ids": list(backstory["scenes"][1]["prop_ids"][:2]),
            "text": "An unapproved summary.",
        })

    with pytest.raises(ValueError):
        validate(artifact, artifact["scenes"][1], backstory, truth, "memory_loop_replay")


@pytest.mark.parametrize("mutation", [
    "missing_arm", "duplicate_arm", "unknown_arm", "bad_result", "missing_failures", "false_pass",
    "missing_round", "duplicate_round", "failed_round", "failed_round_exchange", "missing_round_transcript",
    "unapproved_application", "unknown_round_source", "changed_configuration", "changed_relevance", "capture_enabled",
    "unbound_round_review", "missing_round_sculptor", "changed_round_input", "changed_derived_projection",
])
def test_memory_loop_matrix_and_round_evidence_fail_closed(mutation):
    artifact, backstory, truth = bundle("memory_loop_replay")
    scene = artifact["scenes"][1]
    if mutation == "missing_arm":
        scene["grades"].pop()
    elif mutation == "duplicate_arm":
        scene["grades"][-1] = scene["grades"][0]
    elif mutation == "unknown_arm":
        scene["grades"][0]["repetition"] = 99
    elif mutation == "bad_result":
        scene["grades"][0]["ground_truth_result"] = "proposal_matches"
    elif mutation == "missing_failures":
        del scene["grades"][0]["hard_failures"]
    elif mutation == "false_pass":
        scene["grades"][0]["hard_failures"] = ["unknown_evidence_cited"]
        scene["grades"][0]["ground_truth_result"] = "passes_hard_gates"
    elif mutation == "missing_round":
        artifact["curation"].pop()
    elif mutation == "duplicate_round":
        artifact["curation"][-1] = artifact["curation"][0]
    elif mutation == "failed_round":
        artifact["curation"][0]["status"] = "failed"
        artifact["curation"][0]["failure"] = "provider_failure"
    elif mutation == "failed_round_exchange":
        artifact["curation"][0]["agent_exchanges"][0]["status"] = "failed"
    elif mutation == "missing_round_transcript":
        artifact["curation"][0]["agent_exchanges"] = []
    elif mutation == "unapproved_application":
        artifact["curation"][1]["provenance_decision"] = "reject"
    elif mutation == "unknown_round_source":
        artifact["curation"][1]["source_prop_ids"] = ["another-account"]
    elif mutation == "changed_configuration":
        artifact["curation_rounds"] = 2
    elif mutation == "changed_relevance":
        scene["relevant_prop_ids"] = []
    elif mutation == "capture_enabled":
        artifact["capture_enabled"] = True
    elif mutation == "unbound_round_review":
        artifact["curation"][1]["agent_exchanges"][1]["output"]["proposal_digest"] = "0" * 64
    elif mutation == "missing_round_sculptor":
        artifact["curation"][1]["agent_exchanges"] = artifact["curation"][1]["agent_exchanges"][1:]
    elif mutation == "changed_round_input":
        exchange = artifact["curation"][1]["agent_exchanges"][0]
        payload = json.loads(exchange["input_prompt"])
        payload["memories"][0]["text"] = "Another account's content."
        exchange["input_prompt"] = json.dumps(payload)
    elif mutation == "changed_derived_projection":
        derived = next(item for item in artifact["curation"][1]["retrieval_view"] if item["kind"] == "derived_summary")
        derived["text"] = "Unreviewed replacement text."

    with pytest.raises(ValueError):
        validate(artifact, scene, backstory, truth, "memory_loop_replay")


@pytest.mark.parametrize("mutation", [
    "missing_grade", "malformed_failures", "false_pass", "changed_expected", "changed_source",
    "changed_hash", "missing_outcome", "missing_approval", "missing_audit", "unknown_source",
    "missing_transcript", "failed_exchange", "missing_adopted_judgment",
    "unbound_review", "missing_sculptor", "unknown_retrieval", "changed_review_source", "changed_sculptor_input",
    "changed_sculptor_output", "changed_review_proposal",
])
def test_curation_requires_singular_grade_and_actual_authorized_outcome(mutation):
    artifact, backstory, truth = bundle("curation_replay")
    scene = artifact["scenes"][0]
    if mutation == "missing_grade":
        del scene["grade"]
    elif mutation == "malformed_failures":
        scene["grade"]["failures"] = "none"
    elif mutation == "false_pass":
        scene["grade"]["hard_pass"] = False
    elif mutation == "changed_expected":
        scene["expected"]["primary_behavior"] = "unrelated"
    elif mutation == "changed_source":
        scene["input_memories"][0]["text"] = "Changed original."
    elif mutation == "changed_hash":
        scene["source_hashes_after"][0]["sha256"] = "0" * 64
    elif mutation == "missing_outcome":
        del scene["actual_outcome"]["application_created"]
    elif mutation == "missing_approval":
        scene["actual_outcome"]["provenance_decision"] = "reject"
    elif mutation == "missing_audit":
        scene["actual_outcome"]["audit_verified"] = False
    elif mutation == "unknown_source":
        scene["response"]["action"]["source_memory_ids"] = ["another-account"]
    elif mutation == "missing_transcript":
        scene["agent_exchanges"] = []
    elif mutation == "failed_exchange":
        scene["agent_exchanges"][0]["status"] = "failed"
    elif mutation == "missing_adopted_judgment":
        truth["proposals"] = truth["proposals"][1:]
    elif mutation == "unbound_review":
        scene["agent_exchanges"][1]["output"]["proposal_digest"] = "0" * 64
    elif mutation == "missing_sculptor":
        scene["agent_exchanges"] = scene["agent_exchanges"][1:]
    elif mutation == "unknown_retrieval":
        scene["actual_outcome"]["retrieval_memory_ids"] = ["another-account-memory"]
    elif mutation == "changed_review_source":
        exchange = scene["agent_exchanges"][1]
        payload = json.loads(exchange["input_prompt"])
        payload["sources"][0]["text"] = "Different content."
        exchange["input_prompt"] = json.dumps(payload)
    elif mutation == "changed_sculptor_input":
        exchange = scene["agent_exchanges"][0]
        payload = json.loads(exchange["input_prompt"])
        payload["memories"][0]["text"] = "Different content."
        exchange["input_prompt"] = json.dumps(payload)
    elif mutation == "changed_sculptor_output":
        scene["agent_exchanges"][0]["output"]["action"]["source_memory_ids"] = ["unapproved"]
    elif mutation == "changed_review_proposal":
        exchange = scene["agent_exchanges"][1]
        payload = json.loads(exchange["input_prompt"])
        payload["proposal"]["action"]["source_memory_ids"].reverse()
        exchange["input_prompt"] = json.dumps(payload)

    with pytest.raises(ValueError):
        validate(artifact, scene, backstory, truth, "curation_replay")


def test_reviewed_idempotent_curation_keeps_valid_audit_evidence():
    artifact, backstory, truth = bundle("curation_replay")
    scene = artifact["scenes"][0]
    scene["actual_outcome"]["application_created"] = False
    scene["grade"]["hard_pass"] = False
    scene["grade"]["failures"] = ["outcome_application_created_mismatch"]
    scene["ground_truth_result"] = "fails_hard_gates"

    assert validate(artifact, scene, backstory, truth, "curation_replay")


def test_derived_retrieval_identity_is_bound_to_the_reviewed_action():
    artifact, backstory, truth = bundle("curation_replay")
    scene = next(item for item in artifact["scenes"] if any(identity.startswith("topic_") for identity in item["actual_outcome"]["retrieval_memory_ids"]))
    assert validate(artifact, scene, backstory, truth, "curation_replay")

    scene["actual_outcome"]["retrieval_memory_ids"] = ["topic_" + "0" * 64]
    with pytest.raises(ValueError):
        validate(artifact, scene, backstory, truth, "curation_replay")


@pytest.mark.parametrize("mutation", ["missing_grade", "duplicate_grade", "wrong_objective", "inconsistent_result"])
def test_mixed_connection_preserves_exact_adopted_judgment_coverage(mutation):
    artifact, backstory, truth = bundle("connection_curation_replay")
    scene = artifact["scenes"][5]
    if mutation == "missing_grade":
        scene["grades"] = []
    elif mutation == "duplicate_grade":
        scene["grades"].append(scene["grades"][0])
    elif mutation == "wrong_objective":
        scene["grades"][0]["objective_id"] = "bounded_memory_curation"
    elif mutation == "inconsistent_result":
        scene["hard_gate_pass"] = not scene["hard_gate_pass"]
    with pytest.raises(ValueError):
        validate(artifact, scene, backstory, truth, "connection_curation_replay")
