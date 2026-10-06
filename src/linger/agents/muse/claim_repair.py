"""Preserve accepted claim coverage and supporting sources during revision."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from src.linger.agents.muse.models import (
    DraftSentence, MuseCandidate, RetainedSource, SentenceMapping, limit_claim_texts,
)

if TYPE_CHECKING:
    from src.linger.agents.provenance.models import (
        FindingLocation, ProvenanceReview, RiskFinding, UncoveredResponseSpan,
    )


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


_SENTENCE_BREAK = re.compile(r"(?<=[.?!])[\"'”’)\]*_]*(?=\s)|\n[ \t]*\n")
_MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")
_WORD = re.compile(r"\w+")
# A connective or two left unmapped ("but", "and so") is not a source claim.
_MAX_UNMAPPED_WORDS = 3
# Word overlap at which a new sentence reads as a rewrite of a draft sentence.
_REWRITE_SIMILARITY = 0.5
# A claim is kept draft wording when one unbroken run of draft words is this long
# and covers this share of the claim's words.
_MIN_KEPT_RUN = 5
_MIN_KEPT_SHARE = 0.7


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for match in _SENTENCE_BREAK.finditer(text):
        spans.append((start, match.end()))
        start = match.end()
    spans.append((start, len(text)))
    trimmed = []
    for start, end in spans:
        segment = text[start:end]
        if segment.strip():
            lead = len(segment) - len(segment.lstrip())
            trimmed.append((start + lead, start + len(segment.rstrip())))
    return trimmed


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _overlaps(start: int, end: int, intervals: list[tuple[int, int]]) -> bool:
    return any(a < end and start < b for a, b in intervals)


def _finding_intervals(location: FindingLocation, candidate: MuseCandidate) -> list[tuple[int, int]] | None:
    """Reply text a finding names, or None when it could concern any sentence."""
    reply = candidate.reply
    if location.source_field == "candidate.response":
        quote = getattr(location, "quote", None)
        if location.kind != "text_span" or location.path or not quote:
            return None
        return _occurrences(reply, quote) or None
    if location.source_field != "candidate.evidence_uses":
        return None
    parts = location.path.split("/")[1:]
    if not parts or not parts[0].isdigit() or int(parts[0]) >= len(candidate.evidence_uses):
        return None
    use = candidate.evidence_uses[int(parts[0])]
    fields = {"supported_claims": use.supported_claims, "limit_claims": limit_claim_texts(use)}
    if len(parts) >= 3 and parts[1] in fields and parts[2].isdigit():
        texts = fields[parts[1]][int(parts[2]):int(parts[2]) + 1]
    else:
        quote = getattr(use, "exact_quote", None)
        texts = (*use.supported_claims, *limit_claim_texts(use), *((quote,) if quote else ()))
    return [interval for text in texts for interval in _occurrences(reply, text)] or None


def draft_sentences_for_revision(
    candidate: MuseCandidate, review: ProvenanceReview,
    uncovered_spans: tuple[UncoveredResponseSpan, ...],
) -> tuple[DraftSentence, ...]:
    """Mark the sentences findings name; an unplaceable finding leaves every sentence open."""
    if review.response_decision != "revise":
        return ()
    placed: list[list[tuple[int, int]]] = []
    for finding in review.response_findings:
        intervals = _finding_intervals(finding.location, candidate)
        if intervals is None:
            return ()
        placed.append(intervals)
    source_dependent = {item.span_index for item in review.coverage_audit
                        if item.classification == "source_dependent"}
    needs_source = [(span.start, span.end) for span in uncovered_spans
                    if span.span_index in source_dependent]
    reply = candidate.reply
    sentences = []
    for start, end in _sentence_spans(reply):
        # Indexes into `response_findings`, the revision's `review.findings`.
        findings = tuple(index for index, intervals in enumerate(placed) if _overlaps(start, end, intervals))
        sentences.append(DraftSentence(
            text=reply[start:end],
            flagged=bool(findings),
            needs_source=_overlaps(start, end, needs_source),
            finding_indexes=findings,
            source_mappings=_sentence_mappings(candidate, start, end),
        ))
    return label_sentences(candidate, tuple(sentences))


def _label_units(reply: str) -> list[list[int]]:
    """Runs of sentence indexes joined by a quotation the splitter cut; every other sentence alone."""
    from src.linger.agents.provenance.quotation_audit import quoted_response_spans

    spans = _sentence_spans(reply)
    quotes = [(quote.start, quote.end) for quote in quoted_response_spans(reply)]
    units: list[list[int]] = []
    for index, (start, _) in enumerate(spans):
        if index and any(a < spans[index - 1][1] and start < b for a, b in quotes):
            units[-1].append(index)
        else:
            units.append([index])
    return units


def label_sentences(
    candidate: MuseCandidate, sentences: tuple[DraftSentence, ...],
) -> tuple[DraftSentence, ...]:
    """Label each unit of unflagged sentences whose text and declarations the revision can carry whole."""
    spans = _sentence_spans(candidate.reply)
    labels: dict[int, str] = {}
    for unit in _label_units(candidate.reply):
        start, end = spans[unit[0]][0], spans[unit[-1]][1]
        if any(sentences[i].flagged or sentences[i].needs_source for i in unit):
            continue
        if not _carried_without_loss(candidate, start, end):
            continue
        labels.update((i, f"{{{{SENTENCE_{unit[0] + 1}}}}}") for i in unit)
    return tuple(sentence.model_copy(update={"label": labels.get(i)}) for i, sentence in enumerate(sentences))


def _carried_without_loss(candidate: MuseCandidate, start: int, end: int) -> bool:
    """Every limit and quote touching the unit lies inside it, beside a supported claim of the same source."""
    reply = candidate.reply
    for use in candidate.evidence_uses:
        quote = getattr(use, "exact_quote", None)
        touching = [found for text in (*limit_claim_texts(use), *((quote,) if quote else ()))
                    for found in _occurrences(reply, text) if _overlaps(start, end, [found])]
        if not touching:
            continue
        if any(a < start or end < b for a, b in touching):
            return False
        if not any(_WORD.search(reply[max(a, start):min(b, end)])
                   for claim in use.supported_claims for a, b in _occurrences(reply, claim)
                   if _overlaps(start, end, [(a, b)])):
            return False
    return True


def _sentence_mappings(candidate: MuseCandidate, start: int, end: int) -> tuple[SentenceMapping, ...]:
    """Each declared text that overlaps the sentence span, with its declaration and field."""
    reply = candidate.reply
    mappings = []
    for index, use in enumerate(candidate.evidence_uses):
        source = use.quote if use.source_kind == "session_line" else use.evidence_id
        quote = getattr(use, "exact_quote", None)
        for field, texts in (("supported_claims", use.supported_claims), ("limit_claims", limit_claim_texts(use)),
                             ("exact_quote", (quote,) if quote else ())):
            mappings += [
                SentenceMapping(source_kind=use.source_kind, evidence_id=source, mapped_text=text,
                                declaration_index=index, field=field)
                for text in texts if _overlaps(start, end, _occurrences(reply, text))
            ]
    return tuple(mappings)


def _mapping_keys(mappings: tuple[SentenceMapping, ...]) -> set[tuple[str, str, str]]:
    return {(item.source_kind, item.evidence_id, _normalized(item.mapped_text)) for item in mappings}


def _similarity(first: str, second: str) -> float:
    return SequenceMatcher(None, first.lower().split(), second.lower().split(), autojunk=False).ratio()


def _unmapped_words(candidate: MuseCandidate, start: int, end: int) -> int:
    reply = candidate.reply
    covered = bytearray(len(reply))
    for use in candidate.evidence_uses:
        quote = getattr(use, "exact_quote", None)
        for text in (*use.supported_claims, *limit_claim_texts(use), *((quote,) if quote else ())):
            for a, b in _occurrences(reply, text):
                covered[a:b] = b"\1" * (b - a)
    unmapped = "".join(" " if covered[index] else reply[index] for index in range(start, end))
    return len(_WORD.findall(_MARKDOWN_LINK.sub(" ", unmapped)))


def added_source_errors(
    candidate: MuseCandidate, draft_sentences: tuple[DraftSentence, ...], findings: tuple[RiskFinding, ...],
) -> list[dict[str, object]]:
    """Keep the draft's sources on draft wording no finding disputes; new wording may cite any source."""
    if not draft_sentences:
        return []
    texts = [_normalized(sentence.text) for sentence in draft_sentences]
    draft = " ".join(texts)
    disputed: list[tuple[int, int]] = []
    mapped: list[tuple[int, int, tuple[str, str]]] = []
    offset = 0
    for sentence, text in zip(draft_sentences, texts):
        for index in sentence.finding_indexes:
            if index >= len(findings):
                continue
            location = findings[index].location
            quote = getattr(location, "quote", None) if location.source_field == "candidate.response" else None
            # A finding on a declaration frees every mapping in the sentences it names.
            disputed.extend(quote and _occurrences(draft, _normalized(quote)) or [(offset, offset + len(text))])
        for mapping in sentence.source_mappings:
            mapped.extend((a, b, (mapping.source_kind, mapping.evidence_id))
                          for a, b in _occurrences(draft, _normalized(mapping.mapped_text)))
        offset += len(text) + 1
    # Draft words with their character spans; case, punctuation and link targets do not count.
    spans = [match.span() for match in _WORD.finditer(_MARKDOWN_LINK.sub(lambda m: " " * len(m[0]), draft))]
    words = [draft[a:b].lower().strip("_") for a, b in spans]
    errors = []
    for use in candidate.evidence_uses:
        source = (use.source_kind, use.quote if use.source_kind == "session_line" else use.evidence_id)
        for claim in use.supported_claims:
            claimed = [word.lower().strip("_") for word in _WORD.findall(_MARKDOWN_LINK.sub(" ", claim))]
            run = SequenceMatcher(None, words, claimed, autojunk=False).find_longest_match(
                0, len(words), 0, len(claimed))
            if run.size < _MIN_KEPT_RUN or run.size < _MIN_KEPT_SHARE * len(claimed):
                continue
            # Every draft occurrence of the kept run counts.
            run_words = words[run.a:run.a + run.size]
            found = [(spans[i][0], spans[i + run.size - 1][1]) for i in range(len(words) - run.size + 1)
                     if words[i:i + run.size] == run_words]
            if any(_overlaps(a, b, disputed) for a, b in found):
                continue
            # Draft wording the draft left unmapped may cite any source.
            before = {key for a, b, key in mapped if _overlaps(a, b, found)}
            if before and source not in before:
                start = candidate.reply.find(claim)
                errors.append({
                    "path": "evidence_uses", "value": claim,
                    "response_start": start, "response_end": start + len(claim),
                    "source_kind": use.source_kind, "evidence_id": source[1],
                    "error": (
                        "This wording was kept from the draft and no finding disputes it or its sources, "
                        "so it must keep the draft's sources: remove this added source from it. If a "
                        "retained source now has no claim, rewrite the flagged claim to state what "
                        "that source establishes rather than attaching the source to other text."
                    ),
                })
    return errors


