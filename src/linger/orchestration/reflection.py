"""Application-owned Muse-to-Provenance release flow."""

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Literal, Mapping

import logfire
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_core import to_jsonable_python

from apps.backend.telemetry import (
    record_failure,
    review_attrs,
    run_agent_traced,
    set_span_attrs,
)
from apps.backend.contracts import (
    EvidenceItem,
    MuseDraftInput,
    MuseRevisionInput,
    MuseRevisionReview,
)
from src.linger.agents.muse.models import EvidenceUse, MemoryCandidate, MuseCandidate
from src.linger.agents.muse.prompt import (
    DRAFT_PROMPT_FINGERPRINT,
    REVISION_PROMPT_FINGERPRINT,
)
from src.linger.agents.provenance.models import (
    CandidateUnderReview,
    CurrentLine,
    ProvenanceContext,
    ProvenanceInput,
    ProvenancePolicy,
    ProvenanceReview,
    RiskCode,
)
from src.linger.agents.provenance.prompt import (
    PROMPT_FINGERPRINT as PROVENANCE_PROMPT_FINGERPRINT,
)
from src.linger.agents.serendipity.models import (
    ConnectionExplorationResult,
    ConnectionProposal,
)
from src.linger.contracts.emotional import EMOTIONAL_BOUNDARY_RESPONSE
from src.linger.contracts.librarian import (
    LIBRARIAN_RESPONSE_ADAPTER,
    LIBRARIAN_ROUTING_RESPONSE_ADAPTER,
    ClarificationRequest,
    EvidenceRecord,
    NoMatch,
    RetrievalResult,
    RoutedWork,
)
from src.linger.contracts.turn import ReleaseScope
from src.linger.orchestration.capture import CaptureBindingError, candidate_from_review
from src.linger.orchestration.grounding import evidence_record_from_item
from src.linger.orchestration.turn_context import turn_evidence
from src.linger.services.memory import AutomaticMemoryCandidate

SAFE_DECLINE = "I’m sorry, but I can’t provide a reliable response to that right now."
SPOILER_DECLINE = (
    "I’m not sure where you are in the book, so I’d rather not risk getting "
    "ahead of you."
)
PIPELINE_FAILURE_DECLINE = (
    "Something went wrong on my side just now — mind asking again?"
)
FailureStage = Literal[
    "emotional_boundary_preflight",
    "muse_draft",
    "provenance_review",
    "muse_revision",
    "deterministic_validation",
]
FailureType = Literal["application", "model", "validation"]
CaptureFailure = Literal["invalid_capture_binding"]
CaptureNomination = Literal["candidate", "no_candidate"]
BoundaryOrigin = Literal["preflight", "candidate_review"]


class ReleaseValidationError(ValueError):
    """Raised when a passed candidate cannot be proven against trusted evidence."""


@dataclass(frozen=True)
class ReflectionRelease:
    """The released text and the real path that authorised it."""

    reply: str
    release_source: Literal[
        "muse_candidate",
        "application_emotional_boundary",
        "application_safe_decline",
    ]
    boundary_origin: BoundaryOrigin | None = None
    provenance_verdicts: tuple[Literal["pass", "revise", "reject"], ...] = ()
    revision_count: int = 0
    failure_stage: FailureStage | None = None
    failure_type: FailureType | None = None
    failure_retryable: bool | None = None
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
    # Content-free handles only. Rejected candidate text never crosses this boundary.
    evidence_ids: tuple[str, ...] = ()
    review_finding_codes: tuple[tuple[RiskCode, ...], ...] = ()

    def __post_init__(self) -> None:
        is_boundary = self.release_source == "application_emotional_boundary"
        if is_boundary != (self.boundary_origin is not None):
            raise ValueError(
                "boundary_origin is required only for an emotional-boundary release"
            )
        has_failure = self.failure_stage is not None
        if has_failure != (self.failure_type is not None):
            raise ValueError("failure_type is required only with failure_stage")
        if has_failure != (self.failure_retryable is not None):
            raise ValueError("failure_retryable is required only with failure_stage")


def _codes(*reviews: ProvenanceReview) -> tuple[RiskCode, ...]:
    """Collect risk codes across one or both reviews, first occurrence first."""
    # Not filtered by applies_to: a non-pass response always carries a
    # response-scoped finding, so a capture finding can only widen this set
    # into decline_text's generic fallback, never redirect the selection.
    seen: dict[RiskCode, None] = {}
    for review in reviews:
        for finding in review.findings:
            seen.setdefault(finding.code, None)
    return tuple(seen)


