"""Persist replay facts separately from a required, validated scenario review."""

from __future__ import annotations

import hashlib
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
    recorded_execution_diagnostics,
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
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioAssessment(StrictModel):
    goal: Text
    input_validity: Text
    ground_truth_validity: Text


class ExecutionDiagnostic(StrictModel):
    category: Literal[
        "provider_http_error", "provider_error", "model_output_error", "output_repair_exhausted",
        "usage_limit", "post_call_rejection", "application", "cancelled", "unknown",
    ]
    detail: Text
    source: Literal["recorded", "offline_validation", "manual_review"]
    confidence: Confidence
    evidence_refs: list[Reference] = Field(min_length=1, max_length=12)
    provider_status_code: int | None = Field(default=None, ge=400, le=599, strict=True)
    provider_error_kind: Literal["http", "timeout", "connection", "other"] | None = None


class SemanticFinding(StrictModel):
    kind: Literal[
        "wrong_attribution", "unsupported_claim", "missing_required_claim",
        "missing_required_context", "reviewer_false_positive", "other",
    ]
    explanation: Text
    evidence_refs: list[Reference] = Field(min_length=1, max_length=12)


class SemanticReview(StrictModel):
    """Explicit reviewer judgment; hard gates and citation presence never fill this."""

    status: Literal["unreviewed", "passed", "failed", "inconclusive"] = "unreviewed"
    findings: list[SemanticFinding] = Field(default_factory=list, max_length=20)
    evidence_refs: list[Reference] = Field(default_factory=list, max_length=12)
    scope: Text | None = None

    @model_validator(mode="after")
    def require_review_evidence(self) -> SemanticReview:
        if self.status == "unreviewed":
            if self.findings or self.evidence_refs or self.scope is not None:
                raise ValueError("unreviewed semantics cannot contain review judgments")
        elif not self.evidence_refs or self.scope is None:
            raise ValueError("semantic review requires explicit scope and evidence")
        if self.status == "passed" and self.findings:
            raise ValueError("semantic pass cannot retain findings")
        if self.status == "failed" and not self.findings:
            raise ValueError("semantic failure requires a specific finding")
        return self


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
    semantic_review: SemanticReview = Field(default_factory=SemanticReview)
    execution_findings: list[ExecutionDiagnostic] = Field(default_factory=list, max_length=12)


class NextStep(StrictModel):
    target: Literal["scenario", "application", "evaluator", "configuration", "observability", "investigation"]
    action: Text
    verification: Text


class AnalysisReview(StrictModel):
    facts_sha256: Digest | None = None
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
    execution_diagnostics: list[ExecutionDiagnostic] = Field(default_factory=list)


class AnalysisDocument(StrictModel):
    schema_version: Literal["2", "3"] = "2"
    facts_sha256: Digest | None = None
    scenario_dir: str
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
        if self.schema_version == "3":
            if self.facts_sha256 != _facts_digest(self.model_dump(mode="json")):
                raise ValueError("recorded analysis facts changed; prepare a new report from the original artifact")
            if self.review is not None and self.review.facts_sha256 != self.facts_sha256:
                raise ValueError("review identity does not match the recorded analysis facts")
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


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _facts_digest(document: dict) -> str:
    return _digest({key: value for key, value in document.items() if key not in {"review", "facts_sha256"}})


