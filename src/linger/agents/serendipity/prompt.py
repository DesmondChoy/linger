"""Effective runtime instructions and contract-aware Serendipity fingerprint."""

from src.linger.agents.serendipity.skills import CONNECTION_DISCOVERY

INSTRUCTIONS = CONNECTION_DISCOVERY.effective_instructions
PROMPT_FINGERPRINT = CONNECTION_DISCOVERY.fingerprint(
    template_id="serendipity.search-rank-select", version="3"
)
