"""Map a claim to the declared record that states it when Muse mapped it only to another.

Muse sometimes writes a clause from one retrieved record into a claim it maps only to
another record it declares. Each of the Librarian's stated answers names a record and a
quote that code has bound to that record's text, so the application can add the missing
mapping without a model call. It never removes a mapping, and the review still judges
whether each declared source supports the claim.

Known limit: a phrase that the claim's own records lack and a verified quote of another
declared record contains is taken as evidence that the claim draws on that record, even
when the phrase is as plain as "little girl" or "chapter five".
"""

import re
from collections.abc import Mapping

from src.linger.agents.muse.claim_repair import _normalized, _occurrences, _overlaps, _splits_word
from src.linger.agents.muse.models import MuseCandidate
from src.linger.contracts.librarian import EvidenceRecord, StatedAnswer

_WORD = re.compile(r"[^\W\d_]+")
# No phrase runs across the end of a sentence or paragraph.
_BREAK = re.compile(r"[.!?;:]|\n\s*\n")
# Function words, speech verbs and contraction stems say nothing about which record a claim draws on.
_STOPWORDS = frozenset(
    "about all also and any are because been being but can could did does down even for from had has "
    "have her here hers him his how into its just may might more most must not off one only our out "
    "over she should than that the their them then there these they this those too very was were what "
    "when which who whom why will with would you your said says say ain aren couldn didn doesn don hadn "
    "hasn haven isn shouldn wasn weren won wouldn".split()
)


def _is_content(word: str) -> bool:
    """Three or more letters and not a function word; no stemming."""
    return len(word) > 2 and word not in _STOPWORDS


def _content_words(text: str) -> set[str]:
    return set(filter(_is_content, _WORD.findall(text.casefold())))


def _phrases(text: str) -> list[tuple[str, ...]]:
    """Each casefolded run of words from one content word to the next within a sentence, in order,
    with the function words between them."""
    phrases: list[tuple[str, ...]] = []
    for sentence in _BREAK.split(text.casefold()):
        run: list[str] = []
        for word in _WORD.findall(sentence):
            if _is_content(word):
                if run:
                    phrases.append((*run, word))
                run = [word]
            elif run:
                run.append(word)
    return phrases


def _whole_words(quote: str, text: str) -> str | None:
    """The quote without a first or last word that its record's text continues, or None unless
    the text holds the quote, whitespace aside."""
    text, found = _normalized(text), _normalized(quote)
    start = text.find(found)
    if start < 0:
        return None
    if _splits_word(text, start):
        quote = re.sub(r"^\s*[^\W_]+", "", quote)
    if _splits_word(text, start + len(found)):
        quote = re.sub(r"[^\W_]+\s*$", "", quote)
    return quote


def _shared_phrase(claim: str, quote: str, texts: list[str]) -> tuple[str, ...] | None:
    """The claim's first phrase that the quote has word for word and whose two content words
    none of `texts` contains. A name or other single shared word ties nothing together."""
    present = {word for text in texts for word in _content_words(text)}
    quoted = set(_phrases(quote))
    return next((phrase for phrase in _phrases(claim)
                 if phrase in quoted and not present.intersection((phrase[0], phrase[-1]))), None)


def _covers(candidate: MuseCandidate, claims: list[str], claim: str, phrase: tuple[str, ...]) -> bool:
    """Whether one of `claims` overlaps `claim` in the reply and already holds the phrase's content words."""
    found = _occurrences(candidate.reply, claim)
    return any(
        {phrase[0], phrase[-1]} <= _content_words(covering)
        and any(_overlaps(a, b, found) for a, b in _occurrences(candidate.reply, covering))
        for covering in claims
    )


def stated_claim_additions(
    candidate: MuseCandidate, answers: tuple[StatedAnswer, ...], evidence: Mapping[str, EvidenceRecord],
) -> list[tuple[int, str]]:
    """Each (declaration index, claim) to add, at most one per claim.

    A claim mapped only to book records is stated by the first answer, in list order, whose quote
    shares a phrase with it: two content words with the same function words between them, inside
    one sentence, that the text of none of the claim's other records contains. If that answer's
    record is declared elsewhere in the candidate, the claim joins its first declaration, unless
    the record already supports this claim or an overlapping one holding the phrase. The answer
    text is the Librarian's paraphrase and counts for nothing; a quote counts only as whole words
    standing in its record's text.
    """
    declared: dict[str, int] = {}  # Each book record's first declaration.
    mapped: dict[str, set[str]] = {}
    supported: dict[str, list[str]] = {}
    other: set[str] = set()  # Claims a memory, page or reader line also supports are left alone.
    for index, use in enumerate(candidate.evidence_uses):
        if use.source_kind != "book_corpus":
            other.update(use.supported_claims)
            continue
        declared.setdefault(use.evidence_id, index)
        supported.setdefault(use.evidence_id, []).extend(use.supported_claims)
        for claim in use.supported_claims:
            mapped.setdefault(claim, set()).add(use.evidence_id)
    # Only an answer of a record the candidate declares can add a mapping.
    quotes = [(answer.evidence_id, quote) for answer in answers
              if answer.evidence_id in declared and answer.evidence_id in evidence
              and (quote := _whole_words(answer.source_quote, evidence[answer.evidence_id].text)) is not None]
    additions: list[tuple[int, str]] = []
    for claim, records in mapped.items():
        if claim in other or any(record not in evidence for record in records):
            continue
        for stating, quote in quotes:
            phrase = _shared_phrase(claim, quote, [evidence[record].text for record in records if record != stating])
            if phrase is None:
                continue
            # The first answer that states the claim decides, so the result is the same when reapplied.
            # A claim already mapped to the stating record covers itself.
            if not _covers(candidate, supported[stating], claim, phrase):
                additions.append((declared[stating], claim))
            break
    return additions


def with_supported_claim(candidate: MuseCandidate, index: int, claim: str) -> MuseCandidate:
    """The candidate with `claim` appended to one declaration's supported claims."""
    uses = list(candidate.evidence_uses)
    uses[index] = uses[index].model_copy(update={"supported_claims": (*uses[index].supported_claims, claim)})
    return candidate.model_copy(update={"evidence_uses": tuple(uses)})
