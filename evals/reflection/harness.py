"""Typed expected behaviour for one reflection-and-grounding Scene.

Specification flow 4.2.1 grades three questions per Scene: what the application
released, whether retrieval was needed at all, and whether every released
citation stayed inside the reader's boundary. `GroundingExpectation` states all
three as one discriminated value so a Scene cannot claim, for example, that
retrieval was unnecessary while also naming permitted evidence.

Deterministic hard gates only. Whether the reflection reads well is a semantic
judgment that stays separately reviewable.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

ReleaseSource = Literal[
    "muse_candidate",
    "application_emotional_boundary",
    "application_safe_decline",
]

PrimaryBehavior = Literal[
    "grounded_reflection",
    "non_grounded_reflection",
    "bounded_clarification",
    "weak_evidence_decline",
]


class StrictModel(BaseModel):
    """Reject unreviewed Ground truth schema drift."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class GroundedRelease(StrictModel):
    """The Scene must retrieve and release, citing only permitted evidence."""

    kind: Literal["grounded_release"]
    permitted_evidence_ids: tuple[str, ...] = Field(min_length=1)
    chapter_max: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_unique_evidence(self) -> Self:
        if len(set(self.permitted_evidence_ids)) != len(self.permitted_evidence_ids):
            raise ValueError("permitted evidence IDs must be unique")
        return self


class UngroundedRelease(StrictModel):
    """The Scene must answer without retrieving book evidence at all."""

    kind: Literal["ungrounded_release"]


class ClarificationRelease(StrictModel):
    """An unresolved boundary must produce a question, not book content."""

    kind: Literal["clarification_release"]


class SafeDecline(StrictModel):
    """The evidence cannot support the request, so nothing is released."""

    kind: Literal["safe_decline"]


ExpectedRelease = Annotated[
    GroundedRelease | UngroundedRelease | ClarificationRelease | SafeDecline,
    Field(discriminator="kind"),
]

_EXPECTED_KIND: dict[PrimaryBehavior, str] = {
    "grounded_reflection": "grounded_release",
    "non_grounded_reflection": "ungrounded_release",
    "bounded_clarification": "clarification_release",
    "weak_evidence_decline": "safe_decline",
}

_RELEASE_SOURCE: dict[str, ReleaseSource] = {
    "grounded_release": "muse_candidate",
    "ungrounded_release": "muse_candidate",
    "clarification_release": "muse_candidate",
    "safe_decline": "application_safe_decline",
}


class GroundingExpectation(StrictModel):
    """Reusable expected behaviour for one reflection-and-grounding Scene."""

    primary_behavior: PrimaryBehavior
    expected: ExpectedRelease
    forbidden_post_boundary_facts: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_expected_behavior(self) -> Self:
        required = _EXPECTED_KIND[self.primary_behavior]
        if self.expected.kind != required:
            raise ValueError(
                f"{self.primary_behavior} requires expected.kind={required!r}, "
                f"not {self.expected.kind!r}"
            )
        if len(set(self.forbidden_post_boundary_facts)) != len(
            self.forbidden_post_boundary_facts
        ):
            raise ValueError("forbidden post-boundary facts must be unique")
        return self

    @property
    def retrieval_required(self) -> bool:
        """Report whether this Scene must consult book evidence."""
        return self.expected.kind == "grounded_release"

    @property
    def release_source(self) -> ReleaseSource:
        """Report the application release path this Scene must take."""
        return _RELEASE_SOURCE[self.expected.kind]

    @property
    def permitted_evidence_ids(self) -> frozenset[str]:
        """Report the only evidence IDs a released citation may name."""
        if isinstance(self.expected, GroundedRelease):
            return frozenset(self.expected.permitted_evidence_ids)
        return frozenset()