def _artifact_hash(artifact: dict | None, path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    raw = path.read_bytes()
    if artifact is not None and json.loads(raw) != artifact:
        raise ValueError("artifact path does not contain the supplied run")
    return hashlib.sha256(raw).hexdigest()


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
    "actual_outcome", "curation_status", "source_hashes_before", "source_hashes_after",
    "session_turn_release_sources", "existing_memories_unchanged", "retry", "trace_id", "events",
    "semantic_review_required", "late_provenance_findings",
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
    raw_observations = (artifact or {}).get("scenes", ())
    indexed_observations = [
        (index, scene) for index, scene in enumerate(raw_observations)
        if isinstance(scene, dict) and isinstance(scene.get("scene_id"), str)
    ] if isinstance(raw_observations, (list, tuple)) else []
    observations = [scene for _, scene in indexed_observations]
    proposals = records(ground_truth.get("proposals"))
    scene_ids = list(dict.fromkeys(scene["scene_id"] for scene in planned))
    planned_ids = set(scene_ids)
    for record in [*proposals, *observations]:
        if isinstance(record.get("scene_id"), str) and record["scene_id"] not in scene_ids:
            scene_ids.append(record["scene_id"])
    by_id = {scene["scene_id"]: scene for scene in observations}
    observation_indices = {scene["scene_id"]: index for index, scene in indexed_observations}
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
                    raise ValueError("artifact Scene is not present in the scenario")
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
                {key: exchange[key] for key in (
                    "sequence", "role", "stage", "status", "failure_code", "failure_category",
                    "provider_status_code", "provider_error_kind", "output", "tool_exchanges",
                ) if key in exchange}
                for exchange in records(observed["agent_exchanges"])
            ]
        facts.append({
            "scene_id": scene_id, "order": order, "status": status, **counts,
            "expected": expected, "observed": decisive, "failures": failures,
            "evidence_refs": [f"scenes[{order - 1}].expected", f"scenes[{order - 1}].observed"],
            "execution_diagnostics": recorded_execution_diagnostics(observed, observation_indices[scene_id]) if observed else [],
        })
    summary = summarize_artifact({"scenes": valid_observations}) if valid_observations else {
        "scenes_total": 0, "scenes_passed": 0, "scenes_failed": 0, "scenes_ungraded": 0,
        "judgments_total": 0, "judgments_passed": 0, "judgments_failed": 0,
        "failures": [], "execution_failures": [],
    }
    return facts, summary, errors


