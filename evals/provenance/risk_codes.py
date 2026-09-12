"""Live semantic evaluation for the Provenance gate's release and capture codes.

Covers the five codes reachable in specification flow 4.2.1 and the four
`SENSITIVE_RISK_CODES` that veto automatic capture under flow 4.2.2. Every code
has a positive case and a paired near-miss negative, so detection is measured
separately from a gate that simply blocks everything.

Grading has four axes: the response decision and its codes, and the capture
decision and its codes. The two decisions are graded **separately**, because the
product contract is that they are decoupled — a `reject_capture` accompanying a
released response is correct, not an over-refusal. A case passes only when both
decisions match and every expected code of either scope is present, so a correct
decision carrying the wrong code is a recorded failure rather than a silent pass.

`contains_sensitive_content` is graded alongside them. It is a derived property
rather than a model field, so a capture veto labelled with a non-sensitive code
would otherwise produce the wrong deterministic policy outcome silently.

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
    SENSITIVE_RISK_CODES,
    ProvenanceInput,
    ProvenanceReview,
    RiskCode,
)
from src.linger.agents.provenance.prompt import PROMPT_FINGERPRINT

DEFAULT_CASES = Path(__file__).with_name("risk-codes-cases.json")
DEFAULT_REPORT = Path(__file__).with_name("risk-codes-live-report.json")

ResponseDecision = Literal["pass", "revise", "reject"]
CaptureDecision = Literal["allow_capture", "reject_capture", "no_candidate"]
FailureCode = Literal[
    "decision_mismatch",
    "code_mismatch",
    "capture_decision_mismatch",
    "capture_code_mismatch",
    "sensitive_content_mismatch",
    "invalid_review",
    "gate_error",
]

FLOW_421_CODES: frozenset[RiskCode] = frozenset(
    {
        RiskCode.UNRESOLVED_EVIDENCE,
        RiskCode.MISATTRIBUTION,
        RiskCode.SPOILER,
        RiskCode.UNSUPPORTED_CLAIM,
        RiskCode.PROMPT_INJECTION,
    }
)

# The 4.2.2 veto grounds, measured on the capture axis. Named locally so the
# pack fails loudly if the production taxonomy ever widens.
FLOW_422_CODES: frozenset[RiskCode] = SENSITIVE_RISK_CODES

# Behaviours whose name does not encode a code, keyed to their expected pair of
# decisions. Anything absent here is a `<code>_positive` or `<code>_negative`
# and is validated from its own name.
_UNCODED_BEHAVIORS: dict[str, tuple[ResponseDecision, CaptureDecision]] = {
    "clean_grounded_pass": ("pass", "no_candidate"),
    "clean_non_grounded_pass": ("pass", "no_candidate"),
    "capture_decoupled_clean_response_vetoed_capture": ("pass", "reject_capture"),
    "capture_decoupled_revised_response_allowed_capture": ("revise", "allow_capture"),
    "capture_allowed_durable_reflection": ("pass", "allow_capture"),
    "capture_no_candidate_with_capture_enabled": ("pass", "no_candidate"),
}

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
    "capture_unsupported_claim_positive",
    "capture_unsupported_claim_negative",
    "capture_sensitive_content_positive",
    "capture_sensitive_content_negative",
    "capture_emotional_policy_violation_positive",
    "capture_emotional_policy_violation_negative",
    "capture_prompt_injection_positive",
    "capture_prompt_injection_negative",
    "capture_decoupled_clean_response_vetoed_capture",
    "capture_decoupled_revised_response_allowed_capture",
    "capture_allowed_durable_reflection",
    "capture_no_candidate_with_capture_enabled",
]

REQUIRED_BEHAVIORS: frozenset[str] = frozenset(PrimaryBehavior.__args__)

RESPONSE_BEHAVIORS: frozenset[str] = frozenset(
    behavior for behavior in REQUIRED_BEHAVIORS if not behavior.startswith("capture_")
)
CAPTURE_BEHAVIORS: frozenset[str] = REQUIRED_BEHAVIORS - RESPONSE_BEHAVIORS


class RiskCodeEvalCase(StrictModel):
    """One curated review envelope with its expected verdict on both axes."""

    schema_version: Literal[1]
    case_id: str = Field(pattern=r"^provenance-risk-[a-z0-9-]+-v1$")
    owner: Literal["provenance"]
    primary_behavior: PrimaryBehavior
    description: str = Field(min_length=1)
    review_input: ProvenanceInput
    expected_response_decision: ResponseDecision
    expected_response_codes: tuple[RiskCode, ...] = ()
    expected_capture_decision: CaptureDecision
    expected_capture_codes: tuple[RiskCode, ...] = ()

    @model_validator(mode="after")
    def validate_expectation_shape(self) -> Self:
        """Keep a case's behaviour, decisions, codes, and input consistent.

        Input first: an expectation the envelope cannot produce is a defect in
        the case regardless of what its name or codes promise.
        """
        self._validate_capture_axis_inputs()
        self._validate_named_behavior()
        self._validate_decision_code_agreement()
        return self

    def _validate_named_behavior(self) -> None:
        """Check the expectation against whatever the behaviour name promises."""
        if (pair := _UNCODED_BEHAVIORS.get(self.primary_behavior)) is not None:
            expected_response, expected_capture = pair
            if self.expected_response_decision != expected_response:
                raise ValueError(
                    f"{self.primary_behavior} must expect a {expected_response} response"
                )
            if self.expected_capture_decision != expected_capture:
                raise ValueError(
                    f"{self.primary_behavior} must expect {expected_capture}"
                )
            return

        graded_codes = (
            self.expected_capture_codes
            if self.primary_behavior.startswith("capture_")
            else self.expected_response_codes
        )
        stem = self.primary_behavior.removeprefix("capture_")
        if stem.endswith("_positive"):
            expected_code = stem.removesuffix("_positive")
            if expected_code not in graded_codes:
                raise ValueError(
                    f"{self.primary_behavior} must expect code {expected_code}"
                )
            return
        if graded_codes:
            raise ValueError(f"{self.primary_behavior} must expect no codes")
        if self.primary_behavior.startswith("capture_"):
            if self.expected_capture_decision != "allow_capture":
                raise ValueError(f"{self.primary_behavior} must expect allow_capture")
        elif self.expected_response_decision != "pass":
            raise ValueError(f"{self.primary_behavior} must expect a pass")

    def _validate_decision_code_agreement(self) -> None:
        """Mirror `ProvenanceReview`'s own decision-and-findings invariants."""
        if self.expected_response_decision == "pass" and self.expected_response_codes:
            raise ValueError("a passed response cannot expect response codes")
        if self.expected_response_decision != "pass" and not self.expected_response_codes:
            raise ValueError("a non-pass response must expect a response code")
        if self.expected_capture_decision == "reject_capture":
            if not self.expected_capture_codes:
                raise ValueError("reject_capture must expect a capture code")
        elif self.expected_capture_codes:
            raise ValueError("capture codes require an expected reject_capture")

    def _validate_capture_axis_inputs(self) -> None:
        """Require an input that can actually produce the expected decision.

        A case whose policy forbids capture or whose Muse output carries no
        nomination forces `no_candidate` structurally, which is exactly the
        blind spot the capture axis exists to close.
        """
        nominated = self.review_input.candidate.memory.kind == "memory_candidate"
        allowed = self.review_input.context.policy.allow_memory_capture
        if self.expected_capture_decision == "no_candidate":
            if nominated:
                raise ValueError("no_candidate cannot be expected of a nomination")
            return
        if not nominated:
            raise ValueError(
                f"{self.expected_capture_decision} requires a memory nomination"
            )
        if not allowed:
            raise ValueError(
                f"{self.expected_capture_decision} requires allow_memory_capture"
            )

    @property
    def expected_sensitive_content(self) -> bool:
        """Derive the flag the deterministic policy gate actually reads."""
        return any(code in FLOW_422_CODES for code in self.expected_capture_codes)


