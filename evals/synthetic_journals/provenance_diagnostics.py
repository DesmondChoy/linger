"""Evaluation-only diagnostics over recorded Provenance candidate reviews."""

from __future__ import annotations

import json
from collections.abc import Sequence

from src.linger.agents.contracts import StrictModel
from src.linger.agents.provenance.models import ProvenanceInput, ProvenanceReview, RiskFinding

from .transcript import AgentExchange


class LateProvenanceFinding(StrictModel):
    """A revision-check objection to draft text the first review already accepted."""

    code: str
    text: str


def _flagged_text(task: ProvenanceInput, finding: RiskFinding) -> str | None:
    location = finding.location
    if location.source_field == "candidate.response" and location.path == "":
        return getattr(location, "quote", None)
    if location.source_field == "candidate.evidence_uses":
        parts = location.path.strip("/").split("/")
        if len(parts) == 3 and parts[1] == "supported_claims" and parts[0].isdecimal() and parts[2].isdecimal():
            uses = task.candidate.evidence_uses
            declaration, claim = int(parts[0]), int(parts[2])
            if declaration < len(uses) and claim < len(uses[declaration].supported_claims):
                return uses[declaration].supported_claims[claim]
    return None


def _intervals(text: str, fragment: str) -> list[tuple[int, int]]:
    found, start = [], text.find(fragment)
    while start != -1:
        found.append((start, start + len(fragment)))
        start = text.find(fragment, start + 1)
    return found


def late_provenance_findings(exchanges: Sequence[AgentExchange]) -> tuple[LateProvenanceFinding, ...]:
    """Report revision findings on unchanged draft text that the first review left unflagged."""
    reviews = [
        exchange for exchange in exchanges
        if exchange.role == "Provenance" and exchange.stage == "review"
        and exchange.status == "success" and exchange.output is not None
    ]
    late: list[LateProvenanceFinding] = []
    for first, second in zip(reviews, reviews[1:]):
        first_task = ProvenanceInput.model_validate_json(first.input_prompt)
        second_task = ProvenanceInput.model_validate_json(second.input_prompt)
        if second_task.previous_response_review is None:
            continue
        draft = first_task.candidate.response
        first_review = ProvenanceReview.model_validate(
            first.output if isinstance(first.output, dict) else json.loads(first.output)
        )
        second_review = ProvenanceReview.model_validate(
            second.output if isinstance(second.output, dict) else json.loads(second.output)
        )
        flagged = [
            interval
            for finding in first_review.response_findings
            if (text := _flagged_text(first_task, finding))
            for interval in _intervals(draft, text)
        ]
        for finding in second_review.response_findings:
            text = _flagged_text(second_task, finding)
            if not text:
                continue
            unchanged = _intervals(draft, text)
            if unchanged and not any(
                start < flagged_end and end > flagged_start
                for start, end in unchanged
                for flagged_start, flagged_end in flagged
            ):
                late.append(LateProvenanceFinding(code=finding.code, text=text))
    return tuple(late)
