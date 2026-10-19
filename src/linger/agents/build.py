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


ROLES = ("muse", "librarian", "serendipity", "provenance", "sculptor")
REASONING_EFFORTS = ("minimal", "low", "medium", "high")
# Project defaults for OpenAI models, overridden by LINGER_ROLE_REASONING. On
# 2026-10-08 Serendipity at medium passed 119 of 140 weak and restraint
# component runs against 93 at low (evals/serendipity/reports/
# experiment-reasoning-2026-10-08.json); other roles keep the shared setting.
DEFAULT_ROLE_REASONING = {"serendipity": "medium"}


def build_model(role: str | None = None) -> Model:
    """Build the configured provider model, or a role's configured override."""
    settings = get_settings()
    unknown = (set(settings.linger_role_models) | set(settings.linger_role_reasoning)) - set(ROLES)
    if unknown:
        raise RuntimeError(f"Unknown roles in LINGER_ROLE_MODELS or LINGER_ROLE_REASONING: {sorted(unknown)}.")
    spec = settings.linger_role_models.get(role, settings.linger_model) if role else settings.linger_model
    if spec == settings.linger_model:
        _warn_if_nonstandard(settings.linger_model)
    reasoning = settings.linger_role_reasoning.get(role) if role else None
    if reasoning is None and role in DEFAULT_ROLE_REASONING and spec.startswith("openai:"):
        reasoning = DEFAULT_ROLE_REASONING[role]
    return model_from_spec(spec, reasoning)


def model_from_spec(spec: str, reasoning: str | None = None) -> Model:
    """Build `provider:model`, optionally with an OpenAI reasoning effort."""
    provider_name, _, model_name = spec.partition(":")
    if provider_name not in SUPPORTED_PROVIDERS or not model_name:
        raise RuntimeError(
            f"Unsupported model {spec!r}. Use provider:model with one of: {', '.join(SUPPORTED_PROVIDERS)}."
        )
    if reasoning is not None and (provider_name != "openai" or reasoning not in REASONING_EFFORTS):
        raise RuntimeError(
            f"Reasoning effort {reasoning!r} needs an OpenAI model and one of: {', '.join(REASONING_EFFORTS)}."
        )
    return _provider_model(provider_name, model_name, reasoning)


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


def _provider_model(provider_name: str, model_name: str, reasoning: str | None = None) -> Model:
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
                settings=(
                    OpenAIResponsesModelSettings(openai_reasoning_effort=reasoning) if reasoning
                    else LUNA_SETTINGS if model_name == "gpt-6-luna" else None
                ),
            )
        case "anthropic":
            model = AnthropicModel(
                model_name,
                provider=AnthropicProvider(api_key=api_key),
            )
        case _:  # pragma: no cover - guarded by SUPPORTED_PROVIDERS
            raise AssertionError(f"Unhandled provider: {provider_name}")

    return model
