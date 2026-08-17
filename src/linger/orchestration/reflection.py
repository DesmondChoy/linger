"""Application-owned Muse-to-Provenance release flow."""

import json
from dataclasses import dataclass
from typing import Any, Literal, Mapping

import logfire
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ToolReturnPart
from pydantic_core import to_jsonable_python

from apps.backend.telemetry import review_attrs, review_context_attrs
from src.linger.agents.muse.models import MuseCandidate
from src.linger.agents.provenance.models import ProvenanceReview, RiskCode
from src.linger.contracts.librarian import (
    LIBRARIAN_RESPONSE_ADAPTER,
    EvidenceRecord,
    RetrievalResult,
)
from src.linger.contracts.turn import ReleaseScope

SAFE_DECLINE = "I’m sorry, but I can’t provide a reliable response to that right now."
FailureStage = Literal[
    "muse_draft",
    "provenance_review",
    "muse_revision",
    "deterministic_validation",
]


class ReleaseValidationError(ValueError):
    """Raised when a passed candidate cannot be proven against trusted evidence."""


@dataclass(frozen=True)
class ReflectionRelease:
    """The released text and the real path that authorised it."""

    reply: str
    release_source: Literal["muse_candidate", "application_safe_decline"]
    provenance_verdicts: tuple[Literal["pass", "revise", "reject"], ...] = ()
    revision_count: int = 0
    failure_stage: FailureStage | None = None
    # Why Provenance blocked, as bare risk codes. The matching critique contains
    # rejected draft text and therefore never crosses the release boundary.
    finding_codes: tuple[RiskCode, ...] = ()


def _codes(*reviews: ProvenanceReview) -> tuple[RiskCode, ...]:
    """Collect risk codes across one or both reviews, first occurrence first."""
    seen: dict[RiskCode, None] = {}
    for review in reviews:
        for finding in review.findings:
            seen.setdefault(finding.code, None)
    return tuple(seen)


def _safe_decline(
    *,
    verdicts: tuple[Literal["pass", "revise", "reject"], ...] = (),
    revision_count: int = 0,
    failure_stage: FailureStage | None = None,
    finding_codes: tuple[RiskCode, ...] = (),
) -> ReflectionRelease:
    return ReflectionRelease(
        reply=SAFE_DECLINE,
        release_source="application_safe_decline",
        provenance_verdicts=verdicts,
        revision_count=revision_count,
        failure_stage=failure_stage,
        finding_codes=finding_codes,
    )


def _tool_results(run_result: Any) -> list[dict[str, object]]:
    """Extract the actual bounded tool outputs that could support Muse's draft."""
    return [
        {
            "tool_name": part.tool_name,
            "outcome": part.outcome,
            "content": to_jsonable_python(part.content, serialize_unknown=True),
        }
        # Only this invocation may authorise this candidate. History can contain
        # tool results from older turns, so `all_messages()` is not safe here.
        for message in run_result.new_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart)
        and part.tool_name in {"librarian_search", "serendipity_explore"}
    ]


def _candidate(output: object) -> MuseCandidate:
    """Validate and trim one typed Muse output without relaxing its schema."""
    try:
        candidate = MuseCandidate.model_validate(output)
    except Exception:
        raise ReleaseValidationError("Muse returned an invalid candidate") from None
    reply = candidate.reply.strip()
    if not reply:
        raise ReleaseValidationError("Muse returned an empty candidate")
    return candidate.model_copy(update={"reply": reply})


