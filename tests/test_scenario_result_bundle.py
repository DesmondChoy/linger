"""Consolidation preserves reviewed evidence after the original files are removed."""

import hashlib
import json
from pathlib import Path

import pytest

from evals.synthetic_journals.scenario_analysis import write_analysis_report
from tests.test_scenario_analysis import _review, _scenario, _scene


@pytest.fixture
def completed_run(tmp_path):
    scenario = _scenario(tmp_path)
    (scenario / "ground-truth-adoption.json").write_text('{"reviewer": "test"}\n')
    directory = tmp_path / "results" / "example-diagnostic"
    directory.mkdir(parents=True)
    artifact = {
        "run_id": "a" * 32,
        "trace_id": "b" * 32,
        "ground_truth_status": "adopted",
        "objective_ids": ["grounded_book_reflection"],
        "scenes": [_scene("second"), _scene("first")],
    }
    for scene in artifact["scenes"]:
        scene["agent_exchanges"] = [{
            "role": "Muse", "stage": "draft", "input_prompt": "Observed input",
            "model_messages": [{"parts": [{"part_kind": "text", "content": "Observed message"}]}],
            "output": {"reply": scene["reply"]},
        }]
    evaluation = directory / "evaluation.json"
    evaluation.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n")
    log = directory / "run.log"
    log.write_text("Original process log\n")
    report = write_analysis_report(
        scenario, repository_root=tmp_path, model="openai:test", category="none", problems=[],
        artifact=artifact, output_path=evaluation, run_log_path=log,
        execution_status="completed", report_dir=directory,
        logfire_url="https://logfire.example/exact-evaluation",
    )
    analysis_path = report.with_suffix(".json")
    analysis = json.loads(analysis_path.read_text())
    review = _review(analysis)
    for index, item in enumerate(review["scenes"]):
        item["semantic_review"] = {
            "status": "failed" if index == 0 else "passed",
            "scope": "Review the released response against the complete request.",
            "evidence_refs": [f"scenes[{index}].observed"],
        }
        if index == 0:
            item["assessment"] = "potential_false_positive"
            item["semantic_review"]["findings"] = [{
                "kind": "missing_required_context", "explanation": "The reply drops the personal reflection.",
                "evidence_refs": ["scenes[0].observed"],
            }]
    analysis["review"] = review
    analysis_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False) + "\n")
    (directory / "remote-visibility.json").write_text(json.dumps({
        "evaluation_url": "https://logfire.example/exact-evaluation", "completed_cases": 2,
        "verified_at": "2026-10-16T11:20:00+08:00", "trace_id": "b" * 32,
        "method": "Authenticated read-back of this evaluation and its model spans.",
    }))
    transcripts = directory / "scene-transcripts"
    transcripts.mkdir()
    for scene in artifact["scenes"]:
        (transcripts / f"{scene['scene_id']}.json").write_text(
            json.dumps(scene, indent=2, ensure_ascii=False) + "\n"
        )
    return directory, evaluation.read_bytes(), analysis


def test_bundle_keeps_only_two_files_and_preserves_original_evaluation_and_review(completed_run, tmp_path):
    from evals.synthetic_journals.result_bundle import bundle_run, extract_evaluation

    directory, original_bytes, original_analysis = completed_run
    bundle_run(directory, backup_root=tmp_path / "backups")

    assert sorted(path.name for path in directory.iterdir()) == ["result.json", "summary.md"]
    result = json.loads((directory / "result.json").read_text())
    assert result["evidence"]["analysis"]["data"] == original_analysis
    assert result["outcomes"]["automated"] == original_analysis["summary"]
    assert result["outcomes"]["response_review"] == {"failed": 1, "passed": 1}
    assert [scene["scene_id"] for scene in result["scenes"]] == ["first", "second"]
    assert result["scenes"][0]["response_review"] == "failed"
    embedded = result["evidence"]["evaluation"]
    assert embedded["sha256"] == hashlib.sha256(original_bytes).hexdigest()
    assert "source_text" not in embedded or embedded["source_text"] is None
    assert embedded["data"]["scenes"][0]["agent_exchanges"][0]["input_prompt"] == "Observed input"
    restored = extract_evaluation(directory / "result.json", tmp_path / "restored.json")
    assert restored.read_bytes() == original_bytes
    with pytest.raises((ValueError, FileExistsError)):
        extract_evaluation(directory / "result.json", restored)
    assert list((tmp_path / "backups").rglob("*.tar.gz"))


