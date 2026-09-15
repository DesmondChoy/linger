"""CLI behind the conversational run-scenario skill; confirmation belongs to the user."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .scenario_catalog import (
    REPOSITORY_ROOT,
    discover,
    inspect_scenario,
    scenario_hashes,
    redact,
    selected_scenario,
)
from .scenario_analysis import render_analysis_report, write_analysis_report
from .scenario_diagnostics import summarize_artifact

LINK_MARKER = "SYNTHETIC_EVALUATION_LOGFIRE="


def write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as output:
        output.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def create_menu(repository_root: Path, output: Path | None = None) -> tuple[Path, dict[str, Any]]:
    menu = {
        "schema_version": 2,
        "repository_root": str(repository_root.resolve()),
        "created_at": datetime.now().astimezone().isoformat(),
        "entries": discover(repository_root),
    }
    if output is None:
        output = Path(tempfile.gettempdir()) / f"linger-scenario-menu-{uuid4().hex}.json"
    write_json(output, menu)
    return output, menu


def read_selection(menu_path: Path, number: int, repository_root: Path) -> tuple[Path, dict[str, Any]]:
    menu = json.loads(menu_path.read_text(encoding="utf-8"))
    if menu.get("schema_version") != 2 or menu.get("repository_root") != str(repository_root.resolve()):
        raise ValueError("The menu belongs to another checkout or version; refresh it.")
    return selected_scenario(menu, number, repository_root)


def preflight(scenario: Path, entry: dict[str, Any], repository_root: Path, model: str | None) -> dict[str, Any]:
    current = inspect_scenario(scenario, repository_root, model)
    if current["hashes"] != entry["hashes"]:
        current["issues"].insert(0, {
            "category": "selection",
            "detail": "Scenario files changed after the displayed menu; refresh it and choose again.",
        })
    return current


def telemetry_result(log: str) -> dict[str, Any] | None:
    for line in reversed(log.splitlines()):
        if line.startswith(LINK_MARKER):
            try:
                value = json.loads(line[len(LINK_MARKER):])
                if isinstance(value, dict):
                    return value
            except ValueError:
                pass
    return None


def run_selected(
    menu_path: Path,
    number: int,
    confirmed_model: str,
    *,
    repository_root: Path = REPOSITORY_ROOT,
    timeout_seconds: float = 1800,
) -> dict[str, Any]:
    scenario, entry = read_selection(menu_path, number, repository_root)
    check = preflight(scenario, entry, repository_root, confirmed_model)
    model = check["configuration"]["model"]
    if check["issues"]:
        problems = [item["detail"] for item in check["issues"]]
        report = write_analysis_report(
            scenario, repository_root=repository_root, model=model,
            category=check["issues"][0]["category"], problems=problems,
            execution_status="not_started",
        )
        return {
            "status": "blocked", "execution_status": "not_started", "model": model,
            "problems": problems, "analysis_report": str(report),
            "analysis_data": str(report.with_suffix(".json")),
        }

    stamp = datetime.now().astimezone().strftime("%Y-%m-%dT%H%M%S%z")
    run_directory = Path(tempfile.mkdtemp(prefix=f"scenario-run-{stamp}-", dir=scenario))
    artifact_path = run_directory / "evaluation.json"
    log_path = run_directory / "run.log"
    summary_path = run_directory / "summary.json"
    command = [
        sys.executable, "-m", check["runner"],
        str(scenario / "backstory.json"), str(scenario / "ground-truth.json"),
        "--adoption", str(scenario / "ground-truth-adoption.json"),
        "--output", str(artifact_path),
    ]
    environment = dict(os.environ, LINGER_MODEL=model)
    if check["requires_web"]:
        environment["LINGER_WEB_SEARCH_ENABLED"] = "true"
    result: dict[str, Any] = {
        "scenario": scenario.name, "model": model, "command": command,
        "started_at": datetime.now().astimezone().isoformat(),
        "scenario_hashes": check["hashes"],
        "artifact": str(artifact_path), "run_log": str(log_path),
        "summary_file": str(summary_path),
        "execution_status": "failed",
    }
    print(f"SCENARIO_RUN_STARTED={json.dumps(result)}", flush=True)
    problems: list[str] = []
    category = "execution"
    artifact: dict[str, Any] | None = None
    log = ""
    try:
        completed = subprocess.run(
            command, cwd=repository_root, env=environment,
            capture_output=True, text=True, timeout=timeout_seconds,
        )
        log = completed.stdout + "\n" + completed.stderr
        result["returncode"] = completed.returncode
        result["execution_status"] = "completed" if completed.returncode == 0 else "failed"
        if completed.returncode:
            problems.append(f"Replay exited with status {completed.returncode}. Inspect the saved run log.")
    except subprocess.TimeoutExpired as exc:
        result["execution_status"] = "timed_out"
        def decode(value: str | bytes | None) -> str:
            return value.decode(errors="replace") if isinstance(value, bytes) else value or ""
        log = decode(exc.stdout) + "\n" + decode(exc.stderr)
        problems.append(f"Replay exceeded the {timeout_seconds:g}-second execution limit.")
    except OSError as exc:
        problems.append(f"{type(exc).__name__}: {redact(str(exc), repository_root)}")
    except KeyboardInterrupt:
        result["execution_status"] = "interrupted"
        problems.append("Replay was interrupted; no automatic retry was attempted.")
    try:
        if artifact_path.is_file():
            parsed = json.loads(artifact_path.read_text(encoding="utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("Replay artifact is not a JSON object.")
            artifact = parsed
            observations = artifact.get("scenes")
            if not isinstance(observations, list):
                raise ValueError("Replay artifact has no Scene result list.")
            observed_ids = [scene.get("scene_id") for scene in observations if isinstance(scene, dict)]
            if (
                any(not isinstance(scene_id, str) for scene_id in observed_ids)
                or len(observed_ids) != len(observations)
                or len(set(observed_ids)) != len(observed_ids)
                or set(observed_ids) != set(check["scene_ids"])
            ):
                raise ValueError(
                    "Replay results must cover every scenario Scene exactly once; "
                    "missing, duplicate, or unexpected Scene observations prevent a complete evaluation."
                )
            summary = summarize_artifact(artifact)
            result["results"] = summary
            if summary["scenes_failed"] or summary["judgments_failed"]:
                if not problems:
                    category = "execution" if summary["execution_failures"] else "behavioral"
                problems.append(
                    "The artifact records a provider or application execution failure; do not interpret it as a Ground truth mismatch."
                    if summary["execution_failures"] else
                    "The replay completed with failed evaluation checks; see expected versus observed evidence."
                )
        elif not problems:
            problems.append("Replay exited successfully but did not save its evaluation artifact.")
    except (OSError, ValueError, TypeError) as exc:
        problems.append(f"{type(exc).__name__}: {redact(str(exc), repository_root)}")
    log = redact(log, repository_root)
    log_path.write_text(log, encoding="utf-8")
    telemetry = telemetry_result(log)
    result["telemetry"] = telemetry
    result["logfire_url"] = telemetry.get("url") if telemetry else None
    if not telemetry or not telemetry.get("url") or telemetry.get("flushed") is not True:
        if not problems:
            category = "telemetry"
        problems.append("Logfire link or successful telemetry flush was unavailable; remote visibility is unverified.")
    if scenario_hashes(scenario) != check["hashes"]:
        category = "selection"
        problems.append("Scenario files changed during execution; do not treat this run as evidence for the current scenario.")
    result["status"] = "failed" if problems else "passed"
    result["problems"] = problems
    result["finished_at"] = datetime.now().astimezone().isoformat()
    report = write_analysis_report(
        scenario, repository_root=repository_root, model=model,
        category=category if problems else "none", problems=problems, artifact=artifact,
        logfire_url=result["logfire_url"], output_path=artifact_path if artifact_path.is_file() else None,
        run_log_path=log_path, execution_status=result["execution_status"], telemetry=telemetry,
    )
    result["analysis_report"] = str(report)
    result["analysis_data"] = str(report.with_suffix(".json"))
    write_json(summary_path, result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="action", required=True)
    menu = subcommands.add_parser("menu", help="Discover scenarios and save the numbered selection.")
    menu.add_argument("--output", type=Path)
    report = subcommands.add_parser("report", help="Validate and render a completed analysis without running models.")
    report.add_argument("--analysis", type=Path, required=True)
    for action in ("inspect", "check", "run"):
        command = subcommands.add_parser(action)
        command.add_argument("--menu", type=Path, required=True)
        command.add_argument("--number", type=int, required=True)
        if action == "run":
            command.add_argument("--confirmed-model", required=True, help="Exact provider:model explicitly confirmed by the user for this run.")
            command.add_argument("--timeout-seconds", type=float, default=1800)
        else:
            command.add_argument("--model")
    args = parser.parse_args(argv)
    try:
        if args.action == "menu":
            path, snapshot = create_menu(REPOSITORY_ROOT, args.output)
            for entry in snapshot["entries"]:
                reasons = list(dict.fromkeys(item["category"] for item in entry["issues"]))
                labels = ["scenario validation" if reason == "scenario" else reason for reason in reasons]
                status = "Ready" if not reasons else "Blocked: " + ", ".join(labels)
                print(f"{entry['number']}. {entry['title']} — {entry['scene_count']} Scenes · {status}\n   {entry['description']}")
            print(f"SCENARIO_MENU_FILE={path}")
            return 0
        if args.action == "report":
            report_path = render_analysis_report(args.analysis)
            result = {"analysis_report": str(report_path), "analysis_data": str(args.analysis.resolve())}
        elif args.action == "run":
            result = run_selected(args.menu, args.number, args.confirmed_model, timeout_seconds=args.timeout_seconds)
        else:
            scenario, entry = read_selection(args.menu, args.number, REPOSITORY_ROOT)
            result = preflight(scenario, entry, REPOSITORY_ROOT, args.model)
            if args.action == "check" and result["issues"]:
                report = write_analysis_report(
                    scenario, repository_root=REPOSITORY_ROOT, model=result["configuration"]["model"],
                    category=result["issues"][0]["category"],
                    problems=[item["detail"] for item in result["issues"]],
                    execution_status="not_started",
                )
                result["analysis_report"] = str(report)
                result["analysis_data"] = str(report.with_suffix(".json"))
        print("SCENARIO_RESULT=" + json.dumps(result, ensure_ascii=False))
        return 1 if result.get("status") in {"blocked", "failed"} or result.get("issues") else 0
    except (OSError, ValueError, KeyError) as exc:
        print("SCENARIO_ERROR=" + redact(str(exc), REPOSITORY_ROOT), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
