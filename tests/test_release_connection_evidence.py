"""Extra book passages require verifiable authority before release classification."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from apps.backend.contracts import EvidenceItem
from apps.backend.librarian import Librarian
from evals.release.connection_evidence import verified_connection_book_evidence
from evals.release.gate import validate_artifact
from evals.release.policy import publication_decision
from provenance_fixtures import review_with_audits
from src.linger.agents.provenance.models import ProvenanceInput


ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "cross-source-connections-and-restraint--muse-librarian-serendipity-provenance--2026-09-12"
EXTRA = "pg11-v01b38ea4-ch05-ln1179-1219"
RUNNER = "evals.synthetic_journals.connection_replay"


def book_record(identity=EXTRA):
    canonical = Librarian().fetch_by_id(identity)
    assert canonical is not None
    return EvidenceItem(
        evidence_id=canonical.evidence_id, work_id=canonical.work_id,
        book_version_id=canonical.book_version_id, chapter_id=canonical.chapter_id,
        source_title="Alice's Adventures in Wonderland", location=canonical.location,
        chapter=canonical.chapter_number, part_id=canonical.part_id,
        source_sha256=canonical.source_sha256, source_lines=canonical.source_lines,
        excerpt=canonical.text, relevance=1,
    ).model_dump(mode="json")


@pytest.fixture
def evidence():
    saved = json.loads((ROOT / "results" / SCENARIO / "result.json").read_text())["evidence"]
    artifact = saved["evaluation"]["data"]
    backstory = saved["inputs"]["backstory.json"]["data"]
    truth = saved["inputs"]["ground-truth.json"]["data"]
    observed = artifact["scenes"][0]
    extra = book_record()
    for event in observed["events"]:
        if event["kind"] == "search" and event["source"] == "book_corpus":
            event["evidence_json"].append(json.dumps(extra))
        if event["kind"] == "discovery":
            event["evidence_json"].append(json.dumps(extra))
            decision = json.loads(event["decision_json"])
            decision["evidence_ids"].append(EXTRA)
            event["decision_json"] = json.dumps(decision)
    selection = next(item for item in observed["agent_exchanges"] if item["role"] == "Serendipity")
    selection["output"] = decision
    tool = next(item for item in selection["tool_exchanges"] if item["tool_name"] == "search_librarian")
    tool["result"]["evidence"].append(extra)
    tool["result"]["judgement"]["relevant_evidence_ids"].append(EXTRA)
    assessment = next(item for item in observed["agent_exchanges"]
                      if item["role"] == "Librarian" and item["stage"] == "evidence_strength")
    assessment["output"]["relevant_evidence_ids"].append("E3")
    assessment["output"]["support"].append({
        "evidence_id": "E3", "part_index": 0, "necessary_support": "The related identity exchange in Chapter 5.",
    })
    observed["grades"][0]["failures"] = ["authorized_book_selection_mismatch"]
    observed["hard_gate_pass"] = False
    planned = next(item for item in backstory["scenes"] if item["scene_id"] == observed["scene_id"])
    return artifact, observed, planned, backstory, truth


def proof(evidence):
    artifact, observed, planned, backstory, truth = evidence
    return verified_connection_book_evidence(observed, planned, backstory, truth, RUNNER)


def add_citation(evidence):
    _, observed, _, _, _ = evidence
    canonical = Librarian().fetch_by_id(EXTRA)
    sentence = "Alice tells the Pigeon that she is a little girl."
    candidate = next(item for item in reversed(observed["agent_exchanges"])
                     if item["role"] == "Muse" and item["stage"] in {"draft", "revision"})
    candidate["output"]["reply"] += " " + sentence
    candidate["output"]["evidence_uses"].append({
        "source_kind": "book_corpus", "evidence_id": EXTRA, "source_location": canonical.location,
        "supported_claims": [sentence], "limit_claims": [], "exact_quote": None,
    })
    observed["reply"] = candidate["output"]["reply"]
    observed["released_evidence_ids"].append(EXTRA)
    observed["events"][-1]["released_evidence_ids"].append(EXTRA)
    review = next(item for item in reversed(observed["agent_exchanges"])
                  if item["role"] == "Provenance" and item["stage"] == "review")
    payload = json.loads(review["input_prompt"])
    payload["candidate"] = {
        "response": candidate["output"]["reply"], "memory": candidate["output"]["memory"],
        "evidence_uses": candidate["output"]["evidence_uses"],
    }
    payload["canonical_book_evidence"].append(canonical.model_dump(mode="json"))
    task = ProvenanceInput.model_validate(payload)
    review["input_prompt"] = task.model_dump_json()
    review["output"] = review_with_audits(task, {
        "response_decision": "pass", "capture_decision": "no_candidate",
        "emotional_boundary_decision": "not_required",
        "finding_resolutions": review["output"]["finding_resolutions"],
    }).model_dump(mode="json")
    observed["grades"][0]["failures"].append("authorized_book_citation_mismatch")


def candidate_summary(evidence, tmp_path):
    artifact, _, _, backstory, truth = evidence
    hashes = {}
    for filename, data in (("backstory.json", backstory), ("ground-truth.json", truth)):
        raw = json.dumps(data).encode()
        (tmp_path / filename).write_bytes(raw)
        hashes[filename] = hashlib.sha256(raw).hexdigest()
    (tmp_path / "ground-truth-adoption.json").write_text(json.dumps({
        "adopted_ground_truth_identity": artifact["dataset_version"],
    }))
    return validate_artifact(artifact, tmp_path, {
        "runner": RUNNER, "objective_ids": artifact["objective_ids"], "hashes": hashes,
    })


@pytest.mark.parametrize("cited", [False, True])
def test_verified_extra_book_remains_a_failed_judgment_without_blocking(evidence, tmp_path, cited):
    if cited:
        add_citation(evidence)
    before = deepcopy(evidence)
    assert proof(evidence) is True
    # The saved fixture also has an unrelated old S3 restraint failure.
    evidence[0]["scenes"][2]["grades"][0]["failures"] = ["unnecessary_declined_exploration"]
    summary = candidate_summary(evidence, tmp_path)
    assert summary["judgments_total"] == 4
    assert summary["judgments_passed"] == 2
    assert summary["judgments_failed"] == 2
    assert not summary["blocking_failures"]
    assert publication_decision(
        judgments_passed=summary["judgments_passed"], judgments_total=summary["judgments_total"],
        complete=True, blocked=False, auto_publish_enabled=True, threshold=80,
    )["route"] == "manual"
    before[0]["scenes"][2]["grades"][0]["failures"] = ["unnecessary_declined_exploration"]
    assert evidence == before


@pytest.mark.parametrize("attempt", ["selection", "assessment", "tool", "search_event"])
@pytest.mark.parametrize("cited", [False, True])
def test_failed_earlier_attempt_does_not_invalidate_successful_authority_proof(evidence, tmp_path, attempt, cited):
    if cited:
        add_citation(evidence)
    observed = evidence[1]
    selection = next(item for item in observed["agent_exchanges"] if item["role"] == "Serendipity")
    if attempt in {"selection", "assessment"}:
        original = selection if attempt == "selection" else next(
            item for item in observed["agent_exchanges"]
            if item["role"] == "Librarian" and item["stage"] == "evidence_strength"
        )
        failed = deepcopy(original)
        failed.update(status="failure", output=None, tool_exchanges=[], usage=None,
                      failure_code="earlier_model_failed", failure_category="unknown_error")
        observed["agent_exchanges"].insert(observed["agent_exchanges"].index(original), failed)
        for index, exchange in enumerate(observed["agent_exchanges"], 1):
            exchange["sequence"] = index
    elif attempt == "tool":
        failed = deepcopy(next(tool for tool in selection["tool_exchanges"]
                               if tool["tool_name"] == "search_librarian"))
        failed.update(outcome="failure", result=None, tool_call_id="failed-earlier-search")
        selection["tool_exchanges"].insert(0, failed)
    else:
        failed = deepcopy(next(event for event in observed["events"]
                               if event["kind"] == "search" and event["source"] == "book_corpus"))
        failed.update(status="retrieval_unavailable", evidence_json=[], failure_code="earlier_search_failed")
        observed["events"].insert(0, failed)
    observed["grades"][0]["failures"].append("provider_failure" if attempt in {"selection", "assessment"}
                                              else "retrieval_failure")
    assert proof(evidence) is True
    summary = candidate_summary(evidence, tmp_path)
    assert not summary["blocking_failures"]
    assert summary["judgments_total"] == 4
    assert summary["judgments_passed"] == 2
    assert summary["judgments_failed"] == 2
    if attempt in {"selection", "assessment"}:
        assert any("earlier_model_failed" in item["detail"] for item in summary["execution_failures"])


@pytest.mark.parametrize("mutation", [
    "missing_ledger", "forged_text", "missing_source_tool", "changed_tool_result",
    "missing_transcript", "missing_selection", "different_selection", "missing_review",
    "unbound_review", "wrong_line", "widened_scope", "missing_scope", "release_ids",
    "review_not_passed", "failed_book_tool", "failed_exchange", "missing_release",
    "empty_extra", "mixed_unknown", "foreign_memory", "later_chapter",
    "missing_first_review", "missing_draft", "missing_judgement", "unselected_passages",
    "missing_book_search", "missing_librarian", "wrong_librarian_selection",
    "review_retrieval_disabled", "review_connection_disabled",
])
def test_labels_cannot_replace_complete_authorized_evidence(evidence, tmp_path, mutation):
    observed = evidence[1]
    selection = next(item for item in observed["agent_exchanges"] if item["role"] == "Serendipity")
    review = next(item for item in reversed(observed["agent_exchanges"])
                  if item["role"] == "Provenance" and item["stage"] == "review")
    if mutation == "missing_book_search":
        observed["events"] = [e for e in observed["events"] if not (
            e["kind"] == "search" and e["source"] == "book_corpus"
        )]
    elif mutation == "missing_librarian":
        observed["agent_exchanges"] = [e for e in observed["agent_exchanges"] if e["role"] != "Librarian"]
        for index, exchange in enumerate(observed["agent_exchanges"], 1):
            exchange["sequence"] = index
    elif mutation == "wrong_librarian_selection":
        output = next(e["output"] for e in observed["agent_exchanges"]
                      if e["role"] == "Librarian" and e["stage"] == "evidence_strength")
        output["relevant_evidence_ids"] = ["E1"]
        output["support"] = [x for x in output["support"] if x["evidence_id"] == "E1"]
    elif mutation in {"review_retrieval_disabled", "review_connection_disabled"}:
        payload = json.loads(review["input_prompt"])
        field = "allow_retrieval" if mutation == "review_retrieval_disabled" else "allow_connection"
        payload["context"]["policy"][field] = False
        review["input_prompt"] = json.dumps(payload)
    elif mutation == "missing_ledger":
        for event in observed["events"]:
            event["evidence_json"] = [raw for raw in event["evidence_json"]
                                      if json.loads(raw)["evidence_id"] != EXTRA]
    elif mutation == "forged_text":
        for event in observed["events"]:
            event["evidence_json"] = [json.dumps(json.loads(raw) | {"excerpt": "Forged."})
                                      if json.loads(raw)["evidence_id"] == EXTRA else raw
                                      for raw in event["evidence_json"]]
    elif mutation == "missing_source_tool":
        selection["tool_exchanges"] = [t for t in selection["tool_exchanges"] if t["tool_name"] != "search_librarian"]
    elif mutation in {"missing_judgement", "unselected_passages"}:
        result = next(t for t in selection["tool_exchanges"] if t["tool_name"] == "search_librarian")["result"]
        if mutation == "missing_judgement":
            del result["judgement"]
        else:
            result["judgement"]["relevant_evidence_ids"] = []
    elif mutation == "changed_tool_result":
        next(t for t in selection["tool_exchanges"] if t["tool_name"] == "search_librarian")["result"]["evidence"] = []
    elif mutation == "missing_transcript":
        observed["agent_exchanges"] = []
    elif mutation == "missing_selection":
        observed["agent_exchanges"].remove(selection)
    elif mutation == "different_selection":
        selection["output"] = selection["output"] | {"evidence_ids": [EXTRA]}
    elif mutation == "missing_review":
        observed["agent_exchanges"] = [e for e in observed["agent_exchanges"] if e["role"] != "Provenance"]
    elif mutation in {"missing_first_review", "missing_draft"}:
        role, stage = ("Muse", "draft") if mutation == "missing_draft" else ("Provenance", "review")
        removed = next(e for e in observed["agent_exchanges"] if (e["role"], e["stage"]) == (role, stage))
        observed["agent_exchanges"].remove(removed)
        for index, exchange in enumerate(observed["agent_exchanges"], 1):
            exchange["sequence"] = index
    elif mutation == "unbound_review":
        payload = json.loads(review["input_prompt"])
        payload["candidate"]["response"] = "A different response."
        review["input_prompt"] = json.dumps(payload)
    elif mutation == "wrong_line":
        observed["line_id"] = "different-line"
    elif mutation in {"widened_scope", "missing_scope"}:
        task = json.loads(selection["input_prompt"])
        if mutation == "widened_scope":
            task["scope"]["book_scopes"][0]["chapter_max"] = 6
        else:
            task["scope"]["book_scopes"] = []
        selection["input_prompt"] = json.dumps(task)
    elif mutation == "release_ids":
        observed["released_evidence_ids"].append(EXTRA)
    elif mutation == "review_not_passed":
        observed["events"][-1]["provenance_verdicts"] = ["reject"]
    elif mutation == "failed_book_tool":
        next(t for t in selection["tool_exchanges"] if t["tool_name"] == "search_librarian")["outcome"] = "failed"
    elif mutation == "failed_exchange":
        selection["status"] = "failed"
    elif mutation == "missing_release":
        observed["events"].pop()
    elif mutation in {"empty_extra", "mixed_unknown", "foreign_memory", "later_chapter"}:
        discovery = next(e for e in observed["events"] if e["kind"] == "discovery")
        decision = json.loads(discovery["decision_json"])
        if mutation == "empty_extra":
            decision["evidence_ids"].remove(EXTRA)
        elif mutation == "mixed_unknown":
            decision["evidence_ids"].append("unknown")
        else:
            replacement = ("another-account-memory" if mutation == "foreign_memory"
                           else "pg11-v01b38ea4-ch06-ln1268-1307")
            decision["evidence_ids"] = [replacement if i == EXTRA else i for i in decision["evidence_ids"]]
        discovery["decision_json"] = json.dumps(decision)
        selection["output"] = decision
    assert proof(evidence) is False
    with pytest.raises(ValueError):
        candidate_summary(evidence, tmp_path)



@pytest.mark.parametrize("failure", ["private_query_disclosure", "missing_release_observation"])
def test_verified_extra_book_does_not_waive_an_independent_blocker(evidence, tmp_path, failure):
    evidence[1]["grades"][0]["failures"].append(failure)
    summary = candidate_summary(evidence, tmp_path)
    assert proof(evidence) is True
    assert failure in [item["detail"] for item in summary["blocking_failures"]]
    assert publication_decision(
        judgments_passed=99, judgments_total=100, complete=True,
        blocked=bool(summary["blocking_failures"]), auto_publish_enabled=True,
    )["route"] == "blocked"
