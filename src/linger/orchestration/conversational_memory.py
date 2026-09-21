"""Application-owned triggers for conversational curation and surfacing."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Literal

from pydantic import Field

from src.linger.agents.contracts import StrictModel
from src.linger.agents.sculptor.models import CuratableMemory
from src.linger.agents.sculptor.surfacing_models import (
    PriorSurfacing,
    SurfaceNow,
    SurfacingContext,
    SurfacingDecision,
    SurfacingInput,
)
from src.linger.contracts.connection_evidence import MemoryConnectionEvidence
from src.linger.contracts.curation import CuratedMemory
from src.linger.contracts.surfacing import MemorySurfacingHandoff
from src.linger.orchestration.curation import CurationLoopResult, run_curation_loop
from src.linger.orchestration.surfacing import propose_surfacing
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
    records: Sequence[CuratedMemory | MemoryRecord],
    *,
    limit: int,
) -> tuple[CuratedMemory | MemoryRecord, ...]:
    query_tokens = _tokens(query)
    ranked = sorted(
        (
            (len(query_tokens & _tokens(record.text)), record)
            for record in records
        ),
        key=lambda item: (-item[0], item[1].memory_id),
    )
    return tuple(record for overlap, record in ranked[:limit] if overlap > 0)


def select_relevant_memories(
    current_context: str,
    memories: Sequence[CuratedMemory],
    *,
    limit: int = 12,
) -> tuple[CuratedMemory, ...]:
    """Return a deterministic bounded subset with positive lexical overlap."""

    if not current_context.strip():
        raise ValueError("current context must not be blank")
    if not 1 <= limit <= 12:
        raise ValueError("memory selection limit must be between 1 and 12")
    return tuple(_rank_relevant(current_context, memories, limit=limit))  # type: ignore[return-value]


SurfacingDecider = Callable[[SurfacingInput], Awaitable[SurfacingDecision]]


async def prepare_surfacing_handoff(
    *,
    account_scope: str,
    current_context: str,
    memories: Sequence[CuratedMemory],
    now: datetime,
    history: tuple[PriorSurfacing, ...] = (),
    decide: SurfacingDecider = propose_surfacing,
) -> MemorySurfacingHandoff | None:
    """Ask Sculptor about relevant state and bind a surface-now decision."""

    selected = select_relevant_memories(current_context, memories)
    if not selected:
        return None
    decision = await decide(
        SurfacingInput(
            account_scope=account_scope,
            context=SurfacingContext(
                now=now,
                current_context=current_context,
                history=history,
            ),
            memories=tuple(
                CuratableMemory(memory_id=item.memory_id, text=item.text)
                for item in selected
            ),
        )
    )
    if not isinstance(decision, SurfaceNow):
        return None
    by_id = {item.memory_id: item for item in selected}
    sources = tuple(
        MemoryConnectionEvidence(
            evidence_id=memory_id,
            excerpt=by_id[memory_id].text,
        )
        for memory_id in decision.source_memory_ids
    )
    return MemorySurfacingHandoff(
        suggestion=decision.suggestion,
        source_memory_ids=decision.source_memory_ids,
        sources=sources,
    )


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
