"""Application-owned Muse-to-Provenance release flow."""

import json

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage

from src.linger.agents.provenance.models import ProvenanceVerdict

SAFE_DECLINE = "I’m sorry, but I can’t provide a reliable response to that right now."


async def _review(
    candidate: str,
    provenance: Agent[None, ProvenanceVerdict],
) -> ProvenanceVerdict:
    payload = json.dumps({"candidate_response": candidate}, ensure_ascii=False)
    result = await provenance.run(payload)
    return result.output


async def reflection_reply(
    message: str,
    history: list[ModelMessage],
    *,
    muse: Agent[None, str],
    provenance: Agent[None, ProvenanceVerdict],
) -> str:
    """Return only approved output, with at most one reviewed revision."""
    draft_result = await muse.run(message, message_history=history)
    candidate = draft_result.output.strip()
    if not candidate:
        return SAFE_DECLINE

    try:
        verdict = await _review(candidate, provenance)
    except Exception:
        return SAFE_DECLINE

    if verdict.decision == "pass":
        return candidate
    if verdict.decision != "revise":
        return SAFE_DECLINE

    revision_request = json.dumps(
        {
            "task": "Revise the candidate once to address the review critique.",
            "original_user_message": message,
            "candidate_response": candidate,
            "review_critique": verdict.critique,
        },
        ensure_ascii=False,
    )
    try:
        revision_result = await muse.run(revision_request, message_history=history)
        revised_candidate = revision_result.output.strip()
        if not revised_candidate:
            return SAFE_DECLINE
        revised_verdict = await _review(revised_candidate, provenance)
    except Exception:
        return SAFE_DECLINE

    if revised_verdict.decision == "pass":
        return revised_candidate
    return SAFE_DECLINE
