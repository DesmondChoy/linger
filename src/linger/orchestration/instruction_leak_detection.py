"""Deterministic backstop against a candidate quoting its own instructions."""

import re
from functools import lru_cache

_APOSTROPHE_FOLD = str.maketrans({"'": "", "‘": "", "’": "", "ʼ": ""})
_SEPARATOR = re.compile(r"\W+")
# The longest reply fragment the reflection skill models as good output is
# fourteen words, so a shorter window would decline legitimate replies.
_WINDOW_WORDS = 16
_MIN_RUN_CHARS = 80


def _words(text: str) -> list[str]:
    """Reduce text to lowercase word tokens, dropping punctuation and markup."""
    return _SEPARATOR.sub(" ", text.translate(_APOSTROPHE_FOLD).casefold()).split()


@lru_cache(maxsize=4)
def _instruction_windows(instructions: str) -> frozenset[str]:
    """Return every long normalized word window of `instructions`, computed once."""
    words = _words(instructions)
    windows = (
        " ".join(words[start : start + _WINDOW_WORDS])
        for start in range(len(words) - _WINDOW_WORDS + 1)
    )
    return frozenset(window for window in windows if len(window) >= _MIN_RUN_CHARS)


def detect_instruction_leak(reply: str, instructions: str) -> bool:
    """Report whether `reply` reproduces a long verbatim run of `instructions`.

    Both sides are reduced to the same word tokens, so case, spacing,
    punctuation, quote characters, and Markdown around an otherwise verbatim
    span do not hide it. Every window of the reply is checked, so a run
    anywhere in a longer reply is caught. Paraphrase is Provenance's judgment,
    not this backstop's.
    """
    windows = _instruction_windows(instructions)
    words = _words(reply)
    return any(
        " ".join(words[start : start + _WINDOW_WORDS]) in windows
        for start in range(len(words) - _WINDOW_WORDS + 1)
    )
