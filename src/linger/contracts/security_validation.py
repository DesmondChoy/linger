"""Typed, value-free decisions for deterministic privacy boundaries."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import StrEnum
from importlib.metadata import version

# DataFog is opt-in for telemetry. Force its opt-out before importing it so a
# deployment-level opt-in cannot enable telemetry inside Linger.
os.environ["DATAFOG_NO_TELEMETRY"] = "1"

# The opt-out must be set before DataFog loads its telemetry code.
import datafog  # noqa: E402
from pydantic_ai_harness.guardrails.detectors import redact_secrets
from src.linger.contracts.text_folding import fold_for_detection

DATAFOG_VERSION = version("datafog")
SECRET_DETECTOR_VERSION = version("pydantic-ai-harness")

INJECTION_BLOCK_MESSAGE = (
    "This turn was blocked because instruction-like content was detected in "
    "the request or its source material. Rephrase the request or remove the "
    "affected source and try again."
)
_CREDENTIAL_BLOCK_MESSAGE = "This request was blocked because it contains a credential."
INJECTION_RULESET_VERSION = "1"


class ValidationCategory(StrEnum):
    PII = "pii"
    CREDENTIAL = "credential"
    PROMPT_INJECTION = "prompt_injection"


class ValidationDisposition(StrEnum):
    REDACT = "redact"
    BLOCK = "block"


class ValidationBoundary(StrEnum):
    PROVIDER_REQUEST = "provider_request"
    USER_INPUT = "user_input"
    UNTRUSTED_CONTEXT = "untrusted_context"
    GENERATED_OUTPUT = "generated_output"
    PERSISTENT_STORAGE = "persistent_storage"


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    """A safe finding. Source offsets are transient and never contain values."""

    category: ValidationCategory
    detector_id: str
    detector_version: str
    boundary: ValidationBoundary
    disposition: ValidationDisposition
    pattern_id: str | None = None
    source_start: int | None = None
    source_end: int | None = None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Redacted text and value-free decisions for one text boundary."""

    text: str
    findings: tuple[ValidationFinding, ...]
    user_message: str | None = None

    @property
    def blocked(self) -> bool:
        return any(
            finding.disposition is ValidationDisposition.BLOCK
            for finding in self.findings
        )


class SecurityValidationBlocked(RuntimeError):
    """A value-free exception that stops a blocked request or candidate."""

    def __init__(self, category: ValidationCategory, user_message: str) -> None:
        self.category = category
        self.user_message = user_message
        super().__init__(user_message)


@dataclass(frozen=True, slots=True)
class InjectionRule:
    """An adopted injection rule supplied by the application policy."""

    pattern_id: str
    expression: re.Pattern[str]


USER_INPUT_INJECTION_RULES = (
    InjectionRule(
        pattern_id="override_companion_instructions",
        expression=re.compile(
            r"\bignore\b.{0,50}\b(?:previous|prior|your|app|application|system)\b"
            r".{0,30}\binstructions?\b",
            re.IGNORECASE,
        ),
    ),
    InjectionRule(
        pattern_id="request_hidden_instructions",
        expression=re.compile(
            r"\b(?:reveal|show|print|repeat|disclose)\b.{0,50}\b"
            r"(?:hidden\s+)?(?:system\s+)?(?:prompt|instructions?)\b",
            re.IGNORECASE,
        ),
    ),
    InjectionRule(
        pattern_id="follow_replacement_instructions",
        expression=re.compile(
            r"\bfollow\s+only\b.{0,50}\binstructions?\b",
            re.IGNORECASE,
        ),
    ),
)


def validate_user_input(text: str) -> ValidationResult:
    """Redact PII and block credentials in the incoming chat message."""
    return _validate_text(text, ValidationBoundary.USER_INPUT)


