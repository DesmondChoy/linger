"""Bounded inputs and proposal-only decisions for proactive memory surfacing."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    Field,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from src.linger.agents.contracts import StrictModel
from src.linger.agents.sculptor.models import CuratableMemory


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("text must not be blank")
    return value


NonblankText = Annotated[str, AfterValidator(_nonblank)]


def _unique_sources(value: tuple[str, ...]) -> tuple[str, ...]:
    if len(value) != len(set(value)):
        raise ValueError("source memory IDs must be unique")
    return value


SourceMemoryIds = Annotated[
    tuple[NonblankText, ...], Field(max_length=12), AfterValidator(_unique_sources)
]


class PriorSurfacing(StrictModel):
    surfacing_id: NonblankText
    suggestion: NonblankText
    outcome: Literal["surfaced", "dismissed"]
    occurred_at: AwareDatetime
    suppress_until: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_suppression_time(self) -> Self:
        if self.suppress_until is not None and self.suppress_until <= self.occurred_at:
            raise ValueError("suppression must end after the prior surfacing occurred")
        return self


class SurfacingContext(StrictModel):
    now: AwareDatetime
    current_context: NonblankText
    history: tuple[PriorSurfacing, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def validate_history(self) -> Self:
        identifiers = tuple(item.surfacing_id for item in self.history)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("prior surfacing IDs must be unique")
        if any(item.occurred_at > self.now for item in self.history):
            raise ValueError("prior surfacing cannot occur after now")
        return self


class SurfacingInput(StrictModel):
    account_scope: NonblankText
    context: SurfacingContext
    memories: tuple[CuratableMemory, ...] = Field(max_length=12)

    @model_validator(mode="after")
    def validate_memories(self) -> Self:
        identifiers = tuple(memory.memory_id for memory in self.memories)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("memory IDs must be unique")
        if any(
            not memory.memory_id.strip() or not memory.text.strip()
            for memory in self.memories
        ):
            raise ValueError("memory IDs and text must not be blank")
        return self


class AtTime(StrictModel):
    kind: Literal["time"]
    at: AwareDatetime


class OnCondition(StrictModel):
    kind: Literal["condition"]
    condition: NonblankText


Reconsideration = Annotated[AtTime | OnCondition, Field(discriminator="kind")]


class SurfaceNow(StrictModel):
    decision: Literal["surface_now"]
    source_memory_ids: SourceMemoryIds = Field(min_length=1)
    suggestion: NonblankText
    rationale: NonblankText


class Defer(StrictModel):
    decision: Literal["defer"]
    source_memory_ids: SourceMemoryIds = Field(min_length=1)
    suggestion: NonblankText
    rationale: NonblankText
    reconsideration: Reconsideration


class DoNotSurface(StrictModel):
    decision: Literal["do_not_surface"]
    source_memory_ids: SourceMemoryIds = ()
    reason: Literal[
        "irrelevant",
        "insufficient_evidence",
        "superseded",
        "repetition",
        "sensitive_inference",
    ]
    rationale: NonblankText


SurfacingDecision = SurfaceNow | Defer | DoNotSurface
SURFACING_DECISION_ADAPTER = TypeAdapter(
    Annotated[SurfacingDecision, Field(discriminator="decision")]
)


class InvalidSurfacingProposal(ValueError):
    """A proposal violates its schema, supplied sources, or decision time."""

    def __init__(
        self, message: str, *, proposal: SurfacingDecision | None = None
    ) -> None:
        super().__init__(message)
        self.proposal = proposal


def validate_surfacing_decision(
    input: SurfacingInput, response: object
) -> SurfacingDecision:
    """Check the hard boundary without claiming semantic usefulness."""
    if isinstance(response, (SurfaceNow, Defer, DoNotSurface)):
        response = response.model_dump()
    try:
        decision = SURFACING_DECISION_ADAPTER.validate_python(response)
    except ValidationError:
        raise InvalidSurfacingProposal("Sculptor returned malformed output") from None
    input_ids = {memory.memory_id for memory in input.memories}
    if set(decision.source_memory_ids) - input_ids:
        raise InvalidSurfacingProposal(
            "Sculptor referenced unknown memories", proposal=decision
        )
    if (
        isinstance(decision, Defer)
        and isinstance(decision.reconsideration, AtTime)
        and decision.reconsideration.at <= input.context.now
    ):
        raise InvalidSurfacingProposal(
            "reconsideration time must be after now", proposal=decision
        )
    return decision
