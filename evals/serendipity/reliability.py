"""Repeated-run reliability experiment for the Serendipity component suite.

The component suite runs each case once, so a green report is a single sample
rather than a rate.  Because the agent's decision is model-sampled, a case can
pass now and fail on the next identical run — and for Serendipity that risk is
structural rather than incidental: an eligible candidate occupies one of only
four rubric strength positions, so two plausible candidates frequently land in
the same position, and a candidate sitting on a position boundary can flip the
whole decision between a proposal and a decline.

This experiment holds everything constant except model sampling and asks one
question: which cases are actually stable?

Method
------
One agent is built once and reused for every run, so instructions, contracts,
tool permissions and retry budgets are identical across repeats.  Each case is
executed `--repeat` times against its own fixture evidence.  The report records
the per-run verdicts and derives:

* ``pass_at_k``  — the case passed at least once   (capability)
* ``pass_pow_k`` — the case passed every time      (reliability)

The gap between them is the result.  A case that is ``pass_at_k`` but not
``pass_pow_k`` is unstable, and the suite's usual single-run report would show
it as green or red depending only on which sample it happened to draw.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from uuid import uuid4

from pydantic import Field

from apps.backend.config import get_settings
from apps.backend.telemetry import configure_component_evaluation_telemetry
from src.linger.agents.contracts import StrictModel
from src.linger.agents.serendipity.agent import build_serendipity_agent
from src.linger.agents.serendipity.prompt import (
    MEMORY_RECALL_PROMPT_FINGERPRINT,
    PROMPT_FINGERPRINT,
)
from src.linger.agents.serendipity.skills import CONNECTION_DISCOVERY, MEMORY_RECALL

from .harness import SerendipityEvalCase, dataset_digest, load_serendipity_eval_cases
from .runner import _skill_for, run_case

EXECUTION_ERROR = "execution_error"


class RunOutcome(StrictModel):
    """One execution of one case."""

    hard_pass: bool
    status: str
    decline_reason: str | None = None
    failures: tuple[str, ...] = ()
    latency_seconds: float | None = None
    model_requests: int | None = None
    tool_calls: int | None = None


class CaseReliability(StrictModel):
    """Repeated-run behaviour of a single case."""

    case_id: str
    primary_behavior: str
    contrast_group: str
    tier: str = "regression"
    repeats: int = Field(ge=1)
    passes: int = Field(ge=0)
    pass_at_k: bool
    pass_pow_k: bool
    unstable: bool
    decision_unstable: bool
    observed_statuses: tuple[str, ...]
    intermittent_failures: tuple[str, ...] = ()
    mean_latency_seconds: float | None = None
    mean_model_requests: float | None = None
    runs: tuple[RunOutcome, ...]


class ReliabilitySummary(StrictModel):
    """Pass rates for one group of cases: the whole run, or one tier of it."""

    case_count: int
    repeats: int
    total_runs: int
    total_passes: int
    run_pass_rate: float
    cases_pass_pow_k: int
    cases_unstable: int
    cases_never_passed: int
    cases_with_unstable_decision: int
    suite_pass_pow_k: bool


class ReliabilityReport(StrictModel):
    """Durable record of one reliability experiment."""

    schema_version: int = 2
    experiment: str = "serendipity-component-reliability"
    run_id: str
    generated_at: datetime
    model: str
    # The skill and prompt digest each run actually used, keyed by skill id.
    # Production picks the skill from the intent, so one run can use both.
    prompt_digests: dict[str, str]
    dataset_digest: str
    concurrency: int
    summary: ReliabilitySummary
    # Regression cases should stay near 100%; capability cases are expected
    # to start low. Reporting them together would let one hide the other.
    tiers: dict[str, ReliabilitySummary]
    cases: tuple[CaseReliability, ...]


def _outcome_from_report(report: object) -> RunOutcome:
    """Project a CaseRunReport into the fields this experiment compares."""
    grade = report.grade  # type: ignore[attr-defined]
    observation = report.observation  # type: ignore[attr-defined]
    response = observation.response
    status = str(response.get("status", "unknown"))
    reason = response.get("reason")
    return RunOutcome(
        hard_pass=grade.hard_pass,
        status=status,
        decline_reason=str(reason) if isinstance(reason, str) else None,
        failures=tuple(grade.failures),
        latency_seconds=observation.latency_seconds,
        model_requests=observation.model_requests,
        tool_calls=observation.tool_calls,
    )


PROMPT_DIGESTS = {
    CONNECTION_DISCOVERY.skill_id: PROMPT_FINGERPRINT.digest,
    MEMORY_RECALL.skill_id: MEMORY_RECALL_PROMPT_FINGERPRINT.digest,
}


def _summarise(results: tuple[CaseReliability, ...], repeats: int) -> ReliabilitySummary:
    total_runs = len(results) * repeats
    total_passes = sum(item.passes for item in results)
    return ReliabilitySummary(
        case_count=len(results),
        repeats=repeats,
        total_runs=total_runs,
        total_passes=total_passes,
        run_pass_rate=round(total_passes / total_runs, 4) if total_runs else 0.0,
        cases_pass_pow_k=sum(item.pass_pow_k for item in results),
        cases_unstable=sum(item.unstable for item in results),
        cases_never_passed=sum(not item.pass_at_k for item in results),
        cases_with_unstable_decision=sum(item.decision_unstable for item in results),
        suite_pass_pow_k=all(item.pass_pow_k for item in results),
    )


def _summarise_case(
    case: SerendipityEvalCase,
    outcomes: tuple[RunOutcome, ...],
) -> CaseReliability:
    passes = sum(outcome.hard_pass for outcome in outcomes)
    repeats = len(outcomes)
    statuses = tuple(dict.fromkeys(outcome.status for outcome in outcomes))
    # A failure that appears in some runs but not all is the actionable signal:
    # it is a real defect that a single-run report would hide half the time.
    counts = Counter(
        failure for outcome in outcomes for failure in set(outcome.failures)
    )
    intermittent = tuple(
        sorted(reason for reason, count in counts.items() if count < repeats)
    )
    latencies = [o.latency_seconds for o in outcomes if o.latency_seconds is not None]
    requests = [o.model_requests for o in outcomes if o.model_requests is not None]
    return CaseReliability(
        case_id=case.case_id,
        primary_behavior=case.primary_behavior,
        contrast_group=case.contrast_group,
        tier=case.tier,
        repeats=repeats,
        passes=passes,
        pass_at_k=passes >= 1,
        pass_pow_k=passes == repeats,
        unstable=0 < passes < repeats,
        decision_unstable=len(statuses) > 1,
        observed_statuses=statuses,
        intermittent_failures=intermittent,
        mean_latency_seconds=round(fmean(latencies), 3) if latencies else None,
        mean_model_requests=round(fmean(requests), 2) if requests else None,
        runs=outcomes,
    )


async def run_reliability_experiment(
    *,
    repeats: int = 5,
    cases: tuple[SerendipityEvalCase, ...] | None = None,
    case_ids: tuple[str, ...] = (),
    tier: str | None = None,
    concurrency: int = 1,
    configure_logfire: bool = True,
) -> ReliabilityReport:
    """Execute every selected case `repeats` times through one shared agent."""
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    active = cases or load_serendipity_eval_cases()
    if case_ids:
        wanted = set(case_ids)
        active = tuple(case for case in active if case.case_id in wanted)
        missing = wanted - {case.case_id for case in active}
        if missing:
            raise ValueError(f"unknown case ids: {sorted(missing)}")
    if tier is not None:
        active = tuple(case for case in active if case.tier == tier)
    if not active:
        raise ValueError("no cases selected")

    agent = build_serendipity_agent()
    if configure_logfire:
        configure_component_evaluation_telemetry(agent)
    limiter = asyncio.Semaphore(concurrency)

    async def one_run(case: SerendipityEvalCase) -> RunOutcome:
        async with limiter:
            try:
                report = await run_case(case, agent=agent)
            except Exception as error:  # an error is a failure, never a gap
                return RunOutcome(
                    hard_pass=False,
                    status=EXECUTION_ERROR,
                    failures=(f"{EXECUTION_ERROR}: {type(error).__name__}: {error}",),
                )
            return _outcome_from_report(report)

    results: list[CaseReliability] = []
    for case in active:
        outcomes = await asyncio.gather(*(one_run(case) for _ in range(repeats)))
        summary = _summarise_case(case, tuple(outcomes))
        results.append(summary)
        print(_case_line(summary), flush=True)

    used = sorted({_skill_for(case).skill_id for case in active})
    return ReliabilityReport(
        run_id=uuid4().hex,
        generated_at=datetime.now(UTC),
        model=get_settings().linger_model,
        prompt_digests={skill_id: PROMPT_DIGESTS[skill_id] for skill_id in used},
        dataset_digest=dataset_digest(active),
        concurrency=concurrency,
        summary=_summarise(tuple(results), repeats),
        tiers={
            name: _summarise(tuple(item for item in results if item.tier == name), repeats)
            for name in sorted({item.tier for item in results})
        },
        cases=tuple(results),
    )


def _case_line(case: CaseReliability) -> str:
    bar = "".join("+" if run.hard_pass else "." for run in case.runs)
    if case.pass_pow_k:
        mark = "stable "
    elif case.pass_at_k:
        mark = "UNSTABLE"
    else:
        mark = "failing"
    return f"  {mark}  {case.passes}/{case.repeats}  [{bar}]  {case.case_id}"


def _print_summary(report: ReliabilityReport) -> None:
    s = report.summary
    print()
    prompts = ", ".join(f"{skill} {digest[:8]}" for skill, digest in report.prompt_digests.items())
    print(f"model {report.model} · prompts {prompts} · dataset {report.dataset_digest[:12]}")
    print(f"{s.case_count} cases × {s.repeats} repeats = {s.total_runs} runs")
    print()
    print(f"  pass^k  (passed every run) : {s.cases_pass_pow_k}/{s.case_count} cases")
    print(f"  unstable (flipped)         : {s.cases_unstable}/{s.case_count} cases")
    print(f"  never passed               : {s.cases_never_passed}/{s.case_count} cases")
    print(f"  decision flipped           : {s.cases_with_unstable_decision}/{s.case_count} cases")
    print(f"  run pass rate              : {s.run_pass_rate:.0%}")
    for name, tier in report.tiers.items():
        print(
            f"  {name:<27}: {tier.cases_pass_pow_k}/{tier.case_count} cases stable, "
            f"{tier.total_passes}/{tier.total_runs} runs"
        )
    print()
    unstable = [case for case in report.cases if case.unstable]
    if unstable:
        print("Unstable cases — a single-run report shows these green or red by luck:")
        for case in unstable:
            print(f"  {case.case_id}  ({case.passes}/{case.repeats})")
            print(f"    behaviour: {case.primary_behavior}")
            print(f"    decisions seen: {', '.join(case.observed_statuses)}")
            for reason in case.intermittent_failures:
                print(f"    intermittent: {reason}")
    else:
        print("No case flipped. The suite's single-run result is reproducible at this k.")
    print()
    verdict = "REPRODUCIBLE" if s.suite_pass_pow_k else "NOT REPRODUCIBLE"
    print(f"Suite pass^{s.repeats}: {verdict}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=5, help="runs per case (default 5)")
    parser.add_argument(
        "--case", action="append", default=[], dest="case_ids",
        help="limit to this case id; repeatable",
    )
    parser.add_argument(
        "--tier", choices=("regression", "capability"),
        help="run only regression (should stay green) or capability (hard) cases",
    )
    parser.add_argument(
        "--concurrency", type=int, default=1,
        help="parallel runs; above 1 makes latency figures unreliable (default 1)",
    )
    parser.add_argument("--no-logfire", action="store_true")
    return parser


async def _main() -> None:
    args = _parser().parse_args()
    report = await run_reliability_experiment(
        repeats=args.repeat,
        case_ids=tuple(args.case_ids),
        tier=args.tier,
        concurrency=args.concurrency,
        configure_logfire=not args.no_logfire,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    _print_summary(report)
    print(f"\nreport: {args.output}")


if __name__ == "__main__":
    asyncio.run(_main())