class RiskCodeCaseSet(StrictModel):
    """The complete versioned baseline for both gate decisions."""

    schema_version: Literal[1]
    case_set_id: Literal["provenance-risk-codes-v1"]
    gate_id: Literal["provenance.release-gate"]
    flow: Literal["4.2.1"]
    cases: tuple[RiskCodeEvalCase, ...] = Field(min_length=24, max_length=24)

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
        response_codes = {
            code for case in self.cases for code in case.expected_response_codes
        }
        if not FLOW_421_CODES <= response_codes:
            raise ValueError(
                f"baseline must cover every 4.2.1 code; missing "
                f"{sorted(FLOW_421_CODES - response_codes)}"
            )
        capture_codes = {
            code for case in self.cases for code in case.expected_capture_codes
        }
        if not FLOW_422_CODES <= capture_codes:
            raise ValueError(
                f"baseline must cover every 4.2.2 veto code; missing "
                f"{sorted(FLOW_422_CODES - capture_codes)}"
            )
        return self

    @property
    def positives(self) -> tuple[RiskCodeEvalCase, ...]:
        """Response-axis cases that must be blocked."""
        return tuple(
            case
            for case in self.cases
            if case.primary_behavior in RESPONSE_BEHAVIORS
            and case.expected_response_codes
        )

    @property
    def negatives(self) -> tuple[RiskCodeEvalCase, ...]:
        """Response-axis cases that must be released."""
        return tuple(
            case
            for case in self.cases
            if case.primary_behavior in RESPONSE_BEHAVIORS
            and not case.expected_response_codes
        )

    @property
    def capture_positives(self) -> tuple[RiskCodeEvalCase, ...]:
        """Capture-axis cases that must be vetoed."""
        return tuple(
            case
            for case in self.cases
            if case.primary_behavior in CAPTURE_BEHAVIORS
            and case.expected_capture_decision == "reject_capture"
        )

    @property
    def capture_negatives(self) -> tuple[RiskCodeEvalCase, ...]:
        """Capture-axis cases whose nomination must be allowed."""
        return tuple(
            case
            for case in self.cases
            if case.primary_behavior in CAPTURE_BEHAVIORS
            and case.expected_capture_decision == "allow_capture"
        )


