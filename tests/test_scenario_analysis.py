"""Analysis completion, grade integrity, and evidence separation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.synthetic_journals.scenario_analysis import render_analysis_report, write_analysis_report


def _package(root: Path) -> Path:
    package = root / "example"
    package.mkdir()
    (package / "backstory.json").write_text(json.dumps({"scenes": [
        {"scene_id": "second", "order": 2}, {"scene_id": "first", "order": 1},
    ]}))
    (package / "ground-truth.json").write_text(json.dumps({"proposals": [
        {"scene_id": scene_id, "proposal_id": f"p-{scene_id}", "objective_id": "grounded_book_reflection",
         "expected_outcomes": [f"Quote the passage for {scene_id}."],
         "prohibited_outcomes": ["Invent a passage."],
         "book_expectation": {"kind": "grounded_book_reflection", "retrieval": "required"}}
        for scene_id in ("first", "second")
    ]}))
    return package


def _scene(scene_id: str, *, failed: bool = False) -> dict:
    return {"scene_id": scene_id, "reply": f"Observed reply for {scene_id}.", "grades": [{
        "proposal_id": f"p-{scene_id}", "hard_pass": not failed,
        "failures": ["missing_required_quote"] if failed else [],
    }]}


def _write(root: Path, *, artifact: dict | None = None, execution_status: str = "completed", **kwargs) -> Path:
    package = _package(root)
    return write_analysis_report(
        package, repository_root=root, model="openai:test", category="none", problems=[],
        artifact=artifact, execution_status=execution_status, **kwargs,
    )


def _review(data: dict) -> dict:
    assessments = {
        "passed": "credible_pass", "failed": "supported_failure", "ungraded": "inconclusive",
        "incomplete": "inconclusive", "not_run": "not_exercised",
    }
    return {
        "verdict": "The recorded grades have been reviewed against the scenario goal.",
        "scenario_assessment": {
            "goal": "Exercise exact passage quotation.",
            "input_validity": "The supplied reading position and passage request are consistent.",
            "ground_truth_validity": "The expectation still requires a retrieved exact quotation.",
        },
        "confidence": "confirmed",
        "scenes": [{
            "scene_id": scene["scene_id"],
            "expected_behavior": f"Quote the passage for {scene['scene_id']}.",
            "observed_behavior": f"Inspect the recorded reply for {scene['scene_id']}.",
            "interpretation": f"The recorded path for {scene['scene_id']} was compared with its intended behavior.",
            "assessment": assessments[scene["status"]], "confidence": "confirmed",
            "evidence_refs": scene["evidence_refs"],
            "grade_reliability": f"The exact quotation check for {scene['scene_id']} covers this claim; broader interpretation is outside its scope.",
            "next_step": "No corrective action identified." if scene["status"] == "passed" else "Inspect the missing or failed observation.",
        } for scene in data["scenes"]],
        "next_steps": [],
    }


def _save_review(path: Path, review: dict | None = None) -> dict:
    data = json.loads(path.read_text())
    data["review"] = review if review is not None else _review(data)
    path.write_text(json.dumps(data, indent=2))
    return data


def test_all_pass_attempt_saves_pending_report_for_every_scene_in_package_order(tmp_path):
    path = _write(tmp_path, artifact={"scenes": [_scene("second"), _scene("first")]})
    data = json.loads(path.with_suffix(".json").read_text())
    assert data["review"] is None
    assert [scene["scene_id"] for scene in data["scenes"]] == ["first", "second"]
    assert [scene["status"] for scene in data["scenes"]] == ["passed", "passed"]
    assert data["summary"]["judgments_passed"] == 2
    assert data["scenes"][0]["expected"][0]["book_expectation"]["retrieval"] == "required"
    assert data["scenes"][0]["observed"]["reply"] == "Observed reply for first."
    report = path.read_text()
    assert "Analysis pending" in report
    assert "### first" in report and "### second" in report
    assert "Remote trace visibility: unverified" in report
    with pytest.raises(ValueError, match="review is required"):
        render_analysis_report(path.with_suffix(".json"))


def test_final_report_contains_pass_commentary_and_renders_deterministically(tmp_path):
    path = _write(tmp_path, artifact={"scenes": [_scene("first"), _scene("second")]})
    data_path = path.with_suffix(".json")
    before = json.loads(data_path.read_text())
    reviewed = _save_review(data_path)
    reviewed["review"]["scenes"].reverse()
    data_path.write_text(json.dumps(reviewed))
    assert render_analysis_report(data_path) == path
    first_render = path.read_bytes()
    render_analysis_report(data_path)
    assert path.read_bytes() == first_render
    report = first_render.decode()
    for scene_id in ("first", "second"):
        assert f"Quote the passage for {scene_id}." in report
        assert f"Inspect the recorded reply for {scene_id}." in report
        assert f"The exact quotation check for {scene_id}" in report
        assert f"The recorded path for {scene_id}" in report
    assert report.index("### first") < report.index("### second")
    assert "No corrective action identified." in report
    assert "Analysis pending" not in report
    assert [line for line in report.splitlines() if line.startswith("## ")] == [
        "## Outcome", "## Scene results", "## Scene analysis", "## Next steps", "## Evidence",
    ]
    assert "scenes[0].expected" not in report
    after = json.loads(data_path.read_text())
    assert {k: v for k, v in after.items() if k != "review"} == {k: v for k, v in before.items() if k != "review"}


def test_mixed_results_preserve_failed_grades_when_review_explains_unexercised_behavior(tmp_path):
    path = _write(tmp_path, artifact={"scenes": [_scene("first"), _scene("second", failed=True)]})
    data_path = path.with_suffix(".json")
    data = json.loads(data_path.read_text())
    review = _review(data)
    review["scenes"][1].update({
        "assessment": "not_exercised", "interpretation": "An upstream book clarification prevented quotation retrieval.",
        "grade_reliability": "The failed grade correctly records absent quotation; it does not establish a quotation-model defect.",
    })
    review["next_steps"] = [{"target": "scenario", "action": "Clarify the work identity in the input.", "verification": "Validate the revised package and obtain fresh adoption."}]
    _save_review(data_path, review)
    render_analysis_report(data_path)
    report = path.read_text()
    assert "1 passed, 1 failed" in report
    assert "upstream book clarification" in report
    assert "not exercised" in report
    assert "fresh adoption" in report
    assert json.loads(data_path.read_text())["scenes"][1]["status"] == "failed"


@pytest.mark.parametrize("kind", ["missing", "duplicate", "unknown"])
def test_review_requires_exact_scene_coverage(tmp_path, kind):
    path = _write(tmp_path, artifact={"scenes": [_scene("first"), _scene("second")]})
    data_path = path.with_suffix(".json")
    data = json.loads(data_path.read_text())
    review = _review(data)
    if kind == "missing":
        review["scenes"].pop()
    elif kind == "duplicate":
        review["scenes"].append(review["scenes"][0])
    else:
        review["scenes"][1]["scene_id"] = "not-in-package"
    _save_review(data_path, review)
    pending = path.read_bytes()
    with pytest.raises(ValidationError, match="cover every recorded Scene exactly once"):
        render_analysis_report(data_path)
    assert path.read_bytes() == pending


@pytest.mark.parametrize(("failed", "assessment"), [(True, "credible_pass"), (False, "supported_failure")])
def test_review_cannot_relabel_recorded_grade(tmp_path, failed, assessment):
    path = _write(tmp_path, artifact={"scenes": [_scene("first", failed=failed), _scene("second")]})
    data_path = path.with_suffix(".json")
    data = json.loads(data_path.read_text())
    review = _review(data)
    review["scenes"][0]["assessment"] = assessment
    _save_review(data_path, review)
    with pytest.raises(ValidationError, match="conflicts with recorded result"):
        render_analysis_report(data_path)


def test_review_requires_evidence_grade_reliability_and_no_extra_fields(tmp_path):
    path = _write(tmp_path, artifact={"scenes": [_scene("first"), _scene("second")]})
    data_path = path.with_suffix(".json")
    data = json.loads(data_path.read_text())
    for field, value in (("evidence_refs", []), ("grade_reliability", ""), ("status", "failed")):
        review = _review(data)
        review["scenes"][0][field] = value
        _save_review(data_path, review)
        with pytest.raises(ValidationError):
            render_analysis_report(data_path)


def test_blocked_attempt_has_every_scene_not_run_and_requires_commentary(tmp_path):
    path = _write(tmp_path, execution_status="not_started")
    data_path = path.with_suffix(".json")
    data = json.loads(data_path.read_text())
    assert [scene["status"] for scene in data["scenes"]] == ["not_run", "not_run"]
    assert data["summary"]["scenes_total"] == 0
    _save_review(data_path)
    render_analysis_report(data_path)
    assert "not started" in path.read_text()
    assert "not run" in path.read_text()


def test_partial_observation_does_not_claim_missing_scene_never_ran(tmp_path):
    path = _write(tmp_path, artifact={"scenes": [_scene("first")]}, execution_status="interrupted")
    data_path = path.with_suffix(".json")
    data = json.loads(data_path.read_text())
    assert [scene["status"] for scene in data["scenes"]] == ["passed", "incomplete"]
    assert data["summary"]["scenes_total"] == 1
    assert "Incomplete observations do not establish which paths ran" in path.read_text()
    review = _review(data)
    review["scenes"][1]["assessment"] = "credible_pass"
    _save_review(data_path, review)
    with pytest.raises(ValidationError):
        render_analysis_report(data_path)


def test_ungraded_scene_retains_observation_without_invented_judgment(tmp_path):
    artifact = {"scenes": [_scene("first"), {
        "scene_id": "second", "ground_truth_result": "not_applicable", "structural_findings": [],
    }]}
    path = _write(tmp_path, artifact=artifact)
    data_path = path.with_suffix(".json")
    data = json.loads(data_path.read_text())
    assert data["scenes"][1]["status"] == "ungraded"
    assert data["summary"]["judgments_total"] == 1
    _save_review(data_path)
    render_analysis_report(data_path)
    assert "1 ungraded" in path.read_text()


def test_execution_failure_remains_separate_from_passing_scene_results(tmp_path):
    path = _write(tmp_path, artifact={"scenes": [_scene("first"), _scene("second")]}, execution_status="failed")
    _save_review(path.with_suffix(".json"))
    render_analysis_report(path.with_suffix(".json"))
    report = path.read_text()
    assert "Execution: **failed**" in report
    assert "2 passed, 0 failed" in report


def test_raw_evidence_stays_in_json_and_report_creation_is_unique(tmp_path):
    package = _package(tmp_path)
    log_path = package / "run.log"
    log_path.write_text("RAW_TRACEBACK_LINE\nOPENAI_API_KEY=sk-private1234567890abcdefghij\n")
    authority_before = {p.name: p.read_bytes() for p in package.glob("*.json")}
    arguments = dict(
        repository_root=tmp_path, model="openai:test", category="provider", problems=["Provider failed."],
        artifact={"scenes": [_scene("first"), _scene("second")]}, run_log_path=log_path,
        telemetry={"flushed": True, "url": "https://logfire.example/run/1", "remote_visibility": "verified"},
        timestamp="2026-09-13T12:00:00+08:00", execution_status="completed",
    )
    first = write_analysis_report(package, **arguments)
    second = write_analysis_report(package, **arguments)
    assert first != second
    assert first.with_suffix(".json").exists()
    raw = first.with_suffix(".json").read_text()
    facts = json.loads(raw)
    report = first.read_text()
    assert "RAW_TRACEBACK_LINE" in raw and "RAW_TRACEBACK_LINE" not in report
    assert "[REDACTED]" in raw and "sk-private" not in raw
    for digest in facts["evidence"]["diagnostics"]["source_hashes"].values():
        if digest:
            assert digest not in report
    assert "Open this run in Logfire" in report
    assert "Remote trace visibility: unverified" in report
    for name, original in authority_before.items():
        assert (package / name).read_bytes() == original


def test_review_can_identify_a_possible_false_positive_without_changing_pass(tmp_path):
    path = _write(tmp_path, artifact={"scenes": [_scene("first"), _scene("second")]})
    data_path = path.with_suffix(".json")
    data = json.loads(data_path.read_text())
    review = _review(data)
    review["scenes"][0].update({
        "assessment": "potential_false_positive", "confidence": "likely",
        "grade_reliability": "The observed response omitted the requested explanation; the grader checked only quotation presence.",
    })
    _save_review(data_path, review)
    render_analysis_report(data_path)
    assert "potential false positive" in path.read_text()
    assert "2 passed, 0 failed" in path.read_text()


def test_partial_grade_and_malformed_package_fields_still_produce_reviewable_facts(tmp_path):
    package = _package(tmp_path)
    (package / "ground-truth.json").write_text('{"proposals":null}')
    path = write_analysis_report(
        package, repository_root=tmp_path, model="openai:test", category="execution", problems=[],
        artifact={"scenes": [{"scene_id": "first", "grades": None}]}, execution_status="failed",
    )
    data = json.loads(path.with_suffix(".json").read_text())
    assert [scene["status"] for scene in data["scenes"]] == ["incomplete", "incomplete"]
    assert data["summary"]["judgments_total"] == 0
    assert data["evidence"]["artifact_problems"]


def test_structured_secrets_are_redacted_without_losing_authorization_basis(tmp_path):
    scene = _scene("first")
    scene["response"] = {"api_key": "private-unformatted-value", "authorization_basis": "memory_supported"}
    path = _write(tmp_path, artifact={"scenes": [scene, _scene("second")]})
    data = json.loads(path.with_suffix(".json").read_text())
    response = data["scenes"][0]["observed"]["response"]
    assert response["api_key"] == "[REDACTED]"
    assert response["authorization_basis"] == "memory_supported"


def test_book_scene_scope_remains_available_for_ground_truth_validity_review(tmp_path):
    package = _package(tmp_path)
    truth_path = package / "ground-truth.json"
    truth = json.loads(truth_path.read_text())
    facts = {"scene_id": "first", "scope": {"kind": "librarian_inferred", "supporting_evidence_ids": ["identity", "quote"]}}
    truth["book_scene_facts"] = [facts]
    truth_path.write_text(json.dumps(truth))
    path = write_analysis_report(
        package, repository_root=tmp_path, model="openai:test", category="none", problems=[],
        artifact={"scenes": [_scene("first"), _scene("second")]}, execution_status="completed",
    )
    data = json.loads(path.with_suffix(".json").read_text())
    assert {"book_scene_facts": facts} in data["scenes"][0]["expected"]