def validate_untrusted_span(
    text: str,
    *,
    injection_rules: tuple[InjectionRule, ...],
    boundary: ValidationBoundary = ValidationBoundary.UNTRUSTED_CONTEXT,
) -> ValidationResult:
    """Check credentials and adopted injection rules before context entry."""
    # The chat entry point already redacts PII before this check. Keep this
    # boundary focused on credentials and the configured injection rules.
    result = validate_credentials(text, boundary=boundary)
    findings = list(result.findings)
    for rule in injection_rules:
        match = rule.expression.search(text)
        if match is None:
            continue
        findings.append(
            ValidationFinding(
                category=ValidationCategory.PROMPT_INJECTION,
                detector_id="linger_injection_rules",
                detector_version=INJECTION_RULESET_VERSION,
                boundary=boundary,
                disposition=ValidationDisposition.BLOCK,
                pattern_id=rule.pattern_id,
                source_start=match.start(),
                source_end=match.end(),
            )
        )
    message = INJECTION_BLOCK_MESSAGE if any(
        finding.category is ValidationCategory.PROMPT_INJECTION
        for finding in findings
    ) else result.user_message
    blocked = any(
        finding.disposition is ValidationDisposition.BLOCK
        for finding in findings
    )
    return ValidationResult("" if blocked else result.text, tuple(findings), message)


def validate_generated_credentials(text: str) -> ValidationResult:
    """Block credentials in generated text without applying PII detection."""
    return validate_credentials(text, boundary=ValidationBoundary.GENERATED_OUTPUT)


def validate_credentials(
    text: str,
    *,
    boundary: ValidationBoundary = ValidationBoundary.PERSISTENT_STORAGE,
) -> ValidationResult:
    """Block credentials without applying PII detection."""
    if not isinstance(text, str):
        raise TypeError("security validation accepts text only")
    try:
        secret_detected = any(
            redact_secrets(candidate).action != "allow"
            for candidate in dict.fromkeys((text, fold_for_detection(text)))
        )
    except Exception:
        raise RuntimeError("security validator failed") from None
    if not secret_detected:
        return ValidationResult(text, ())
    return ValidationResult(
        "",
        (ValidationFinding(
            category=ValidationCategory.CREDENTIAL,
            detector_id="pydantic_ai_harness.redact_secrets",
            detector_version=SECRET_DETECTOR_VERSION,
            boundary=boundary,
            disposition=ValidationDisposition.BLOCK,
        ),),
        _CREDENTIAL_BLOCK_MESSAGE,
    )


def check_storage_credentials(value: object) -> object:
    """Reject credential-bearing string leaves in JSON-like values."""
    if isinstance(value, str):
        result = validate_credentials(value)
        if result.blocked:
            raise SecurityValidationBlocked(
                ValidationCategory.CREDENTIAL,
                result.user_message or _CREDENTIAL_BLOCK_MESSAGE,
            )
        return result.text
    if isinstance(value, dict):
        return {key: check_storage_credentials(item) for key, item in value.items()}
    if isinstance(value, list):
        return [check_storage_credentials(item) for item in value]
    if isinstance(value, tuple):
        return tuple(check_storage_credentials(item) for item in value)
    return value


def _validate_text(text: str, boundary: ValidationBoundary) -> ValidationResult:
    if not isinstance(text, str):
        raise TypeError("security validation accepts text only")

    try:
        scan = datafog.scan(
            text,
            engine="regex",
            entity_types=["EMAIL", "PHONE"],
        )
        entities = tuple(scan.entities)
        redaction = datafog.redact(
            text,
            entities=list(entities),
            engine="regex",
        )
        redacted_text = redaction.redacted_text
        del redaction
        secret_detected = any(
            redact_secrets(candidate).action != "allow"
            for candidate in dict.fromkeys((text, fold_for_detection(text)))
        )
    except Exception:
        # Detector exceptions may include input data. Replace them with a
        # fixed message so callers cannot leak text through error reporting.
        raise RuntimeError("security validator failed") from None

    findings = [
        ValidationFinding(
            category=ValidationCategory.PII,
            detector_id="datafog.regex",
            detector_version=DATAFOG_VERSION,
            boundary=boundary,
            disposition=ValidationDisposition.REDACT,
            pattern_id=entity.type,
            source_start=entity.start,
            source_end=entity.end,
        )
        for entity in entities
    ]
    message = None
    if secret_detected:
        findings.append(
            ValidationFinding(
                category=ValidationCategory.CREDENTIAL,
                detector_id="pydantic_ai_harness.redact_secrets",
                detector_version=SECRET_DETECTOR_VERSION,
                boundary=boundary,
                disposition=ValidationDisposition.BLOCK,
            )
        )
        message = _CREDENTIAL_BLOCK_MESSAGE

    if secret_detected:
        # Never return the blocked credential, even inside a result intended
        # only for internal control flow.
        redacted_text = ""
    return ValidationResult(redacted_text, tuple(findings), message)
