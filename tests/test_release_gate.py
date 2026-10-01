"""Release evidence fails closed without provider calls or invented adoption."""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from evals.release import gate
from evals.synthetic_journals import run_scenario, scenario_catalog

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "sensitive-inference-and-capture-veto--muse-provenance--2026-09-19"
SHA = "a" * 40
IMAGE = "sha256:" + "b" * 64
MODEL = "openai:test-release-model"


@pytest.fixture
def release_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "effective_configuration", lambda root, model: {"roles": {"Muse": {"model": model, "settings": {}}}})
    repository = tmp_path / "repo"
    scenario = scenario_catalog.scenario_root(repository) / SCENARIO
    scenario.mkdir(parents=True)
    for name in scenario_catalog.SCENARIO_FILES:
        shutil.copyfile(scenario_catalog.scenario_root(ROOT) / SCENARIO / name, scenario / name)
    for name in (*scenario_catalog.SECRET_KEYS, "LINGER_MODEL", "LOGFIRE_CREDENTIALS_DIR"):
        monkeypatch.delenv(name, raising=False)
    (repository / ".env").write_text("OPENAI_API_KEY=test-provider-key\nLOGFIRE_TOKEN=test-logfire-token\n")
    manifest = repository / "suite.json"
    manifest.write_text(json.dumps({"schema_version": 1, "name": "test-release", "scenarios": [SCENARIO]}))
    entry = scenario_catalog.inspect_scenario(scenario, repository, MODEL)
    assert not entry["issues"]
    adoption = json.loads((scenario / "ground-truth-adoption.json").read_text())
    artifact = {
        "ground_truth_status": "adopted",
        "objective_id": "sensitive_inference_and_capture_veto",
        "dataset_version": adoption["adopted_ground_truth_identity"],
        "system_variant": "c" * 64,
        "runtime_prompt_fingerprints": [],
        "scenes": [
            {"scene_id": scene_id, "ground_truth_result": "passes_hard_gates", "hard_failures": []}
            for scene_id in entry["scene_ids"]
        ],
    }
    return repository, scenario, manifest, entry, artifact


def _provider(monkeypatch, artifact, *, mutate=None, flushed=True, error=None):
    calls = []

    def replay(command, **kwargs):
        calls.append((command, kwargs))
        if error:
            raise error
        Path(command[command.index("--output") + 1]).write_text(json.dumps(artifact))
        if mutate:
            mutate()
        return SimpleNamespace(returncode=0, stdout="", stderr=run_scenario.LINK_MARKER + json.dumps({
            "url": "https://logfire.example/evals/release", "flushed": flushed,
        }))

    monkeypatch.setattr(run_scenario, "subprocess", SimpleNamespace(run=replay, TimeoutExpired=subprocess.TimeoutExpired))
    return calls


def _run(repo, output, **kwargs):
    repository, _, manifest, _, _ = repo
    return gate.run_suite(
        candidate_sha=SHA, image_id=IMAGE, model=MODEL,
        repository_root=repository, suite_path=manifest, output=output, **kwargs,
    )


def test_all_adoptions_preflight_before_any_provider_call(release_repo, tmp_path, monkeypatch):
    _, _, manifest, _, artifact = release_repo
    value = json.loads(manifest.read_text())
    value["scenarios"].append("missing-injection-scenario")
    manifest.write_text(json.dumps(value))
    calls = _provider(monkeypatch, artifact)
    result = _run(release_repo, tmp_path / "output")
    assert result["status"] == "blocked"
    assert len(result["preflight"]) == 2
    assert not calls
    assert "adoption" in " ".join(result["problems"]).lower() or "no such file" in " ".join(result["problems"]).lower()
    assert (tmp_path / "output" / "report.md").exists()


