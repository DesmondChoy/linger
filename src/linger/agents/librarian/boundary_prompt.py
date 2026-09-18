"""Effective shared-plus-skill fingerprint for librarian.boundary-inference."""

from src.linger.agents.librarian.skills import BOUNDARY_INFERENCE, BOUNDARY_INFERENCE_NO_HISTORY, EVENT_IDENTIFICATION


PROMPT_FINGERPRINT = BOUNDARY_INFERENCE.fingerprint(
    template_id="librarian.boundary-inference"
)

NO_HISTORY_PROMPT_FINGERPRINT = BOUNDARY_INFERENCE_NO_HISTORY.fingerprint(
    template_id="librarian.boundary-inference-no-history"
)

EVENT_IDENTIFICATION_PROMPT_FINGERPRINT = EVENT_IDENTIFICATION.fingerprint(
    template_id="librarian.event-identification"
)