def _trusted_book_evidence(
    tool_results: list[dict[str, object]],
    release_scope: ReleaseScope | None,
) -> dict[str, EvidenceRecord]:
    """Build a turn-local index from typed Librarian results only."""
    evidence: dict[str, EvidenceRecord] = {}
    for tool_result in tool_results:
        if tool_result["tool_name"] != "librarian_search":
            continue
        try:
            response = LIBRARIAN_RESPONSE_ADAPTER.validate_python(tool_result["content"])
        except Exception:
            raise ReleaseValidationError("Librarian returned an invalid response") from None
        if not isinstance(response, RetrievalResult):
            continue
        if release_scope is None:
            raise ReleaseValidationError("Librarian result has no trusted release scope")

        searched = response.searched_scope
        if (
            searched.work_id != release_scope.work_id
            or searched.book_version_id != release_scope.book_version_id
            or searched.max_chapter_inclusive > release_scope.chapter_max
        ):
            raise ReleaseValidationError("Librarian result exceeds the release scope")

        for record in response.evidence:
            start_line, end_line = record.source_lines
            if (
                record.work_id != searched.work_id
                or record.book_version_id != searched.book_version_id
                or record.chapter_number > searched.max_chapter_inclusive
                or start_line < 1
                or end_line < start_line
            ):
                raise ReleaseValidationError("Librarian evidence exceeds its searched scope")
            existing = evidence.get(record.evidence_id)
            if existing is not None and existing != record:
                raise ReleaseValidationError("Librarian evidence identifier is ambiguous")
            evidence[record.evidence_id] = record
    return evidence


def _validate_release(
    candidate: MuseCandidate,
    tool_results: list[dict[str, object]],
    release_scope: ReleaseScope | None,
) -> None:
    """Validate declared book citations after semantic approval."""
    evidence = _trusted_book_evidence(tool_results, release_scope)
    for declared in candidate.evidence_uses:
        if declared.source_kind != "book_corpus":
            raise ReleaseValidationError("Candidate uses an unsupported evidence source")
        record = evidence.get(declared.evidence_id)
        if record is None:
            raise ReleaseValidationError("Candidate cites unresolved evidence")
        if declared.source_location != record.location:
            raise ReleaseValidationError("Candidate cites an incorrect source location")
        if declared.exact_quote is not None and (
            declared.exact_quote not in candidate.reply
            or declared.exact_quote not in record.text
        ):
            raise ReleaseValidationError("Candidate exact quotation is not supported")


def _context_with_tool_results(
    review_context: Mapping[str, object],
    tool_results: list[dict[str, object]],
) -> dict[str, object]:
    """Attach evidence from Muse's real tool calls without trusting its claims."""
    context = dict(review_context)
    context["muse_tool_results"] = tool_results
    cited_evidence = [
        result["content"] for result in tool_results if result["tool_name"] == "librarian_search"
    ]
    connection_proposals = [
        result["content"] for result in tool_results if result["tool_name"] == "serendipity_explore"
    ]
    if cited_evidence:
        context["cited_evidence"] = cited_evidence
    if connection_proposals:
        context["connection_proposal"] = connection_proposals
    return context


async def _review(
    candidate: MuseCandidate,
    provenance: Agent[None, ProvenanceReview],
    review_context: Mapping[str, object],
) -> ProvenanceReview:
    payload = json.dumps(
        {
            **review_context,
            "candidate_response": candidate.reply,
            "candidate_evidence_uses": [
                evidence.model_dump(mode="json") for evidence in candidate.evidence_uses
            ],
        },
        ensure_ascii=False,
    )
    with logfire.span("provenance.review", **review_context_attrs(review_context)) as span:
        result = await provenance.run(payload)
        review = result.output
        span.set_attribute("review", review_attrs(review))
    return review


async def reflection_reply(
    message: str,
    history: list[ModelMessage],
    *,
    muse: Agent[None, MuseCandidate],
    provenance: Agent[None, ProvenanceReview],
    review_context: Mapping[str, object] | None = None,
    release_scope: ReleaseScope | None = None,
) -> ReflectionRelease:
    """Return an approved candidate or an application-authored safe decline."""
    review_context = review_context or {}
    with logfire.span("reflection.release") as span:
        return await _reflection_reply(
            message,
            history,
            muse=muse,
            provenance=provenance,
            review_context=review_context,
            release_scope=release_scope,
            span=span,
        )


def _record_release(span: Any, release: ReflectionRelease) -> ReflectionRelease:
    """Attach the release outcome to the parent span.

    Every field here is an enum, tuple of enums, or int, so §8.1 permits all of
    them — `finding_codes` included, being a fixed `RiskCode` enum. Provenance
    critique prose is intentionally absent from `ReflectionRelease` because it
    quotes rejected candidate text verbatim.
    """
    span.set_attribute("release_source", release.release_source)
    span.set_attribute("provenance_verdicts", list(release.provenance_verdicts))
    span.set_attribute("revision_count", release.revision_count)
    span.set_attribute("failure_stage", release.failure_stage)
    span.set_attribute("finding_codes", list(release.finding_codes))
    return release


