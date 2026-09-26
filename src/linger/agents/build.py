"""Shared model and provider selection for Linger's five reusable role Agents.

Role packages construct their own Agents at import time. An unsupported
`LINGER_MODEL` therefore fails at startup rather than on the first request.
"""

import logging
from functools import cache

from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider

from apps.backend.config import get_settings

SUPPORTED_PROVIDERS = ("google", "openai", "anthropic")
# The team's shared model. `LINGER_MODEL` comes from each developer's `.env`,
# so a different value is allowed but warned about: results would not be
# comparable with the rest of the team's.
STANDARD_MODEL = "openai:gpt-6-luna"
LUNA_SETTINGS = OpenAIResponsesModelSettings(openai_reasoning_effort="low")
# Fast tier for Muse turn triage. A provider without an entry uses
# `LINGER_MODEL` itself, so triage never needs its own configuration.
TRIAGE_MODEL_NAMES = {"openai": "gpt-6-luna", "google": "gemini-2.5-flash"}


def build_model() -> Model:
    """Build the configured provider model."""
    settings = get_settings()
    provider_name, _, model_name = settings.linger_model.partition(":")
    if provider_name not in SUPPORTED_PROVIDERS or not model_name:
        raise RuntimeError(
            f"Unsupported LINGER_MODEL, we got {settings.linger_model!r}. "
            f"Choose one of: {', '.join(SUPPORTED_PROVIDERS)}."
        )
    _warn_if_nonstandard(settings.linger_model)
    return _provider_model(provider_name, model_name)


def build_triage_model() -> Model:
    """Build the configured provider's small model, else the configured model."""
    provider_name = get_settings().linger_model.partition(":")[0]
    triage_name = TRIAGE_MODEL_NAMES.get(provider_name)
    if triage_name is None:
        return build_model()
    return _provider_model(provider_name, triage_name)


@cache
def _warn_if_nonstandard(linger_model: str) -> None:
    """Warn once per process when this machine's model differs from the team's."""
    if linger_model != STANDARD_MODEL:
        logging.getLogger("linger.models").warning(
            "LINGER_MODEL is %r, not the team standard %r; set LINGER_MODEL=%s in .env "
            "so results are comparable.",
            linger_model, STANDARD_MODEL, STANDARD_MODEL,
        )


def _provider_model(provider_name: str, model_name: str) -> Model:
    api_key = get_settings().api_key_for(provider_name)
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
                settings=LUNA_SETTINGS if model_name == "gpt-6-luna" else None,
            )
        case "anthropic":
            model = AnthropicModel(
                model_name,
                provider=AnthropicProvider(api_key=api_key),
            )
        case _:  # pragma: no cover - guarded by SUPPORTED_PROVIDERS
            raise AssertionError(f"Unhandled provider: {provider_name}")

    return model
