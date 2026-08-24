"""Shared PydanticAI agent construction.

Every Linger agent (Muse, Provenance, ...) is built here, so model and provider
selection lives in one place and each agent module supplies only its
instructions. Agents are built at import time and reused for the process, which
means an unsupported `LINGER_MODEL` fails at startup rather than on the first
request.
"""


from collections.abc import Sequence
from typing import Any, TypeVar, overload

from pydantic_ai import Agent, AgentRetries, Tool
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider

from apps.backend.config import get_settings

SUPPORTED_PROVIDERS = ("google", "openai", "anthropic")
OutputT = TypeVar("OutputT")


def build_model() -> Model:
    """Build the configured provider model."""
    settings = get_settings()
    provider_name, _, model_name = settings.linger_model.partition(":")
    if provider_name not in SUPPORTED_PROVIDERS or not model_name:
        raise RuntimeError(
            f"Unsupported LINGER_MODEL, we got {settings.linger_model!r}. "
            f"Choose one of: {', '.join(SUPPORTED_PROVIDERS)}."
        )

    api_key = settings.api_key_for(provider_name)
    match provider_name:
        case "google":
            model = GoogleModel(
                model_name,
                provider=GoogleProvider(api_key=api_key),
            )
        case "openai":
            model = OpenAIResponsesModel(
                model_name,
                provider=OpenAIProvider(api_key=api_key),
            )
        case "anthropic":
            model = AnthropicModel(
                model_name,
                provider=AnthropicProvider(api_key=api_key),
            )
        case _:  # pragma: no cover - guarded by SUPPORTED_PROVIDERS
            raise AssertionError(f"Unhandled provider: {provider_name}")

    return model


@overload
def build_agent(
    instructions: str,
    *,
    output_type: None = None,
    name: str | None = None,
    tools: Sequence[Tool[None]] = (),
    retries: int | AgentRetries | None = None,
) -> Agent[None, str]: ...


@overload
def build_agent(
    instructions: str,
    *,
    output_type: type[OutputT],
    name: str | None = None,
    tools: Sequence[Tool[None]] = (),
    retries: int | AgentRetries | None = None,
) -> Agent[None, OutputT]: ...


def build_agent(
    instructions: str,
    *,
    output_type: type[Any] | None = None,
    name: str | None = None,
    tools: Sequence[Tool[None]] = (),
    retries: int | AgentRetries | None = None,
) -> Agent[None, Any]:
    """Build an agent with the configured model and requested output contract."""
    selected_output: type[Any] = output_type or str
    return Agent(
        build_model(),
        output_type=selected_output,
        instructions=instructions,
        name=name,
        tools=tools,
        retries=retries,
    )