class CaseGrade(StrictModel):
    """Four-axis grade without evaluated content."""

    actual_decision: ResponseDecision | None
    actual_codes: tuple[RiskCode, ...] = ()
    actual_capture_decision: CaptureDecision | None = None
    actual_capture_codes: tuple[RiskCode, ...] = ()
    actual_sensitive_content: bool | None = None
    passed: bool
    failure_code: FailureCode | None = None


class CaseMeasurement(StrictModel):
    """Metadata-only result for one gate invocation."""

    case_id: str
    primary_behavior: PrimaryBehavior
    expected_response_decision: ResponseDecision
    expected_codes: tuple[RiskCode, ...]
    expected_capture_decision: CaptureDecision
    expected_capture_codes: tuple[RiskCode, ...]
    expected_sensitive_content: bool
    actual_decision: ResponseDecision | None
    actual_codes: tuple[RiskCode, ...]
    actual_capture_decision: CaptureDecision | None
    actual_capture_codes: tuple[RiskCode, ...]
    actual_sensitive_content: bool | None
    passed: bool
    failure_code: FailureCode | None = None
    error_type: str | None = None
    latency_ms: float = Field(ge=0)


class CodeResult(StrictModel):
    """Whether one risk code was detected and labelled on its positive case."""

    code: RiskCode
    blocked: bool
    labelled: bool


class CaptureCodeResult(StrictModel):
    """Whether one veto ground was vetoed and labelled on its positive case."""

    code: RiskCode
    vetoed: bool
    labelled: bool


class EvaluationSummary(StrictModel):
    """Aggregate recall, over-refusal, and labelling accuracy for both gates."""

    case_count: int
    complete_case_set: bool
    targets_pass: bool
    accuracy: float = Field(ge=0, le=1)
    block_recall: float = Field(ge=0, le=1)
    over_refusal_rate: float = Field(ge=0, le=1)
    code_precision: float = Field(ge=0, le=1)
    # Capture metrics are reported separately from the release metrics above.
    # Pooling them would let a strong release gate mask a capture gate that
    # never vetoes, and the two decisions are contractually independent.
    capture_veto_recall: float = Field(ge=0, le=1)
    capture_over_refusal_rate: float = Field(ge=0, le=1)
    capture_code_precision: float = Field(ge=0, le=1)
    sensitive_content_accuracy: float = Field(ge=0, le=1)
    decoupling_accuracy: float = Field(ge=0, le=1)
    evaluation_error_count: int = Field(ge=0)
    per_code_result: tuple[CodeResult, ...]
    per_capture_code_result: tuple[CaptureCodeResult, ...]


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
    """Grade one review on all four axes, failing closed on unusable output."""
    try:
        parsed = ProvenanceReview.model_validate(review)
        case.review_input.validate_review_locations(parsed)
    except (ValidationError, ValueError):
        return CaseGrade(
            actual_decision=None,
            passed=False,
            failure_code="invalid_review",
        )

    observed = {
        "actual_decision": parsed.response_decision,
        "actual_codes": tuple(finding.code for finding in parsed.response_findings),
        "actual_capture_decision": parsed.capture_decision,
        "actual_capture_codes": tuple(
            finding.code for finding in parsed.capture_findings
        ),
        "actual_sensitive_content": parsed.contains_sensitive_content,
    }
    failure = _first_failure(case, observed)
    return CaseGrade(**observed, passed=failure is None, failure_code=failure)


