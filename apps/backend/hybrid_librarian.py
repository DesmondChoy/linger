"""Selected spoiler-bounded hybrid retrieval strategy for Librarian."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

import bm25s
import numpy as np

from apps.backend.contracts import (
    BookScope,
    EvidenceBundle,
    EvidenceItem,
    LibrarianRequest,
)
from apps.backend.librarian import (
    CorpusScopeError,
    Librarian,
    Paragraph,
    _paragraphs,
)
from src.linger.corpus.units import CorpusUnit, read_unit
from src.linger.corpus import registry


EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
RERANKER_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"
TARGET_WORDS = 350
OVERLAP_WORDS = 60
KEYWORD_CANDIDATES = 10
SEMANTIC_CANDIDATES = 10
MAX_RERANKER_CANDIDATES = 15
RRF_K = 60
OVERLAP_DEDUPE_THRESHOLD = 0.5


class EmbeddingModel(Protocol):
    def passage_embed(self, documents: list[str]): ...
    def query_embed(self, query: str): ...


class RerankerModel(Protocol):
    def rerank(self, query: str, documents: list[str]): ...


@dataclass(frozen=True)
class Candidate:
    metadata: CorpusUnit
    text: str
    source_lines: tuple[int, int]
    score: float = 0.0

    @property
    def evidence_id(self) -> str:
        start, end = self.source_lines
        return f"{self.metadata.chapter_id}-ln{start:04d}-{end:04d}"


@dataclass(frozen=True)
class HybridIndex:
    candidates: tuple[Candidate, ...]
    embeddings: np.ndarray
    bm25: bm25s.BM25


def _word_count(text: str) -> int:
    return len(text.split())


def _windows(metadata: CorpusUnit, paragraphs: tuple[Paragraph, ...]) -> list[Candidate]:
    """Build exact, overlapping search windows without crossing a chapter."""
    windows: list[Candidate] = []
    start = 0
    while start < len(paragraphs):
        end = start
        words = 0
        while end < len(paragraphs):
            paragraph_words = _word_count(paragraphs[end].text)
            if end > start and words + paragraph_words > TARGET_WORDS:
                break
            words += paragraph_words
            end += 1
        if end == start:
            end += 1

        selected = paragraphs[start:end]
        windows.append(
            Candidate(
                metadata=metadata,
                text="\n\n".join(paragraph.text for paragraph in selected),
                source_lines=(selected[0].source_lines[0], selected[-1].source_lines[1]),
            )
        )
        if end >= len(paragraphs):
            break

        next_start = end
        overlap = 0
        while next_start > start and overlap < OVERLAP_WORDS:
            next_start -= 1
            overlap += _word_count(paragraphs[next_start].text)
        start = end if next_start <= start else next_start
    return windows


def _cosine(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    denominator = np.maximum(np.linalg.norm(matrix, axis=1) * np.linalg.norm(query), 1e-12)
    return matrix @ query / denominator


def _strongly_overlaps(left: Candidate, right: Candidate) -> bool:
    if left.metadata.chapter_id != right.metadata.chapter_id:
        return False
    left_start, left_end = left.source_lines
    right_start, right_end = right.source_lines
    intersection = max(0, min(left_end, right_end) - max(left_start, right_start) + 1)
    shorter = min(left_end - left_start + 1, right_end - right_start + 1)
    return intersection / shorter >= OVERLAP_DEDUPE_THRESHOLD


def _dedupe(candidates: list[Candidate], limit: int) -> list[Candidate]:
    selected: list[Candidate] = []
    for candidate in candidates:
        if any(_strongly_overlaps(candidate, existing) for existing in selected):
            continue
        selected.append(candidate)
        if len(selected) == limit:
            break
    return selected


class HybridLibrarian(Librarian):
    """BM25 + embeddings + reciprocal-rank fusion + local cross-encoder."""

    def __init__(
        self,
        *,
        embedding_model: EmbeddingModel | None = None,
        reranker: RerankerModel | None = None,
    ) -> None:
        self._embedding = embedding_model
        self._reranker = reranker
        self._indexes: dict[tuple[tuple[str, str, str, int, tuple[str, ...]], ...], HybridIndex] = {}

    def _embedding_model(self) -> EmbeddingModel:
        if self._embedding is None:
            from fastembed import TextEmbedding

            self._embedding = TextEmbedding(model_name=EMBEDDING_MODEL)
        return self._embedding

    def _reranker_model(self) -> RerankerModel:
        if self._reranker is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            self._reranker = TextCrossEncoder(model_name=RERANKER_MODEL)
        return self._reranker

    def _eligible_windows(self, request: LibrarianRequest) -> list[Candidate]:
        candidates: list[Candidate] = []
        for scope in request.book_scopes:
            registration, eligible = self.eligible_units(scope)
            for unit in eligible:
                try:
                    metadata, body = read_unit(registration, unit)
                except (OSError, ValueError) as exc:
                    raise CorpusScopeError(str(exc)) from exc
                candidates.extend(_windows(metadata, _paragraphs(metadata, body)))
        return candidates

    @staticmethod
    def _scope_key(request: LibrarianRequest) -> tuple[tuple[str, str, str, int, tuple[str, ...]], ...]:
        return tuple(sorted(
            (scope.work_id, scope.book_version_id, scope.part_id, scope.chapter_max or 0, tuple(sorted(scope.unit_ids)))
            for scope in request.book_scopes
        ))

    def _index(self, request: LibrarianRequest) -> HybridIndex:
        scopes: list[BookScope] = []
        for scope in request.book_scopes:
            if scope.unit_ids:
                # Validate membership even when an index is already cached.
                self.eligible_units(scope)
                scopes.append(scope)
                continue
            registered = self.registered_scope(scope.work_id, scope.book_version_id, scope.part_id)
            if registered is None or scope.chapter_max is None:
                raise CorpusScopeError("unregistered chapter scope")
            scopes.append(scope.model_copy(update={"chapter_max": min(scope.chapter_max, registered.max_chapter)}))
        request = request.model_copy(update={"book_scopes": scopes})
        key = self._scope_key(request)
        cached = self._indexes.get(key)
        if cached is not None:
            return cached

        candidates = self._eligible_windows(request)
        retriever = bm25s.BM25()
        if candidates:
            texts = [candidate.text for candidate in candidates]
            retriever.index(
                bm25s.tokenize(texts, show_progress=False), show_progress=False
            )
            embeddings = np.asarray(
                list(self._embedding_model().passage_embed(texts))
            )
        else:
            embeddings = np.empty((0, 0))
        built = HybridIndex(tuple(candidates), embeddings, retriever)
        self._indexes[key] = built
        return built

    @staticmethod
    def _bm25(query: str, index: HybridIndex) -> list[Candidate]:
        ids, scores = index.bm25.retrieve(
            bm25s.tokenize(query, show_progress=False),
            k=min(KEYWORD_CANDIDATES, len(index.candidates)),
            show_progress=False,
        )
        return [
            Candidate(candidate.metadata, candidate.text, candidate.source_lines, float(score))
            for candidate, score in zip(
                (index.candidates[int(candidate_index)] for candidate_index in ids[0]),
                scores[0],
                strict=True,
            )
            if float(score) > 0
        ]

    def _semantic(
        self,
        query: str,
        index: HybridIndex,
        threshold: float,
    ) -> list[Candidate]:
        model = self._embedding_model()
        query_embedding = np.asarray(next(iter(model.query_embed(query))))
        scores = _cosine(query_embedding, index.embeddings)
        order = np.argsort(-scores)[:SEMANTIC_CANDIDATES]
        return [
            Candidate(
                index.candidates[int(candidate_index)].metadata,
                index.candidates[int(candidate_index)].text,
                index.candidates[int(candidate_index)].source_lines,
                float(scores[candidate_index]),
            )
            for candidate_index in order
            if float(scores[candidate_index]) >= threshold
        ]

    @staticmethod
    def _fuse(keyword: list[Candidate], semantic: list[Candidate]) -> list[Candidate]:
        by_id: dict[str, Candidate] = {}
        scores: dict[str, float] = {}
        for results in (keyword, semantic):
            for rank, candidate in enumerate(results, start=1):
                by_id[candidate.evidence_id] = candidate
                scores[candidate.evidence_id] = scores.get(candidate.evidence_id, 0.0) + 1 / (
                    RRF_K + rank
                )
        ranked = [
            Candidate(item.metadata, item.text, item.source_lines, scores[evidence_id])
            for evidence_id, item in sorted(
                by_id.items(), key=lambda entry: -scores[entry[0]]
            )
        ]
        return _dedupe(ranked, MAX_RERANKER_CANDIDATES)

    def retrieve(self, request: LibrarianRequest) -> EvidenceBundle:
        return self._retrieve(request, recover_for_judgement=False)

    def retrieve_for_judgement(self, request: LibrarianRequest) -> EvidenceBundle:
        """Keep one below-cutoff candidate private until answerability is judged."""
        return self._retrieve(request, recover_for_judgement=True)

    def _retrieve(self, request: LibrarianRequest, *, recover_for_judgement: bool) -> EvidenceBundle:
        index = self._index(request)
        if not index.candidates:
            return EvidenceBundle(items=[], retrieval_note="No eligible chapter text was searched.")

        keyword = self._bm25(request.query, index)
        semantic = self._semantic(request.query, index, request.retrieval_score_threshold)
        fused = self._fuse(keyword, semantic)
        if not fused:
            return EvidenceBundle(items=[], retrieval_note="No candidate cleared retrieval thresholds.")

        raw_scores = self._reranker_model().rerank(
            request.query, [candidate.text for candidate in fused]
        )
        scored = sorted(
            (
                Candidate(
                    candidate.metadata,
                    candidate.text,
                    candidate.source_lines,
                    1 / (1 + math.exp(-float(score))),
                )
                for candidate, score in zip(fused, raw_scores, strict=True)
            ),
            key=lambda candidate: -candidate.score,
        )
        final = _dedupe(
            [
                candidate
                for candidate in scored
                if candidate.score >= request.retrieval_score_threshold
            ],
            request.max_results,
        )
        if not final and recover_for_judgement:
            final = scored[:1]

        items = [
            EvidenceItem(
                evidence_id=candidate.evidence_id,
                work_id=candidate.metadata.work_id,
                book_version_id=candidate.metadata.book_version_id,
                chapter_id=candidate.metadata.chapter_id,
                source_title=registry.CORPORA[candidate.metadata.work_id].book.title,
                location=(
                    f"{candidate.metadata.label} — "
                    f"{candidate.metadata.title}, source lines "
                    f"{candidate.source_lines[0]}-{candidate.source_lines[1]}"
                ),
                chapter=candidate.metadata.chapter_number,
                part_id=candidate.metadata.part_id,
                source_sha256=candidate.metadata.source_sha256,
                source_lines=candidate.source_lines,
                excerpt=candidate.text,
                relevance=candidate.score,
            )
            for candidate in final
        ]
        return EvidenceBundle(
            items=items,
            retrieval_note=(
                "The complete immutable work was searched privately for boundary inference; "
                "candidate passage text is not a disclosure grant."
                if request.purpose == "boundary_inference"
                else (
                    "Only exact text inside the validated request boundary was searched using "
                    "BM25, local semantic embeddings, reciprocal-rank fusion, and local reranking."
                )
            ),
        )