async def _reflection_reply(
    message: str,
    history: list[ModelMessage],
    *,
    muse: Agent[None, MuseCandidate],
    provenance: Agent[None, ProvenanceReview],
    review_context: Mapping[str, object],
    release_scope: ReleaseScope | None,
    span: Any,
) -> ReflectionRelease:
    """The release flow, with the parent span threaded through for attributes."""
    try:
        with logfire.span("muse.draft"):
            draft_result = await muse.run(message, message_history=history)
        candidate = _candidate(draft_result.output)
        draft_tool_results = _tool_results(draft_result)
    except Exception as exc:
        span.record_exception(exc)
        return _record_release(span, _safe_decline(failure_stage="muse_draft"))
    draft_review_context = _context_with_tool_results(review_context, draft_tool_results)

    try:
        review = await _review(candidate, provenance, draft_review_context)
    except Exception as exc:
        span.record_exception(exc)
        return _record_release(span, _safe_decline(failure_stage="provenance_review"))

    if review.response_decision == "pass":
        try:
            _validate_release(candidate, draft_tool_results, release_scope)
        except ReleaseValidationError as exc:
            span.record_exception(exc)
            return _record_release(
                span,
                _safe_decline(
                    verdicts=("pass",),
                    failure_stage="deterministic_validation",
                    finding_codes=_codes(review),
                ),
            )
        return _record_release(
            span,
            ReflectionRelease(
                reply=candidate.reply,
                release_source="muse_candidate",
                provenance_verdicts=("pass",),
                finding_codes=_codes(review),
            ),
        )
    if review.response_decision != "revise":
        return _record_release(
            span,
            _safe_decline(
                verdicts=(review.response_decision,),
                finding_codes=_codes(review),
            ),
        )

    revision_critique = review.critique()
    revision_request = json.dumps(
        {
            "task": "Revise the candidate once to address the review critique.",
            "original_muse_input": message,
            "candidate_response": candidate.reply,
            "candidate_evidence_uses": [
                evidence.model_dump(mode="json") for evidence in candidate.evidence_uses
            ],
            "review_critique": revision_critique,
        },
        ensure_ascii=False,
    )
    try:
        with logfire.span("muse.revision"):
            revision_result = await muse.run(revision_request, message_history=history)
        revised_candidate = _candidate(revision_result.output)
    except Exception as exc:
        span.record_exception(exc)
        return _record_release(
            span,
            _safe_decline(
                verdicts=("revise",),
                revision_count=1,
                failure_stage="muse_revision",
                finding_codes=_codes(review),
            ),
        )

    try:
        revised_tool_results = draft_tool_results + _tool_results(revision_result)
        revised_review = await _review(
            revised_candidate,
            provenance,
            _context_with_tool_results(review_context, revised_tool_results),
        )
    except Exception as exc:
        span.record_exception(exc)
        return _record_release(
            span,
            _safe_decline(
                verdicts=("revise",),
                revision_count=1,
                failure_stage="provenance_review",
                finding_codes=_codes(review),
            ),
        )

    if revised_review.response_decision == "pass":
        try:
            _validate_release(revised_candidate, revised_tool_results, release_scope)
        except ReleaseValidationError as exc:
            span.record_exception(exc)
            return _record_release(
                span,
                _safe_decline(
                    verdicts=("revise", "pass"),
                    revision_count=1,
                    failure_stage="deterministic_validation",
                    finding_codes=_codes(review, revised_review),
                ),
            )
        return _record_release(
            span,
            ReflectionRelease(
                reply=revised_candidate.reply,
                release_source="muse_candidate",
                provenance_verdicts=("revise", "pass"),
                revision_count=1,
                finding_codes=_codes(review, revised_review),
            ),
        )
    return _record_release(
        span,
        _safe_decline(
            verdicts=("revise", revised_review.response_decision),
            revision_count=1,
            finding_codes=_codes(review, revised_review),
        ),
    )
