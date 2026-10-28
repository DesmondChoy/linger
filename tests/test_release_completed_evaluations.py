"""Completed task failures are scored; only security, crashes, and bad evidence block."""

from copy import deepcopy
import json

import pytest

from evals.release import gate
from evals.synthetic_journals import run_scenario, scenario_catalog
from tests.test_release_gate import _provider, SHA, IMAGE, MODEL
from tests.completed_evaluation_fixtures import book_evidence, continuity_evidence
from tests.test_release_workflow_checks import candidate


def run_candidate(evidence, tmp_path, monkeypatch, *, passing_judgments=1, mutation=None):
    repository = tmp_path / "repository"
    scenario = scenario_catalog.scenario_root(repository) / "test-completed-evaluation"
    scenario.mkdir(parents=True)
    backstory = deepcopy(evidence["backstory"])
    backstory["scenes"] = [deepcopy(evidence["planned"])]
    artifact = deepcopy(evidence["artifact"])
    artifact.update(ground_truth_status="adopted", dataset_version="a" * 64,
                    objective_ids=evidence["planned"]["objective_ids"], scenes=[deepcopy(evidence["scene"])])
    truth = deepcopy(evidence["truth"])
    for index in range(passing_judgments):
        identity = f"comparison-{index}"
        objective = "spoiler_boundary_clarification" if "book_replay" in evidence["runner"] else "session_scoped_conversation_continuity"
        planned = {"scene_id": identity, "line_ids": [evidence["planned"]["line_ids"][-1]],
                   "objective_ids": [objective], "prop_ids": []}
        backstory["scenes"].append(planned)
        if "book_replay" in evidence["runner"]:
            truth["proposals"].append({"proposal_id": identity, "scene_id": identity, "objective_id": objective})
            observation = {"grades": [{"proposal_id": identity, "objective_id": objective,
                                        "hard_pass": True, "failures": []}]}
        else:
            observation = {"role": "comparison", "structural_findings": []}
        artifact["scenes"].append(observation | {"scene_id": identity, "agent_exchanges": [], "ground_truth_result": "passes_hard_gates"})
    if mutation:
        mutation(artifact["scenes"][0])
    for name, value in (("backstory.json", backstory), ("ground-truth.json", truth),
                        ("ground-truth-adoption.json", {"adopted_ground_truth_identity": "a" * 64})):
        (scenario / name).write_text(json.dumps(value))
    entry = {"scenario": scenario.name, "runner": evidence["runner"], "objective_ids": artifact["objective_ids"],
             "scene_ids": [scene["scene_id"] for scene in artifact["scenes"]], "issues": [], "requires_web": False,
             "configuration": {"model": MODEL}, "hashes": scenario_catalog.scenario_hashes(scenario)}
    suite = repository / "suite.json"
    suite.write_text(json.dumps({"schema_version": 1, "name": "completed-evaluation-test", "scenarios": [scenario.name]}))
    monkeypatch.setattr(gate, "inspect_scenario", lambda *args: entry)
    monkeypatch.setattr(gate, "effective_configuration", lambda *args: {"roles": {"Muse": {"model": MODEL}}})
    monkeypatch.setattr(run_scenario, "preflight", lambda *args: entry)
    monkeypatch.setattr(run_scenario, "write_analysis_report", lambda *args, **kwargs: tmp_path / "analysis.md")
    _provider(monkeypatch, artifact)
    output = tmp_path / "behavioral"
    result = gate.run_suite(candidate_sha=SHA, image_id=IMAGE, model=MODEL, output=output,
                            repository_root=repository, suite_path=suite,
                            auto_publish_enabled=True, auto_publish_threshold=80)
    assert json.loads((output / "repeat-1/scenario-1/evaluation.json").read_text()) == artifact
    return result, output


@pytest.mark.parametrize("passed,route", [(4, "manual"), (5, "automatic")])
def test_completed_model_error_runs_through_gate_and_publication_evidence(book_evidence, tmp_path, monkeypatch, passed, route):
    result, output = run_candidate(book_evidence, tmp_path, monkeypatch, passing_judgments=passed)
    run = result["runs"][0]
    assert result["status"] == "review_required"
    assert result["publication"]["route"] == route
    assert run["problems"] == run["blocking_problems"] == []
    assert run["evaluation_findings"]
    assert len(run["results"]["execution_failures"]) == 1
    assert candidate.validate_publication_evidence(result) == (passed, passed + 1)
    candidate.validate_evaluation_artifacts(result, output)
    report = (output / "report.md").read_text()
    assert "Recorded agent error" in report and "not an evaluation process crash" in report


