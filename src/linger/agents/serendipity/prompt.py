"""Effective runtime instructions and contract-aware Serendipity fingerprints."""

from src.linger.agents.serendipity.skills import (
    CONNECTION_DISCOVERY,
    MEMORY_RECALL,
    SOURCE_GATHERING,
)

INSTRUCTIONS = CONNECTION_DISCOVERY.effective_instructions
PROMPT_FINGERPRINT = CONNECTION_DISCOVERY.fingerprint(
    template_id="serendipity.search-rank-select"
)
MEMORY_RECALL_PROMPT_FINGERPRINT = MEMORY_RECALL.fingerprint(
    template_id="serendipity.memory-recall"
)
SOURCE_GATHERING_PROMPT_FINGERPRINT = SOURCE_GATHERING.fingerprint(
    template_id="serendipity.source-gathering"
)
