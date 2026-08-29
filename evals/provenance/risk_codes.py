"""Live semantic evaluation for the Provenance candidate gate's risk codes.

Covers the five codes reachable in specification flow 4.2.1. Every code has a
positive case and a paired near-miss negative, so detection is measured
separately from a gate that simply blocks everything.

Grading has two axes. A case passes only when the response decision matches and
every expected code is present, so a correct decision carrying the wrong code is
a recorded failure rather than a silent pass.

Reports contain case IDs, labels, codes, and runtime metadata only. They never
retain candidate text, evidence text, or model rationales.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator

from evals.provenance.harness import StrictModel, run_case, run_report_command
from src.linger.agents.provenance.models import (
    ProvenanceInput,
    ProvenanceReview,
    RiskCode,
)
from src.linger.agents.provenance.prompt import PROMPT_FINGERPRINT

DEFAULT_CASES = Path(__file__).with_name("risk-codes-cases.json")
DEFAULT_REPORT = Path(__file__).with_name("risk-codes-live-report.json")

ResponseDecision = Literal["pass", "revise", "reject"]
FailureCode = Literal[
    "decision_mismatch",
    "code_mismatch",
    "invalid_review",
    "gate_error",
]

FLOW_421_CODES: frozenset[RiskCode] = frozenset(
    {
        "unresolved_evidence",
        "misattribution",
        "spoiler",
        "unsupported_claim",
        "prompt_injection",
    }
)

PrimaryBehavior = Literal[
    "unresolved_evidence_positive",
    "unresolved_evidence_negative",
    "misattribution_positive",
    "misattribution_negative",
    "spoiler_positive",
    "spoiler_negative",
    "unsupported_claim_positive",
    "unsupported_claim_negative",
    "prompt_injection_positive",
    "prompt_injection_negative",
    "clean_grounded_pass",
    "clean_non_grounded_pass",
]

REQUIRED_BEHAVIORS: frozenset[str] = frozenset(PrimaryBehavior.__args__)


class RiskCodeEvalCase(StrictModel):
    """One curated review envelope with its expected verdict."""

    schema_version: Literal[1]
    case_id: str = Field(pattern=r"^provenance-risk-[a-z0-9-]+-v1$")
    owner: Literal["provenance"]
    primary_behavior: PrimaryBehavior
    description: str = Field(min_length=1)
    review_input: ProvenanceInput
    expected_response_decision: ResponseDecision
    expected_codes: tuple[RiskCode, ...] = ()

    @model_validator(mode="after")
    def validate_expectation_shape(self) -> Self:
        """Keep a case's behaviour, decision, and codes mutually consistent."""
        if self.primary_behavior.endswith("_positive"):
            expected_code = self.primary_behavior.removesuffix("_positive")
            if self.expected_response_decision == "pass":
                raise ValueError(f"{self.primary_behavior} must not expect a pass")
            if expected_code not in self.expected_codes:
                raise ValueError(
                    f"{self.primary_behavior} must expect code {expected_code}"
                )
            return self
        if self.expected_response_decision != "pass":
            raise ValueError(f"{self.primary_behavior} must expect a pass")
        if self.expected_codes:
            raise ValueError(f"{self.primary_behavior} must expect no codes")
        return self


class RiskCodeCaseSet(StrictModel):
    """The complete versioned candidate-gate baseline."""

    schema_version: Literal[1]
    case_set_id: Literal["provenance-risk-codes-v1"]
    gate_id: Literal["provenance.release-gate"]
    flow: Literal["4.2.1"]
    cases: tuple[RiskCodeEvalCase, ...] = Field(min_length=12, max_length=12)

    @model_validator(mode="after")
    def validate_topology(self) -> Self:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("risk-code case IDs must be unique")
        behaviors = {case.primary_behavior for case in self.cases}
        if behaviors != REQUIRED_BEHAVIORS:
            raise ValueError(
                "risk-code baseline must contain exactly one case for each "
                "required behavior"
            )
        covered = {code for case in self.cases for code in case.expected_codes}
        if not FLOW_421_CODES <= covered:
            raise ValueError(
                f"baseline must cover every 4.2.1 code; missing "
                f"{sorted(FLOW_421_CODES - covered)}"
            )
        return self

    @property
    def positives(self) -> tuple[RiskCodeEvalCase, ...]:
        return tuple(case for case in self.cases if case.expected_codes)

    @property
    def negatives(self) -> tuple[RiskCodeEvalCase, ...]:
        return tuple(case for case in self.cases if not case.expected_codes)


