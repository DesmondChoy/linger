"""Deterministic decision checks; suggestion quality remains independent review."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator

from src.linger.agents.contracts import StrictModel
from src.linger.agents.sculptor.surfacing_models import (
    SURFACING_DECISION_ADAPTER,
    AtTime,
    Defer,
    DoNotSurface,
    InvalidSurfacingProposal,
    NonblankText,
    Reconsideration,
    SourceMemoryIds,
    SurfaceNow,
    SurfacingInput,
    validate_surfacing_decision,
)

CASE_DECISIONS = {
    "timely": "surface_now",
    "deferred": "defer",
    "superseded": "do_not_surface",
    "repeated": "do_not_surface",
    "unsupported": "do_not_surface",
    "sensitive": "do_not_surface",
}


class SurfacingExpectation(StrictModel):
    case_kind: Literal[
        "timely", "deferred", "superseded", "repeated", "unsupported", "sensitive"
    ]
    decision: Literal["surface_now", "defer", "do_not_surface"]
    required_source_ids: SourceMemoryIds = ()
    allowed_source_ids: SourceMemoryIds = ()
    reason: Literal[
        "irrelevant", "insufficient_evidence", "superseded", "repetition",
        "sensitive_inference",
    ] | None = None
    reconsideration: Reconsideration | None = None
    semantic_criteria: tuple[NonblankText, ...] = Field(min_length=1)
    forbidden_claims: tuple[NonblankText, ...] = ()

    @model_validator(mode="after")
    def validate_expectation(self) -> Self:
        if self.decision != CASE_DECISIONS[self.case_kind]:
            raise ValueError("case_kind does not match the expected decision")
        if not set(self.required_source_ids) <= set(self.allowed_source_ids):
            raise ValueError("required sources must be allowed sources")
        if self.decision != "do_not_surface" and not self.required_source_ids:
            raise ValueError("surface and defer expectations require supporting sources")
        if (self.decision == "defer") != (self.reconsideration is not None):
            raise ValueError("only defer requires reconsideration")
        if (self.decision == "do_not_surface") != (self.reason is not None):
            raise ValueError("only do_not_surface requires a reason")
        reasons = {
            "superseded": {"superseded"},
            "repeated": {"repetition"},
            "unsupported": {"irrelevant", "insufficient_evidence"},
            "sensitive": {"sensitive_inference"},
        }
        if self.case_kind in reasons and self.reason not in reasons[self.case_kind]:
            raise ValueError("case_kind does not match the expected reason")
        return self


class SurfacingGrade(StrictModel):
    hard_failures: tuple[str, ...]
    decision_match: bool
    semantic_review_required: Literal[True] = True
    semantic_criteria: tuple[str, ...]
    forbidden_claims: tuple[str, ...]


def grade_surfacing_expectation(
    input: SurfacingInput,
    response: object,
    expected: SurfacingExpectation,
) -> SurfacingGrade:
    """Check structure, source selection, timing and labels, never prose meaning."""
    failures: list[str] = []
    match = False
    if isinstance(response, (SurfaceNow, Defer, DoNotSurface)):
        response = response.model_dump()
    try:
        parsed = SURFACING_DECISION_ADAPTER.validate_python(response)
    except ValidationError:
        failures.append("invalid_response:malformed_output")
    else:
        match = parsed.decision == expected.decision
        try:
            validate_surfacing_decision(input, parsed)
        except InvalidSurfacingProposal as error:
            failures.append(f"invalid_response:{error}")
        if not match:
            failures.append("decision_mismatch")
        sources = set(parsed.source_memory_ids)
        if not set(expected.required_source_ids) <= sources:
            failures.append("missing_required_sources")
        if not sources <= set(expected.allowed_source_ids):
            failures.append("disallowed_sources")
        if isinstance(parsed, DoNotSurface) and parsed.reason != expected.reason:
            failures.append("reason_mismatch")
        if isinstance(parsed, Defer) and expected.reconsideration is not None:
            actual = parsed.reconsideration
            wanted = expected.reconsideration
            if actual.kind != wanted.kind:
                failures.append("reconsideration_kind_mismatch")
            elif isinstance(actual, AtTime) and isinstance(wanted, AtTime):
                if actual.at != wanted.at:
                    failures.append("reconsideration_time_mismatch")
    return SurfacingGrade(
        hard_failures=tuple(failures),
        decision_match=match,
        semantic_criteria=expected.semantic_criteria,
        forbidden_claims=expected.forbidden_claims,
    )
