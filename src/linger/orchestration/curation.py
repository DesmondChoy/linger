"""Application-owned reviewed curation workflow and deterministic hand-off."""

import json
from typing import Literal

from pydantic import ValidationError
from pydantic_ai import Agent

from apps.backend.telemetry import run_agent_traced
from src.linger.agents.contracts import StrictModel
from src.linger.agents.provenance.curation import curation_provenance_agent
from src.linger.agents.provenance.curation_models import (
    CurationProvenanceReview,
    CurationReviewInput,
    CurationSourceEvidence,
)
from src.linger.agents.provenance.curation_prompt import (
    PROMPT_FINGERPRINT as CURATION_REVIEW_PROMPT_FINGERPRINT,
)
from src.linger.agents.sculptor.agent import sculptor_agent
from src.linger.agents.sculptor.models import (
    AccountScopedMemories,
    CuratableMemory,
    CurationProposal,
    NoCurationProposal,
    SCULPTOR_RESPONSE_ADAPTER,
    SculptorResponse,
)
from src.linger.agents.sculptor.prompt import PROMPT_FINGERPRINT
from src.linger.contracts.curation import (
    ApprovedCuration,
    CurationApplyResult,
    CurationPlan,
    CurationSourceSnapshot,
)
from src.linger.services.memory import (
    AccountContext,
    MemoryPolicyService,
    MemoryRecord,
    memory_record_sha256,
)


class InvalidCurationProposal(ValueError):
    """Raised when a proposal escapes its typed, account-scoped input."""


class InvalidCurationReview(ValueError):
    """Raised when Provenance does not review the exact proposed curation."""


class CurationLoopResult(StrictModel):
    """One complete, inspectable curation attempt."""

    status: Literal[
        "no_change",
        "provenance_revise",
        "provenance_reject",
        "applied",
    ]
    sculptor_response: SculptorResponse
    proposal_digest: str | None = None
    provenance_review: CurationProvenanceReview | None = None
    application: CurationApplyResult | None = None
    source_hashes_before: tuple[CurationSourceSnapshot, ...]
    source_hashes_after: tuple[CurationSourceSnapshot, ...]
    source_immutable: Literal[True] = True


