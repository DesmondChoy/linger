"""Application-owned trigger for capture-triggered conversational curation."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Sequence
from typing import Literal

from pydantic import Field

from src.linger.agents.contracts import StrictModel
from src.linger.orchestration.curation import CurationLoopResult, run_curation_loop
from src.linger.services.memory import AccountContext, MemoryPolicyService, MemoryRecord

_TOKEN = re.compile(r"[\w’'-]+", re.UNICODE)
_LOW_SIGNAL_TOKENS = frozenset({
    "a", "am", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "i", "in", "is", "it", "my", "of", "on", "or", "that", "the", "this",
    "to", "was", "with",
})


def _tokens(text: str) -> frozenset[str]:
    return frozenset(
        normalised
        for token in _TOKEN.findall(text)
        if (normalised := token.casefold()) not in _LOW_SIGNAL_TOKENS
    )


def _rank_relevant(
    query: str,
    records: Sequence[MemoryRecord],
    *,
    limit: int,
) -> tuple[MemoryRecord, ...]:
    query_tokens = _tokens(query)
    ranked = sorted(
        (
            (len(query_tokens & _tokens(record.text)), record)
            for record in records
        ),
        key=lambda item: (-item[0], item[1].memory_id),
    )
    return tuple(record for overlap, record in ranked[:limit] if overlap > 0)


class ConversationalCurationOutcome(StrictModel):
    """Content-free outcome of the capture-triggered curation hook."""

    status: Literal[
        "not_triggered",
        "no_relevant_prior_memory",
        "no_change",
        "provenance_revise",
        "provenance_reject",
        "applied",
        "failed",
    ]
    memory_ids: tuple[str, ...] = Field(max_length=12)
    proposal_digest: str | None = None


CurationRunner = Callable[..., Awaitable[CurationLoopResult]]


async def curate_after_capture(
    context: AccountContext,
    captured: MemoryRecord,
    *,
    created: bool,
    service: MemoryPolicyService,
    run_loop: CurationRunner = run_curation_loop,
) -> ConversationalCurationOutcome:
    """Run reviewed curation once for a new capture and relevant originals."""

    if not created:
        return ConversationalCurationOutcome(status="not_triggered", memory_ids=())
    try:
        earlier = tuple(
            record
            for record in service.list_active(context)
            if record.memory_id != captured.memory_id
        )
        relevant = _rank_relevant(captured.text, earlier, limit=11)
    except Exception:
        return ConversationalCurationOutcome(
            status="failed",
            memory_ids=(captured.memory_id,),
        )
    if not relevant:
        return ConversationalCurationOutcome(
            status="no_relevant_prior_memory",
            memory_ids=(captured.memory_id,),
        )
    memory_ids = (captured.memory_id, *(record.memory_id for record in relevant))
    try:
        result = await run_loop(context, memory_ids, service=service)
    except Exception:
        return ConversationalCurationOutcome(status="failed", memory_ids=memory_ids)
    return ConversationalCurationOutcome(
        status=result.status,
        memory_ids=memory_ids,
        proposal_digest=result.proposal_digest,
    )
