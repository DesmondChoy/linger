"""Typed contracts for Serendipity search, comparison, and selection."""

from __future__ import annotations

from collections.abc import Collection
from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, model_validator

from apps.backend.contracts import BookScope, EvidenceItem
from src.linger.agents.contracts import StrictModel
from src.linger.agents.librarian.models import EvidenceStrengthDecision
from src.linger.contracts.connection_evidence import MemoryConnectionEvidence, WebConnectionEvidence


ConnectionIntent = Literal["find_connection", "gather_sources", "get_recommendation", "recall_memory"]
PresentationMode = Literal["direct", "ask_before_showing"]
SearchSourceKind = Literal["memory", "book_corpus", "web"]
DeclineReason = Literal[
    "no_permitted_evidence",
    "insufficient_evidence",
    "unsupported_cue",
    "generic_theme_match",
    "no_matching_memory",
    "no_clear_winner",
    "spoiler_boundary",
    "source_scope_violation",
    "unsafe_evidence",
    "retrieval_unavailable",
]
PolicyFlag = Literal[
    "contains_web_claim",
]
Disqualifier = Literal[
    "generic_only",
    "insufficient_support",
    "scope_risk",
    "privacy_risk",
    "spoiler_risk",
    "prompt_injection",
]


class ConnectionScope(StrictModel):
    """Trusted search grant attached by application code, never model output."""

    allowed_sources: tuple[SearchSourceKind, ...]
    book_scopes: tuple[BookScope, ...] = ()
    # Exact application-known public pages may be opened directly; None requires search leads.
    web_source_urls: tuple[str, ...] | None = None
    # Set when the reader asked about their reading without naming books: every
    # granted book is searched, so a narrow selection cannot skip the relevant one.
    search_all_granted_books: bool = False

    @model_validator(mode="after")
    def require_coherent_source_grant(self) -> Self:
        if len(self.allowed_sources) != len(set(self.allowed_sources)):
            raise ValueError("allowed search sources must be unique")
        if "book_corpus" in self.allowed_sources and not self.book_scopes:
            raise ValueError("book-corpus access requires at least one book scope")
        if self.book_scopes and "book_corpus" not in self.allowed_sources:
            raise ValueError("book scopes require book-corpus access")
        if self.search_all_granted_books and not self.book_scopes:
            raise ValueError("searching all granted books requires a book grant")
        if self.web_source_urls is not None:
            if len(self.web_source_urls) != len(set(self.web_source_urls)):
                raise ValueError("public source URLs must be unique")
            if any(not url.startswith(("https://", "http://")) for url in self.web_source_urls):
                raise ValueError("public sources require HTTP URLs")
            if self.web_source_urls and "web" not in self.allowed_sources:
                raise ValueError("public sources require a web grant")
        identities = tuple(
            (scope.work_id, scope.book_version_id) for scope in self.book_scopes
        )
        if len(identities) != len(set(identities)):
            raise ValueError("book scopes must identify unique revisions")
        return self


class ConnectionDiscoveryInput(StrictModel):
    """The dynamic search task and authority granted to Serendipity."""

    cue: str = Field(min_length=1, max_length=8_000)
    intent: ConnectionIntent
    presentation: PresentationMode
    scope: ConnectionScope




ConnectionEvidence = Annotated[
    EvidenceItem | MemoryConnectionEvidence | WebConnectionEvidence,
    Field(discriminator="source_kind"),
]


class InternalSearchResult(StrictModel):
    """Eligible book records returned by one bounded Librarian search."""

    outcome: Literal["evidence_found", "no_evidence", "retrieval_unavailable"]
    evidence: tuple[EvidenceItem, ...] = ()
    judgement: EvidenceStrengthDecision | None

    @model_validator(mode="after")
    def outcome_matches_evidence(self) -> Self:
        if self.outcome == "evidence_found" and not self.evidence:
            raise ValueError("evidence_found requires evidence")
        if self.outcome != "evidence_found" and self.evidence:
            raise ValueError(f"{self.outcome} cannot include evidence")
        if self.outcome == "retrieval_unavailable":
            if self.judgement is not None:
                raise ValueError("retrieval failure cannot include a judgement")
        else:
            if self.judgement is None:
                raise ValueError("completed book search requires a judgement")
            if set(self.judgement.relevant_evidence_ids) != {
                item.evidence_id for item in self.evidence
            }:
                raise ValueError("book evidence must match the judge's selection")
        return self


