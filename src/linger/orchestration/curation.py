"""Application-owned validation around Sculptor curation proposals."""

import json

from pydantic import ValidationError
from pydantic_ai import Agent

from src.linger.agents.sculptor.agent import sculptor_agent
from src.linger.agents.sculptor.models import (
    AccountScopedMemories,
    CurationProposal,
    SCULPTOR_RESPONSE_ADAPTER,
    SculptorResponse,
)


class InvalidCurationProposal(ValueError):
    """Raised when a proposal escapes its typed, account-scoped input."""


def _model_input(batch: AccountScopedMemories) -> str:
    payload = {
        "memories": [memory.model_dump(mode="json") for memory in batch.memories]
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


async def propose_curation(
    batch: AccountScopedMemories,
    *,
    agent: Agent[None, SculptorResponse] = sculptor_agent,
) -> SculptorResponse:
    """Return a validated proposal without exposing account or storage metadata."""
    result = await agent.run(_model_input(batch))
    try:
        response = SCULPTOR_RESPONSE_ADAPTER.validate_python(result.output)
    except ValidationError as exc:
        raise InvalidCurationProposal("Sculptor returned malformed output") from exc

    if isinstance(response, CurationProposal):
        input_ids = {memory.memory_id for memory in batch.memories}
        unknown_ids = set(response.action.source_memory_ids) - input_ids
        if unknown_ids:
            raise InvalidCurationProposal(
                f"Sculptor referenced unknown memories: {sorted(unknown_ids)}"
            )
    return response
