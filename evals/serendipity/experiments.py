"""Paired experiments on why Serendipity declines outside recommendations.

Each experiment scores two conditions in one session, alternating runs within
each case, with the current skill:

- `intent`: the web-recommendation cases as written (`find_connection`) against
  the intent production triage sends for that request (`get_recommendation`,
  presented directly).
- `pages`: web fixtures described in one sentence against the real page text
  production would open (`page_snapshots.json`).
- `reasoning`: Serendipity at the shared low reasoning effort against medium.
- `model`: Serendipity on `gpt-6-luna` against `gpt-5.6-luna`.

`reasoning` and `model` change every case, so they run on the weak behaviours
and on the restraint behaviours that a looser agent could break.

    uv run python -m evals.serendipity.experiments intent \\
        --output evals/serendipity/reports/experiment-intent-2026-10-08.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from src.linger.agents.build import model_from_spec

from .harness import SerendipityEvalCase, load_serendipity_eval_cases
from .page_snapshots import SNAPSHOTS
from .reliability import Condition, ReliabilityReport, run_paired_reliability

WEB_RECOMMENDATION = "route_external_recommendation_to_web"
WEAK = {
    WEB_RECOMMENDATION,
    "expand_source_only_when_justified",
    "select_evidence_with_a_real_semantic_bridge",
    "exclude_ineligible_evidence_before_selection",
}
RESTRAINT = {"decline_when_no_supported_bridge_exists", "rank_the_strongest_supported_connection"}


def _variant(case: SerendipityEvalCase, **changes: Any) -> SerendipityEvalCase:
    data = case.model_dump(mode="json")
    for path, value in changes.items():
        target = data
        *parents, leaf = path.split(".")
        for key in parents:
            target = target[key]
        target[leaf] = value
    return SerendipityEvalCase.model_validate(data)


def triage_intent_variants(cases: tuple[SerendipityEvalCase, ...]) -> dict[str, SerendipityEvalCase]:
    """Give each web-recommendation case the intent production triage would pin."""
    return {
        case.case_id: _variant(
            case,
            **{"input.intent": "get_recommendation", "input.presentation": "direct",
               "expected.presentation": "direct"},
        )
        for case in cases
        if case.primary_behavior == WEB_RECOMMENDATION and case.input.intent == "find_connection"
    }


def real_page_variants(
    cases: tuple[SerendipityEvalCase, ...], snapshots: dict[str, dict[str, str]],
) -> dict[str, SerendipityEvalCase]:
    """Replace one-sentence page fixtures with the page text production would open."""
    variants = {}
    for case in cases:
        evidence = case.model_dump(mode="json")["tool_evidence"]
        changed = False
        for item in evidence:
            page = snapshots.get(item["evidence_id"]) if item["source_kind"] == "web" else None
            if page and page["text"].strip():
                item["excerpt"] = page["text"]
                changed = True
        if changed:
            variants[case.case_id] = _variant(case, tool_evidence=evidence)
    return variants


def plan(name: str) -> tuple[tuple[SerendipityEvalCase, ...], dict[str, Condition]]:
    discovery = tuple(case for case in load_serendipity_eval_cases() if case.input.intent != "gather_sources")
    if name == "intent":
        variants = triage_intent_variants(discovery)
        cases = tuple(case for case in discovery if case.primary_behavior == WEB_RECOMMENDATION)
        return cases, {"as-written": Condition(), "triage-intent": Condition(case_variants=variants)}
    if name == "pages":
        variants = real_page_variants(discovery, json.loads(SNAPSHOTS.read_text(encoding="utf-8")))
        cases = tuple(case for case in discovery if case.case_id in variants)
        return cases, {"one-sentence-pages": Condition(), "real-pages": Condition(case_variants=variants)}
    cases = tuple(case for case in discovery if case.primary_behavior in WEAK | RESTRAINT)
    if name == "reasoning":
        return cases, {
            "low": Condition(),
            "medium": Condition(model=model_from_spec("openai:gpt-6-luna", "medium")),
        }
    if name == "model":
        return cases, {
            "gpt-6-luna": Condition(),
            "gpt-5.6-luna": Condition(model=model_from_spec("openai:gpt-5.6-luna")),
        }
    raise SystemExit(f"unknown experiment {name!r}")


def compare(reports: dict[str, ReliabilityReport]) -> dict[str, Any]:
    (first, a), (second, b) = reports.items()
    behaviours: dict[str, dict[str, int]] = {}
    for left, right in zip(a.cases, b.cases):
        row = behaviours.setdefault(left.primary_behavior, {first: 0, second: 0, "runs": 0})
        row[first] += left.passes
        row[second] += right.passes
        row["runs"] += left.repeats
    return {
        "conditions": [first, second],
        first: a.summary.total_passes,
        second: b.summary.total_passes,
        "runs": a.summary.total_runs,
        "cases_up": sum(right.passes > left.passes for left, right in zip(a.cases, b.cases)),
        "cases_down": sum(right.passes < left.passes for left, right in zip(a.cases, b.cases)),
        "by_behaviour": behaviours,
        "case_changes": {
            left.case_id: [left.passes, right.passes]
            for left, right in zip(a.cases, b.cases) if left.passes != right.passes
        },
    }


async def run(name: str, repeats: int, concurrency: int) -> dict[str, Any]:
    cases, conditions = plan(name)
    reports = await run_paired_reliability(conditions, repeats=repeats, cases=cases, concurrency=concurrency)
    return {
        "experiment": name,
        "comparison": compare(reports),
        "reports": {key: report.model_dump(mode="json") for key, report in reports.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("experiment", choices=("intent", "pages", "reasoning", "model"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args()
    result = asyncio.run(run(args.experiment, args.repeat, args.concurrency))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["comparison"], indent=2))


if __name__ == "__main__":
    main()
