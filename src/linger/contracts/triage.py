"""What one reader message needs answered, decided before Muse drafts."""

from typing import Literal

from pydantic import Field

from src.linger.contracts.base import StrictModel

BookContentNeed = Literal["yes", "no", "unsure"]
MemoryNeed = Literal[
    "own_earlier_reflections",
    "source_comparison",
    "outside_recommendation",
    "none",
    "unsure",
]
OverrideAttempt = Literal["no_attempt", "attempted"]


class TurnTriageInput(StrictModel):
    """The current reader message alone: no history, session state, or earlier triage."""

    current_line: str = Field(min_length=1, max_length=8000)


class TurnNeeds(StrictModel):
    """Independent needs of the answer and its override signal; never a tool name or a grant."""

    book_content: BookContentNeed
    memory: MemoryNeed
    override_attempt: OverrideAttempt = "no_attempt"
