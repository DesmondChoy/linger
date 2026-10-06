"""Compatibility check for callers that still need a Boolean privacy veto."""

from __future__ import annotations

from src.linger.contracts.security_validation import validate_storage_text


def contains_personal_data_or_secret(text: str) -> bool:
    """Whether the shared validator finds PII or a credential in `text`."""
    return bool(validate_storage_text(text).findings)
