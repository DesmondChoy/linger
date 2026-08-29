"""Application-owned contracts for reviewed deterministic curation."""

from __future__ import annotations

import hashlib
import json
from typing import Literal, Self

from pydantic import Field, model_validator

from src.linger.agents.contracts import StrictModel
from src.linger.agents.provenance.curation_models import (
    CurationProvenanceReview,
    review_digest,
)
from src.linger.agents.sculptor.models import CurationProposal


def canonical_digest(payload: object) -> str:
    """Hash one JSON-compatible value with stable key and whitespace rules."""

    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


class CurationSourceSnapshot(StrictModel):
    """The immutable record identity against which a proposal was made."""

    memory_id: str = Field(min_length=1)
    record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CurationPlan(StrictModel):
    """A complete proposal bound to account scope and source snapshots."""

    account_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    base_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal: CurationProposal
    source_snapshots: tuple[CurationSourceSnapshot, ...] = Field(
        min_length=1,
        max_length=12,
    )

    @model_validator(mode="after")
    def require_exact_unique_sources(self) -> Self:
        source_ids = tuple(item.memory_id for item in self.source_snapshots)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("curation plan source IDs must be unique")
        if set(source_ids) != set(self.proposal.action.source_memory_ids):
            raise ValueError("curation plan snapshots must exactly match the proposal")
        return self

    @property
    def digest(self) -> str:
        """Return the identity reviewed and later revalidated before writing."""

        return canonical_digest(self.model_dump(mode="json"))


class ApprovedCuration(StrictModel):
    """The only reviewed command accepted by deterministic write policy."""

    plan: CurationPlan
    review: CurationProvenanceReview

    @model_validator(mode="after")
    def require_bound_allow(self) -> Self:
        if self.review.decision != "allow":
            raise ValueError("only an allowed curation review can be applied")
        if self.review.proposal_digest != self.plan.digest:
            raise ValueError("curation approval is bound to a different proposal")
        return self

    @property
    def review_digest(self) -> str:
        return review_digest(self.review)


class AppliedCuration(StrictModel):
    """One immutable account-scoped curation audit event."""

    schema_version: Literal["1"] = "1"
    event_id: str = Field(pattern=r"^cur_[0-9a-f]{64}$")
    account_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    base_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_review_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_review: CurationProvenanceReview
    proposal: CurationProposal
    source_snapshots: tuple[CurationSourceSnapshot, ...] = Field(
        min_length=1,
        max_length=12,
    )
    applied_at: str = Field(min_length=1)

    @model_validator(mode="after")
    def verify_bound_audit_payload(self) -> Self:
        plan = CurationPlan(
            account_key=self.account_key,
            base_state_sha256=self.base_state_sha256,
            proposal=self.proposal,
            source_snapshots=self.source_snapshots,
        )
        if plan.digest != self.proposal_digest:
            raise ValueError("curation audit proposal digest does not match its payload")
        if self.event_id != f"cur_{self.proposal_digest}":
            raise ValueError("curation audit event ID does not match its proposal")
        if self.provenance_review.decision != "allow":
            raise ValueError("curation audit must contain an allowed review")
        if self.provenance_review.proposal_digest != self.proposal_digest:
            raise ValueError("curation audit review is bound to another proposal")
        if review_digest(self.provenance_review) != self.provenance_review_digest:
            raise ValueError("curation audit review digest does not match its payload")
        return self


class CurationVerification(StrictModel):
    """Deterministic audit verification against current immutable sources."""

    event_id: str
    verified: bool
    failures: tuple[str, ...] = ()


class CurationApplyResult(StrictModel):
    """The persisted event and immediate verification result."""

    event: AppliedCuration
    created: bool
    verification: CurationVerification


class CuratedMemory(StrictModel):
    """One retrieval item materialized from originals and curation events."""

    memory_id: str = Field(min_length=1)
    kind: Literal["original", "derived_summary", "topic_group"]
    text: str = Field(min_length=1)
    source_memory_ids: tuple[str, ...] = Field(min_length=1, max_length=12)
    evidence_ids: tuple[str, ...] = ()
    duplicate_memory_ids: tuple[str, ...] = ()
    topic_labels: tuple[str, ...] = ()
    created_at: str = Field(min_length=1)
