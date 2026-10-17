"""Export recorded synthetic-persona runs for the read-only replay view.

Each scenario under `synthetic-journal-evaluation/scenarios` that has at least
one saved `scenario-run-*/evaluation.json` becomes a persona. The snapshot keeps
what the replay renders: the persona and the Props placed in the account before
the run, each Scene's Lines and adopted checks, and per run the recorded turns,
agent activity, grades and the completed analysis review.

Nothing is inferred. Values are copied from committed records. Each agent's
input (the synthetic prompt it received) is kept, clipped; full model message
transcripts, system instructions and local paths are left out.

Output: `personas/index.json` for the gallery and one `personas/<id>.json` per
persona, so the replay loads only the persona being viewed.

    uv run python apps/frontend/scripts/export_personas.py [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from evals.synthetic_journals.scenario_catalog import discover  # noqa: E402
from evals.synthetic_journals.scenario_diagnostics import summarize_artifact  # noqa: E402
from src.linger.corpus.registry import CORPORA  # noqa: E402

TITLES = {work_id: registration.book.title for work_id, registration in CORPORA.items()}

SCENARIOS = REPO / "synthetic-journal-evaluation/scenarios"
CATALOG = REPO / "synthetic-journal-evaluation/evaluation-objectives.yaml"
OUTPUT = REPO / "apps/frontend/src/replay/personas"

TEXT_LIMIT = 4000
OUTPUT_LIMIT = 4000
INPUT_LIMIT = 8000
EVIDENCE_TEXT_LIMIT = 1200


def clip(text: Any, limit: int = TEXT_LIMIT) -> str:
    value = text if isinstance(text, str) else "" if text is None else json.dumps(text, ensure_ascii=False)
    return value if len(value) <= limit else value[: limit - 1] + "…"


def records(value: Any) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def timestamp(value: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def exchange_times(exchange: dict) -> tuple[float | None, float | None]:
    stamps = [
        stamp for message in records(exchange.get("model_messages"))
        if (stamp := timestamp(message.get("timestamp"))) is not None
    ]
    return (min(stamps), max(stamps)) if stamps else (None, None)


def exchanges(scene: dict) -> list[dict]:
    items = records(scene.get("agent_exchanges"))
    starts = [start for item in items if (start := exchange_times(item)[0]) is not None]
    origin = min(starts) if starts else None
    projected = []
    for item in items:
        start, end = exchange_times(item)
        projected.append({
            "sequence": item.get("sequence"),
            "role": item.get("role"),
            "stage": item.get("stage"),
            "skill": item.get("skill_id"),
            "status": item.get("status") or "success",
            "failureCode": item.get("failure_code"),
            "inputOrigin": item.get("input_origin"),
            "outputReceiver": item.get("output_receiver"),
            "startMs": round((start - origin) * 1000) if start is not None and origin is not None else None,
            "endMs": round((end - origin) * 1000) if end is not None and origin is not None else None,
            "input": clip(item.get("input_prompt"), INPUT_LIMIT) if item.get("input_prompt") else None,
            "output": clip(item.get("output"), OUTPUT_LIMIT) if item.get("output") is not None else None,
            "toolCalls": [
                {"tool": call.get("tool_name"), "outcome": call.get("outcome")}
                for call in records(item.get("tool_exchanges"))
            ],
        })
    return projected


def parsed(text: Any) -> Any:
    if not isinstance(text, str):
        return text
    try:
        return json.loads(text)
    except ValueError:
        return text


def draft_input(items: list[dict]) -> dict:
    """Muse's recorded draft input: the assembled MuseTurn contract and context."""
    for item in items:
        if item.get("role") == "Muse" and item.get("stage") == "draft" and item.get("input_prompt"):
            value = parsed(item["input_prompt"])
            if isinstance(value, dict):
                return value
    return {}


def trimmed_evidence(record: Any) -> Any:
    if isinstance(record, dict) and isinstance(record.get("text"), str):
        return {**record, "text": clip(record["text"], EVIDENCE_TEXT_LIMIT)}
    if isinstance(record, dict) and isinstance(record.get("excerpt"), str):
        return {**record, "excerpt": clip(record["excerpt"], EVIDENCE_TEXT_LIMIT)}
    return record


