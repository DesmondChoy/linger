"""Export a small, deterministic catalog and package-evidence snapshot for the UI."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml


APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]
CATALOG = REPO / "synthetic-journal-evaluation/evaluation-objectives.yaml"
PACKAGES = REPO / "synthetic-journal-evaluation/packages"


def scene_record(scene: dict) -> dict:
    failures = list(scene.get("gate_failures", []))
    for grade in scene.get("grades", []):
        failures.extend(grade.get("failures", []))
    failures = list(dict.fromkeys(failures))
    return {
        "id": scene["scene_id"],
        "result": scene.get("ground_truth_result") or (
            "Recorded grade failure" if failures else "No overall verdict in this summary"
        ),
        "failures": failures,
    }


def export() -> dict:
    catalog = yaml.safe_load(CATALOG.read_text())
    packages = []
    for package in sorted(PACKAGES.iterdir(), reverse=True):
        backstory_path = package / "backstory.json"
        truth_path = package / "ground-truth.json"
        if not backstory_path.is_file() or not truth_path.is_file():
            continue
        backstory = json.loads(backstory_path.read_text())
        truth = json.loads(truth_path.read_text())
        runs = []
        for path in sorted(package.glob("*.json")):
            record = json.loads(path.read_text())
            if not isinstance(record, dict) or not record.get("run_id"):
                continue
            scenes = record.get("scenes", [])
            runs.append({
                "file": path.name,
                "runId": record["run_id"],
                "kind": "summary" if record.get("record_kind") == "synthetic_replay_summary" or path.name.endswith("-summary.json") else "artifact",
                "scenes": [scene_record(scene) for scene in scenes],
            })
        packages.append({
            "id": package.name,
            "objectiveIds": backstory["objective_ids"],
            "sceneCount": len(backstory["scenes"]),
            "proposalCount": len(truth["proposals"]),
            "adoptionRecorded": (package / "ground-truth-adoption.json").is_file(),
            "runs": runs,
        })
    objectives = []
    for objective in catalog["evaluation_objectives"]:
        menu = objective["menu"]
        metadata = objective["evaluation_metadata"]
        objectives.append({
            "id": objective["id"],
            "title": menu["title"],
            "family": menu["family"],
            "summary": menu["summary"].strip(),
            "measures": metadata["suggested_measures"],
            "academicValue": metadata["academic_value"],
            "criteria": metadata["observable_outcomes"],
            "packageCount": sum(objective["id"] in p["objectiveIds"] for p in packages),
        })
    return {
        "catalogSha256": hashlib.sha256(CATALOG.read_bytes()).hexdigest(),
        "catalogSource": str(CATALOG.relative_to(REPO)),
        "families": [{"id": f["id"], "label": f["label"]} for f in catalog["menu_families"]],
        "objectives": objectives,
        "packages": packages,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = APP / "src/catalog.json"
    text = json.dumps(export(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not output.exists() or output.read_text() != text:
            raise SystemExit("Catalog snapshot is stale. Run pnpm refresh-data.")
        print("Catalog and package snapshot match repository sources.")
    else:
        output.write_text(text)
        print(f"Wrote {output}")
