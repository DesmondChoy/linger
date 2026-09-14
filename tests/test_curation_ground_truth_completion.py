"""Evaluator policy completion preserves generated labels and adopted files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.synthetic_journals.complete_curation_ground_truth import (
    complete_curation_ground_truth,
    main,
)
from evals.synthetic_journals.validate_scenario import validate_scenario_files
from src.linger.agents.sculptor.models import DerivedSummary
from tests.test_synthetic_curation_replay import _curation_documents, _json_bytes


def _authoring_documents() -> tuple[bytes, dict]:
    _, ground_truth, backstory_bytes = _curation_documents()
    for proposal in ground_truth["proposals"]:
        action = proposal["curation"]["expected"].get("action", {})
        action.pop("max_summary_words", None)
        action.pop("semantic_review", None)
    return backstory_bytes, ground_truth


def _write_documents(tmp_path: Path, ground_truth: dict, backstory: bytes) -> tuple[Path, Path]:
    backstory_path = tmp_path / "backstory.json"
    ground_truth_path = tmp_path / "ground-truth.json"
    backstory_path.write_bytes(backstory)
    ground_truth_path.write_bytes(_json_bytes(ground_truth))
    return backstory_path, ground_truth_path


def test_completes_repository_policy_without_changing_candidate_labels(tmp_path: Path) -> None:
    backstory_bytes, authored = _authoring_documents()
    authored_bytes = _json_bytes(authored)

    completed_bytes = complete_curation_ground_truth(
        backstory_bytes, authored_bytes, run_configurations={}
    )
    completed = json.loads(completed_bytes)
    summary = completed["proposals"][2]["curation"]["expected"]["action"]
    assert summary.pop("max_summary_words") == 100
    summary_review = summary.pop("semantic_review")
    assert summary_review["criteria"]
    assert summary_review["forbidden_claims"]
    topic = completed["proposals"][3]["curation"]["expected"]["action"]
    topic_review = topic.pop("semantic_review")
    assert topic_review["criteria"]
    assert topic_review["forbidden_claims"]
    assert completed == authored
    assert _json_bytes(authored) == authored_bytes

    backstory_path, ground_truth_path = _write_documents(tmp_path, authored, backstory_bytes)
    assert main([str(backstory_path), str(ground_truth_path)]) == 0
    assert backstory_path.read_bytes() == backstory_bytes
    assert ground_truth_path.read_bytes() == completed_bytes
    validate_scenario_files(backstory_path, ground_truth_path)
    assert {path.name for path in tmp_path.iterdir()} == {"backstory.json", "ground-truth.json"}


def test_policy_word_limit_matches_the_production_boundary() -> None:
    backstory_bytes, authored = _authoring_documents()
    completed = json.loads(complete_curation_ground_truth(
        backstory_bytes, _json_bytes(authored), run_configurations={}
    ))
    limit = completed["proposals"][2]["curation"]["expected"]["action"]["max_summary_words"]
    DerivedSummary(action="update_derived_summary", source_memory_ids=("a", "b"), summary=" ".join(["x"] * limit))
    with pytest.raises(ValidationError, match="at most 100 words"):
        DerivedSummary(action="update_derived_summary", source_memory_ids=("a", "b"), summary=" ".join(["x"] * (limit + 1)))


@pytest.mark.parametrize("proposal_index", [0, 2, 3])
@pytest.mark.parametrize("field,value", [("max_summary_words", 100), ("semantic_review", None)])
def test_rejects_supplied_policy_even_when_it_matches_or_is_null(
    tmp_path: Path, proposal_index: int, field: str, value: object
) -> None:
    backstory_bytes, authored = _authoring_documents()
    authored["proposals"][proposal_index]["curation"]["expected"]["action"][field] = value
    backstory_path, ground_truth_path = _write_documents(tmp_path, authored, backstory_bytes)
    original = ground_truth_path.read_bytes()

    with pytest.raises(ValueError, match="evaluator-owned"):
        complete_curation_ground_truth(backstory_bytes, original, run_configurations={})
    assert main([str(backstory_path), str(ground_truth_path)]) == 1
    assert ground_truth_path.read_bytes() == original


def test_repeated_completion_refuses_without_changing_bytes(tmp_path: Path) -> None:
    backstory_bytes, authored = _authoring_documents()
    backstory_path, ground_truth_path = _write_documents(tmp_path, authored, backstory_bytes)
    assert main([str(backstory_path), str(ground_truth_path)]) == 0
    completed = ground_truth_path.read_bytes()
    assert main([str(backstory_path), str(ground_truth_path)]) == 1
    assert ground_truth_path.read_bytes() == completed


def test_refuses_existing_adoption_without_changing_either_file(tmp_path: Path) -> None:
    backstory_bytes, authored = _authoring_documents()
    backstory_path, ground_truth_path = _write_documents(tmp_path, authored, backstory_bytes)
    adoption_path = tmp_path / "ground-truth-adoption.json"
    adoption_path.write_bytes(b"existing adoption, even if malformed")
    originals = {path: path.read_bytes() for path in tmp_path.iterdir()}

    assert main([str(backstory_path), str(ground_truth_path)]) == 1
    assert {path: path.read_bytes() for path in tmp_path.iterdir()} == originals


def test_failed_atomic_replacement_preserves_files_and_removes_temporary_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backstory_bytes, authored = _authoring_documents()
    backstory_path, ground_truth_path = _write_documents(tmp_path, authored, backstory_bytes)
    originals = {path: path.read_bytes() for path in tmp_path.iterdir()}

    def fail_replace(source: Path, target: Path) -> None:
        assert target == ground_truth_path
        assert source.parent == ground_truth_path.parent
        raise OSError("replacement unavailable")

    monkeypatch.setattr(
        "evals.synthetic_journals.complete_curation_ground_truth.os.replace", fail_replace
    )
    assert main([str(backstory_path), str(ground_truth_path)]) == 1
    assert {path: path.read_bytes() for path in tmp_path.iterdir()} == originals


@pytest.mark.parametrize("failure", ["hash", "span", "unknown_field", "source_id", "missing_label"])
def test_validation_failure_preserves_original_bytes(tmp_path: Path, failure: str) -> None:
    backstory_bytes, authored = _authoring_documents()
    if failure == "hash":
        authored["backstory_sha256"] = "0" * 64
    elif failure == "span":
        authored["proposals"][0]["exact_spans"][0]["text"] = "unsupported text"
    elif failure == "unknown_field":
        authored["proposals"][2]["curation"]["expected"]["action"]["foreign"] = True
    elif failure == "source_id":
        authored["proposals"][2]["curation"]["expected"]["action"]["source_memory_ids"][0] = "unknown"
    else:
        authored["proposals"][2].pop("expected_outcomes")
    backstory_path, ground_truth_path = _write_documents(tmp_path, authored, backstory_bytes)
    originals = {path: path.read_bytes() for path in tmp_path.iterdir()}

    assert main([str(backstory_path), str(ground_truth_path)]) == 1
    assert {path: path.read_bytes() for path in tmp_path.iterdir()} == originals


def test_rejects_scenario_without_the_curation_objective() -> None:
    backstory_bytes, authored = _authoring_documents()
    backstory = json.loads(backstory_bytes)
    backstory["objective_ids"] = ["unrelated"]
    for scene in backstory["scenes"]:
        scene["objective_ids"] = ["unrelated"]
    with pytest.raises(ValueError, match="bounded_memory_curation"):
        complete_curation_ground_truth(_json_bytes(backstory), _json_bytes(authored), run_configurations={})


def test_rejects_duplicate_json_keys_without_hiding_the_supplied_value() -> None:
    backstory_bytes, authored = _authoring_documents()
    duplicated = _json_bytes(authored).replace(
        b'"ground_truth_status": "proposed"',
        b'"ground_truth_status": "adopted", "ground_truth_status": "proposed"',
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        complete_curation_ground_truth(backstory_bytes, duplicated, run_configurations={})
