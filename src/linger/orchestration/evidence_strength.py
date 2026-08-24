"""Application-owned dispatch and validation for evidence-strength judgment."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from apps.backend.telemetry import run_agent_traced
from src.linger.agents.librarian.models import EvidenceStrengthDecision
from src.linger.agents.librarian.prompt import PROMPT_FINGERPRINT
from src.linger.contracts.librarian import EvidenceRecord


StrengthJudge = Callable[
    [str, tuple[EvidenceRecord, ...]], Awaitable[EvidenceStrengthDecision]
]


async def judge_evidence_strength(
    query: str,
    evidence: tuple[EvidenceRecord, ...],
) -> EvidenceStrengthDecision:
    """Ask Librarian to judge answerability, then reject invented evidence IDs."""
    # Imported lazily so contract and boundary-only callers do not need model
    # credentials until an actual non-empty evidence set must be judged.
    from src.linger.agents.librarian.agent import librarian_strength_agent

    payload = json.dumps(
        {
            "query": query,
            "evidence": [record.model_dump(mode="json") for record in evidence],
        },
        ensure_ascii=False,
    )
    result = await run_agent_traced(
        librarian_strength_agent,
        payload,
        span_name="librarian.evidence_strength",
        role="Librarian",
        stage="evidence_strength",
        input_contract="LibrarianEvidenceStrengthInput.v1",
        output_contract=(
            "src.linger.agents.librarian.models.EvidenceStrengthDecision"
        ),
        prompt_template_id=PROMPT_FINGERPRINT.template_id,
        prompt_version=PROMPT_FINGERPRINT.version,
        prompt_digest=PROMPT_FINGERPRINT.digest,
        failure_code="evidence_strength_model_failed",
    )
    decision = result.output

    available_ids = {record.evidence_id for record in evidence}
    selected_ids = set(decision.relevant_evidence_ids)
    if not selected_ids.issubset(available_ids):
        raise ValueError("evidence-strength judge returned an unknown evidence ID")
    return decision