def _review_codes(*reviews: ProvenanceReview) -> tuple[tuple[RiskCode, ...], ...]:
    """Keep finding codes attached to the review call that produced them."""
    return tuple(tuple(finding.code for finding in review.findings) for review in reviews)


def _evidence_ids(candidate: MuseCandidate) -> tuple[str, ...]:
    """Keep declared book-corpus evidence handles; session lines have no ID."""
    return tuple(
        dict.fromkeys(
            use.evidence_id
            for use in candidate.evidence_uses
            if use.source_kind == "book_corpus"
        )
    )


def _released_user_lines(history: list[ModelMessage]) -> tuple[str, ...]:
    """Return released user-authored Line text from this session, never Muse replies."""
    return tuple(
        part.content
        for message in history
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart) and isinstance(part.content, str)
    )


def _verified_session_lines(
    evidence_uses: tuple[EvidenceUse, ...],
    released_user_lines: tuple[str, ...],
) -> tuple[str, ...]:
    """Resolve each declared session-line quote as an exact substring of one line.

    `released_user_lines` carries prior released turns plus the current turn's
    own user message, so a same-turn echo verifies without laundering anything.
    """
    verified: dict[str, None] = {}
    for declared in evidence_uses:
        if declared.source_kind != "session_line":
            continue
        if any(declared.quote in line for line in released_user_lines):
            verified.setdefault(declared.quote, None)
    return tuple(verified)


def _nomination(candidate: MuseCandidate) -> CaptureNomination:
    """Report Muse's actual nomination without serializing candidate text."""
    return "candidate" if isinstance(candidate.memory, MemoryCandidate) else "no_candidate"


def decline_text(
    failure_stage: FailureStage | None,
    finding_codes: tuple[RiskCode, ...],
) -> str:
    """Pick the one fixed, application-authored decline for a blocked turn."""
    if failure_stage is not None:
        return PIPELINE_FAILURE_DECLINE
    if set(finding_codes) == {"spoiler"}:
        return SPOILER_DECLINE
    return SAFE_DECLINE


def _safe_decline(
    *,
    verdicts: tuple[Literal["pass", "revise", "reject"], ...] = (),
    revision_count: int = 0,
    failure_stage: FailureStage | None = None,
    failure_type: FailureType | None = None,
    failure_retryable: bool | None = None,
    finding_codes: tuple[RiskCode, ...] = (),
    capture_nomination: CaptureNomination | None = None,
    capture_decision: Literal[
        "allow_capture", "reject_capture", "no_candidate"
    ] | None = None,
    automatic_capture_candidate: AutomaticMemoryCandidate | None = None,
    capture_failure: CaptureFailure | None = None,
    librarian_grounding_calls: tuple[dict[str, object], ...] = (),
    evidence_ids: tuple[str, ...] = (),
    review_finding_codes: tuple[tuple[RiskCode, ...], ...] = (),
) -> ReflectionRelease:
    return ReflectionRelease(
        reply=decline_text(failure_stage, finding_codes),
        release_source="application_safe_decline",
        provenance_verdicts=verdicts,
        revision_count=revision_count,
        failure_stage=failure_stage,
        failure_type=failure_type,
        failure_retryable=failure_retryable,
        finding_codes=finding_codes,
        capture_nomination=capture_nomination,
        capture_decision=capture_decision,
        automatic_capture_candidate=automatic_capture_candidate,
        capture_failure=capture_failure,
        librarian_grounding_calls=librarian_grounding_calls,
        evidence_ids=evidence_ids,
        review_finding_codes=review_finding_codes,
    )