def draft_sentence_errors(
    candidate: MuseCandidate, draft_sentences: tuple[DraftSentence, ...],
) -> list[dict[str, object]]:
    """Keep unflagged sentences word for word, require each finding to change a sentence it
    names, and map or delete source-dependent ones."""
    if not draft_sentences:
        return []
    reply = candidate.reply
    spans = _sentence_spans(reply)
    revised = [_normalized(reply[start:end]) for start, end in spans]
    drafted = [_normalized(sentence.text) for sentence in draft_sentences]
    errors: list[dict[str, object]] = []
    # Flagged draft sentences that changed nothing: their revised span, or None
    # when the needs_source error already reports them.
    kept: dict[int, tuple[int, int] | None] = {}
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, drafted, revised, autojunk=False).get_opcodes():
        for j in range(j1, j2):
            start, end = spans[j]
            if tag == "equal":
                index, unchanged = i1 + j - j1, True
            elif revised[j] in drafted:
                index, unchanged = drafted.index(revised[j]), True
            elif tag == "insert":
                neighbours = [draft_sentences[i] for i in (i1 - 1, i1) if 0 <= i < len(drafted)]
                if not any(sentence.flagged for sentence in neighbours):
                    errors.append({
                        "path": "reply", "value": reply[start:end],
                        "response_start": start, "response_end": end,
                        "error": (
                            "This new sentence is not beside any sentence a finding names. Only "
                            "flagged sentences may change: delete it, or place the repair next "
                            "to the flagged sentence it repairs."
                        ),
                    })
                continue
            else:
                block = range(i1, i2)
                index = max(block, key=lambda i: _similarity(drafted[i], revised[j]))
                if not draft_sentences[index].flagged and any(draft_sentences[i].flagged for i in block) and (
                    _similarity(drafted[index], revised[j]) < _REWRITE_SIMILARITY
                ):
                    # New wording beside a flagged repair, not a rewrite of this sentence.
                    index = max((i for i in block if draft_sentences[i].flagged),
                                key=lambda i: _similarity(drafted[i], revised[j]))
                unchanged = False
            origin = draft_sentences[index]
            if not unchanged and not origin.flagged:
                errors.append({
                    "path": "reply", "value": reply[start:end], "draft_sentence": origin.text,
                    "response_start": start, "response_end": end,
                    "error": (
                        "This rewrites a draft sentence that no finding names. Only flagged "
                        "sentences may change, because the next review has no revision left to "
                        "repair new wording. Restore only this draft_sentence word for word, or "
                        "delete it, and keep the repairs already made: each finding must still "
                        "change at least one sentence it names."
                    ),
                })
            elif (origin.needs_source and not revised[j].endswith("?")
                  and _similarity(_normalized(origin.text), revised[j]) >= _REWRITE_SIMILARITY
                  and _unmapped_words(candidate, start, end) > _MAX_UNMAPPED_WORDS):
                kept.setdefault(index, None)
                errors.append({
                    "path": "evidence_uses", "value": reply[start:end],
                    "response_start": start, "response_end": end,
                    "error": (
                        "The review judged this sentence's unmapped content source-dependent. "
                        "Map its complete substantive content to the sources that support it, or "
                        "delete it. Rewording alone does not resolve it."
                    ),
                })
            elif (unchanged and origin.flagged and _mapping_keys(origin.source_mappings)
                  == _mapping_keys(_sentence_mappings(candidate, start, end))):
                kept.setdefault(index, (start, end))
    unaddressed: dict[int, tuple[int, int]] = {}
    for finding in {finding for sentence in draft_sentences for finding in sentence.finding_indexes}:
        named = [i for i, sentence in enumerate(draft_sentences) if finding in sentence.finding_indexes]
        if all(i in kept for i in named):
            unaddressed.update((i, span) for i in named if (span := kept[i]) is not None)
    for index, (start, end) in sorted(unaddressed.items(), key=lambda item: item[1]):
        errors.append({
            "path": "reply", "value": reply[start:end], "draft_sentence": draft_sentences[index].text,
            "response_start": start, "response_end": end,
            "error": (
                "A review finding names this sentence, and no sentence it names was repaired: "
                "this one came back unchanged with the same sources. Repair at least one of "
                "them: rewrite the sentence to state only what the source establishes, delete "
                "it, or change a source mapping the finding disputes."
            ),
        })
    return errors
