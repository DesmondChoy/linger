"""Application-owned Muse-to-Provenance release flow."""

import json
from dataclasses import dataclass
from typing import Any, Literal, Mapping

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ToolReturnPart
from pydantic_core import to_jsonable_python

from src.linger.agents.provenance.models import ProvenanceReview

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


def _safe_decline(
    *,
    verdicts: tuple[Literal["pass", "revise", "reject"], ...] = (),
    critiques: tuple[str, ...] = (),
    revision_count: int = 0,
    failure_stage: Literal["muse_draft", "provenance_review", "muse_revision"] | None = None,
) -> ReflectionRelease:
    return ReflectionRelease(
        reply=SAFE_DECLINE,
        release_source="application_safe_decline",
        provenance_verdicts=verdicts,
        critiques=critiques,
        revision_count=revision_count,
        failure_stage=failure_stage,
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
) -> ProvenanceVerdict:
    payload = json.dumps(
        {**review_context, "candidate_response": candidate},
        ensure_ascii=False,
    )
    result = await provenance.run(payload)
    return result.output


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
    draft_result = await muse.run(message, message_history=history)
    candidate = draft_result.output.strip()
    if not candidate:
        return _safe_decline(failure_stage="muse_draft")
    draft_tool_results = _tool_results(draft_result)
    draft_review_context = _context_with_tool_results(review_context, draft_tool_results)

    try:
        review = await _review(candidate, provenance, draft_review_context)
    except Exception:
        return _safe_decline(failure_stage="provenance_review")

    if review.decision == "pass":
        return ReflectionRelease(
            reply=candidate,
            release_source="muse_candidate",
            provenance_verdicts=("pass",),
            critiques=(review.critique,),
        )
    if review.decision != "revise":
        return _safe_decline(
            verdicts=(review.decision,),
            critiques=(review.critique,),
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
        revision_result = await muse.run(revision_request, message_history=history)
    except Exception:
        return _safe_decline(
            verdicts=("revise",),
            critiques=(verdict.critique,),
            revision_count=1,
            failure_stage="muse_revision",
        )

    revised_candidate = revision_result.output.strip()
    if not revised_candidate:
        return _safe_decline(
            verdicts=("revise",),
            critiques=(verdict.critique,),
            revision_count=1,
            failure_stage="muse_revision",
        )

    try:
        revised_tool_results = draft_tool_results + _tool_results(revision_result)
        revised_verdict = await _review(
            revised_candidate,
            provenance,
            _context_with_tool_results(review_context, revised_tool_results),
        )
    except Exception:
        return _safe_decline(
            verdicts=("revise",),
            critiques=(verdict.critique,),
            revision_count=1,
            failure_stage="provenance_review",
        )

    if revised_verdict.decision == "pass":
        return ReflectionRelease(
            reply=revised_candidate,
            release_source="muse_candidate",
            provenance_verdicts=("revise", "pass"),
            critiques=(verdict.critique, revised_verdict.critique),
            revision_count=1,
        )
    return _safe_decline(
        verdicts=("revise", revised_verdict.decision),
        critiques=(verdict.critique, revised_verdict.critique),
        revision_count=1,
    )
