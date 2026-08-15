"""Pure, evidence-backed connection discovery."""

import re

import logfire

from .contracts import ConnectionBrief, ConnectionDecline, ConnectionProposal, ConnectionResult, EvidenceBundle


ALICE_TERMS = {"identity", "who", "myself", "self", "change", "growing", "caterpillar", "unsettled", "rule", "authority", "fair", "power", "absurd"}
ANIMAL_FARM_TERMS = {"power", "rule", "rules", "equal", "equality", "revolution", "control", "propaganda", "leadership", "pigs", "milk", "apples"}
ALICE_BOOK_IDS = {
    "alice-s-adventures-in-wonderland",
    "alice-adventures-in-wonderland",
    "alice-wonderland",
}


def insufficient_evidence() -> ConnectionDecline:
    return ConnectionDecline(
        reason="insufficient_evidence",
        safe_next_step="There is not enough spoiler-safe evidence yet; try again after another chapter or describe the moment that stayed with you.",
    )


# `extract_args=False` is required, not stylistic: the arguments carry the
# reader's cue and raw book excerpts, which §8.1 bars from telemetry. The
# caller's span in `connection.py` records the safe projections instead.
@logfire.instrument("serendipity.discover", extract_args=False, record_return=False)
def discover(brief: ConnectionBrief, evidence: EvidenceBundle) -> ConnectionResult:
    """Return a proposal or decline from an already-authorised evidence bundle.

    This function has no tools, storage, network access, or agent side effects.
    Librarian owns retrieval; orchestration owns the decision to call us.
    """
    if brief.book_id not in ALICE_BOOK_IDS | {"animal-farm"} or brief.chapter_max is None:
        return ConnectionDecline(
            reason="unsupported_cue",
            safe_next_step="This book has no registered evidence corpus yet, so Linger can reflect without proposing sourced connections.",
        )

    words = set(re.findall(r"[a-z]+", brief.cue.lower()))
    evidence_ids = {item.evidence_id for item in evidence.items}
    source_titles = {item.source_title for item in evidence.items if item.source_kind == "book_corpus"}
    cross_book = len(source_titles) > 1
    if brief.book_id == "animal-farm":
        if not words & ANIMAL_FARM_TERMS:
            return ConnectionDecline(reason="unsupported_cue", safe_next_step="Name a question about power, equality, rules, or leadership.")
        if cross_book:
            support = ["animal-ch2-equality", "alice-ch3-rules"]
            claim = "Animal Farm and Wonderland both state universal-sounding rules about fairness, inviting a comparison of how those rules operate."
            interpretation = "This is a tentative cross-book resonance, not a claim that the books mean the same thing."
            follow_up = "Does the comparison make the animals' rules feel clearer, or stranger?"
        else:
            support = ["animal-ch2-equality", "animal-ch3-milk"]
            claim = "Animal Farm places its promise that all animals are equal beside the decision to reserve milk and apples for the pigs."
            interpretation = "The connection is tentative: the contrast raises a question about who benefits when a shared rule is put into practice."
            follow_up = "Which change feels most important to you: the rules, the resources, or who gets to explain them?"
    else:
        if not words & ALICE_TERMS:
            return ConnectionDecline(reason="unsupported_cue", safe_next_step="Name a feeling, question, or recurring idea from the scene.")
        if cross_book:
            support = ["alice-ch3-rules", "animal-ch2-equality"]
            claim = "Wonderland and Animal Farm both state universal-sounding rules about fairness, inviting a comparison of how those rules operate."
            interpretation = "This is a tentative cross-book resonance, not a claim that the books mean the same thing."
            follow_up = "Does the comparison make Wonderland's rules feel playful, threatening, or both?"
        else:
            identity_evidence = next(
                (item for item in ("alice-ch5-identity", "alice-ch5-reason") if item in evidence_ids),
                "alice-ch5-identity",
            )
            support = ["alice-ch4-change", identity_evidence]
            claim = "Alice's bodily changes sit beside the Caterpillar's question about who she is, linking identity to conditions that refuse to stay fixed."
            interpretation = "The connection is tentative: repeated physical change complicates Alice's attempt to explain herself."
            follow_up = "Does that scene feel unsettling, liberating, or a little of both?"

    if not set(support).issubset(evidence_ids):
        return insufficient_evidence()
    return ConnectionProposal(
        tentative_claim=claim,
        evidence_ids=support,
        interpretation=interpretation,
        uncertainty="medium",
        suggested_follow_up=follow_up,
    )
