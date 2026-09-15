"""Application-owned dispatch and validation for evidence-strength judgment."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic_ai import Agent

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
    agent: Agent[None, Any] | None = None,
) -> BookRequestPlan:
    """Identify the book needs before retrieval can influence their scope."""
    if agent is None:
        from src.linger.agents.librarian.agent import librarian_agent

        agent = librarian_agent

    request_input = LibrarianBookRequestInput(
        current_line=reader_question,
        prior_reader_statements=prior_reader_statements,
    )
    fingerprint = BOOK_REQUEST.fingerprint()
    planned = await run_agent_traced(
        agent,
        request_input.model_dump_json(),
        span_name="librarian.book_request",
        role="Librarian",
        stage="book_request",
        input_contract="LibrarianBookRequestInput.v1",
        output_contract="src.linger.agents.librarian.models.BookRequestPlan",
        prompt_template_id=fingerprint.template_id,
        prompt_digest=fingerprint.digest,
        failure_code="book_request_model_failed",
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
    max_evidence_records: int = 5,
    agent: Agent[None, Any] | None = None,
) -> EvidenceStrengthDecision:
    """Assess records against the same immutable needs that drove retrieval."""
    if agent is None:
        from src.linger.agents.librarian.agent import librarian_agent

        agent = librarian_agent
    if not plan.parts:
        return EvidenceStrengthDecision(
            evidence_strength="none",
            strength_reason="No book question was identified in the supplied reader context.",
        )
    task = LibrarianEvidenceStrengthInput(
        request=plan, evidence=evidence,
        max_evidence_records=max_evidence_records,
    )
    result = await run_agent_traced(
        agent,
        task.model_dump_json(),
        span_name="librarian.evidence_strength",
        role="Librarian",
        stage="evidence_strength",
        input_contract="LibrarianEvidenceStrengthInput.v6",
        output_contract=(
            "src.linger.agents.librarian.models.BookEvidenceAssessment"
        ),
        prompt_template_id=PROMPT_FINGERPRINT.template_id,
        prompt_digest=PROMPT_FINGERPRINT.digest,
        failure_code="evidence_strength_model_failed",
        **EVIDENCE_ASSESSMENT.run_options(),
    )
    assessment: BookEvidenceAssessment = result.output
    supported_parts = {item.part_index for item in assessment.support}
    requested_parts = set(range(len(plan.parts)))
    if not supported_parts.issubset(requested_parts):
        raise ValueError("evidence assessment introduced an unknown requested part")
    if assessment.evidence_strength == "sufficient" and supported_parts != requested_parts:
        raise ValueError("sufficient evidence must support every requested part")
    decision = EvidenceStrengthDecision.model_validate(
        assessment.model_dump(exclude={"support"})
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
    plan = await plan_book_request(
        reader_question if reader_question is not None else query,
        prior_reader_statements=prior_reader_statements, agent=agent,
    )
    return await assess_book_evidence(
        plan, evidence, max_evidence_records=max_evidence_records, agent=agent,
    )
