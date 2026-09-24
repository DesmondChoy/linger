"""Recount saved experiment artifacts. Standard library only; no live calls."""

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = ROOT / "synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17"
SOURCES = {}


def read(path):
    SOURCES[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text())


def strict_case(suite, row):
    if suite == "mapping":
        return row.get("grade", {}).get("passed") is True and row.get("error_type") is None
    checks = [row.get("strength_correct") is True]
    if suite == "direct":
        checks += [row.get("evidence_recall") == 1, row.get("final_evidence_precision") == 1,
                   row.get("citations_resolve") is True, row.get("spoiler_safe") is True,
                   row.get("response_kind") == "result", row.get("response", {}).get("kind") == "result"]
    else:
        calls = row.get("librarian_calls", [])
        checks += [row.get("final_evidence_recall") == 1, row.get("final_citation_precision") == 1,
                   row.get("exact_citations_resolve") is True, row.get("spoiler_exposure") is False,
                   row.get("release_source") == "muse_candidate", "failure_stage" in row,
                   row.get("failure_stage") is None,
                   row.get("provenance_verdicts", [])[-1:] == ["pass"], bool(calls),
                   all(all(c.get(k) is True for k in ("query_argument_absent", "work_id_matches",
                           "book_version_id_matches", "application_owned_scope")) for c in calls)]
    return all(checks)


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
                     + ["| " + " | ".join(map(str, r)) + " |" for r in rows])