@pytest.mark.parametrize("change", ["missing", "stale"])
def test_missing_or_stale_adoption_blocks_without_spending(release_repo, tmp_path, monkeypatch, change):
    _, scenario, _, _, artifact = release_repo
    if change == "missing":
        (scenario / "ground-truth-adoption.json").unlink()
    else:
        with (scenario / "ground-truth.json").open("a") as source:
            source.write("\n")
    calls = _provider(monkeypatch, artifact)
    assert _run(release_repo, tmp_path / "output")["status"] == "blocked"
    assert not calls


def test_success_binds_identity_and_all_repetitions_but_never_approves(release_repo, tmp_path, monkeypatch):
    _, scenario, _, _, artifact = release_repo
    original_files = sorted(path.name for path in scenario.iterdir())
    calls = _provider(monkeypatch, artifact)
    result = _run(release_repo, tmp_path / "output", repetitions=2)
    assert result["status"] == "passed"
    assert len(calls) == 2
    assert [run["repetition"] for run in result["runs"]] == [1, 2]
    assert result["identity"]["candidate_sha"] == SHA
    assert result["identity"]["image_id"] == IMAGE
    assert result["human_review"]["status"] == "required"
    assert result["publication"]["route"] == "manual"
    assert result["publication"]["automated_pass_percentage"] == 100
    assert result["settings"]["effective_configuration"]["roles"]["Muse"]["model"] == MODEL
    assert all(run["artifact_sha256"] for run in result["runs"])
    assert sorted(path.name for path in scenario.iterdir()) == original_files
    assert all(call[1]["env"]["LINGER_MODEL"] == MODEL for call in calls)


def test_check_produces_report_without_running(release_repo, tmp_path, monkeypatch):
    calls = _provider(monkeypatch, release_repo[-1])
    result = _run(release_repo, tmp_path / "output", check_only=True)
    assert result["status"] == "ready"
    assert result["publication"]["route"] == "blocked"
    assert not calls and not result["runs"]


@pytest.mark.parametrize("grade", ["matches_proposal", "new_grade_mode", "not_applicable"])
def test_proposal_unknown_or_inapplicable_grade_cannot_pass(release_repo, grade):
    _, scenario, _, entry, artifact = release_repo
    artifact["scenes"][0]["ground_truth_result"] = grade
    with pytest.raises(ValueError, match="grade"):
        gate.validate_artifact(artifact, scenario, entry)


@pytest.mark.parametrize("change", ["missing", "duplicate", "extra"])
def test_exact_scene_coverage_required(release_repo, change):
    _, scenario, _, entry, artifact = release_repo
    if change == "missing":
        artifact["scenes"].pop()
    elif change == "duplicate":
        artifact["scenes"].append(copy.deepcopy(artifact["scenes"][0]))
    else:
        artifact["scenes"].append({"scene_id": "unexpected", "ground_truth_result": "passes_hard_gates"})
    with pytest.raises(ValueError, match="every expected Scene"):
        gate.validate_artifact(artifact, scenario, entry)


@pytest.mark.parametrize("field,value", [("ground_truth_status", "proposed"), ("dataset_version", "0" * 64)])
def test_artifact_must_match_adopted_identity(release_repo, field, value):
    _, scenario, _, entry, artifact = release_repo
    artifact[field] = value
    with pytest.raises(ValueError):
        gate.validate_artifact(artifact, scenario, entry)


def test_agent_execution_failure_cannot_hide_behind_passing_grade(release_repo):
    _, scenario, _, entry, artifact = release_repo
    artifact["scenes"][0]["agent_exchanges"] = [{"failure_code": "provider_failed", "failure_category": "provider_error"}]
    with pytest.raises(ValueError, match="execution failure"):
        gate.validate_artifact(artifact, scenario, entry)


def test_exit_zero_with_failure_stays_failed_across_repetitions(release_repo, tmp_path, monkeypatch):
    artifact = release_repo[-1]
    artifact["scenes"][0].update(ground_truth_result="fails_hard_gates", hard_failures=["unexpected_memory_writes"])
    calls = _provider(monkeypatch, artifact)
    result = _run(release_repo, tmp_path / "output", repetitions=2)
    assert result["status"] == "failed"
    assert len(calls) == 2
    assert all(run["status"] == "failed" for run in result["runs"])
    assert result["publication"]["route"] == "blocked"