def connection_events(scene: dict) -> list[dict]:
    """Serendipity's recorded queries, searches, results and decision, in order."""
    events = []
    for event in records(scene.get("events")):
        fields = {key: value for key, value in event.items() if value not in (None, [], "")}
        if "evidence_json" in fields:
            fields["evidence"] = [trimmed_evidence(parsed(item)) for item in fields.pop("evidence_json")]
        if "decision_json" in fields:
            fields["decision"] = parsed(fields.pop("decision_json"))
        events.append(fields)
    return events


def grounding_calls(scene: dict) -> list[dict]:
    return [
        {**call, "evidence": [trimmed_evidence(item) for item in records(call.get("evidence"))]}
        for call in records(scene.get("grounding_calls"))
    ]


def sources(scene: dict, context: dict) -> list[dict]:
    """Reader-facing sources rebuilt from the released evidence identifiers."""
    known: dict[str, dict] = {}
    for call in records(scene.get("grounding_calls")):
        for item in records(call.get("evidence")):
            known[item.get("evidence_id")] = item
    for item in records(scene.get("boundary_support_evidence")):
        known.setdefault(item.get("evidence_id"), item)
    for event in records(scene.get("events")):
        for raw in event.get("evidence_json") or []:
            item = parsed(raw)
            if isinstance(item, dict) and item.get("evidence_id"):
                known.setdefault(item["evidence_id"], item)
    projected = []
    for evidence_id in scene.get("released_evidence_ids") or []:
        item = known.get(evidence_id, {})
        if str(evidence_id).startswith(("http://", "https://")):
            projected.append({"kind": "web", "label": evidence_id, "location": None, "url": evidence_id})
        elif str(evidence_id).startswith("mem_") or item.get("source_kind") == "memory":
            projected.append({"kind": "memory", "label": "Your earlier reflection", "location": None, "url": None})
        else:
            title = context.get("work_title") if context.get("work_id") == item.get("work_id") else None
            projected.append({
                "kind": "book",
                "label": title or TITLES.get(item.get("work_id")) or "Book passage",
                "location": str(item.get("location") or "").split(", source lines")[0] or None,
                "url": None,
            })
    return projected


def turns(scene: dict, lines: list[str]) -> list[dict]:
    """The reader/Linger exchanges a Scene recorded, oldest first, each with its own agent runs."""
    items = records(scene.get("agent_exchanges"))
    projected_exchanges = exchanges(scene)

    def turn(user_message: Any, reply: Any, release: Any, sequences: tuple[int, int] | None) -> dict:
        own = [
            (raw, projected) for raw, projected in zip(items, projected_exchanges)
            if sequences is None or sequences[0] <= (raw.get("sequence") or 0) <= sequences[1]
        ]
        draft = draft_input([raw for raw, _ in own])
        context = scene.get("context_resolution") or draft.get("context_resolution")
        return {
            "userMessage": clip(user_message),
            "reply": clip(reply),
            "releaseSource": release,
            "provenanceVerdicts": scene.get("provenance_verdicts") or [],
            "capture": scene.get("capture"),
            "contextResolution": context,
            "museTurn": draft.get("muse_turn"),
            "prompt": clip(json.dumps(draft, ensure_ascii=False), INPUT_LIMIT) if draft else None,
            "memorySurfacing": draft.get("memory_surfacing"),
            "releasedEvidenceIds": scene.get("released_evidence_ids") or [],
            "sources": sources(scene, context or {}),
            "groundingCalls": grounding_calls(scene),
            "connectionEvents": connection_events(scene),
            "capturedMemory": (
                {"memoryId": scene.get("memory_id") or next(iter(scene.get("created_memory_ids") or []), None),
                 "text": scene.get("stored_text")}
                if scene.get("stored_text") else None
            ),
            "exchanges": [projected for _, projected in own],
        }

    recorded = records(scene.get("turns"))
    if recorded:
        # Session Scenes record which agent runs belong to each turn by sequence number.
        return [
            {
                **turn(
                    item.get("input_line") or item.get("line") or item.get("user_message"),
                    item.get("reply"),
                    item.get("release_source"),
                    (item["exchange_sequence_first"], item["exchange_sequence_last"])
                    if item.get("exchange_sequence_first") is not None else None,
                ),
                "capture": item.get("capture"),
                "releasedEvidenceIds": [],
                "sources": [],
                "groundingCalls": [],
                "connectionEvents": [],
            }
            for item in recorded
        ]
    if scene.get("reply") is None and scene.get("input_line") is None:
        return []
    return [turn(scene.get("input_line") or " ".join(lines), scene.get("reply"), scene.get("release_source"), None)]


