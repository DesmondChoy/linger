"""Run current Serendipity cases through the production agent and fixture tools."""

from __future__ import annotations

import argparse
import asyncio
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field
from pydantic_ai import Agent
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models import Model
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext
from pydantic_evals.reporting import ReportCaseFailure

from apps.backend.config import get_settings
from apps.backend.contracts import EvidenceBundle, EvidenceItem
from apps.backend.telemetry import configure_component_evaluation_telemetry
from src.linger.agents.build import build_model
from src.linger.agents.contracts import StrictModel
from src.linger.agents.serendipity.agent import build_serendipity_agent
from src.linger.agents.serendipity.models import (
    ConnectionDecline,
    ConnectionProposal,
    WebConnectionEvidence,
)
from src.linger.agents.serendipity.prompt import PROMPT_FINGERPRINT
from src.linger.agents.serendipity.skills import CONNECTION_DISCOVERY
from src.linger.agents.serendipity.tools import (
    GuardedExaSearch,
    SerendipityDependencies,
)
from src.linger.prompts import load_prompt

from .harness import (
    ExpectedProposal,
    GradeResult,
    RunObservation,
    SearchObservation,
    SemanticGrade,
    SerendipityEvalCase,
    dataset_digest,
    grade_serendipity_run,
    load_serendipity_eval_cases,
)


class SemanticDecision(StrictModel):
    criteria_met: tuple[str, ...] = ()
    criteria_failed: tuple[str, ...] = ()
    forbidden_claims_found: tuple[str, ...] = ()
    explanation: str = Field(min_length=1, max_length=2_000)


class CaseRunReport(StrictModel):
    case_id: str
    primary_behavior: str
    contrast_group: str
    observation: RunObservation
    grade: GradeResult


class CaseExecutionErrorReport(StrictModel):
    case_id: str
    primary_behavior: str
    contrast_group: str
    error_message: str
    trace_id: str | None


class SuiteSummary(StrictModel):
    case_count: int
    hard_pass_count: int
    hard_fail_count: int
    execution_error_count: int
    semantic_pass_count: int
    semantic_fail_count: int
    semantic_not_reviewed_count: int


class SuiteRunReport(StrictModel):
    schema_version: Literal[2] = 2
    run_id: str
    generated_at: datetime
    dataset_digest: str
    model: str
    skill_id: str = CONNECTION_DISCOVERY.skill_id
    prompt_template_id: str
    prompt_digest: str
    git_revision: str | None
    logfire_trace_id: str | None
    summary: SuiteSummary
    cases: tuple[CaseRunReport | CaseExecutionErrorReport, ...]


class _FixtureLibrarian:
    def __init__(self, evidence: tuple[EvidenceItem, ...]) -> None:
        self.evidence = evidence

    def retrieve(self, _request: object) -> EvidenceBundle:
        return EvidenceBundle(
            items=list(self.evidence),
            retrieval_note="Fixture-backed Serendipity component evaluation.",
        )


class _FixtureExaClient:
    def __init__(self, evidence: tuple[WebConnectionEvidence, ...]) -> None:
        self.evidence = evidence

    async def search(self, *_args: object, **_kwargs: object) -> object:
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    url=item.evidence_id,
                    title=item.title,
                    published_date=None,
                    author=None,
                    highlights=[item.excerpt[:500]],
                )
                for item in self.evidence
            ],
            output=None,
        )

    async def get_contents(self, urls: object, **_kwargs: object) -> object:
        requested = {urls} if isinstance(urls, str) else set(urls)
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    url=item.evidence_id,
                    title=item.title,
                    published_date=None,
                    author=None,
                    text=item.excerpt,
                )
                for item in self.evidence
                if item.evidence_id in requested
            ]
        )


def _web_capability(case: SerendipityEvalCase) -> GuardedExaSearch:
    evidence = tuple(
        item for item in case.tool_evidence if isinstance(item, WebConnectionEvidence)
    )
    return GuardedExaSearch(
        num_results=5,
        max_text_chars=8_000,
        include_deep_search=False,
        client=_FixtureExaClient(evidence),
        # The selected production skill owns instructions; tools return fixtures only.
        guidance="",
    )


def _usage_value(usage: object, name: str) -> int | None:
    value = getattr(usage, name, None)
    return value if isinstance(value, int) else None


