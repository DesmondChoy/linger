"""The chat agent.

A single PydanticAI agent with no tools and a plain-text reply. This is the
seam where Linger's real agents (Muse, Provenance, ...) drop in later without
the HTTP surface changing.
"""

from pydantic_ai import Agent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from ....apps.backend.config import get_settings

INSTRUCTIONS = """You are Linger, a thoughtful reading and reflection companion.
Be warm, concise, and concrete. Ask a follow-up question when it would genuinely
help. If you are unsure of a fact, say so rather than guessing."""


def _build_agent() -> Agent[None, str]:
    settings = get_settings()
    provider_name, _, model_name = settings.linger_model.partition(":")
    if provider_name != "google" or not model_name:
        raise RuntimeError(
            f"LINGER_MODEL must look like 'google:<model>', got {settings.linger_model!r}. "
            "Only the Google provider is wired up right now."
        )

    model = GoogleModel(
        model_name,
        provider=GoogleProvider(api_key=settings.google_api_key),
    )
    return Agent(model, instructions=INSTRUCTIONS)


chat_agent = _build_agent()
