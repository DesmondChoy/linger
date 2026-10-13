"""Provider-boundary credential checks shared by Linger's reusable Agents."""

from __future__ import annotations

import copy
from dataclasses import fields, is_dataclass, replace
from typing import Any

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import (
    CompactionPart,
    ModelRequest,
    ModelResponse,
    NativeToolCallPart,
    NativeToolReturnPart,
    RetryPromptPart,
    SystemPromptPart,
    TextContent,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.tools import RunContext, ToolDefinition

from src.linger.contracts.security_validation import (
    SecurityValidationBlocked,
    ValidationBoundary,
    ValidationCategory,
    validate_credentials,
)


def credential_checked_messages(messages: list[Any]) -> list[Any]:
    """Return a copy of model history after checking for credentials."""
    sanitized = copy.deepcopy(messages)
    return [_sanitize_message(message) for message in sanitized]


class ProviderCredentialGuard(AbstractCapability[Any]):
    """Stop provider requests that contain a detected credential."""

    async def before_model_request(
        self,
        _ctx: RunContext[Any],
        request_context: ModelRequestContext,
    ) -> ModelRequestContext:
        request_context.messages = credential_checked_messages(request_context.messages)
        request_context.model_request_parameters = _sanitize_request_parameters(
            copy.deepcopy(request_context.model_request_parameters)
        )
        return request_context


def _sanitize_message(message: Any) -> Any:
    if isinstance(message, ModelRequest):
        parts = [_sanitize_part(part) for part in message.parts]
        return replace(
            message,
            instructions=_sanitize_optional_text(message.instructions),
            parts=tuple(parts) if isinstance(message.parts, tuple) else parts,
        )
    if isinstance(message, ModelResponse):
        parts = [_sanitize_part(part) for part in message.parts]
        return replace(
            message,
            parts=tuple(parts) if isinstance(message.parts, tuple) else parts,
        )
    return message


def _sanitize_part(part: Any) -> Any:
    if isinstance(part, (SystemPromptPart, UserPromptPart)):
        return replace(part, content=_sanitize_content(part.content))
    if isinstance(part, (ToolCallPart, NativeToolCallPart)):
        return replace(part, args=_sanitize_json_value(part.args))
    if isinstance(part, (ToolReturnPart, NativeToolReturnPart)):
        return replace(part, content=_sanitize_json_value(part.content))
    if isinstance(part, RetryPromptPart):
        return replace(part, content=_sanitize_json_value(part.content))
    if isinstance(part, (TextPart, ThinkingPart, CompactionPart)):
        return replace(part, content=_sanitize_optional_text(part.content))
    return part


def _sanitize_content(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, TextContent):
        return replace(value, content=_sanitize_text(value.content))
    if isinstance(value, list):
        return [_sanitize_content(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_content(item) for item in value)
    if is_dataclass(value):
        changes = {
            item.name: _sanitize_content(getattr(value, item.name))
            for item in fields(value)
            if item.name in {"content", "url", "transcript"}
            and isinstance(getattr(value, item.name), (str, list, tuple, TextContent))
        }
        return replace(value, **changes) if changes else value
    return value


def _sanitize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, dict):
        return {key: _sanitize_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_json_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_json_value(item) for item in value)
    if is_dataclass(value):
        changes = {
            item.name: _sanitize_json_value(getattr(value, item.name))
            for item in fields(value)
            if item.name in {"content", "url", "transcript"}
            and isinstance(getattr(value, item.name), (str, dict, list, tuple))
        }
        return replace(value, **changes) if changes else value
    return value


def _sanitize_request_parameters(parameters: Any) -> Any:
    if parameters.instruction_parts:
        parameters.instruction_parts = [
            replace(part, content=_sanitize_text(part.content))
            for part in parameters.instruction_parts
        ]
    if isinstance(parameters.prompted_output_template, str):
        parameters.prompted_output_template = _sanitize_text(
            parameters.prompted_output_template
        )
    parameters.function_tools = [
        _sanitize_tool_definition(tool) for tool in parameters.function_tools
    ]
    parameters.output_tools = [
        _sanitize_tool_definition(tool) for tool in parameters.output_tools
    ]
    if parameters.output_object is not None:
        parameters.output_object = _sanitize_schema_dataclass(parameters.output_object)
    return parameters


def _sanitize_tool_definition(tool: ToolDefinition) -> ToolDefinition:
    return replace(
        tool,
        description=_sanitize_optional_text(tool.description),
        parameters_json_schema=_sanitize_schema(tool.parameters_json_schema),
    )


def _sanitize_schema_dataclass(value: Any) -> Any:
    if not is_dataclass(value):
        return value
    changes = {
        item.name: _sanitize_schema(getattr(value, item.name))
        for item in fields(value)
        if item.name in {"description", "json_schema", "schema"}
    }
    return replace(value, **changes) if changes else value


def _sanitize_schema(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, dict):
        return {key: _sanitize_schema(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_schema(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_schema(item) for item in value)
    return value


def _sanitize_optional_text(value: str | None) -> str | None:
    return _sanitize_text(value) if value is not None else None


def _sanitize_text(value: str) -> str:
    result = validate_credentials(value, boundary=ValidationBoundary.PROVIDER_REQUEST)
    if result.blocked:
        raise SecurityValidationBlocked(
            ValidationCategory.CREDENTIAL,
            result.user_message or "This request was blocked because it contains a credential.",
        )
    return result.text