def emotional_boundary_release(
    *,
    origin: BoundaryOrigin,
    review_path: tuple[ProvenanceReview, ...] = (),
    candidate: MuseCandidate | None = None,
    tool_results: list[dict[str, object]] | None = None,
) -> ReflectionRelease:
    """Return the canonical boundary with content-free audit metadata."""
    if origin == "preflight" and (review_path or candidate is not None):
        raise ValueError("a preflight boundary cannot have candidate data")
    if origin == "candidate_review" and (not review_path or candidate is None):
        raise ValueError(
            "a candidate-review boundary requires its candidate and review path"
        )
    if len(review_path) > 2:
        raise ValueError("an emotional boundary can follow at most one revision")
    tool_results = tool_results or []
    return ReflectionRelease(
        reply=EMOTIONAL_BOUNDARY_RESPONSE,
        release_source="application_emotional_boundary",
        boundary_origin=origin,
        provenance_verdicts=tuple(
            review.response_decision for review in review_path
        ),
        revision_count=max(0, len(review_path) - 1),
        finding_codes=_codes(*review_path),
        capture_nomination=_nomination(candidate) if candidate is not None else None,
        capture_decision=(review_path[-1].capture_decision if review_path else None),
        librarian_grounding_calls=_librarian_grounding(tool_results),
        evidence_ids=_evidence_ids(candidate) if candidate is not None else (),
        review_finding_codes=_review_codes(*review_path),
    )


def emotional_preflight_safe_decline(
    *,
    failure_type: FailureType = "model",
    retryable: bool = True,
) -> ReflectionRelease:
    """Fail closed when the no-tool boundary classifier cannot complete."""
    return _safe_decline(
        failure_stage="emotional_boundary_preflight",
        failure_type=failure_type,
        failure_retryable=retryable,
    )


def _review_requires_emotional_boundary(review: ProvenanceReview) -> bool:
    """Read the gate's explicit disposition for a preflight miss."""
    return review.emotional_boundary_decision == "required"


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
        and part.tool_name in {"librarian_search", "librarian_route", "serendipity_explore"}
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
        and part.tool_name in {"librarian_search", "librarian_route", "serendipity_explore"}
    ]


def _routing_responses(
    tool_results: list[dict[str, object]],
) -> list[RoutedWork | ClarificationRequest | NoMatch]:
    """Validate every `librarian_route` payload once for the checks below."""
    responses: list[RoutedWork | ClarificationRequest | NoMatch] = []
    for result in tool_results:
        if result["tool_name"] != "librarian_route":
            continue
        try:
            responses.append(
                LIBRARIAN_ROUTING_RESPONSE_ADAPTER.validate_python(result["content"])
            )
        except Exception:
            raise ReleaseValidationError(
                "Librarian routing returned an invalid response"
            ) from None
    return responses


def _required_clarification(
    routing_responses: list[RoutedWork | ClarificationRequest | NoMatch],
) -> str | None:
    """Return the exact question Librarian issued via `librarian_route`, if any.

    Clarifications now originate only from the tool flow: Librarian judged the
    reader's request as book-dependent but could not resolve a spoiler
    boundary, and returned a question for Muse to relay verbatim. Any
    clarification among possibly several `librarian_route` calls this turn
    binds the gate — the first one found, not the last.
    """
    for response in routing_responses:
        if isinstance(response, ClarificationRequest):
            return response.question
    return None


def _routed_release_scope(
    routing_responses: list[RoutedWork | ClarificationRequest | NoMatch],
) -> ReleaseScope | None:
    """Derive a trusted release scope from a routed work, if Librarian found one.

    This grants the same application-side authority `_infer_request_boundary`
    used to grant under `boundary_source="librarian_inferred"`: Librarian's
    own private, validated inference — never Muse's text — sets the ceiling.
    """
    for response in routing_responses:
        if isinstance(response, RoutedWork):
            return ReleaseScope(
                work_id=response.work_id,
                book_version_id=response.book_version_id,
                chapter_max=response.max_chapter_inclusive,
            )
    return None


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
        if result["tool_name"] in ("librarian_search", "librarian_route")
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


def _validate_record_scope(
    record: EvidenceRecord,
    release_scope: ReleaseScope | None,
    previously_released_evidence_ids: frozenset[str],
) -> None:
    start_line, end_line = record.source_lines
    if start_line < 1 or end_line < start_line:
        raise ReleaseValidationError("Book evidence has invalid source lines")
    if record.evidence_id in previously_released_evidence_ids:
        return
    if release_scope is None or (
        record.work_id != release_scope.work_id
        or record.book_version_id != release_scope.book_version_id
        or record.chapter_number > release_scope.chapter_max
    ):
        raise ReleaseValidationError("Book evidence exceeds the release scope")


