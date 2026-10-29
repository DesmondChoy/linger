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
LATER = "pg11-v01b38ea4-ch06-ln1259-1267"
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


def add_citation(evidence, identity=EXTRA):
    _, observed, _, _, _ = evidence
    canonical = Librarian().fetch_by_id(identity)
    sentence = "Alice tells the Pigeon that she is a little girl."
    candidate = next(item for item in reversed(observed["agent_exchanges"])
                     if item["role"] == "Muse" and item["stage"] in {"draft", "revision"})
    candidate["output"]["reply"] += " " + sentence
    candidate["output"]["evidence_uses"].append({
        "source_kind": "book_corpus", "evidence_id": identity, "source_location": canonical.location,
        "supported_claims": [sentence], "limit_claims": [], "exact_quote": None,
    })
    observed["reply"] = candidate["output"]["reply"]
    observed["released_evidence_ids"].append(identity)
    observed["events"][-1]["released_evidence_ids"].append(identity)
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


def replace_extra_record(evidence, identity):
    observed = evidence[1]
    old = book_record()
    record = book_record(identity)
    for event in observed["events"]:
        event["evidence_json"] = [json.dumps(record) if json.loads(raw)["evidence_id"] == EXTRA else raw
                                  for raw in event["evidence_json"]]
        if event["kind"] == "discovery":
            decision = json.loads(event["decision_json"])
            decision["evidence_ids"] = [identity if item == EXTRA else item for item in decision["evidence_ids"]]
            event["decision_json"] = json.dumps(decision)
    selection = next(item for item in observed["agent_exchanges"] if item["role"] == "Serendipity")
    selection["output"]["evidence_ids"] = [identity if item == EXTRA else item
                                          for item in selection["output"]["evidence_ids"]]
    result = next(tool["result"] for tool in selection["tool_exchanges"] if tool["tool_name"] == "search_librarian")
    result["evidence"] = [record if item["evidence_id"] == EXTRA else item for item in result["evidence"]]
    result["judgement"]["relevant_evidence_ids"] = [identity if item == EXTRA else item
                                                   for item in result["judgement"]["relevant_evidence_ids"]]
    assessment = next(item for item in observed["agent_exchanges"]
                      if item["role"] == "Librarian" and item["stage"] == "evidence_strength")
    payload = json.loads(assessment["input_prompt"])
    canonical = Librarian().fetch_by_id(identity).model_dump(mode="json")
    for index, supplied in enumerate(payload["evidence"]):
        if supplied["text"] == old["excerpt"] and supplied["source_lines"] == old["source_lines"]:
            payload["evidence"][index] = canonical | {"evidence_id": supplied["evidence_id"]}
    assessment["input_prompt"] = json.dumps(payload)


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


@pytest.mark.parametrize("scope", ["widened", "narrowed", "different_work"])
def test_reading_progress_scope_does_not_block_canonical_book_proof(evidence, tmp_path, scope):
    selection = next(item for item in evidence[1]["agent_exchanges"] if item["role"] == "Serendipity")
    task = json.loads(selection["input_prompt"])
    if scope == "different_work":
        task["scope"]["book_scopes"][0].update(work_id="pg23", book_version_id="pg23-vd3f08ac3")
    else:
        task["scope"]["book_scopes"][0]["chapter_max"] = 6 if scope == "widened" else 2
    selection["input_prompt"] = json.dumps(task)

    assert proof(evidence) is True
    assert not candidate_summary(evidence, tmp_path)["blocking_failures"]


@pytest.mark.parametrize("cited", [False, True])
@pytest.mark.parametrize("identity", [EXTRA, LATER])
def test_raw_book_scope_labels_require_canonical_proof_without_chapter_limits(evidence, tmp_path, cited, identity):
    if identity != EXTRA:
        replace_extra_record(evidence, identity)
    if cited:
        add_citation(evidence, identity)
    failures = evidence[1]["grades"][0]["failures"]
    failures[:] = ["unpermitted_citation" if code == "authorized_book_citation_mismatch"
                   else "unpermitted_selected_evidence" for code in failures]
    original = deepcopy(evidence)

    assert proof(evidence) is True
    summary = candidate_summary(evidence, tmp_path)
    assert evidence == original
    assert not summary["blocking_failures"]
    assert summary["judgments_total"] == 4
    assert summary["judgments_passed"] == 2
    assert summary["judgments_failed"] == 2
    normalized = [item for item in summary["behavioral_failures"] if item["detail"] == "book_reading_scope_mismatch"]
    assert {item["raw_detail"] for item in normalized} == set(failures)


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
    "unbound_review", "wrong_line", "malformed_source_grant", "missing_book_operation", "release_ids",
    "review_not_passed", "failed_book_tool", "failed_exchange", "missing_release",
    "empty_extra", "mixed_unknown", "foreign_memory", "unobserved_later_chapter",
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
    elif mutation in {"malformed_source_grant", "missing_book_operation"}:
        task = json.loads(selection["input_prompt"])
        task["scope"]["book_scopes"] = []
        if mutation == "missing_book_operation":
            task["scope"]["allowed_sources"].remove("book_corpus")
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
    elif mutation in {"empty_extra", "mixed_unknown", "foreign_memory", "unobserved_later_chapter"}:
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


