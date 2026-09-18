"""Test named-source support and complementary contributions to joint claims."""

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

from evals.provenance.harness import StrictModel, run_case, run_report_command
from evals.provenance.risk_codes import (
    CaseGrade,
    RiskCodeEvalCase,
    grade_review,
    review_with_configured_agent,
)
from src.linger.agents.provenance.prompt import PROMPT_FINGERPRINT

DEFAULT_CASES = Path(__file__).with_name("claim-mapping-cases.json")
DEFAULT_REPORT = Path(__file__).resolve().parents[2] / "tmp/provenance-claim-mapping-report.json"


class ClaimMappingCases(StrictModel):
    case_set_id: Literal["provenance-claim-mapping-v1"]
    cases: tuple[RiskCodeEvalCase, RiskCodeEvalCase, RiskCodeEvalCase, RiskCodeEvalCase]


class CaseResult(StrictModel):
    case_id: str
    expected_response_decision: str
    expected_response_codes: tuple[str, ...]
    grade: CaseGrade
    error_type: str | None
    latency_ms: float


class Summary(StrictModel):
    cases_total: int
    cases_passed: int
    targets_pass: bool


class ClaimMappingReport(StrictModel):
    generated_at: datetime
    case_set_id: str
    case_set_digest: str
    model: str
    prompt_template_id: str
    prompt_digest: str
    summary: Summary
    cases: tuple[CaseResult, ...]


def load_cases(path: Path = DEFAULT_CASES) -> ClaimMappingCases:
    return ClaimMappingCases.model_validate_json(path.read_bytes())


async def run_evaluation(*, gate=None, model_name: str | None = None) -> ClaimMappingReport:
    """Review each fixed candidate once through the existing production adapter."""
    case_set = load_cases()
    if model_name is None:
        if gate is None:
            from apps.backend.config import get_settings

            model_name = get_settings().linger_model
        else:
            model_name = "injected-gate"
    selected_gate = gate if gate is not None else review_with_configured_agent
    results = []
    for case in case_set.cases:
        grade, error_type, latency_ms = await run_case(
            case,
            selected_gate,
            grade_review,
            lambda: CaseGrade(actual_decision=None, passed=False, failure_code="gate_error"),
        )
        results.append(CaseResult(
            case_id=case.case_id,
            expected_response_decision=case.expected_response_decision,
            expected_response_codes=case.expected_response_codes,
            grade=grade,
            error_type=error_type,
            latency_ms=latency_ms,
        ))
    passed = sum(result.grade.passed for result in results)
    return ClaimMappingReport(
        generated_at=datetime.now(UTC),
        case_set_id=case_set.case_set_id,
        case_set_digest=sha256(case_set.model_dump_json().encode()).hexdigest(),
        model=model_name,
        prompt_template_id=PROMPT_FINGERPRINT.template_id,
        prompt_digest=PROMPT_FINGERPRINT.digest,
        summary=Summary(
            cases_total=len(results), cases_passed=passed, targets_pass=passed == len(results),
        ),
        cases=tuple(results),
    )


if __name__ == "__main__":
    run_report_command(run_evaluation, DEFAULT_REPORT, __doc__)