def _trusted_book_evidence(
    release_scope: ReleaseScope | None,
    previously_released_evidence_ids: frozenset[str],
) -> dict[str, EvidenceRecord]:
    """Read the application-owned evidence index, never model message history."""
    evidence = dict(turn_evidence())
    for record in evidence.values():
        _validate_record_scope(
            record,
            release_scope,
            previously_released_evidence_ids,
        )
    return evidence


def _validated_book_evidence(
    tool_results: list[dict[str, object]],
    release_scope: ReleaseScope | None,
    previously_released_evidence_ids: frozenset[str],
) -> dict[str, EvidenceRecord]:
    """Validate current tool handoffs against the shared trusted index."""
    evidence = _trusted_book_evidence(
        release_scope,
        previously_released_evidence_ids,
    )
    for tool_result in tool_results:
        if tool_result["tool_name"] == "librarian_search":
            try:
                response = LIBRARIAN_RESPONSE_ADAPTER.validate_python(
                    tool_result["content"]
                )
            except Exception:
                raise ReleaseValidationError(
                    "Librarian returned an invalid response"
                ) from None
            if not isinstance(response, RetrievalResult):
                continue
            if release_scope is None:
                raise ReleaseValidationError(
                    "Librarian result has no trusted release scope"
                )
            searched = response.searched_scope
            if (
                searched.work_id != release_scope.work_id
                or searched.book_version_id != release_scope.book_version_id
                or searched.max_chapter_inclusive > release_scope.chapter_max
            ):
                raise ReleaseValidationError("Librarian result exceeds the release scope")
            for record in response.evidence:
                if (
                    record.work_id != searched.work_id
                    or record.book_version_id != searched.book_version_id
                    or record.chapter_number > searched.max_chapter_inclusive
                    or evidence.get(record.evidence_id) != record
                ):
                    raise ReleaseValidationError(
                        "Librarian result is not registered in the turn evidence"
                    )
            continue

        if tool_result["tool_name"] != "serendipity_explore":
            continue
        try:
            exploration = ConnectionExplorationResult.model_validate(
                tool_result["content"]
            )
        except Exception:
            raise ReleaseValidationError(
                "Serendipity returned an invalid response"
            ) from None
        if not isinstance(exploration.decision, ConnectionProposal):
            if exploration.evidence:
                raise ReleaseValidationError(
                    "A Serendipity decline returned unexpected evidence"
                )
            continue

        selected_ids = set(exploration.decision.selected_candidate.evidence_ids)
        returned_ids = {item.evidence_id for item in exploration.evidence}
        if selected_ids != returned_ids:
            raise ReleaseValidationError(
                "Serendipity proposal evidence does not match its selected candidate"
            )
        for item in exploration.evidence:
            if not isinstance(item, EvidenceItem):
                raise ReleaseValidationError(
                    "Serendipity web evidence is not a citation authority"
                )
            record = evidence_record_from_item(item)
            _validate_record_scope(record, release_scope, frozenset())
            if evidence.get(record.evidence_id) != record:
                raise ReleaseValidationError(
                    "Serendipity evidence is not registered in the turn evidence"
                )
    return evidence


def _validate_release(
    candidate: MuseCandidate,
    tool_results: list[dict[str, object]],
    release_scope: ReleaseScope | None,
    previously_released_evidence_ids: frozenset[str],
    required_clarification: str | None = None,
    released_user_lines: tuple[str, ...] = (),
) -> None:
    """Validate declared book and session-line citations after semantic approval."""
    if required_clarification is not None and (
        candidate.evidence_uses
        or any(result["tool_name"] != "librarian_route" for result in tool_results)
    ):
        raise ReleaseValidationError(
            "An unresolved spoiler boundary requires the exact clarification only"
        )
    evidence = _validated_book_evidence(
        tool_results,
        release_scope,
        previously_released_evidence_ids,
    )
    for declared in candidate.evidence_uses:
        if declared.source_kind == "session_line":
            if not any(
                declared.quote in line for line in released_user_lines
            ):
                raise ReleaseValidationError("Candidate cites an unresolved session line")
            continue
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


