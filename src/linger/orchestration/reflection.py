"""Application-owned Muse-to-Provenance release flow."""

import json
from dataclasses import dataclass
from typing import Any, Literal, Mapping

import logfire
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ToolCallPart, ToolReturnPart
from pydantic_core import to_jsonable_python

from apps.backend.telemetry import (
    record_failure,
    review_attrs,
    run_agent_traced,
    set_span_attrs,
)
from src.linger.agents.muse.models import MemoryCandidate, MuseCandidate
from src.linger.agents.provenance.models import ProvenanceReview, RiskCode
from src.linger.contracts.librarian import (
    LIBRARIAN_RESPONSE_ADAPTER,
    EvidenceRecord,
    RetrievalResult,
)
from src.linger.contracts.turn import ReleaseScope
from src.linger.orchestration.capture import CaptureBindingError, candidate_from_review
from src.linger.services.memory import AutomaticMemoryCandidate

SAFE_DECLINE = "I’m sorry, but I can’t provide a reliable response to that right now."
FailureStage = Literal[
    "muse_draft",
    "provenance_review",
    "muse_revision",
    "deterministic_validation",
]
CaptureFailure = Literal["invalid_capture_binding"]
CaptureNomination = Literal["candidate", "no_candidate"]


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
    capture_nomination: CaptureNomination | None = None
    capture_decision: Literal["allow_capture", "reject_capture", "no_candidate"] | None = None
    automatic_capture_candidate: AutomaticMemoryCandidate | None = None
    capture_failure: CaptureFailure | None = None
    # Muse's direct librarian_search calls, outside connection discovery.
    # Inspection-only: request args plus the validated LibrarianResponse.
    librarian_grounding_calls: tuple[dict[str, object], ...] = ()


def _codes(*reviews: ProvenanceReview) -> tuple[RiskCode, ...]:
    """Collect risk codes across one or both reviews, first occurrence first."""
    seen: dict[RiskCode, None] = {}
    for review in reviews:
        for finding in review.findings:
            seen.setdefault(finding.code, None)
    return tuple(seen)


def _nomination(candidate: MuseCandidate) -> CaptureNomination:
    """Report Muse's actual nomination without serializing candidate text."""
    return "candidate" if isinstance(candidate.memory, MemoryCandidate) else "no_candidate"


def _safe_decline(
    *,
    verdicts: tuple[Literal["pass", "revise", "reject"], ...] = (),
    revision_count: int = 0,
    failure_stage: FailureStage | None = None,
    finding_codes: tuple[RiskCode, ...] = (),
    capture_nomination: CaptureNomination | None = None,
    capture_decision: Literal[
        "allow_capture", "reject_capture", "no_candidate"
    ] | None = None,
    automatic_capture_candidate: AutomaticMemoryCandidate | None = None,
    capture_failure: CaptureFailure | None = None,
    librarian_grounding_calls: tuple[dict[str, object], ...] = (),
) -> ReflectionRelease:
    return ReflectionRelease(
        reply=SAFE_DECLINE,
        release_source="application_safe_decline",
        provenance_verdicts=verdicts,
        revision_count=revision_count,
        failure_stage=failure_stage,
        finding_codes=finding_codes,
        capture_nomination=capture_nomination,
        capture_decision=capture_decision,
        automatic_capture_candidate=automatic_capture_candidate,
        capture_failure=capture_failure,
        librarian_grounding_calls=librarian_grounding_calls,
    )


def _tool_results(run_result: Any) -> list[dict[str, object]]:
    """Extract the actual bounded tool calls and outputs that could support Muse's draft."""
    # Only this invocation may authorise this candidate. History can contain
    # tool results from older turns, so `all_messages()` is not safe here.
    messages = run_result.new_messages()
    call_args: dict[str, dict[str, object]] = {
        part.tool_call_id: (part.args_as_dict() or {})
        for message in messages
        for part in message.parts
        if isinstance(part, ToolCallPart)
        and part.tool_name in {"librarian_search", "serendipity_explore"}
    }
    return [
        {
            "tool_name": part.tool_name,
            "outcome": part.outcome,
            "args": call_args.get(part.tool_call_id, {}),
            "content": to_jsonable_python(part.content, serialize_unknown=True),
        }
        for message in messages
        for part in message.parts
        if isinstance(part, ToolReturnPart)
        and part.tool_name in {"librarian_search", "serendipity_explore"}
    ]