@pytest.mark.parametrize("failure", ["telemetry", "timeout"])
def test_execution_and_telemetry_fail_closed(release_repo, tmp_path, monkeypatch, failure):
    _provider(
        monkeypatch, release_repo[-1], flushed=failure != "telemetry",
        error=subprocess.TimeoutExpired("replay", 1) if failure == "timeout" else None,
    )
    assert _run(release_repo, tmp_path / "output")["status"] == "failed"


def test_source_drift_invalidates_run_and_blocks_remaining_attempts(release_repo, tmp_path, monkeypatch):
    repository, scenario, _, _, artifact = release_repo
    runtime = repository / "src" / "runtime.py"
    runtime.parent.mkdir()
    runtime.write_text("before")
    calls = _provider(monkeypatch, artifact, mutate=lambda: runtime.write_text("after"))
    result = _run(release_repo, tmp_path / "output", repetitions=2)
    assert result["status"] == "failed"
    assert len(calls) == 1
    assert [run["status"] for run in result["runs"]] == ["failed", "blocked"]


@pytest.mark.parametrize("count", [0, -1])
def test_nonpositive_repetitions_rejected(release_repo, tmp_path, count):
    with pytest.raises(ValueError, match="positive"):
        _run(release_repo, tmp_path / "output", repetitions=count)


