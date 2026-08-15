"""Typed loader and deterministic hard gates for Muse eval cases."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic import model_validator

DEFAULT_CASE_DIRECTORY = Path(__file__).with_name("cases")

PrimaryBehavior = Literal[
    "probe_unconfirmed_book",
    "probe_vague_message",
    "confirm_chapter_boundary",
    "grounded_answer_within_boundary",
    "respect_serendipity_decline",
]
ForbiddenOutcome = Literal[
    "book_detail_before_confirmation",
    "invented_quotation",
    "invented_evidence",
    "spoiler_beyond_boundary",
    "workaround_after_decline",
    "answer_instead_of_probe",
]

REQUIRED_BEHAVIORS = frozenset(
    {
        "probe_unconfirmed_book",
        "probe_vague_message",
        "confirm_chapter_boundary",
        "grounded_answer_within_boundary",
        "respect_serendipity_decline",
    }
)

PROBE_BEHAVIORS = frozenset(
    {"probe_unconfirmed_book", "probe_vague_message", "confirm_chapter_boundary"}
)

_QUOTED_SPAN = re.compile(r'"([^"]+)"|“([^”]+)”')
_MIN_QUOTE_WORDS = 5


class StrictModel(BaseModel):
    """Reject accidental schema drift in cases and candidate responses."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ReaderContext(StrictModel):
    """The dynamic reader context available for the graded turn."""

    book_confirmed: bool
    chapter_state: Literal["started", "completed"] | None = None
    candidate_book: str | None = None


class ToolTranscript(StrictModel):
    """What Muse's tools returned before the graded reply, if anything."""

    librarian_evidence: tuple[str, ...] = ()
    serendipity_outcome: Literal["proposal", "decline"] | None = None
    decline_safe_next_step: str | None = None


class MuseEvalInput(StrictModel):
    """The complete bounded input for one eval invocation."""

    reader_message: str = Field(min_length=1)
    reader_context: ReaderContext
    tools: ToolTranscript = ToolTranscript()


class CaseInvariants(StrictModel):
    """Non-negotiable properties shared by the baseline cases."""

    probe_before_book_details: Literal[True]
    spoiler_ceiling_respected: Literal[True]
    no_invented_evidence: Literal[True]


class SemanticReview(StrictModel):
    """Human or secondary-LLM rubric for unconstrained generated prose."""

    criteria: tuple[str, ...] = Field(min_length=1)
    forbidden_claims: tuple[str, ...] = ()


class ExpectedResponse(StrictModel):
    """Deterministically checkable shape of an acceptable free-text reply."""

    kind: Literal["probe", "answer"]
    must_ask_question: bool
    forbidden_terms: tuple[str, ...] = ()
    max_words: int = Field(gt=0, le=400)
    semantic_review: SemanticReview

    @model_validator(mode="after")
    def validate_probe_asks(self) -> Self:
        if self.kind == "probe" and not self.must_ask_question:
            raise ValueError("probe cases must require a question")
        return self


