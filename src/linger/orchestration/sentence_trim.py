"""Remove the sentences a revision's review names, with no model call.

The application's last step before it declines a revision. It deletes whole
sentences only and repairs nothing. It refuses wherever removal could change
what the remaining text says or leave a fragment: when in doubt the turn
declines as before. A trimmed reply is not approved by this step; Provenance
judges it in a further review and release validation still applies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from src.linger.agents.muse.claim_repair import (
    finding_intervals,
    label_units,
    occurrences,
    overlaps,
    sentence_spans,
)
from src.linger.agents.muse.models import MuseCandidate, limit_claim_texts, supported_claim_errors
from src.linger.agents.provenance.models import MAX_FINDINGS, ProvenanceReview, RiskCode, RiskFinding

# Findings that say reply text asserts something its declared sources do not
# establish, resolve, attribute or cite. Deleting the text removes the defect.
# Spoiler, emotional, persona, advice, scope and security findings are left out:
# they are safety outcomes, and what they object to may not be one sentence.
TRIMMABLE_CODES: frozenset[RiskCode] = frozenset(
    {
        RiskCode.UNSUPPORTED_CLAIM,
        RiskCode.UNRESOLVED_EVIDENCE,
        RiskCode.MISATTRIBUTION,
        RiskCode.UNCITED_WEB_CLAIM,
    }
)

TrimRefusal = Literal[
    "review_not_revise",
    "finding_code",
    "structured_reply",
    "unplaced_finding",
    "unsafe_boundary",
    "split_delimiters",
    "fragment_remainder",
    "dependent_remainder",
    "empty_reply",
    "no_mapped_claim",
    "invalid_candidate",
]

# List items, Markdown links or images, and numbered citations tie text
# together in ways sentence removal does not follow.
_STRUCTURE = re.compile(r"(?m)^[ \t]*(?:[-*+•]|\d+[.)])[ \t]|!?\[[^\]]*\]\([^)]*\)|\[\d+\]")
# A sentence end the splitter may have misread: an initial, a short
# abbreviation, an ellipsis, or a colon that leads into what follows.
_DOUBTFUL_END = re.compile(
    r"(?i)(?:(?:^|\s)[\"'“‘(\[*_]*(?:[^\W\d_]|mr|mrs|ms|dr|st|prof|jr|sr|vs|etc|cf|ch|no|vol|pp?|e\.g|i\.e)\."
    r"|\.\.\.|…|:)[\"'”’)\]*_]*$"
)
_WORD = re.compile(r"\w+")
# A sentence beside a removed one must stand alone. Under four words it is
# nearly always an answer, a lead-in or a tag on its neighbour ("No.", "Two
# reasons.", "What then?") rather than a complete statement.
_MIN_NEIGHBOUR_WORDS = 4
# Openings that lean on the sentence before: connectives, pointers into a
# list or pair, and third-person pronouns whose antecedent may have been the
# removed sentence. "also" anywhere in the opening four words counts too
# ("The Pigeon also").
_DEPENDENT_OPENING = re.compile(
    r"(?i)\W*(?:that|this|these|those|so|then|and|but|also|or|yet|thus|therefore|hence|however|instead"
    r"|otherwise|because|which|such|nor|both|nevertheless|nonetheless|there|here"
    r"|he|she|they|him|her|his|their|it"
    r"|as a result|for example|for instance|in contrast|by contrast"
    r"|the (?:first|second|other|latter|former))\b"
)
_DELIMITER = re.compile(r"\*\*|[“”‘’«»()\[\]\"`_*]")
_CLOSERS = {"”": "“", "’": "‘", "»": "«", ")": "(", "]": "["}


class TrimRefused(ValueError):
    """The review's findings cannot be safely cured by deleting sentences."""

    def __init__(self, reason: TrimRefusal) -> None:
        super().__init__(reason)
        self.reason: TrimRefusal = reason


@dataclass(frozen=True)
class SentenceTrim:
    """A candidate with whole sentences removed, the sentences that went, and why."""

    candidate: MuseCandidate
    # Reply text: for the next review and local inspection, never for telemetry.
    removed: tuple[str, ...]
    # Every finding that prompted the trim, each placed on the untrimmed reply.
    findings: tuple[RiskFinding, ...]


def _delimiter_pairs(text: str) -> list[tuple[int, int]] | None:
    """Matched quotation, bracket and emphasis marks, or None when any is unmatched."""
    pairs: list[tuple[int, int]] = []
    nested: list[tuple[str, int]] = []
    toggled: dict[str, int] = {}
    for match in _DELIMITER.finditer(text):
        mark, at = match.group(), match.start()
        inside_word = bool(_WORD.fullmatch(text[at - 1:at]) and _WORD.fullmatch(text[at + 1:at + 2]))
        if mark in "_*" and inside_word:
            continue
        if mark == "’" and (inside_word or not any(kind == "‘" for kind, _ in nested)):
            continue  # an apostrophe
        if mark in _CLOSERS:
            if not nested or nested[-1][0] != _CLOSERS[mark]:
                return None
            pairs.append((nested.pop()[1], at))
        elif mark in _CLOSERS.values():
            nested.append((mark, at))
        elif mark in toggled:
            pairs.append((toggled.pop(mark), at))
        else:
            toggled[mark] = at
    return None if nested or toggled else pairs