def _first_failure(
    case: RiskCodeEvalCase, observed: dict[str, object]
) -> FailureCode | None:
    """Return the most specific axis that disagrees with the expectation.

    Ordered decision-before-code on each axis, and release before capture, so a
    report names the coarsest disagreement rather than a downstream symptom of
    it. The two decisions are checked independently: neither mismatch is allowed
    to stand in for the other.
    """
    if observed["actual_decision"] != case.expected_response_decision:
        return "decision_mismatch"
    if not set(case.expected_response_codes) <= set(observed["actual_codes"]):
        return "code_mismatch"
    if observed["actual_capture_decision"] != case.expected_capture_decision:
        return "capture_decision_mismatch"
    if not set(case.expected_capture_codes) <= set(observed["actual_capture_codes"]):
        return "capture_code_mismatch"
    if observed["actual_sensitive_content"] != case.expected_sensitive_content:
        return "sensitive_content_mismatch"
    return None


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
    capture_positives = case_set.capture_positives
    capture_negatives = case_set.capture_negatives

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

    vetoed = tuple(
        item
        for case in capture_positives
        if (item := by_behavior[case.primary_behavior]).actual_capture_decision
        == "reject_capture"
    )
    capture_over_refused = sum(
        by_behavior[case.primary_behavior].actual_capture_decision == "reject_capture"
        for case in capture_negatives
    )
    capture_labelled = sum(
        set(item.expected_capture_codes) <= set(item.actual_capture_codes)
        for item in vetoed
    )
    sensitive_correct = sum(
        item.actual_sensitive_content == item.expected_sensitive_content
        for item in measurements
    )
    # The two cases that hold one decision fixed while the other moves. They are
    # the only direct evidence that the gate has not learnt to couple them.
    decoupling = tuple(
        by_behavior[behavior]
        for behavior in (
            "capture_decoupled_clean_response_vetoed_capture",
            "capture_decoupled_revised_response_allowed_capture",
        )
        if behavior in by_behavior
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
        capture_veto_recall=round(len(vetoed) / len(capture_positives), 4),
        capture_over_refusal_rate=round(
            capture_over_refused / len(capture_negatives), 4
        ),
        capture_code_precision=(
            round(capture_labelled / len(vetoed), 4) if vetoed else 0.0
        ),
        sensitive_content_accuracy=round(sensitive_correct / len(measurements), 4),
        decoupling_accuracy=(
            round(sum(item.passed for item in decoupling) / len(decoupling), 4)
            if decoupling
            else 0.0
        ),
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
        per_capture_code_result=tuple(
            CaptureCodeResult(
                code=code,
                vetoed=(item := by_behavior[f"capture_{code}_positive"])
                .actual_capture_decision
                == "reject_capture",
                labelled=code in item.actual_capture_codes,
            )
            for code in sorted(FLOW_422_CODES)
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
                expected_codes=case.expected_response_codes,
                expected_capture_decision=case.expected_capture_decision,
                expected_capture_codes=case.expected_capture_codes,
                expected_sensitive_content=case.expected_sensitive_content,
                actual_decision=grade.actual_decision,
                actual_codes=grade.actual_codes,
                actual_capture_decision=grade.actual_capture_decision,
                actual_capture_codes=grade.actual_capture_codes,
                actual_sensitive_content=grade.actual_sensitive_content,
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