async def review_semantics(
    case: SerendipityEvalCase,
    response: dict[str, object],
    *,
    model: Model | None = None,
) -> SemanticGrade:
    """Apply an optional structured secondary-model rubric to one proposal."""
    if not isinstance(case.expected, ExpectedProposal):
        return SemanticGrade()
    reviewer = Agent(
        model or build_model(),
        name="SerendipitySemanticReviewer",
        output_type=SemanticDecision,
        instructions=load_prompt("evaluation", "serendipity_review"),
    )
    result = await reviewer.run(
        case.model_dump_json(include={"input", "tool_evidence", "expected"})
        + "\nObserved response:\n"
        + str(response)
    )
    decision = result.output
    failed = bool(decision.criteria_failed or decision.forbidden_claims_found)
    return SemanticGrade(
        status="fail" if failed else "pass",
        criteria_met=decision.criteria_met,
        criteria_failed=decision.criteria_failed,
        forbidden_claims_found=decision.forbidden_claims_found,
        explanation=decision.explanation,
    )


async def run_case(
    case: SerendipityEvalCase,
    *,
    model: Model | None = None,
    agent: Any | None = None,
    semantic_model: Model | None = None,
    run_semantic_review: bool = False,
) -> CaseRunReport:
    """Execute the production agent with case-owned Librarian and Exa fixtures."""
    book_evidence = tuple(
        item for item in case.tool_evidence if isinstance(item, EvidenceItem)
    )
    deps = SerendipityDependencies(
        task=case.input,
        librarian=_FixtureLibrarian(book_evidence),  # type: ignore[arg-type]
    )
    capabilities = (
        [_web_capability(case)]
        if "web" in case.input.scope.allowed_sources
        else []
    )
    active_agent = agent or build_serendipity_agent(model)
    started = perf_counter()
    result = await active_agent.run(
        case.input.model_dump_json(),
        deps=deps,
        capabilities=capabilities,
        **CONNECTION_DISCOVERY.run_options(),
    )
    latency = perf_counter() - started
    messages = result.all_messages()
    tool_calls = sum(
        isinstance(part, ToolCallPart)
        for message in messages
        for part in message.parts
    )
    usage = result.usage
    model_requests = _usage_value(usage, "requests") or 0
    recorded_tool_calls = _usage_value(usage, "tool_calls")
    available_tools = ["search_librarian"]
    if capabilities:
        available_tools.extend(("web_search", "get_page"))
    observation = RunObservation(
        response=result.output.model_dump(mode="json"),
        evidence=tuple(deps.evidence.values()),
        searches=tuple(
            SearchObservation(
                operation=search.operation,
                source=search.source,
                outcome=search.outcome,
            )
            for search in deps.searches
        ),
        available_tools=tuple(available_tools),
        model_requests=model_requests,
        tool_calls=recorded_tool_calls if recorded_tool_calls is not None else tool_calls,
        latency_seconds=latency,
        input_tokens=_usage_value(usage, "input_tokens"),
        output_tokens=_usage_value(usage, "output_tokens"),
    )
    semantic_grade = (
        await review_semantics(case, observation.response, model=semantic_model)
        if run_semantic_review and isinstance(result.output, ConnectionProposal)
        else SemanticGrade()
    )
    return CaseRunReport(
        case_id=case.case_id,
        primary_behavior=case.primary_behavior,
        contrast_group=case.contrast_group,
        observation=observation,
        grade=grade_serendipity_run(
            case,
            observation,
            semantic_grade=semantic_grade,
        ),
    )


@dataclass(repr=False)
class _HardGateEvaluator(
    Evaluator[SerendipityEvalCase, CaseRunReport, dict[str, object]]
):
    def evaluate(
        self,
        ctx: EvaluatorContext[
            SerendipityEvalCase,
            CaseRunReport,
            dict[str, object],
        ],
    ) -> str:
        return "pass" if ctx.output.grade.hard_pass else "fail"

    def get_default_evaluation_name(self) -> str:
        return "serendipity_component_hard_gate"


