"""Deterministic replay summaries and bounded diagnostic evidence."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

_PASS_RESULTS = {"passes_hard_gates", "matches_proposal"}
_FAIL_RESULTS = {"fails_hard_gates", "differs_from_proposal"}
_SOURCE_NAMES = ("backstory.json", "ground-truth.json", "ground-truth-adoption.json")


def _failure_details(record: dict[str, Any]) -> list[str]:
    failures = [
        str(item)
        for key in ("failures", "hard_failures", "gate_failures", "structural_findings")
        for item in record.get(key, ())
    ]
    if record.get("ground_truth_result") in _FAIL_RESULTS:
        failures = failures or [str(record["ground_truth_result"])]
    if record.get("hard_pass") is False or record.get("hard_gate_pass") is False:
        failures = failures or ["deterministic hard gate failed"]
    return list(dict.fromkeys(failures))


def summarize_artifact(artifact: dict) -> dict:
    """Count deterministic judgments across the registered replay artifact shapes.

    Continuity control Scenes have no Ground truth judgment. Their structural
    findings still fail the Scene. Unknown or empty artifacts cannot pass.
    """
    scenes = artifact.get("scenes")
    if not isinstance(scenes, (list, tuple)) or not scenes:
        raise ValueError("replay artifact contains no Scenes")
    summary = {
        "scenes_total": len(scenes),
        "scenes_passed": 0,
        "scenes_failed": 0,
        "scenes_ungraded": 0,
        "judgments_total": 0,
        "judgments_passed": 0,
        "judgments_failed": 0,
        "failures": [],
        "execution_failures": [],
    }
    for scene in scenes:
        if not isinstance(scene, dict) or not scene.get("scene_id"):
            raise ValueError("replay artifact contains an invalid Scene")
        scene_id = scene["scene_id"]
        details = _failure_details(scene)
        ungraded = scene.get("ground_truth_result") == "not_applicable"
        if "grades" in scene:
            grades = scene["grades"]
        elif isinstance(scene.get("grade"), dict):
            grades = [scene["grade"]]
        elif scene.get("ground_truth_result") in _PASS_RESULTS | _FAIL_RESULTS:
            grades = [{key: value for key, value in scene.items() if key != "structural_findings"}]
        elif ungraded:
            grades = []
        else:
            raise ValueError(f"Scene {scene_id} has no recognized deterministic grade")
        if not isinstance(grades, (list, tuple)) or (not grades and not ungraded):
            raise ValueError(f"Scene {scene_id} has no deterministic judgments")
        scene_failures: list[dict] = []
        for grade in grades:
            if not isinstance(grade, dict) or not any(
                key in grade
                for key in ("failures", "hard_failures", "gate_failures", "hard_pass", "ground_truth_result")
            ):
                raise ValueError(f"Scene {scene_id} contains an unrecognized grade")
            failures = _failure_details(grade)
            summary["judgments_total"] += 1
            summary["judgments_failed" if failures else "judgments_passed"] += 1
            for detail in failures:
                item = {"scene_id": scene_id, "detail": detail}
                if grade.get("proposal_id"):
                    item["proposal_id"] = grade["proposal_id"]
                scene_failures.append(item)
        # Scene-level execution and invariant failures must survive even when a
        # proposal grade or a not-applicable continuity label has no failures.
        execution_error = scene.get("execution_error")
        if isinstance(execution_error, dict):
            details.append(str(execution_error.get("code", "scene execution failed")))
            summary["execution_failures"].append({"scene_id": scene_id, "detail": details[-1]})
        for turn in scene.get("turns", ()):
            if isinstance(turn, dict) and turn.get("failure_type") in {"model", "application"}:
                kind = "provider" if turn["failure_type"] == "model" else "application"
                details.append(f"{kind} failure at {turn.get('failure_stage') or 'unknown stage'}")
                summary["execution_failures"].append({"scene_id": scene_id, "detail": details[-1]})
        for detail in details:
            if scene_failures and detail in _FAIL_RESULTS | {"deterministic hard gate failed"}:
                continue
            if detail not in {item["detail"] for item in scene_failures}:
                scene_failures.append({"scene_id": scene_id, "detail": detail})
        if scene_failures:
            summary["scenes_failed"] += 1
            for exchange in scene.get("agent_exchanges", ()):
                if isinstance(exchange, dict) and exchange.get("failure_code"):
                    summary["execution_failures"].append({
                        "scene_id": scene_id,
                        "detail": f"{exchange.get('role', 'agent')} {exchange.get('stage', '')}: {exchange['failure_code']}",
                    })
        elif ungraded:
            summary["scenes_ungraded"] += 1
        else:
            summary["scenes_passed"] += 1
        summary["failures"].extend(scene_failures)
        summary["execution_failures"].extend(
            item for item in scene_failures
            if item["detail"] in {"provider_failure", "execution_failure"}
        )
    return summary


def _safe_text(value: object, limit: int = 1800) -> str:
    text = str(value)
    text = re.sub(r"\b(?:sk-[A-Za-z0-9_-]{8,}|AIza[A-Za-z0-9_-]{20,})\b", "[REDACTED]", text)
    text = re.sub(
        r"(?i)(\b[A-Z_]*(?:API_KEY|ACCESS_TOKEN|SECRET_KEY|LOGFIRE_TOKEN)\b[\"']?\s*[:=]\s*[\"']?)[^\"'\s,;]+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?(?:bearer\s+)?)[^\"'\s,;]+",
        r"\1[REDACTED]",
        text,
    )
    text = text.replace("\x00", "").replace("```", "''' ")
    return text if len(text) <= limit else text[:limit] + "… [truncated]"


def _read_json(path: Path) -> dict:
    try:
        if path.stat().st_size > 10_000_000:
            return {}
        document = json.loads(path.read_text(encoding="utf-8"))
        return document if isinstance(document, dict) else {}
    except (OSError, UnicodeError, ValueError):
        return {}


def _git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _run_log_tail(path: Path) -> str:
    try:
        with path.open("rb") as log:
            size = log.seek(0, 2)
            log.seek(max(0, size - 65536))
            raw = log.read(65536).decode("utf-8", errors="replace")
    except OSError:
        return "Saved run log could not be read."
    tail = _safe_text("\n".join(raw.splitlines()[-30:]), 65536)
    return tail if len(tail) <= 3500 else "[earlier log output omitted]\n" + tail[-3500:]


def collect_diagnostic_evidence(
    scenario_dir: Path, repository_root: Path, run_log_path: Path | None = None,
) -> dict:
    """Collect local hashes and bounded history without exporting reviewer data."""
    hashes: dict[str, str | None] = {}
    for name in _SOURCE_NAMES:
        try:
            with (scenario_dir / name).open("rb") as source:
                hashes[name] = hashlib.file_digest(source, "sha256").hexdigest()
        except OSError:
            hashes[name] = None
    adoption = _read_json(scenario_dir / "ground-truth-adoption.json")
    adoption_matches = {}
    for name, key in (
        ("backstory.json", "backstory_sha256"),
        ("ground-truth.json", "proposed_ground_truth_sha256"),
    ):
        expected = adoption.get(key)
        if isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected):
            adoption_matches[name] = {"adopted_sha256": expected, "matches": hashes[name] == expected}
    reviewed_at = adoption.get("reviewed_at")
    try:
        reviewed_time = datetime.fromisoformat(reviewed_at) if isinstance(reviewed_at, str) else None
    except ValueError:
        reviewed_time = None
    if reviewed_time is not None and reviewed_time.tzinfo is None:
        reviewed_time = None
    return {
        "source_hashes": hashes,
        "adoption_hash_matches": adoption_matches,
        "declared_adoption_time": reviewed_time.isoformat() if reviewed_time else None,
        "git": _history_evidence(scenario_dir, repository_root, hashes, reviewed_time),
        "run_log_tail": _run_log_tail(run_log_path) if run_log_path else None,
        "limits": [
            "Hash matches do not validate adoption decisions or scenario contracts.",
            "Adoption time and a matching scenario commit do not establish the generation revision.",
            "History is limited to 12 relevant commits. Changed commits are leads, not causal proof.",
            "The run log excerpt contains at most 30 lines and 3500 characters plus an omission marker.",
        ],
    }


def _history_evidence(
    scenario_dir: Path, repository_root: Path, hashes: dict[str, str | None],
    reviewed_time: datetime | None,
) -> dict:
    revision = _git(repository_root, "rev-parse", "HEAD")
    if not revision:
        return {"available": False, "reason": "Git revision and history are unavailable."}
    result: dict[str, Any] = {"available": True, "revision": revision}
    try:
        relative = scenario_dir.resolve().relative_to(repository_root.resolve())
    except ValueError:
        result["reason"] = "Scenario is outside this repository; no scenario baseline is available."
        return result
    sources = [(relative / name).as_posix() for name in _SOURCE_NAMES]
    scope = [
        "evals/synthetic_journals", "synthetic-journal-evaluation/evaluation-objectives.yaml",
        "docs/specification.md", "docs/agent-skills.md", "src/linger", "apps/backend",
    ]
    dirty = _git(repository_root, "status", "--short", "--untracked-files=all", "--", *sources, *scope)
    result["scoped_working_tree_changes"] = _safe_text(dirty, 4000) if dirty is not None else None
    path_snapshot = _git(repository_root, "log", "-1", "--format=%H", "--", *sources)
    content_commits = {
        commit for source in sources
        if (commit := _git(
            repository_root, "log", "-1", "--follow", "--find-renames=100%",
            "--diff-filter=AMDT", "--format=%H", "--", source,
        ))
    }
    baseline = _git(
        repository_root, "log", "-1", "--topo-order", "--format=%H", *sorted(content_commits),
    ) if content_commits else None
    result["scenario_commit"] = baseline or None
    if baseline:
        result["scenario_commit_description"] = _safe_text(
            _git(repository_root, "show", "-s", "--format=%h %cI %s", baseline)
        )
        def matches_source(name: str) -> bool:
            # The content baseline can precede exact renames; the latest path
            # snapshot retains those same bytes under the current filenames.
            committed_blob = _git(repository_root, "rev-parse", f"{path_snapshot}:{(relative / name).as_posix()}")
            return committed_blob is not None and committed_blob == _git(
                repository_root, "hash-object", "--no-filters", str(scenario_dir / name)
            )

        result["current_scenario_matches_commit"] = all(
            matches_source(name)
            for name, digest in hashes.items() if digest is not None
        ) and all(hashes.get(name) for name in ("backstory.json", "ground-truth.json"))
        committed_at = _git(repository_root, "show", "-s", "--format=%cI", baseline)
        if reviewed_time and committed_at and reviewed_time < datetime.fromisoformat(committed_at):
            history_args = [f"--since={reviewed_time.isoformat()}"]
            result["history_window"] = "since earlier declared adoption time, including changes before a later scenario move or edit"
        else:
            history_args = [f"{baseline}..HEAD"]
            result["history_window"] = "after scenario-content baseline"
    elif reviewed_time:
        history_args = [f"--since={reviewed_time.isoformat()}"]
        result["history_window"] = "since declared adoption time; no scenario commit was found"
    else:
        history_args = []
        result["history_window"] = "recent commits; no scenario or adoption baseline was found"
    history = _git(repository_root, "log", "-12", *history_args, "--format=%h %cI %s", "--name-only", "--", *scope)
    result["recent_commits"] = _safe_text(history, 6500) if history is not None else None
    return result


__all__ = ["collect_diagnostic_evidence", "summarize_artifact"]