class MemorySearchResult(StrictModel):
    """Eligible active memories returned by one bounded account-scoped search."""

    outcome: Literal["evidence_found", "no_evidence"]
    evidence: tuple[MemoryConnectionEvidence, ...] = ()

    @model_validator(mode="after")
    def outcome_matches_evidence(self) -> Self:
        if self.outcome == "evidence_found" and not self.evidence:
            raise ValueError("evidence_found requires evidence")
        if self.outcome == "no_evidence" and self.evidence:
            raise ValueError("no_evidence cannot include evidence")
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
            and self.reflective_value != "low"
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
        strengths = tuple(candidate.rubric.ranking_key for candidate in self.shortlist)
        if any(left < right for left, right in zip(strengths, strengths[1:])):
            raise ValueError("shortlist ranks must follow the anchored rubric order")
        if strengths[0] == strengths[1]:
            raise ValueError("the rank-one candidate must be a clear rubric winner")
        if self.selected_candidate_id != self.shortlist[0].candidate_id:
            raise ValueError("the selected candidate must be the rank-one candidate")
        if any(not candidate.rubric.eligible for candidate in self.shortlist):
            raise ValueError("a proposal shortlist may contain only eligible candidates")
        cited = set().union(
            *(frozenset(candidate.evidence_ids) for candidate in self.shortlist)
        )
        if len(cited) < 2:
            raise ValueError(
                "a shortlist resting on one record cannot compare two connections"
            )
        return self

    @property
    def selected_candidate(self) -> ConnectionCandidate:
        return self.shortlist[0]


class ConnectionDecline(StrictModel):
    """A first-class decision that no eligible candidate should be surfaced."""

    status: Literal["decline"] = "decline"
    reason: DeclineReason
    safe_next_step: str = Field(min_length=1, max_length=500)


class MemoryRecall(StrictModel):
    """The reader's own earlier records on what the cue asks about."""

    status: Literal["recall"] = "recall"
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=3)
    relevance_note: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def require_unique_evidence(self) -> Self:
        if any(not evidence_id or len(evidence_id) > 200 for evidence_id in self.evidence_ids):
            raise ValueError("recalled evidence IDs must be non-empty and bounded")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("recalled evidence IDs must be unique")
        return self


class PublicSourceCheck(StrictModel):
    """Whether one supplied public URL answers a source the reader requested."""

    url: str = Field(min_length=1, max_length=2_000)
    requested_as: str | None = Field(
        default=None, min_length=1, max_length=1_000,
        description=(
            "An exact span from cue naming the public source the reader requests, "
            "including an indirect reference such as 'that essay'. Null when the "
            "reader did not request this permitted source."
        ),
    )


class SourceBundle(StrictModel):
    """Records for every source the reader named, gathered without choosing among them."""

    status: Literal["gathered"] = "gathered"
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=12)
    unfound_sources: tuple[
        Annotated[str, Field(min_length=1, max_length=200)], ...
    ] = Field(
        default=(),
        max_length=6,
        description=(
            "The reader's own names for requested sources that no returned record "
            "supports, so the reply can say plainly what could not be found."
        ),
    )
    relevance_note: str = Field(min_length=1, max_length=500)
    public_source_checks: tuple[PublicSourceCheck, ...] = Field(
        default=(),
        description=(
            "One check for every URL in scope.web_source_urls. Identify which are "
            "requested; permission alone does not require opening a source."
        ),
    )

    @model_validator(mode="after")
    def require_unique_evidence(self) -> Self:
        if any(not evidence_id or len(evidence_id) > 2_000 for evidence_id in self.evidence_ids):
            raise ValueError("gathered evidence IDs must be non-empty and bounded")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("gathered evidence IDs must be unique")
        if len(self.unfound_sources) != len(set(self.unfound_sources)):
            raise ValueError("unfound sources must be unique")
        urls = [check.url for check in self.public_source_checks]
        if len(urls) != len(set(urls)):
            raise ValueError("public source checks must identify unique URLs")
        return self


def public_source_check_errors(
    bundle: SourceBundle, task: ConnectionDiscoveryInput, attempted_urls: Collection[str],
) -> list[str]:
    """Keep permission distinct from a requested source and verify real open attempts."""
    expected = set(task.scope.web_source_urls or ())
    supplied = {check.url for check in bundle.public_source_checks}
    errors = []
    if supplied != expected:
        errors.append(
            "public_source_checks must account for every supplied public URL exactly once. "
            f"Missing: {sorted(expected - supplied)}; unexpected: {sorted(supplied - expected)}. "
            "For a requested source, copy its exact reader reference from cue into requested_as; "
            "open it with get_page before returning if it has not been attempted. "
            "Use null for a permitted source the reader did not request."
        )
    unattempted = []
    for index, check in enumerate(bundle.public_source_checks):
        if check.requested_as is None:
            continue
        if not check.requested_as.strip() or check.requested_as not in task.cue:
            errors.append(
                f"public_source_checks[{index}].requested_as must be a non-empty exact span "
                "from cue naming the requested public source. Do not invent or rewrite the reference."
            )
        if check.url in expected and check.url not in attempted_urls:
            unattempted.append(check.url)
    if unattempted:
        errors.append(
            "Open every requested supplied page with get_page before returning gathered or "
            f"unfound sources. These requested pages have not been attempted: {sorted(unattempted)}. "
            "A page that was not opened is not a failed search."
        )
    return errors


SerendipityResponse = ConnectionProposal | ConnectionDecline | MemoryRecall | SourceBundle
SERENDIPITY_RESPONSE_ADAPTER = TypeAdapter(
    Annotated[SerendipityResponse, Field(discriminator="status")]
)


class ConnectionExplorationResult(StrictModel):
    """Validated Serendipity decision plus its request-local evidence bundle."""

    decision: Annotated[SerendipityResponse, Field(discriminator="status")]
    evidence: tuple[ConnectionEvidence, ...] = ()