def main():
    attempts, observations = [], []
    for file in sorted(BASE.glob("iteration-*/summary.json")):
        summary = read(file)
        folder = file.parent
        iteration = summary["iteration"]
        row = {"iteration": iteration, "folder": folder.name, "model": summary["model"],
               "model_settings": summary.get("model_settings"),
               "selected_suites": summary["suites"], "complete_selection": summary["complete_evaluation_set"],
               "source_unchanged": summary["source_unchanged"], "all_pass": summary["all_pass"],
               "native_passed": 0, "native_total": 0, "judgments_passed": 0, "judgments_total": 0,
               "recovered_native": False, "components": {}}
        native = [(r["suite"], r["native_summary"]["results"], folder / f"suite-{r['suite']}.json")
                  for r in summary["results"] if r.get("native_summary", {}).get("results")]
        recovery = folder / "suite-4.recovery.json"
        if recovery.exists():
            receipt = read(recovery)
            relative = receipt["artifact"].split("/synthetic-journal-evaluation/", 1)[1]
            native.append(("4", receipt["summary"], ROOT / "synthetic-journal-evaluation" / relative))
            row["recovered_native"] = True
        for suite, counts, artifact_path in native:
            row["native_passed"] += counts["scenes_passed"]
            row["native_total"] += counts["scenes_total"]
            row["judgments_passed"] += counts["judgments_passed"]
            row["judgments_total"] += counts["judgments_total"]
            artifact = read(artifact_path)
            scenes = artifact["scenes"]
            assert len(scenes) == counts["scenes_total"], artifact_path
            passed = 0
            for scene in scenes:
                ok = scene.get("hard_gate_pass", scene.get("ground_truth_result") == "passes_hard_gates")
                passed += bool(ok)
                codes = sorted({code for grade in scene["grades"] for code in grade.get("failures", [])})
                observations.append({"iteration": iteration, "suite": suite, "scene": scene["scene_id"],
                                     "passed": bool(ok), "failure_codes": codes,
                                     "artifact": str(artifact_path.relative_to(ROOT))})
            assert passed == counts["scenes_passed"], artifact_path
        for suite in ("direct", "release", "mapping", "smoke"):
            path = folder / f"suite-{suite}.json"
            if not path.exists():
                row["components"][suite] = None
                continue
            artifact = read(path)
            if suite == "smoke":
                row["components"][suite] = {"passed": int(artifact["hard_gate_pass"]), "total": 1}
            else:
                cases = artifact["cases"]
                row["components"][suite] = {"passed": sum(strict_case(suite, c) for c in cases),
                                             "total": len(cases), "recorded_summary": artifact["summary"]}
        before, after = read(folder / "source-hashes.json"), read(folder / "source-hashes-after.json")
        row["source_snapshot_matches"] = before == after
        attempts.append(row)
    index = read(BASE / "report-index.json")
    assessments = Counter()
    reviewed = set()
    for entry in index["native_scenario_reports"]:
        relative = entry["analysis_data"].split("/synthetic-journal-evaluation/", 1)[1]
        review = read(ROOT / "synthetic-journal-evaluation" / relative)
        for scene in review["review"]["scenes"]:
            key = (int(entry["iteration"].split("-")[1]), entry["suite"].removeprefix("suite-"), scene["scene_id"])
            assert key not in reviewed, key
            reviewed.add(key)
            assessments[scene["assessment"]] += 1
    assert reviewed == {(o["iteration"], o["suite"], o["scene"]) for o in observations}
    patterns = Counter(code for o in observations for code in o["failure_codes"])
    nonquota = Counter(code for o in observations if o["iteration"] != 20 for code in o["failure_codes"])
    scenarios = defaultdict(lambda: Counter())
    for o in observations:
        scenarios[o["suite"]]["total"] += 1
        scenarios[o["suite"]]["passed"] += o["passed"]
    concentrations = defaultdict(lambda: Counter())
    for o in observations:
        concentrations[f"{o['suite']}:{o['scene']}"]["observed"] += 1
        concentrations[f"{o['suite']}:{o['scene']}"]["failed"] += not o["passed"]
    data = {"method": "Saved artifacts only. One failure-code count per iteration/suite/scene; categories overlap. Recovered attempt-15 Pigeon included. Missing outcomes excluded.",
            "attempts": attempts, "native_observations": observations,
            "archived_review_assessments": dict(assessments), "scene_failure_concentrations": dict(concentrations),
            "failure_code_scene_incidence": dict(patterns.most_common()),
            "failure_code_scene_incidence_excluding_iteration_20": dict(nonquota.most_common()),
            "scenario_occurrences": dict(scenarios), "source_sha256": SOURCES}
    (HERE / "aggregate.json").write_text(json.dumps(data, indent=2) + "\n")
    def component(a, name):
        c = a["components"][name]
        if c:
            return f"{c['passed']}/{c['total']}"
        return "Unavailable / ungraded" if name in a["selected_suites"] else "Not run"
    rows = []
    for a in attempts:
        scope = "Interrupted" if a["iteration"] == 15 else "Full selection" if a["complete_selection"] else "Subset"
        rows.append([f"[{a['iteration']}](../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/{a['folder']}/summary.json)",
                     scope, f"{a['native_passed']}/{a['native_total']}" + (" recovered" if a["recovered_native"] else ""),
                     f"{a['judgments_passed']}/{a['judgments_total']}",
                     *(component(a, s) for s in ("direct", "release", "mapping", "smoke"))])
    content = ["# Saved experiment measurements", "", "Generated by `aggregate.py`. See [the report](report.md) for interpretation and limitations.", "",
               "## Attempt results", "", "Full selection describes the requested suite set, not successful execution. Attempt 15 contains recovered Pigeon results only; seven native scenario outcomes, covering 26 Scenes, are unavailable. Component counts use the strict batch-driver case checks. Not run is distinct from failed. Smoke is one structural case, not a semantic-quality score.", "",
               table(["Attempt", "Scope", "Native Scenes", "Judgments", "Direct", "Release", "Mapping", "Smoke"], rows), "",
               "## Repeated native observations", "", "These are repeated evaluations of the same small dataset on changing versions. Counts describe the archive, not production reliability. Attempt 15 contributes three recovered Scenes. Attempt 20 includes quota failures.", "",
               table(["Suite", "Passing observations", "Observed Scenes"], [[k,v['passed'],v['total']] for k,v in sorted(scenarios.items(),key=lambda x:int(x[0]))]), "",
               "## Saved semantic assessments", "", "These are archived AI-assisted artifact reviews, not independent human labels or new model-judge runs. They qualify the mechanical grades rather than replace them.", "",
               table(["Assessment", "Scene observations"], sorted(assessments.items())), "",
               "## Recurrent failing Scenes", "", "Ranked by failed observations. Targeted reruns over-sample known failures. Includes attempt 20.", "",
               table(["Suite and Scene", "Failed observations", "Observed attempts"], [[k,v['failed'],v['observed']] for k,v in sorted(concentrations.items(),key=lambda x:-x[1]['failed']) if v['failed']]), "",
               "## Failure-code incidence", "", "Each code is counted once per saved Scene per attempt, even if two judgments report it. One Scene can have several codes. These are symptoms, not independent root causes. Excluding attempt 20 removes the largest quota outage; it does not remove every provider or execution failure.", "",
               table(["Failure code", "All saved Scenes", "Without attempt 20"], [[f"`{k}`",v,nonquota[k]] for k,v in patterns.most_common()]), "",
               "## Reproduction", "", "From the repository root, run:", "", "```sh", "python3 docs/reports/librarian-experiments-2026-09-24/aggregate.py", "```", "",
               "This reads local JSON and writes `aggregate.json` and this file. It makes no provider calls. The JSON records source-file SHA-256 hashes and every native Scene's result and codes. Assertions reconcile Scene counts against saved native summaries. Source snapshots are compared to their completion snapshots; this does not establish that today's runtime is identical.", ""]
    (HERE / "measurements.md").write_text("\n".join(content))
    print(f"{len(attempts)} attempts; {len(observations)} saved native Scene observations; {sum(o['passed'] for o in observations)} passed; {len(SOURCES)} source files")


if __name__ == "__main__":
    main()