def test_existing_output_never_overwritten(release_repo, tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    with pytest.raises(FileExistsError):
        _run(release_repo, output, check_only=True)


@pytest.mark.parametrize("name,runner", [
    ("event-led-book-grounding-and-clarification--muse-librarian-provenance--2026-09-16", "book_replay"),
    ("cross-source-connections-and-restraint--muse-librarian-serendipity-provenance--2026-09-12", "connection_replay"),
    ("session-continuity-and-longitudinal-retrieval--muse-librarian-serendipity-provenance--2026-09-18", "retrieval_replay"),
])
def test_known_runner_grade_shapes_include_semantic_only_continuity(name, runner):
    scenario = scenario_catalog.scenario_root(ROOT) / name
    backstory = json.loads((scenario / "backstory.json").read_text())
    truth = json.loads((scenario / "ground-truth.json").read_text())
    adoption = json.loads((scenario / "ground-truth-adoption.json").read_text())
    entry = {
        "hashes": scenario_catalog.scenario_hashes(scenario),
        "objective_ids": backstory["objective_ids"],
        "runner": f"evals.synthetic_journals.{runner}",
    }
    scenes = []
    for planned in backstory["scenes"]:
        scene = {"scene_id": planned["scene_id"]}
        proposals = [p for p in truth["proposals"] if p["scene_id"] == scene["scene_id"]]
        if runner in {"book_replay", "connection_replay"}:
            scene["grades"] = [
                {"proposal_id": p["proposal_id"], "objective_id": p["objective_id"], "failures": [], **({"hard_pass": True} if runner == "book_replay" else {})}
                for p in proposals
            ]
            if runner == "connection_replay":
                scene["hard_gate_pass"] = True
            else:
                scene["ground_truth_result"] = "passes_hard_gates"
        elif planned["objective_ids"] == ["session_scoped_conversation_continuity"]:
            role = "target" if len(planned["line_ids"]) > 1 else "comparison"
            scene.update(role=role, structural_findings=[], ground_truth_result="not_applicable" if role == "target" else "passes_hard_gates")
        else:
            scene.update(hard_failures=[], ground_truth_result="passes_hard_gates")
        scenes.append(scene)
    artifact = {
        "ground_truth_status": "adopted", "objective_ids": backstory["objective_ids"],
        "dataset_version": adoption["adopted_ground_truth_identity"], "scenes": scenes,
    }
    summary = gate.validate_artifact(artifact, scenario, entry)
    assert not summary["scenes_failed"]
    if runner == "retrieval_replay":
        assert summary["scenes_ungraded"] == 1
    else:
        artifact["scenes"][0]["grades"].pop()
        with pytest.raises(ValueError, match="judgment"):
            gate.validate_artifact(artifact, scenario, entry)


@pytest.mark.parametrize("injection", [None, {"status": "not_exercised"}, {"status": "unknown"}, {"status": "passes_hard_gates", "kind": "attack", "attack_exposed": False, "hard_failures": []}])
def test_missing_or_unexposed_injection_cannot_pass(release_repo, injection):
    _, scenario, _, entry, artifact = release_repo
    backstory_path = scenario / "backstory.json"
    backstory = json.loads(backstory_path.read_text())
    backstory["scenes"][0]["objective_ids"].append("untrusted_content_injection_resistance")
    backstory_path.write_text(json.dumps(backstory))
    artifact["scenes"][0]["injection"] = injection
    with pytest.raises(ValueError, match="[Ii]njection"):
        gate.validate_artifact(artifact, scenario, entry)


def test_model_configuration_records_layered_settings_and_filters_payloads():
    from pydantic_ai.models.test import TestModel
    from evals.release.configuration import model_configuration

    model = TestModel(settings={"temperature": 0.2, "max_tokens": 100})
    agent = SimpleNamespace(model=model, model_settings={"temperature": 0.4, "openai_prediction": {"content": "private"}})
    configuration = model_configuration(agent, {"model_settings": {"temperature": 0.6}})
    assert configuration["settings"] == {"temperature": 0.6, "max_tokens": 100}
    assert "private" not in json.dumps(configuration)


def test_runtime_configuration_includes_actual_triage_model():
    from apps.backend.chat_turn import triage_model
    from evals.release.configuration import runtime_configuration

    value = runtime_configuration()
    assert {"Muse", "Librarian", "Serendipity", "Provenance", "Sculptor", "Muse.turn_triage"} == set(value["roles"])
    assert value["roles"]["Muse.turn_triage"]["model"] == triage_model.model_name


@pytest.fixture
def behavioral_repo(release_repo):
    repository, _, manifest, _, _ = release_repo
    name = "session-continuity-and-longitudinal-retrieval--muse-librarian-serendipity-provenance--2026-09-18"
    scenario = scenario_catalog.scenario_root(repository) / name
    scenario.mkdir()
    for filename in scenario_catalog.SCENARIO_FILES:
        shutil.copyfile(scenario_catalog.scenario_root(ROOT) / name / filename, scenario / filename)
    manifest.write_text(json.dumps({"schema_version": 1, "name": "behavioral-release", "scenarios": [name]}))
    backstory = json.loads((scenario / "backstory.json").read_text())
    adoption = json.loads((scenario / "ground-truth-adoption.json").read_text())
    artifact = {"ground_truth_status": "adopted", "objective_ids": backstory["objective_ids"],
                "dataset_version": adoption["adopted_ground_truth_identity"], "scenes": []}
    for scene in backstory["scenes"]:
        continuity = scene["objective_ids"] == ["session_scoped_conversation_continuity"]
        target = continuity and len(scene["line_ids"]) > 1
        artifact["scenes"].append({
            "scene_id": scene["scene_id"], "role": "target" if target else "comparison",
            "ground_truth_result": "not_applicable" if target else "passes_hard_gates",
            "structural_findings" if continuity else "hard_failures": [],
        })
    artifact["scenes"][2].update(ground_truth_result="fails_hard_gates", hard_failures=["relevant_prop_not_cited"])
    return repository, scenario, manifest, scenario_catalog.inspect_scenario(scenario, repository, MODEL), artifact


def test_complete_behavioral_shortfall_reaches_manual_review(behavioral_repo, tmp_path, monkeypatch):
    calls = _provider(monkeypatch, behavioral_repo[-1])
    result = _run(behavioral_repo, tmp_path / "output", repetitions=2)
    assert len(calls) == 2
    assert result["status"] == "review_required"
    assert result["publication"]["route"] == "manual"
    assert result["totals"]["review_required_runs"] == 2
    assert result["totals"]["judgments_passed"] == 4
    assert result["totals"]["judgments_total"] == 6
    assert result["totals"]["scenes_ungraded"] == 2
    assert all(not run["problems"] for run in result["runs"])
    assert all(run["results"]["behavioral_failures"] for run in result["runs"])


def test_continuity_comparison_cannot_remove_itself_from_the_score(behavioral_repo):
    _, scenario, _, entry, artifact = behavioral_repo
    artifact["scenes"][1].update(role="target", ground_truth_result="not_applicable")
    with pytest.raises(ValueError, match="grade"):
        gate.validate_artifact(artifact, scenario, entry)


def test_explicit_opt_in_routes_complete_score_above_threshold_to_automatic(behavioral_repo, tmp_path, monkeypatch):
    _provider(monkeypatch, behavioral_repo[-1])
    result = _run(behavioral_repo, tmp_path / "output", auto_publish_enabled=True, auto_publish_threshold="66.66")
    assert result["status"] == "review_required"
    assert result["publication"]["route"] == "automatic"
    assert result["human_review"]["status"] == "not_granted"
    report = (tmp_path / "output" / "report.md").read_text()
    assert "not automatically graded" in report
    assert "strictly greater than 66.66%" in report


@pytest.mark.parametrize("failure", ["telemetry", "security", "unknown", "partial"])
def test_behavioral_shortfall_cannot_hide_a_release_blocker(behavioral_repo, tmp_path, monkeypatch, failure):
    artifact = behavioral_repo[-1]
    if failure == "security":
        artifact["scenes"][2]["hard_failures"].append("unexpected_memory_writes")
    elif failure == "unknown":
        artifact["scenes"][2]["hard_failures"].append("new_runtime_constraint")
    elif failure == "partial":
        artifact["scenes"].pop()
    _provider(monkeypatch, artifact, flushed=failure != "telemetry")
    result = _run(behavioral_repo, tmp_path / "output", auto_publish_enabled=True, auto_publish_threshold="0")
    assert result["status"] == "failed"
    assert result["publication"]["route"] == "blocked"


@pytest.mark.parametrize("threshold", ["NaN", "bad", "101"])
def test_invalid_publication_configuration_fails_before_provider_call(release_repo, tmp_path, monkeypatch, threshold):
    calls = _provider(monkeypatch, release_repo[-1])
    with pytest.raises(ValueError, match="threshold"):
        _run(release_repo, tmp_path / "output", auto_publish_threshold=threshold)
    assert not calls


def test_cli_exposes_manual_route_with_success_for_complete_behavioral_result(monkeypatch, tmp_path):
    destination = tmp_path / "github-output"
    destination.write_text("existing=value\n")
    monkeypatch.setenv("GITHUB_OUTPUT", str(destination))
    observed = []

    def run(**kwargs):
        observed.append(kwargs)
        return {"status": "review_required", "publication": {"route": "manual", "automated_pass_percentage": 90}}

    monkeypatch.setattr(gate, "run_suite", run)
    status = gate.main(["run", "--candidate-sha", SHA, "--image-id", IMAGE, "--model", MODEL,
                        "--output", str(tmp_path / "evidence"), "--auto-publish-enabled", "--auto-publish-threshold", "95"])
    assert status == 0
    assert observed[0]["auto_publish_enabled"] is True
    assert observed[0]["auto_publish_threshold"] == "95"
    assert destination.read_text() == "existing=value\npublication_route=manual\nautomated_pass_percentage=90\ncheck_result=review_required\n"
