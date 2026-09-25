"""Deterministic first-person self-harm and suicide detector."""

import re

from src.linger.contracts.text_folding import fold_for_self_harm

_APOSTROPHE_FOLD = str.maketrans({"‘": "'", "’": "'", "ʼ": "'"})

_ACT = (
    r"(?:kill(?:ing)? myself|end(?:ing)? (?:my life|it all)|"
    r"tak(?:e|ing) my (?:own )?life|hurt(?:ing)? myself|harm(?:ing)? myself|"
    r"cut(?:ting)? myself(?! off)|commit(?:ting)? suicide|"
    r"unalive(?:d|ing)? (?:myself|me))"
)
_I_AM = r"i(?:'m|m| am)"
_ADVERB = r"(?:just |really |honestly |seriously |sometimes )?"
_WANT = r"(?:want|wanted|wnat|wan|need|plan|planned|intend|intended)"
_GOING_TO = r"(?:(?:going|about|ready|planning|preparing) to|gonna)"

_FIRST_PERSON_SELF_HARM_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        rf"\bi {_ADVERB}(?:{_WANT} to|wanna) "
        rf"(?:{_ACT}\b|die\b(?! of ))",
        rf"\b{_I_AM} {_ADVERB}{_GOING_TO} {_ACT}\b",
        rf"\bi(?:'ve| have| had)? ?been {_ACT}\b",
        rf"\bi (?:keep|kept|can'?t stop) {_ACT}\b",
        rf"\bi(?:'ve| have|'m|m| am)? ?(?:been )?"
        rf"(?:thinking|thought|planning|planned) (?:about|of) (?:suicide|{_ACT})\b",
        rf"\bi (?:keep|kept|can'?t stop) thinking about (?:suicide|{_ACT})\b",
        rf"\b(?:{_I_AM}(?: feeling)?|i(?:'ve| have) been|i feel|i felt) "
        rf"{_ADVERB}suicidal\b",
        r"\bi(?: have| had|'ve had|'ve got) suicidal (?:thoughts|feelings|ideation)\b",
        r"\bi (?:don'?t|do not) want to be alive\b",
        # Clause must end here so "don't want to live in this city" does not match.
        r"\bi (?:don'?t|do not) want to (?:live|wake up|exist)"
        r"(?:\s+any ?more)?(?=[.,!?;:]|$)",
        r"\bi (?:don'?t|do not) want to be here any ?more\b",
        rf"\b(?:{_I_AM}|i'?d|i'?ll|i would|i will)(?: be)? better off dead\b",
        r"\bi(?:'ve| have)? ?(?:got )?no reason to (?:live|go on)\b",
        r"\bbetter off without me\b",
        # Dialect elisions of "was/were" before "never born" (e.g. Singlish).
        r"\bbetter if i(?: was| were)? never born\b",
        r"\bi wish i (?:was|were) never born\b",
    )
)


def _normalize(text: str) -> str:
    return " ".join(text.translate(_APOSTROPHE_FOLD).casefold().split())


def detect_first_person_self_harm(text: str) -> bool:
    """Match a first-person self-harm or suicide statement, never a third-person one."""
    normalized = _normalize(fold_for_self_harm(text))
    return any(
        pattern.search(normalized) for pattern in _FIRST_PERSON_SELF_HARM_PATTERNS
    )
