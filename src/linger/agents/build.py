"""Shared model and provider selection for Linger's five reusable role Agents.

Role packages construct their own Agents at import time. An unsupported
`LINGER_MODEL` therefore fails at startup rather than on the first request.
"""

from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider

from apps.backend.config import get_settings

SUPPORTED_PROVIDERS = ("google", "openai", "anthropic")


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
