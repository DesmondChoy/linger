"""Serendipity's supervised self-improvement loop over its component suite.

Round 0 scores the production connection-discovery skill on the practice
cases, so Serendipity's offline self-review skill has traces to read. Each
round, Serendipity names its most frequent failure and specifies exact edits to
its own instructions. Application code applies the edits to a candidate copy
and scores the candidate and the production skill together in one session,
alternating their runs, so day-to-day variation cannot pass for a gain. A
candidate that meets the pass mark fixed in `protocol.json` must meet it again
in a fresh paired comparison before it counts, because the loop keeps its best
round and that round's luck. A confirmed candidate is then compared with
production on the held-back cases. Production is never changed here:
promotion is an owner decision.

    uv run python -m evals.serendipity.self_improvement \\
        --output-dir evals/serendipity/self_improvement/2026-10-06

Every step writes its record before the next starts, and a rerun with the same
directory reuses existing records instead of paying for the run again.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_ai import capture_run_messages
from pydantic_ai.messages import RetryPromptPart, ToolCallPart

from apps.backend.config import get_settings
from apps.backend.telemetry import configure_component_evaluation_telemetry
from src.linger.agents.serendipity.agent import serendipity_agent
from src.linger.agents.serendipity.self_review_models import (
    CaseTrace,
    EarlierRound,
    ObservedRun,
    SelfReviewInput,
    SkillCorrection,
    apply_edits,
)
from src.linger.agents.serendipity.skills import CONNECTION_DISCOVERY
from src.linger.agents.skills import RuntimeSkill
from src.linger.contracts.base import StrictModel
from src.linger.orchestration.serendipity_self_review import (
    SELF_REVIEW_FINGERPRINT,
    propose_skill_correction,
)

from .harness import SerendipityEvalCase, load_serendipity_eval_cases
from .reliability import ReliabilityReport, run_paired_reliability, run_reliability_experiment

# Pre-registered on 2026-10-06, before round 0 ran. Held-back books test whether
# a correction generalises to books Serendipity never saw during review.
HELD_BACK_BOOKS = ("keller", "pinocchio")
MIN_PRACTICE_GAIN = 10
MAX_CASE_LOSS = 2
STABLE_FLOOR = 4
MAX_ROUNDS = 3
REVIEW_ATTEMPTS = 2
MAX_EXCERPT_CHARS = 1_500


class PassMark(StrictModel):
    min_practice_gain: int
    max_case_loss: int
    stable_floor: int
    description: str


class Protocol(StrictModel):
    experiment: str = "serendipity-self-improvement"
    model: str
    repeats: int
    max_rounds: int
    held_back_books: tuple[str, ...]
    practice_case_ids: tuple[str, ...]
    held_back_case_ids: tuple[str, ...]
    starting_skill_digest: str
    self_review_digest: str
    pass_mark: PassMark
    # 2: every comparison is paired in one session, and a pass must be confirmed.
    design_version: int = 1
    # Changes made after round 0 started. Only the self-review instructions may
    # change; the split, pass mark, model, and scored skill never do.
    amendments: tuple[dict[str, str], ...] = ()


class Decision(StrictModel):
    passed: bool
    practice_passes_baseline: int
    practice_passes_candidate: int
    practice_runs: int
    gain: int
    case_losses: dict[str, int] = Field(default_factory=dict)
    reasons: tuple[str, ...]
    execution_errors_candidate: int


def is_held_back(case: SerendipityEvalCase) -> bool:
    return any(f"-{book}-" in case.case_id for book in HELD_BACK_BOOKS)


def split_cases(
    cases: tuple[SerendipityEvalCase, ...],
) -> tuple[tuple[SerendipityEvalCase, ...], tuple[SerendipityEvalCase, ...]]:
    practice = tuple(case for case in cases if not is_held_back(case))
    held_back = tuple(case for case in cases if is_held_back(case))
    return practice, held_back


def pass_mark() -> PassMark:
    return PassMark(
        min_practice_gain=MIN_PRACTICE_GAIN,
        max_case_loss=MAX_CASE_LOSS,
        stable_floor=STABLE_FLOOR,
        description=(
            f"Scored in the same session as the production skill, a candidate passes when its "
            f"practice passes exceed production's by at least {MIN_PRACTICE_GAIN}, no practice case "
            f"loses more than {MAX_CASE_LOSS} passes, and no practice case that passed every "
            f"production run falls below {STABLE_FLOOR}. A pass counts only if a fresh paired "
            f"comparison passes again."
        ),
    )


def _execution_errors(report: ReliabilityReport) -> int:
    return sum(run.status == "execution_error" for case in report.cases for run in case.runs)


def decide(baseline: ReliabilityReport, candidate: ReliabilityReport) -> Decision:
    """Judge a candidate against round 0 by the pre-registered pass mark."""
    before = {case.case_id: case for case in baseline.cases}
    after = {case.case_id: case for case in candidate.cases}
    if before.keys() != after.keys():
        raise ValueError("baseline and candidate must score the same cases")
    gain = candidate.summary.total_passes - baseline.summary.total_passes
    losses = {
        case_id: before[case_id].passes - after[case_id].passes
        for case_id in sorted(before)
        if after[case_id].passes < before[case_id].passes
    }
    reasons: list[str] = []
    if gain < MIN_PRACTICE_GAIN:
        reasons.append(f"practice gain {gain} is below {MIN_PRACTICE_GAIN}")
    if heavy := sorted(case_id for case_id, loss in losses.items() if loss > MAX_CASE_LOSS):
        reasons.append(f"cases lost more than {MAX_CASE_LOSS} passes: {heavy}")
    if fallen := sorted(
        case_id for case_id, case in before.items()
        if case.passes == case.repeats and after[case_id].passes < STABLE_FLOOR
    ):
        reasons.append(f"stable cases fell below {STABLE_FLOOR}: {fallen}")
    return Decision(
        passed=not reasons,
        practice_passes_baseline=baseline.summary.total_passes,
        practice_passes_candidate=candidate.summary.total_passes,
        practice_runs=candidate.summary.total_runs,
        gain=gain,
        case_losses=losses,
        reasons=tuple(reasons) or ("meets the pass mark",),
        execution_errors_candidate=_execution_errors(candidate),
    )


def _evidence(case: SerendipityEvalCase) -> tuple[dict[str, Any], ...]:
    items = []
    for item in case.tool_evidence:
        data = item.model_dump(mode="json")
        for key in ("excerpt", "text"):
            if isinstance(data.get(key), str) and len(data[key]) > MAX_EXCERPT_CHARS:
                data[key] = data[key][:MAX_EXCERPT_CHARS] + " [...]"
        items.append(data)
    return tuple(items)


def traces(
    cases: tuple[SerendipityEvalCase, ...], report: ReliabilityReport,
) -> tuple[CaseTrace, ...]:
    """Every practice case and its runs; a case that always passed shows one run."""
    by_id = {case.case_id: case for case in cases}
    result = []
    for scored in report.cases:
        case = by_id[scored.case_id]
        runs = scored.runs if scored.passes < scored.repeats else scored.runs[:1]
        result.append(CaseTrace(
            case_id=case.case_id,
            behavior=case.primary_behavior,
            tier=case.tier,
            description=case.description,
            task=case.input.model_dump(mode="json"),
            evidence=_evidence(case),
            book_judgement=case.book_judgement.model_dump(mode="json") if case.book_judgement else None,
            expected_searches=case.expected_searches.model_dump(mode="json"),
            expected=case.expected.model_dump(mode="json"),
            passes=scored.passes,
            repeats=scored.repeats,
            runs=tuple(
                ObservedRun(
                    passed=run.hard_pass,
                    status=run.status,
                    decline_reason=run.decline_reason,
                    searches=run.searches,
                    response=run.response,
                    failures=run.failures,
                )
                for run in runs
            ),
        ))
    return tuple(result)


def candidate_skill(instructions: str) -> RuntimeSkill:
    return replace(CONNECTION_DISCOVERY, instructions=instructions)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _load_report(path: Path) -> ReliabilityReport | None:
    if not path.exists():
        return None
    return ReliabilityReport.model_validate_json(path.read_text(encoding="utf-8"))


async def _score(
    path: Path,
    cases: tuple[SerendipityEvalCase, ...],
    skill: RuntimeSkill,
    *,
    repeats: int,
    concurrency: int,
) -> ReliabilityReport:
    if (existing := _load_report(path)) is not None:
        print(f"reusing {path}", flush=True)
        return existing
    print(f"scoring {len(cases)} cases x {repeats} -> {path}", flush=True)
    report = await run_reliability_experiment(
        repeats=repeats, cases=cases, concurrency=concurrency, discovery_skill=skill,
    )
    _write(path, report.model_dump_json(indent=2))
    return report


async def _score_pair(
    directory: Path,
    name: str,
    cases: tuple[SerendipityEvalCase, ...],
    candidate: RuntimeSkill,
    *,
    repeats: int,
    concurrency: int,
) -> tuple[ReliabilityReport, ReliabilityReport]:
    """Score production and the candidate in one session, alternating their runs."""
    paths = (directory / f"{name}-production.json", directory / f"{name}-candidate.json")
    loaded = tuple(_load_report(path) for path in paths)
    if all(report is not None for report in loaded):
        print(f"reusing {directory}/{name}-*", flush=True)
        return loaded  # type: ignore[return-value]
    print(f"scoring {len(cases)} cases x {repeats}, production and candidate -> {directory}/{name}-*", flush=True)
    reports = await run_paired_reliability(
        {"production": CONNECTION_DISCOVERY, "candidate": candidate},
        repeats=repeats, cases=cases, concurrency=concurrency,
    )
    for path, key in zip(paths, ("production", "candidate")):
        _write(path, reports[key].model_dump_json(indent=2))
    return reports["production"], reports["candidate"]


async def _review(
    round_dir: Path, task: SelfReviewInput,
) -> SkillCorrection | None:
    path = round_dir / "correction.json"
    if path.exists():
        return SkillCorrection.model_validate_json(path.read_text(encoding="utf-8"))
    _write(round_dir / "review-input.json", task.model_dump_json(indent=2))
    errors = []
    for attempt in range(1, REVIEW_ATTEMPTS + 1):
        print(f"self-review attempt {attempt}", flush=True)
        with capture_run_messages() as messages:
            try:
                correction = await propose_skill_correction(task)
            except Exception as error:  # recorded, then one fresh attempt
                errors.append({
                    "attempt": attempt,
                    "error": f"{type(error).__name__}: {error}",
                    "retry_prompts": [
                        str(part.content) for message in messages for part in message.parts
                        if isinstance(part, RetryPromptPart)
                    ],
                    "last_output": next(
                        (part.args for message in reversed(messages) for part in message.parts
                         if isinstance(part, ToolCallPart)),
                        None,
                    ),
                })
                _write(round_dir / "review-errors.json", json.dumps(errors, indent=2, default=str))
                continue
        _write(path, correction.model_dump_json(indent=2))
        return correction
    return None


def _summary_markdown(
    protocol: Protocol,
    baseline: ReliabilityReport,
    rounds: list[dict[str, Any]],
    held_back: dict[str, Any] | None,
) -> str:
    lines = [
        "# Serendipity self-improvement loop",
        "",
        f"Model `{protocol.model}`, {protocol.repeats} repeats per case. "
        f"Practice {len(protocol.practice_case_ids)} cases; held back "
        f"{len(protocol.held_back_case_ids)} cases ({', '.join(protocol.held_back_books)}).",
        "",
        f"Pass mark: {protocol.pass_mark.description}",
        "",
        f"Round 0 (production skill, traces for the review): {baseline.summary.total_passes} of "
        f"{baseline.summary.total_runs} practice runs.",
        "",
        "| Round | Target failure | Production | Candidate | Gain | Decision | Confirmation |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in rounds:
        decision = item.get("decision")
        if decision is None:
            lines.append(f"| {item['round']} | — | — | — | — | {item['outcome']} | — |")
            continue
        confirm = item.get("confirmation")
        confirm_text = "—" if confirm is None else (
            f"{confirm['practice_passes_baseline']} → {confirm['practice_passes_candidate']} "
            f"({confirm['gain']:+d}): {'confirmed' if confirm['passed'] else 'not confirmed'}"
        )
        lines.append(
            f"| {item['round']} | {item['target']} | {decision['practice_passes_baseline']} | "
            f"{decision['practice_passes_candidate']} | {decision['gain']:+d} | "
            f"{'pass' if decision['passed'] else 'fail: ' + '; '.join(decision['reasons'])} | {confirm_text} |"
        )
    if held_back:
        lines += [
            "",
            f"Held-back cases, same session: {held_back['baseline']} of {held_back['runs']} with the production "
            f"skill, {held_back['candidate']} of {held_back['runs']} with the confirmed candidate.",
        ]
    return "\n".join(lines) + "\n"


async def run_loop(
    output_dir: Path, *, repeats: int = 5, concurrency: int = 2, max_rounds: int = MAX_ROUNDS,
    amendment: str | None = None,
) -> dict[str, Any]:
    cases = load_serendipity_eval_cases()
    practice, held_back = split_cases(cases)
    protocol_path = output_dir / "protocol.json"
    protocol = Protocol(
        model=get_settings().linger_model,
        repeats=repeats,
        max_rounds=max_rounds,
        held_back_books=HELD_BACK_BOOKS,
        practice_case_ids=tuple(case.case_id for case in practice),
        held_back_case_ids=tuple(case.case_id for case in held_back),
        starting_skill_digest=CONNECTION_DISCOVERY.fingerprint().digest,
        self_review_digest=SELF_REVIEW_FINGERPRINT.digest,
        pass_mark=pass_mark(),
        design_version=2,
    )
    if protocol_path.exists():
        recorded = Protocol.model_validate_json(protocol_path.read_text(encoding="utf-8"))
        fixed = {"self_review_digest", "amendments"}
        if recorded.model_dump(exclude=fixed) != protocol.model_dump(exclude=fixed):
            raise SystemExit(f"{protocol_path} records a different protocol; use a new output directory")
        if recorded.self_review_digest != protocol.self_review_digest:
            if not amendment:
                raise SystemExit("the self-review instructions changed; pass --amendment with the reason")
            recorded = recorded.model_copy(update={
                "self_review_digest": protocol.self_review_digest,
                "amendments": (*recorded.amendments, {
                    "date": datetime.now(UTC).isoformat(timespec="seconds"),
                    "field": "self_review_digest",
                    "old": recorded.self_review_digest,
                    "new": protocol.self_review_digest,
                    "reason": amendment,
                }),
            })
            _write(protocol_path, recorded.model_dump_json(indent=2))
        protocol = recorded
    else:
        _write(protocol_path, protocol.model_dump_json(indent=2))

    configure_component_evaluation_telemetry(serendipity_agent)
    baseline = await _score(
        output_dir / "round-0" / "practice.json", practice, CONNECTION_DISCOVERY,
        repeats=repeats, concurrency=concurrency,
    )

    best_instructions, best_report, best_gain = CONNECTION_DISCOVERY.instructions, baseline, 0
    earlier: list[EarlierRound] = []
    rounds: list[dict[str, Any]] = []
    winner: str | None = None
    for number in range(1, max_rounds + 1):
        round_dir = output_dir / f"round-{number}"
        task = SelfReviewInput(
            skill_name=CONNECTION_DISCOVERY.name,
            current_instructions=best_instructions,
            cases=traces(practice, best_report),
            earlier_rounds=tuple(earlier),
        )
        correction = await _review(round_dir, task)
        if correction is None:
            rounds.append({"round": number, "outcome": "no valid correction after two attempts"})
            break
        instructions = apply_edits(best_instructions, correction.edits)
        _write(round_dir / "candidate-SKILL.md", instructions + "\n")
        candidate = candidate_skill(instructions)
        production, scored = await _score_pair(
            round_dir, "practice", practice, candidate, repeats=repeats, concurrency=concurrency,
        )
        decision = decide(production, scored)
        _write(round_dir / "decision.json", decision.model_dump_json(indent=2))
        item: dict[str, Any] = {
            "round": number, "target": correction.target_category,
            "decision": decision.model_dump(mode="json"), "outcome": "pass" if decision.passed else "fail",
        }
        confirmed = False
        if decision.passed:
            again_base, again = await _score_pair(
                round_dir, "confirm", practice, candidate, repeats=repeats, concurrency=concurrency,
            )
            confirmation = decide(again_base, again)
            _write(round_dir / "confirm-decision.json", confirmation.model_dump_json(indent=2))
            item["confirmation"] = confirmation.model_dump(mode="json")
            confirmed = confirmation.passed
            item["outcome"] = "confirmed" if confirmed else "not confirmed"
        rounds.append(item)
        earlier.append(EarlierRound(
            round=number,
            categories=correction.categories,
            target_category=correction.target_category,
            edits=correction.edits,
            expected_fixes=correction.expected_fixes,
            practice_passes_before=production.summary.total_passes,
            practice_passes_after=scored.summary.total_passes,
            practice_runs=scored.summary.total_runs,
            outcome=(
                "passed and was confirmed" if confirmed
                else "passed but was not confirmed in a fresh comparison" if decision.passed
                else "kept as the new starting point" if decision.gain > best_gain
                else "discarded; the next round starts from the earlier instructions"
            ),
        ))
        if decision.gain > best_gain:
            best_instructions, best_report, best_gain = instructions, scored, decision.gain
        if confirmed:
            winner = instructions
            break

    held_back_result = None
    if winner is not None:
        held_base, held_cand = await _score_pair(
            output_dir / "final", "held-back", held_back, candidate_skill(winner),
            repeats=repeats, concurrency=concurrency,
        )
        _write(output_dir / "final" / "candidate-SKILL.md", winner + "\n")
        held_back_result = {
            "baseline": held_base.summary.total_passes,
            "candidate": held_cand.summary.total_passes,
            "runs": held_cand.summary.total_runs,
            "case_changes": {
                case.case_id: after.passes - case.passes
                for case, after in zip(held_base.cases, held_cand.cases)
                if after.passes != case.passes
            },
        }
    summary = {
        "protocol": protocol.model_dump(mode="json"),
        "baseline_practice_passes": baseline.summary.total_passes,
        "baseline_practice_runs": baseline.summary.total_runs,
        "rounds": rounds,
        "held_back": held_back_result,
        "promotion": "awaiting owner approval" if winner is not None else "no candidate confirmed",
    }
    _write(output_dir / "summary.json", json.dumps(summary, indent=2))
    _write(output_dir / "summary.md", _summary_markdown(protocol, baseline, rounds, held_back_result))
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--max-rounds", type=int, default=MAX_ROUNDS)
    parser.add_argument("--amendment", help="why the self-review instructions changed mid-run")
    return parser


def main() -> None:
    args = _parser().parse_args()
    summary = asyncio.run(run_loop(
        args.output_dir, repeats=args.repeat, concurrency=args.concurrency, max_rounds=args.max_rounds,
        amendment=args.amendment,
    ))
    print((args.output_dir / "summary.md").read_text(encoding="utf-8"))
    print(json.dumps({"promotion": summary["promotion"]}))


if __name__ == "__main__":
    main()