def review_for(folder: Path, run_dir: Path) -> dict | None:
    """The completed analysis review written for exactly this run, if any."""
    for path in sorted(folder.glob("analysis-report-*.json"), reverse=True):
        try:
            report = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        artifact = str((report.get("evidence") or {}).get("artifact_path") or "")
        if artifact.endswith(f"{run_dir.name}/evaluation.json") and report.get("review"):
            return report["review"]
    return None


def run_projection(folder: Path, run_dir: Path, planned: dict[str, dict]) -> dict | None:
    artifact_path = run_dir / "evaluation.json"
    summary_path = run_dir / "summary.json"
    # The helper writes summary.json last, so a run without it was interrupted.
    if not artifact_path.is_file() or not summary_path.is_file():
        return None
    artifact = json.loads(artifact_path.read_text())
    observed = records(artifact.get("scenes"))
    if not observed:
        return None
    summary = json.loads(summary_path.read_text())
    review = review_for(folder, run_dir)
    reviewed = {item.get("scene_id"): item for item in records((review or {}).get("scenes"))}

    scenes = []
    for scene in observed:
        scene_id = scene.get("scene_id")
        result = summarize_artifact({"scenes": [scene]})
        status = "failed" if result["scenes_failed"] else "ungraded" if result["scenes_ungraded"] else "passed"
        notes = reviewed.get(scene_id) or {}
        curation = scene.get("response") if scene.get("reply") is None and scene.get("input_line") is None else None
        scenes.append({
            "sceneId": scene_id,
            "status": status,
            "failures": [item.get("detail") for item in result["failures"]],
            "executionFailures": [item.get("detail") for item in result["execution_failures"]],
            "assessment": notes.get("assessment"),
            "analysis": notes.get("interpretation"),
            "turns": turns(scene, planned.get(scene_id, {}).get("lines", [])),
            "curation": {
                "inputMemories": [
                    {"id": item.get("memory_id"), "text": item.get("text")}
                    for item in records(scene.get("input_memories"))
                ],
                "response": curation,
                "outcome": scene.get("actual_outcome"),
                "status": scene.get("curation_status"),
                "sourcesUnchanged": scene.get("source_immutable"),
                "exchanges": exchanges(scene),
            } if curation is not None else None,
        })
    totals = summarize_artifact({"scenes": observed})
    return {
        "id": artifact.get("run_id") or run_dir.name,
        "startedAt": summary.get("started_at"),
        "model": summary.get("model"),
        "systemVariant": (artifact.get("system_variant") or "")[:8] or None,
        "passed": totals["scenes_passed"],
        "failed": totals["scenes_failed"],
        "ungraded": totals["scenes_ungraded"],
        "total": totals["scenes_total"],
        "executionFailures": len(totals["execution_failures"]),
        "logfireUrl": summary.get("logfire_url"),
        "verdict": (review or {}).get("verdict"),
        "scenes": scenes,
    }


