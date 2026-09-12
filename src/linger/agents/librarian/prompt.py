"""Effective shared-plus-skill fingerprint for librarian.evidence-strength."""

from src.linger.agents.librarian.skills import EVIDENCE_ASSESSMENT


PROMPT_FINGERPRINT = EVIDENCE_ASSESSMENT.fingerprint(
    template_id="librarian.evidence-strength", version="3"
)