class CaseGrade(StrictModel):
    """Two-axis grade without evaluated content."""

    actual_decision: ResponseDecision | None
    actual_codes: tuple[RiskCode, ...] = ()
    passed: bool
    failure_code: FailureCode | None = None


class CaseMeasurement(StrictModel):
    """Metadata-only result for one gate invocation."""

    case_id: str
    primary_behavior: PrimaryBehavior
    expected_response_decision: ResponseDecision
    expected_codes: tuple[RiskCode, ...]
    actual_decision: ResponseDecision | None
    actual_codes: tuple[RiskCode, ...]
    passed: bool
    failure_code: FailureCode | None = None
    error_type: str | None = None
    latency_ms: float = Field(ge=0)


class CodeResult(StrictModel):
    """Whether one risk code was detected and labelled on its positive case."""

    code: RiskCode
    blocked: bool
    labelled: bool


class EvaluationSummary(StrictModel):
    """Aggregate release-gate recall, over-refusal, and labelling accuracy."""

    case_count: int
    complete_case_set: bool
    targets_pass: bool
    accuracy: float = Field(ge=0, le=1)
    block_recall: float = Field(ge=0, le=1)
    over_refusal_rate: float = Field(ge=0, le=1)
    code_precision: float = Field(ge=0, le=1)
    evaluation_error_count: int = Field(ge=0)
    per_code_result: tuple[CodeResult, ...]


class EvaluationReport(StrictModel):
    """Versioned metadata-only live-evaluation report."""

    schema_version: Literal[1]
    generated_at: datetime
    case_set_id: Literal["provenance-risk-codes-v1"]
    gate_id: Literal["provenance.release-gate"]
    flow: Literal["4.2.1"]
    model: str
    prompt_template_id: str
    prompt_version: str
    prompt_digest: str
    summary: EvaluationSummary
    cases: tuple[CaseMeasurement, ...]


def load_risk_code_cases(path: Path = DEFAULT_CASES) -> RiskCodeCaseSet:
    """Load and validate the complete curated gate baseline."""
    try:
        return RiskCodeCaseSet.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise ValueError(f"invalid risk-code eval case set: {path}") from exc


def grade_review(case: RiskCodeEvalCase, review: object) -> CaseGrade:
    """Grade one review on both axes, failing closed on unusable output."""
    try:
        parsed = ProvenanceReview.model_validate(review)
        case.review_input.validate_review_locations(parsed)
    except (ValidationError, ValueError):
        return CaseGrade(
            actual_decision=None,
            passed=False,
            failure_code="invalid_review",
        )

    codes = tuple(finding.code for finding in parsed.response_findings)
    if parsed.response_decision != case.expected_response_decision:
        return CaseGrade(
            actual_decision=parsed.response_decision,
            actual_codes=codes,
            passed=False,
            failure_code="decision_mismatch",
        )
    if not set(case.expected_codes) <= set(codes):
        return CaseGrade(
            actual_decision=parsed.response_decision,
            actual_codes=codes,
            passed=False,
            failure_code="code_mismatch",
        )
    return CaseGrade(
        actual_decision=parsed.response_decision,
        actual_codes=codes,
        passed=True,
    )


