"""Shared PydanticAI agent construction.

Every Linger agent (Muse, Provenance, ...) is built here, so model and provider
selection lives in one place and each agent module supplies only its
instructions. Agents are built at import time and reused for the process, which
means an unsupported `LINGER_MODEL` fails at startup rather than on the first
request.
"""


from pydantic_ai import Agent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from apps.backend.config import get_settings

SUPPORTED_PROVIDERS = ["google", "openai", "anthropic"]

def build_agent(instructions: str) -> Agent[None, str]:
    # .env settings are read here
    settings = get_settings()
    provider_name, _, model_name = settings.linger_model.partition(":")
    if provider_name not in SUPPORTED_PROVIDERS or not model_name:
        raise RuntimeError(
            f"Unsupported LINGER_MODEL, we got {settings.linger_model!r}. "
            f"Only the {SUPPORTED_PROVIDERS} providers are wired up right now."
        )
        
    match provider_name:
        case "google":
            model = GoogleModel(
                model_name,
                provider=GoogleProvider(api_key=settings.api_key),
            )
        case "openai":
            # Implementation for OpenAI provider
            pass
        case "anthropic":
            # Implementation for Anthropic provider
            pass
        case _:
            raise RuntimeError(f"Unsupported provider: {provider_name}")

    return Agent(model, instructions=instructions)



