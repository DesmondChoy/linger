"""Effective instructions and fingerprint for the selected Provenance skill."""

from src.linger.agents.provenance.skills import CANDIDATE_REVIEW

INSTRUCTIONS = CANDIDATE_REVIEW.effective_instructions
PROMPT_FINGERPRINT = CANDIDATE_REVIEW.fingerprint(
    template_id="provenance.release-gate",
)
