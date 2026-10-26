"""Props from the committed scenario replay snapshot, for loading into a live account.

The snapshot is written by `apps/frontend/scripts/export_scenarios.py` from
reviewed scenario records. Only scenarios listed in its index can be loaded, so
a request never chooses the file or the text that is saved.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.linger.services.memory import ScenarioProp

SNAPSHOT = Path(__file__).resolve().parents[2] / "apps/frontend/src/replay/scenarios"


def scenario_props(scenario_id: str, snapshot: Path = SNAPSHOT) -> tuple[ScenarioProp, ...] | None:
    """The scenario's Props, or None when the snapshot does not list it."""

    index = json.loads((snapshot / "index.json").read_text(encoding="utf-8"))
    if scenario_id not in {entry["id"] for entry in index["scenarios"]}:
        return None
    scenario = json.loads((snapshot / f"{scenario_id}.json").read_text(encoding="utf-8"))
    return tuple(
        ScenarioProp(
            prop_id=prop["id"],
            text=prop["text"],
            recorded_at=datetime.fromisoformat(prop["recordedAt"]) if prop["recordedAt"] else None,
        )
        for prop in scenario["props"]
    )
