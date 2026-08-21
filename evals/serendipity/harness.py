"""Typed loader and deterministic hard gates for Serendipity eval cases."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, ValidationError, model_validator

from src.linger.agents.contracts import StrictModel
from src.linger.agents.serendipity.models import (
    SERENDIPITY_RESPONSE_ADAPTER,
    ConnectionEvidence,
    ConnectionDecline,
    ConnectionDiscoveryInput,
    ConnectionProposal,
    DeclineReason,
    PresentationMode,
    SerendipityResponse,
)

DEFAULT_CASE_DIRECTORY = Path(__file__).with_name("cases")

PrimaryBehavior = Literal[
    "supported_same_book_connection",
    "supported_memory_connection",
    "supported_web_connection",
    "insufficient_evidence_decline",
    "generic_theme_decline",
    "unsafe_evidence_decline",
    "no_clear_winner_decline",
]
REQUIRED_BEHAVIORS = frozenset(
    {
        "supported_same_book_connection",
        "supported_memory_connection",
        "supported_web_connection",
        "insufficient_evidence_decline",
        "generic_theme_decline",
        "unsafe_evidence_decline",
        "no_clear_winner_decline",
    }
)


class SemanticReview(StrictModel):
    """Criteria requiring human or secondary-LLM review."""

    criteria: tuple[str, ...]
    forbidden_claims: tuple[str, ...] = ()


class ExpectedProposal(StrictModel):
    status: Literal["proposal"]
    required_evidence_ids: tuple[str, ...]
    presentation: PresentationMode
    minimum_shortlist_size: Literal[2]
    selected_rank: Literal[1]
    semantic_review: SemanticReview


class ExpectedDecline(StrictModel):
    status: Literal["decline"]
    allowed_reasons: tuple[DeclineReason, ...]


ExpectedResponse = Annotated[
    ExpectedProposal | ExpectedDecline,
    Field(discriminator="status"),
]


class CaseInvariants(StrictModel):
    no_storage_authority: Literal[True]
    no_release_authority: Literal[True]
    run_evidence_only: Literal[True]
    search_before_proposal: Literal[True]
    shortlist_compared: Literal[True]


class SerendipityEvalCase(StrictModel):
    """One frozen, bounded Serendipity behavior case."""

    schema_version: Literal[2]
    case_id: str = Field(pattern=r"^serendipity-[a-z0-9-]+-v2$")
    owner: Literal["serendipity"]
    primary_behavior: PrimaryBehavior
    description: str = Field(min_length=1)
    input: ConnectionDiscoveryInput
    tool_evidence: tuple[ConnectionEvidence, ...]
    expected: ExpectedResponse
    invariants: CaseInvariants

    @model_validator(mode="after")
    def expected_shape_matches_behavior(self) -> Self:
        if self.primary_behavior in {
            "supported_same_book_connection",
            "supported_memory_connection",
            "supported_web_connection",
        }:
            if not isinstance(self.expected, ExpectedProposal):
                raise ValueError("the supported case must expect a proposal")
            available_ids = {item.evidence_id for item in self.tool_evidence}
            if not set(self.expected.required_evidence_ids).issubset(available_ids):
                raise ValueError("expected proposal cites evidence outside tool results")
            return self
        if not isinstance(self.expected, ExpectedDecline):
            raise ValueError("decline behaviors must expect a decline")
        return self


class GradeResult(StrictModel):
    hard_pass: bool
    failures: tuple[str, ...]
    semantic_review_required: bool
    semantic_criteria: tuple[str, ...] = ()
    forbidden_semantic_claims: tuple[str, ...] = ()


def load_serendipity_eval_cases(
    case_directory: Path = DEFAULT_CASE_DIRECTORY,
) -> tuple[SerendipityEvalCase, ...]:
    """Load exactly one versioned case for every current baseline behavior."""
    paths = sorted(case_directory.glob("*.json"))
    if len(paths) != len(REQUIRED_BEHAVIORS):
        raise ValueError(
            f"expected {len(REQUIRED_BEHAVIORS)} Serendipity cases, found {len(paths)}"
        )
    cases: list[SerendipityEvalCase] = []
    for path in paths:
        try:
            cases.append(
                SerendipityEvalCase.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            )
        except (OSError, ValidationError) as exc:
            raise ValueError(f"invalid Serendipity eval case: {path}") from exc
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Serendipity case IDs must be unique")
    behaviors = {case.primary_behavior for case in cases}
    if behaviors != REQUIRED_BEHAVIORS:
        raise ValueError(
            "Serendipity baseline must contain exactly one case for each behavior"
        )
    return tuple(cases)


def grade_serendipity_response(
    case: SerendipityEvalCase,
    response: SerendipityResponse | dict[str, object],
) -> GradeResult:
    """Apply hard contract gates while leaving generated prose to semantic review."""
    semantic_review = (
        {
            "semantic_review_required": True,
            "semantic_criteria": case.expected.semantic_review.criteria,
            "forbidden_semantic_claims": case.expected.semantic_review.forbidden_claims,
        }
        if isinstance(case.expected, ExpectedProposal)
        else {
            "semantic_review_required": False,
            "semantic_criteria": (),
            "forbidden_semantic_claims": (),
        }
    )
    try:
        parsed = SERENDIPITY_RESPONSE_ADAPTER.validate_python(response)
    except ValidationError as exc:
        return GradeResult(
            hard_pass=False,
            failures=(f"invalid_response:{exc.error_count()}_validation_error(s)",),
            **semantic_review,
        )

    failures: list[str] = []
    if isinstance(case.expected, ExpectedDecline):
        if not isinstance(parsed, ConnectionDecline):
            failures.append("expected_decline")
        elif parsed.reason not in case.expected.allowed_reasons:
            failures.append(f"unexpected_decline_reason:{parsed.reason}")
    elif not isinstance(parsed, ConnectionProposal):
        failures.append("expected_proposal")
    else:
        available_ids = {item.evidence_id for item in case.tool_evidence}
        selected_evidence_ids = parsed.selected_candidate.evidence_ids
        if not set(selected_evidence_ids).issubset(available_ids):
            failures.append("proposal_references_unknown_evidence")
        if not set(case.expected.required_evidence_ids).issubset(
            selected_evidence_ids
        ):
            failures.append("proposal_missing_required_evidence")
        if parsed.presentation != case.expected.presentation:
            failures.append("proposal_changed_presentation")
        evidence_by_id = {item.evidence_id: item for item in case.tool_evidence}
        cited_kinds = {
            evidence_by_id[evidence_id].source_kind
            for evidence_id in selected_evidence_ids
            if evidence_id in evidence_by_id
        }
        flags = set(parsed.policy_flags)
        if ("authorised_memory" in cited_kinds) != (
            "uses_authorised_memory" in flags
        ):
            failures.append("proposal_memory_flag_mismatch")
        if ("web" in cited_kinds) != ("contains_web_claim" in flags):
            failures.append("proposal_web_flag_mismatch")

    return GradeResult(
        hard_pass=not failures,
        failures=tuple(failures),
        **semantic_review,
    )
