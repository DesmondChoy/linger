"""Live measurement of Muse's turn-triage classifier on labelled single messages.

Reports contain case IDs, labels, aggregate metrics, and runtime metadata only.
They never retain the evaluated messages.

    uv run python -m evals.muse.turn_triage --runs 3
    uv run python -m evals.muse.turn_triage --runs 1 --main-model
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from statistics import median
from time import perf_counter

from pydantic_ai.models import Model

from src.linger.agents.build import build_model, build_triage_model
from src.linger.agents.muse.agent import muse_chat_agent
from src.linger.agents.muse.prompt import TURN_TRIAGE_PROMPT_FINGERPRINT
from src.linger.agents.muse.skills import TURN_TRIAGE
from src.linger.contracts.triage import TurnTriageInput

DEFAULT_CASES = Path(__file__).with_name("cases") / "triage" / "turn_triage_cases.json"
FIELDS = ("book_content", "memory", "override_attempt")
CONCURRENCY = 4


async def _classify(case: dict, model: Model, gate: asyncio.Semaphore) -> dict:
    """Run the same skill selection as `triage_turn`, keeping usage for costing."""
    prompt = TurnTriageInput(current_line=case["current_line"]).model_dump_json()
    async with gate:
        started = perf_counter()
        try:
            result = await muse_chat_agent.run(prompt, model=model, **TURN_TRIAGE.run_options())
        except Exception as error:  # a failed call is a measured outcome, not a crash
            status = getattr(error, "status_code", "")
            return {"error": f"{type(error).__name__}{status}", "seconds": perf_counter() - started}
        usage = result.usage
        return {
            **result.output.model_dump(),
            "seconds": perf_counter() - started,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        }


async def measure(cases: list[dict], model: Model, runs: int) -> dict:
    gate = asyncio.Semaphore(CONCURRENCY)
    per_run = [
        await asyncio.gather(*(_classify(case, model, gate) for case in cases))
        for _ in range(runs)
    ]
    calls = [call for run in per_run for call in run]
    answered = [call for call in calls if "error" not in call]
    report: dict = {
        "model": model.model_name,
        "prompt_fingerprint": TURN_TRIAGE_PROMPT_FINGERPRINT.model_dump(mode="json"),
        "runs": runs,
        "cases": len(cases),
        "errors": dict(Counter(call["error"] for call in calls if "error" in call)),
        "latency_seconds": (
            {
                "median": round(median(call["seconds"] for call in answered), 2),
                "p90": round(
                    sorted(call["seconds"] for call in answered)[int(len(answered) * 0.9)], 2
                ),
                "max": round(max(call["seconds"] for call in answered), 2),
            }
            if answered
            else None
        ),
        "mean_input_tokens": (
            round(sum(call["input_tokens"] for call in answered) / len(answered))
            if answered
            else None
        ),
        "mean_output_tokens": (
            round(sum(call["output_tokens"] for call in answered) / len(answered))
            if answered
            else None
        ),
    }
    for field in FIELDS:
        confusion: Counter[str] = Counter()
        unacceptable = []
        answered_calls_for_field = 0
        for case, *outcomes in zip(cases, *per_run):
            for run_index, outcome in enumerate(outcomes, start=1):
                got = outcome.get(field, "error")
                confusion[f"{case[field][0]} -> {got}"] += 1
                if "error" in outcome:
                    continue
                answered_calls_for_field += 1
                if got not in case[field]:
                    unacceptable.append(
                        {"case_id": case["case_id"], "run": run_index,
                         "acceptable": case[field], "got": got}
                    )
        stable = sum(
            len(answered) == 1
            for answered in (
                {outcome[field] for outcome in outcomes if "error" not in outcome}
                for outcomes in zip(*per_run)
            )
            if answered
        )
        report[field] = {
            "acceptable_rate": (
                round(1 - len(unacceptable) / answered_calls_for_field, 3)
                if answered_calls_for_field
                else None
            ),
            "cases_identical_across_runs": f"{stable}/{len(cases)}",
            "confusion_primary_to_got": dict(sorted(confusion.items())),
            "unacceptable": unacceptable,
        }
    # The two errors the exposure design cannot absorb or most wants to avoid,
    # plus the memory-specific misses and the pinned-recall cost. Errored
    # calls are excluded throughout: a provider rate limit is not a
    # classifier regression.
    report["book_content"]["wrong_no"] = [
        item for item in report["book_content"]["unacceptable"] if item["got"] == "no"
    ]
    named = [
        index for index, case in enumerate(cases)
        if case["category"] in {"personal_names_book", "personal_theme_names_book"}
    ]
    named_calls = [
        run[index] for run in per_run for index in named if "error" not in run[index]
    ]
    report["book_content"]["yes_on_personal_lines_naming_a_book"] = (
        f"{sum(call.get('book_content') == 'yes' for call in named_calls)}/{len(named_calls)}"
    )
    # wrong_none_strict: recall was needed and the tool was hidden, with no
    # recovery via unsure. wrong_none_soft: unsure was acceptable, so the
    # miss had a softer landing.
    report["memory"]["wrong_none_strict"] = [
        item for item in report["memory"]["unacceptable"]
        if item["got"] == "none" and "unsure" not in item["acceptable"]
    ]
    report["memory"]["wrong_none_soft"] = [
        item for item in report["memory"]["unacceptable"]
        if item["got"] == "none" and "unsure" in item["acceptable"]
    ]
    pinned = [
        index for index, case in enumerate(cases)
        if case["memory"][0] == "own_earlier_reflections" and "unsure" not in case["memory"]
    ]
    pinned_calls = [
        run[index] for run in per_run for index in pinned if "error" not in run[index]
    ]
    report["memory"]["pinned_recall_lost_to_unsure"] = (
        f"{sum(call.get('memory') == 'unsure' for call in pinned_calls)}/{len(pinned_calls)}"
    )
    # missed_attempts: an override attempt classified as none, the miss the
    # exposure design cannot absorb. false_alarms: the reverse, a clean
    # message classified as an attempt.
    report["override_attempt"]["missed_attempts"] = [
        item for item in report["override_attempt"]["unacceptable"] if item["got"] == "no_attempt"
    ]
    report["override_attempt"]["false_alarms"] = [
        item for item in report["override_attempt"]["unacceptable"] if item["got"] == "attempted"
    ]
    report["per_case"] = {
        case["case_id"]: [
            f"{outcome.get('book_content', 'error')}/{outcome.get('memory', 'error')}/"
            f"{outcome.get('override_attempt', 'error')}"
            for outcome in outcomes
        ]
        for case, *outcomes in zip(cases, *per_run)
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--main-model", action="store_true", help="use LINGER_MODEL itself")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    cases = json.loads(args.cases.read_text(encoding="utf-8"))["cases"]
    model = build_model() if args.main_model else build_triage_model()
    report = asyncio.run(measure(cases, model, args.runs))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
