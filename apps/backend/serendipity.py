"""Pure, evidence-backed connection discovery."""

import re

from .contracts import ConnectionBrief, ConnectionDecline, ConnectionProposal, ConnectionResult, EvidenceBundle


ALICE_TERMS = {"identity", "who", "myself", "self", "change", "growing", "caterpillar", "unsettled", "rule", "authority", "fair", "power", "absurd"}
ALICE_WORK_ID = "pg11"


def insufficient_evidence() -> ConnectionDecline:
    return ConnectionDecline(
        reason="insufficient_evidence",
        safe_next_step="There is not enough spoiler-safe evidence yet; try again after another chapter or describe the moment that stayed with you.",
    )


def discover(brief: ConnectionBrief, evidence: EvidenceBundle) -> ConnectionResult:
    """Return a proposal or decline from an already-authorised evidence bundle.

    This function has no tools, storage, network access, or agent side effects.
    Librarian owns retrieval; orchestration owns the decision to call us.
    """
    if brief.book_id != ALICE_WORK_ID or brief.chapter_max is None:
        return ConnectionDecline(
            reason="unsupported_cue",
            safe_next_step="This book has no registered evidence corpus yet, so Linger can reflect without proposing sourced connections.",
        )

    words = set(re.findall(r"[a-z]+", brief.cue.lower()))
    if not words & ALICE_TERMS:
        return ConnectionDecline(reason="unsupported_cue", safe_next_step="Name a feeling, question, or recurring idea from the scene.")

    change_evidence = next((item for item in evidence.items if item.chapter == 4), None)
    identity_evidence = next((item for item in evidence.items if item.chapter == 5), None)
    if change_evidence is None or identity_evidence is None:
        return insufficient_evidence()

    support = [change_evidence.evidence_id, identity_evidence.evidence_id]
    claim = "Alice's bodily changes sit beside the Caterpillar's question about who she is, linking identity to conditions that refuse to stay fixed."
    interpretation = "The connection is tentative: repeated physical change complicates Alice's attempt to explain herself."
    follow_up = "Does that scene feel unsettling, liberating, or a little of both?"

    return ConnectionProposal(
        tentative_claim=claim,
        evidence_ids=support,
        interpretation=interpretation,
        uncertainty="medium",
        suggested_follow_up=follow_up,
    )
