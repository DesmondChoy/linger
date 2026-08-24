"""Application-owned emotional-content boundary for one Muse turn."""

from typing import Literal

from pydantic import Field

from src.linger.contracts.base import StrictModel


EMOTIONAL_CONTENT_POLICY_VERSION = "1"
EMOTIONAL_BOUNDARY_RESPONSE_ID = "distressing_disclosure_v1"
EMOTIONAL_BOUNDARY_RESPONSE = (
    "That sounds deeply distressing. I don’t want to keep probing, and I’m not "
    "able to assess your wellbeing. Please consider reaching out to someone you "
    "trust or a qualified professional for support."
)


class EmotionalContentPolicy(StrictModel):
    """Fixed request-local behavior; it grants no diagnosis or crisis authority."""

    version: Literal["1"] = EMOTIONAL_CONTENT_POLICY_VERSION
    boundary_response_id: Literal["distressing_disclosure_v1"] = (
        EMOTIONAL_BOUNDARY_RESPONSE_ID
    )
    prohibit_diagnosis: Literal[True] = True
    stop_probing_after_distress: Literal[True] = True
    suppress_tools: Literal[True] = True
    suppress_capture: Literal[True] = True


class EmotionalBoundaryInput(StrictModel):
    """Minimal request-local input for the no-tool policy preflight."""

    current_line: str = Field(min_length=1, max_length=8000)
    policy: EmotionalContentPolicy


class EmotionalBoundaryAssessment(StrictModel):
    """A product-boundary decision, never a wellbeing assessment."""

    decision: Literal["continue_reflection", "apply_boundary"]
