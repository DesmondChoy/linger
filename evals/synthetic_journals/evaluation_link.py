"""Expose one evaluation's Logfire location without changing its outcome."""

from __future__ import annotations

import json
import sys
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import logfire
from pydantic_evals.reporting import EvaluationReport

LOGFIRE_MARKER = "SYNTHETIC_EVALUATION_LOGFIRE="


def emit_evaluation_link(
    report: EvaluationReport[Any, Any, Any], *, dataset_name: str
) -> None:
    """Print machine-readable telemetry status, including for failed cases."""

    status: dict[str, str | bool | None] = {
        "url": None,
        "trace_id": report.trace_id,
        "span_id": report.span_id,
        "flushed": False,
    }
    errors: list[str] = []
    try:
        url = logfire.url_from_eval(report)
        if url is not None:
            parts = urlsplit(url)
            dataset_path = f"/evals/{quote(dataset_name, safe='')}/compare"
            if (
                parts.path.endswith("/evals/compare")
                and not parts.path.endswith(dataset_path)
            ):
                path = parts.path.removesuffix("/evals/compare") + dataset_path
                url = urlunsplit(parts._replace(path=path))
        status["url"] = url
    except Exception as error:
        errors.append(f"url_from_eval: {type(error).__name__}")
    try:
        status["flushed"] = logfire.force_flush()
    except Exception as error:
        errors.append(f"force_flush: {type(error).__name__}")
    if errors:
        status["error"] = "; ".join(errors)
    print(LOGFIRE_MARKER + json.dumps(status), file=sys.stderr, flush=True)
