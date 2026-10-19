"""Offline analyses of saved reliability reports: a direct-only gate, and cost.

`gate` asks what a deterministic rule would do if it turned every proposal
whose winning candidate has `partial` cue fit into an `unsupported_cue`
decline. The rule acts on the agent's own ratings after the run, so it can be
scored exactly on saved runs without calling the model again.

`cost` turns saved token counts into dollars and cost per passing run.

    uv run python -m evals.serendipity.analysis gate \\
        evals/serendipity/reports/experiment-reasoning-suite-2026-10-13.json --arm medium
    uv run python -m evals.serendipity.analysis cost \\
        evals/serendipity/reports/experiment-reasoning-suite-2026-10-13.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .harness import ExpectedDecline, SerendipityEvalCase, load_serendipity_eval_cases

GATE_REASON = "unsupported_cue"
# USD per million tokens (input, output), from third-party price listings on
# 2026-10-13; reasoning tokens are billed as output.
PRICES = {
    "gpt-6-luna": (0.10, 0.50),
    "gpt-5.6-luna": (0.20, 1.20),
}


def gated_pass(run: dict[str, Any], case: SerendipityEvalCase) -> bool:
    """Whether a run would pass if proposals with a `partial` winner declined."""
    response = run.get("response") or {}
    if response.get("status") != "proposal":
        return bool(run["hard_pass"])
    if response["shortlist"][0]["rubric"]["cue_fit"] == "direct":
        return bool(run["hard_pass"])
    if not isinstance(case.expected, ExpectedDecline):
        return False
    remaining = [failure for failure in run["failures"] if failure != "expected_decline"]
    return GATE_REASON in case.expected.allowed_reasons and not remaining


def gate(report: dict[str, Any]) -> dict[str, Any]:
    cases = {case.case_id: case for case in load_serendipity_eval_cases()}
    by_behaviour: dict[str, dict[str, int]] = {}
    changed: dict[str, list[int]] = {}
    for row in report["cases"]:
        case = cases[row["case_id"]]
        after = sum(gated_pass(run, case) for run in row["runs"])
        counts = by_behaviour.setdefault(row["primary_behavior"], {"before": 0, "after": 0, "runs": 0})
        counts["before"] += row["passes"]
        counts["after"] += after
        counts["runs"] += row["repeats"]
        if after != row["passes"]:
            changed[row["case_id"]] = [row["passes"], after]
    return {
        "before": sum(item["before"] for item in by_behaviour.values()),
        "after": sum(item["after"] for item in by_behaviour.values()),
        "runs": sum(item["runs"] for item in by_behaviour.values()),
        "by_behaviour": by_behaviour,
        "case_changes": changed,
    }


def cost(report: dict[str, Any]) -> dict[str, Any]:
    model = report["model"].split(":", 1)[1].split(" ")[0]
    price_in, price_out = PRICES[model]
    runs = [run for row in report["cases"] for run in row["runs"]]
    tokens_in = sum(run.get("input_tokens") or 0 for run in runs)
    tokens_out = sum(run.get("output_tokens") or 0 for run in runs)
    dollars = (tokens_in * price_in + tokens_out * price_out) / 1_000_000
    passes = sum(run["hard_pass"] for run in runs)
    return {
        "model": report["model"],
        "runs": len(runs),
        "passes": passes,
        "mean_input_tokens": round(tokens_in / len(runs)),
        "mean_output_tokens": round(tokens_out / len(runs)),
        "usd_total": round(dollars, 4),
        "usd_per_run": round(dollars / len(runs), 6),
        "usd_per_pass": round(dollars / passes, 6) if passes else None,
    }


def _arms(path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["reports"] if "reports" in data else {"report": data}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("analysis", choices=("gate", "cost"))
    parser.add_argument("report", type=Path)
    parser.add_argument("--arm", help="one arm of a paired experiment report; default all")
    args = parser.parse_args()
    arms = _arms(args.report)
    selected = {args.arm: arms[args.arm]} if args.arm else arms
    run = gate if args.analysis == "gate" else cost
    print(json.dumps({name: run(report) for name, report in selected.items()}, indent=2))


if __name__ == "__main__":
    main()
