"""Effective instructions and fingerprint for the selected Provenance skill."""

from src.linger.agents.provenance.skills import EMOTIONAL_PREFLIGHT

INSTRUCTIONS = EMOTIONAL_PREFLIGHT.effective_instructions
EMOTIONAL_BOUNDARY_PROMPT_FINGERPRINT = EMOTIONAL_PREFLIGHT.fingerprint(
    template_id="provenance.emotional-boundary",
    version="4",
)