def persona_projection(folder: Path, entry: dict, families: dict[str, str]) -> dict | None:
    backstory = json.loads((folder / "backstory.json").read_text())
    truth = json.loads((folder / "ground-truth.json").read_text())
    lines = {line.get("line_id"): line.get("text", "") for line in records(backstory.get("lines"))}
    proposals: dict[str, list[dict]] = {}
    for proposal in records(truth.get("proposals")):
        proposals.setdefault(proposal.get("scene_id"), []).append(proposal)

    scenes = []
    for scene in sorted(records(backstory.get("scenes")), key=lambda item: item.get("order") or 0):
        scene_id = scene.get("scene_id")
        scenes.append({
            "id": scene_id,
            "order": scene.get("order"),
            "freshSession": bool(scene.get("fresh_session")),
            "objectiveIds": scene.get("objective_ids", []),
            "propIds": scene.get("prop_ids", []),
            "lines": [lines[line_id] for line_id in scene.get("line_ids", []) if line_id in lines],
            "expected": [text for item in proposals.get(scene_id, []) for text in item.get("expected_outcomes", [])],
            "prohibited": [text for item in proposals.get(scene_id, []) for text in item.get("prohibited_outcomes", [])],
        })
    planned = {scene["id"]: scene for scene in scenes}

    runs = [
        run for run_dir in sorted(folder.glob("scenario-run-*"), reverse=True)
        if run_dir.is_dir() and (run := run_projection(folder, run_dir, planned)) is not None
    ]
    if not runs:
        return None
    objective_ids = backstory.get("objective_ids", [])
    person = backstory.get("backstory", {})
    return {
        "id": folder.name,
        "title": entry.get("title") or folder.name,
        # Folder names end in the scenario's generation date; it tells same-titled scenarios apart.
        "dated": folder.name.rsplit("--", 1)[-1],
        "description": entry.get("description") or "",
        "family": next((families[item] for item in objective_ids if item in families), "other"),
        "objectiveIds": objective_ids,
        "personId": person.get("person_id"),
        "context": person.get("context", ""),
        "props": [
            {"id": prop.get("prop_id"), "text": prop.get("source_text", "")}
            for prop in records(backstory.get("props"))
        ],
        "scenes": scenes,
        "runs": runs,
    }


def export() -> dict:
    catalog = yaml.safe_load(CATALOG.read_text())
    family_labels = [{"id": item["id"], "label": item["label"]} for item in catalog.get("menu_families", [])]
    objectives = next(
        value for key, value in catalog.items()
        if key != "menu_families" and isinstance(value, list) and value and isinstance(value[0], dict) and "menu" in value[0]
    )
    families = {item["id"]: (item.get("menu") or {}).get("family") for item in objectives}
    entries = {entry["scenario"]: entry for entry in discover(REPO)}
    personas = []
    for folder in sorted(SCENARIOS.iterdir()):
        if not (folder / "backstory.json").is_file() or not (folder / "ground-truth.json").is_file():
            continue
        persona = persona_projection(folder, entries.get(folder.name, {}), families)
        if persona is not None:
            personas.append(persona)
    return {"source": str(SCENARIOS.relative_to(REPO)), "families": family_labels, "personas": personas}


def files(snapshot: dict) -> dict[str, str]:
    """Gallery index plus one file per persona, keyed by file name."""
    index = {
        "source": snapshot["source"],
        "families": snapshot["families"],
        "personas": [
            {
                "id": persona["id"], "title": persona["title"], "dated": persona["dated"],
                "description": persona["description"], "family": persona["family"],
                "runs": [
                    {key: run[key] for key in ("id", "startedAt", "passed", "failed", "ungraded", "total", "executionFailures")}
                    for run in persona["runs"]
                ],
            }
            for persona in snapshot["personas"]
        ],
    }
    output = {"index.json": json.dumps(index, ensure_ascii=False, indent=2) + "\n"}
    for persona in snapshot["personas"]:
        output[f"{persona['id']}.json"] = json.dumps(persona, ensure_ascii=False, indent=2) + "\n"
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the snapshot is stale")
    args = parser.parse_args()
    expected = files(export())
    if args.check:
        current = {path.name: path.read_text() for path in OUTPUT.glob("*.json")} if OUTPUT.is_dir() else {}
        if current != expected:
            raise SystemExit("Persona snapshot is stale. Run apps/frontend/scripts/export_personas.py.")
        print("Persona snapshot matches the scenario archive.")
    else:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        for stale in OUTPUT.glob("*.json"):
            if stale.name not in expected:
                stale.unlink()
        for name, text in expected.items():
            (OUTPUT / name).write_text(text)
        size = sum(len(text) for text in expected.values()) // 1024
        print(f"Wrote {len(expected)} files to {OUTPUT.relative_to(REPO)} ({size} KB total)")
