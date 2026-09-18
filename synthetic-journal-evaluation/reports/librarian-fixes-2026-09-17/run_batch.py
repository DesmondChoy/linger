"""One reserved evaluation-set iteration; no automatic suite retries.

Use --plan to inspect commands without reserving budget or making provider calls.
The direct suite executes the notebook's case helpers, not the entire notebook.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from threading import Event
from time import monotonic
from uuid import uuid4

BASE = Path(__file__).resolve().parent
ROOT = next(path for path in BASE.parents if (path / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT))
from src.linger.agents.build import LUNA_SETTINGS

PYTHON = ROOT / ".venv/bin/python"
MODEL = "openai:gpt-5.6-luna"
SUITES = ("4", "6", "7", "8", "9", "10", "11", "12", "release", "direct", "smoke")
RUNNABLE_SUITES = (*SUITES, "mapping")
STOP = Event()


def now():
    return datetime.now(UTC).isoformat()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes(menu, suites):
    names = subprocess.check_output([
        "git", "ls-files", "-co", "--exclude-standard", "--", "apps/backend", "src/linger",
        "evals", "notebooks", "pyproject.toml", "uv.lock",
    ], cwd=ROOT, text=True).splitlines()
    paths = {ROOT / name for name in names}
    paths.update((Path(__file__), BASE / "run_live.py", BASE / "run_smoke.py", menu))
    for entry in read(menu)["entries"]:
        if str(entry["number"]) in suites:
            scenario = ROOT / "synthetic-journal-evaluation/scenarios" / entry["scenario"]
            for name, expected in entry["hashes"].items():
                path = scenario / name
                if not path.is_file() or digest(path) != expected:
                    raise ValueError(f"Frozen scenario input changed: {path}")
                paths.add(path)
    return {str(path.relative_to(ROOT)): digest(path) for path in sorted(paths) if path.is_file()}


def reserve(budget_path, suites, hashes):
    with budget_path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        budget = read(budget_path)
        entries = budget["iterations"]
        if not isinstance(entries, list) or len(entries) >= min(20, budget["maximum_iterations"]):
            raise RuntimeError("Live evaluation iteration budget exhausted")
        iteration = len(entries) + 1
        folder = BASE / f"iteration-{iteration:02d}-{uuid4().hex[:8]}"
        folder.mkdir(exist_ok=False)
        reservation = {
            "iteration": iteration, "reservation_id": uuid4().hex, "reserved_at": now(),
            "status": "reserved", "suites": suites, "model": MODEL,
            "model_settings": dict(LUNA_SETTINGS), "directory": str(folder),
            "source_manifest_sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
        }
        entries.append(reservation)
        write(budget_path, budget)
        return folder, reservation


def finish_reservation(budget_path, reservation, summary):
    with budget_path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        budget = read(budget_path)
        entry = next(item for item in budget["iterations"] if item["reservation_id"] == reservation["reservation_id"])
        entry.update(status="complete", finished_at=now(), all_pass=summary["all_pass"],
                     selected_pass=summary["selected_pass"], summary=str(Path(entry["directory"]) / "summary.json"))
        write(budget_path, budget)


def command(suite, menu, output):
    if suite.isdigit():
        return [str(PYTHON), "-m", "evals.synthetic_journals.run_scenario", "run", "--menu", str(menu),
                "--number", suite, "--confirmed-model", MODEL]
    if suite == "smoke":
        return [str(PYTHON), str(BASE / "run_smoke.py"), "--output", str(output)]
    return [str(PYTHON), str(BASE / "run_live.py"), suite, "--output", str(output)]


def numeric_one(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == 1


def grade(suite, report, expected_ids):
    failures = []
    if suite.isdigit():
        scenes = report.get("scenes", [])
        if len(scenes) != len(expected_ids) or {row.get("scene_id") for row in scenes} != set(expected_ids):
            failures.append("incomplete_or_duplicate_scenes")
        for row in scenes:
            label = row.get("scene_id", "unknown")
            grades = row.get("grades", [])
            hard_pass = (row.get("hard_gate_pass") is True if "hard_gate_pass" in row
                         else row.get("ground_truth_result") == "passes_hard_gates")
            if not hard_pass or not grades:
                failures.append(f"{label}:hard_gate_or_missing_grades")
            for result in grades:
                if (result.get("failures") != []
                        or ("hard_gate_pass" not in row and result.get("hard_pass") is not True)):
                    failures.append(f"{label}:{result.get('proposal_id')}:grade_failures")
                if result.get("first_failure_stage") is not None:
                    failures.append(f"{label}:{result.get('proposal_id')}:stage_failure")
    elif suite == "mapping":
        rows = report.get("cases", [])
        if len(rows) != len(expected_ids) or {row.get("case_id") for row in rows} != set(expected_ids):
            failures.append("incomplete_or_duplicate_cases")
        for row in rows:
            if row.get("grade", {}).get("passed") is not True or row.get("error_type") is not None:
                failures.append(f"{row.get('case_id')}:mapping_grade")
        if report.get("summary", {}).get("targets_pass") is not True:
            failures.append("mapping_targets")
    elif suite == "smoke":
        expected = {"invocation", "retrieval", "serendipity_selection", "muse_presentation", "provenance_review", "deterministic_release"}
        stages = report.get("stages", [])
        if (report.get("hard_gate_pass") is not True or len(stages) != len(expected)
                or {stage.get("stage") for stage in stages} != expected
                or any(stage.get("status") != "passed" for stage in stages)):
            failures.append("smoke_hard_grades")
    else:
        rows = report.get("cases", [])
        if len(rows) != 12 or len(rows) != len(expected_ids) or {row.get("case_id") for row in rows} != set(expected_ids):
            failures.append("incomplete_or_duplicate_cases")
        for row in rows:
            checks = {"strength_correct": row.get("strength_correct") is True}
            if suite == "release":
                checks.update(
                    recall=numeric_one(row.get("final_evidence_recall")),
                    precision=numeric_one(row.get("final_citation_precision")),
                    citations=row.get("exact_citations_resolve") is True,
                    spoiler_safe=row.get("spoiler_exposure") is False,
                    release=row.get("release_source") == "muse_candidate" and "failure_stage" in row and row["failure_stage"] is None,
                    provenance=bool(row.get("provenance_verdicts")) and row["provenance_verdicts"][-1] == "pass",
                    call_contract=bool(row.get("librarian_calls")) and all(
                        call.get("query_argument_absent") is True and call.get("work_id_matches") is True
                        and call.get("book_version_id_matches") is True and call.get("application_owned_scope") is True
                        for call in row.get("librarian_calls", [])),
                )
            else:
                checks.update(
                    recall=numeric_one(row.get("evidence_recall")),
                    precision=numeric_one(row.get("final_evidence_precision")),
                    citations=row.get("citations_resolve") is True,
                    spoiler_safe=row.get("spoiler_safe") is True,
                    contract=row.get("response_kind") == "result" and row.get("response", {}).get("kind") == "result",
                )
            failures.extend(f"{row.get('case_id')}:{name}" for name, passed in checks.items() if not passed)
        if suite == "release" and report.get("summary", {}).get("targets_pass") is not True:
            failures.append("native_release_targets")
    return failures


def execute(suite, menu, folder, expected_ids):
    output = folder / f"suite-{suite}.json"
    log = folder / f"suite-{suite}.log"
    argv = command(suite, menu, output)
    env = dict(os.environ, LINGER_MODEL=MODEL, HF_HUB_OFFLINE="1", LINGER_WEB_SEARCH_ENABLED="true" if suite == "smoke" else "false")
    result = {"suite": suite, "command": argv, "started_at": now(), "log": str(log), "passed": False}
    try:
        if STOP.is_set():
            raise RuntimeError("Batch interrupted before suite launch")
        with log.open("x") as handle:
            process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
            started = monotonic()
            while process.poll() is None:
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    if STOP.is_set() or monotonic() - started > 3600:
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait()
                        raise RuntimeError("Suite interrupted or exceeded one-hour execution limit; not retried")
        result["returncode"] = process.returncode
        if suite.isdigit():
            lines = [line.removeprefix("SCENARIO_RESULT=") for line in log.read_text().splitlines() if line.startswith("SCENARIO_RESULT=")]
            if len(lines) != 1:
                raise ValueError("Native helper did not emit exactly one final SCENARIO_RESULT")
            native = json.loads(lines[0])
            write(folder / f"suite-{suite}.native-summary.json", native)
            result["native_summary"] = native
            if native.get("artifact"):
                shutil.copyfile(native["artifact"], output)
            else:
                raise ValueError("Native helper saved no evaluation artifact")
        report = read(output)
        failures = grade(suite, report, expected_ids)
        if process.returncode != 0:
            failures.append(f"process_exit:{process.returncode}")
        if suite.isdigit() and result["native_summary"].get("status") != "passed":
            failures.append("native_helper_not_passed")
        result.update(artifact=str(output), failures=failures, passed=not failures)
    except Exception as error:
        result.update(error=f"{type(error).__name__}: {error}", failures=["execution_or_report_error"])
    result["finished_at"] = now()
    write(folder / f"suite-{suite}.status.json", result)
    print(json.dumps({"suite": suite, "passed": result["passed"], "failures": result["failures"]}), flush=True)
    return result


def main(args):
    suites = args.suites or list(SUITES)
    if len(suites) != len(set(suites)):
        raise ValueError("Duplicate suites would retry a live evaluation")
    concurrency = min(args.concurrency, len(suites))
    if concurrency < 1:
        raise ValueError("At least one suite must be allowed to run")
    menu = args.menu.resolve()
    hashes = source_hashes(menu, suites)
    entries = {str(entry["number"]): entry for entry in read(menu)["entries"]}
    cases = read(ROOT / "evals/librarian/cases.json")["cases"]
    expected = {suite: entries[suite]["scene_ids"] if suite.isdigit() else [case["case_id"] for case in cases] for suite in suites}
    if "mapping" in suites:
        expected["mapping"] = [case["case_id"] for case in read(ROOT / "evals/provenance/claim-mapping-cases.json")["cases"]]
    if args.plan:
        print(json.dumps({"model": MODEL, "model_settings": dict(LUNA_SETTINGS), "suites": suites, "maximum_concurrent_suites": concurrency,
                          "commands": [command(suite, menu, BASE / "NEW_ITERATION" / f"suite-{suite}.json") for suite in suites],
                          "source_file_count": len(hashes), "provider_calls": False, "budget_reserved": False}, indent=2))
        return 0
    folder, reservation = reserve(args.budget.resolve(), suites, hashes)
    write(folder / "source-hashes.json", hashes)
    shutil.copyfile(menu, folder / "menu.json")
    write(folder / "reservation.json", reservation)
    print(f"ITERATION_DIRECTORY={folder}", flush=True)
    results = []
    executor = ThreadPoolExecutor(max_workers=concurrency)
    try:
        futures = [executor.submit(execute, suite, folder / "menu.json", folder, expected[suite]) for suite in suites]
        for future in as_completed(futures):
            results.append(future.result())
            write(folder / "progress.json", results)
    except KeyboardInterrupt:
        STOP.set()
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    # Read durable statuses even if interrupted while waiting for a future.
    results = [read(folder / f"suite-{suite}.status.json") for suite in suites if (folder / f"suite-{suite}.status.json").exists()]
    source_error = None
    try:
        after = source_hashes(menu, suites)
    except (OSError, ValueError) as error:
        after = {}
        source_error = f"{type(error).__name__}: {error}"
    write(folder / "source-hashes-after.json", after)
    selected_pass = len(results) == len(suites) and all(result["passed"] for result in results) and after == hashes
    complete_set = set(SUITES).issubset(suites)
    summary = {"model": MODEL, "model_settings": dict(LUNA_SETTINGS), "iteration": reservation["iteration"], "suites": suites,
               "maximum_concurrent_suites": concurrency,
               "complete_evaluation_set": complete_set, "source_unchanged": after == hashes, "source_error": source_error,
               "selected_pass": selected_pass, "all_pass": selected_pass and complete_set,
               "finished_at": now(), "results": results, "semantic_review": "Not performed by this deterministic batch driver"}
    write(folder / "summary.json", summary)
    finish_reservation(args.budget.resolve(), reservation, summary)
    print(f"BATCH_SUMMARY={folder / 'summary.json'}", flush=True)
    return 0 if selected_pass else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suites", nargs="+", choices=RUNNABLE_SUITES)
    parser.add_argument("--menu", type=Path, default=BASE / "saved-menu.json")
    parser.add_argument("--budget", type=Path, default=BASE / "live-budget.json")
    parser.add_argument("--concurrency", type=int, choices=range(1, 13), default=6,
                        help="Maximum simultaneous suites; each selected suite still runs exactly once")
    parser.add_argument("--plan", action="store_true", help="Inspect without budget reservation or live calls")
    raise SystemExit(main(parser.parse_args()))
