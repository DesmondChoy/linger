"""Export a projected snapshot of saved evaluations for the chat application.

The archive under `synthetic-journal-evaluation/scenarios` is several megabytes,
most of it evidence bodies and transcripts the UI never shows. This writes only
the fields the Saved evaluation surface renders: the persona, the props placed
in the account before a run, each scene's line and adopted checks, and, per run,
the observed route and its grades.

Nothing here is inferred. Every value is copied from a committed record, and a
run that carries no adopted grade is exported with a null tally rather than a
guess.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SNAPSHOT = REPO / "packages/architecture-map/src/evaluations.json"
SCENARIOS = REPO / "synthetic-journal-evaluation/scenarios"

# Replies are shown as evidence of what a build actually said. They are quoted
# in full up to this length so a reader can judge them, then elided.
REPLY_LIMIT = 900


def run_label(path: Path) -> str:
    """Name a run after the change it was testing, from its file name."""
    stem = path.stem
    for suffix in ("-replay-summary", "-regression-summary", "-summary", "-findings"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem.replace("-", " ") if stem else "baseline"


def scene_projection(scene: dict) -> dict:
    grades = [
        {
            "objectiveId": grade.get("objective_id"),
            "hardPass": bool(grade.get("hard_pass")),
            "failures": list(grade.get("failures", [])),
        }
        for grade in scene.get("grades", [])
    ]
    reply = scene.get("reply") or ""
    return {
        "sceneId": scene.get("scene_id"),
        "routeCalled": bool(scene.get("route_called")),
        "routedCeiling": scene.get("routed_ceiling"),
        "boundaryDecision": scene.get("boundary_decision"),
        "boundarySupportMemoryIds": list(scene.get("boundary_support_memory_ids", [])),
        "groundingCallCount": len(scene.get("grounding_calls", [])),
        "releasedEvidenceIds": list(scene.get("released_evidence_ids", [])),
        "releaseSource": scene.get("release_source"),
        "provenanceVerdicts": list(scene.get("provenance_verdicts", [])),
        "reply": reply[:REPLY_LIMIT] + ("…" if len(reply) > REPLY_LIMIT else ""),
        "observations": [
            {
                "role": item.get("role"),
                "stage": item.get("stage"),
                "status": item.get("status"),
                "toolCalls": item.get("tool_call_count"),
                "template": (item.get("prompt_fingerprint") or {}).get("template_id"),
                "templateVersion": (item.get("prompt_fingerprint") or {}).get("version"),
            }
            for item in scene.get("agent_observations", [])
        ],
        "grades": grades,
    }


def run_projection(path: Path, record: dict) -> dict:
    scenes = [scene_projection(scene) for scene in record.get("scenes", [])]
    graded = [grade for scene in scenes for grade in scene["grades"]]
    passed = record.get("judgments_passed")
    total = record.get("judgments_total")
    if total is None and graded:
        # Older records carry per-scene grades without the aggregate tally.
        passed = sum(1 for grade in graded if grade["hardPass"])
        total = len(graded)
    return {
        "id": record["run_id"],
        "label": run_label(path),
        "file": path.name,
        "systemVariant": (record.get("system_variant") or "")[:8] or None,
        "gitHead": (record.get("git_head") or "")[:8] or None,
        "model": record.get("configured_model"),
        "groundTruthStatus": record.get("ground_truth_status"),
        "passed": passed,
        "total": total,
        "cautions": list(record.get("interpretation_cautions", [])),
        "scenes": scenes,
    }


def scenario_projection(folder: Path) -> dict | None:
    backstory_path = folder / "backstory.json"
    truth_path = folder / "ground-truth.json"
    if not backstory_path.is_file() or not truth_path.is_file():
        return None
    backstory = json.loads(backstory_path.read_text())
    truth = json.loads(truth_path.read_text())

    lines = {line["line_id"]: line for line in backstory.get("lines", [])}
    proposals: dict[str, list[dict]] = {}
    for proposal in truth.get("proposals", []):
        proposals.setdefault(proposal.get("scene_id"), []).append(proposal)

    scenes = []
    for scene in backstory.get("scenes", []):
        scene_id = scene["scene_id"]
        text = " ".join(
            lines[line_id]["text"] for line_id in scene.get("line_ids", []) if line_id in lines
        )
        expected: list[str] = []
        prohibited: list[str] = []
        for proposal in proposals.get(scene_id, []):
            expected.extend(proposal.get("expected_outcomes", []))
            prohibited.extend(proposal.get("prohibited_outcomes", []))
        scenes.append({
            "id": scene_id,
            "order": scene.get("order"),
            "freshSession": bool(scene.get("fresh_session")),
            "objectiveIds": scene.get("objective_ids", []),
            "propIds": scene.get("prop_ids", []),
            "line": text,
            "expected": expected,
            "prohibited": prohibited,
        })

    runs = []
    for path in sorted(folder.glob("*.json")):
        try:
            record = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or not record.get("run_id"):
            continue
        runs.append(run_projection(path, record))

    person = backstory.get("backstory", {})
    return {
        "id": folder.name,
        "objectiveIds": backstory.get("objective_ids", []),
        "persona": {
            "id": person.get("person_id"),
            "context": person.get("context", ""),
        },
        "props": [
            {
                "id": prop.get("prop_id"),
                "sourceText": prop.get("source_text", ""),
                "activeScenes": [
                    entry.get("scene_id")
                    for entry in prop.get("lifecycle", [])
                    if entry.get("state") == "active"
                ],
            }
            for prop in backstory.get("props", [])
        ],
        "scenes": scenes,
        "runs": runs,
        "adoptionRecorded": (folder / "ground-truth-adoption.json").is_file(),
    }


def export() -> dict:
    scenarios = []
    for folder in sorted(SCENARIOS.iterdir()):
        if not folder.is_dir():
            continue
        projection = scenario_projection(folder)
        if projection is not None:
            scenarios.append(projection)
    return {
        "source": str(SCENARIOS.relative_to(REPO)),
        "scenarios": scenarios,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(export(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not SNAPSHOT.exists() or SNAPSHOT.read_text() != text:
            raise SystemExit("Evaluation snapshot is stale. Run pnpm refresh-data.")
        print("Evaluation snapshot matches the scenario archive.")
    else:
        SNAPSHOT.write_text(text)
        print(f"Wrote {SNAPSHOT} ({len(text) // 1024} KB)")
