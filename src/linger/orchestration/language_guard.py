"""Deterministic, conservative guard for the reader message's language."""

from __future__ import annotations

import re
from dataclasses import dataclass

from fast_langdetect import LangDetectConfig, LangDetector

# The lite lid.176 model ships inside the wheel, so detection never touches
# the network. Each classification call is truncated to this many characters.
_WINDOW_LENGTH = 80
_DETECTOR = LangDetector(LangDetectConfig(model="lite", max_input_length=_WINDOW_LENGTH))
_TOP_K = 3

# A trailing window shorter than this is merged into the previous one instead
# of being classified alone, where a one- or two-word fragment is easily
# mislabelled and would otherwise swing the verdict on its own.
_MIN_WINDOW_LENGTH = 30

# Refuse only when at least this share of the message's (gate-passing) letters
# sits in windows confidently classified as non-English.
MIN_NON_ENGLISH_LETTER_SHARE = 0.5

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


def _passes_prose_gates(text: str) -> bool:
    """Whether `text` has enough alphabetic signal to classify at all."""
    words = _WORD_PATTERN.findall(text)
    letters = _letter_count(text)
    cjk_chars = len(_CJK_PATTERN.findall(text))
    if len(words) < MIN_ALPHABETIC_WORDS:
        return False
    if letters < MIN_LETTERS and cjk_chars < MIN_CJK_CHARS:
        return False
    non_space = re.sub(r"\s+", "", text)
    if non_space and (letters / len(non_space)) < MIN_LETTER_RATIO:
        return False
    return True


def _split_into_windows(text: str) -> list[str]:
    """Pack words into ~_WINDOW_LENGTH-character windows, merging a short tail into the last."""
    tokens = text.split()
    if not tokens:
        return [text]
    windows: list[str] = []
    current: list[str] = []
    current_len = 0
    for token in tokens:
        extra = len(token) + (1 if current else 0)
        if current and current_len + extra > _WINDOW_LENGTH:
            windows.append(" ".join(current))
            current, current_len = [], 0
            extra = len(token)
        current.append(token)
        current_len += extra
    if current:
        windows.append(" ".join(current))
    if len(windows) > 1 and len(windows[-1]) < _MIN_WINDOW_LENGTH:
        tail = windows.pop()
        windows[-1] = f"{windows[-1]} {tail}"
    return windows


@dataclass(frozen=True)
class _WindowClassification:
    """The detector's raw top result for one window, before any thresholding."""

    top_language: str
    top_confidence: float
    english_confidence: float


def _classify_window(window: str) -> _WindowClassification | None:
    results = _DETECTOR.detect(window, k=_TOP_K)
    if not results:
        return None
    scores = {str(result["lang"]): float(result["score"]) for result in results}
    top_language = str(results[0]["lang"])
    return _WindowClassification(
        top_language=top_language,
        top_confidence=scores[top_language],
        english_confidence=scores.get("en", 0.0),
    )


def _as_verdict(classification: _WindowClassification) -> LanguageVerdict | None:
    if classification.top_language == "en" or classification.top_confidence < MIN_TOP_CONFIDENCE:
        return None
    if (classification.top_confidence - classification.english_confidence) < MIN_MARGIN_OVER_ENGLISH:
        return None
    return LanguageVerdict(
        language=classification.top_language,
        confidence=classification.top_confidence,
        english_confidence=classification.english_confidence,
    )


def detect_non_english(text: str) -> LanguageVerdict | None:
    """Refuse when confidently non-English windows carry most of the message's classified letters."""
    stripped = text.strip()
    if not stripped:
        return None
    if not _passes_prose_gates(stripped):
        return None

    # Unsure windows count for neither side; only confident calls weigh in.
    total_letters = 0
    non_english_letters = 0
    verdicts: list[LanguageVerdict] = []
    for window in _split_into_windows(stripped):
        if not _passes_prose_gates(window):
            continue
        classification = _classify_window(window)
        if classification is None:
            continue
        weight = _letter_count(window)
        verdict = _as_verdict(classification)
        if verdict is not None:
            total_letters += weight
            non_english_letters += weight
            verdicts.append(verdict)
        elif classification.top_language == "en":
            total_letters += weight

    if total_letters == 0 or not verdicts:
        return None
    if (non_english_letters / total_letters) < MIN_NON_ENGLISH_LETTER_SHARE:
        return None
    return max(verdicts, key=lambda verdict: verdict.confidence)
