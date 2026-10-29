"""Public book scope mistakes keep their failed grades without a security claim."""

from copy import deepcopy
import hashlib
import json

import pytest

from tests.test_release_connection_evidence import EXTRA, add_citation, candidate_summary, evidence
from tests.test_release_reading_evidence import ROOT, SCENARIO, add_later_citation, evidence as book_evidence


def use_raw_scope_labels(evidence, cited):
    if cited:
        add_citation(evidence)
    grade = evidence[1]["grades"][0]
    grade["failures"] = [
        code.replace("authorized_book_selection_mismatch", "unpermitted_selected_evidence")
        .replace("authorized_book_citation_mismatch", "unpermitted_citation")
        for code in grade["failures"]
    ]
    evidence[0]["scenes"][2]["grades"][0]["failures"] = ["unnecessary_declined_exploration"]


@pytest.mark.parametrize("cited", [False, True])
def test_verified_public_book_scope_failures_keep_raw_grades_and_score(evidence, tmp_path, cited):
    use_raw_scope_labels(evidence, cited)
    original = deepcopy(evidence)

    summary = candidate_summary(evidence, tmp_path)

    assert evidence == original
    assert (summary["judgments_passed"], summary["judgments_total"]) == (2, 4)
    assert summary["judgments_failed"] == 2
    assert summary["blocking_failures"] == []
    failures = [item for item in summary["behavioral_failures"] if item["detail"] == "book_reading_scope_mismatch"]
    assert {item["raw_detail"] for item in failures} == (
        {"unpermitted_selected_evidence", "unpermitted_citation"} if cited else {"unpermitted_selected_evidence"}
    )


def test_changed_book_evidence_is_not_hidden_by_scope_classification(evidence, tmp_path):
    use_raw_scope_labels(evidence, cited=False)
    for event in evidence[1]["events"]:
        event["evidence_json"] = [
            json.dumps(json.loads(raw) | {"excerpt": "Changed source content."})
            if json.loads(raw)["evidence_id"] == EXTRA else raw
            for raw in event["evidence_json"]
        ]

    summary = candidate_summary(evidence, tmp_path)

    assert any(item["detail"] == "unpermitted_selected_evidence" for item in summary["blocking_failures"])


@pytest.fixture
def book_release(book_evidence, tmp_path):
    saved = json.loads((ROOT / "results" / SCENARIO / "result.json").read_text())["evidence"]
    artifact = saved["evaluation"]["data"]
    artifact["scenes"][0] = book_evidence[0]
    hashes = {}
    for filename in ("backstory.json", "ground-truth.json"):
        raw = json.dumps(saved["inputs"][filename]["data"]).encode()
        (tmp_path / filename).write_bytes(raw)
        hashes[filename] = hashlib.sha256(raw).hexdigest()
    (tmp_path / "ground-truth-adoption.json").write_text(json.dumps({
        "adopted_ground_truth_identity": artifact["dataset_version"],
    }))
    return artifact, tmp_path, {
        "runner": "evals.synthetic_journals.book_replay", "objective_ids": artifact["objective_ids"], "hashes": hashes,
    }


def test_book_citation_scope_mismatch_keeps_its_failed_grade(book_release):
    from evals.release.gate import validate_artifact
    from evals.synthetic_journals.scenario_diagnostics import summarize_artifact

    artifact, _, _ = book_release
    add_later_citation(artifact["scenes"][0])
    original = deepcopy(artifact)
    counts = summarize_artifact(artifact)
    summary = validate_artifact(*book_release)
    assert artifact == original
    assert summary["judgments_failed"] == counts["judgments_failed"]
    assert summary["judgments_total"] == counts["judgments_total"]
    assert summary["blocking_failures"] == []
    assert any(item["detail"] == "book_reading_scope_mismatch"
               and item["raw_detail"] == "response_cited_unpermitted_evidence"
               for item in summary["behavioral_failures"])


def test_book_scope_quality_cannot_hide_a_failed_judgment(book_release):
    from evals.release.gate import validate_artifact

    observed = book_release[0]["scenes"][0]
    add_later_citation(observed)
    observed["grades"][0]["hard_pass"] = True
    with pytest.raises(ValueError, match="book source observations"):
        validate_artifact(*book_release)


@pytest.mark.parametrize("corrupt", [False, True])
def test_completed_book_failure_still_requires_valid_source_observations(book_release, corrupt):
    from evals.release.gate import validate_artifact

    observed = book_release[0]["scenes"][0]
    failed = deepcopy(next(item for item in observed["agent_exchanges"] if item["role"] == "Muse" and item["stage"] == "draft"))
    failed.update(sequence=1, status="failure", output=None, failure_code="muse_model_failed", failure_category="unknown_error")
    observed["agent_exchanges"] = [failed]
    observed.update(reply="The agent could not finish.", released_evidence_ids=[],
                    release_source="application_safe_decline", provenance_verdicts=[],
                    ground_truth_result="fails_hard_gates")
    observed["grades"][0].update(hard_pass=False, failures=["evidence_exceeded_safe_scope"])
    if corrupt:
        observed["grounding_calls"][0]["evidence"][0]["text"] = "Forged source evidence."
        with pytest.raises(ValueError, match="book source observations"):
            validate_artifact(*book_release)
    else:
        summary = validate_artifact(*book_release)
        assert summary["blocking_failures"] == []
        assert any(item["detail"] == "evidence_exceeded_safe_scope" for item in summary["behavioral_failures"])