async def review_with_configured_agent(case: RiskCodeEvalCase) -> ProvenanceReview:
    """Run the production gate exactly as `orchestration.reflection` calls it."""
    from src.linger.agents.provenance.agent import provenance_agent

    result = await provenance_agent.run(
        case.review_input.model_dump_json(),
    )
    return result.output


def _summarize(
    case_set: RiskCodeCaseSet, measurements: tuple[CaseMeasurement, ...]
) -> EvaluationSummary:
    by_behavior = {item.primary_behavior: item for item in measurements}
    positives = case_set.positives
    negatives = case_set.negatives

    blocked = tuple(
        item
        for case in positives
        if (item := by_behavior[case.primary_behavior]).actual_decision
        not in (None, "pass")
    )
    over_refused = sum(
        by_behavior[case.primary_behavior].actual_decision not in (None, "pass")
        for case in negatives
    )
    correctly_labelled = sum(
        set(by_behavior[case.primary_behavior].expected_codes)
        <= set(by_behavior[case.primary_behavior].actual_codes)
        for case in positives
        if by_behavior[case.primary_behavior] in blocked
    )
    passed_count = sum(item.passed for item in measurements)
    complete_case_set = {
        item.primary_behavior for item in measurements
    } == REQUIRED_BEHAVIORS

    return EvaluationSummary(
        case_count=len(measurements),
        complete_case_set=complete_case_set,
        targets_pass=complete_case_set and passed_count == len(measurements),
        accuracy=round(passed_count / len(measurements), 4),
        block_recall=round(len(blocked) / len(positives), 4),
        over_refusal_rate=round(over_refused / len(negatives), 4),
        code_precision=round(correctly_labelled / len(blocked), 4) if blocked else 0.0,
        evaluation_error_count=sum(
            item.actual_decision is None for item in measurements
        ),
        per_code_result=tuple(
            CodeResult(
                code=code,
                blocked=(item := by_behavior[f"{code}_positive"]).actual_decision
                not in (None, "pass"),
                labelled=code in item.actual_codes,
            )
            for code in sorted(FLOW_421_CODES)
        ),
    )


async def run_evaluation(
    *,
    gate=None,
    case_set: RiskCodeCaseSet | None = None,
    model_name: str | None = None,
) -> EvaluationReport:
    """Run every case and return a report that excludes evaluated content."""
    selected_cases = case_set or load_risk_code_cases()
    selected_gate = gate or review_with_configured_agent
    if model_name is None:
        if gate is None:
            from apps.backend.config import get_settings

            model_name = get_settings().linger_model
        else:
            model_name = "injected-gate"

    measurements: list[CaseMeasurement] = []
    for case in selected_cases.cases:
        grade, error_type, latency_ms = await run_case(
            case,
            selected_gate,
            grade_review,
            lambda: CaseGrade(
                actual_decision=None, passed=False, failure_code="gate_error"
            ),
        )
        measurements.append(
            CaseMeasurement(
                case_id=case.case_id,
                primary_behavior=case.primary_behavior,
                expected_response_decision=case.expected_response_decision,
                expected_codes=case.expected_codes,
                actual_decision=grade.actual_decision,
                actual_codes=grade.actual_codes,
                passed=grade.passed,
                failure_code=grade.failure_code,
                error_type=error_type,
                latency_ms=latency_ms,
            )
        )

    return EvaluationReport(
        schema_version=1,
        generated_at=datetime.now(UTC),
        case_set_id=selected_cases.case_set_id,
        gate_id=selected_cases.gate_id,
        flow=selected_cases.flow,
        model=model_name,
        prompt_template_id=PROMPT_FINGERPRINT.template_id,
        prompt_version=PROMPT_FINGERPRINT.version,
        prompt_digest=PROMPT_FINGERPRINT.digest,
        summary=_summarize(selected_cases, tuple(measurements)),
        cases=tuple(measurements),
    )


if __name__ == "__main__":
    run_report_command(run_evaluation, DEFAULT_REPORT, __doc__)