def _git_revision() -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def _ordered_results(
    cases: tuple[SerendipityEvalCase, ...],
    outputs: tuple[CaseRunReport, ...],
    failures: tuple[
        ReportCaseFailure[SerendipityEvalCase, CaseRunReport, dict[str, object]],
        ...,
    ],
) -> tuple[CaseRunReport | CaseExecutionErrorReport, ...]:
    """Preserve dataset order while making captured task errors reportable."""
    outputs_by_id = {output.case_id: output for output in outputs}
    failures_by_id = {failure.name: failure for failure in failures}
    ordered: list[CaseRunReport | CaseExecutionErrorReport] = []
    for case in cases:
        output = outputs_by_id.get(case.case_id)
        failure = failures_by_id.get(case.case_id)
        if output is not None and failure is not None:
            raise RuntimeError(f"case produced both an output and failure: {case.case_id}")
        if output is not None:
            ordered.append(output)
            continue
        if failure is None:
            raise RuntimeError(f"case produced neither output nor failure: {case.case_id}")
        ordered.append(
            CaseExecutionErrorReport(
                case_id=case.case_id,
                primary_behavior=case.primary_behavior,
                contrast_group=case.contrast_group,
                error_message=failure.error_message,
                trace_id=failure.trace_id,
            )
        )
    return tuple(ordered)


async def run_suite(
    *,
    cases: tuple[SerendipityEvalCase, ...] | None = None,
    model: Model | None = None,
    semantic_model: Model | None = None,
    run_semantic_review: bool = False,
    configure_logfire: bool = True,
) -> SuiteRunReport:
    """Run all current cases and retain a reproducible report."""
    active_cases = cases or load_serendipity_eval_cases()
    agent = build_serendipity_agent(model)
    if configure_logfire:
        configure_component_evaluation_telemetry(agent)
    run_id = uuid4().hex
    outputs: list[CaseRunReport] = []

    async def evaluate_case(case: SerendipityEvalCase) -> CaseRunReport:
        output = await run_case(
            case,
            model=model,
            agent=agent,
            semantic_model=semantic_model,
            run_semantic_review=run_semantic_review,
        )
        outputs.append(output)
        return output

    dataset = Dataset(
        name="serendipity-component",
        cases=[
            Case(
                name=case.case_id,
                inputs=case,
                metadata={
                    "scope": "component",
                    "owner": "serendipity",
                    "skill_id": CONNECTION_DISCOVERY.skill_id,
                    "primary_behavior": case.primary_behavior,
                    "contrast_group": case.contrast_group,
                },
            )
            for case in active_cases
        ],
        evaluators=[_HardGateEvaluator()],
    )
    eval_report = await dataset.evaluate(
        evaluate_case,
        name=f"serendipity-component-{run_id[:8]}",
        task_name="serendipity_fixture_backed_agent",
        max_concurrency=1,
        progress=False,
        metadata={
            "content_classification": "synthetic_and_public",
            "evaluation_scope": "component",
            "dataset_digest": dataset_digest(active_cases),
            "run_id": run_id,
        },
    )
    ordered = _ordered_results(
        active_cases,
        tuple(outputs),
        tuple(eval_report.failures),
    )
    completed = tuple(
        output for output in ordered if isinstance(output, CaseRunReport)
    )
    execution_error_count = len(ordered) - len(completed)
    semantic_statuses = [output.grade.semantic_grade.status for output in completed]
    summary = SuiteSummary(
        case_count=len(ordered),
        hard_pass_count=sum(output.grade.hard_pass for output in completed),
        hard_fail_count=(
            sum(not output.grade.hard_pass for output in completed)
            + execution_error_count
        ),
        execution_error_count=execution_error_count,
        semantic_pass_count=semantic_statuses.count("pass"),
        semantic_fail_count=semantic_statuses.count("fail"),
        semantic_not_reviewed_count=(
            semantic_statuses.count("not_reviewed") + execution_error_count
        ),
    )
    return SuiteRunReport(
        run_id=run_id,
        generated_at=datetime.now(UTC),
        dataset_digest=dataset_digest(active_cases),
        model=get_settings().linger_model,
        prompt_template_id=PROMPT_FINGERPRINT.template_id,
        prompt_digest=PROMPT_FINGERPRINT.digest,
        git_revision=_git_revision(),
        logfire_trace_id=eval_report.trace_id,
        summary=summary,
        cases=ordered,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--semantic-review", action="store_true")
    parser.add_argument("--no-logfire", action="store_true")
    return parser


async def _main() -> None:
    args = _parser().parse_args()
    report = await run_suite(
        run_semantic_review=args.semantic_review,
        configure_logfire=not args.no_logfire,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    asyncio.run(_main())