def _librarian_grounding(
    tool_results: list[dict[str, object]],
) -> tuple[dict[str, object], ...]:
    """Expose Muse's direct grounding calls for inspection only.

    This is diagnostic surfacing of an already-validated tool result, not a new
    authority: release still depends solely on `_trusted_book_evidence`.
    """
    return tuple(
        {
            "request": result["args"],
            "outcome": result["outcome"],
            "response": result["content"],
        }
        for result in tool_results
        if result["tool_name"] == "librarian_search"
    )


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
    capture_source_text: str,
) -> ProvenanceReview:
    payload = json.dumps(
        {
            **review_context,
            "candidate_response": candidate.reply,
            "candidate_evidence_uses": [
                evidence.model_dump(mode="json") for evidence in candidate.evidence_uses
            ],
            "candidate_memory": candidate.memory.model_dump(mode="json"),
            "capture_source_text": capture_source_text,
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


def _reviewed_capture(
    candidate: MuseCandidate,
    review: ProvenanceReview,
    *,
    capture_source_text: str,
    source_event_id: str,
    tool_results: list[dict[str, object]],
    release_scope: ReleaseScope | None,
) -> tuple[AutomaticMemoryCandidate | None, CaptureFailure | None]:
    """Bind one reviewed nomination to exact user words and trusted evidence."""
    try:
        evidence_ids = frozenset(_trusted_book_evidence(tool_results, release_scope))
        bound = candidate_from_review(
            review,
            nomination=candidate.memory,
            source_text=capture_source_text,
            source_event_id=source_event_id,
            available_evidence_ids=evidence_ids,
        )
    except (CaptureBindingError, ReleaseValidationError):
        return None, "invalid_capture_binding"
    return bound, None


async def reflection_reply(
    message: str,
    history: list[ModelMessage],
    *,
    muse: Agent[None, MuseCandidate],
    provenance: Agent[None, ProvenanceReview],
    review_context: Mapping[str, object] | None = None,
    release_scope: ReleaseScope | None = None,
    capture_source_text: str = "",
    source_event_id: str = "",
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
                capture_source_text=capture_source_text,
                source_event_id=source_event_id,
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
    capture_source_text: str,
    source_event_id: str,
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
    draft_nomination = _nomination(candidate)
    draft_review_context = _context_with_tool_results(review_context, draft_tool_results)

    try:
        review = await _review(
            candidate,
            provenance,
            draft_review_context,
            capture_source_text,
        )
    except Exception:
        return _record_release(
            span,
            _safe_decline(
                failure_stage="provenance_review",
                capture_nomination=draft_nomination,
                librarian_grounding_calls=_librarian_grounding(draft_tool_results),
            ),
        )

    if review.response_decision != "revise":
        capture, capture_failure = _reviewed_capture(
            candidate,
            review,
            capture_source_text=capture_source_text,
            source_event_id=source_event_id,
            tool_results=draft_tool_results,
            release_scope=release_scope,
        )

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
                    capture_nomination=draft_nomination,
                    capture_decision=review.capture_decision,
                    automatic_capture_candidate=capture,
                    capture_failure=capture_failure,
                    librarian_grounding_calls=_librarian_grounding(draft_tool_results),
                ),
            )
        return _record_release(
            span,
            ReflectionRelease(
                reply=candidate.reply,
                release_source="muse_candidate",
                provenance_verdicts=("pass",),
                finding_codes=_codes(review),
                capture_nomination=draft_nomination,
                capture_decision=review.capture_decision,
                automatic_capture_candidate=capture,
                capture_failure=capture_failure,
                librarian_grounding_calls=_librarian_grounding(draft_tool_results),
            ),
        )
    if review.response_decision != "revise":
        return _record_release(
            span,
            _safe_decline(
                verdicts=(review.response_decision,),
                finding_codes=_codes(review),
                capture_nomination=draft_nomination,
                capture_decision=review.capture_decision,
                automatic_capture_candidate=capture,
                capture_failure=capture_failure,
                librarian_grounding_calls=_librarian_grounding(draft_tool_results),
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
            "candidate_memory": candidate.memory.model_dump(mode="json"),
            "muse_tool_results": draft_tool_results,
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
                capture_nomination=draft_nomination,
                librarian_grounding_calls=_librarian_grounding(draft_tool_results),
            ),
        )

    revised_nomination = _nomination(revised_candidate)

    try:
        revised_tool_results = draft_tool_results + _tool_results(revision_result)
        revised_review = await _review(
            revised_candidate,
            provenance,
            _context_with_tool_results(review_context, revised_tool_results),
            capture_source_text,
        )
    except Exception:
        return _record_release(
            span,
            _safe_decline(
                verdicts=("revise",),
                revision_count=1,
                failure_stage="provenance_review",
                finding_codes=_codes(review),
                capture_nomination=revised_nomination,
                librarian_grounding_calls=_librarian_grounding(draft_tool_results),
            ),
        )

    capture, capture_failure = _reviewed_capture(
        revised_candidate,
        revised_review,
        capture_source_text=capture_source_text,
        source_event_id=source_event_id,
        tool_results=revised_tool_results,
        release_scope=release_scope,
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
                    capture_nomination=revised_nomination,
                    capture_decision=revised_review.capture_decision,
                    automatic_capture_candidate=capture,
                    capture_failure=capture_failure,
                    librarian_grounding_calls=_librarian_grounding(revised_tool_results),
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
                capture_nomination=revised_nomination,
                capture_decision=revised_review.capture_decision,
                automatic_capture_candidate=capture,
                capture_failure=capture_failure,
                librarian_grounding_calls=_librarian_grounding(revised_tool_results),
            ),
        )
    return _record_release(
        span,
        _safe_decline(
            verdicts=("revise", revised_review.response_decision),
            revision_count=1,
            finding_codes=_codes(review, revised_review),
            capture_nomination=revised_nomination,
            capture_decision=revised_review.capture_decision,
            automatic_capture_candidate=capture,
            capture_failure=capture_failure,
            librarian_grounding_calls=_librarian_grounding(revised_tool_results),
        ),
    )
