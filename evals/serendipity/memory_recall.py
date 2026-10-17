"""Recall@k of Serendipity's memory search over adopted Scenario memory stores.

For every adopted Scenario proposal that cites the reader's own memories, the
store is the set of Props active in that Scene, the query is the reader's Line,
and the relevant records are the Props the adopted Ground truth cites. The
ranking is production `search_memories`, called directly, so no model runs and
the result costs nothing.

The query is the reader's own words. In production Serendipity writes the
memory query itself, so this measures the search with the reader's phrasing,
not with Serendipity's.

    uv run python -m evals.serendipity.memory_recall \\
        --output evals/serendipity/reports/memory-recall-at-k-2026-10-08.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.linger.agents.serendipity.models import ConnectionDiscoveryInput, ConnectionScope
from src.linger.agents.serendipity.tools import MAX_RESULTS_PER_SOURCE, SerendipityDependencies, search_memories
from src.linger.contracts.curation import CuratedMemory

SCENARIOS = Path("synthetic-journal-evaluation/scenarios")
KS = (1, 3, 5)
# Curation and capture proposals cite Props as material to curate, not as
# answers to retrieve.
EXCLUDED_OBJECTIVE_WORDS = ("curation", "capture")


def _active_props(backstory: dict[str, Any], scene: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {prop["prop_id"]: prop for prop in backstory.get("props", [])}
    active = [
        prop for prop in by_id.values()
        if any(
            entry.get("scene_id") == scene["scene_id"] and entry.get("state") == "active"
            for entry in prop.get("lifecycle", [])
        )
    ]
    return active or [by_id[prop_id] for prop_id in scene.get("prop_ids", []) if prop_id in by_id]


def rank(query: str, props: list[dict[str, Any]], limit: int = MAX_RESULTS_PER_SOURCE) -> list[str]:
    """Production memory search over these Props, returning the ranked Prop ids."""
    deps = SerendipityDependencies(
        task=ConnectionDiscoveryInput(
            cue=query, intent="recall_memory", presentation="direct",
            scope=ConnectionScope(allowed_sources=("memory",)),
        ),
        librarian=None,  # type: ignore[arg-type]
        memories=tuple(
            CuratedMemory(
                memory_id=prop["prop_id"], kind="original", text=prop["source_text"],
                source_memory_ids=(prop["prop_id"],), created_at="2026-09-01T00:00:00Z",
            )
            for prop in props
        ),
    )
    result = search_memories(SimpleNamespace(deps=deps), query, limit)  # type: ignore[arg-type]
    return [item.evidence_id for item in result.evidence]


def queries() -> list[dict[str, Any]]:
    rows = []
    for folder in sorted(SCENARIOS.iterdir()):
        backstory_path, truth_path = folder / "backstory.json", folder / "ground-truth.json"
        if not (backstory_path.exists() and truth_path.exists()):
            continue
        backstory = json.loads(backstory_path.read_text(encoding="utf-8"))
        truth = json.loads(truth_path.read_text(encoding="utf-8"))
        scenes = {scene["scene_id"]: scene for scene in backstory.get("scenes", [])}
        lines = {line["line_id"]: line for line in backstory.get("lines", [])}
        for proposal in truth.get("proposals", []):
            if any(word in proposal.get("objective_id", "") for word in EXCLUDED_OBJECTIVE_WORDS):
                continue
            cited = [item["prop_id"] for item in proposal.get("evidence", []) if item.get("kind") == "prop"]
            scene = scenes.get(proposal.get("scene_id"))
            if not cited or scene is None:
                continue
            query = " ".join(lines[line_id]["text"] for line_id in scene.get("line_ids", []) if line_id in lines)
            store = _active_props(backstory, scene)
            relevant = [prop_id for prop_id in cited if prop_id in {prop["prop_id"] for prop in store}]
            if not query or not relevant:
                continue
            rows.append({
                "scenario": folder.name, "proposal_id": proposal["proposal_id"],
                "objective_id": proposal["objective_id"], "query": query,
                "store_size": len(store), "relevant": relevant,
                "ranked": rank(query, store),
            })
    return rows


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def recall(row: dict[str, Any], k: int) -> float:
        return len(set(row["relevant"]) & set(row["ranked"][:k])) / len(row["relevant"])

    return {
        "queries": len(rows),
        "mean_store_size": round(sum(row["store_size"] for row in rows) / len(rows), 2) if rows else None,
        **{f"recall_at_{k}": round(sum(recall(row, k) for row in rows) / len(rows), 3) for k in KS},
        **{f"all_relevant_at_{k}": sum(recall(row, k) == 1 for row in rows) for k in KS},
        "nothing_found": sum(not row["ranked"] for row in rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rows = queries()
    by_store = {}
    for row in rows:
        by_store.setdefault(row["scenario"], []).append(row)
    report = {
        "experiment": "serendipity-memory-recall-at-k",
        "query_source": "reader Line text; production search_memories ranking",
        "overall": summarise(rows),
        "by_scenario": {name: summarise(items) for name, items in by_store.items()},
        "rows": rows,
    }
    print(json.dumps({"overall": report["overall"], "by_scenario": report["by_scenario"]}, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
