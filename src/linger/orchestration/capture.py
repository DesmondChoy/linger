"""Application-owned derivation of automatic-capture flags from a review.

The Memory & Policy Service enforces automatic-capture policy, but two of its
gates read flags that must originate from Provenance rather than from the
caller. This module is the only place those flags are set, so no caller can
authorise its own capture (specification sections 4.1 and 4.2.2).
"""

from __future__ import annotations

from src.linger.agents.provenance.models import ProvenanceReview
from src.linger.services.memory import AutomaticMemoryCandidate


def candidate_from_review(
    review: ProvenanceReview,
    *,
    text: str,
    source_event_id: str,
    evidence_ids: tuple[str, ...] = (),
) -> AutomaticMemoryCandidate:
    """Build a candidate whose review flags are owned by Provenance."""
    return AutomaticMemoryCandidate(
        text=text,
        source_event_id=source_event_id,
        review_allows_capture=review.capture_decision == "allow_capture",
        contains_sensitive_content=review.contains_sensitive_content,
        evidence_ids=evidence_ids,
    )


def vetoed_candidate(
    *,
    text: str,
    source_event_id: str,
    evidence_ids: tuple[str, ...] = (),
) -> AutomaticMemoryCandidate:
    """Build the fail-closed candidate used when no review verdict exists.

    A review that never completed cannot authorise capture, so an unreviewed
    candidate is refused exactly as an explicit veto is.
    """
    return AutomaticMemoryCandidate(
        text=text,
        source_event_id=source_event_id,
        review_allows_capture=False,
        contains_sensitive_content=False,
        evidence_ids=evidence_ids,
    )
