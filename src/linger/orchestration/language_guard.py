"""Deterministic, conservative guard for the reader message's language."""

from __future__ import annotations

import re
from dataclasses import dataclass

from fast_langdetect import LangDetectConfig, LangDetector

# The lite lid.176 model ships inside the wheel, so detection never touches
# the network. Input is truncated to the library's default 80 characters.
_DETECTOR = LangDetector(LangDetectConfig(model="lite", max_input_length=80))
_TOP_K = 3

# One CJK/Hangul character counts as one word; those scripts have no spaces.
_CJK_PATTERN = re.compile(r"[一-鿿぀-ヿ가-힣]")
_WORD_PATTERN = re.compile(r"[一-鿿぀-ヿ가-힣]|[^\W\d_]+")

# Below these bounds the signal is unreliable, so short text always passes.
# CJK/Hangul text has no spaces, so it qualifies by character count instead.
MIN_ALPHABETIC_WORDS = 4
MIN_LETTERS = 20
MIN_CJK_CHARS = 8

# Below this fraction of letters among non-whitespace characters, the
# message is numbers/punctuation (page refs, timestamps, emoji), not prose.
MIN_LETTER_RATIO = 0.4

# Refuse only when the top language is confidently non-English: genuine
# single-language sentences score 0.9-1.0 with English absent from the top
# results, while mixed text scores its top language around 0.6.
MIN_TOP_CONFIDENCE = 0.7
MIN_MARGIN_OVER_ENGLISH = 0.5


@dataclass(frozen=True)
class LanguageVerdict:
    """A confident non-English classification."""

    language: str  # lowercase ISO 639-1 code, e.g. "fr"
    confidence: float
    english_confidence: float


def _letter_count(text: str) -> int:
    return sum(1 for character in text if character.isalpha())


def detect_non_english(text: str) -> LanguageVerdict | None:
    """Return a verdict only when `text` is confidently not English."""
    stripped = text.strip()
    if not stripped:
        return None

    words = _WORD_PATTERN.findall(stripped)
    letters = _letter_count(stripped)
    cjk_chars = len(_CJK_PATTERN.findall(stripped))
    if len(words) < MIN_ALPHABETIC_WORDS:
        return None
    if letters < MIN_LETTERS and cjk_chars < MIN_CJK_CHARS:
        return None

    non_space = re.sub(r"\s+", "", stripped)
    if non_space and (letters / len(non_space)) < MIN_LETTER_RATIO:
        return None

    results = _DETECTOR.detect(stripped, k=_TOP_K)
    if not results:
        return None
    scores = {str(result["lang"]): float(result["score"]) for result in results}
    top_language = str(results[0]["lang"])
    top_confidence = scores[top_language]
    english_confidence = scores.get("en", 0.0)
    if top_language == "en" or top_confidence < MIN_TOP_CONFIDENCE:
        return None
    if (top_confidence - english_confidence) < MIN_MARGIN_OVER_ENGLISH:
        return None

    return LanguageVerdict(
        language=top_language,
        confidence=top_confidence,
        english_confidence=english_confidence,
    )
