"""Application-owned Muse-to-Provenance release flow."""

import json
from dataclasses import dataclass
from typing import Any, Literal, Mapping

import logfire
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ToolReturnPart
from pydantic_core import to_jsonable_python

from apps.backend.telemetry import review_attrs, review_context_attrs
from src.linger.agents.provenance.models import ProvenanceReview, RiskCode

SAFE_DECLINE = "I’m sorry, but I can’t provide a reliable response to that right now."


@dataclass(frozen=True)
class ReflectionRelease:
    """The released text and the real path that authorised it."""

    reply: str
    release_source: Literal["muse_candidate", "application_safe_decline"]
    provenance_verdicts: tuple[Literal["pass", "revise", "reject"], ...] = ()
    critiques: tuple[str, ...] = ()
    revision_count: int = 0
    failure_stage: Literal["muse_draft", "provenance_review", "muse_revision"] | None = None
    # Why Provenance blocked, as bare risk codes. `critiques` carries the same
    # findings rendered as prose with the offending quote, which specification
    # section 8.1 bars from logs; the codes are a fixed enum and are loggable.
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
    critiques: tuple[str, ...] = (),
    revision_count: int = 0,
    failure_stage: Literal["muse_draft", "provenance_review", "muse_revision"] | None = None,
    finding_codes: tuple[RiskCode, ...] = (),
) -> ReflectionRelease:
    return ReflectionRelease(
        reply=SAFE_DECLINE,
        release_source="application_safe_decline",
        provenance_verdicts=verdicts,
        critiques=critiques,
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
        for message in run_result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart)
        and part.tool_name in {"librarian_search", "serendipity_explore"}
    ]


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
    candidate: str,
    provenance: Agent[None, ProvenanceReview],
    review_context: Mapping[str, object],
) -> ProvenanceReview:
    payload = json.dumps(
        {**review_context, "candidate_response": candidate},
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
    muse: Agent[None, str],
    provenance: Agent[None, ProvenanceReview],
    review_context: Mapping[str, object] | None = None,
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
            span=span,
        )


def _record_release(span: Any, release: ReflectionRelease) -> ReflectionRelease:
    """Attach the release outcome to the parent span.

    Every field here is an enum, tuple of enums, or int, so §8.1 permits all of
    them — `finding_codes` included, being a fixed `RiskCode` enum. `critiques`
    is excluded: the same findings rendered as prose quote the candidate
    response verbatim.
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
    muse: Agent[None, str],
    provenance: Agent[None, ProvenanceReview],
    review_context: Mapping[str, object],
    span: Any,
) -> ReflectionRelease:
    """The release flow, with the parent span threaded through for attributes."""
    with logfire.span("muse.draft"):
        draft_result = await muse.run(message, message_history=history)
    candidate = draft_result.output.strip()
    if not candidate:
        return _record_release(span, _safe_decline(failure_stage="muse_draft"))
    draft_tool_results = _tool_results(draft_result)
    draft_review_context = _context_with_tool_results(review_context, draft_tool_results)

    try:
        review = await _review(candidate, provenance, draft_review_context)
    except Exception as exc:
        span.record_exception(exc)
        return _record_release(span, _safe_decline(failure_stage="provenance_review"))

    if review.response_decision == "pass":
        return _record_release(
            span,
            ReflectionRelease(
                reply=candidate,
                release_source="muse_candidate",
                provenance_verdicts=("pass",),
                critiques=(review.critique(),),
                finding_codes=_codes(review),
            ),
        )
    if review.response_decision != "revise":
        return _record_release(
            span,
            _safe_decline(
                verdicts=(review.response_decision,),
                critiques=(review.critique(),),
                finding_codes=_codes(review),
            ),
        )

    revision_request = json.dumps(
        {
            "task": "Revise the candidate once to address the review critique.",
            "original_muse_input": message,
            "candidate_response": candidate,
            "review_critique": review.critique(),
        },
        ensure_ascii=False,
    )
    try:
        with logfire.span("muse.revision"):
            revision_result = await muse.run(revision_request, message_history=history)
    except Exception as exc:
        span.record_exception(exc)
        return _record_release(
            span,
            _safe_decline(
                verdicts=("revise",),
                critiques=(review.critique(),),
                revision_count=1,
                failure_stage="muse_revision",
                finding_codes=_codes(review),
            ),
        )

    revised_candidate = revision_result.output.strip()
    if not revised_candidate:
        return _record_release(
            span,
            _safe_decline(
                verdicts=("revise",),
                critiques=(review.critique(),),
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
                critiques=(review.critique(),),
                revision_count=1,
                failure_stage="provenance_review",
                finding_codes=_codes(review),
            ),
        )

    if revised_review.response_decision == "pass":
        return _record_release(
            span,
            ReflectionRelease(
                reply=revised_candidate,
                release_source="muse_candidate",
                provenance_verdicts=("revise", "pass"),
                critiques=(review.critique(), revised_review.critique()),
                revision_count=1,
                finding_codes=_codes(review, revised_review),
            ),
        )
    return _record_release(
        span,
        _safe_decline(
            verdicts=("revise", revised_review.response_decision),
            critiques=(review.critique(), revised_review.critique()),
            revision_count=1,
            finding_codes=_codes(review, revised_review),
        ),
    )
