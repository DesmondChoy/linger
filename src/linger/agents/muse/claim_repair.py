"""Preserve coverage of unchanged, previously accepted claims during revision."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.linger.agents.muse.models import MuseCandidate

if TYPE_CHECKING:
    from src.linger.agents.provenance.models import ProvenanceReview


def _occurrences(text: str, fragment: str) -> list[tuple[int, int]]:
    intervals = []
    start = text.find(fragment)
    while start >= 0:
        intervals.append((start, start + len(fragment)))
        start = text.find(fragment, start + 1)
    return intervals


def accepted_claims_for_revision(
    candidate: MuseCandidate, review: ProvenanceReview,
) -> tuple[str, ...]:
    """Retain no obligation for rejected mappings or findings that could affect them."""
    from src.linger.agents.provenance.models import build_claim_support_groups

    if review.response_decision != "revise":
        return ()
    audits = {item.group_index: item for item in review.claim_audit}
    accepted = []
    for group in build_claim_support_groups(candidate.evidence_uses, candidate.reply):
        audit = audits.get(group.group_index)
        members = {(item.declaration_index, item.claim_index) for item in group.declarations}
        direct_members = {(item.declaration_index, item.claim_index)
                          for item in group.declarations if item.direct}
        if (
            audit is None or not audit.supported
            or len(audit.source_contributions) != len(members)
            or {(item.declaration_index, item.claim_index) for item in audit.source_contributions} != members
            or not all(item.contributes for item in audit.source_contributions
                       if (item.declaration_index, item.claim_index) in direct_members)
        ):
            continue
        if any(_finding_affects_claim(finding.location, candidate.reply, group.claim, members)
               for finding in review.response_findings):
            continue
        accepted.append(group.claim)
    return tuple(accepted)


def _finding_affects_claim(location, reply: str, claim: str, members: set[tuple[int, int]]) -> bool:
    if location.source_field == "candidate.response":
        if location.kind != "text_span" or location.path:
            return True
        found = _occurrences(reply, location.quote)
        if not found:
            return True
        return any(a < d and c < b for a, b in found for c, d in _occurrences(reply, claim))
    if location.source_field != "candidate.evidence_uses":
        return True
    parts = location.path.split("/")[1:]
    if not parts or not parts[0].isdigit():
        return True
    declaration = int(parts[0])
    if len(parts) >= 3 and parts[1] == "supported_claims" and parts[2].isdigit():
        return (declaration, int(parts[2])) in members
    return any(index == declaration for index, _ in members)


def retained_claim_errors(
    candidate: MuseCandidate, previously_accepted_claims: tuple[str, ...],
) -> list[dict[str, object]]:
    """Require current mapping coverage, without assigning sources or approving support."""
    covered = bytearray(len(candidate.reply))
    for use in candidate.evidence_uses:
        for claim in use.supported_claims:
            for start, end in _occurrences(candidate.reply, claim):
                covered[start:end] = b"\1" * (end - start)
    errors = []
    for claim in previously_accepted_claims:
        for start, end in _occurrences(candidate.reply, claim):
            if any(not covered[index] and not candidate.reply[index].isspace()
                   for index in range(start, end)):
                errors.append({
                    "path": "evidence_uses", "value": claim,
                    "response_start": start, "response_end": end,
                    "error": (
                        "This unchanged claim had accepted source mappings in the first review, "
                        "but the revision dropped part or all of its mapping. Map its retained "
                        "text to current authorized supporting sources, or remove/rewrite it. "
                        "Split or expanded exact claim spans are allowed. Do not copy a source "
                        "assignment blindly: the next review independently checks support."
                    ),
                })
    return errors
