"""Deterministic detection of shaped personal data or credentials in text."""

from __future__ import annotations

from pydantic_ai_harness.guardrails.detectors import personal_data, redact_secrets

from src.linger.contracts.text_folding import fold_for_detection

_PHONE_NUMBER = (
    # International: "+" then 8 to 15 digits, at most one separator between any two.
    r"\+\d(?:[ .()-]?\d){7,14}(?!\d)"
    # National: a parenthesised or separated area code, then 3 and 4 more digits.
    # Both separators are required, so a bare digit run, a year range, an ISO
    # date, an ISBN, and a page range are all left alone.
    r"|(?<![\d(])(?:\(\d{3}\)[ .-]?|\d{3}[ .-])\d{3}[ .-]\d{4}(?!\d)"
)

_redact_personal_data = personal_data(extra={"phone": _PHONE_NUMBER})


def contains_personal_data_or_secret(text: str) -> bool:
    """Whether maintained detectors would rewrite `text` or its folded copy."""
    candidates = (text, fold_for_detection(text))
    return any(
        detector(candidate).action != "allow"
        for detector in (_redact_personal_data, redact_secrets)
        for candidate in candidates
    )
