"""Persist replay facts separately from a required, validated scenario review."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .scenario_diagnostics import (
    _read_json,
    _safe_text,
    collect_diagnostic_evidence,
    summarize_artifact,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1600)]
Reference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]
Confidence = Literal["confirmed", "likely", "unresolved"]
SceneStatus = Literal["passed", "failed", "ungraded", "not_run", "incomplete"]
Assessment = Literal[
    "credible_pass", "pass_with_limitations", "potential_false_positive",
    "supported_failure", "potential_false_negative", "inconclusive", "not_exercised",
]
ExecutionStatus = Literal["unknown", "not_started", "completed", "failed", "timed_out", "interrupted"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioAssessment(StrictModel):
    goal: Text
    input_validity: Text
    ground_truth_validity: Text


class SceneReview(StrictModel):
    scene_id: Text
    expected_behavior: Text
    observed_behavior: Text
    interpretation: Text
    assessment: Assessment
    confidence: Confidence
    evidence_refs: list[Reference] = Field(min_length=1, max_length=12)
    grade_reliability: Text
    next_step: Text


class NextStep(StrictModel):
    target: Literal["scenario", "application", "evaluator", "configuration", "observability", "investigation"]
    action: Text
    verification: Text


class AnalysisReview(StrictModel):
    verdict: Text
    scenario_assessment: ScenarioAssessment
    confidence: Confidence
    scenes: list[SceneReview]
    next_steps: list[NextStep] = Field(max_length=12)


class SceneFacts(StrictModel):
    scene_id: str
    order: int
    status: SceneStatus
    judgments_total: int = Field(ge=0)
    judgments_passed: int = Field(ge=0)
    judgments_failed: int = Field(ge=0)
    expected: list[dict[str, Any]]
    observed: dict[str, Any]
    failures: list[dict[str, Any]]
    evidence_refs: list[str]


class AnalysisDocument(StrictModel):
    schema_version: Literal["1"] = "1"
    package_dir: str
    created_at: str
    model: str
    execution_status: ExecutionStatus
    category: str
    problems: list[str]
    summary: dict[str, Any]
    scenes: list[SceneFacts]
    telemetry: dict[str, Any]
    evidence: dict[str, Any]
    review: AnalysisReview | None = None

    @model_validator(mode="after")
    def validate_review_coverage(self) -> AnalysisDocument:
        facts = {scene.scene_id: scene for scene in self.scenes}
        if len(facts) != len(self.scenes):
            raise ValueError("recorded Scene IDs must be unique")
        if self.review is None:
            return self
        reviews = {scene.scene_id: scene for scene in self.review.scenes}
        if len(reviews) != len(self.review.scenes) or set(reviews) != set(facts):
            raise ValueError("review must cover every recorded Scene exactly once")
        permitted = {
            "passed": {"credible_pass", "pass_with_limitations", "potential_false_positive", "inconclusive"},
            "failed": {"supported_failure", "potential_false_negative", "inconclusive", "not_exercised"},
            "ungraded": {"inconclusive", "not_exercised"},
            "not_run": {"not_exercised"},
            "incomplete": {"inconclusive", "not_exercised"},
        }
        for scene_id, review in reviews.items():
            if review.assessment not in permitted[facts[scene_id].status]:
                raise ValueError(f"review assessment conflicts with recorded result for Scene {scene_id}")
        return self


_EXPECTED_KEYS = (
    "proposal_id", "objective_id", "expected_outcomes", "prohibited_outcomes", "exact_spans",
    "evidence", "prop_relevance",
    "capture", "curation", "surfacing", "grounding", "connection", "book_expectation", "pairing",
)
_OBSERVED_KEYS = (
    "ground_truth_result", "hard_gate_pass", "hard_failures", "grades", "grade", "structural_findings",
    "gate_failures", "execution_error", "input_line", "context_resolution", "actual_capture_label",
    "actual_nomination", "capture", "stored_text", "stored_record_count", "response", "reply",
    "release_source", "boundary_decision", "route_called", "routed_ceiling", "routed_work_id",
    "routed_book_version_id", "routed_passage_ids", "boundary_support_memory_ids",
    "boundary_support_evidence", "grounding_calls", "released_evidence_ids", "provenance_verdicts",
    "semantic_spoiler_results", "source_immutable", "input_immutable", "turns",
    "session_turn_release_sources", "existing_memories_unchanged", "retry", "trace_id", "events",
)


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return _safe_text(value, 20000)
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if re.search(r"(?i)(?:api[_-]?key|access[_-]?token|secret[_-]?key|logfire[_-]?token)$|^authorization$", str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def _scene_facts(backstory: dict, ground_truth: dict, artifact: dict | None, execution_status: str) -> tuple[list[dict], dict, list[str]]:
    def records(value: Any) -> list[dict]:
        return [item for item in value if isinstance(item, dict)] if isinstance(value, (list, tuple)) else []

    planned = [scene for scene in records(backstory.get("scenes")) if isinstance(scene.get("scene_id"), str)]
    planned.sort(key=lambda scene: scene.get("order") if isinstance(scene.get("order"), int) else 0)
    observations = [scene for scene in records((artifact or {}).get("scenes")) if isinstance(scene.get("scene_id"), str)]
    proposals = records(ground_truth.get("proposals"))
    scene_ids = list(dict.fromkeys(scene["scene_id"] for scene in planned))
    planned_ids = set(scene_ids)
    for record in [*proposals, *observations]:
        if isinstance(record.get("scene_id"), str) and record["scene_id"] not in scene_ids:
            scene_ids.append(record["scene_id"])
    by_id = {scene["scene_id"]: scene for scene in observations}
    duplicate_ids = {scene["scene_id"] for scene in observations if sum(item["scene_id"] == scene["scene_id"] for item in observations) > 1}
    facts, valid_observations, errors = [], [], []
    for order, scene_id in enumerate(scene_ids, 1):
        observed = by_id.get(scene_id)
        status = "not_run" if execution_status == "not_started" else "incomplete"
        counts = {"judgments_total": 0, "judgments_passed": 0, "judgments_failed": 0}
        failures = []
        if observed is not None:
            try:
                if planned_ids and scene_id not in planned_ids:
                    raise ValueError("artifact Scene is not present in the package")
                if scene_id in duplicate_ids:
                    raise ValueError("artifact has duplicate Scene observations")
                result = summarize_artifact({"scenes": [observed]})
                status = "failed" if result["scenes_failed"] else "ungraded" if result["scenes_ungraded"] else "passed"
                counts = {key: result[key] for key in counts}
                failures = result["failures"]
                valid_observations.append(observed)
            except (TypeError, ValueError) as error:
                status = "incomplete"
                errors.append(f"{scene_id}: {_safe_text(error)}")
        expected = [
            {key: proposal[key] for key in _EXPECTED_KEYS if key in proposal and proposal[key] is not None}
            for proposal in proposals if proposal.get("scene_id") == scene_id
        ]
        expected.extend(
            {"book_scene_facts": scene}
            for scene in records(ground_truth.get("book_scene_facts")) if scene.get("scene_id") == scene_id
        )
        if not expected and observed:
            expected = [{key: observed[key] for key in ("expected", "expected_capture") if key in observed}]
            expected = [item for item in expected if item]
        decisive = {key: observed[key] for key in _OBSERVED_KEYS if key in observed} if observed else {}
        if observed and observed.get("agent_exchanges"):
            decisive["agent_activity"] = [
                {key: exchange[key] for key in ("role", "stage", "status", "failure_code", "output", "tool_exchanges") if key in exchange}
                for exchange in records(observed["agent_exchanges"])
            ]
        facts.append({
            "scene_id": scene_id, "order": order, "status": status, **counts,
            "expected": expected, "observed": decisive, "failures": failures,
            "evidence_refs": [f"scenes[{order - 1}].expected", f"scenes[{order - 1}].observed"],
        })
    summary = summarize_artifact({"scenes": valid_observations}) if valid_observations else {
        "scenes_total": 0, "scenes_passed": 0, "scenes_failed": 0, "scenes_ungraded": 0,
        "judgments_total": 0, "judgments_passed": 0, "judgments_failed": 0,
        "failures": [], "execution_failures": [],
    }
    return facts, summary, errors


def write_analysis_report(
    package_dir: Path,
    *,
    repository_root: Path,
    model: str,
    category: str,
    problems: list[str],
    artifact: dict | None = None,
    logfire_url: str | None = None,
    output_path: Path | None = None,
    run_log_path: Path | None = None,
    timestamp: str | None = None,
    execution_status: ExecutionStatus = "unknown",
    telemetry: dict | None = None,
) -> Path:
    """Save review-ready facts and an initial Markdown report for every attempt."""
    package_dir = package_dir.resolve()
    stamp = timestamp or datetime.now().astimezone().isoformat(timespec="seconds")
    safe_stamp = re.sub(r"[^A-Za-z0-9_+-]", "", stamp)[:60] or "undated"
    data_path = package_dir / f"analysis-report-{safe_stamp}-{uuid4().hex[:8]}.json"
    scenes, summary, errors = _scene_facts(
        _read_json(package_dir / "backstory.json"), _read_json(package_dir / "ground-truth.json"),
        artifact, execution_status,
    )
    transport = {key: (telemetry or {})[key] for key in (
        "url", "trace_id", "span_id", "flushed", "remote_visibility", "verification_evidence",
    ) if key in (telemetry or {})}
    transport["url"] = logfire_url or transport.get("url")
    if transport.get("remote_visibility") != "verified" or not transport.get("verification_evidence"):
        transport["remote_visibility"] = "unverified"
    evidence = {
        "artifact_path": str(output_path.resolve()) if output_path else None,
        "run_log_path": str(run_log_path.resolve()) if run_log_path else None,
        "package_sources": {name: str(package_dir / name) for name in ("backstory.json", "ground-truth.json", "ground-truth-adoption.json")},
        "run_identity": {key: artifact[key] for key in (
            "run_id", "trace_id", "dataset_version", "system_variant", "objective_id", "objective_ids", "ground_truth_status",
        ) if artifact and key in artifact},
        "diagnostics": collect_diagnostic_evidence(package_dir, repository_root, run_log_path),
        "artifact_problems": errors,
    }
    document = AnalysisDocument.model_validate(_redact({
        "package_dir": str(package_dir), "created_at": stamp, "model": model,
        "execution_status": execution_status, "category": category, "problems": problems,
        "summary": summary, "scenes": scenes, "telemetry": transport, "evidence": evidence, "review": None,
    }))
    with data_path.open("x", encoding="utf-8") as stream:
        stream.write(document.model_dump_json(indent=2) + "\n")
    return render_analysis_report(data_path, require_review=False)


def _text(value: object) -> str:
    return _safe_text(value, 2000).replace("\n", " ")


def _label(value: str) -> str:
    return value.replace("_", " ")


def render_analysis_report(data_path: Path, *, require_review: bool = True) -> Path:
    """Render only saved facts and validated review prose; never revise grades."""
    document = AnalysisDocument.model_validate_json(data_path.read_bytes())
    if require_review and document.review is None:
        raise ValueError("analysis review is required before finalizing the report")
    review = document.review
    counts = document.summary
    report = ["# Scenario analysis", "", "## Outcome", "",
        f"Package: `{_text(Path(document.package_dir).name)}`. Model API: `{_text(document.model)}`.", "",
        f"Report generated at: `{_text(document.created_at)}`.", "",
        f"Execution: **{_label(document.execution_status)}**. Recorded results: "
        f"**{counts['scenes_passed']} passed, {counts['scenes_failed']} failed, {counts['scenes_ungraded']} ungraded**. "
        f"Deterministic judgments: **{counts['judgments_passed']}/{counts['judgments_total']} passed**.", "",
    ]
    missing = sum(scene.status in {"not_run", "incomplete"} for scene in document.scenes)
    if missing:
        noun, verb = ("Scene", "has") if missing == 1 else ("Scenes", "have")
        report.extend([f"{missing} {noun} {verb} no complete recorded result. Incomplete observations do not establish which paths ran.", ""])
    if document.problems:
        report.extend(["Reported problem: " + " ".join(_safe_text(problem.splitlines()[0], 300) for problem in document.problems[:3] if problem), ""])
    if review:
        report.extend([_text(review.verdict) + f" Confidence: {review.confidence}.", "",
            f"Scenario goal: {_text(review.scenario_assessment.goal)}", "",
            f"Input validity: {_text(review.scenario_assessment.input_validity)} "
            f"Ground truth validity: {_text(review.scenario_assessment.ground_truth_validity)}", ""])
    else:
        report.extend(["**Analysis pending.** The recorded results below have not yet been reviewed for meaning or grade reliability.", ""])
    reviews = {scene.scene_id: scene for scene in review.scenes} if review else {}
    report.extend(["## Scene results", "", "| Scene | Expected behavior | Observed behavior | Recorded result | Judgments passed | Assessment |", "| --- | --- | --- | --- | --- | --- |"])
    for scene in document.scenes:
        item = reviews.get(scene.scene_id)
        assessment = _label(item.assessment) if item else "Analysis pending"
        expected = _text(item.expected_behavior).replace("|", "\\|") if item else "Analysis pending"
        observed = _text(item.observed_behavior).replace("|", "\\|") if item else "Analysis pending"
        report.append(f"| {_text(scene.scene_id).replace('|', '\\|')} | {expected} | {observed} | {_label(scene.status)} | {scene.judgments_passed}/{scene.judgments_total} | {assessment} |")
    if not document.scenes:
        report.append("| No readable Scene definitions | unavailable | unavailable | incomplete | 0/0 | " + ("inconclusive" if review else "Analysis pending") + " |")
    report.extend(["", "## Scene analysis", ""])
    if not document.scenes:
        report.extend(["No Scene definitions could be read. Behavior coverage remains unknown.", ""])
    for scene in document.scenes:
        report.extend([f"### {_text(scene.scene_id)}", "", f"Recorded result: **{_label(scene.status)}**.", ""])
        item = reviews.get(scene.scene_id)
        if item is None:
            report.extend(["Analysis pending. Review the expected behavior, the observed path, and whether the grade supports the Scene's goal.", ""])
            continue
        report.extend([
            f"{_text(item.interpretation)} Assessment: {_label(item.assessment)}. Confidence: {item.confidence}.", "",
            f"Grade reliability: {_text(item.grade_reliability)}", "",
            f"Next step: {_text(item.next_step)}", "",
        ])
    report.extend(["## Next steps", ""])
    if review is None:
        report.extend(["Review every Scene and fill only the saved JSON's `review` field, then validate and render the completed analysis.", ""])
    elif not review.next_steps:
        report.extend(["No corrective action identified.", ""])
    else:
        for index, step in enumerate(review.next_steps, 1):
            report.append(f"{index}. {_label(step.target).capitalize()}: {_text(step.action)} Verification: {_text(step.verification)}")
        report.append("")
    report.extend(["## Evidence", "", f"[Analysis data and detailed evidence](<{data_path.resolve()}>)", ""])
    for label, key in (("Evaluation artifact", "artifact_path"), ("Run log", "run_log_path")):
        if document.evidence.get(key):
            report.extend([f"[{label}](<{_text(document.evidence[key])}>)", ""])
    if document.telemetry.get("url"):
        report.extend([f"[Open this run in Logfire](<{_text(document.telemetry['url'])}>)", ""])
    visible = document.telemetry.get("remote_visibility") == "verified" and document.telemetry.get("verification_evidence")
    report.extend([
        "Remote trace visibility: " + ("verified. " + _text(document.telemetry["verification_evidence"]) if visible else "unverified. An export flush or URL does not establish remote visibility."), "",
        "Source hashes, bounded logs, and Git context are in the linked analysis data. Recorded grades remain separate from review judgments.", "",
    ])
    path = data_path.with_suffix(".md")
    path.write_text("\n".join(report), encoding="utf-8")
    return path


__all__ = ["AnalysisDocument", "AnalysisReview", "NextStep", "ScenarioAssessment", "SceneReview", "render_analysis_report", "write_analysis_report"]
