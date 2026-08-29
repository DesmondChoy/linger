"""Shared plumbing for Provenance live case packs.

Holds only what every pack does identically: the strict base model, the timed
invocation loop that converts an exception into a redacted grade, and the CLI
that writes a report and fails the command when targets do not pass. Case
contracts, grading rules, and metrics stay in each pack.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Reject unreviewed case and report schema drift."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Grade(Protocol):
    """The per-case verdict every pack's grade function returns."""

    passed: bool


class Report(Protocol):
    """A pack report whose summary decides the command's exit status."""

    summary: Any

    def model_dump_json(self, *, indent: int | None = None) -> str: ...


async def run_case[Case, GradeT: Grade](
    case: Case,
    invoke: Callable[[Case], Awaitable[object]],
    grade: Callable[[Case, object], GradeT],
    on_error: Callable[[], GradeT],
) -> tuple[GradeT, str | None, float]:
    """Invoke and grade one case, returning the error type instead of raising."""
    started = perf_counter()
    try:
        return grade(case, await invoke(case)), None, _elapsed_ms(started)
    except Exception as exc:  # Report failure metadata without retaining content.
        return on_error(), type(exc).__name__, _elapsed_ms(started)


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1_000, 1)


def run_report_command(
    build_report: Callable[[], Awaitable[Report]],
    default_report: Path,
    description: str | None = None,
) -> None:
    """Write a report to `--report` and exit nonzero unless its targets pass."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--report", type=Path, default=default_report)
    args = parser.parse_args()

    report = asyncio.run(build_report())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(report.summary.model_dump_json(indent=2), flush=True)
    if not report.summary.targets_pass:
        raise SystemExit(1)
