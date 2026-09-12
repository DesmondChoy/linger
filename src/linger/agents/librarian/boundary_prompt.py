"""Effective shared-plus-skill fingerprint for librarian.boundary-inference."""

from src.linger.agents.librarian.skills import BOUNDARY_INFERENCE


PROMPT_FINGERPRINT = BOUNDARY_INFERENCE.fingerprint(
    template_id="librarian.boundary-inference", version="7"
)
