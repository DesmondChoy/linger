"""Application-owned dispatch and validation for evidence-strength judgment."""

from __future__ import annotations

from typing import Any, Literal, Protocol

import logfire
from pydantic_ai import Agent, UsageLimits

from apps.backend.telemetry import run_agent_traced
from src.linger.agents.librarian.models import (
    BookEvidenceAssessment,
    BookRequestPlan,
    book_request_span_errors,
    EvidenceStrengthDecision,
    LibrarianBookRequestInput,
    LibrarianEvidenceStrengthInput,
)
from src.linger.agents.librarian.prompt import PROMPT_FINGERPRINT
from src.linger.agents.librarian.skills import BOOK_REQUEST, EVIDENCE_ASSESSMENT
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.contracts.session import ReaderStatement

# No tools reach either judgment; these bound their own structured-output repair
# attempts. A model that answers with calls to tools it was never given would
# otherwise keep earning fresh retry prompts.
BOOK_REQUEST_REQUEST_LIMIT = BOOK_REQUEST.output_retries + 1
EVIDENCE_ASSESSMENT_REQUEST_LIMIT = EVIDENCE_ASSESSMENT.output_retries + 1


class StrengthJudge(Protocol):
    async def __call__(
        self,
        query: str,
        evidence: tuple[EvidenceRecord, ...],
        /,
        *,
        max_evidence_records: int,
    ) -> EvidenceStrengthDecision: ...


async def plan_book_request(
    reader_question: str,
    *,
    prior_reader_statements: tuple[ReaderStatement, ...] = (),
    search_target: Literal["book_evidence", "reading_progress"] = "book_evidence",
    agent: Agent[None, Any] | None = None,
) -> BookRequestPlan:
    """Identify the book needs before retrieval can influence their scope."""
    if agent is None:
        from src.linger.agents.librarian.agent import librarian_agent

        agent = librarian_agent

    request_input = LibrarianBookRequestInput(
        current_line=reader_question,
        prior_reader_statements=prior_reader_statements,
        search_target=search_target,
    )
    fingerprint = BOOK_REQUEST.fingerprint()
    planned = await run_agent_traced(
        agent,
        request_input.model_dump_json(),
        span_name="librarian.book_request",
        role="Librarian",
        stage="book_request",
        input_contract="LibrarianBookRequestInput.v2",
        output_contract="src.linger.agents.librarian.models.BookRequestPlan",
        prompt_template_id=fingerprint.template_id,
        prompt_digest=fingerprint.digest,
        failure_code="book_request_model_failed",
        usage_limits=UsageLimits(request_limit=BOOK_REQUEST_REQUEST_LIMIT),
        **BOOK_REQUEST.run_options(),
    )
    plan = planned.output
    if book_request_span_errors(plan, request_input):
        raise ValueError("book request contains an invented or empty reader span")
    return plan


async def assess_book_evidence(
    plan: BookRequestPlan,
    evidence: tuple[EvidenceRecord, ...],
    *,
    original_request: LibrarianBookRequestInput,
    max_evidence_records: int = 5,
    agent: Agent[None, Any] | None = None,
) -> EvidenceStrengthDecision:
    """Assess planned and originally requested needs against scoped evidence."""
    if agent is None:
        from src.linger.agents.librarian.agent import librarian_agent

        agent = librarian_agent
    task = LibrarianEvidenceStrengthInput(
        original_request=original_request,
        request=plan, evidence=evidence,
        max_evidence_records=max_evidence_records,
    )
    result = await run_agent_traced(
        agent,
        task.model_dump_json(),
        span_name="librarian.evidence_strength",
        role="Librarian",
        stage="evidence_strength",
        input_contract="LibrarianEvidenceStrengthInput.v7",
        output_contract=(
            "src.linger.agents.librarian.models.BookEvidenceAssessment"
        ),
        prompt_template_id=PROMPT_FINGERPRINT.template_id,
        prompt_digest=PROMPT_FINGERPRINT.digest,
        failure_code="evidence_strength_model_failed",
        usage_limits=UsageLimits(request_limit=EVIDENCE_ASSESSMENT_REQUEST_LIMIT),
        **EVIDENCE_ASSESSMENT.run_options(),
    )
    assessment: BookEvidenceAssessment = result.output
    additions = BookRequestPlan(parts=assessment.additional_parts)
    if book_request_span_errors(additions, original_request):
        raise ValueError("additional book needs contain an invented reader span")
    supported_parts = {item.part_index for item in assessment.support}
    requested_parts = set(range(len(plan.parts) + len(assessment.additional_parts)))
    if not supported_parts.issubset(requested_parts):
        raise ValueError("evidence assessment introduced an unknown requested part")
    if assessment.evidence_strength == "sufficient" and supported_parts != requested_parts:
        raise ValueError("sufficient evidence must support every requested part")
    decision = EvidenceStrengthDecision.model_validate(
        assessment.model_dump(exclude={"support", "additional_parts"})
    )

    available_ids = {record.evidence_id for record in evidence}
    selected_ids = set(decision.relevant_evidence_ids)
    if not selected_ids.issubset(available_ids):
        raise ValueError("evidence-strength judge returned an unknown evidence ID")
    if len(decision.relevant_evidence_ids) != len(selected_ids) or len(selected_ids) > max_evidence_records:
        raise ValueError("evidence-strength judge exceeded the unique evidence selection budget")
    return decision


async def judge_evidence_strength(
    query: str,
    evidence: tuple[EvidenceRecord, ...],
    *,
    agent: Agent[None, Any] | None = None,
    max_evidence_records: int = 5,
    reader_question: str | None = None,
    prior_reader_statements: tuple[ReaderStatement, ...] = (),
) -> EvidenceStrengthDecision:
    """Plan and assess an already fixed set, including exact passage grants."""
    try:
        plan = await plan_book_request(
            reader_question if reader_question is not None else query,
            prior_reader_statements=prior_reader_statements, agent=agent,
        )
    except Exception:
        logfire.warning("librarian.book_request_fallback", reason="planning_unavailable")
        plan = BookRequestPlan(parts=())
    return await assess_book_evidence(
        plan, evidence, max_evidence_records=max_evidence_records, agent=agent,
        original_request=LibrarianBookRequestInput(
            current_line=reader_question if reader_question is not None else query,
            prior_reader_statements=prior_reader_statements,
        ),
    )
