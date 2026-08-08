"""Sample chat agent.

A single PydanticAI agent build function with no tools and a plain-text reply. 
This is the seam where Linger's real agents (Muse, Provenance, ...) drop in later without the HTTP surface changing.
"""


from pydantic_ai import Agent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from apps.backend.config import get_settings

SUPPORTED_PROVIDERS = ["google"]

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
        case _:
            raise RuntimeError(f"Unsupported provider: {provider_name}")

    return Agent(model, instructions=instructions)



