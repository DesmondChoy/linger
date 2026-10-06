"""Replay the three captured, no-tool tasks through current role boundaries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic_ai import UsageLimits
from pydantic_ai.messages import ModelMessagesTypeAdapter

from apps.backend.telemetry import run_agent_traced
from src.linger.agents.contracts import PromptFingerprint
from src.linger.agents.librarian.models import (
    BookEvidenceAssessment,
    LibrarianBookRequestInput,
    LibrarianEvidenceStrengthInput,
    book_request_span_errors,
    evidence_assessment_errors,
)
from src.linger.agents.librarian.skills import BOOK_REQUEST, EVIDENCE_ASSESSMENT
from src.linger.agents.librarian.prompt import PROMPT_FINGERPRINT as EVIDENCE_FINGERPRINT
from src.linger.agents.provenance.models import ProvenanceInput
from src.linger.agents.provenance.review_context import reset_review_input, set_review_input
from src.linger.agents.provenance.skills import CANDIDATE_REVIEW
from src.linger.agents.provenance.prompt import PROMPT_FINGERPRINT as REVIEW_FINGERPRINT
from src.linger.agents.skills import RuntimeSkill

from .transcript import AgentExchange

SUPPORTED_STAGES = frozenset({
    ("Librarian", "book_request"),
    ("Librarian", "evidence_strength"),
    ("Provenance", "review"),
})


@dataclass(frozen=True)
class CapturedTask:
    exchange: AgentExchange
    skill: RuntimeSkill
    fingerprint: PromptFingerprint
    prompt: str
    agent: Any

    async def invoke(self) -> Any:
        # Reparse for every repetition: neither a role nor a validator can alter
        # the next repetition's context or stored conversation.
        task = self.skill.input_type.model_validate_json(self.prompt)
        history = ModelMessagesTypeAdapter.validate_python(list(self.exchange.message_history))
        token = set_review_input(task) if isinstance(task, ProvenanceInput) else None
        fingerprint = self.fingerprint
        try:
            result = await run_agent_traced(
                self.agent, self.prompt,
                span_name=f"captured_stage.{self.exchange.role.lower()}.{self.exchange.stage}",
                role=self.exchange.role, stage=self.exchange.stage,
                input_contract=f"{type(task).__module__}.{type(task).__name__}",
                output_contract=f"{self.skill.output_type.__module__}.{self.skill.output_type.__name__}",
                prompt_template_id=fingerprint.template_id,
                prompt_digest=fingerprint.digest,
                failure_code="captured_stage_model_failed",
                message_history=history,
                usage_limits=UsageLimits(request_limit=self.skill.output_retries + 1),
                **self.skill.run_options(),
            )
            _validate_application_result(task, result.output)
            return result.output
        finally:
            if token is not None:
                reset_review_input(token)


def prepare_captured_task(exchange: AgentExchange, *, agent: Any = None) -> CapturedTask:
    """Apply today's typed input and skill without sending adopted expectations."""
    key = (exchange.role, exchange.stage)
    if key not in SUPPORTED_STAGES:
        raise ValueError(f"Captured replay does not support {exchange.role}/{exchange.stage}")
    skill = {
        ("Librarian", "book_request"): BOOK_REQUEST,
        ("Librarian", "evidence_strength"): EVIDENCE_ASSESSMENT,
        ("Provenance", "review"): CANDIDATE_REVIEW,
    }[key]
    typed_input = skill.input_type.model_validate_json(exchange.input_prompt)
    ModelMessagesTypeAdapter.validate_python(list(exchange.message_history))
    if agent is None:
        if exchange.role == "Librarian":
            from src.linger.agents.librarian.agent import librarian_agent
            agent = librarian_agent
        else:
            from src.linger.agents.provenance.agent import provenance_agent
            agent = provenance_agent
    fingerprint = {
        ("Librarian", "book_request"): BOOK_REQUEST.fingerprint(),
        ("Librarian", "evidence_strength"): EVIDENCE_FINGERPRINT,
        ("Provenance", "review"): REVIEW_FINGERPRINT,
    }[key]
    return CapturedTask(exchange, skill, fingerprint, typed_input.model_dump_json(), agent)


def _validate_application_result(task: Any, output: Any) -> None:
    """Retain the post-call checks performed by the production entry points.

    Agent capabilities already apply in-run repair. These final domain checks
    match evidence_strength.plan_book_request/assess_book_evidence and _review;
    captured replay cannot call those entry points because they construct fresh
    inputs and omit captured message history.
    """
    if isinstance(task, ProvenanceInput):
        task.validate_review(output)
    elif isinstance(task, LibrarianBookRequestInput):
        if book_request_span_errors(output, task):
            raise ValueError("book request contains an invented or empty reader span")
    elif isinstance(task, LibrarianEvidenceStrengthInput):
        assessment = BookEvidenceAssessment.model_validate(
            output.model_dump(mode="json") if isinstance(output, BookEvidenceAssessment) else output,
        )
        errors = evidence_assessment_errors(assessment, task)
        if errors:
            raise ValueError(json.dumps({"error": "Invalid evidence assessment.", "errors": errors}, ensure_ascii=False))
