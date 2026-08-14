"""Typed loader and deterministic hard gates for Sculptor eval cases."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic import model_validator

from src.linger.agents.sculptor.models import (
    CurationProposal as CurationProposalResponse,
    DerivedSummary as DerivedSummaryResponse,
    DuplicateLink as DuplicateLinkResponse,
    NoCurationProposal as NoCurationProposalResponse,
    SCULPTOR_RESPONSE_ADAPTER as RESPONSE_ADAPTER,
    SculptorResponse,
    TopicGroup as TopicGroupResponse,
)

DEFAULT_CASE_DIRECTORY = Path(__file__).with_name("cases")

PrimaryBehavior = Literal[
    "exact_duplicate",
    "paraphrased_duplicate",
    "noisy_memory_summary",
    "related_topic_group",
    "superficial_similarity_no_change",
]
ForbiddenOutcome = Literal[
    "delete_original",
    "rewrite_original",
    "reference_unknown_memory",
    "collapse_provenance",
    "derive_unsupported_claim",
    "link_related_memories_as_duplicates",
    "group_unrelated_memories",
]

REQUIRED_BEHAVIORS = frozenset(
    {
        "exact_duplicate",
        "paraphrased_duplicate",
        "noisy_memory_summary",
        "related_topic_group",
        "superficial_similarity_no_change",
    }
)


class StrictModel(BaseModel):
    """Reject accidental schema drift in cases and candidate responses."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class EvalMemory(StrictModel):
    """One immutable, account-scoped memory supplied to Sculptor."""

    memory_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    capture_type: Literal["explicit", "automatic", "correction"]
    source_event_id: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()


class CurationInput(StrictModel):
    """The complete bounded input for one eval invocation."""

    account_scope: str = Field(min_length=1)
    memories: tuple[EvalMemory, ...] = Field(min_length=2, max_length=12)


class CaseInvariants(StrictModel):
    """Non-negotiable properties shared by the baseline cases."""

    originals_immutable: Literal[True]
    provenance_required: Literal[True]
    no_storage_authority: Literal[True]


class SemanticReview(StrictModel):
    """Human or secondary-LLM rubric for unconstrained generated prose."""

    criteria: tuple[str, ...] = Field(min_length=1)
    forbidden_claims: tuple[str, ...] = ()


class DuplicateLinkExpectation(StrictModel):
    action: Literal["link_duplicates"]
    source_memory_ids: tuple[str, ...] = Field(min_length=2, max_length=2)


class DerivedSummaryExpectation(StrictModel):
    action: Literal["update_derived_summary"]
    source_memory_ids: tuple[str, ...] = Field(min_length=2)
    max_summary_words: int = Field(gt=0, le=100)
    semantic_review: SemanticReview


class TopicGroupExpectation(StrictModel):
    action: Literal["assign_topic_group"]
    source_memory_ids: tuple[str, ...] = Field(min_length=2)
    semantic_review: SemanticReview


ExpectedAction = Annotated[
    DuplicateLinkExpectation
    | DerivedSummaryExpectation
    | TopicGroupExpectation,
    Field(discriminator="action"),
]


class ExpectedCurationProposal(StrictModel):
    kind: Literal["curation_proposal"]
    action: ExpectedAction


class ExpectedNoCurationProposal(StrictModel):
    kind: Literal["no_curation_proposal"]
    reason_category: Literal["superficial_similarity"]


ExpectedResponse = Annotated[
    ExpectedCurationProposal | ExpectedNoCurationProposal,
    Field(discriminator="kind"),
]


