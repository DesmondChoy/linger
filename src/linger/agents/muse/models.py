"""Typed Muse output used by the application release and capture boundaries."""

import re
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from src.linger.agents.contracts import StrictModel

MemoryCandidateReasonCode = Literal[
    "durable_reflection",
    "stable_preference_or_intention",
    "personally_significant_incident",
]
NoMemoryCandidateReasonCode = Literal[
    "transient_or_low_signal",
    "unsupported_third_party_claim",
    "near_duplicate_without_update",
    "nomination_policy_ambiguous",
    "no_user_words",
    "automatic_capture_disabled",
    "emotional_boundary",
]


class EvidenceClaimSupport(StrictModel):
    """Exact reply spans to which one source declares a supporting contribution."""

    supported_claims: tuple[
        Annotated[str, Field(min_length=1, max_length=20_000)], ...
    ] = Field(
        min_length=1,
        description=(
            "Exact substantive reply spans to which this source contributes support. "
            "A complete claim may be repeated across declarations when several sources jointly support it; "
            "this source need only establish its relevant part, while the declared sources together "
            "must establish the whole claim. "
            "Include the factual description or interpretation itself, not just its introductory phrase. "
            "Map all claims that rely on this source and update them when revising the reply."
        ),
    )

    @model_validator(mode="after")
    def require_distinct_claims(self) -> Self:
        if any(not claim.strip() for claim in self.supported_claims):
            raise ValueError("supported_claims must not contain blank text")
        if len(set(self.supported_claims)) != len(self.supported_claims):
            raise ValueError("supported_claims must not repeat a claim for the same source")
        return self


class BookEvidenceUse(EvidenceClaimSupport):
    """One book-corpus record Muse declares as support for its reply."""

    source_kind: Literal["book_corpus"]
    evidence_id: str = Field(min_length=1, max_length=200)
    source_location: str = Field(min_length=1, max_length=500)
    exact_quote: str | None = Field(default=None, min_length=1, max_length=2_000)


class MemoryEvidenceUse(EvidenceClaimSupport):
    """An exact account-scoped memory selected during this turn's discovery."""

    source_kind: Literal["memory"]
    evidence_id: str = Field(min_length=1, max_length=200)
    exact_quote: str | None = Field(default=None, min_length=1, max_length=2_000)


class WebEvidenceUse(EvidenceClaimSupport):
    """An opened public page selected during this turn's discovery."""

    source_kind: Literal["web"]
    evidence_id: str = Field(min_length=1, max_length=2_000)
    exact_quote: str | None = Field(default=None, min_length=1, max_length=2_000)


class SessionLineUse(EvidenceClaimSupport):
    """The reader's exact earlier wording Muse declares as support for its reply."""

    source_kind: Literal["session_line"]
    # A trivial fragment ("I ", "the ") would verify against nearly any line.
    quote: str = Field(min_length=12, max_length=2_000)


EvidenceUse = Annotated[
    BookEvidenceUse | MemoryEvidenceUse | WebEvidenceUse | SessionLineUse,
    Field(discriminator="source_kind"),
]


class MemoryCandidate(StrictModel):
    """One untrusted nomination containing only exact words from this user turn."""

    kind: Literal["memory_candidate"]
    text: str = Field(min_length=1, max_length=8_000)
    start_codepoint: int = Field(ge=0)
    end_codepoint: int = Field(ge=1)
    reason_code: MemoryCandidateReasonCode
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def offsets_match_text_length(self) -> Self:
        if self.end_codepoint - self.start_codepoint != len(self.text):
            raise ValueError("candidate offsets must match the nominated text length")
        return self


class NoMemoryCandidate(StrictModel):
    """A machine-checkable reason that this turn has no nomination."""

    kind: Literal["no_memory_candidate"]
    reason_code: NoMemoryCandidateReasonCode


MemoryNomination = Annotated[
    MemoryCandidate | NoMemoryCandidate,
    Field(discriminator="kind"),
]


class MuseCandidate(StrictModel):
    """A complete visible reply plus untrusted evidence and memory declarations."""

    reply: str = Field(min_length=1, max_length=20_000)
    evidence_uses: tuple[EvidenceUse, ...] = ()
    memory: MemoryNomination


def _has_bounded_span(fragment: str, reply: str) -> bool:
    start = r"(?<![\w.,:/’'-])" if fragment[:1].isdigit() else r"(?<![\w’'-])"
    end = r"(?![\w’'-]|[.,:/]\d)" if fragment[-1:].isdigit() else r"(?![\w’'-])"
    return bool(re.search(start + re.escape(fragment) + end, reply))


def supported_claim_errors(
    reply: str, evidence_uses: tuple[EvidenceUse, ...]
) -> list[dict[str, object]]:
    """Locate every mapping error without deciding whether a source entails it."""
    errors: list[dict[str, object]] = []
    for evidence_index, declared in enumerate(evidence_uses):
        path = f"evidence_uses[{evidence_index}].supported_claims"
        claims = declared.supported_claims
        if not claims:
            errors.append({
                "path": path, "value": [],
                "error": "supported_claims must contain at least one exact claim span.",
            })
        seen: set[str] = set()
        for claim_index, claim in enumerate(claims):
            problems = []
            if not claim.strip():
                problems.append("must not be blank")
            if claim in seen:
                problems.append("duplicates an earlier claim for this source")
            if claim not in reply:
                problems.append("is not an exact span from the current reply")
            if problems:
                error: dict[str, object] = {
                    "path": f"{path}[{claim_index}]", "value": claim,
                    "error": "supported_claims entry " + "; ".join(problems) + ".",
                }
                trimmed = claim.strip()
                span = claim.rstrip(".,;:!?")
                if claim not in reply and trimmed != claim and trimmed and _has_bounded_span(trimmed, reply):
                    error["suggested_span"] = trimmed
                    error["suggestion_reason"] = (
                        "Removing only outer whitespace yields this exact reply span. "
                        "Copy it explicitly if it maps the complete substantive claim; "
                        "the declaration is still invalid until corrected."
                    )
                elif (
                    claim not in reply
                    and span != claim
                    and span.strip()
                    and _has_bounded_span(span, reply)
                ):
                    error["suggested_span"] = span
                    error["suggestion_reason"] = (
                        "Removing only terminal punctuation yields this exact reply span. "
                        "A citation or Markdown marker may separate the text from its "
                        "sentence punctuation. Explicitly use this span if it maps the "
                        "complete substantive claim, or revise the reply and remap it."
                    )
                errors.append(error)
            seen.add(claim)
    return errors


def validate_supported_claims(reply: str, evidence_uses: tuple[EvidenceUse, ...]) -> None:
    """Check mapping structure, not whether the source entails the claim."""
    if supported_claim_errors(reply, evidence_uses):
        raise ValueError(
            "supported_claims must contain distinct, non-empty exact spans from the current reply"
        )
