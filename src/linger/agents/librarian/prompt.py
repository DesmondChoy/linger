"""Effective shared-plus-skill fingerprints for Librarian's search-result skills."""

from src.linger.agents.librarian.skills import EVIDENCE_ASSESSMENT, STATED_ANSWERS


PROMPT_FINGERPRINT = EVIDENCE_ASSESSMENT.fingerprint(
    template_id="librarian.evidence-strength"
)

STATED_ANSWERS_PROMPT_FINGERPRINT = STATED_ANSWERS.fingerprint(
    template_id="librarian.stated-answers"
)