def _provenance_context(review_context: Mapping[str, object]) -> ProvenanceContext:
    """Validate the trusted application context before it reaches Provenance."""
    if not review_context:
        return ProvenanceContext(
            policy=ProvenancePolicy(
                spoiler_ceiling=None,
                allow_retrieval=False,
                allow_connection=False,
                allow_memory_capture=False,
            ),
            reading_context=None,
        )
    unexpected = set(review_context) - {"policy_constraints", "reading_context"}
    if unexpected:
        raise ReleaseValidationError("Provenance context contains unknown fields")
    try:
        return ProvenanceContext.model_validate(
            {
                "policy": review_context["policy_constraints"],
                "reading_context": review_context.get("reading_context"),
            }
        )
    except Exception:
        raise ReleaseValidationError("Provenance context is invalid") from None


def _effective_review_context(
    review_context: Mapping[str, object],
    routing_responses: list[RoutedWork | ClarificationRequest | NoMatch],
) -> Mapping[str, object]:
    """Extend Provenance's trusted context with a same-turn routed boundary.

    A reader-confirmed boundary already present in `review_context` always
    wins — a routed inferred ceiling never widens or replaces it, matching
    `_routed_release_scope`'s own priority. Only when no reading context was
    resolved before Muse ran does a `RoutedWork` result grant Provenance the
    same authority the deterministic release gate already trusts; Muse's own
    text is never a source for this.
    """
    if not review_context or review_context.get("reading_context") is not None:
        return review_context
    routed = next(
        (response for response in routing_responses if isinstance(response, RoutedWork)),
        None,
    )
    if routed is None:
        return review_context
    policy = dict(review_context.get("policy_constraints") or {})
    policy["spoiler_ceiling"] = routed.max_chapter_inclusive
    policy["allow_retrieval"] = True
    return {
        **review_context,
        "policy_constraints": policy,
        "reading_context": {
            "work_id": routed.work_id,
            "chapter_max": routed.max_chapter_inclusive,
            "boundary_source": "librarian_inferred",
        },
    }


def _provenance_input(
    candidate: MuseCandidate,
    review_context: Mapping[str, object],
    tool_results: list[dict[str, object]],
    capture_source_text: str,
    released_user_lines: tuple[str, ...],
) -> ProvenanceInput:
    """Build the sole typed envelope for one Provenance review."""
    # librarian_route only identifies a work and boundary; it carries no book
    # evidence or connection proposal for Provenance to inspect.
    grounding_results = [
        result for result in tool_results if result["tool_name"] != "librarian_route"
    ]
    try:
        return ProvenanceInput.model_validate(
            {
                "context": _provenance_context(review_context),
                "canonical_book_evidence": tuple(turn_evidence().values()),
                "canonical_session_lines": _verified_session_lines(
                    candidate.evidence_uses, released_user_lines
                ),
                "untrusted_tool_outcomes": grounding_results,
                "candidate": CandidateUnderReview(
                    response=candidate.reply,
                    evidence_uses=candidate.evidence_uses,
                    memory=candidate.memory,
                ),
                "current_line": CurrentLine(text=capture_source_text),
            }
        )
    except ReleaseValidationError:
        raise
    except Exception:
        raise ReleaseValidationError("Provenance input is invalid") from None


async def _review(
    candidate: MuseCandidate,
    provenance: Agent[None, ProvenanceReview],
    review_context: Mapping[str, object],
    tool_results: list[dict[str, object]],
    capture_source_text: str,
    released_user_lines: tuple[str, ...],
) -> ProvenanceReview:
    review_input = _provenance_input(
        candidate,
        review_context,
        tool_results,
        capture_source_text,
        released_user_lines,
    )
    payload = json.dumps(
        review_input.model_dump(mode="json"),
        ensure_ascii=False,
    )
    result = await run_agent_traced(
        provenance,
        payload,
        span_name="provenance.review",
        role="Provenance",
        stage="review",
        input_contract="src.linger.agents.provenance.models.ProvenanceInput",
        output_contract="src.linger.agents.provenance.models.ProvenanceReview",
        input_origin="Muse",
        prompt_template_id=PROVENANCE_PROMPT_FINGERPRINT.template_id,
        prompt_version=PROVENANCE_PROMPT_FINGERPRINT.version,
        prompt_digest=PROVENANCE_PROMPT_FINGERPRINT.digest,
        failure_code="provenance_model_failed",
        result_attrs=lambda run_result: review_attrs(run_result.output),
    )
    try:
        review = ProvenanceReview.model_validate(result.output)
        review_input.validate_review_locations(review)
    except Exception:
        raise ReleaseValidationError("Provenance review output is invalid") from None
    return review


