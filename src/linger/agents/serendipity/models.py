"""Typed contracts for Serendipity search, comparison, and selection."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, model_validator

from src.linger.agents.contracts import StrictModel


ConnectionIntent = Literal["find_connection", "get_recommendation"]
PresentationMode = Literal["direct", "ask_before_showing"]
SearchSourceKind = Literal["authorised_memory", "book_corpus", "web"]
InternalSourceKind = Literal["authorised_memory", "book_corpus"]
DeclineReason = Literal[
    "no_permitted_evidence",
    "insufficient_evidence",
    "unsupported_cue",
    "generic_theme_match",
    "no_clear_winner",
    "spoiler_boundary",
    "source_scope_violation",
    "unsafe_evidence",
    "retrieval_unavailable",
]
PolicyFlag = Literal[
    "contains_web_claim",
    "uses_authorised_memory",
    "reader_consent_required",
]
Disqualifier = Literal[
    "generic_only",
    "insufficient_support",
    "scope_risk",
    "privacy_risk",
    "spoiler_risk",
    "prompt_injection",
]


class BookEvidenceScope(StrictModel):
    """One book revision Serendipity may ask Librarian to search."""

    work_id: str = Field(min_length=1, max_length=200)
    book_version_id: str = Field(min_length=1, max_length=200)
    chapter_max: int = Field(ge=1)


class PhotographCue(StrictModel):
    """A user-supplied photograph that forms part of the current cue."""

    asset_id: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=8_000)


class ConnectionScope(StrictModel):
    """Trusted search grant attached by application code, never model output."""

    allowed_sources: tuple[SearchSourceKind, ...]
    book_scopes: tuple[BookEvidenceScope, ...] = ()

    @model_validator(mode="after")
    def require_coherent_source_grant(self) -> Self:
        if not self.allowed_sources:
            raise ValueError("at least one search source must be permitted")
        if len(self.allowed_sources) != len(set(self.allowed_sources)):
            raise ValueError("allowed search sources must be unique")
        if "book_corpus" in self.allowed_sources and not self.book_scopes:
            raise ValueError("book-corpus access requires at least one book scope")
        if self.book_scopes and "book_corpus" not in self.allowed_sources:
            raise ValueError("book scopes require book-corpus access")
        identities = tuple(
            (scope.work_id, scope.book_version_id) for scope in self.book_scopes
        )
        if len(identities) != len(set(identities)):
            raise ValueError("book scopes must identify unique revisions")
        return self


class ConnectionDiscoveryInput(StrictModel):
    """The dynamic search task and authority granted to Serendipity."""

    request_id: str = Field(min_length=1, max_length=200)
    cue: str = Field(min_length=1, max_length=2_000)
    photograph: PhotographCue | None = None
    intent: ConnectionIntent
    presentation: PresentationMode
    scope: ConnectionScope


class BookConnectionEvidence(StrictModel):
    """One exact, spoiler-bounded canonical book record from Librarian."""

    source_kind: Literal["book_corpus"] = "book_corpus"
    evidence_id: str = Field(min_length=1, max_length=2_000)
    source_title: str = Field(min_length=1, max_length=500)
    work_id: str = Field(min_length=1, max_length=200)
    book_version_id: str = Field(min_length=1, max_length=200)
    chapter: int = Field(ge=1)
    location: str = Field(min_length=1, max_length=500)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_lines: tuple[int, int]
    excerpt: str = Field(min_length=1, max_length=8_000)
    trust_level: Literal["canonical"] = "canonical"

    @model_validator(mode="after")
    def require_valid_source_lines(self) -> Self:
        start, end = self.source_lines
        if start < 1 or end < start:
            raise ValueError("source lines must be a positive inclusive range")
        return self


class MemoryConnectionEvidence(StrictModel):
    """One active reader-authored memory resolved by Librarian."""

    source_kind: Literal["authorised_memory"] = "authorised_memory"
    evidence_id: str = Field(min_length=1, max_length=2_000)
    excerpt: str = Field(min_length=1, max_length=8_000)
    capture_type: Literal["explicit", "automatic", "correction"]
    recorded_at: str = Field(min_length=1, max_length=100)
    trust_level: Literal["reader_authored"] = "reader_authored"


class WebConnectionEvidence(StrictModel):
    """One retrievable public-web record returned by Exa."""

    source_kind: Literal["web"] = "web"
    evidence_id: str = Field(min_length=1, max_length=2_000)
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1, max_length=2_000)
    excerpt: str = Field(min_length=1, max_length=8_000)
    trust_level: Literal["external"] = "external"


ConnectionEvidence = Annotated[
    BookConnectionEvidence | MemoryConnectionEvidence | WebConnectionEvidence,
    Field(discriminator="source_kind"),
]


class InternalSearchResult(StrictModel):
    """Several eligible internal records returned by one Librarian search."""

    query: str = Field(min_length=1, max_length=2_000)
    searched_sources: tuple[InternalSourceKind, ...]
    outcome: Literal["evidence_found", "no_evidence", "partial_failure"]
    evidence: tuple[ConnectionEvidence, ...] = ()
    unavailable_sources: tuple[InternalSourceKind, ...] = ()

    @model_validator(mode="after")
    def outcome_matches_evidence(self) -> Self:
        if not self.searched_sources:
            raise ValueError("an internal search requires at least one source")
        if len(self.searched_sources) != len(set(self.searched_sources)):
            raise ValueError("searched internal sources must be unique")
        if any(
            item.source_kind not in self.searched_sources
            or item.source_kind == "web"
            for item in self.evidence
        ):
            raise ValueError(
                "Librarian results must match the searched internal sources"
            )
        if self.outcome == "evidence_found" and not self.evidence:
            raise ValueError("evidence_found requires evidence")
        if self.outcome == "no_evidence" and self.evidence:
            raise ValueError("no_evidence cannot include evidence")
        if self.outcome == "partial_failure" and not self.unavailable_sources:
            raise ValueError("partial_failure requires an unavailable source")
        if set(self.unavailable_sources) - set(self.searched_sources):
            raise ValueError("unavailable sources must have been searched")
        return self


class CandidateRubric(StrictModel):
    """Anchored ordinal comparison; these values are not probabilities."""

    cue_fit: Literal["direct", "partial", "weak"]
    reflective_value: Literal["high", "medium", "low"]
    safety: Literal["clear", "review", "ineligible"]
    disqualifiers: tuple[Disqualifier, ...] = ()

    @property
    def eligible(self) -> bool:
        return (
            self.cue_fit != "weak"
            and self.safety == "clear"
            and not self.disqualifiers
        )

    @property
    def ranking_key(self) -> tuple[int, int, int]:
        """Lexical ordinal strength; this is not a confidence score."""
        return (
            {"direct": 2, "partial": 1, "weak": 0}[self.cue_fit],
            {"high": 2, "medium": 1, "low": 0}[self.reflective_value],
            {"clear": 2, "review": 1, "ineligible": 0}[self.safety],
        )

    @model_validator(mode="after")
    def require_unique_disqualifiers(self) -> Self:
        if len(self.disqualifiers) != len(set(self.disqualifiers)):
            raise ValueError("candidate disqualifiers must be unique")
        return self


class ConnectionCandidate(StrictModel):
    """One shortlisted interpretation compared against the other candidates."""

    candidate_id: str = Field(pattern=r"^candidate-[a-z0-9-]+$", max_length=100)
    rank: int = Field(ge=1, le=3)
    tentative_claim: str = Field(min_length=1, max_length=1_000)
    evidence_ids: tuple[str, ...]
    shared_structure: str = Field(min_length=1, max_length=1_000)
    meaningful_difference: str = Field(min_length=1, max_length=1_000)
    interpretation: str = Field(min_length=1, max_length=2_000)
    rubric: CandidateRubric
    comparison_note: str = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def require_unique_evidence(self) -> Self:
        if not self.evidence_ids:
            raise ValueError("a candidate requires cited evidence")
        if any(not evidence_id or len(evidence_id) > 2_000 for evidence_id in self.evidence_ids):
            raise ValueError("candidate evidence IDs must be non-empty and bounded")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("candidate evidence IDs must be unique")
        return self


class ConnectionProposal(StrictModel):
    """The winning connection plus the shortlist that justified its selection."""

    status: Literal["proposal"] = "proposal"
    shortlist: tuple[ConnectionCandidate, ...] = Field(min_length=2, max_length=3)
    selected_candidate_id: str = Field(min_length=1, max_length=100)
    uncertainty: Literal["low", "medium", "high"]
    presentation: PresentationMode
    suggested_follow_up: str = Field(min_length=1, max_length=500)
    policy_flags: tuple[PolicyFlag, ...] = ()

    @model_validator(mode="after")
    def require_ranked_eligible_winner(self) -> Self:
        if len(self.policy_flags) != len(set(self.policy_flags)):
            raise ValueError("proposal policy flags must be unique")
        candidate_ids = tuple(candidate.candidate_id for candidate in self.shortlist)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("shortlisted candidate IDs must be unique")
        claims = tuple(
            " ".join(candidate.tentative_claim.casefold().split())
            for candidate in self.shortlist
        )
        if len(claims) != len(set(claims)):
            raise ValueError(
                "shortlisted candidates must express distinct connections"
            )
        ranks = tuple(candidate.rank for candidate in self.shortlist)
        if ranks != tuple(range(1, len(self.shortlist) + 1)):
            raise ValueError("shortlist must be ordered by unique contiguous ranks")
        strengths = tuple(candidate.rubric.ranking_key for candidate in self.shortlist)
        if any(left < right for left, right in zip(strengths, strengths[1:])):
            raise ValueError("shortlist ranks must follow the anchored rubric order")
        selected = next(
            (
                candidate
                for candidate in self.shortlist
                if candidate.candidate_id == self.selected_candidate_id
            ),
            None,
        )
        if selected is None or selected.rank != 1:
            raise ValueError("the selected candidate must be the rank-one candidate")
        if any(not candidate.rubric.eligible for candidate in self.shortlist):
            raise ValueError("a proposal shortlist may contain only eligible candidates")
        return self

    @property
    def selected_candidate(self) -> ConnectionCandidate:
        return next(
            candidate
            for candidate in self.shortlist
            if candidate.candidate_id == self.selected_candidate_id
        )


class ConnectionDecline(StrictModel):
    """A first-class decision that no eligible candidate should be surfaced."""

    status: Literal["decline"] = "decline"
    reason: DeclineReason
    safe_next_step: str = Field(min_length=1, max_length=500)
    shortlist: tuple[ConnectionCandidate, ...] = Field(default=(), max_length=3)


SerendipityResponse = ConnectionProposal | ConnectionDecline
SERENDIPITY_RESPONSE_ADAPTER = TypeAdapter(
    Annotated[SerendipityResponse, Field(discriminator="status")]
)


class ConnectionExplorationResult(StrictModel):
    """Validated Serendipity decision plus its request-local evidence bundle."""

    decision: Annotated[SerendipityResponse, Field(discriminator="status")]
    evidence: tuple[ConnectionEvidence, ...] = ()
