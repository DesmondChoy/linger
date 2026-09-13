"""Outcome and history evidence tests for scenario failure reports."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from evals.synthetic_journals.scenario_diagnostics import (
    summarize_artifact,
    collect_diagnostic_evidence,
)


@pytest.mark.parametrize(
    ("scene", "judgments", "failures"),
    [
        (
            {"scene_id": "capture", "ground_truth_result": "fails_hard_gates", "hard_failures": ["stored_text_mismatch"]},
            1, ["stored_text_mismatch"],
        ),
        (
            {"scene_id": "curation", "ground_truth_result": "fails_hard_gates", "grade": {"hard_pass": False, "failures": ["action_mismatch"]}},
            1, ["action_mismatch"],
        ),
        (
            {"scene_id": "book", "ground_truth_result": "fails_hard_gates", "grades": [
                {"proposal_id": "grounding", "hard_pass": True, "failures": []},
                {"proposal_id": "spoilers", "hard_pass": False, "failures": ["spoiler_leak"]},
            ]},
            2, ["spoiler_leak"],
        ),
        (
            {"scene_id": "connection", "hard_gate_pass": False, "grades": [
                {"proposal_id": "connection", "failures": ["provider_failure"]},
            ]},
            1, ["provider_failure"],
        ),
        (
            {"scene_id": "surfacing", "ground_truth_result": "fails_hard_gates", "grade": {"hard_failures": ["invalid_response"]}, "execution_error": {"code": "surfacing_model_failed"}},
            1, ["invalid_response", "surfacing_model_failed"],
        ),
        (
            {"scene_id": "reflection", "ground_truth_result": "fails_hard_gates", "gate_failures": ["wrong_release"], "turns": [{"failure_type": "model", "failure_stage": "muse_draft"}]},
            1, ["wrong_release", "provider failure at muse_draft"],
        ),
    ],
)
def test_runner_failures_never_become_a_passing_summary(scene, judgments, failures):
    result = summarize_artifact({"scenes": [scene]})
    assert result["scenes_failed"] == 1
    assert result["scenes_passed"] == 0
    assert result["judgments_total"] == judgments
    assert result["judgments_failed"] == 1
    assert {item["detail"] for item in result["failures"]} >= set(failures)
    if scene["scene_id"] == "book":
        assert result["judgments_passed"] == 1
        assert {"scene_id": "book", "proposal_id": "spoilers", "detail": "spoiler_leak"} in result["failures"]


def test_continuity_control_does_not_inflate_adopted_judgment_count():
    result = summarize_artifact({"scenes": [
        {"scene_id": "control", "ground_truth_result": "not_applicable", "structural_findings": []},
        {"scene_id": "comparison", "ground_truth_result": "passes_hard_gates", "structural_findings": []},
        {"scene_id": "broken-control", "ground_truth_result": "not_applicable", "structural_findings": ["cross_session_history"]},
    ]})
    assert result["scenes_total"] == 3
    assert result["scenes_ungraded"] == result["scenes_failed"] == result["scenes_passed"] == 1
    assert result["judgments_total"] == result["judgments_passed"] == 1
    assert result["judgments_failed"] == 0
    assert result["failures"] == [{"scene_id": "broken-control", "detail": "cross_session_history"}]


def test_book_failure_retains_failed_agent_exchange_as_execution_evidence():
    result = summarize_artifact({"scenes": [{
        "scene_id": "book", "grades": [{"proposal_id": "quote", "hard_pass": False, "failures": ["missing_retrieval"]}],
        "agent_exchanges": [{"role": "Muse", "stage": "draft", "status": "failed", "failure_code": "muse_failed"}],
    }]})
    assert result["scenes_failed"] == 1
    assert result["execution_failures"] == [{"scene_id": "book", "detail": "Muse draft: muse_failed"}]


def test_continuity_invariants_fail_the_scene_without_relabeling_ground_truth():
    result = summarize_artifact({"scenes": [{
        "scene_id": "comparison", "ground_truth_result": "passes_hard_gates",
        "structural_findings": ["incorrect_session_message_count"],
    }]})
    assert result["scenes_failed"] == 1
    assert result["judgments_passed"] == 1
    assert result["judgments_failed"] == 0
    assert result["failures"] == [{"scene_id": "comparison", "detail": "incorrect_session_message_count"}]


@pytest.mark.parametrize("artifact", [
    {}, {"scenes": []}, {"scenes": [{"scene_id": "unknown"}]},
    {"scenes": [{"scene_id": "missing-grade", "grades": []}]},
])
def test_incomplete_artifact_cannot_pass(artifact):
    with pytest.raises(ValueError):
        summarize_artifact(artifact)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _scenario(root: Path) -> Path:
    scenario = root / "synthetic-journal-evaluation" / "scenarios" / "example"
    scenario.mkdir(parents=True)
    backstory = json.dumps({"objective_ids": ["grounded_book_reflection"]})
    ground_truth = json.dumps({"proposals": [{
        "proposal_id": "p1", "scene_id": "s1", "objective_id": "grounded_book_reflection",
        "expected_outcomes": ["Use the adopted passage."],
        "prohibited_outcomes": ["Reveal the later chapter."],
        "book_expectation": {"kind": "grounded_book_reflection", "required_evidence_ids": ["e1"]},
    }]})
    (scenario / "backstory.json").write_text(backstory)
    (scenario / "ground-truth.json").write_text(ground_truth)
    (scenario / "ground-truth-adoption.json").write_text(json.dumps({
        "backstory_sha256": hashlib.sha256(backstory.encode()).hexdigest(),
        "proposed_ground_truth_sha256": hashlib.sha256(ground_truth.encode()).hexdigest(),
        "reviewed_at": "2026-09-01T12:00:00+08:00",
        "reviewer": {"reviewer_id": "private-reviewer-name"},
    }))
    return scenario


def test_evidence_records_verified_baseline_and_scoped_changes(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    scenario = _scenario(tmp_path)
    _git(tmp_path, "add", "synthetic-journal-evaluation")
    _git(tmp_path, "commit", "-qm", "Adopt the example scenario")
    scenario_revision = _git(tmp_path, "rev-parse", "HEAD")
    runtime = tmp_path / "src" / "linger" / "agents" / "muse.py"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("changed_contract = True\n")
    _git(tmp_path, "add", "src")
    _git(tmp_path, "commit", "-qm", "Change grounded response contract")
    current_revision = _git(tmp_path, "rev-parse", "HEAD")
    runtime.write_text("changed_contract = False\n")
    evidence = collect_diagnostic_evidence(scenario, tmp_path)
    assert evidence["git"]["scenario_commit"] == scenario_revision
    assert evidence["git"]["revision"] == current_revision
    assert evidence["git"]["current_scenario_matches_commit"] is True
    assert "Change grounded response contract" in evidence["git"]["recent_commits"]
    assert "M src/linger/agents/muse.py" in evidence["git"]["scoped_working_tree_changes"]
    assert evidence["adoption_hash_matches"]["ground-truth.json"]["matches"] is True
    assert evidence["declared_adoption_time"] == "2026-09-01T12:00:00+08:00"
    assert "private-reviewer-name" not in json.dumps(evidence)


def test_dirty_scenario_is_not_described_as_a_committed_generation(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    scenario = _scenario(tmp_path)
    _git(tmp_path, "add", "synthetic-journal-evaluation")
    _git(tmp_path, "commit", "-qm", "Scenario baseline")
    with (scenario / "ground-truth.json").open("a") as stream:
        stream.write("\n")
    evidence = collect_diagnostic_evidence(scenario, tmp_path)
    assert evidence["adoption_hash_matches"]["ground-truth.json"]["matches"] is False
    assert evidence["git"]["current_scenario_matches_commit"] is False


def test_untracked_scenario_does_not_invent_generation_revision(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    (tmp_path / "README.md").write_text("Example\n")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-qm", "Repository baseline")
    scenario = _scenario(tmp_path)
    evidence = collect_diagnostic_evidence(scenario, tmp_path)
    assert evidence["git"]["scenario_commit"] is None
    assert "no scenario commit" in evidence["git"]["history_window"]


def test_log_evidence_is_bounded_redacted_and_works_without_git(tmp_path):
    scenario = _scenario(tmp_path)
    run_log = scenario / "run.log"
    run_log.write_text(
        "EARLY_NOISE\n" * 2000
        + "Verbose traceback data\n" * 20
        + "OPENAI_API_KEY=sk-private1234567890abcdefghijklmnopqrstuvwxyz\n"
        + "Authorization: Bearer privatebearer456\n"
        + "ProviderError: model was unavailable\n"
    )
    evidence = collect_diagnostic_evidence(scenario, tmp_path, run_log)
    tail = evidence["run_log_tail"]
    assert "ProviderError: model was unavailable" in tail
    assert "[REDACTED]" in tail
    assert "sk-private" not in tail and "privatebearer456" not in tail
    assert tail.count("EARLY_NOISE") < 10
    assert len(tail) <= 3530
    assert evidence["git"]["available"] is False