def write_analysis_report(
    scenario_dir: Path,
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
    report_dir: Path | None = None,
) -> Path:
    """Save review-ready facts and an initial Markdown report for every attempt."""
    scenario_dir = scenario_dir.resolve()
    stamp = timestamp or datetime.now().astimezone().isoformat(timespec="seconds")
    safe_stamp = re.sub(r"[^A-Za-z0-9_+-]", "", stamp)[:60] or "undated"
    destination = report_dir.resolve() if report_dir else scenario_dir
    destination.mkdir(parents=True, exist_ok=True)
    data_path = destination / f"analysis-report-{safe_stamp}-{uuid4().hex[:8]}.json"
    scenes, summary, errors = _scene_facts(
        _read_json(scenario_dir / "backstory.json"), _read_json(scenario_dir / "ground-truth.json"),
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
        "artifact_sha256": _artifact_hash(artifact, output_path),
        "run_log_path": str(run_log_path.resolve()) if run_log_path else None,
        "scenario_sources": {name: str(scenario_dir / name) for name in ("backstory.json", "ground-truth.json", "ground-truth-adoption.json")},
        "run_identity": {key: artifact[key] for key in (
            "run_id", "trace_id", "dataset_version", "system_variant", "objective_id", "objective_ids", "ground_truth_status",
        ) if artifact and key in artifact},
        "diagnostics": collect_diagnostic_evidence(scenario_dir, repository_root, run_log_path),
        "artifact_problems": errors,
    }
    facts = _redact({
        "schema_version": "3",
        "scenario_dir": str(scenario_dir), "created_at": stamp, "model": model,
        "execution_status": execution_status, "category": category, "problems": problems,
        "summary": summary, "scenes": scenes, "telemetry": transport, "evidence": evidence, "review": None,
    })
    facts["scenes"] = [SceneFacts.model_validate(scene).model_dump(mode="json") for scene in facts["scenes"]]
    facts["facts_sha256"] = _facts_digest(facts)
    document = AnalysisDocument.model_validate(facts)
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
    artifact_hash = document.evidence.get("artifact_sha256")
    if artifact_hash:
        source = Path(document.evidence["artifact_path"])
        if not source.is_file() or _artifact_hash(None, source) != artifact_hash:
            raise ValueError("original evaluation artifact changed or is unavailable")
    if require_review and document.review is None:
        raise ValueError("analysis review is required before finalizing the report")
    review = document.review
    counts = document.summary
    report = ["# Scenario analysis", "", "## Outcome", "",
        f"Scenario: `{_text(Path(document.scenario_dir).name)}`. Model API: `{_text(document.model)}`.", "",
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
    report.extend(["Semantic status is an explicit review judgment, independent of the recorded hard grades.", ""])
    if document.schema_version == "2":
        report.extend(["This older report has no verified facts/review identity binding; its saved review remains readable.", ""])
    report.extend(["## Scene results", "", "| Scene | Expected behavior | Observed behavior | Recorded result | Judgments passed | Assessment | Semantic review |", "| --- | --- | --- | --- | --- | --- | --- |"])
    for scene in document.scenes:
        item = reviews.get(scene.scene_id)
        assessment = _label(item.assessment) if item else "Analysis pending"
        expected = _text(item.expected_behavior).replace("|", "\\|") if item else "Analysis pending"
        observed = _text(item.observed_behavior).replace("|", "\\|") if item else "Analysis pending"
        semantic_status = item.semantic_review.status if item else "unreviewed"
        report.append(f"| {_text(scene.scene_id).replace('|', '\\|')} | {expected} | {observed} | {_label(scene.status)} | {scene.judgments_passed}/{scene.judgments_total} | {assessment} | {semantic_status} |")
    if not document.scenes:
        report.append("| No readable Scene definitions | unavailable | unavailable | incomplete | 0/0 | " + ("inconclusive" if review else "Analysis pending") + " | unreviewed |")
    report.extend(["", "## Scene analysis", ""])
    if not document.scenes:
        report.extend(["No Scene definitions could be read. Behavior coverage remains unknown.", ""])
    for scene in document.scenes:
        report.extend([f"### {_text(scene.scene_id)}", "", f"Recorded result: **{_label(scene.status)}**.", ""])
        item = reviews.get(scene.scene_id)
        for diagnostic in [*scene.execution_diagnostics, *(item.execution_findings if item else [])]:
            report.extend([
                f"Execution evidence ({_label(diagnostic.category)}; {_label(diagnostic.source)}; {diagnostic.confidence}): {_text(diagnostic.detail)}",
                "Evidence: " + "; ".join(_text(ref) for ref in diagnostic.evidence_refs) + ".", "",
            ])
        if item is None:
            report.extend(["Analysis pending. Review the expected behavior, the observed path, and whether the grade supports the Scene's goal.", ""])
            continue
        report.extend([
            f"{_text(item.interpretation)} Assessment: {_label(item.assessment)}. Confidence: {item.confidence}.", "",
            f"Grade reliability: {_text(item.grade_reliability)}", "",
            f"Next step: {_text(item.next_step)}", "",
        ])
        semantic = item.semantic_review
        report.extend([f"Semantic review: **{semantic.status}**." + (f" Scope: {_text(semantic.scope)}" if semantic.scope else ""), ""])
        if semantic.evidence_refs:
            report.extend(["Semantic evidence: " + "; ".join(_text(ref) for ref in semantic.evidence_refs) + ".", ""])
        for finding in semantic.findings:
            report.extend([
                f"{_label(finding.kind).capitalize()}: {_text(finding.explanation)}",
                "Evidence: " + "; ".join(_text(ref) for ref in finding.evidence_refs) + ".", "",
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


__all__ = [
    "AnalysisDocument", "AnalysisReview", "ExecutionDiagnostic", "NextStep", "ScenarioAssessment",
    "SceneReview", "SemanticFinding", "SemanticReview", "render_analysis_report", "write_analysis_report",
]
