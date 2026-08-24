"""Policy-separated Logfire tracing for runtime and synthetic evaluation.

Automatic FastAPI and Pydantic AI instrumentation expose fields outside
Linger's telemetry contract, including endpoint arguments, raw URLs, prompt
instructions, and exception messages. Human runtime traffic therefore emits
only explicit application-owned spans and attributes. The synthetic replay
runner may explicitly enable content-bearing Pydantic AI instrumentation under
the separate evaluation service.
"""

import asyncio
from collections.abc import Callable, Mapping, Sequence
from contextvars import ContextVar
from typing import Any, Literal

import logfire
from opentelemetry.trace import format_span_id, format_trace_id

from src.linger.agents.provenance.models import ProvenanceReview
from src.linger.agents.serendipity.models import ConnectionDiscoveryInput
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.evaluation_transcript import active_evaluation_transcript_sink

from .config import get_settings
from .contracts import EvidenceBundle, LibrarianRequest

SERVICE_NAME = "linger-backend"
EVALUATION_SERVICE_NAME = "linger-evals"
EVALUATION_AGENT_NAMES = frozenset(
    {"Muse", "Provenance", "Librarian", "Serendipity", "Sculptor"}
)
AgentRole = Literal[
    "Application",
    "Muse",
    "Provenance",
    "Librarian",
    "Serendipity",
    "Sculptor",
]
_ACTIVE_AGENT_ROLE: ContextVar[AgentRole | None] = ContextVar(
    "linger_active_agent_role",
    default=None,
)


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


def configure_synthetic_evaluation_telemetry(agents: Sequence[Any]) -> None:
    """Enable native AI panels only for the explicit synthetic replay process."""

    agent_names = {getattr(agent, "name", None) for agent in agents}
    if agent_names != EVALUATION_AGENT_NAMES:
        raise ValueError(
            "synthetic evaluation instrumentation requires the five named agents"
        )

    token = get_settings().logfire_token
    logfire.configure(
        token=token.get_secret_value() if token else None,
        send_to_logfire="if-token-present",
        service_name=EVALUATION_SERVICE_NAME,
        environment="synthetic-evaluation",
        resource_attributes={
            "content.classification": "synthetic",
            "linger.telemetry.mode": "synthetic_evaluation",
        },
        console=False,
        inspect_arguments=False,
        distributed_tracing=False,
    )
    for agent in agents:
        logfire.instrument_pydantic_ai(
            agent,
            include_content=True,
            include_binary_content=False,
            include_model_request_parameters=False,
            version=5,
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
    prompt_version: str,
    prompt_digest: str,
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
        "prompt.digest": prompt_digest,
        "status": "started",
        "retry_count": 0,
    }


def handoff_attrs(
    *,
    role: AgentRole,
    input_origin: AgentRole,
    output_receiver: AgentRole,
    input_contract: str,
    output_contract: str,
) -> dict[str, object]:
    """Fixed logical routing around one application-mediated agent call."""

    return {
        "handoff.input.origin": input_origin,
        "handoff.input.receiver": role,
        "handoff.input.contract": input_contract,
        "handoff.output.origin": role,
        "handoff.output.receiver": output_receiver,
        "handoff.output.contract": output_contract,
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
    role: AgentRole,
    stage: str,
    input_contract: str,
    output_contract: str,
    prompt_template_id: str,
    prompt_version: str,
    prompt_digest: str,
    failure_code: str,
    input_origin: AgentRole | None = None,
    output_receiver: AgentRole | None = None,
    retryable: bool = True,
    result_attrs: Callable[[Any], Mapping[str, object | None]] | None = None,
    **run_kwargs: Any,
) -> Any:
    """Run one agent without allowing its prompt or exception into telemetry.

    Exceptions are re-raised only after the span closes, so Logfire never
    receives their messages or stack traces.
    """
    caller_role = _ACTIVE_AGENT_ROLE.get()
    resolved_input_origin = input_origin or caller_role or "Application"
    resolved_output_receiver = output_receiver or caller_role or "Application"
    cancelled = False
    caught: Exception | None = None
    result: Any = None
    transcript_status = "failure"
    transcript_failure_code: str | None = failure_code
    transcript_sink = active_evaluation_transcript_sink()
    transcript_handle: object | None = None
    with logfire.span(
        span_name,
        **agent_attrs(
            role=role,
            stage=stage,
            prompt_template_id=prompt_template_id,
            prompt_version=prompt_version,
            prompt_digest=prompt_digest,
        ),
        **handoff_attrs(
            role=role,
            input_origin=resolved_input_origin,
            output_receiver=resolved_output_receiver,
            input_contract=input_contract,
            output_contract=output_contract,
        ),
    ) as span:
        span_context = span.get_span_context()
        if transcript_sink is not None:
            transcript_handle = transcript_sink.begin_agent_exchange(
                role=role,
                stage=stage,
                input_origin=resolved_input_origin,
                output_receiver=resolved_output_receiver,
                input_contract=input_contract,
                output_contract=output_contract,
                prompt_template_id=prompt_template_id,
                prompt_version=prompt_version,
                prompt_digest=prompt_digest,
                input_prompt=prompt,
                message_history=run_kwargs.get("message_history", ()),
                trace_id=format_trace_id(span_context.trace_id),
                span_id=format_span_id(span_context.span_id),
            )
        role_token = _ACTIVE_AGENT_ROLE.set(role)
        try:
            result = await agent.run(prompt, **run_kwargs)
        except asyncio.CancelledError:
            cancelled = True
            transcript_status = "cancelled"
            transcript_failure_code = "request_cancelled"
            record_failure(
                span,
                stage=stage,
                code="request_cancelled",
                retryable=False,
                failure_type="application",
            )
        except Exception as exc:
            caught = exc
            transcript_failure_code = failure_code
            record_failure(
                span,
                stage=stage,
                code=failure_code,
                retryable=retryable,
                failure_type="model",
            )
        else:
            try:
                if result_attrs is not None:
                    set_span_attrs(span, result_attrs(result))
            except Exception:
                transcript_failure_code = "agent_result_projection_failed"
                record_failure(
                    span,
                    stage=stage,
                    code="agent_result_projection_failed",
                    retryable=False,
                    failure_type="application",
                )
            else:
                _record_agent_success(span, result)
                transcript_status = "success"
                transcript_failure_code = None
        finally:
            _ACTIVE_AGENT_ROLE.reset(role_token)

    if transcript_sink is not None and transcript_handle is not None:
        transcript_sink.complete_agent_exchange(
            transcript_handle,
            result=result,
            status=transcript_status,
            failure_code=transcript_failure_code,
        )

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
        "provenance.emotional_boundary_decision": (
            review.emotional_boundary_decision
        ),
        "provenance.capture_decision": review.capture_decision,
        "provenance.finding_codes": [finding.code for finding in review.findings],
        "provenance.finding_count": len(review.findings),
    }


def emotional_boundary_attrs(
    assessment: EmotionalBoundaryAssessment,
) -> dict[str, object]:
    """Fixed preflight decision with no current-Line or rationale content."""
    return {"provenance.preflight_decision": assessment.decision}
