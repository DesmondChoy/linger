"""Detector-only text folding. Never used for stored or quoted text."""

from __future__ import annotations

import re
import unicodedata

_COMBINING_CATEGORIES = frozenset({"Mn", "Mc", "Me"})

# Lowercase Cyrillic/Greek letters visually identical to a Latin letter.
_HOMOGLYPHS: dict[str, str] = {
    # Cyrillic
    "а": "a",
    "е": "e",
    "о": "o",
    "р": "p",
    "с": "c",
    "у": "y",
    "х": "x",
    "і": "i",
    "ј": "j",
    "ѕ": "s",
    # Greek
    "α": "a",
    "ε": "e",
    "ο": "o",
    "ρ": "p",
    "ν": "v",
    "υ": "u",
}

_HOMOGLYPH_TABLE = str.maketrans(_HOMOGLYPHS)


def fold_for_detection(text: str) -> str:
    """NFKD, strip combining marks, map homoglyphs, casefold, NFKC."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(
        char
        for char in decomposed
        if unicodedata.category(char) not in _COMBINING_CATEGORIES
    )
    folded = stripped.translate(_HOMOGLYPH_TABLE).casefold()
    return unicodedata.normalize("NFKC", folded)


# '2' and '8' stand for whole words, so they are left out.
_LEET_MAP = {
    "0": "o",
    "1": "i",
    "3": "e",
    "4": "a",
    "5": "s",
    "7": "t",
    "@": "a",
    "$": "s",
    "!": "i",
}

_LEET_TOKEN = re.compile(r"[A-Za-z0-9@$!]+")

# Three or more single letters separated by space, hyphen, dot, or underscore.
_SPACED_LETTERS = re.compile(r"\b([a-zA-Z])(?:[ \-._]([a-zA-Z])){2,}\b")


def _fold_leet_token(match: re.Match[str]) -> str:
    # Only tokens mixing a letter with a digit fold, so plain numbers stay intact.
    token = match.group(0)
    if not (any(char.isdigit() for char in token) and any(char.isalpha() for char in token)):
        return token
    return "".join(_LEET_MAP.get(char, char) for char in token)


def _collapse_spaced_letters(match: re.Match[str]) -> str:
    return re.sub(r"[ \-._]", "", match.group(0))


def fold_for_self_harm(text: str) -> str:
    """`fold_for_detection` plus leetspeak and spaced-letter collapse."""
    folded = fold_for_detection(text)
    collapsed = _SPACED_LETTERS.sub(_collapse_spaced_letters, folded)
    return _LEET_TOKEN.sub(_fold_leet_token, collapsed)
