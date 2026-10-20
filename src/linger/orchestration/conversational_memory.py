"""Application-owned trigger for capture-triggered conversational curation."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Sequence
from typing import Literal, Protocol

import bm25s
import numpy as np
from pydantic import Field

from src.linger.contracts.base import StrictModel
from src.linger.contracts.curation import CurationCandidate
from src.linger.orchestration.curation import CurationLoopResult, run_curation_loop
from src.linger.services.memory import AccountContext, MemoryPolicyService, MemoryRecord

# Below this cosine similarity an earlier memory is never shown to Sculptor.
# Measured on bge-small-en-v1.5: same-event pairs score from about 0.50 and
# the median pair of all saved memories scores 0.47, so the floor drops
# clearly unrelated memories without losing related ones.
SEMANTIC_FLOOR = 0.5
EARLIER_LIMIT = 11
# Reciprocal rank fusion constant, as in the hybrid Librarian.
RRF_K = 60


class EmbeddingModel(Protocol):
    def passage_embed(self, documents: list[str]) -> Iterable[Sequence[float]]: ...
    def query_embed(self, query: str) -> Iterable[Sequence[float]]: ...


def _unit(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return np.divide(vectors, norms, out=np.zeros_like(vectors), where=norms > 0)


def _keyword_ranks(query: str, texts: list[str]) -> dict[int, int]:
    """Rank texts by BM25 against the query; texts with no matching term get no rank."""
    query_tokens = bm25s.tokenize(query, stopwords="en_plus", return_ids=False, show_progress=False)[0]
    if not query_tokens:
        return {}
    corpus = bm25s.tokenize(texts, stopwords="en_plus", show_progress=False)
    if not corpus.vocab:
        return {}
    retriever = bm25s.BM25()
    retriever.index(corpus, show_progress=False)
    scores = retriever.get_scores(query_tokens)
    matched = sorted((index for index in range(len(texts)) if scores[index] > 0), key=lambda index: -scores[index])
    return {index: rank for rank, index in enumerate(matched)}


# How many of the best unselected candidates to record beside the batch.
NEAR_MISS_LIMIT = 5


def _rank_relevant(
    query: str,
    records: Sequence[MemoryRecord],
    *,
    embedding: EmbeddingModel,
    limit: int,
) -> tuple[CurationCandidate, ...]:
    """Fuse meaning and keyword rankings; select only memories close enough in meaning.

    Returns the selected candidates in fused order, then the nearest unselected ones.
    """
    if not records:
        return ()
    texts = [record.text for record in records]
    passages = _unit(np.asarray(list(embedding.passage_embed(texts)), dtype=float))
    question = _unit(np.asarray(next(iter(embedding.query_embed(query))), dtype=float))
    similarity = passages @ question
    by_meaning = sorted(range(len(texts)), key=lambda index: (-similarity[index], records[index].memory_id))
    semantic = {index: rank for rank, index in enumerate(by_meaning)}
    keyword = _keyword_ranks(query, texts)
    fused = sorted(
        (index for index in range(len(texts)) if similarity[index] >= SEMANTIC_FLOOR),
        key=lambda index: (
            -(
                1 / (RRF_K + semantic[index] + 1)
                + (1 / (RRF_K + keyword[index] + 1) if index in keyword else 0.0)
            ),
            records[index].memory_id,
        ),
    )
    selected = fused[:limit]
    chosen = set(selected)
    near_misses = [index for index in by_meaning if index not in chosen][:NEAR_MISS_LIMIT]

    def candidate(index: int) -> CurationCandidate:
        return CurationCandidate(
            memory_id=records[index].memory_id,
            similarity=round(float(similarity[index]), 3),
            keyword_rank=keyword[index] + 1 if index in keyword else None,
            selected=index in chosen,
        )

    return tuple(candidate(index) for index in (*selected, *near_misses))


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
    # How many earlier originals were scored, and the batch plus its nearest misses.
    scored_count: int = 0
    candidates: tuple[CurationCandidate, ...] = Field(
        default=(), max_length=EARLIER_LIMIT + NEAR_MISS_LIMIT
    )


CurationRunner = Callable[..., Awaitable[CurationLoopResult]]


async def curate_after_capture(
    context: AccountContext,
    captured: MemoryRecord,
    *,
    created: bool,
    service: MemoryPolicyService,
    embedding: EmbeddingModel,
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
        # Embedding is CPU-bound; keep it off the event loop.
        candidates = await asyncio.to_thread(
            _rank_relevant, captured.text, earlier, embedding=embedding, limit=EARLIER_LIMIT
        )
    except Exception:
        return ConversationalCurationOutcome(
            status="failed",
            memory_ids=(captured.memory_id,),
        )
    scores = {"scored_count": len(earlier), "candidates": candidates}
    relevant = tuple(item.memory_id for item in candidates if item.selected)
    if not relevant:
        return ConversationalCurationOutcome(
            status="no_relevant_prior_memory",
            memory_ids=(captured.memory_id,),
            **scores,
        )
    memory_ids = (captured.memory_id, *relevant)
    try:
        result = await run_loop(context, memory_ids, service=service)
    except Exception:
        return ConversationalCurationOutcome(status="failed", memory_ids=memory_ids, **scores)
    return ConversationalCurationOutcome(
        status=result.status,
        memory_ids=memory_ids,
        proposal_digest=result.proposal_digest,
        **scores,
    )
