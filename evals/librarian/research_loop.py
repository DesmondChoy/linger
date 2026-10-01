"""Experiment 4: Sculptor's retrieval error analysis and research, one round at a time.

- `prompt --round N` writes the exact instructions and input summary for owner review.
- `analyse --round N` runs Sculptor's error analysis on the round's practice traces.
- `approve --round N --step analysis|specification` records the owner's approval.
- `research --round N` runs Sculptor's web research from the approved analysis.

Every attempt, failed or not, is kept with its searches, opened pages, answers,
and retry requests. Held-back needs never reach Sculptor.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic_ai import capture_run_messages
from pydantic_ai.messages import RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart, UserPromptPart

from evals.librarian.chapter_cue_recall import RUNS as CUE_RUNS, _approver, _fresh
from src.linger.agents.sculptor.research_models import (
    EarlierRound,
    ErrorAnalysis,
    ErrorAnalysisInput,
    ResearchInput,
    ResearchSpecification,
)

ROOT = Path(__file__).with_name("research_runs")
DESCRIPTION = Path(__file__).with_name("retrieval_description.md")
STARTING_TRACES = CUE_RUNS / "stage2-practice-traces.json"
MAX_SEARCHES = 10
MAX_PAGES = 10


def _round(number: int) -> Path:
    path = ROOT / f"round-{number}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing {path.relative_to(ROOT.parent)}; run the earlier step first.")
    return json.loads(path.read_text(encoding="utf-8"))


def _traces(number: int) -> dict[str, Any]:
    """Round 1 starts from Stage 2; later rounds name their traces in `traces.json`."""
    pointer = _round(number) / "traces.json"
    path = Path(_read(pointer)["path"]) if pointer.exists() else STARTING_TRACES
    return _fresh(path, _read(path)["search"])


def _approved(number: int, step: str) -> dict[str, Any]:
    """Return a step's output only when the owner approved exactly this file."""
    output = _round(number) / f"{step}.json"
    approval = _read(_round(number) / f"{step}-approval.json")
    if approval["sha256"] != _sha256(output):
        raise SystemExit(f"round-{number}/{step}.json changed after approval; approve it again.")
    return _read(output)


def _earlier_rounds(number: int) -> tuple[EarlierRound, ...]:
    rounds = []
    for earlier in range(1, number):
        result = _read(_round(earlier) / "practice-result.json")
        rounds.append(EarlierRound(
            round=earlier,
            categories=ErrorAnalysis.model_validate(_approved(earlier, "analysis")["output"]).categories,
            specification=_approved(earlier, "specification")["output"],
            practice_passed=result["passed"], practice_total=result["total"],
        ))
    return tuple(rounds)


def analysis_input(number: int) -> ErrorAnalysisInput:
    traces = _traces(number)
    return ErrorAnalysisInput(
        book_title="The Adventures of Pinocchio",
        retrieval_description=DESCRIPTION.read_text(encoding="utf-8"),
        chapter_tags=traces["chapter_tags"], traces=traces["traces"],
        earlier_rounds=_earlier_rounds(number),
    )


def research_input(number: int) -> ResearchInput:
    analysis = ErrorAnalysis.model_validate(_approved(number, "analysis")["output"])
    return ResearchInput(
        **analysis_input(number).model_dump(), error_analysis=analysis,
        max_searches=MAX_SEARCHES, max_pages=MAX_PAGES,
    )


def _turns(messages: list[Any], input_sha256: str) -> list[dict[str, Any]]:
    turns = []
    for message in messages:
        for part in message.parts:
            if isinstance(part, UserPromptPart):
                turns.append({"part": "input", "input_sha256": input_sha256})
            elif isinstance(part, ToolCallPart):
                turns.append({"part": "call", "tool": part.tool_name, "args": part.args_as_dict()})
            elif isinstance(part, ToolReturnPart):
                turns.append({"part": "tool_result", "tool": part.tool_name,
                              "content": str(part.content)[:2_000]})
            elif isinstance(part, RetryPromptPart):
                turns.append({"part": "retry_request", "content": part.model_response()})
            elif isinstance(part, TextPart):
                turns.append({"part": "text", "content": part.content})
    return turns


