"""Canonical public book mistakes remain distinguishable from invalid evidence."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from apps.backend.librarian import Librarian
from evals.release.security_evidence import verified_book_reading_evidence, verified_book_source_records
from provenance_fixtures import review_with_audits
from src.linger.agents.provenance.models import ProvenanceInput


ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "event-led-book-grounding-and-clarification--muse-librarian-provenance--2026-09-16"
RUNNER = "evals.synthetic_journals.book_replay"
LATER = "pg11-v01b38ea4-ch05-ln1179-1219"


@pytest.fixture
def evidence():
    saved = json.loads((ROOT / "results" / SCENARIO / "result.json").read_text())["evidence"]
    observed = saved["evaluation"]["data"]["scenes"][0]
    backstory = saved["inputs"]["backstory.json"]["data"]
    planned = next(item for item in backstory["scenes"] if item["scene_id"] == observed["scene_id"])
    return observed, planned, backstory


def proof(evidence, runner=RUNNER):
    return verified_book_reading_evidence(*evidence, runner)


def final_pair(observed):
    muse = next(item for item in reversed(observed["agent_exchanges"])
                if item["role"] == "Muse" and item["stage"] in {"draft", "revision"})
    review = next(item for item in reversed(observed["agent_exchanges"])
                  if item["role"] == "Provenance" and item["stage"] == "review")
    return muse, review


def add_later_citation(observed, identity=LATER):
    canonical = Librarian().fetch_by_id(identity)
    muse, review = final_pair(observed)
    sentence = "Alice tells the Pigeon that she is a little girl."
    muse["output"]["reply"] += " " + sentence
    muse["output"]["evidence_uses"].append({
        "source_kind": "book_corpus", "evidence_id": identity,
        "source_location": canonical.location, "supported_claims": [sentence],
        "limit_claims": [], "exact_quote": None,
    })
    observed["reply"] = muse["output"]["reply"]
    observed["released_evidence_ids"].append(identity)
    observed["grounding_calls"][0]["evidence"].append(canonical.model_dump(mode="json"))
    payload = json.loads(review["input_prompt"])
    payload["candidate"] = {
        "response": muse["output"]["reply"], "memory": muse["output"]["memory"],
        "evidence_uses": muse["output"]["evidence_uses"],
    }
    payload["canonical_book_evidence"].append(canonical.model_dump(mode="json"))
    task = ProvenanceInput.model_validate(payload)
    review["input_prompt"] = task.model_dump_json()
    review["output"] = review_with_audits(task, {
        "response_decision": "pass", "capture_decision": "no_candidate",
        "emotional_boundary_decision": "not_required",
        "finding_resolutions": review["output"]["finding_resolutions"],
    }).model_dump(mode="json")
    observed["grades"][0].update(hard_pass=False, failures=["response_cited_unpermitted_evidence"])
    observed["ground_truth_result"] = "fails_hard_gates"


def test_completed_canonical_later_chapter_is_proved_without_changing_its_grade(evidence):
    assert proof(evidence) is True
    add_later_citation(evidence[0])
    assert evidence[0]["routed_ceiling"] == 3
    before = deepcopy(evidence)
    assert proof(evidence) is True
    assert evidence == before
    assert evidence[0]["grades"][0]["failures"] == ["response_cited_unpermitted_evidence"]


def test_canonical_public_book_mistake_does_not_require_a_confirmed_reading_boundary(evidence):
    observed = evidence[0]
    add_later_citation(observed)
    muse, review = final_pair(observed)
    envelope = json.loads(muse["input_prompt"])
    envelope["muse_turn"]["reading_context"] = None
    envelope["muse_turn"]["policy"].update(spoiler_ceiling=None, allow_retrieval=False, allow_connection=False)
    muse["input_prompt"] = json.dumps(envelope)
    payload = json.loads(review["input_prompt"])
    payload["context"]["reading_context"] = None
    payload["context"]["policy"].update(spoiler_ceiling=None, allow_retrieval=False, allow_connection=False)
    review["input_prompt"] = json.dumps(payload)
    assert proof(evidence) is True


def test_another_canonical_public_work_is_still_a_book_quality_mistake(evidence):
    add_later_citation(evidence[0], "pga0100011-vc7ff4da7-ch05-ln1133-1158")
    assert proof(evidence) is True


def test_complete_failed_agent_task_keeps_valid_source_evidence_without_a_successful_reply(evidence):
    observed = evidence[0]
    muse, review = final_pair(observed)
    observed["agent_exchanges"].remove(review)
    muse.update(status="failure", output=None, failure_code="muse_model_failed", failure_category="unknown_error")
    observed.update(reply="The task could not be completed.", released_evidence_ids=[],
                    release_source="application_safe_decline", provenance_verdicts=[],
                    ground_truth_result="fails_hard_gates")
    observed["grades"][0].update(hard_pass=False, failures=["evidence_exceeded_safe_scope"])
    before = deepcopy(observed)
    assert verified_book_source_records(observed) is True
    assert proof(evidence) is False
    assert observed == before


@pytest.mark.parametrize("location", ["review", "grounding", "boundary"])
def test_recorded_book_inventories_reject_corrupt_records(evidence, location):
    observed = evidence[0]
    _, review = final_pair(observed)
    if location == "review":
        payload = json.loads(review["input_prompt"])
        payload["canonical_book_evidence"][0]["text"] = "A forged passage."
        review["input_prompt"] = json.dumps(payload)
    elif location == "grounding":
        observed["grounding_calls"][0]["evidence"][0]["text"] = "A forged passage."
    else:
        observed["boundary_support_evidence"] = [
            observed["grounding_calls"][0]["evidence"][0] | {"text": "A forged passage."},
        ]
    assert verified_book_source_records(observed) is False


@pytest.mark.parametrize("location", ["grounding", "review"])
@pytest.mark.parametrize("kind", ["string", "float", "boolean"])
def test_book_source_metadata_must_not_be_coerced_into_canonical_records(evidence, location, kind):
    observed = evidence[0]
    _, review = final_pair(observed)
    payload = json.loads(review["input_prompt"])
    record = (observed["grounding_calls"][0]["evidence"][0] if location == "grounding"
              else payload["canonical_book_evidence"][0])
    chapter = record["chapter_number"]
    record["chapter_number"] = {"string": str(chapter), "float": float(chapter), "boolean": True}[kind]
    if location == "review":
        review["input_prompt"] = json.dumps(payload)
    assert verified_book_source_records(observed) is False
    assert proof(evidence) is False


def test_failed_review_attempt_with_malformed_input_does_not_replace_actual_source_observations(evidence):
    observed = evidence[0]
    _, review = final_pair(observed)
    review.update(status="failure", output=None, failure_code="provenance_model_failed",
                  input_prompt="The attempted review input could not be serialized.")
    observed.update(release_source="application_safe_decline", released_evidence_ids=[], provenance_verdicts=[],
                    ground_truth_result="fails_hard_gates")
    observed["grades"][0].update(hard_pass=False, failures=["evidence_exceeded_safe_scope"])
    before = deepcopy(observed)
    assert verified_book_source_records(observed) is True
    assert proof(evidence) is False
    assert observed == before


def test_empty_failed_attempt_inventory_is_valid_but_missing_required_release_source_is_not(evidence):
    observed = evidence[0]
    muse, review = final_pair(observed)
    observed["agent_exchanges"].remove(review)
    muse.update(status="failure", output=None, failure_code="muse_model_failed", failure_category="unknown_error")
    observed.update(grounding_calls=[], boundary_support_evidence=[], released_evidence_ids=[],
                    release_source="application_safe_decline", provenance_verdicts=[])
    assert verified_book_source_records(observed) is True
    observed["released_evidence_ids"] = [LATER]
    assert verified_book_source_records(observed) is False


def test_existing_revised_book_reply_keeps_its_actual_approval_chain():
    saved = json.loads((ROOT / "results" / SCENARIO / "result.json").read_text())["evidence"]
    observed = saved["evaluation"]["data"]["scenes"][2]
    backstory = saved["inputs"]["backstory.json"]["data"]
    planned = next(item for item in backstory["scenes"] if item["scene_id"] == observed["scene_id"])
    assert observed["provenance_verdicts"] == ["revise", "pass"]
    assert proof((observed, planned, backstory)) is True

    review = final_pair(observed)[1]
    payload = json.loads(review["input_prompt"])
    payload["previous_response_review"]["candidate"]["response"] = "An unobserved earlier draft."
    review["input_prompt"] = json.dumps(payload)
    assert proof((observed, planned, backstory)) is False


@pytest.mark.parametrize("mutation", [
    "missing_exchanges", "missing_muse", "missing_review", "failed_muse", "failed_review",
    "provider_error", "wrong_contract", "wrong_scene", "wrong_line", "wrong_input_line",
    "wrong_muse_line", "wrong_review_line", "unbound_review", "wrong_reply", "wrong_verdicts",
    "missing_approval", "missing_records", "forged_text", "forged_source_hash", "forged_source_lines",
    "forged_grounding", "forged_boundary_evidence", "unknown_id", "missing_citation", "duplicate_citation",
    "memory_use", "web_use", "session_use", "wrong_source_location", "stale_review", "incomplete_audit",
])
def test_missing_invalid_or_private_evidence_cannot_be_relabelled_as_a_book_mistake(evidence, mutation):
    observed, planned, _ = evidence
    add_later_citation(observed)
    muse, review = final_pair(observed)
    payload = json.loads(review["input_prompt"])
    if mutation == "missing_exchanges":
        observed["agent_exchanges"] = []
    elif mutation in {"missing_muse", "missing_review"}:
        observed["agent_exchanges"].remove(muse if mutation == "missing_muse" else review)
    elif mutation in {"failed_muse", "failed_review"}:
        exchange = muse if mutation == "failed_muse" else review
        exchange.update(status="failure", failure_code="model_failed")
    elif mutation == "provider_error":
        review["provider_status_code"] = 429
    elif mutation == "wrong_contract":
        review["input_contract"] = "untrusted.Review"
    elif mutation == "wrong_scene":
        planned["scene_id"] = "another-scene"
    elif mutation == "wrong_line":
        observed["line_id"] = "another-line"
    elif mutation == "wrong_input_line":
        observed["input_line"] = "A different reader input."
    elif mutation == "wrong_muse_line":
        envelope = json.loads(muse["input_prompt"])
        envelope["muse_turn"]["user_message"] = "A different reader input."
        muse["input_prompt"] = json.dumps(envelope)
    elif mutation == "wrong_review_line":
        payload["current_line"]["text"] = "A different reader input."
    elif mutation == "unbound_review":
        payload["candidate"]["response"] = "An independently approved reply."
    elif mutation == "wrong_reply":
        observed["reply"] = "An unreviewed reply."
    elif mutation == "wrong_verdicts":
        observed["provenance_verdicts"] = ["revise", "pass"]
    elif mutation == "missing_approval":
        observed["provenance_verdicts"] = []
    elif mutation == "missing_records":
        payload["canonical_book_evidence"] = []
    elif mutation in {"forged_text", "forged_source_hash", "forged_source_lines"}:
        key, value = {
            "forged_text": ("text", "A forged passage."),
            "forged_source_hash": ("source_sha256", "0" * 64),
            "forged_source_lines": ("source_lines", [1, 2]),
        }[mutation]
        payload["canonical_book_evidence"][-1][key] = value
    elif mutation == "forged_grounding":
        observed["grounding_calls"][0]["evidence"][-1]["text"] = "A forged passage."
    elif mutation == "forged_boundary_evidence":
        observed["boundary_support_evidence"] = [payload["canonical_book_evidence"][-1] | {"text": "A forged passage."}]
    elif mutation in {"unknown_id", "missing_citation", "duplicate_citation"}:
        if mutation == "unknown_id":
            observed["released_evidence_ids"].append("another-account-memory")
        elif mutation == "missing_citation":
            observed["released_evidence_ids"].remove(LATER)
        else:
            observed["released_evidence_ids"].append(LATER)
    elif mutation in {"memory_use", "web_use", "session_use"}:
        use = muse["output"]["evidence_uses"][-1]
        if mutation == "session_use":
            replacement = {"source_kind": "session_line", "quote": "An earlier private reader statement.",
                           "supported_claims": use["supported_claims"]}
        else:
            replacement = {key: value for key, value in use.items() if key != "source_location"}
            replacement["source_kind"] = "memory" if mutation == "memory_use" else "web"
        muse["output"]["evidence_uses"][-1] = replacement
        payload["candidate"]["evidence_uses"][-1] = replacement
    elif mutation == "wrong_source_location":
        muse["output"]["evidence_uses"][-1]["source_location"] = "A different location."
        payload["candidate"]["evidence_uses"][-1]["source_location"] = "A different location."
    elif mutation == "stale_review":
        muse["sequence"], review["sequence"] = review["sequence"], muse["sequence"]
        observed["agent_exchanges"].sort(key=lambda exchange: exchange["sequence"])
    elif mutation == "incomplete_audit":
        review["output"]["claim_audit"] = []
    review["input_prompt"] = json.dumps(payload)
    assert proof(evidence) is False


@pytest.mark.parametrize("runner", ["evals.synthetic_journals.reflection_replay", "connection_replay", "unknown"])
def test_unsupported_runners_do_not_gain_a_book_exception(evidence, runner):
    assert proof(evidence, runner) is False
