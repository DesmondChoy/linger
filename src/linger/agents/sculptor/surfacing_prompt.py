"""Effective shared-plus-skill fingerprint for sculptor.surfacing."""

from src.linger.agents.sculptor.skills import MEMORY_SURFACING


PROMPT_FINGERPRINT = MEMORY_SURFACING.fingerprint(
    template_id="sculptor.surfacing", version="3"
)
