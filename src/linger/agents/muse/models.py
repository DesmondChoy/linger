"""Typed Muse output used by the application release and capture boundaries."""

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
]


class EvidenceUse(StrictModel):
    """One book-corpus record Muse declares as support for its reply."""

    source_kind: Literal["book_corpus"]
    evidence_id: str = Field(min_length=1, max_length=200)
    source_location: str = Field(min_length=1, max_length=500)
    exact_quote: str | None = Field(default=None, min_length=1, max_length=2_000)


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
