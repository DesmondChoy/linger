"""Content-bearing transcript models for reviewed synthetic evaluations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import Field
from pydantic_core import to_jsonable_python
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ToolCallPart,
    ToolReturnPart,
)

from src.linger.agents.contracts import PromptFingerprint
from src.linger.evaluation_transcript import active_evaluation_correlation_id

from .models import StrictModel


class AgentUsage(StrictModel):
    input_tokens: int | None
    output_tokens: int | None
    requests: int | None
    cost_usd: Decimal | None


class ToolExchange(StrictModel):
    """One model-visible tool call and its returned payload."""

    tool_call_id: str
    tool_name: str
    arguments: Any
    result: Any | None
    outcome: str | None


class AgentExchange(StrictModel):
    """Complete observable input and output for one evaluated agent call."""

    sequence: int = Field(ge=1)
    role: str
    stage: str
    input_origin: str
    input_receiver: str
    output_origin: str
    output_receiver: str
    input_contract: str
    output_contract: str
    correlation_id: str | None = None
    prompt_fingerprint: PromptFingerprint
    input_prompt: str
    message_history: tuple[Any, ...]
    model_messages: tuple[Any, ...]
    output: Any | None
    tool_exchanges: tuple[ToolExchange, ...]
    usage: AgentUsage | None
    status: str
    failure_code: str | None
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    span_id: str = Field(pattern=r"^[0-9a-f]{16}$")


@dataclass
class _PendingExchange:
    sequence: int
    role: str
    stage: str
    input_origin: str
    output_receiver: str
    input_contract: str
    output_contract: str
    correlation_id: str | None
    prompt_fingerprint: PromptFingerprint
    input_prompt: str
    message_history: tuple[Any, ...]
    trace_id: str
    span_id: str
    completed: AgentExchange | None = None


class SceneTranscriptRecorder:
    """Invocation-ordered recorder bound explicitly around one synthetic Scene."""

    def __init__(self) -> None:
        self._pending: list[_PendingExchange] = []

    def begin_agent_exchange(
        self,
        *,
        role: str,
        stage: str,
        input_origin: str,
        output_receiver: str,
        input_contract: str,
        output_contract: str,
        prompt_template_id: str,
        prompt_version: str,
        prompt_digest: str,
        input_prompt: str,
        message_history: Any,
        trace_id: str,
        span_id: str,
    ) -> object:
        pending = _PendingExchange(
            sequence=len(self._pending) + 1,
            role=role,
            stage=stage,
            input_origin=input_origin,
            output_receiver=output_receiver,
            input_contract=input_contract,
            output_contract=output_contract,
            correlation_id=active_evaluation_correlation_id(),
            prompt_fingerprint=PromptFingerprint(
                template_id=prompt_template_id,
                version=prompt_version,
                digest=prompt_digest,
            ),
            input_prompt=input_prompt,
            message_history=tuple(message_history),
            trace_id=trace_id,
            span_id=span_id,
        )
        self._pending.append(pending)
        return pending

    def complete_agent_exchange(
        self,
        handle: object,
        *,
        result: Any | None,
        status: str,
        failure_code: str | None,
    ) -> None:
        if not isinstance(handle, _PendingExchange) or handle not in self._pending:
            raise ValueError("unknown evaluation transcript exchange")
        if handle.completed is not None:
            raise ValueError("evaluation transcript exchange completed twice")

        messages = tuple(result.new_messages()) if result is not None else ()
        handle.completed = AgentExchange(
            sequence=handle.sequence,
            role=handle.role,
            stage=handle.stage,
            input_origin=handle.input_origin,
            input_receiver=handle.role,
            output_origin=handle.role,
            output_receiver=handle.output_receiver,
            input_contract=handle.input_contract,
            output_contract=handle.output_contract,
            correlation_id=handle.correlation_id,
            prompt_fingerprint=handle.prompt_fingerprint,
            input_prompt=handle.input_prompt,
            message_history=_serialize_messages(handle.message_history),
            model_messages=_serialize_messages(messages),
            output=(
                to_jsonable_python(result.output, serialize_unknown=True)
                if result is not None
                else None
            ),
            tool_exchanges=_tool_exchanges(messages),
            usage=_usage(result),
            status=status,
            failure_code=failure_code,
            trace_id=handle.trace_id,
            span_id=handle.span_id,
        )

    @property
    def exchanges(self) -> tuple[AgentExchange, ...]:
        incomplete = [item.sequence for item in self._pending if item.completed is None]
        if incomplete:
            raise RuntimeError(
                f"incomplete evaluation transcript exchanges: {incomplete}"
            )
        return tuple(item.completed for item in self._pending if item.completed)


def _serialize_messages(messages: tuple[Any, ...]) -> tuple[Any, ...]:
    if not messages:
        return ()
    serialized = ModelMessagesTypeAdapter.dump_python(list(messages), mode="json")
    return tuple(
        {
            **message,
            "parts": tuple(
                part
                for part in message["parts"]
                if part.get("part_kind") != "thinking"
            ),
        }
        for message in serialized
    )


def _tool_exchanges(messages: tuple[Any, ...]) -> tuple[ToolExchange, ...]:
    calls: dict[str, ToolCallPart] = {}
    returns: dict[str, ToolReturnPart] = {}
    order: list[str] = []
    for message in messages:
        for part in message.parts:
            if isinstance(part, ToolCallPart):
                if part.tool_name == "final_result":
                    continue
                calls[part.tool_call_id] = part
                order.append(part.tool_call_id)
            elif isinstance(part, ToolReturnPart):
                if part.tool_name == "final_result":
                    continue
                returns[part.tool_call_id] = part

    return tuple(
        ToolExchange(
            tool_call_id=tool_call_id,
            tool_name=call.tool_name,
            arguments=to_jsonable_python(call.args, serialize_unknown=True),
            result=(
                to_jsonable_python(returned.content, serialize_unknown=True)
                if (returned := returns.get(tool_call_id)) is not None
                else None
            ),
            outcome=(returned.outcome if returned is not None else None),
        )
        for tool_call_id in order
        for call in (calls[tool_call_id],)
    )


def _usage(result: Any | None) -> AgentUsage | None:
    if result is None:
        return None
    value = getattr(result, "usage", None)
    value = value() if callable(value) else value
    if value is None:
        return None
    return AgentUsage(
        input_tokens=getattr(value, "input_tokens", None),
        output_tokens=getattr(value, "output_tokens", None),
        requests=getattr(value, "requests", None),
        cost_usd=getattr(value, "cost", None),
    )
