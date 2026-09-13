"""The guided scenario workflow preserves selection, evidence, and run scope."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from evals.synthetic_journals import run_scenario, scenario_catalog
from evals.synthetic_journals.adoption import build_ground_truth_adoption
from evals.synthetic_journals.validate_scenario import validate_scenario_files

ROOT = Path(__file__).resolve().parents[1]
POTTERY = "pottery-memory-curation--sculptor--2026-08-29"
ROSES = "alice-roses-concealment-and-restraint--muse-librarian-serendipity-provenance--2026-09-12"
LOGFIRE_URL = (
    "https://logfire.example/project/evals/scenario/compare"
    "?experiment=0123456789-abcdef"
)
FAKE_KEYS = {
    "OPENAI_API_KEY": "unit-test-openai-key",
    "GOOGLE_API_KEY": "unit-test-google-key",
    "ANTHROPIC_API_KEY": "unit-test-anthropic-key",
    "EXA_API_KEY": "unit-test-exa-key",
    "LOGFIRE_TOKEN": "unit-test-logfire-token",
}


def _copy_scenario(repository: Path, name: str = POTTERY, source: str = POTTERY) -> Path:
    destination = scenario_catalog.scenario_root(repository) / name
    destination.mkdir(parents=True)
    for filename in scenario_catalog.SCENARIO_FILES:
        shutil.copyfile(scenario_catalog.scenario_root(ROOT) / source / filename, destination / filename)
    return destination


@pytest.fixture
def scenario_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    for name in (*scenario_catalog.SECRET_KEYS, "LINGER_MODEL", "LOGFIRE_CREDENTIALS_DIR", "LINGER_WEB_SEARCH_ENABLED"):
        monkeypatch.delenv(name, raising=False)
    repository = tmp_path / "repository"
    scenario = _copy_scenario(repository)
    (repository / ".env").write_text(
        "LINGER_MODEL=openai:configured-model\n"
        + "".join(f"{key}={value}\n" for key, value in FAKE_KEYS.items())
    )
    catalog = repository / "synthetic-journal-evaluation"
    (catalog / "evaluation-objectives.yaml").write_text(
        "evaluation_objectives:\n"
        "  - id: bounded_memory_curation\n"
        "    menu:\n"
        "      title: Preserve supplied memory sources\n"
    )
    return repository, scenario


def _menu(repository: Path) -> tuple[Path, int]:
    path, menu = run_scenario.create_menu(repository, repository / "menu.json")
    entry = next(item for item in menu["entries"] if item["scenario"] == POTTERY)
    assert entry["issues"] == []
    return path, entry["number"]


def test_supported_legacy_reflection_scenario_is_not_rejected_by_connection_compiler(scenario_repo):
    from tests.test_synthetic_reflection_replay import (
        _content_document, _ground_truth_document, _json_bytes,
    )

    repository, _ = scenario_repo
    scenario = scenario_catalog.scenario_root(repository) / "legacy-reflection"
    scenario.mkdir()
    backstory_bytes = _json_bytes(_content_document())
    truth = _ground_truth_document(backstory_bytes)
    truth["proposals"][0]["prop_relevance"] = [{"prop_id": "prop-01", "relevance": "relevant"}]
    truth_bytes = _json_bytes(truth)
    (scenario / "backstory.json").write_bytes(backstory_bytes)
    (scenario / "ground-truth.json").write_bytes(truth_bytes)
    _, proposed = validate_scenario_files(scenario / "backstory.json", scenario / "ground-truth.json")
    adoption = build_ground_truth_adoption(proposed, truth_bytes, reviewer_id="isolated-test-reviewer")
    (scenario / "ground-truth-adoption.json").write_text(adoption.model_dump_json())

    inspected = scenario_catalog.inspect_scenario(scenario, repository, "openai:confirmed-model")
    assert inspected["runner"] == "evals.synthetic_journals.connection_replay"
    assert inspected["issues"] == []


def _artifact(*, failed: bool = False, scenario_name: str = POTTERY) -> dict:
    scene_ids = [
        scene["scene_id"] for scene in json.loads(
            (scenario_catalog.scenario_root(ROOT) / scenario_name / "backstory.json").read_text()
        )["scenes"]
    ]
    return {
        "ground_truth_status": "adopted",
        "scenes": [{
            "scene_id": scene_id,
            "grade": {
                "hard_pass": not (failed and index == 0),
                "failures": ["expected link_duplicates"] if failed and index == 0 else [],
            },
        } for index, scene_id in enumerate(scene_ids)],
    }


def _marker(*, flushed: bool = True) -> str:
    return run_scenario.LINK_MARKER + json.dumps({
        "url": LOGFIRE_URL,
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "flushed": flushed,
    })


def _stub_replay(
    monkeypatch: pytest.MonkeyPatch,
    *,
    artifact: dict | None = None,
    returncode: int = 0,
    stderr: str | None = None,
) -> list[tuple[list[str], dict]]:
    calls = []

    def replay(command, **kwargs):
        calls.append((command, kwargs))
        if artifact is not None:
            Path(command[command.index("--output") + 1]).write_text(json.dumps(artifact))
        return SimpleNamespace(returncode=returncode, stdout="", stderr=stderr if stderr is not None else _marker())

    # Replace only this module's provider process interface; report generation
    # still uses the real, local Git commands in scenario_diagnostics.
    monkeypatch.setattr(run_scenario, "subprocess", SimpleNamespace(
        run=replay, TimeoutExpired=subprocess.TimeoutExpired,
    ))
    return calls


@pytest.mark.parametrize("failed_index", [None, 0, 11])
def test_guided_combined_run_preserves_original_files_and_reports_both_objectives(
    scenario_repo, monkeypatch, failed_index
) -> None:
    from tests.test_synthetic_capture_curation_replay import _combined_documents

    repository, _ = scenario_repo
    scenario = scenario_catalog.scenario_root(repository) / "combined-capture-curation"
    scenario.mkdir()
    backstory, truth, backstory_bytes = _combined_documents()
    truth_bytes = json.dumps(truth).encode()
    (scenario / "backstory.json").write_bytes(backstory_bytes)
    (scenario / "ground-truth.json").write_bytes(truth_bytes)
    _, proposed = validate_scenario_files(scenario / "backstory.json", scenario / "ground-truth.json")
    adoption = build_ground_truth_adoption(proposed, truth_bytes, reviewer_id="isolated-test-reviewer")
    (scenario / "ground-truth-adoption.json").write_text(adoption.model_dump_json())
    original_hashes = scenario_catalog.scenario_hashes(scenario)
    menu_path, menu = run_scenario.create_menu(repository, repository / "menu.json")
    entry = next(item for item in menu["entries"] if item["scenario"] == scenario.name)
    assert entry["issues"] == []
    observations = []
    for index, scene in enumerate(backstory["scenes"]):
        passed = index != failed_index
        observation = {
            "scene_id": scene["scene_id"],
            "ground_truth_result": "passes_hard_gates" if passed else "fails_hard_gates",
        }
        if scene["objective_ids"] == ["reviewed_automatic_memory_capture"]:
            observation["hard_failures"] = [] if passed else ["nomination_mismatch"]
        else:
            observation["grade"] = {
                "hard_pass": passed,
                "failures": [] if passed else ["expected link_duplicates"],
            }
        observations.append(observation)
    calls = _stub_replay(monkeypatch, artifact={
        "objective_ids": backstory["objective_ids"],
        "ground_truth_status": "adopted",
        "scenes": observations,
    })

    result = run_scenario.run_selected(
        menu_path, entry["number"], "openai:selected-model", repository_root=repository
    )

    assert result["status"] == ("passed" if failed_index is None else "failed")
    assert calls[0][0][2:5] == [
        "evals.synthetic_journals.capture_curation_replay",
        str(scenario / "backstory.json"), str(scenario / "ground-truth.json"),
    ]
    command = calls[0][0]
    assert command[command.index("--adoption") + 1] == str(scenario / "ground-truth-adoption.json")
    assert scenario_catalog.scenario_hashes(scenario) == original_hashes
    assert result["results"]["scenes_total"] == 16
    assert result["results"]["judgments_failed"] == (0 if failed_index is None else 1)
    analysis = json.loads(Path(result["analysis_data"]).read_text())
    assert analysis["evidence"]["run_identity"]["objective_ids"] == backstory["objective_ids"]
    assert [scene["scene_id"] for scene in analysis["scenes"]] == [
        scene["scene_id"] for scene in backstory["scenes"]
    ]
    assert all(scene["status"] != "not_run" for scene in analysis["scenes"])


def test_provider_failure_inside_zero_exit_artifact_is_execution_error(scenario_repo, monkeypatch):
    repository, _ = scenario_repo
    menu, number = _menu(repository)
    artifact = _artifact()
    artifact["scenes"][0]["grade"] = {"hard_pass": False, "failures": ["provider_failure"]}
    _stub_replay(monkeypatch, artifact=artifact)

    result = run_scenario.run_selected(menu, number, "openai:confirmed-model", repository_root=repository)

    assert result["status"] == "failed"
    assert result["results"]["execution_failures"]
    analysis = json.loads(Path(result["analysis_data"]).read_text())
    assert analysis["category"] == "execution"
    assert analysis["summary"]["execution_failures"]


def test_menu_discovers_scenarios_and_extracts_description_without_generation(scenario_repo) -> None:
    repository, scenario = scenario_repo
    fallback = _copy_scenario(repository, "zebra-notes--test")
    unfinished = scenario_catalog.scenario_root(repository) / "unfinished"
    unfinished.mkdir()
    (scenario_catalog.scenario_root(repository) / "README.md").write_text("A file, not a scenario.")
    (scenario_catalog.scenario_root(repository) / "linked-scenario").symlink_to(scenario, target_is_directory=True)
    (repository / "synthetic-journal-evaluation" / "scenario_descriptions.md").write_text(
        "# Scenarios\n\n## Pottery from the source document\n\n"
        "Objective: Prove source preservation\n"
        "  across duplicate notes and unrelated topics.\n\n"
        f"[Backstory](scenarios/{scenario.name}/backstory.json)\n"
        "This following paragraph is not part of the objective.\n"
    )

    entries = scenario_catalog.discover(repository)

    assert {entry["scenario"] for entry in entries} == {scenario.name, fallback.name, unfinished.name}
    assert [entry["number"] for entry in entries] == [1, 2, 3]
    by_scenario = {entry["scenario"]: entry for entry in entries}
    described = by_scenario[scenario.name]
    assert described["title"] == "Pottery from the source document"
    assert described["description"] == "Prove source preservation across duplicate notes and unrelated topics."
    assert described["scene_count"] == 5
    assert described["issues"] == []
    assert by_scenario[fallback.name]["title"] == "Zebra notes"
    assert by_scenario[fallback.name]["description"] == "Preserve supplied memory sources"
    assert by_scenario[unfinished.name]["issues"]


def test_saved_menu_number_keeps_its_scenario_after_discovery_changes(scenario_repo, monkeypatch) -> None:
    repository, scenario = scenario_repo
    menu_path, number = _menu(repository)
    _copy_scenario(repository, "aaa-new-scenario--test")
    assert scenario_catalog.discover(repository)[0]["scenario"] != scenario.name
    calls = _stub_replay(monkeypatch, artifact=_artifact())

    result = run_scenario.run_selected(menu_path, number, "openai:selected-model", repository_root=repository)

    assert result["status"] == "passed"
    assert result["scenario"] == scenario.name
    assert calls[0][0][3] == str(scenario / "backstory.json")


def test_pre_rename_menu_requests_refresh_before_selection(scenario_repo) -> None:
    repository, _ = scenario_repo
    path, menu = run_scenario.create_menu(repository, repository / "old-menu.json")
    menu["schema_version"] = 1
    for entry in menu["entries"]:
        entry["package"] = entry.pop("scenario")
    path.write_text(json.dumps(menu))

    with pytest.raises(ValueError, match="refresh"):
        run_scenario.read_selection(path, 1, repository)


def test_changed_scenario_hashes_block_invocation_and_save_diagnosis(scenario_repo, monkeypatch) -> None:
    repository, scenario = scenario_repo
    menu_path, number = _menu(repository)
    truth = scenario / "ground-truth.json"
    truth.write_text(truth.read_text() + "\n")
    calls = _stub_replay(monkeypatch, artifact=_artifact())

    result = run_scenario.run_selected(menu_path, number, "openai:selected-model", repository_root=repository)

    assert result["status"] == "blocked"
    assert calls == []
    report = Path(result["analysis_report"])
    assert report.parent == scenario
    assert "Scenario files changed after the displayed menu" in report.read_text()
    analysis = json.loads(Path(result["analysis_data"]).read_text())
    assert analysis["execution_status"] == "not_started"
    assert all(scene["status"] == "not_run" for scene in analysis["scenes"])
    assert not list(scenario.glob("scenario-run-*"))


def test_cli_requires_explicit_confirmed_model_before_run(scenario_repo, monkeypatch, capsys) -> None:
    repository, _ = scenario_repo
    menu_path, number = _menu(repository)
    invoke = Mock(side_effect=AssertionError("confirmation is required"))
    monkeypatch.setattr(run_scenario, "run_selected", invoke)

    with pytest.raises(SystemExit) as raised:
        run_scenario.main(["run", "--menu", str(menu_path), "--number", str(number)])

    assert raised.value.code == 2
    assert "--confirmed-model" in capsys.readouterr().err
    invoke.assert_not_called()


def test_selected_model_and_web_search_are_scoped_to_provider_process(scenario_repo, monkeypatch) -> None:
    repository, _ = scenario_repo
    roses = _copy_scenario(repository, ROSES, ROSES)
    monkeypatch.setenv("LINGER_MODEL", "openai:ambient-model")
    monkeypatch.setenv("LINGER_WEB_SEARCH_ENABLED", "false")
    original_env_file = (repository / ".env").read_bytes()
    menu_path, menu = run_scenario.create_menu(repository, repository / "menu.json")
    entry = next(item for item in menu["entries"] if item["scenario"] == roses.name)
    assert entry["issues"] == []
    assert entry["requires_web"] is True
    calls = _stub_replay(monkeypatch, artifact=_artifact(scenario_name=ROSES))

    result = run_scenario.run_selected(menu_path, entry["number"], "google:selected-model", repository_root=repository)

    assert result["status"] == "passed"
    command, invocation = calls[0]
    assert command[2] == "evals.synthetic_journals.connection_replay"
    assert invocation["cwd"] == repository
    assert invocation["env"]["LINGER_MODEL"] == "google:selected-model"
    assert invocation["env"]["LINGER_WEB_SEARCH_ENABLED"] == "true"
    assert os.environ["LINGER_MODEL"] == "openai:ambient-model"
    assert os.environ["LINGER_WEB_SEARCH_ENABLED"] == "false"
    assert (repository / ".env").read_bytes() == original_env_file


def test_missing_selected_provider_key_blocks_and_report_contains_no_credentials(scenario_repo, monkeypatch, capsys) -> None:
    repository, scenario = scenario_repo
    menu_path, number = _menu(repository)
    env_file = repository / ".env"
    env_file.write_text(env_file.read_text().replace(f"ANTHROPIC_API_KEY={FAKE_KEYS['ANTHROPIC_API_KEY']}\n", ""))
    calls = _stub_replay(monkeypatch, artifact=_artifact())

    result = run_scenario.run_selected(menu_path, number, "anthropic:selected-model", repository_root=repository)

    assert result["status"] == "blocked"
    assert calls == []
    report = Path(result["analysis_report"])
    assert report.parent == scenario
    text = report.read_text()
    assert "Missing ANTHROPIC_API_KEY" in text
    rendered = json.dumps(result) + text + Path(result["analysis_data"]).read_text() + capsys.readouterr().out
    assert all(secret not in rendered for secret in FAKE_KEYS.values())


def test_failed_grades_fail_wrapper_even_when_runner_exits_zero(scenario_repo, monkeypatch) -> None:
    repository, scenario = scenario_repo
    menu_path, number = _menu(repository)
    _stub_replay(monkeypatch, artifact=_artifact(failed=True))

    result = run_scenario.run_selected(menu_path, number, "openai:selected-model", repository_root=repository)

    assert result["returncode"] == 0
    assert result["status"] == "failed"
    assert result["results"]["scenes_failed"] == 1
    assert result["results"]["judgments_failed"] == 1
    assert result["logfire_url"] == LOGFIRE_URL
    report = Path(result["analysis_report"])
    assert report.parent == scenario
    analysis = json.loads(Path(result["analysis_data"]).read_text())
    assert analysis["category"] == "behavioral"
    assert analysis["execution_status"] == "completed"
    failed_scene = next(scene for scene in analysis["scenes"] if scene["status"] == "failed")
    assert failed_scene["expected"]
    assert failed_scene["observed"]
    assert "expected link_duplicates" in json.dumps(failed_scene["failures"])


def test_failed_runner_keeps_exact_stderr_evaluation_link(scenario_repo, monkeypatch) -> None:
    repository, _ = scenario_repo
    menu_path, number = _menu(repository)
    stderr = "provider failure\n" + _marker() + "\n  " + _marker() + "\n" + run_scenario.LINK_MARKER + "invalid-json\n"
    _stub_replay(monkeypatch, returncode=7, stderr=stderr)

    result = run_scenario.run_selected(menu_path, number, "openai:selected-model", repository_root=repository)

    assert result["status"] == "failed"
    assert result["returncode"] == 7
    assert result["logfire_url"] == LOGFIRE_URL
    assert result["telemetry"]["trace_id"] == "a" * 32
    assert LOGFIRE_URL in Path(result["analysis_report"]).read_text()
    assert "provider failure" in Path(result["run_log"]).read_text()
    assert not Path(result["artifact"]).exists()


@pytest.mark.parametrize("saved_artifact", [False, True])
def test_timeout_saves_partial_redacted_log_and_report(scenario_repo, monkeypatch, saved_artifact) -> None:
    repository, scenario = scenario_repo
    menu_path, number = _menu(repository)

    def timeout(command, **kwargs):
        if saved_artifact:
            Path(command[command.index("--output") + 1]).write_text(json.dumps(_artifact()))
        raise subprocess.TimeoutExpired(
            command, kwargs["timeout"],
            output=f"provider stalled: {FAKE_KEYS['OPENAI_API_KEY']}".encode(),
            stderr=b"partial provider response",
        )

    monkeypatch.setattr(run_scenario, "subprocess", SimpleNamespace(run=timeout, TimeoutExpired=subprocess.TimeoutExpired))
    result = run_scenario.run_selected(menu_path, number, "openai:selected-model", repository_root=repository, timeout_seconds=0.25)
    if saved_artifact:
        assert result["results"]["judgments_passed"] == 5
        analysis = json.loads(Path(result["analysis_data"]).read_text())
        assert analysis["summary"]["judgments_passed"] == 5

    assert result["status"] == "failed"
    assert result["execution_status"] == "timed_out"
    assert any("0.25-second execution limit" in problem for problem in result["problems"])
    assert Path(result["analysis_report"]).parent == scenario
    log = Path(result["run_log"]).read_text()
    assert "partial provider response" in log
    assert "[REDACTED]" in log
    assert FAKE_KEYS["OPENAI_API_KEY"] not in log
    assert result["logfire_url"] is None
    assert json.loads(Path(result["summary_file"]).read_text())["status"] == "failed"


def test_repeated_runs_preserve_previous_output_and_use_unique_directories(scenario_repo, monkeypatch) -> None:
    repository, scenario = scenario_repo
    menu_path, number = _menu(repository)
    calls = _stub_replay(monkeypatch, artifact=_artifact())
    first = run_scenario.run_selected(menu_path, number, "openai:selected-model", repository_root=repository)
    previous = {name: Path(first[name]).read_bytes() for name in ("artifact", "run_log", "summary_file")}

    second = run_scenario.run_selected(menu_path, number, "openai:selected-model", repository_root=repository)

    assert first["status"] == second["status"] == "passed"
    assert len(calls) == 2
    first_directory = Path(first["artifact"]).parent
    second_directory = Path(second["artifact"]).parent
    assert first_directory != second_directory
    assert first_directory.parent == second_directory.parent == scenario
    assert first_directory.name.startswith("scenario-run-")
    for name, original in previous.items():
        assert Path(first[name]).read_bytes() == original
        assert Path(first[name]) != Path(second[name])
    assert {Path(first[name]).parent for name in previous} == {first_directory}


def test_existing_menu_snapshot_is_never_overwritten(scenario_repo, tmp_path) -> None:
    repository, _ = scenario_repo
    menu_path = tmp_path / "chosen-menu.json"
    run_scenario.create_menu(repository, menu_path)
    displayed = menu_path.read_bytes()
    _copy_scenario(repository, "another-scenario--test")

    with pytest.raises(FileExistsError):
        run_scenario.create_menu(repository, menu_path)

    assert menu_path.read_bytes() == displayed


def test_passing_run_also_saves_analysis_of_every_scenario_scene(scenario_repo, monkeypatch) -> None:
    repository, scenario = scenario_repo
    menu_path, number = _menu(repository)
    _stub_replay(monkeypatch, artifact=_artifact())

    result = run_scenario.run_selected(menu_path, number, "openai:selected-model", repository_root=repository)

    assert result["status"] == "passed"
    assert result["execution_status"] == "completed"
    assert Path(result["analysis_report"]).is_file()
    data = json.loads(Path(result["analysis_data"]).read_text())
    assert data["review"] is None
    assert data["summary"]["judgments_passed"] == 5
    expected_scene_ids = [scene["scene_id"] for scene in json.loads((scenario / "backstory.json").read_text())["scenes"]]
    assert [scene["scene_id"] for scene in data["scenes"]] == expected_scene_ids
    assert all(scene["status"] == "passed" for scene in data["scenes"])


@pytest.mark.parametrize("shape", ["missing", "duplicate", "unexpected", "malformed_grade"])
def test_incomplete_results_preserve_evidence_without_claiming_success(scenario_repo, monkeypatch, shape) -> None:
    repository, _ = scenario_repo
    menu_path, number = _menu(repository)
    artifact = _artifact()
    if shape == "missing":
        artifact["scenes"].pop()
    elif shape == "duplicate":
        artifact["scenes"].append(artifact["scenes"][0])
    elif shape == "unexpected":
        artifact["scenes"][0]["scene_id"] = "unrequested-scene"
    else:
        artifact["scenes"][0]["grade"] = {"hard_pass": False, "failures": None}
    _stub_replay(monkeypatch, artifact=artifact)

    result = run_scenario.run_selected(menu_path, number, "openai:selected-model", repository_root=repository)

    assert result["status"] == "failed"
    assert result["execution_status"] == "completed"
    assert result["problems"]
    assert "results" not in result
    assert json.loads(Path(result["artifact"]).read_text()) == artifact
    assert json.loads(Path(result["summary_file"]).read_text())["status"] == "failed"
    data = json.loads(Path(result["analysis_data"]).read_text())
    assert any(scene["status"] == "incomplete" for scene in data["scenes"])
    assert data["summary"]["judgments_passed"] == 4
    assert Path(result["analysis_report"]).is_file()


def test_report_command_rejects_pending_review_without_rerunning(scenario_repo, monkeypatch) -> None:
    repository, _ = scenario_repo
    menu_path, number = _menu(repository)
    calls = _stub_replay(monkeypatch, artifact=_artifact())
    result = run_scenario.run_selected(menu_path, number, "openai:selected-model", repository_root=repository)
    before = Path(result["analysis_report"]).read_bytes()

    assert run_scenario.main(["report", "--analysis", result["analysis_data"]]) == 2

    assert len(calls) == 1
    assert Path(result["analysis_report"]).read_bytes() == before
