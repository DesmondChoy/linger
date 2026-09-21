"""Deterministic, high-precision first-person self-harm and suicide detector."""

import re

_APOSTROPHE_FOLD = str.maketrans({"‘": "'", "’": "'", "ʼ": "'"})

_ACT = (
    r"(?:kill(?:ing)? myself|end(?:ing)? (?:my life|it all)|"
    r"tak(?:e|ing) my (?:own )?life|hurt(?:ing)? myself|harm(?:ing)? myself|"
    r"cut(?:ting)? myself(?! off)|commit(?:ting)? suicide)"
)
_I_AM = r"i(?:'m|m| am)"
_ADVERB = r"(?:just |really |honestly |seriously |sometimes )?"

_FIRST_PERSON_SELF_HARM_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        rf"\bi {_ADVERB}(?:want|wanted|need|plan|planned|intend|intended) to "
        rf"(?:{_ACT}\b|die\b(?! of ))",
        rf"\b{_I_AM} {_ADVERB}(?:going|about|ready|planning|preparing) to {_ACT}\b",
        rf"\bi(?:'ve| have| had)? ?been {_ACT}\b",
        rf"\bi (?:keep|kept|can'?t stop) {_ACT}\b",
        rf"\bi(?:'ve| have|'m|m| am)? ?(?:been )?"
        rf"(?:thinking|thought|planning|planned) (?:about|of) (?:suicide|{_ACT})\b",
        rf"\bi (?:keep|kept|can'?t stop) thinking about (?:suicide|{_ACT})\b",
        rf"\b(?:{_I_AM}(?: feeling)?|i(?:'ve| have) been|i feel|i felt) "
        rf"{_ADVERB}suicidal\b",
        r"\bi(?: have| had|'ve had|'ve got) suicidal (?:thoughts|feelings|ideation)\b",
        r"\bi (?:don'?t|do not) want to be alive\b",
        r"\bi (?:don'?t|do not) want to (?:live|wake up|exist) any ?more\b",
        rf"\b(?:{_I_AM}|i'?d|i'?ll|i would|i will)(?: be)? better off dead\b",
    )
)


def _normalize(text: str) -> str:
    return " ".join(text.translate(_APOSTROPHE_FOLD).casefold().split())


def detect_first_person_self_harm(text: str) -> bool:
    """Match a first-person self-harm or suicide statement, never a third-person one."""
    normalized = _normalize(text)
    return any(
        pattern.search(normalized) for pattern in _FIRST_PERSON_SELF_HARM_PATTERNS
    )