@pytest.mark.parametrize("mutation", ["memory", "web", "unknown", "forged_canonical"])
def test_raw_mixed_labels_cannot_demote_nonbook_or_unverified_sources(evidence, tmp_path, mutation):
    observed = evidence[1]
    observed["grades"][0]["failures"] = ["unpermitted_selected_evidence"]
    selection = next(item for item in observed["agent_exchanges"] if item["role"] == "Serendipity")
    if mutation == "unknown":
        selection["output"]["evidence_ids"] = ["unknown-source" if item == EXTRA else item
                                               for item in selection["output"]["evidence_ids"]]
        discovery = next(event for event in observed["events"] if event["kind"] == "discovery")
        discovery["decision_json"] = json.dumps(selection["output"])
    else:
        for event in observed["events"]:
            records = []
            for raw in event["evidence_json"]:
                record = json.loads(raw)
                if record["evidence_id"] == EXTRA:
                    if mutation == "forged_canonical":
                        record["excerpt"] = "A fabricated passage."
                    else:
                        record.update(source_kind=mutation, trust_level="account_scoped" if mutation == "memory" else "external")
                records.append(json.dumps(record))
            event["evidence_json"] = records
        if mutation == "forged_canonical":
            result = next(tool["result"] for tool in selection["tool_exchanges"] if tool["tool_name"] == "search_librarian")
            for record in result["evidence"]:
                if record["evidence_id"] == EXTRA:
                    record["excerpt"] = "A fabricated passage."
            assessment = next(item for item in observed["agent_exchanges"]
                              if item["role"] == "Librarian" and item["stage"] == "evidence_strength")
            payload = json.loads(assessment["input_prompt"])
            for record in payload["evidence"]:
                if record["text"] == book_record()["excerpt"]:
                    record["text"] = "A fabricated passage."
            assessment["input_prompt"] = json.dumps(payload)

    assert proof(evidence) is False
    summary = candidate_summary(evidence, tmp_path)
    assert any(item["detail"] == "unpermitted_selected_evidence" and item["category"] == "security"
               for item in summary["blocking_failures"])


def test_malformed_chapter_metadata_cannot_be_coerced_into_canonical_book_proof(evidence, tmp_path):
    identity = "pg11-v01b38ea4-ch01-ln0231-0256"
    replace_extra_record(evidence, identity)
    observed = evidence[1]
    observed["grades"][0]["failures"] = ["unpermitted_selected_evidence"]
    for event in observed["events"]:
        records = []
        for raw in event["evidence_json"]:
            record = json.loads(raw)
            if record["evidence_id"] == identity:
                record["chapter"] = True
            records.append(json.dumps(record))
        event["evidence_json"] = records
    selection = next(item for item in observed["agent_exchanges"] if item["role"] == "Serendipity")
    result = next(tool["result"] for tool in selection["tool_exchanges"] if tool["tool_name"] == "search_librarian")
    for record in result["evidence"]:
        if record["evidence_id"] == identity:
            record["chapter"] = True

    assert proof(evidence) is False
    summary = candidate_summary(evidence, tmp_path)
    assert any(item["detail"] == "unpermitted_selected_evidence" for item in summary["blocking_failures"])


def decline_after_selection(evidence):
    from src.linger.contracts.turn import SAFE_DECLINE

    observed = evidence[1]
    observed["grades"][0]["failures"] = ["unpermitted_selected_evidence"]
    observed.update(release_source="application_safe_decline", released_evidence_ids=[], reply=SAFE_DECLINE)
    observed["agent_exchanges"] = [item for item in observed["agent_exchanges"]
                                   if not (item["role"] == "Provenance" and item["stage"] == "review")]
    for sequence, exchange in enumerate(observed["agent_exchanges"], 1):
        exchange["sequence"] = sequence
        if exchange["role"] == "Muse" and exchange["stage"] in {"draft", "revision"}:
            exchange.update(status="failure", output=None, failure_code="muse_model_failed",
                            failure_category="unknown_error", usage=None)
    observed["events"][-1].update(
        status="declined", release_source="application_safe_decline", released_evidence_ids=[],
        provenance_verdicts=[], failure_code="muse_model_failed", failure_stage="muse_draft",
    )