def test_continuity_refusal_stays_visible_without_inventing_judgments(continuity_evidence, tmp_path, monkeypatch):
    result, output = run_candidate(continuity_evidence, tmp_path, monkeypatch)
    assert result["status"] == "review_required"
    assert result["publication"]["route"] == "automatic"
    assert candidate.validate_publication_evidence(result) == (1, 1)
    assert result["totals"]["scenes_failed"] == 1
    assert result["runs"][0]["results"]["behavioral_failures"][0]["detail"] == "unreleased_turn:line-1"
    candidate.validate_evaluation_artifacts(result, output)


@pytest.mark.parametrize("failure", ["private_query_disclosure", "unexpected_memory_writes"])
def test_quality_failure_does_not_waive_an_independent_security_failure(book_evidence, tmp_path, monkeypatch, failure):
    result, _ = run_candidate(book_evidence, tmp_path, monkeypatch, passing_judgments=5,
                              mutation=lambda scene: scene["grades"][0]["failures"].append(failure))
    assert result["publication"]["route"] == "blocked"
    assert result["totals"]["judgments_passed"] == 5
    assert result["runs"][0]["results"]["blocking_failures"][0]["detail"] == failure


@pytest.mark.parametrize("category", ["provider_error", "unknown_error", "cancelled"])
def test_agent_failure_category_does_not_change_a_completed_evaluation_into_a_crash(book_evidence, tmp_path, monkeypatch, category):
    def change(scene):
        failed = scene["agent_exchanges"][4]
        failed["failure_category"] = category
        failed["provider_status_code"] = 401 if category == "provider_error" else None
    result, output = run_candidate(book_evidence, tmp_path, monkeypatch, passing_judgments=5, mutation=change)
    assert result["publication"]["route"] == "automatic"
    assert candidate.validate_publication_evidence(result) == (5, 6)
    candidate.validate_evaluation_artifacts(result, output)


@pytest.mark.parametrize("passed,route", [(4, "manual"), (5, "automatic")])
def test_malformed_book_id_is_a_failed_task_with_complete_evidence(book_evidence, tmp_path, monkeypatch, passed, route):
    def change(scene):
        scene["release_source"] = "application_safe_decline"
        scene["reply"] = "Something went wrong on my side just now — mind asking again?"
        scene["provenance_verdicts"] = []
        scene["agent_exchanges"] = scene["agent_exchanges"][:3]
        failed = scene["agent_exchanges"][2]
        failed.update(status="failure", output=None, failure_code="muse_model_failed", failure_category="unknown_error")
        failed["tool_exchanges"] = [
            {"tool_call_id": "route", "tool_name": "librarian_route", "arguments": {},
             "result": {"book_version_id": "pg11-v01b38ea4"}, "outcome": "success"},
            {"tool_call_id": "search", "tool_name": "librarian_search", "arguments": {"work_id": "pg11", "book_version_id": "pg11-v01b38ea"},
             "result": None, "outcome": None},
        ]
        scene["grades"][0]["failures"] = ["grounding_call_did_not_return_evidence_result",
            "response_not_released_from_allowed_source", "provenance_did_not_pass_release"]
    result, output = run_candidate(book_evidence, tmp_path, monkeypatch, passing_judgments=passed, mutation=change)
    assert result["status"] == "review_required"
    assert result["publication"]["route"] == route
    assert (result["totals"]["judgments_passed"], result["totals"]["judgments_total"]) == (passed, passed + 1)
    assert result["runs"][0]["results"]["execution_failures"] == [{"scene_id": "boundary", "detail": "Muse draft: muse_model_failed"}]
    assert candidate.validate_publication_evidence(result) == (passed, passed + 1)
    candidate.validate_evaluation_artifacts(result, output)


def test_future_task_failure_needs_no_new_exception(book_evidence, tmp_path, monkeypatch):
    result, _ = run_candidate(book_evidence, tmp_path, monkeypatch, passing_judgments=5,
        mutation=lambda scene: scene["grades"][0]["failures"].append("future_task_failure"))
    assert result["publication"]["route"] == "automatic"
    assert result["totals"]["judgments_failed"] == 1


def test_actual_unapproved_muse_release_still_blocks(book_evidence, tmp_path, monkeypatch):
    def change(scene):
        scene.update(release_source="muse_candidate", provenance_verdicts=[])
    result, _ = run_candidate(book_evidence, tmp_path, monkeypatch, passing_judgments=5, mutation=change)
    assert result["publication"]["route"] == "blocked"
    assert "Provenance approval" in " ".join(result["runs"][0]["problems"])
