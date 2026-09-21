"""Application-owned emotional-content boundary for one Muse turn."""

from typing import Literal

from pydantic import Field

from src.linger.contracts.base import StrictModel


EMOTIONAL_CONTENT_POLICY_VERSION = "3"
EMOTIONAL_BOUNDARY_RESPONSE_ID = "distressing_disclosure_v1"
EMOTIONAL_BOUNDARY_RESPONSE = (
    "That sounds deeply distressing. I don’t want to keep probing, and I’m not "
    "able to assess your wellbeing. Please consider reaching out to someone you "
    "trust or a qualified professional for support."
)
EMOTIONAL_SELF_HARM_RESPONSE_ID = "self_harm_disclosure_v1"
EMOTIONAL_SELF_HARM_RESPONSE = (
    "Thank you for telling me. I’m not able to assess your safety or support "
    "you through this, so please reach out to someone who can: a person you "
    "trust, a doctor, or a crisis line. If you’re in immediate danger, contact "
    "your local emergency services. You can find a crisis line for your "
    "country at https://findahelpline.com."
)

BoundaryDecision = Literal["apply_boundary", "apply_self_harm_boundary"]

_BOUNDARY_RESPONSES: dict[BoundaryDecision, str] = {
    "apply_boundary": EMOTIONAL_BOUNDARY_RESPONSE,
    "apply_self_harm_boundary": EMOTIONAL_SELF_HARM_RESPONSE,
}


def boundary_response(decision: BoundaryDecision) -> str:
    """Return the one fixed, app-authored response for an applied boundary."""
    return _BOUNDARY_RESPONSES[decision]


class EmotionalContentPolicy(StrictModel):
    """Conditional behavior after distress, not the current Line's assessment."""

    version: Literal["3"] = EMOTIONAL_CONTENT_POLICY_VERSION
    boundary_response_id: Literal["distressing_disclosure_v1"] = (
        EMOTIONAL_BOUNDARY_RESPONSE_ID
    )
    self_harm_response_id: Literal["self_harm_disclosure_v1"] = (
        EMOTIONAL_SELF_HARM_RESPONSE_ID
    )
    prohibit_diagnosis: Literal[True] = True
    stop_probing_after_distress: Literal[True] = True
    suppress_tools_after_distress: Literal[True] = True
    suppress_capture_after_distress: Literal[True] = True


class EmotionalBoundaryInput(StrictModel):
    """Minimal request-local input for the no-tool policy preflight."""

    current_line: str = Field(min_length=1, max_length=8000)
    policy: EmotionalContentPolicy


class EmotionalBoundaryAssessment(StrictModel):
    """A product-boundary decision, never a wellbeing assessment."""

    decision: Literal[
        "continue_reflection", "apply_boundary", "apply_self_harm_boundary"
    ]
