"""Keep report-facing results compact while preserving the original evidence offline."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import tarfile
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from .scenario_analysis import AnalysisDocument


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class ArchivedFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha256: str
    format: Literal["json", "text", "base64"]
    data: Any
    source_text: str | None = None

    @classmethod
    def capture(cls, raw: bytes, *, json_file: bool = False) -> ArchivedFile:
        if json_file:
            data = json.loads(raw)
            return cls(sha256=_sha(raw), format="json", data=data,
                       source_text=raw.decode("utf-8") if _json_bytes(data) != raw else None)
        try:
            return cls(sha256=_sha(raw), format="text", data=raw.decode("utf-8"))
        except UnicodeDecodeError:
            return cls(sha256=_sha(raw), format="base64", data=base64.b64encode(raw).decode("ascii"))

    def restore(self) -> bytes:
        if self.format == "json":
            raw = self.source_text.encode("utf-8") if self.source_text is not None else _json_bytes(self.data)
            if json.loads(raw) != self.data:
                raise ValueError("archived JSON data disagrees with original serialization")
        elif self.format == "text":
            raw = self.data.encode("utf-8")
        else:
            raw = base64.b64decode(self.data, validate=True)
        if _sha(raw) != self.sha256:
            raise ValueError("archived file hash does not match its contents")
        return raw


def _archive(path: Path, raw: bytes) -> dict:
    return ArchivedFile.capture(raw, json_file=path.suffix == ".json").model_dump(mode="json", exclude_none=True)


def _files(directory: Path) -> list[Path]:
    entries = list(directory.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise ValueError("result directories cannot contain symlinks")
    if any(not path.is_file() and not path.is_dir() for path in entries):
        raise ValueError("result directory contains a special file")
    return sorted(path for path in entries if path.is_file())


def _directory(path: Path) -> Path:
    if path.is_symlink():
        raise ValueError("result directory cannot be a symlink")
    directory = path.resolve(strict=True)
    if not directory.is_dir() or directory.parent.name != "results":
        raise ValueError("bundle a direct run directory inside results/")
    return directory


def _semantic_counts(document: AnalysisDocument) -> dict[str, int]:
    return dict(Counter(scene.semantic_review.status for scene in document.review.scenes))


def _findings(document: AnalysisDocument) -> list[dict]:
    return [
        {"scene_id": scene.scene_id, "explanation": finding.explanation,
         "evidence_refs": list(finding.evidence_refs)}
        for scene in document.review.scenes if scene.semantic_review.status == "failed"
        for finding in scene.semantic_review.findings
    ]


def _validate(bundle: dict) -> tuple[AnalysisDocument, bytes | None]:
    if bundle.get("schema_version") != 1:
        raise ValueError("unsupported result bundle schema")
    evidence = bundle["evidence"]
    analysis = ArchivedFile.model_validate(evidence["analysis"]).restore()
    document = AnalysisDocument.model_validate_json(analysis)
    if document.schema_version != "3" or document.review is None:
        raise ValueError("bundling requires a reviewed version 3 analysis")
    evaluation = ArchivedFile.model_validate(evidence["evaluation"]).restore() if evidence["evaluation"] else None
    expected_hash = document.evidence.get("artifact_sha256")
    if (evaluation is not None and _sha(evaluation) != expected_hash) or (expected_hash and evaluation is None):
        raise ValueError("evaluation does not match the original analysis artifact hash")
    for item in [*evidence["inputs"].values(), *bundle["diagnostics"].values()]:
        ArchivedFile.model_validate(item).restore()
    hashes = document.evidence.get("diagnostics", {}).get("source_hashes", {})
    for name, expected in hashes.items():
        if expected and name not in evidence["inputs"]:
            raise ValueError(f"missing original input snapshot for {name}")
    for name, archived in evidence["inputs"].items():
        if archived["sha256"] != hashes.get(name):
            raise ValueError(f"input snapshot does not match recorded hash for {name}")
    expected_outcomes = {"automated": document.summary, "response_review": _semantic_counts(document)}
    if bundle["outcomes"] != expected_outcomes or bundle["findings"] != _findings(document):
        raise ValueError("bundle outcomes disagree with the original analysis")
    if bundle["run"]["model"] != document.model or bundle["run"]["execution_status"] != document.execution_status:
        raise ValueError("bundle model or execution status disagrees with the original analysis")
    evaluation_data = json.loads(evaluation) if evaluation is not None else {}
    if bundle["run"]["scenario_id"] != Path(document.scenario_dir).name:
        raise ValueError("bundle Scenario identity disagrees with the original analysis")
    if evaluation_data.get("run_id") and bundle["run"]["id"] != evaluation_data["run_id"]:
        raise ValueError("bundle run identity disagrees with the original evaluation")
    if bundle["run"]["observed_agents"] != sorted(_agents(evaluation_data)):
        raise ValueError("bundle observed agents disagree with the original evaluation")
    visibility = bundle["diagnostics"].get("remote-visibility.json")
    verified = json.loads(ArchivedFile.model_validate(visibility).restore()) if visibility else None
    if bundle["telemetry"] != _telemetry(document, evaluation_data, verified):
        raise ValueError("bundle telemetry disagrees with the recorded visibility evidence")
    facts = {scene.scene_id: scene for scene in document.scenes}
    reviews = {scene.scene_id: scene for scene in document.review.scenes}
    if [row["scene_id"] for row in bundle["scenes"]] != list(facts):
        raise ValueError("bundle must retain every original Scene in order")
    for row in bundle["scenes"]:
        fact, review = facts[row["scene_id"]], reviews[row["scene_id"]]
        automated = {"status": fact.status, "judgments_passed": fact.judgments_passed,
                     "judgments_total": fact.judgments_total}
        if (row["automated_result"] != automated or row["response_review"] != review.semantic_review.status
                or row["assessment"] != review.assessment):
            raise ValueError("Scene outcomes disagree with the original analysis")
    return document, evaluation


def _agents(value: Any) -> set[str]:
    if isinstance(value, list):
        return set().union(*(_agents(item) for item in value)) if value else set()
    if not isinstance(value, dict):
        return set()
    found = {exchange["role"] for exchange in value.get("agent_exchanges", []) if exchange.get("role")}
    return found.union(*(_agents(item) for item in value.values()))


def _telemetry(document: AnalysisDocument, evaluation: dict, verified: dict | None) -> dict:
    telemetry = dict(document.telemetry)
    if verified is not None:
        if not verified.get("verified_at") or not verified.get("method"):
            raise ValueError("remote visibility evidence lacks verification date or method")
        if evaluation.get("trace_id") and verified.get("trace_id") != evaluation["trace_id"]:
            raise ValueError("remote visibility evidence belongs to another trace")
        telemetry.update(verified)
        telemetry.update(url=verified.get("evaluation_url", telemetry.get("url")),
                         remote_visibility="verified", verification_evidence=verified["method"])
    return telemetry


def _make_bundle(directory: Path, original: dict[Path, bytes]) -> dict:
    analyses = [path for path in original if path.match("analysis-report-*.json")]
    if len(analyses) != 1:
        raise ValueError("expected exactly one original analysis-report-*.json")
    analysis_path = analyses[0]
    document = AnalysisDocument.model_validate_json(original[analysis_path])
    if document.schema_version != "3" or document.review is None:
        raise ValueError("bundling requires a reviewed version 3 analysis")
    evaluation_path = None
    if document.evidence.get("artifact_sha256"):
        source = document.evidence.get("artifact_path")
        evaluation_path = Path(source).resolve() if source else None
        if (evaluation_path is None or not evaluation_path.is_relative_to(directory)
                or evaluation_path not in original):
            raise ValueError("original evaluation artifact must be inside this run directory")
    evaluation = json.loads(original[evaluation_path]) if evaluation_path else {}
    inputs = {}
    used = {analysis_path, evaluation_path}
    duplicate_paths = []
    for path, raw in original.items():
        if path.parent.name == "scene-transcripts" and path.suffix == ".json":
            if json.loads(raw) in evaluation.get("scenes", []):
                used.add(path)
                duplicate_paths.append(str(path.relative_to(directory)))
    source_hashes = document.evidence.get("diagnostics", {}).get("source_hashes", {})
    for name in ("backstory.json", "ground-truth.json", "ground-truth-adoption.json"):
        if not source_hashes.get(name):
            continue
        path = directory / "inputs" / name
        if path in original:
            raw = original[path]
            used.add(path)
        else:
            source = document.evidence.get("scenario_sources", {}).get(name)
            if not source:
                raise ValueError(f"no original input source for {name}")
            path = Path(source)
            if path.is_symlink():
                raise ValueError("input source cannot be a symlink")
            if not path.is_file():
                raise ValueError(f"original input snapshot is unavailable for {name}")
            raw = path.read_bytes()
        if _sha(raw) != source_hashes.get(name):
            raise ValueError(f"input snapshot does not match recorded hash for {name}")
        inputs[name] = _archive(path, raw)
    manifest = json.loads(original.get(directory / "manifest.json", b"{}"))
    configuration = json.loads(original[directory / "effective-configuration.json"]) if directory / "effective-configuration.json" in original else None
    run_summary = json.loads(original.get((evaluation_path.parent if evaluation_path else analysis_path.parent) / "summary.json", b"{}"))
    reviews = {scene.scene_id: scene for scene in document.review.scenes} if document.review else {}
    rows = []
    for fact in document.scenes:
        if fact.scene_id not in reviews:
            raise ValueError("completed review is required for every Scene")
        review = reviews[fact.scene_id]
        rows.append({"scene_id": fact.scene_id, "expected": review.expected_behavior,
                     "observed": review.observed_behavior,
                     "automated_result": {"status": fact.status, "judgments_passed": fact.judgments_passed,
                                          "judgments_total": fact.judgments_total},
                     "response_review": review.semantic_review.status, "assessment": review.assessment,
                     "key_learning": review.grade_reliability})
    return {
        "schema_version": 1,
        "run": {"id": evaluation.get("run_id", directory.name),
                "scenario_id": Path(document.scenario_dir).name,
                "title": Path(document.scenario_dir).name.split("--")[0].replace("-", " ").capitalize(),
                "model": document.model, "purpose": manifest.get("purpose", "unspecified"),
                "configuration": configuration,
                "code_revision": document.evidence.get("diagnostics", {}).get("git", {}).get("revision"),
                "objective_ids": evaluation.get("objective_ids", [evaluation["objective_id"]] if evaluation.get("objective_id") else []),
                "execution_status": document.execution_status,
                "dates": {"started_at": run_summary.get("started_at", manifest.get("created_at")),
                          "finished_at": run_summary.get("finished_at", document.created_at)},
                "observed_agents": sorted(_agents(evaluation))},
        "outcomes": {"automated": document.summary, "response_review": _semantic_counts(document)},
        "scenes": rows, "findings": _findings(document),
        "report_points": [document.review.verdict],
        "slide_points": [finding["explanation"] for finding in _findings(document)],
        "worked_examples": [],
        "limitations": ["One attempt does not establish repeatability.",
                        "LLM-review is a separate saved judgment; automated grades are unchanged."],
        "telemetry": _telemetry(document, evaluation, json.loads(original[directory / "remote-visibility.json"])
                                if directory / "remote-visibility.json" in original else None),
        "evidence": {"evaluation": _archive(evaluation_path, original[evaluation_path]) if evaluation_path else None,
                     "analysis": _archive(analysis_path, original[analysis_path]), "inputs": inputs,
                     "omitted_duplicate_paths": duplicate_paths},
        "diagnostics": {str(path.relative_to(directory)): _archive(path, raw)
                        for path, raw in original.items() if path not in used},
    }


def _summary(bundle: dict) -> str:
    def text(value: Any) -> str:
        return " ".join(str(value).split()).replace("|", "\\|")

    run, outcomes = bundle["run"], bundle["outcomes"]
    automatic, reviewed = outcomes["automated"], outcomes["response_review"]
    lines = [f"# {text(run['title'])}", "",
             f"{text(run['purpose']).capitalize()} run. {text(run['dates']['finished_at'])}. Model `{text(run['model'])}`.", "",
             f"Execution status: **{text(run['execution_status'])}**.", "",
             f"Automated results: **{automatic['scenes_passed']}/{automatic['scenes_total']} Scenes passed**. "
             f"LLM-review: **{reviewed.get('passed', 0)}/{automatic['scenes_total']} Scenes passed** "
             f"({', '.join(f'{count} {status}' for status, count in reviewed.items())}).", "",
             "## How to read the results", "",
             "**Automated** reports the Scenario runner's implemented checks, such as quotation accuracy "
             "and permitted evidence. A pass means those checks passed. The checks may cover only part "
             "of the reader's request.", "",
             "**LLM-review** is the coding assistant's assessment of the released answer against the reader's "
             "full request and the approved Scenario expectations. The assistant reviews the saved answer, "
             "supporting evidence, and relevant agent exchanges after the run. It is separate from Linger's "
             "five runtime agents. No additional grader model is called, and this is not independent human validation.", "",
             "For LLM-review, **passed** means the review found the expectations met within its scope. "
             "**Failed** means it found a material omission or violation. **Inconclusive** means the evidence "
             "did not support a decision. **Unreviewed** means no response assessment was recorded. "
             "LLM-review does not change the automated result.", ""]
    if bundle["telemetry"].get("url"):
        lines.extend([f"[Open the traces in Logfire](<{bundle['telemetry']['url']}>) "
                      f"(visibility {text(bundle['telemetry'].get('remote_visibility', 'unverified'))}).", ""])
    lines.extend(["| Scene | Expected | Observed | Automated | LLM-review | Key learning |",
                  "| --- | --- | --- | --- | --- | --- |"])
    for row in bundle["scenes"]:
        grade = row["automated_result"]
        fields = [row["scene_id"], row["expected"], row["observed"],
                  f"{grade['status']} ({grade['judgments_passed']}/{grade['judgments_total']})",
                  row["response_review"], row["key_learning"]]
        lines.append("| " + " | ".join(map(text, fields)) + " |")
    for example in bundle.get("worked_examples", []):
        lines.extend(["", "## Worked example", "", f"Scene: `{text(example['scene_id'])}`.", ""])
        for label, key in (("Request", "request"), ("Before revision", "before"),
                           ("Repair instruction", "repair"), ("Released answer", "after"),
                           ("Lesson", "lesson")):
            lines.extend([f"{label}: {text(example[key])}", ""])
        if example.get("trace_url"):
            lines.extend([f"[Inspect this example in Logfire](<{example['trace_url']}>)", ""])
    for label, key in (("Report points", "report_points"), ("Slide points", "slide_points"),
                       ("Limitations", "limitations")):
        lines.extend(["", f"## {label}", "", *[f"- {text(point)}" for point in bundle[key]]])
    lines.extend(["", "The nested `result.json` contains the original evaluation, analysis, adopted inputs, "
                  "and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.", ""])
    return "\n".join(lines)


def render_bundle(result_path: Path) -> Path:
    """Render editable report prose without allowing the recorded outcomes to drift."""
    bundle = json.loads(result_path.read_bytes())
    _validate(bundle)
    output = result_path.with_name("summary.md")
    if output.is_symlink():
        raise ValueError("summary output cannot be a symlink")
    output.write_text(_summary(bundle), encoding="utf-8")
    return output


def extract_evaluation(result_path: Path, output: Path) -> Path:
    """Restore the original evaluation bytes for existing captured-stage tools."""
    _, evaluation = _validate(json.loads(result_path.read_bytes()))
    if evaluation is None:
        raise ValueError("this attempt has no original evaluation artifact to extract")
    with output.open("xb") as stream:
        stream.write(evaluation)
    return output


def bundle_run(directory: Path, *, backup_root: Path | None = None) -> dict:
    """Replace a completed run's files with two validated, lossless report artifacts."""
    directory = _directory(directory)
    result_path = directory / "result.json"
    files = _files(directory)
    if result_path in files:
        if set(files) - {result_path, directory / "summary.md"}:
            raise ValueError("bundle contains unexpected files; preserve them before rebuilding")
        return {"result": str(result_path), "summary": str(render_bundle(result_path)), "status": "unchanged"}
    if directory / "summary.md" in files:
        raise ValueError("summary.md already exists without result.json")
    original = {path: path.read_bytes() for path in files}
    bundle = _make_bundle(directory, original)
    _validate(bundle)
    root = backup_root.resolve() if backup_root else Path(tempfile.mkdtemp(prefix="linger-result-backup-"))
    if root.is_relative_to(directory):
        raise ValueError("backup root must be outside the original run directory")
    root.mkdir(parents=True, exist_ok=True)
    backup = root / f"{directory.name}-{uuid4().hex[:8]}.tar.gz"
    with tarfile.open(backup, "x:gz") as archive:
        for path, raw in original.items():
            info = tarfile.TarInfo(str(Path(directory.name) / path.relative_to(directory)))
            info.size = len(raw)
            archive.addfile(info, io.BytesIO(raw))
    with result_path.open("xb") as stream:
        stream.write(_json_bytes(bundle))
    summary_path = render_bundle(result_path)
    expected = set(original) | {result_path, summary_path}
    if set(_files(directory)) != expected or any(path.read_bytes() != raw for path, raw in original.items()):
        raise ValueError(f"original files changed during bundling; preserved them and backup at {backup}")
    for path in original:
        path.unlink()
    for path in sorted(directory.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_dir():
            path.rmdir()
    return {"result": str(result_path), "summary": str(summary_path), "backup": str(backup), "status": "bundled"}