def trim_named_sentences(
    candidate: MuseCandidate,
    review: ProvenanceReview,
    earlier_findings: tuple[RiskFinding, ...] = (),
) -> SentenceTrim:
    """Delete every sentence a prompting finding names and the declarations that lay in them.

    The prompting findings are the review's response findings and each of
    `earlier_findings` (which `review.finding_resolutions` index) that the
    review left unresolved; an earlier finding counts only when its quoted
    text still stands in this reply. A declared claim, limit or exact quote
    is removed whole, with every sentence it touches. Kept sentences and
    declarations are unchanged, and the stronger of the breaks around a
    removed sentence joins its neighbours.
    """
    if review.response_decision != "revise":
        raise TrimRefused("review_not_revise")
    unresolved = [item.finding_index for item in review.finding_resolutions if item.status == "unresolved"]
    if any(index >= len(earlier_findings) for index in unresolved):
        raise TrimRefused("unplaced_finding")
    carried = tuple(earlier_findings[index] for index in unresolved)
    findings = review.response_findings + tuple(
        finding for finding in carried if finding not in review.response_findings
    )
    if any(finding.code not in TRIMMABLE_CODES for finding in findings) or len(findings) > MAX_FINDINGS:
        raise TrimRefused("finding_code")
    # An earlier finding was located on the draft; only its verbatim reply quote can be placed here.
    if any(finding.location.source_field != "candidate.response" for finding in carried):
        raise TrimRefused("unplaced_finding")

    reply = candidate.reply
    if _STRUCTURE.search(reply):
        raise TrimRefused("structured_reply")
    sentences = sentence_spans(reply)
    # A quotation the splitter cut stays one unit.
    spans = [(sentences[unit[0]][0], sentences[unit[-1]][1]) for unit in label_units(reply)]

    def touched(intervals: list[tuple[int, int]]) -> set[int]:
        return {index for index, (start, end) in enumerate(spans) if overlaps(start, end, intervals)}

    removed: set[int] = set()
    for finding in findings:
        named = touched(finding_intervals(finding.location, candidate) or [])
        if not named:
            raise TrimRefused("unplaced_finding")
        removed |= named

    declared = [
        text for use in candidate.evidence_uses
        for text in (*use.supported_claims, *limit_claim_texts(use), getattr(use, "exact_quote", None)) if text
    ]
    whole = [touched([found]) for text in declared for found in occurrences(reply, text)]
    while any(unit & removed and not unit <= removed for unit in whole):
        removed.update(*(unit for unit in whole if unit & removed))

    kept = [index for index in range(len(spans)) if index not in removed]
    if not kept:
        raise TrimRefused("empty_reply")
    gone = [spans[index] for index in sorted(removed)]

    def text(index: int) -> str:
        return reply[slice(*spans[index])]

    if any(_DOUBTFUL_END.search(text(near)) for index in removed for near in (index - 1, index) if near >= 0):
        raise TrimRefused("unsafe_boundary")
    # A sentence that opens in lower case continues the one before: the splitter cut mid-sentence.
    if any(text(near).lstrip("\"'“‘(*_")[:1].islower()
           for index in removed for near in (index, index + 1) if near < len(spans)):
        raise TrimRefused("unsafe_boundary")
    # A removed sentence may hold a whole quotation, bracket or emphasis, never part of one.
    pairs = _delimiter_pairs(reply)
    if pairs is None or any(
        overlaps(a, b + 1, gone) and not any(start <= a and b < end for start, end in gone)
        for a, b in pairs
    ):
        raise TrimRefused("split_delimiters")
    for index in kept:
        if index - 1 in removed or index + 1 in removed:
            if len(_WORD.findall(text(index))) < _MIN_NEIGHBOUR_WORDS:
                raise TrimRefused("fragment_remainder")
        if index - 1 in removed:
            opening = [word.lower() for word in _WORD.findall(text(index))[:4]]
            if _DEPENDENT_OPENING.match(text(index)) or "also" in opening:
                raise TrimRefused("dependent_remainder")

    parts = [text(kept[0])]
    for before, after in zip(kept, kept[1:]):
        breaks = [reply[spans[index][1]:spans[index + 1][0]] for index in range(before, after)]
        parts += [max(breaks, key=lambda gap: gap.count("\n")), text(after)]

    def lost(declared_text: str) -> bool:
        found = occurrences(reply, declared_text)
        return bool(found) and all(overlaps(start, end, gone) for start, end in found)

    uses = []
    for use in candidate.evidence_uses:
        claims = tuple(claim for claim in use.supported_claims if not lost(claim))
        if not claims:
            continue
        declaration = use.model_dump(mode="json")
        declaration["supported_claims"] = claims
        if "limit_claims" in declaration:
            declaration["limit_claims"] = tuple(limit for limit in limit_claim_texts(use) if not lost(limit))
        if declaration.get("exact_quote") and lost(declaration["exact_quote"]):
            declaration["exact_quote"] = None
        uses.append(declaration)
    if not any(use["source_kind"] != "session_line" for use in uses):
        raise TrimRefused("no_mapped_claim")
    trimmed = MuseCandidate.model_validate({
        "reply": "".join(parts),
        "evidence_uses": uses,
        "memory": candidate.memory.model_dump(mode="json"),
    })
    if supported_claim_errors(trimmed.reply, trimmed.evidence_uses):
        raise TrimRefused("invalid_candidate")
    return SentenceTrim(
        candidate=trimmed, removed=tuple(reply[start:end] for start, end in gone), findings=findings,
    )