async def _attempt(number: int, step: str, task: Any, run: Any, extra: Any = None) -> Any:
    """Run one Sculptor step, keep the attempt whatever happens, and write its output."""
    from apps.backend.config import get_settings
    from apps.backend.telemetry import configure_telemetry

    if (_round(number) / f"{step}-approval.json").exists():
        raise SystemExit(f"Round {number} {step} is already approved.")
    configure_telemetry()
    input_sha256 = hashlib.sha256(task.model_dump_json().encode()).hexdigest()
    attempts = _round(number) / f"{step}-attempts"
    attempts.mkdir(exist_ok=True)
    attempt = attempts / f"attempt-{len(list(attempts.glob('attempt-*.json'))) + 1}.json"
    output, error = None, None
    with capture_run_messages() as messages:
        try:
            output = await run(task)
        except Exception as failure:
            error = f"{type(failure).__name__}: {failure}"[:1_000]
    attempt.write_text(json.dumps({
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": "failed" if error else "succeeded", "error": error,
        "ledger": extra() if extra else None, "turns": _turns(messages, input_sha256),
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Recorded {attempts.name}/{attempt.name} ({'failed' if error else 'succeeded'}).")
    if error:
        raise SystemExit(error)
    (_round(number) / f"{step}.json").write_text(json.dumps({
        "round": number, "step": step,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": get_settings().linger_model, "input_sha256": input_sha256,
        "output": output.model_dump(mode="json"),
        **({"ledger": extra()} if extra else {}),
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


async def analyse(number: int) -> ErrorAnalysis:
    from src.linger.orchestration.retrieval_research import propose_error_analysis

    analysis = await _attempt(number, "analysis", analysis_input(number), propose_error_analysis)
    lines = [f"# Round {number} error analysis", "", "## Categories", ""]
    for category in analysis.categories:
        lines += [f"- **{category.name}** ({len(category.need_ids)}: {', '.join(category.need_ids)}): "
                  f"{category.definition}"]
    lines += ["", "## Notes on each trace", ""]
    lines += [f"- {note.need_id} ({'pass' if note.passed else 'FAIL'}): {note.note or '—'}" for note in analysis.notes]
    (_round(number) / "analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return analysis


async def research(number: int) -> ResearchSpecification:
    from src.linger.agents.sculptor.research_search import ResearchLedger
    from src.linger.orchestration.retrieval_research import propose_research, research_search

    ledger = ResearchLedger(max_searches=MAX_SEARCHES, max_pages=MAX_PAGES)
    search = research_search(ledger)
    specification = await _attempt(
        number, "specification", research_input(number),
        lambda task: propose_research(task, search=search),
        extra=lambda: {"searches": ledger.searches, "opened": ledger.opened},
    )
    lines = [f"# Round {number} specification", "",
             f"**Target:** {specification.target_category}", "", f"**Problem:** {specification.problem}", "",
             f"**Approach:** {specification.approach}", "", "**Changes:**", "",
             *(f"{index}. {change}" for index, change in enumerate(specification.retrieval_changes, 1)), "",
             f"**Sculptor data:** {specification.sculptor_data or 'none'}", "",
             "**Expected fixes:**", "", *(f"- {fix}" for fix in specification.expected_fixes), "",
             "**Risks:**", "",
             *(f"- {risk}" for risk in specification.risks), "",
             f"**Test plan:** {specification.test_plan}", "", f"**Limits:** {specification.limits_check}", "",
             "**Sources:**", "", *(f"- [{source.title}]({source.url}): {source.supports}"
                                    for source in specification.sources), "",
             f"**Searches ({len(ledger.searches)}):** " + "; ".join(ledger.searches)]
    (_round(number) / "specification.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return specification


def approve(number: int, step: str) -> None:
    output = _round(number) / f"{step}.json"
    _read(output)
    (_round(number) / f"{step}-approval.json").write_text(json.dumps({
        "round": number, "step": step, "sha256": _sha256(output), "approved_by": _approver(),
        "approved_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Approved round-{number}/{step}.json.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("analyse", "research"):
        commands.add_parser(name).add_argument("--round", type=int, required=True, dest="number")
    approving = commands.add_parser("approve")
    approving.add_argument("--round", type=int, required=True, dest="number")
    approving.add_argument("--step", choices=("analysis", "specification"), required=True)
    args = parser.parse_args()
    if args.command == "approve":
        approve(args.number, args.step)
    elif args.command == "analyse":
        asyncio.run(analyse(args.number))
        print(f"Wrote round-{args.number}/analysis.md for review.")
    else:
        asyncio.run(research(args.number))
        print(f"Wrote round-{args.number}/specification.md for review.")


if __name__ == "__main__":
    main()