@pytest.mark.parametrize("identity", [EXTRA, LATER])
def test_completed_muse_failure_does_not_turn_canonical_selection_into_security(evidence, tmp_path, identity):
    if identity != EXTRA:
        replace_extra_record(evidence, identity)
    decline_after_selection(evidence)
    original = deepcopy(evidence)

    assert proof(evidence) is True
    summary = candidate_summary(evidence, tmp_path)

    assert evidence == original
    assert not summary["blocking_failures"]
    assert summary["judgments_passed"] == 2
    assert summary["judgments_total"] == 4
    assert summary["judgments_failed"] == 2
    assert any(item["detail"] == "book_reading_scope_mismatch"
               and item["raw_detail"] == "unpermitted_selected_evidence"
               for item in summary["behavioral_failures"])
    assert any("muse_model_failed" in item["detail"] for item in summary["execution_failures"])


@pytest.mark.parametrize("mutation", [
    "missing_muse", "pending_muse", "incomplete_muse", "missing_failure_detail", "missing_source_tool",
    "missing_book_search", "memory_source", "web_source", "unknown_selection", "citation_on_decline",
])
def test_decline_does_not_replace_complete_execution_and_canonical_source_proof(evidence, tmp_path, mutation):
    decline_after_selection(evidence)
    observed = evidence[1]
    muse = next(item for item in observed["agent_exchanges"] if item["role"] == "Muse" and item["stage"] == "draft")
    selection = next(item for item in observed["agent_exchanges"] if item["role"] == "Serendipity")
    if mutation == "missing_muse":
        observed["agent_exchanges"] = [item for item in observed["agent_exchanges"] if item["role"] != "Muse"]
        for sequence, item in enumerate(observed["agent_exchanges"], 1):
            item["sequence"] = sequence
    elif mutation == "pending_muse":
        muse.update(status="pending", failure_code=None, failure_category=None)
    elif mutation == "incomplete_muse":
        muse.update(status="failed", failure_code="incomplete_agent_exchange")
    elif mutation == "missing_failure_detail":
        muse.update(failure_code=None, failure_category=None)
    elif mutation == "missing_source_tool":
        selection["tool_exchanges"] = [tool for tool in selection["tool_exchanges"] if tool["tool_name"] != "search_librarian"]
    elif mutation == "missing_book_search":
        observed["events"] = [event for event in observed["events"] if not (
            event["kind"] == "search" and event["source"] == "book_corpus"
        )]
    elif mutation == "citation_on_decline":
        observed["grades"][0]["failures"] = ["unpermitted_citation"]
    elif mutation in {"memory_source", "web_source"}:
        for event in observed["events"]:
            records = []
            for raw in event["evidence_json"]:
                record = json.loads(raw)
                if record["evidence_id"] == EXTRA:
                    record["source_kind"] = mutation.removesuffix("_source")
                records.append(json.dumps(record))
            event["evidence_json"] = records
    else:
        selection["output"]["evidence_ids"] = ["unknown" if item == EXTRA else item
                                               for item in selection["output"]["evidence_ids"]]
        discovery = next(event for event in observed["events"] if event["kind"] == "discovery")
        discovery["decision_json"] = json.dumps(selection["output"])

    assert proof(evidence) is False
    if mutation in {"pending_muse", "incomplete_muse", "missing_failure_detail"}:
        with pytest.raises(ValueError):
            candidate_summary(evidence, tmp_path)
    else:
        assert candidate_summary(evidence, tmp_path)["blocking_failures"]


@pytest.mark.parametrize("field", ["chapter_number", "source_lines"])
def test_cited_book_metadata_in_review_is_not_coerced_into_canonical_identity(evidence, tmp_path, field):
    add_citation(evidence)
    review = next(item for item in reversed(evidence[1]["agent_exchanges"])
                  if item["role"] == "Provenance" and item["stage"] == "review")
    payload = json.loads(review["input_prompt"])
    record = next(item for item in payload["canonical_book_evidence"] if item["evidence_id"] == EXTRA)
    if field == "chapter_number":
        record[field] = str(record[field])
    else:
        record[field] = [str(value) for value in record[field]]
    review["input_prompt"] = json.dumps(payload)

    assert proof(evidence) is False
    with pytest.raises(ValueError):
        candidate_summary(evidence, tmp_path)
