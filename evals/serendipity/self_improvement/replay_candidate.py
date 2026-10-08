"""Paired Scenario replays of two Serendipity conditions through production chat.

`--compare candidate` (default) compares the committed skill with a
self-improvement candidate. Scenario replay loads the connection-discovery
skill at import, so the driver swaps the skill file between processes and
restores the committed file however it exits. `--compare reasoning` compares
Serendipity at low and medium reasoning effort through LINGER_ROLE_REASONING.
Conditions alternate within each repetition so drift over time affects both
equally.

    uv run python evals/serendipity/self_improvement/replay_candidate.py \\
        evals/serendipity/self_improvement/2026-10-06 --repeats 3
    uv run python evals/serendipity/self_improvement/replay_candidate.py \\
        evals/serendipity/reports/replay-reasoning-2026-10-08 --compare reasoning
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
    parser.add_argument("--compare", choices=("candidate", "reasoning"), default="candidate")
    args = parser.parse_args()
    base_env = {**os.environ, "LINGER_WEB_SEARCH_ENABLED": "true"}
    if args.compare == "candidate":
        candidate = (args.run_dir / "final" / "candidate-SKILL.md").read_text(encoding="utf-8")
        out = args.run_dir / "replay"
        conditions = {"production": (None, {}), "candidate": (candidate, {})}
    else:
        out = args.run_dir
        conditions = {
            "low": (None, {"LINGER_ROLE_REASONING": '{"serendipity": "low"}'}),
            "medium": (None, {"LINGER_ROLE_REASONING": '{"serendipity": "medium"}'}),
        }
    try:
        for rep in range(1, args.repeats + 1):
            for condition, (skill_text, extra_env) in conditions.items():
                _restore()
                if skill_text is not None:
                    SKILL.write_text(skill_text, encoding="utf-8")
                env = {**base_env, **extra_env}
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
