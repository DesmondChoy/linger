"""Typed Provenance hand-off contracts.

One review call carries two decoupled decisions (specification section 4.1):
whether the response may be released, and whether an automatic memory candidate
may be captured. Rejecting capture never suppresses an otherwise safe response.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from src.linger.agents.contracts import StrictModel

# A 1:1 transcription of the specification section 6.5 block conditions.
RiskCode = Literal[
    "unresolved_evidence",
    "misattribution",
    "spoiler",
    "boundary_violation",
    "uncited_web_claim",
    "unsupported_claim",
    "sensitive_content",
    "prompt_injection",
]

# Grounds that make content ineligible for automatic capture.
SENSITIVE_RISK_CODES: frozenset[str] = frozenset(
    {
        "unsupported_claim",
        "sensitive_content",
        "boundary_violation",
        "prompt_injection",
    }
)

# One review reports at most this many findings.
MAX_FINDINGS = 20


class RiskFinding(StrictModel):
    """One detected risk, tied to the span that caused it."""

    code: RiskCode
    quote: str = Field(min_length=1, max_length=300)
    explanation: str = Field(min_length=1, max_length=500)


class ProvenanceReview(StrictModel):
    """One review of one candidate, carrying both release decisions."""

    # `max_length` is enforced below rather than declared on the field: an array
    # bound in the wire schema makes Gemini reject the whole request with
    # "constraint that has too many states for serving". String bounds are fine.
    findings: tuple[RiskFinding, ...] = ()
    response_decision: Literal["pass", "revise", "reject"]
    capture_decision: Literal["allow_capture", "reject_capture", "no_candidate"]

    @model_validator(mode="after")
    def require_justified_refusal(self) -> Self:
        """Forbid blocking without naming a specific risk code."""
        if len(self.findings) > MAX_FINDINGS:
            raise ValueError(f"a review carries at most {MAX_FINDINGS} findings")
        if self.response_decision != "pass" and not self.findings:
            raise ValueError(
                "a non-pass response_decision requires at least one finding"
            )
        if self.capture_decision == "reject_capture" and not self.findings:
            raise ValueError("reject_capture requires at least one finding")
        if self.capture_decision == "allow_capture" and self.contains_sensitive_content:
            raise ValueError("sensitive content cannot be allowed for automatic capture")
        return self

    @property
    def contains_sensitive_content(self) -> bool:
        """Report whether any finding bars this content from automatic capture."""
        return any(finding.code in SENSITIVE_RISK_CODES for finding in self.findings)

    def critique(self) -> str:
        """Render the findings as revision guidance for one Muse retry."""
        return "\n".join(
            f"- [{finding.code}] {finding.explanation} (offending text: {finding.quote!r})"
            for finding in self.findings
        )
