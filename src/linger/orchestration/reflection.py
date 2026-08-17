"""Application-owned Muse-to-Provenance release flow."""

import json
from dataclasses import dataclass
from typing import Any, Literal, Mapping

import logfire
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ToolReturnPart
from pydantic_core import to_jsonable_python

from apps.backend.telemetry import (
    record_failure,
    review_attrs,
    run_agent_traced,
    set_span_attrs,
)
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
    result = await run_agent_traced(
        provenance,
        payload,
        span_name="provenance.review",
        role="Provenance",
        stage="review",
        prompt_template_id="provenance.release-gate",
        failure_code="provenance_model_failed",
        result_attrs=lambda run_result: review_attrs(run_result.output),
    )
    return result.output


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
    caught: Exception | None = None
    release: ReflectionRelease | None = None
    with logfire.span("reflection.release") as span:
        try:
            release = await _reflection_reply(
                message,
                history,
                muse=muse,
                provenance=provenance,
                review_context=review_context,
                release_scope=release_scope,
                span=span,
            )
        except Exception as exc:
            caught = exc
            record_failure(
                span,
                stage="reflection_release",
                code="reflection_pipeline_failed",
                retryable=False,
                failure_type="application",
            )
    if caught is not None:
        raise caught
    assert release is not None
    return release


def _record_release(span: Any, release: ReflectionRelease) -> ReflectionRelease:
    """Attach the release outcome to the parent span.

    Every field is a fixed enum or number permitted by the telemetry contract.
    Provenance critique prose stays out because it quotes candidate text.
    """
    set_span_attrs(
        span,
        {
            "status": (
                "decline"
                if release.release_source == "application_safe_decline"
                else "success"
            ),
            "release.source": release.release_source,
            "release.revision_count": release.revision_count,
            "provenance.finding_codes": list(release.finding_codes),
            "validation.outcome": (
                "passed"
                if release.release_source == "muse_candidate"
                else (
                    "failed"
                    if release.failure_stage == "deterministic_validation"
                    else "not_run"
                )
            ),
        },
    )
    if release.failure_stage is not None:
        failure_code = {
            "muse_draft": "muse_draft_failed",
            "provenance_review": "provenance_review_failed",
            "muse_revision": "muse_revision_failed",
            "deterministic_validation": "release_validation_failed",
        }[release.failure_stage]
        record_failure(
            span,
            stage=release.failure_stage,
            code=failure_code,
            retryable=release.failure_stage != "deterministic_validation",
            failure_type=(
                "validation"
                if release.failure_stage == "deterministic_validation"
                else "model"
            ),
        )
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
        draft_result = await run_agent_traced(
            muse,
            message,
            span_name="muse.draft",
            role="Muse",
            stage="draft",
            prompt_template_id="muse.reflection",
            failure_code="muse_model_failed",
            message_history=history,
        )
        candidate = _candidate(draft_result.output)
        draft_tool_results = _tool_results(draft_result)
    except Exception:
        return _record_release(span, _safe_decline(failure_stage="muse_draft"))
    draft_review_context = _context_with_tool_results(review_context, draft_tool_results)

    try:
        review = await _review(candidate, provenance, draft_review_context)
    except Exception:
        return _record_release(span, _safe_decline(failure_stage="provenance_review"))

    if review.response_decision == "pass":
        try:
            _validate_release(candidate, draft_tool_results, release_scope)
        except ReleaseValidationError:
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
        revision_result = await run_agent_traced(
            muse,
            revision_request,
            span_name="muse.revision",
            role="Muse",
            stage="revision",
            prompt_template_id="muse.revision",
            failure_code="muse_revision_model_failed",
            message_history=history,
        )
        revised_candidate = _candidate(revision_result.output)
    except Exception:
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
    except Exception:
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
        except ReleaseValidationError:
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
