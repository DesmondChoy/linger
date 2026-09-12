"""Effective shared-plus-skill fingerprint for sculptor.curation."""

from src.linger.agents.sculptor.skills import MEMORY_CURATION


PROMPT_FINGERPRINT = MEMORY_CURATION.fingerprint(
    template_id="sculptor.curation", version="5"
)