def _reviewed_capture(
    candidate: MuseCandidate,
    review: ProvenanceReview,
    *,
    capture_source_text: str,
    source_event_id: str,
    tool_results: list[dict[str, object]],
    release_scope: ReleaseScope | None,
    previously_released_evidence_ids: frozenset[str],
) -> tuple[AutomaticMemoryCandidate | None, CaptureFailure | None]:
    """Bind one reviewed nomination to exact user words and trusted evidence."""
    try:
        evidence_ids = frozenset(
            _validated_book_evidence(
                tool_results,
                release_scope,
                previously_released_evidence_ids,
            )
        )
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
    previously_released_evidence_ids: frozenset[str] = frozenset(),
    capture_source_text: str = "",
    source_event_id: str = "",
) -> ReflectionRelease:
    """Return an approved candidate or an application-authored safe decline."""
    review_context = review_context or {}
    cancelled = False
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
                previously_released_evidence_ids=previously_released_evidence_ids,
                capture_source_text=capture_source_text,
                source_event_id=source_event_id,
                span=span,
            )
        except asyncio.CancelledError:
            cancelled = True
            record_failure(
                span,
                stage="reflection_release",
                code="request_cancelled",
                retryable=False,
                failure_type="application",
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
    if cancelled:
        raise asyncio.CancelledError
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
                if release.release_source != "muse_candidate"
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
        assert release.failure_type is not None
        assert release.failure_retryable is not None
        failure_code = {
            "emotional_boundary_preflight": "emotional_boundary_preflight_failed",
            "muse_draft": "muse_draft_failed",
            "provenance_review": "provenance_review_failed",
            "muse_revision": "muse_revision_failed",
            "deterministic_validation": "release_validation_failed",
        }[release.failure_stage]
        record_failure(
            span,
            stage=release.failure_stage,
            code=failure_code,
            retryable=release.failure_retryable,
            failure_type=release.failure_type,
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
    previously_released_evidence_ids: frozenset[str],
    capture_source_text: str,
    source_event_id: str,
    span: Any,
) -> ReflectionRelease:
    """The release flow, with the parent span threaded through for attributes."""
    # A session_line declaration may verify against wording released in an
    # earlier turn, or against the current turn's own message: Provenance
    # already receives that text as `current_line`, so verifying it here
    # launders nothing and avoids declining an innocent same-turn echo.
    released_user_lines = _released_user_lines(history) + (
        (capture_source_text,) if capture_source_text else ()
    )
    try:
        draft_input = MuseDraftInput.model_validate_json(message)
    except Exception:
        return _record_release(
            span,
            _safe_decline(
                failure_stage="muse_draft",
                failure_type="validation",
                failure_retryable=False,
            ),
        )
    try:
        draft_result = await run_agent_traced(
            muse,
            draft_input.model_dump_json(),
            span_name="muse.draft",
            role="Muse",
            stage="draft",
            input_contract="apps.backend.contracts.MuseDraftInput",
            output_contract="src.linger.agents.muse.models.MuseCandidate",
            prompt_template_id=DRAFT_PROMPT_FINGERPRINT.template_id,
            prompt_version=DRAFT_PROMPT_FINGERPRINT.version,
            prompt_digest=DRAFT_PROMPT_FINGERPRINT.digest,
            failure_code="muse_model_failed",
            message_history=history,
        )
    except Exception:
        return _record_release(
            span,
            _safe_decline(
                failure_stage="muse_draft",
                failure_type="model",
                failure_retryable=True,
            ),
        )
    try:
        candidate = _candidate(draft_result.output)
        draft_tool_results = _tool_results(draft_result)
        draft_routing = _routing_responses(draft_tool_results)
    except Exception:
        return _record_release(
            span,
            _safe_decline(
                failure_stage="muse_draft",
                failure_type="validation",
                failure_retryable=False,
            ),
        )
    # A routed work grants the same application-side release authority
    # `_infer_request_boundary` used to grant; an application-confirmed scope
    # (an explicit reader declaration) always takes priority over it.
    draft_release_scope = release_scope or _routed_release_scope(draft_routing)
    draft_review_context = _effective_review_context(review_context, draft_routing)
    draft_nomination = _nomination(candidate)
    try:
        review = await _review(
            candidate,
            provenance,
            draft_review_context,
            draft_tool_results,
            capture_source_text,
            released_user_lines,
        )
    except ReleaseValidationError:
        return _record_release(
            span,
            _safe_decline(
                failure_stage="provenance_review",
                failure_type="validation",
                failure_retryable=False,
                capture_nomination=draft_nomination,
                librarian_grounding_calls=_librarian_grounding(draft_tool_results),
                evidence_ids=_evidence_ids(candidate),
            ),
        )
    except Exception:
        return _record_release(
            span,
            _safe_decline(
                failure_stage="provenance_review",
                failure_type="model",
                failure_retryable=True,
                capture_nomination=draft_nomination,
                librarian_grounding_calls=_librarian_grounding(draft_tool_results),
                evidence_ids=_evidence_ids(candidate),
            ),
        )

    if _review_requires_emotional_boundary(review):
        return _record_release(
            span,
            emotional_boundary_release(
                origin="candidate_review",
                review_path=(review,),
                candidate=candidate,
                tool_results=draft_tool_results,
            ),
        )

    capture, capture_failure = _reviewed_capture(
        candidate,
        review,
        capture_source_text=capture_source_text,
        source_event_id=source_event_id,
        tool_results=draft_tool_results,
        release_scope=draft_release_scope,
        previously_released_evidence_ids=previously_released_evidence_ids,
    )

    if review.response_decision == "pass":
        try:
            _validate_release(
                candidate,
                draft_tool_results,
                draft_release_scope,
                previously_released_evidence_ids,
                _required_clarification(draft_routing),
                released_user_lines,
            )
        except ReleaseValidationError:
            return _record_release(
                span,
                _safe_decline(
                    verdicts=("pass",),
                    failure_stage="deterministic_validation",
                    failure_type="validation",
                    failure_retryable=False,
                    finding_codes=_codes(review),
                    capture_nomination=draft_nomination,
                    capture_decision=review.capture_decision,
                    automatic_capture_candidate=capture,
                    capture_failure=capture_failure,
                    librarian_grounding_calls=_librarian_grounding(draft_tool_results),
                    evidence_ids=_evidence_ids(candidate),
                    review_finding_codes=_review_codes(review),
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
                evidence_ids=_evidence_ids(candidate),
                review_finding_codes=_review_codes(review),
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
                evidence_ids=_evidence_ids(candidate),
                review_finding_codes=_review_codes(review),
            ),
        )

    try:
        revision_request = MuseRevisionInput(
            mode="revision",
            muse_turn=draft_input.muse_turn,
            context_resolution=draft_input.context_resolution,
            prior_evidence=draft_input.prior_evidence,
            review=MuseRevisionReview(findings=review.response_findings),
        ).model_dump_json()
    except Exception:
        return _record_release(
            span,
            _safe_decline(
                verdicts=("revise",),
                revision_count=1,
                failure_stage="muse_revision",
                failure_type="validation",
                failure_retryable=False,
                finding_codes=_codes(review),
                capture_nomination=draft_nomination,
                capture_decision=review.capture_decision,
                automatic_capture_candidate=capture,
                capture_failure=capture_failure,
                librarian_grounding_calls=_librarian_grounding(draft_tool_results),
                evidence_ids=_evidence_ids(candidate),
                review_finding_codes=_review_codes(review),
            ),
        )
    try:
        revision_result = await run_agent_traced(
            muse,
            revision_request,
            span_name="muse.revision",
            role="Muse",
            stage="revision",
            input_contract="apps.backend.contracts.MuseRevisionInput",
            output_contract="src.linger.agents.muse.models.MuseCandidate",
            input_origin="Provenance",
            prompt_template_id=REVISION_PROMPT_FINGERPRINT.template_id,
            prompt_version=REVISION_PROMPT_FINGERPRINT.version,
            prompt_digest=REVISION_PROMPT_FINGERPRINT.digest,
            failure_code="muse_revision_model_failed",
            message_history=[*history, *draft_result.new_messages()],
        )
    except Exception:
        return _record_release(
            span,
            _safe_decline(
                verdicts=("revise",),
                revision_count=1,
                failure_stage="muse_revision",
                failure_type="model",
                failure_retryable=True,
                finding_codes=_codes(review),
                capture_nomination=draft_nomination,
                capture_decision=review.capture_decision,
                automatic_capture_candidate=capture,
                capture_failure=capture_failure,
                librarian_grounding_calls=_librarian_grounding(draft_tool_results),
                evidence_ids=_evidence_ids(candidate),
                review_finding_codes=_review_codes(review),
            ),
        )
    try:
        revised_candidate = _candidate(revision_result.output)
        revised_tool_results = draft_tool_results + _tool_results(revision_result)
        revised_routing = _routing_responses(revised_tool_results)
    except Exception:
        return _record_release(
            span,
            _safe_decline(
                verdicts=("revise",),
                revision_count=1,
                failure_stage="muse_revision",
                failure_type="validation",
                failure_retryable=False,
                finding_codes=_codes(review),
                capture_nomination=draft_nomination,
                capture_decision=review.capture_decision,
                automatic_capture_candidate=capture,
                capture_failure=capture_failure,
                librarian_grounding_calls=_librarian_grounding(draft_tool_results),
                evidence_ids=_evidence_ids(candidate),
                review_finding_codes=_review_codes(review),
            ),
        )

    revised_release_scope = release_scope or _routed_release_scope(revised_routing)
    revised_review_context = _effective_review_context(review_context, revised_routing)
    revised_nomination = _nomination(revised_candidate)

    try:
        revised_review = await _review(
            revised_candidate,
            provenance,
            revised_review_context,
            revised_tool_results,
            capture_source_text,
            released_user_lines,
        )
    except ReleaseValidationError:
        return _record_release(
            span,
            _safe_decline(
                verdicts=("revise",),
                revision_count=1,
                failure_stage="provenance_review",
                failure_type="validation",
                failure_retryable=False,
                finding_codes=_codes(review),
                capture_nomination=draft_nomination,
                capture_decision=review.capture_decision,
                automatic_capture_candidate=capture,
                capture_failure=capture_failure,
                librarian_grounding_calls=_librarian_grounding(revised_tool_results),
                evidence_ids=_evidence_ids(candidate),
                review_finding_codes=_review_codes(review),
            ),
        )
    except Exception:
        return _record_release(
            span,
            _safe_decline(
                verdicts=("revise",),
                revision_count=1,
                failure_stage="provenance_review",
                failure_type="model",
                failure_retryable=True,
                finding_codes=_codes(review),
                capture_nomination=draft_nomination,
                capture_decision=review.capture_decision,
                automatic_capture_candidate=capture,
                capture_failure=capture_failure,
                librarian_grounding_calls=_librarian_grounding(revised_tool_results),
                evidence_ids=_evidence_ids(candidate),
                review_finding_codes=_review_codes(review),
            ),
        )
    if _review_requires_emotional_boundary(revised_review):
        return _record_release(
            span,
            emotional_boundary_release(
                origin="candidate_review",
                review_path=(review, revised_review),
                candidate=revised_candidate,
                tool_results=revised_tool_results,
            ),
        )

    capture, capture_failure = _reviewed_capture(
        revised_candidate,
        revised_review,
        capture_source_text=capture_source_text,
        source_event_id=source_event_id,
        tool_results=revised_tool_results,
        release_scope=revised_release_scope,
        previously_released_evidence_ids=previously_released_evidence_ids,
    )

    if revised_review.response_decision == "pass":
        try:
            _validate_release(
                revised_candidate,
                revised_tool_results,
                revised_release_scope,
                previously_released_evidence_ids,
                _required_clarification(revised_routing),
                released_user_lines,
            )
        except ReleaseValidationError:
            return _record_release(
                span,
                _safe_decline(
                    verdicts=("revise", "pass"),
                    revision_count=1,
                    failure_stage="deterministic_validation",
                    failure_type="validation",
                    failure_retryable=False,
                    finding_codes=_codes(review, revised_review),
                    capture_nomination=revised_nomination,
                    capture_decision=revised_review.capture_decision,
                    automatic_capture_candidate=capture,
                    capture_failure=capture_failure,
                    librarian_grounding_calls=_librarian_grounding(revised_tool_results),
                    evidence_ids=_evidence_ids(revised_candidate),
                    review_finding_codes=_review_codes(review, revised_review),
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
                evidence_ids=_evidence_ids(revised_candidate),
                review_finding_codes=_review_codes(review, revised_review),
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
            evidence_ids=_evidence_ids(revised_candidate),
            review_finding_codes=_review_codes(review, revised_review),
        ),
    )
