"""Case contracts and observed hard gates for Serendipity evaluations."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, ValidationError, model_validator

from src.linger.agents.contracts import StrictModel
from src.linger.agents.serendipity.models import (
    SERENDIPITY_RESPONSE_ADAPTER,
    ConnectionDecline,
    ConnectionDiscoveryInput,
    ConnectionEvidence,
    ConnectionProposal,
    DeclineReason,
    PresentationMode,
    SerendipityResponse,
)

DEFAULT_CASE_DIRECTORY = Path(__file__).with_name("cases") / "current"
MAX_MODEL_REQUESTS = 8
MAX_TOOL_CALLS = 6

PrimaryBehavior = Literal[
    "route_book_relationship_to_librarian",
    "route_external_recommendation_to_web",
    "expand_source_only_when_justified",
    "stop_when_primary_source_is_sufficient",
    "select_evidence_with_a_real_semantic_bridge",
    "rank_the_strongest_supported_connection",
    "decline_when_no_supported_bridge_exists",
    "exclude_ineligible_evidence_before_selection",
]
REQUIRED_BEHAVIORS: frozenset[PrimaryBehavior] = frozenset(
    {
        "route_book_relationship_to_librarian",
        "route_external_recommendation_to_web",
        "expand_source_only_when_justified",
        "stop_when_primary_source_is_sufficient",
        "select_evidence_with_a_real_semantic_bridge",
        "rank_the_strongest_supported_connection",
        "decline_when_no_supported_bridge_exists",
        "exclude_ineligible_evidence_before_selection",
    }
)
SearchOperation = Literal["search_librarian", "web_search", "get_page"]
SemanticStatus = Literal["not_reviewed", "pass", "fail"]


class SemanticReview(StrictModel):
    """Criteria for a separate human or secondary-model judgment."""

    criteria: tuple[str, ...] = Field(min_length=1)
    forbidden_claims: tuple[str, ...] = ()


class ExpectedSearches(StrictModel):
    """Observable routing requirements, not fixture-authored assertions."""

    allowed_operations: tuple[SearchOperation, ...] = Field(min_length=1)
    required_operations: tuple[SearchOperation, ...] = Field(min_length=1)
    primary_operation: SearchOperation

    @model_validator(mode="after")
    def operations_are_coherent(self) -> Self:
        if len(self.allowed_operations) != len(set(self.allowed_operations)):
            raise ValueError("allowed search operations must be unique")
        if len(self.required_operations) != len(set(self.required_operations)):
            raise ValueError("required search operations must be unique")
        allowed = set(self.allowed_operations)
        if not set(self.required_operations).issubset(allowed):
            raise ValueError("required operations must also be allowed")
        if self.primary_operation not in self.required_operations:
            raise ValueError("primary operation must be required")
        return self


class ExpectedProposal(StrictModel):
    status: Literal["proposal"]
    required_evidence_ids: tuple[str, ...] = Field(min_length=1)
    presentation: PresentationMode
    semantic_review: SemanticReview


class ExpectedDecline(StrictModel):
    status: Literal["decline"]
    allowed_reasons: tuple[DeclineReason, ...] = Field(min_length=1)


ExpectedResponse = Annotated[
    ExpectedProposal | ExpectedDecline,
    Field(discriminator="status"),
]


class SerendipityEvalCase(StrictModel):
    """One current component case using canonical runtime contracts."""

    schema_version: Literal[3]
    case_id: str = Field(pattern=r"^serendipity-[a-z0-9-]+-v3$")
    owner: Literal["serendipity"]
    primary_behavior: PrimaryBehavior
    contrast_group: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1)
    input: ConnectionDiscoveryInput
    tool_evidence: tuple[ConnectionEvidence, ...]
    expected_searches: ExpectedSearches
    expected: ExpectedResponse

    @model_validator(mode="after")
    def case_contract_is_coherent(self) -> Self:
        if isinstance(self.expected, ExpectedProposal):
            available_ids = {item.evidence_id for item in self.tool_evidence}
            if not set(self.expected.required_evidence_ids).issubset(available_ids):
                raise ValueError("expected proposal cites evidence outside fixtures")

        granted = set(self.input.scope.allowed_sources)
        evidence_kinds = {item.source_kind for item in self.tool_evidence}
        if not evidence_kinds.issubset(granted):
            raise ValueError("fixture evidence exceeds the case source grant")
        if "web" in evidence_kinds and "get_page" not in self.expected_searches.required_operations:
            raise ValueError("citable web fixtures require an observed get_page")

        first = self.expected_searches.primary_operation
        if self.primary_behavior == "route_book_relationship_to_librarian" and first != "search_librarian":
            raise ValueError("book-relationship routing must start with Librarian")
        if self.primary_behavior == "route_external_recommendation_to_web" and first != "web_search":
            raise ValueError("external-recommendation routing must start with web search")
        if self.primary_behavior == "expand_source_only_when_justified":
            required = set(self.expected_searches.required_operations)
            if "search_librarian" not in required or "web_search" not in required:
                raise ValueError("source expansion must observe both book and web search")
        if self.primary_behavior == "stop_when_primary_source_is_sufficient":
            if len(self.expected_searches.allowed_operations) != 1:
                raise ValueError("primary-source stopping must permit only the primary operation")
        return self


class SearchObservation(StrictModel):
    operation: SearchOperation
    source: Literal["book_corpus", "web"]
    outcome: str


class RunObservation(StrictModel):
    """What the fixture-backed production agent actually did."""

    response: dict[str, object]
    evidence: tuple[ConnectionEvidence, ...]
    searches: tuple[SearchObservation, ...]
    available_tools: tuple[str, ...]
    model_requests: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    latency_seconds: float = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class SemanticGrade(StrictModel):
    status: SemanticStatus = "not_reviewed"
    criteria_met: tuple[str, ...] = ()
    criteria_failed: tuple[str, ...] = ()
    forbidden_claims_found: tuple[str, ...] = ()
    explanation: str | None = None


class GradeResult(StrictModel):
    hard_pass: bool
    failures: tuple[str, ...]
    semantic_review_required: bool
    semantic_criteria: tuple[str, ...] = ()
    forbidden_semantic_claims: tuple[str, ...] = ()
    semantic_grade: SemanticGrade = SemanticGrade()


def load_serendipity_eval_cases(
    case_directory: Path = DEFAULT_CASE_DIRECTORY,
) -> tuple[SerendipityEvalCase, ...]:
    """Load current cases and require minimum behavior and contrast coverage."""
    paths = sorted(case_directory.glob("*.json"))
    if not paths:
        raise ValueError("no current Serendipity evaluation cases found")
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
    observed = {case.primary_behavior for case in cases}
    missing = REQUIRED_BEHAVIORS - observed
    if missing:
        raise ValueError(f"Serendipity baseline is missing behaviors: {sorted(missing)}")
    contrast_counts: dict[str, int] = {}
    for case in cases:
        contrast_counts[case.contrast_group] = contrast_counts.get(case.contrast_group, 0) + 1
    if not any(count >= 2 for count in contrast_counts.values()):
        raise ValueError("Serendipity baseline requires at least one contrast pair")
    return tuple(cases)


def dataset_digest(cases: tuple[SerendipityEvalCase, ...]) -> str:
    """Stable identity over canonical validated case content."""
    payload = "\n".join(
        case.model_dump_json(exclude_none=True) for case in sorted(cases, key=lambda item: item.case_id)
    )
    return sha256(payload.encode()).hexdigest()


def grade_serendipity_run(
    case: SerendipityEvalCase,
    observation: RunObservation,
    *,
    semantic_grade: SemanticGrade | None = None,
) -> GradeResult:
    """Grade contracts and observed activity; semantic quality stays separate."""
    semantic_review = (
        case.expected.semantic_review
        if isinstance(case.expected, ExpectedProposal)
        else None
    )
    try:
        parsed = SERENDIPITY_RESPONSE_ADAPTER.validate_python(observation.response)
    except ValidationError as exc:
        return GradeResult(
            hard_pass=False,
            failures=(f"invalid_response:{exc.error_count()}_validation_error(s)",),
            semantic_review_required=semantic_review is not None,
            semantic_criteria=semantic_review.criteria if semantic_review else (),
            forbidden_semantic_claims=semantic_review.forbidden_claims if semantic_review else (),
            semantic_grade=semantic_grade or SemanticGrade(),
        )

    failures: list[str] = []
    operations = tuple(search.operation for search in observation.searches)
    expected_searches = case.expected_searches
    if not operations:
        failures.append("no_observed_search")
    elif operations[0] != expected_searches.primary_operation:
        failures.append(f"wrong_primary_search:{operations[0]}")
    for required in expected_searches.required_operations:
        if required not in operations:
            failures.append(f"missing_required_search:{required}")
    for operation in operations:
        if operation not in expected_searches.allowed_operations:
            failures.append(f"unexpected_search:{operation}")
    if observation.model_requests > MAX_MODEL_REQUESTS:
        failures.append("model_request_budget_exceeded")
    if observation.tool_calls > MAX_TOOL_CALLS:
        failures.append("tool_call_budget_exceeded")
    forbidden_tools = set(observation.available_tools) - {
        "search_librarian", "web_search", "get_page"
    }
    if forbidden_tools:
        failures.append(f"authority_surface_exceeded:{sorted(forbidden_tools)}")

    evidence_by_id = {item.evidence_id: item for item in observation.evidence}
    if len(evidence_by_id) != len(observation.evidence):
        failures.append("duplicate_observed_evidence_id")
    ceilings = {
        (scope.work_id, scope.book_version_id): scope.chapter_max
        for scope in case.input.scope.book_scopes
    }
    for item in observation.evidence:
        if item.source_kind not in case.input.scope.allowed_sources:
            failures.append(f"evidence_outside_source_grant:{item.evidence_id}")
        if item.source_kind == "book_corpus":
            ceiling = ceilings.get((item.work_id, item.book_version_id))
            if ceiling is None or item.chapter > ceiling:
                failures.append(f"evidence_outside_book_scope:{item.evidence_id}")

    if isinstance(case.expected, ExpectedDecline):
        if not isinstance(parsed, ConnectionDecline):
            failures.append("expected_decline")
        elif parsed.reason not in case.expected.allowed_reasons:
            failures.append(f"unexpected_decline_reason:{parsed.reason}")
    elif not isinstance(parsed, ConnectionProposal):
        failures.append("expected_proposal")
    else:
        selected_ids = parsed.selected_candidate.evidence_ids
        if not set(selected_ids).issubset(evidence_by_id):
            failures.append("proposal_references_unknown_evidence")
        if not set(case.expected.required_evidence_ids).issubset(selected_ids):
            failures.append("proposal_missing_required_evidence")
        if parsed.presentation != case.expected.presentation:
            failures.append("proposal_changed_presentation")
        selected_kinds = {
            evidence_by_id[item].source_kind
            for item in selected_ids
            if item in evidence_by_id
        }
        has_web_flag = "contains_web_claim" in parsed.policy_flags
        if ("web" in selected_kinds) != has_web_flag:
            failures.append("proposal_web_flag_mismatch")
        if "web" in selected_kinds and "get_page" not in operations:
            failures.append("web_evidence_not_opened")

    return GradeResult(
        hard_pass=not failures,
        failures=tuple(failures),
        semantic_review_required=semantic_review is not None,
        semantic_criteria=semantic_review.criteria if semantic_review else (),
        forbidden_semantic_claims=semantic_review.forbidden_claims if semantic_review else (),
        semantic_grade=semantic_grade or SemanticGrade(),
    )


EXPECTED_RESPONSE_ADAPTER = TypeAdapter(ExpectedResponse)
