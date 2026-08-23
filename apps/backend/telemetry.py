"""Metadata-only Logfire tracing for the agent pipeline.

Automatic FastAPI and Pydantic AI instrumentation expose fields outside
Linger's telemetry contract, including endpoint arguments, raw URLs, prompt
instructions, and exception messages. Linger therefore emits only explicit
application-owned spans and attributes from this module.
"""

import asyncio
from collections.abc import Callable, Mapping
from typing import Any

import logfire

from src.linger.agents.provenance.models import ProvenanceReview
from src.linger.agents.serendipity.models import ConnectionDiscoveryInput

from .config import get_settings
from .contracts import EvidenceBundle, LibrarianRequest

SERVICE_NAME = "linger-backend"
PROMPT_VERSION = "1"


def configure_telemetry() -> None:
    """Configure Logfire without enabling content-bearing auto-instrumentation."""
    token = get_settings().logfire_token
    logfire.configure(
        token=token.get_secret_value() if token else None,
        send_to_logfire="if-token-present",
        service_name=SERVICE_NAME,
        console=False,
        inspect_arguments=False,
        distributed_tracing=False,
    )


def set_span_attrs(span: Any, attributes: Mapping[str, object | None]) -> None:
    """Set only populated attributes on a Logfire span."""
    for name, value in attributes.items():
        if value is not None:
            span.set_attribute(name, value)


def agent_attrs(
    *,
    role: str,
    stage: str,
    prompt_template_id: str,
    prompt_version: str = PROMPT_VERSION,
) -> dict[str, object]:
    """Stable agent metadata; no composed prompt or model content."""
    provider, separator, model = get_settings().linger_model.partition(":")
    if not separator:
        model = provider
        provider = "unknown"
    return {
        "agent.role": role,
        "agent.stage": stage,
        "model.provider": provider,
        "model.name": model,
        "prompt.template_id": prompt_template_id,
        "prompt.version": prompt_version,
        "status": "started",
        "retry_count": 0,
    }


def failure_attrs(
    *,
    stage: str,
    code: str,
    retryable: bool,
    failure_type: str,
) -> dict[str, object]:
    """Fixed failure metadata that never inspects an exception object."""
    return {
        "status": "failure",
        "failure.stage": stage,
        "failure.code": code,
        "failure.retryable": retryable,
        "failure.type": failure_type,
    }


def record_failure(
    span: Any,
    *,
    stage: str,
    code: str,
    retryable: bool,
    failure_type: str,
) -> None:
    set_span_attrs(
        span,
        failure_attrs(
            stage=stage,
            code=code,
            retryable=retryable,
            failure_type=failure_type,
        ),
    )


def _record_agent_success(span: Any, result: Any) -> None:
    span.set_attribute("status", "success")
    try:
        usage = getattr(result, "usage", None)
        if callable(usage):
            usage = usage()
    except Exception:
        # Usage is optional diagnostics; it must never break or leak a run.
        return
    if usage is None:
        return
    set_span_attrs(
        span,
        {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "cost.usd": (
                float(cost) if (cost := getattr(usage, "cost", None)) is not None else None
            ),
        },
    )


async def run_agent_traced(
    agent: Any,
    prompt: str,
    *,
    span_name: str,
    role: str,
    stage: str,
    prompt_template_id: str,
    failure_code: str,
    retryable: bool = True,
    result_attrs: Callable[[Any], Mapping[str, object | None]] | None = None,
    **run_kwargs: Any,
) -> Any:
    """Run one agent without allowing its prompt or exception into telemetry.

    Exceptions are re-raised only after the span closes, so Logfire never
    receives their messages or stack traces.
    """
    cancelled = False
    caught: Exception | None = None
    result: Any = None
    with logfire.span(
        span_name,
        **agent_attrs(
            role=role,
            stage=stage,
            prompt_template_id=prompt_template_id,
        ),
    ) as span:
        try:
            result = await agent.run(prompt, **run_kwargs)
            if result_attrs is not None:
                set_span_attrs(span, result_attrs(result))
        except asyncio.CancelledError:
            cancelled = True
            record_failure(
                span,
                stage=stage,
                code="request_cancelled",
                retryable=False,
                failure_type="application",
            )
        except Exception as exc:
            caught = exc
            record_failure(
                span,
                stage=stage,
                code=failure_code,
                retryable=retryable,
                failure_type="model",
            )
        else:
            _record_agent_success(span, result)

    if cancelled:
        raise asyncio.CancelledError
    if caught is not None:
        raise caught
    return result


def connection_scope_attrs(task: ConnectionDiscoveryInput) -> dict[str, object]:
    """Safe Serendipity scope; the reader's cue is deliberately absent."""
    attributes: dict[str, object] = {
        "tool.name": "serendipity_explore",
        "tool.retry_count": 0,
    }
    if task.scope.book_scopes:
        book_scope = task.scope.book_scopes[0]
        attributes["scope.work_id"] = book_scope.work_id
        attributes["scope.book_version_id"] = book_scope.book_version_id
        attributes["scope.chapter_max"] = book_scope.chapter_max
    return attributes


def librarian_request_attrs(request: LibrarianRequest) -> dict[str, object]:
    """Validated public-corpus scope without the reader-derived query."""
    return {
        "tool.name": "librarian_search",
        "tool.retry_count": 0,
        "scope.work_id": [scope.work_id for scope in request.book_scopes],
        "scope.book_version_id": [
            scope.book_version_id for scope in request.book_scopes
        ],
        "scope.chapter_max": [scope.chapter_max for scope in request.book_scopes],
    }


def evidence_attrs(bundle: EvidenceBundle) -> dict[str, object]:
    """Public evidence identifiers and count, never excerpts or notes."""
    return {
        "retrieval.item_count": len(bundle.items),
        "retrieval.evidence_ids": [item.evidence_id for item in bundle.items],
    }


def review_attrs(review: ProvenanceReview) -> dict[str, object]:
    """Fixed decisions and risk codes, never critique prose or quotations."""
    return {
        "provenance.response_decision": review.response_decision,
        "provenance.capture_decision": review.capture_decision,
        "provenance.finding_codes": [finding.code for finding in review.findings],
        "provenance.finding_count": len(review.findings),
    }
