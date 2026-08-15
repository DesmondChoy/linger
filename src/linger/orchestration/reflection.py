"""Application-owned Muse-to-Provenance release flow."""

import json

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage

from src.linger.agents.provenance.models import ProvenanceReview

SAFE_DECLINE = "I’m sorry, but I can’t provide a reliable response to that right now."


async def _review(
    candidate: str,
    provenance: Agent[None, ProvenanceReview],
) -> ProvenanceReview:
    payload = json.dumps({"candidate_response": candidate}, ensure_ascii=False)
    result = await provenance.run(payload)
    return result.output


async def reflection_reply(
    message: str,
    history: list[ModelMessage],
    *,
    muse: Agent[None, str],
    provenance: Agent[None, ProvenanceReview],
) -> str:
    """Return only approved output, with at most one reviewed revision.

    Only `response_decision` is read here. A rejected memory candidate never
    suppresses an otherwise safe response (specification section 4.1); capture
    is handled separately by `orchestration.capture`.
    """
    draft_result = await muse.run(message, message_history=history)
    candidate = draft_result.output.strip()
    if not candidate:
        return SAFE_DECLINE

    try:
        review = await _review(candidate, provenance)
    except Exception:
        return SAFE_DECLINE

    if review.response_decision == "pass":
        return candidate
    if review.response_decision != "revise":
        return SAFE_DECLINE

    revision_request = json.dumps(
        {
            "task": "Revise the candidate once to address the review critique.",
            "original_user_message": message,
            "candidate_response": candidate,
            "review_critique": review.critique(),
        },
        ensure_ascii=False,
    )
    try:
        revision_result = await muse.run(revision_request, message_history=history)
        revised_candidate = revision_result.output.strip()
        if not revised_candidate:
            return SAFE_DECLINE
        revised_review = await _review(revised_candidate, provenance)
    except Exception:
        return SAFE_DECLINE

    if revised_review.response_decision == "pass":
        return revised_candidate
    return SAFE_DECLINE
