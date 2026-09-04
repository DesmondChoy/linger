"""Application-owned derivation of automatic-capture flags from a review.

The Memory & Policy Service enforces automatic-capture policy, but two of its
gates read flags that must originate from Provenance rather than from the
caller. This module is the only place those flags are set, so no caller can
authorise its own capture (specification sections 4.1 and 4.2.2).

Blank nominations fail binding. Substantive text retains its exact whitespace
so the reviewed source span and stored text remain identical.
"""

from __future__ import annotations

from src.linger.agents.muse.models import MemoryCandidate, MemoryNomination
from src.linger.agents.provenance.models import ProvenanceReview
from src.linger.services.memory import AutomaticMemoryCandidate


class CaptureBindingError(ValueError):
    """Raised when review and source text do not identify one exact candidate."""


def candidate_from_review(
    review: ProvenanceReview,
    *,
    nomination: MemoryNomination,
    source_text: str,
    source_event_id: str,
    available_evidence_ids: frozenset[str] = frozenset(),
) -> AutomaticMemoryCandidate | None:
    """Bind Provenance's decision to Muse's exact source-backed nomination."""
    if not isinstance(nomination, MemoryCandidate):
        if review.capture_decision != "no_candidate":
            raise CaptureBindingError("review decision does not match no nomination")
        return None
    if review.capture_decision == "no_candidate":
        raise CaptureBindingError("review ignored an existing nomination")
    if not nomination.text.strip():
        raise CaptureBindingError("nomination must not be blank")
    if source_text[nomination.start_codepoint : nomination.end_codepoint] != nomination.text:
        raise CaptureBindingError("nomination is not an exact source-text slice")
    if not set(nomination.evidence_ids).issubset(available_evidence_ids):
        raise CaptureBindingError("nomination cites unresolved evidence")
    return AutomaticMemoryCandidate(
        text=nomination.text,
        source_event_id=source_event_id,
        review_allows_capture=review.capture_decision == "allow_capture",
        contains_sensitive_content=review.contains_sensitive_content,
        evidence_ids=nomination.evidence_ids,
    )


def vetoed_candidate(
    *,
    nomination: MemoryCandidate,
    source_text: str,
    source_event_id: str,
) -> AutomaticMemoryCandidate:
    """Build the fail-closed candidate used when no review verdict exists.

    A review that never completed cannot authorise capture, so an unreviewed
    candidate is refused exactly as an explicit veto is.
    """
    if not nomination.text.strip():
        raise CaptureBindingError("nomination must not be blank")
    if source_text[nomination.start_codepoint : nomination.end_codepoint] != nomination.text:
        raise CaptureBindingError("nomination is not an exact source-text slice")
    return AutomaticMemoryCandidate(
        text=nomination.text,
        source_event_id=source_event_id,
        review_allows_capture=False,
        contains_sensitive_content=False,
        evidence_ids=nomination.evidence_ids,
    )
