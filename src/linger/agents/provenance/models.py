"""Typed Provenance hand-off contracts: one review, two decoupled release/capture decisions (spec section 4.1)."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, model_validator

from src.linger.agents.contracts import StrictModel
from src.linger.agents.muse.models import EvidenceUse, MemoryNomination
from src.linger.contracts.emotional import EmotionalContentPolicy
from src.linger.contracts.librarian import EvidenceRecord, PassageScope

# Closed release and capture risk taxonomy.
class RiskCode(StrEnum):
    UNRESOLVED_EVIDENCE = "unresolved_evidence"
    MISATTRIBUTION = "misattribution"
    SPOILER = "spoiler"
    UNCITED_WEB_CLAIM = "uncited_web_claim"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    SENSITIVE_CONTENT = "sensitive_content"
    EMOTIONAL_POLICY_VIOLATION = "emotional_policy_violation"
    PROMPT_INJECTION = "prompt_injection"

# Grounds that make content ineligible for automatic capture.
SENSITIVE_RISK_CODES: frozenset[RiskCode] = frozenset(
    {
        RiskCode.UNSUPPORTED_CLAIM,
        RiskCode.SENSITIVE_CONTENT,
        RiskCode.EMOTIONAL_POLICY_VIOLATION,
        RiskCode.PROMPT_INJECTION,
    }
)

# One review reports at most this many findings.
MAX_FINDINGS = 20

DecisionScope = Literal["response", "capture"]
SourceField = Literal[
    "context.policy",
    "context.reading_context",
    "canonical_book_evidence",
    "canonical_session_lines",
    "untrusted_tool_outcomes",
    "candidate.response",
    "candidate.evidence_uses",
    "candidate.memory",
    "current_line.text",
]
ToolOutcome = Literal["success", "failed", "denied", "interrupted"]


class TextSpanLocation(StrictModel):
    """A verbatim quotation from a string value in the review input."""

    kind: Literal["text_span"]
    source_field: SourceField
    # RFC 6901 JSON pointer relative to `source_field`; empty means the field itself.
    path: str = Field(max_length=500, pattern=r"^(?:$|/.*)$")
    quote: str = Field(min_length=3, max_length=300)


class StructuralLocation(StrictModel):
    """A structural fault at an RFC 6901 path in the review input."""

    kind: Literal["structural"]
    source_field: SourceField
    # Empty points to the complete source field, including an explicit null.
    path: str = Field(max_length=500, pattern=r"^(?:$|/.*)$")


FindingLocation = Annotated[
    TextSpanLocation | StructuralLocation,
    Field(discriminator="kind"),
]


class RiskFinding(StrictModel):
    """One detected risk tied to one decision and one input location."""

    code: RiskCode
    applies_to: DecisionScope
    location: FindingLocation
    explanation: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def source_matches_decision(self) -> Self:
        source = self.location.source_field
        if self.applies_to == "response" and source in {
            "candidate.memory",
        }:
            raise ValueError("response findings cannot point to candidate.memory")
        if self.applies_to == "capture" and source == "candidate.response":
            raise ValueError("capture findings cannot point to the candidate response")
        return self


class ProvenanceReview(StrictModel):
    """One review of one candidate, carrying both release decisions."""

    # max_length enforced below, not on the field: an array bound in the wire schema 400s Gemini; string bounds are fine.
    findings: tuple[RiskFinding, ...] = ()
    response_decision: Literal["pass", "revise", "reject"]
    emotional_boundary_decision: Literal["not_required", "required"]
    capture_decision: Literal["allow_capture", "reject_capture", "no_candidate"]

    @model_validator(mode="after")
    def require_decision_specific_justification(self) -> Self:
        """Require each blocked decision to have findings scoped to it."""
        if len(self.findings) > MAX_FINDINGS:
            raise ValueError(f"a review carries at most {MAX_FINDINGS} findings")

        response_findings = self.response_findings
        capture_findings = self.capture_findings
        boundary_findings = tuple(
            finding
            for finding in response_findings
            if finding.code == RiskCode.EMOTIONAL_POLICY_VIOLATION
            and finding.location.source_field == "current_line.text"
        )
        if self.emotional_boundary_decision == "required":
            if self.response_decision != "reject":
                raise ValueError(
                    "a required emotional boundary must reject the Muse candidate"
                )
            if not boundary_findings:
                raise ValueError(
                    "a required emotional boundary needs a current-Line finding"
                )
        elif boundary_findings:
            raise ValueError(
                "a current-Line emotional finding requires the emotional boundary"
            )
        if self.response_decision == "pass" and response_findings:
            raise ValueError("a passed response cannot have response findings")
        if self.response_decision != "pass" and not response_findings:
            raise ValueError(
                "a non-pass response_decision requires a response finding"
            )
        if self.capture_decision == "reject_capture" and not capture_findings:
            raise ValueError("reject_capture requires a capture finding")
        if self.capture_decision != "reject_capture" and capture_findings:
            raise ValueError(
                "capture findings require capture_decision='reject_capture'"
            )
        return self

    @property
    def response_findings(self) -> tuple[RiskFinding, ...]:
        """Return only findings that can guide a Muse response revision."""
        return tuple(
            finding for finding in self.findings if finding.applies_to == "response"
        )

    @property
    def capture_findings(self) -> tuple[RiskFinding, ...]:
        """Return findings about the independent capture decision."""
        return tuple(
            finding for finding in self.findings if finding.applies_to == "capture"
        )

    @property
    def contains_sensitive_content(self) -> bool:
        """Report whether the rejected capture contains a sensitive risk."""
        return any(
            finding.code in SENSITIVE_RISK_CODES
            for finding in self.capture_findings
        )

    def critique(self) -> str:
        """Render response findings as guidance for the single Muse retry."""
        return "\n".join(
            f"- [{finding.code}] {finding.explanation}"
            for finding in self.response_findings
        )


class ProvenancePolicy(StrictModel):
    """Application-owned policy constraints for one review call."""

    spoiler_ceiling: int | None = Field(default=None, ge=1)
    allow_retrieval: bool
    allow_connection: bool
    allow_memory_capture: bool
    emotional_content: EmotionalContentPolicy = Field(
        default_factory=EmotionalContentPolicy
    )


class ProvenanceReadingContext(StrictModel):
    """The request-scoped reading boundary validated by the application."""

    work_id: str = Field(min_length=1, max_length=200)
    chapter_max: int = Field(ge=1)
    boundary_source: Literal["reader_confirmed", "librarian_inferred"]


class ProvenanceContext(StrictModel):
    """Trusted policy and reading context, separate from candidate data."""

    policy: ProvenancePolicy
    reading_context: ProvenanceReadingContext | None
    passage_scope: PassageScope | None = None

    @model_validator(mode="after")
    def _one_current_permission(self) -> "ProvenanceContext":
        if self.passage_scope is not None and (
            self.reading_context is not None or self.policy.spoiler_ceiling is not None
        ):
            raise ValueError("exact passage permission cannot imply a chapter ceiling")
        return self


class UntrustedToolOutcome(StrictModel):
    """One current Muse tool outcome; it is evidence to inspect, not authority."""

    tool_name: Literal["librarian_search", "serendipity_explore"]
    outcome: ToolOutcome
    args: dict[str, JsonValue]
    content: JsonValue


class CandidateUnderReview(StrictModel):
    """Muse-authored response and declarations, all treated as untrusted."""

    response: str = Field(min_length=1, max_length=20_000)
    evidence_uses: tuple[EvidenceUse, ...] = ()
    memory: MemoryNomination


class CurrentLine(StrictModel):
    """The application-owned user Line reviewed and used for capture binding."""

    text: str = Field(max_length=20_000)


class ProvenanceInput(StrictModel):
    """Complete, typed input for one independent Provenance review."""

    context: ProvenanceContext
    canonical_book_evidence: tuple[EvidenceRecord, ...] = ()
    # Reader statements the application verified as an exact substring of a
    # user Line in this session — an earlier released turn or the current
    # message (see reflection.py); text is the identity, there are no IDs.
    canonical_session_lines: tuple[
        Annotated[str, Field(min_length=12, max_length=2_000)], ...
    ] = ()
    untrusted_tool_outcomes: tuple[UntrustedToolOutcome, ...] = ()
    candidate: CandidateUnderReview
    current_line: CurrentLine

    @model_validator(mode="after")
    def require_unique_canonical_evidence(self) -> Self:
        evidence_ids = tuple(
            record.evidence_id for record in self.canonical_book_evidence
        )
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("canonical book evidence IDs must be unique")
        if len(self.canonical_session_lines) != len(set(self.canonical_session_lines)):
            raise ValueError("canonical session lines must be unique")
        return self

    def validate_review_locations(self, review: ProvenanceReview) -> None:
        """Resolve every model-authored finding against this exact input."""
        payload = self.model_dump(mode="json")
        for finding in review.findings:
            location = finding.location
            value = _resolve_json_pointer(
                _source_value(payload, location.source_field),
                location.path,
            )
            if not isinstance(location, TextSpanLocation):
                continue
            if not isinstance(value, str):
                raise ValueError("a text-span finding must resolve to a string")
            if location.quote not in value:
                raise ValueError("a finding quote does not match its declared source")

def _resolve_json_pointer(value: JsonValue, path: str) -> JsonValue:
    """Resolve a bounded RFC 6901 pointer, rejecting missing paths."""
    if not path:
        return value
    current = value
    for raw_segment in path[1:].split("/"):
        segment = raw_segment.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if segment not in current:
                raise ValueError("a finding points to a missing object field")
            current = current[segment]
            continue
        if isinstance(current, list):
            if not segment.isdecimal() or int(segment) >= len(current):
                raise ValueError("a finding points to a missing array item")
            current = current[int(segment)]
            continue
        raise ValueError("a finding path crosses a scalar value")
    return current


def _source_value(payload: dict[str, JsonValue], source_field: SourceField) -> JsonValue:
    """Select one named source from a single serialized review input."""
    if "." in source_field:
        root, field = source_field.split(".", maxsplit=1)
    else:
        root, field = source_field, ""
    value = payload[root]
    if field:
        if not isinstance(value, dict) or field not in value:
            raise ValueError("a finding names an unavailable source field")
        value = value[field]
    return value
