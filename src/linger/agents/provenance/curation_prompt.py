"""Effective instructions and fingerprint for the selected Provenance skill."""

from src.linger.agents.provenance.skills import CURATION_REVIEW

INSTRUCTIONS = CURATION_REVIEW.effective_instructions
PROMPT_FINGERPRINT = CURATION_REVIEW.fingerprint(
    template_id="provenance.curation-gate",
    version="3",
)
