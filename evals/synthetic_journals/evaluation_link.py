"""Expose one evaluation's Logfire location without changing its outcome."""

from __future__ import annotations

import json
import sys
from typing import Any

import logfire
from pydantic_evals.reporting import EvaluationReport

LOGFIRE_MARKER = "SYNTHETIC_EVALUATION_LOGFIRE="


def emit_evaluation_link(report: EvaluationReport[Any, Any, Any]) -> None:
    """Print machine-readable telemetry status, including for failed cases."""

    status: dict[str, str | bool | None] = {
        "url": None,
        "trace_id": report.trace_id,
        "span_id": report.span_id,
        "flushed": False,
    }
    errors: list[str] = []
    try:
        status["url"] = logfire.url_from_eval(report)
    except Exception as error:
        errors.append(f"url_from_eval: {type(error).__name__}")
    try:
        status["flushed"] = logfire.force_flush()
    except Exception as error:
        errors.append(f"force_flush: {type(error).__name__}")
    if errors:
        status["error"] = "; ".join(errors)
    print(LOGFIRE_MARKER + json.dumps(status), file=sys.stderr, flush=True)