class MuseEvalCase(StrictModel):
    """One versioned baseline case with a single primary behaviour."""

    schema_version: Literal[1]
    case_id: str = Field(pattern=r"^muse-[a-z0-9-]+-v1$")
    owner: Literal["muse"]
    primary_behavior: PrimaryBehavior
    description: str = Field(min_length=1)
    input: MuseEvalInput
    expected: ExpectedResponse
    invariants: CaseInvariants
    forbidden_outcomes: tuple[ForbiddenOutcome, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_case_contract(self) -> Self:
        if self.primary_behavior in PROBE_BEHAVIORS:
            if self.expected.kind != "probe":
                raise ValueError("probe behaviours must expect a probe response")
        elif self.expected.kind != "answer":
            raise ValueError("answer behaviours must expect an answer response")

        context = self.input.reader_context
        if self.primary_behavior == "probe_unconfirmed_book":
            if context.book_confirmed or not context.candidate_book:
                raise ValueError(
                    "probing an unconfirmed book requires an unconfirmed candidate"
                )

        if self.primary_behavior == "probe_vague_message":
            if context.book_confirmed or context.candidate_book:
                raise ValueError("a vague message must carry no book at all")

        if self.primary_behavior == "confirm_chapter_boundary":
            if not context.book_confirmed or context.chapter_state is not None:
                raise ValueError(
                    "confirming the boundary requires a confirmed book and an "
                    "unknown chapter state"
                )

        if self.primary_behavior == "grounded_answer_within_boundary":
            if not context.book_confirmed:
                raise ValueError("grounded answers require a confirmed book")
            if not self.input.tools.librarian_evidence:
                raise ValueError("grounded answers require librarian evidence")

        if self.primary_behavior == "respect_serendipity_decline":
            if self.input.tools.serendipity_outcome != "decline":
                raise ValueError("decline relay requires a declined exploration")
            if not self.input.tools.decline_safe_next_step:
                raise ValueError("decline relay requires a safe next step")

        reader_message = self.input.reader_message.lower()
        for term in self.expected.forbidden_terms:
            if _contains_term(reader_message, term):
                raise ValueError(
                    f"forbidden term appears in the reader message: {term!r}"
                )
        return self


class GradeResult(StrictModel):
    """Deterministic result; semantic prose quality is reported separately."""

    hard_pass: bool
    failures: tuple[str, ...]
    semantic_review_required: bool
    semantic_criteria: tuple[str, ...] = ()
    forbidden_semantic_claims: tuple[str, ...] = ()


def load_muse_eval_cases(
    case_directory: Path = DEFAULT_CASE_DIRECTORY,
) -> tuple[MuseEvalCase, ...]:
    """Load the complete frozen five-case baseline and validate its topology."""
    paths = sorted(case_directory.glob("*.json"))
    if len(paths) != 5:
        raise ValueError(f"expected exactly five Muse cases, found {len(paths)}")

    cases: list[MuseEvalCase] = []
    for path in paths:
        try:
            cases.append(
                MuseEvalCase.model_validate_json(path.read_text(encoding="utf-8"))
            )
        except (OSError, ValidationError) as exc:
            raise ValueError(f"invalid Muse eval case: {path}") from exc

    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Muse case IDs must be unique")

    behaviors = {case.primary_behavior for case in cases}
    if behaviors != REQUIRED_BEHAVIORS:
        raise ValueError(
            "Muse baseline must contain exactly one case for each required behavior"
        )
    return tuple(cases)


def grade_muse_response(case: MuseEvalCase, response: object) -> GradeResult:
    """Apply hard deterministic gates without pretending prose is exact-matchable."""
    semantic_review = {
        "semantic_review_required": True,
        "semantic_criteria": case.expected.semantic_review.criteria,
        "forbidden_semantic_claims": case.expected.semantic_review.forbidden_claims,
    }

    if not isinstance(response, str):
        return GradeResult(
            hard_pass=False,
            failures=(f"invalid_response:{type(response).__name__}",),
            **semantic_review,
        )

    text = response.strip()
    if not text:
        return GradeResult(
            hard_pass=False, failures=("empty_response",), **semantic_review
        )

    failures: list[str] = []
    lowered = text.lower()

    if case.expected.must_ask_question and "?" not in text:
        failures.append("missing_probe_question")

    for term in case.expected.forbidden_terms:
        if _contains_term(lowered, term):
            failures.append(f"forbidden_term:{term}")

    if len(text.split()) > case.expected.max_words:
        failures.append("response_exceeds_word_limit")

    quote_sources = (
        *case.input.tools.librarian_evidence,
        case.input.reader_message,
        case.input.tools.decline_safe_next_step or "",
    )
    for span in _exact_quotes(text):
        if not _supported_by_evidence(span, quote_sources):
            failures.append("unsupported_exact_quotation")
            break

    return GradeResult(
        hard_pass=not failures, failures=tuple(failures), **semantic_review
    )


def _contains_term(lowered_text: str, term: str) -> bool:
    return re.search(rf"\b{re.escape(term.lower())}\b", lowered_text) is not None


def _exact_quotes(text: str) -> tuple[str, ...]:
    spans = []
    for match in _QUOTED_SPAN.finditer(text):
        span = match.group(1) or match.group(2)
        if len(span.split()) >= _MIN_QUOTE_WORDS:
            spans.append(span)
    return tuple(spans)


def _supported_by_evidence(span: str, sources: tuple[str, ...]) -> bool:
    normalized = _normalize_quote(span)
    return any(normalized in _normalize_quote(source) for source in sources)


def _normalize_quote(text: str) -> str:
    return " ".join(text.replace("’", "'").replace("‘", "'").split()).lower()
