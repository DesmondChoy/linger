"""Preserve accepted claim coverage and supporting sources during revision."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.linger.agents.muse.models import MuseCandidate, RetainedSource

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


def retained_sources_for_revision(
    candidate: MuseCandidate, review: ProvenanceReview,
) -> tuple[RetainedSource, ...]:
    """Keep every source the review found contributing, unless a finding rejects the source itself."""
    if review.response_decision != "revise":
        return ()
    if any(finding.location.source_field.startswith("canonical_")
           for finding in review.response_findings):
        return ()
    uses = candidate.evidence_uses

    def key(index: int) -> tuple[str, str] | None:
        if index >= len(uses) or uses[index].source_kind == "session_line":
            return None
        return uses[index].source_kind, uses[index].evidence_id

    rejected = {key(index) for finding in review.response_findings
                if (index := _rejected_declaration(finding.location)) is not None}
    retained: dict[tuple[str, str], None] = {}
    for audit in review.claim_audit:
        for item in audit.source_contributions:
            source = key(item.declaration_index) if item.contributes else None
            if source is not None and source not in rejected:
                retained[source] = None
    return tuple(RetainedSource(source_kind=kind, evidence_id=evidence_id)
                 for kind, evidence_id in retained)


def _rejected_declaration(location) -> int | None:
    """A finding on a mapped claim or quotation disputes wording, not the source."""
    if location.source_field != "candidate.evidence_uses":
        return None
    parts = location.path.split("/")[1:]
    if not parts or not parts[0].isdigit():
        return None
    if len(parts) == 1 or parts[1] in {"evidence_id", "source_kind"}:
        return int(parts[0])
    return None


def retained_source_errors(
    candidate: MuseCandidate, retained_sources: tuple[RetainedSource, ...],
) -> list[dict[str, object]]:
    """Require each retained source to stay declared, without choosing its claim."""
    declared = {(use.source_kind, use.evidence_id) for use in candidate.evidence_uses
                if use.source_kind != "session_line"}
    return [{
        "path": "evidence_uses", "value": source.evidence_id,
        "source_kind": source.source_kind,
        "error": (
            "The first review found this source supports part of the reply, and no finding "
            "rejected the source itself, but the revision no longer declares it. A finding about "
            "wording asks for the wording to change, not for supporting evidence to be removed. "
            "Keep this source: rewrite the flagged claim so it states only what the source "
            "establishes, and map that claim to it. Do not add details the source does not state."
        ),
    } for source in retained_sources
        if (source.source_kind, source.evidence_id) not in declared]
