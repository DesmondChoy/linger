"""Boolean privacy check used by synthetic outbound-query evaluations."""

from __future__ import annotations

from pydantic_ai_harness.guardrails.detectors import personal_data, redact_secrets

from src.linger.contracts.text_folding import fold_for_detection

_PHONE_NUMBER = (
    r"\+\d(?:[ .()-]?\d){7,14}(?!\d)"
    r"|(?<![\d(])(?:\(\d{3}\)[ .-]?|\d{3}[ .-])\d{3}[ .-]\d{4}(?!\d)"
)
_redact_personal_data = personal_data(extra={"phone": _PHONE_NUMBER})


def contains_personal_data_or_secret(text: str) -> bool:
    """Whether maintained detectors flag `text` or its folded copy."""
    candidates = (text, fold_for_detection(text))
    return any(
        detector(candidate).action != "allow"
        for detector in (_redact_personal_data, redact_secrets)
        for candidate in candidates
    )
