"""Paired Scenario replays of the production skill and a self-improvement candidate.

Scenario replay runs production chat, which loads the connection-discovery
skill at import. This driver therefore swaps the skill file between processes,
alternating production and candidate in each repetition so drift over time
affects both equally, and restores the committed file however it exits.

    uv run python evals/serendipity/self_improvement/replay_candidate.py \\
        evals/serendipity/self_improvement/2026-10-06 --repeats 3
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

SKILL = Path("src/linger/agents/serendipity/skills/connection-discovery/SKILL.md")
SCENARIOS = Path("synthetic-journal-evaluation/scenarios")
REPLAYS = {
    "cross-source": (
        "evals.synthetic_journals.connection_replay",
        "cross-source-connections-and-restraint--muse-librarian-serendipity-provenance--2026-09-12",
        (),
    ),
    "roses": (
        "evals.synthetic_journals.connection_replay",
        "alice-roses-concealment-and-restraint--muse-librarian-serendipity-provenance--2026-09-12",
        (),
    ),
    "scenes-06-09": (
        "evals.synthetic_journals.connection_curation_replay",
        "memory-curation-and-cross-source-connections--muse-librarian-serendipity-sculptor-provenance--2026-09-19",
        ("--scenes", "scene-06", "scene-07", "scene-08", "scene-09"),
    ),
}
TIMEOUT_SECONDS = 45 * 60


def _restore() -> None:
    subprocess.run(["git", "checkout", "--", str(SKILL)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    candidate = (args.run_dir / "final" / "candidate-SKILL.md").read_text(encoding="utf-8")
    out = args.run_dir / "replay"
    env = {**os.environ, "LINGER_WEB_SEARCH_ENABLED": "true"}
    try:
        for rep in range(1, args.repeats + 1):
            for condition in ("production", "candidate"):
                _restore()
                if condition == "candidate":
                    SKILL.write_text(candidate, encoding="utf-8")
                for name, (module, scenario, extra) in REPLAYS.items():
                    output = out / condition / f"{name}-rep{rep}.json"
                    if output.exists():
                        print(f"reusing {output}", flush=True)
                        continue
                    output.parent.mkdir(parents=True, exist_ok=True)
                    folder = SCENARIOS / scenario
                    command = [
                        "uv", "run", "python", "-m", module,
                        str(folder / "backstory.json"), str(folder / "ground-truth.json"),
                        "--adoption", str(folder / "ground-truth-adoption.json"),
                        "--output", str(output), *extra,
                    ]
                    started = time.monotonic()
                    print(f"start {condition} {name} rep{rep}", flush=True)
                    log = output.with_suffix(".log")
                    try:
                        with log.open("w", encoding="utf-8") as handle:
                            result = subprocess.run(
                                command, env=env, stdout=handle, stderr=subprocess.STDOUT,
                                timeout=TIMEOUT_SECONDS,
                            )
                        status = f"exit {result.returncode}"
                    except subprocess.TimeoutExpired:
                        status = "timeout"
                    print(
                        f"done {condition} {name} rep{rep}: {status} "
                        f"in {time.monotonic() - started:.0f}s",
                        flush=True,
                    )
    finally:
        _restore()
        print("restored production skill", flush=True)


if __name__ == "__main__":
    sys.exit(main())