def test_noncanonical_evaluation_bytes_survive_consolidation(completed_run, tmp_path):
    from evals.synthetic_journals.result_bundle import bundle_run, extract_evaluation

    directory, _, _ = completed_run
    analysis_path = next(directory.glob("analysis-report-*.json"))
    data = json.loads(analysis_path.read_text())
    raw = (directory / "evaluation.json").read_text().replace("  ", "\t")
    (directory / "evaluation.json").write_text(raw)
    from evals.synthetic_journals.scenario_analysis import _facts_digest

    data["evidence"]["artifact_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
    data["facts_sha256"] = _facts_digest(data)
    data["review"]["facts_sha256"] = data["facts_sha256"]
    analysis_path.write_text(json.dumps(data))
    bundle_run(directory, backup_root=tmp_path / "backups")
    restored = extract_evaluation(directory / "result.json", tmp_path / "restored.json")
    assert restored.read_text() == raw


def test_pending_review_and_changed_artifact_leave_original_files_intact(completed_run, tmp_path):
    from evals.synthetic_journals.result_bundle import bundle_run

    directory, _, _ = completed_run
    analysis_path = next(directory.glob("analysis-report-*.json"))
    original = analysis_path.read_text()
    data = json.loads(original)
    data["review"] = None
    analysis_path.write_text(json.dumps(data))
    before = {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
    with pytest.raises(ValueError):
        bundle_run(directory, backup_root=tmp_path / "backups")
    assert before == {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
    analysis_path.write_text(original)
    (directory / "evaluation.json").write_text("{}")
    with pytest.raises(ValueError):
        bundle_run(directory, backup_root=tmp_path / "backups")
    assert analysis_path.is_file()
    assert (directory / "run.log").is_file()


def test_rerender_preserves_grades_and_rejects_changed_outcomes(completed_run, tmp_path):
    from evals.synthetic_journals.result_bundle import bundle_run, render_bundle

    directory, _, _ = completed_run
    backup_root = tmp_path / "backups"
    bundle_run(directory, backup_root=backup_root)
    result_path = directory / "result.json"
    data = json.loads(result_path.read_text())
    data["report_points"] = ["A hard pass can hide the loss of a requested reflection."]
    data["slide_points"] = ["Check the complete answer after repair."]
    data["worked_examples"] = [{
        "scene_id": "first", "request": "Connect the book to my experience.",
        "before": "The draft includes a personal connection.",
        "repair": "Map the claim or delete it.", "after": "The connection is missing.",
        "lesson": "Review whether revision still answers the request.",
    }]
    result_path.write_text(json.dumps(data))
    render_bundle(result_path)
    summary = (directory / "summary.md").read_text()
    assert data["report_points"][0] in summary
    assert data["slide_points"][0] in summary
    assert data["worked_examples"][0]["lesson"] in summary
    backups = list(backup_root.rglob("*.tar.gz"))
    bundle_run(directory, backup_root=backup_root)
    assert list(backup_root.rglob("*.tar.gz")) == backups
    data["outcomes"]["automated"]["scenes_passed"] = 999
    result_path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        render_bundle(result_path)


def test_summary_declares_failure_type_for_each_failed_scene(completed_run, tmp_path):
    from evals.synthetic_journals.result_bundle import bundle_run, render_bundle

    directory, _, _ = completed_run
    bundle_run(directory, backup_root=tmp_path / "backups")
    result_path = directory / "result.json"
    data = json.loads(result_path.read_text())
    failed = next(row["scene_id"] for row in data["scenes"] if row["response_review"] == "failed")
    assert "### " + failed + "\n\n**Failure type: not yet diagnosed.**" in (directory / "summary.md").read_text()

    data["failure_diagnoses"] = [{
        "scene_id": failed, "failure_type": "architectural_failure", "cause": "suspected",
        "failure": "Revision dropped the personal reflection.",
        "ground_truth": "The reply keeps the requested reflection.",
        "root_cause": "No stage re-checks the reflection after a factual repair.",
        "proposed_solution": "Add a coverage check after revision.",
    }]
    result_path.write_text(json.dumps(data))
    render_bundle(result_path)
    summary = (directory / "summary.md").read_text()
    assert "**Failure type: Architectural failure** (cause suspected)." in summary
    assert "**Root cause.** No stage re-checks the reflection after a factual repair." in summary

    diagnosis = data["failure_diagnoses"][0]
    passed = next(row["scene_id"] for row in data["scenes"] if row["scene_id"] != failed)
    for invalid in ([{**diagnosis, "scene_id": passed}], [{**diagnosis, "failure_type": "bad_luck"}],
                    [diagnosis, diagnosis]):
        data["failure_diagnoses"] = invalid
        result_path.write_text(json.dumps(data))
        with pytest.raises(ValueError):
            render_bundle(result_path)


def test_changed_source_snapshot_and_symlinks_are_not_removed(completed_run, tmp_path):
    from evals.synthetic_journals.result_bundle import bundle_run

    directory, _, original_analysis = completed_run
    source = Path(original_analysis["scenario_dir"]) / "backstory.json"
    source.write_text("{}")
    with pytest.raises(ValueError):
        bundle_run(directory, backup_root=tmp_path / "backups")
    assert (directory / "evaluation.json").is_file()
    (directory / "unexpected-link").symlink_to(source)
    with pytest.raises(ValueError):
        bundle_run(directory, backup_root=tmp_path / "backups")
    assert source.is_file()


def test_missing_hash_bound_input_stops_before_removing_evidence(completed_run, tmp_path):
    from evals.synthetic_journals.result_bundle import bundle_run

    directory, _, analysis = completed_run
    (Path(analysis["scenario_dir"]) / "ground-truth-adoption.json").unlink()
    with pytest.raises(ValueError, match="input snapshot is unavailable"):
        bundle_run(directory, backup_root=tmp_path / "backups")
    assert (directory / "evaluation.json").is_file()
    assert not (directory / "result.json").exists()


@pytest.mark.parametrize("execution_status", ["timed_out", "not_started"])
def test_attempt_without_evaluation_preserves_unexercised_results(tmp_path, execution_status):
    from evals.synthetic_journals.result_bundle import bundle_run, extract_evaluation

    scenario = _scenario(tmp_path)
    directory = tmp_path / "results" / "incomplete-attempt"
    directory.mkdir(parents=True)
    report = write_analysis_report(
        scenario, repository_root=tmp_path, model="openai:test", category="execution",
        problems=["The evaluation did not finish."], execution_status=execution_status,
        report_dir=directory,
    )
    path = report.with_suffix(".json")
    data = json.loads(path.read_text())
    data["review"] = _review(data)
    path.write_text(json.dumps(data))
    bundle_run(directory, backup_root=tmp_path / "backups")
    result = json.loads((directory / "result.json").read_text())
    assert result["evidence"]["evaluation"] is None
    assert result["outcomes"]["automated"]["scenes_passed"] == 0
    assert result["outcomes"]["response_review"] == {"unreviewed": 2}
    assert result["run"]["execution_status"] == execution_status
    with pytest.raises(ValueError):
        extract_evaluation(directory / "result.json", tmp_path / "nonexistent-evaluation.json")


def test_offline_cli_bundles_renders_and_extracts_without_executing_a_run(completed_run, tmp_path, monkeypatch):
    from evals.synthetic_journals import run_scenario

    directory, original_bytes, _ = completed_run
    monkeypatch.setattr(run_scenario, "run_selected", lambda *a, **kw: pytest.fail("unexpected live run"))
    assert run_scenario.main(["bundle", "--run-directory", str(directory)]) == 0
    result = directory / "result.json"
    assert run_scenario.main(["report", "--result", str(result)]) == 0
    output = tmp_path / "evaluation.json"
    assert run_scenario.main(["extract", "--result", str(result), "--output", str(output)]) == 0
    assert output.read_bytes() == original_bytes


def test_cli_forwards_explicit_run_output_directory(tmp_path, monkeypatch):
    from unittest.mock import Mock
    from evals.synthetic_journals import run_scenario

    invoke = Mock(return_value={"status": "passed"})
    monkeypatch.setattr(run_scenario, "run_selected", invoke)
    output = tmp_path / "results" / "next-run"
    assert run_scenario.main([
        "run", "--menu", "menu.json", "--number", "1", "--confirmed-model", "openai:test",
        "--output-directory", str(output),
    ]) == 0
    assert invoke.call_args.kwargs["output_directory"] == output