class SculptorEvalCase(StrictModel):
    """One versioned baseline case with a single primary behaviour."""

    schema_version: Literal[1]
    case_id: str = Field(pattern=r"^sculptor-[a-z0-9-]+-v1$")
    owner: Literal["sculptor"]
    primary_behavior: PrimaryBehavior
    description: str = Field(min_length=1)
    input: CurationInput
    expected: ExpectedResponse
    invariants: CaseInvariants
    forbidden_outcomes: tuple[ForbiddenOutcome, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_case_contract(self) -> Self:
        memory_ids = tuple(memory.memory_id for memory in self.input.memories)
        if len(memory_ids) != len(set(memory_ids)):
            raise ValueError("input memory IDs must be unique")

        expected_action_by_behavior = {
            "exact_duplicate": "link_duplicates",
            "paraphrased_duplicate": "link_duplicates",
            "noisy_memory_summary": "update_derived_summary",
            "related_topic_group": "assign_topic_group",
        }
        required_action = expected_action_by_behavior.get(self.primary_behavior)

        if self.primary_behavior == "superficial_similarity_no_change":
            if not isinstance(self.expected, ExpectedNoCurationProposal):
                raise ValueError("the no-change case must expect NoCurationProposal")
            return self

        if not isinstance(self.expected, ExpectedCurationProposal):
            raise ValueError("curation cases must expect CurationProposal")
        if self.expected.action.action != required_action:
            raise ValueError(
                f"{self.primary_behavior} must expect action {required_action}"
            )

        source_ids = self.expected.action.source_memory_ids
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("expected source memory IDs must be unique")
        unknown_ids = set(source_ids) - set(memory_ids)
        if unknown_ids:
            raise ValueError(
                f"expected source memory IDs are outside the input: {sorted(unknown_ids)}"
            )
        return self


class GradeResult(StrictModel):
    """Deterministic result; semantic prose quality is reported separately."""

    hard_pass: bool
    failures: tuple[str, ...]
    semantic_review_required: bool
    semantic_criteria: tuple[str, ...] = ()
    forbidden_semantic_claims: tuple[str, ...] = ()


def load_sculptor_eval_cases(
    case_directory: Path = DEFAULT_CASE_DIRECTORY,
) -> tuple[SculptorEvalCase, ...]:
    """Load the complete frozen five-case baseline and validate its topology."""
    paths = sorted(case_directory.glob("*.json"))
    if len(paths) != 5:
        raise ValueError(f"expected exactly five Sculptor cases, found {len(paths)}")

    cases: list[SculptorEvalCase] = []
    for path in paths:
        try:
            cases.append(
                SculptorEvalCase.model_validate_json(path.read_text(encoding="utf-8"))
            )
        except (OSError, ValidationError) as exc:
            raise ValueError(f"invalid Sculptor eval case: {path}") from exc

    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Sculptor case IDs must be unique")

    behaviors = {case.primary_behavior for case in cases}
    if behaviors != REQUIRED_BEHAVIORS:
        raise ValueError(
            "Sculptor baseline must contain exactly one case for each required behavior"
        )
    return tuple(cases)


def grade_sculptor_response(
    case: SculptorEvalCase,
    response: SculptorResponse | dict[str, object],
) -> GradeResult:
    """Apply hard deterministic gates without pretending prose is exact-matchable."""
    semantic_review = _semantic_review(case)
    try:
        parsed = RESPONSE_ADAPTER.validate_python(response)
    except ValidationError as exc:
        return GradeResult(
            hard_pass=False,
            failures=(f"invalid_response:{exc.error_count()}_validation_error(s)",),
            **semantic_review,
        )

    failures: list[str] = []
    if isinstance(case.expected, ExpectedNoCurationProposal):
        if not isinstance(parsed, NoCurationProposalResponse):
            failures.append("expected_no_curation_proposal")
        return GradeResult(
            hard_pass=not failures,
            failures=tuple(failures),
            **semantic_review,
        )

    if not isinstance(parsed, CurationProposalResponse):
        failures.append("expected_curation_proposal")
        return GradeResult(
            hard_pass=False,
            failures=tuple(failures),
            **semantic_review,
        )

    expected_action = case.expected.action
    actual_action = parsed.action
    if actual_action.action != expected_action.action:
        failures.append(
            f"expected_action:{expected_action.action};got:{actual_action.action}"
        )

    expected_sources = set(expected_action.source_memory_ids)
    actual_sources = set(actual_action.source_memory_ids)
    if len(actual_action.source_memory_ids) != len(actual_sources):
        failures.append("duplicate_source_memory_ids")
    if actual_sources != expected_sources:
        failures.append("source_memory_ids_mismatch")

    input_ids = {memory.memory_id for memory in case.input.memories}
    if not actual_sources <= input_ids:
        failures.append("unknown_source_memory_id")

    if isinstance(expected_action, DerivedSummaryExpectation) and isinstance(
        actual_action, DerivedSummaryResponse
    ):
        if len(actual_action.summary.split()) > expected_action.max_summary_words:
            failures.append("summary_exceeds_word_limit")

    return GradeResult(
        hard_pass=not failures,
        failures=tuple(failures),
        **semantic_review,
    )


def _semantic_review(case: SculptorEvalCase) -> dict[str, object]:
    if not isinstance(case.expected, ExpectedCurationProposal):
        return {
            "semantic_review_required": False,
            "semantic_criteria": (),
            "forbidden_semantic_claims": (),
        }

    action = case.expected.action
    if isinstance(action, (DerivedSummaryExpectation, TopicGroupExpectation)):
        return {
            "semantic_review_required": True,
            "semantic_criteria": action.semantic_review.criteria,
            "forbidden_semantic_claims": action.semantic_review.forbidden_claims,
        }
    return {
        "semantic_review_required": False,
        "semantic_criteria": (),
        "forbidden_semantic_claims": (),
    }