def _model_input(batch: AccountScopedMemories) -> str:
    payload = {
        "memories": [memory.model_dump(mode="json") for memory in batch.memories]
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


async def propose_curation(
    batch: AccountScopedMemories,
    *,
    agent: Agent[None, SculptorResponse] = sculptor_agent,
) -> SculptorResponse:
    """Return a validated proposal without exposing account or storage metadata."""
    result = await run_agent_traced(
        agent,
        _model_input(batch),
        span_name="sculptor.curation",
        role="Sculptor",
        stage="curation",
        input_contract="src.linger.agents.sculptor.models.AccountScopedMemories",
        output_contract="src.linger.agents.sculptor.models.SculptorResponse",
        prompt_template_id=PROMPT_FINGERPRINT.template_id,
        prompt_version=PROMPT_FINGERPRINT.version,
        prompt_digest=PROMPT_FINGERPRINT.digest,
        failure_code="sculptor_model_failed",
        retryable=False,
    )
    try:
        response = SCULPTOR_RESPONSE_ADAPTER.validate_python(result.output)
    except ValidationError:
        raise InvalidCurationProposal("Sculptor returned malformed output") from None

    if isinstance(response, CurationProposal):
        input_ids = {memory.memory_id for memory in batch.memories}
        unknown_ids = set(response.action.source_memory_ids) - input_ids
        if unknown_ids:
            raise InvalidCurationProposal(
                f"Sculptor referenced unknown memories: {sorted(unknown_ids)}"
            )
    return response


async def review_curation(
    review_input: CurationReviewInput,
    *,
    agent: Agent[None, CurationProvenanceReview] = curation_provenance_agent,
) -> CurationProvenanceReview:
    """Obtain a typed no-tool verdict bound to one immutable proposal."""

    result = await run_agent_traced(
        agent,
        review_input.model_dump_json(),
        span_name="provenance.curation_review",
        role="Provenance",
        stage="curation_review",
        input_contract=(
            "src.linger.agents.provenance.curation_models.CurationReviewInput"
        ),
        output_contract=(
            "src.linger.agents.provenance.curation_models.CurationProvenanceReview"
        ),
        prompt_template_id=CURATION_REVIEW_PROMPT_FINGERPRINT.template_id,
        prompt_version=CURATION_REVIEW_PROMPT_FINGERPRINT.version,
        prompt_digest=CURATION_REVIEW_PROMPT_FINGERPRINT.digest,
        failure_code="curation_provenance_model_failed",
        retryable=False,
    )
    try:
        review = CurationProvenanceReview.model_validate(result.output)
        review_input.validate_review(review)
    except (ValidationError, ValueError):
        raise InvalidCurationReview(
            "Provenance returned an invalid or unbound curation review"
        ) from None
    return review


def prepare_curation_plan(
    records: tuple[MemoryRecord, ...],
    proposal: CurationProposal,
    *,
    base_state_sha256: str,
) -> CurationPlan:
    """Bind a proposal to its trusted account and immutable source records."""

    if not records:
        raise InvalidCurationProposal("curation proposal has no trusted sources")
    account_keys = {record.account_key for record in records}
    if len(account_keys) != 1:
        raise InvalidCurationProposal("curation sources cross account scope")
    by_id = {record.memory_id: record for record in records}
    try:
        source_records = tuple(
            by_id[memory_id] for memory_id in proposal.action.source_memory_ids
        )
    except KeyError:
        raise InvalidCurationProposal(
            "curation proposal references an unknown trusted source"
        ) from None
    return CurationPlan(
        account_key=next(iter(account_keys)),
        base_state_sha256=base_state_sha256,
        proposal=proposal,
        source_snapshots=tuple(
            CurationSourceSnapshot(
                memory_id=record.memory_id,
                record_sha256=memory_record_sha256(record),
            )
            for record in source_records
        ),
    )


def curation_review_input(
    plan: CurationPlan,
    records: tuple[MemoryRecord, ...],
) -> CurationReviewInput:
    """Expose only proposal sources and their text to Provenance."""

    by_id = {record.memory_id: record for record in records}
    snapshots = {item.memory_id: item for item in plan.source_snapshots}
    return CurationReviewInput(
        proposal_digest=plan.digest,
        proposal=plan.proposal,
        sources=tuple(
            CurationSourceEvidence(
                memory_id=memory_id,
                text=by_id[memory_id].text,
                record_sha256=snapshots[memory_id].record_sha256,
            )
            for memory_id in plan.proposal.action.source_memory_ids
        ),
    )


async def run_curation_loop(
    context: AccountContext,
    memory_ids: tuple[str, ...],
    *,
    service: MemoryPolicyService,
    sculptor: Agent[None, SculptorResponse] = sculptor_agent,
    provenance: Agent[None, CurationProvenanceReview] = curation_provenance_agent,
) -> CurationLoopResult:
    """Select, propose, review, validate, apply, verify, and expose curation."""

    records = service.select_for_curation(context, memory_ids)
    before = _record_snapshots(records)
    batch = AccountScopedMemories(
        account_scope=records[0].account_key,
        memories=tuple(
            CuratableMemory(memory_id=record.memory_id, text=record.text)
            for record in records
        ),
    )
    response = await propose_curation(batch, agent=sculptor)
    if isinstance(response, NoCurationProposal):
        after = _record_snapshots(service.select_for_curation(context, memory_ids))
        _require_immutable_sources(before, after)
        return CurationLoopResult(
            status="no_change",
            sculptor_response=response,
            source_hashes_before=before,
            source_hashes_after=after,
        )

    plan = prepare_curation_plan(
        records,
        response,
        base_state_sha256=service.curation_state_sha256(context),
    )
    review_input = curation_review_input(plan, records)
    review = await review_curation(review_input, agent=provenance)
    after_review = _record_snapshots(service.select_for_curation(context, memory_ids))
    _require_immutable_sources(before, after_review)
    if review.decision != "allow":
        return CurationLoopResult(
            status=(
                "provenance_revise"
                if review.decision == "revise"
                else "provenance_reject"
            ),
            sculptor_response=response,
            proposal_digest=plan.digest,
            provenance_review=review,
            source_hashes_before=before,
            source_hashes_after=after_review,
        )

    approved = ApprovedCuration(plan=plan, review=review)
    application = service.apply_curation(context, approved)
    after = _record_snapshots(service.select_for_curation(context, memory_ids))
    _require_immutable_sources(before, after)
    return CurationLoopResult(
        status="applied",
        sculptor_response=response,
        proposal_digest=plan.digest,
        provenance_review=review,
        application=application,
        source_hashes_before=before,
        source_hashes_after=after,
    )


def _record_snapshots(
    records: tuple[MemoryRecord, ...],
) -> tuple[CurationSourceSnapshot, ...]:
    return tuple(
        CurationSourceSnapshot(
            memory_id=record.memory_id,
            record_sha256=memory_record_sha256(record),
        )
        for record in records
    )


def _require_immutable_sources(
    before: tuple[CurationSourceSnapshot, ...],
    after: tuple[CurationSourceSnapshot, ...],
) -> None:
    if before != after:
        raise RuntimeError("curation agents changed immutable source records")
