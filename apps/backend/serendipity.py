"""Pure, evidence-backed connection discovery."""

from .contracts import ConnectionBrief, ConnectionDecline, ConnectionProposal, ConnectionResult, EvidenceBundle


ALICE_TERMS = {"identity", "who", "myself", "self", "change", "growing", "caterpillar", "unsettled", "rule", "authority", "fair", "power", "absurd"}
ANIMAL_FARM_TERMS = {"power", "rule", "rules", "equal", "equality", "revolution", "control", "propaganda", "leadership", "pigs", "milk", "apples"}


def discover(brief: ConnectionBrief, evidence: EvidenceBundle) -> ConnectionResult:
    """Return a proposal or decline from an already-authorised evidence bundle.

    This function has no tools, storage, network access, or agent side effects.
    Librarian owns retrieval; orchestration owns the decision to call us.
    """
    if not brief.book_id or brief.chapter_max is None:
            return ConnectionDecline(
                reason="unsupported_cue",
                safe_next_step="This book has no registered evidence corpus yet, so Linger can reflect without proposing sourced connections.",
            )

    words = set(brief.cue.lower().replace("?", " ").replace(",", " ").split())
    source_titles = {item.source_title for item in evidence.items if item.source_kind == "book_corpus"}
    cross_book = len(source_titles) > 1
    if brief.book_id == "animal-farm":
        if not words & ANIMAL_FARM_TERMS:
            return ConnectionDecline(reason="unsupported_cue", safe_next_step="Name a question about power, equality, rules, or leadership.")
        if cross_book:
            claim = "Animal Farm's promise of equality can be compared with Wonderland's unstable rules: both make readers notice the gap between a rule's wording and who gets to define it."
            interpretation = "This is a tentative cross-book resonance, not a claim that the books mean the same thing. Each uses rule-making to create a different kind of unease."
            follow_up = "Does the comparison make the animals' rules feel clearer, or stranger?"
        else:
            claim = "Animal Farm links its promises of equality to the pigs' growing control over shared resources and rules."
            interpretation = "The connection is tentative: the early ideals become meaningful because the animals must decide who is allowed to interpret them."
            follow_up = "Which change feels most important to you: the rules, the resources, or who gets to explain them?"
    else:
        if not words & ALICE_TERMS:
            return ConnectionDecline(reason="unsupported_cue", safe_next_step="Name a feeling, question, or recurring idea from the scene.")
        if cross_book:
            claim = "Alice's unstable rules can be compared with Animal Farm's early equality rules: both make readers notice the gap between a rule's wording and who gets to define it."
            interpretation = "This is a tentative cross-book resonance, not a claim that the books mean the same thing. Each uses rule-making to create a different kind of unease."
            follow_up = "Does the comparison make Wonderland's rules feel playful, threatening, or both?"
        else:
            claim = "Alice's uncertainty about identity is tied to repeated changes in her body and Wonderland's unstable rules."
            interpretation = "The connection is tentative: Wonderland asks Alice to define herself while its own rules refuse to stay stable."
            follow_up = "Does that scene feel unsettling, liberating, or a little of both?"

    if len(evidence.items) < 2:
        return ConnectionDecline(
                reason="insufficient_evidence",
                safe_next_step="There is not enough spoiler-safe evidence yet; try again after another chapter or describe the moment that stayed with you.",
            )
    return ConnectionProposal(
            tentative_claim=claim,
            evidence_ids=[item.evidence_id for item in evidence.items],
            interpretation=interpretation,
            uncertainty="medium",
            suggested_follow_up=follow_up,
    )
