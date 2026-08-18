"""Reproducible five-way retrieval benchmark for the immutable Alice corpus."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import bm25s
import numpy as np
from fastembed import TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.backend.contracts import BookScope, LibrarianRequest
from apps.backend.librarian import Librarian, _paragraphs
from src.linger.corpus.alice import BOOK, BOOK_VERSION_ID, WORK_ID
from src.linger.corpus.book import parse_chapter_markdown


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = Path(__file__).with_name("cases.json")
DEFAULT_REPORT = Path(__file__).with_name("report.json")
STRATEGIES = ("direct", "bm25", "semantic", "hybrid", "hybrid_reranked")
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
RERANKER_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"
TARGET_WORDS = 350
OVERLAP_WORDS = 60
QUALITY_EQUIVALENCE_MARGIN = 0.02
OVERLAP_DEDUPE_THRESHOLD = 0.5
MIN_EVIDENCE_RECALL = 0.90
MIN_CITATION_PRECISION = 0.95


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RelevantRange(StrictModel):
    chapter: int = Field(ge=1)
    start: int = Field(ge=1)
    end: int = Field(ge=1)

    @model_validator(mode="after")
    def ordered(self) -> "RelevantRange":
        if self.start > self.end:
            raise ValueError("relevant range is reversed")
        return self


class BenchmarkCase(StrictModel):
    case_id: str
    query: str = Field(min_length=1)
    chapter_max: int = Field(ge=1)
    expected_strength: Literal["sufficient", "weak", "none"]
    relevant_ranges: tuple[tuple[int, int, int], ...]
    required_ranges: tuple[tuple[int, int, int], ...] | None = None

    @model_validator(mode="after")
    def ranges_match_strength(self) -> "BenchmarkCase":
        for chapter, start, end in self.relevant_ranges:
            RelevantRange(chapter=chapter, start=start, end=end)
            if chapter > self.chapter_max:
                raise ValueError("gold evidence exceeds the spoiler boundary")
        for gold in self.required_ranges or ():
            chapter, start, end = gold
            RelevantRange(chapter=chapter, start=start, end=end)
            if chapter > self.chapter_max:
                raise ValueError("required evidence exceeds the spoiler boundary")
            if gold not in self.relevant_ranges:
                raise ValueError("required evidence must also be a relevant range")
        if (self.expected_strength == "none") != (not self.relevant_ranges):
            raise ValueError("none cases must be the only cases without gold evidence")
        return self

    @property
    def recall_ranges(self) -> tuple[tuple[int, int, int], ...]:
        """Evidence facts required for recall, excluding optional support."""
        return self.required_ranges or self.relevant_ranges


class BenchmarkSet(StrictModel):
    schema_version: Literal[1]
    book_version_id: Literal[BOOK_VERSION_ID]
    cases: tuple[BenchmarkCase, ...] = Field(min_length=1)


@dataclass(frozen=True)
class Window:
    evidence_id: str
    chapter: int
    source_lines: tuple[int, int]
    text: str


@dataclass(frozen=True)
class Hit:
    evidence_id: str
    chapter: int
    source_lines: tuple[int, int]
    text: str
    score: float


@dataclass(frozen=True)
class CaseMeasurement:
    recall: float
    precision: float
    strength_correct: bool
    forbidden_exposure: bool
    citations_resolve: bool
    evidence_tokens: int


def _strongly_overlaps(left: Hit, right: Hit) -> bool:
    if left.chapter != right.chapter:
        return False
    left_start, left_end = left.source_lines
    right_start, right_end = right.source_lines
    intersection = max(0, min(left_end, right_end) - max(left_start, right_start) + 1)
    shorter = min(left_end - left_start + 1, right_end - right_start + 1)
    return intersection / shorter >= OVERLAP_DEDUPE_THRESHOLD


def _dedupe_overlaps(hits: list[Hit], limit: int) -> list[Hit]:
    """Keep ranked evidence diverse by suppressing near-duplicate source windows."""
    selected: list[Hit] = []
    for hit in hits:
        if any(_strongly_overlaps(hit, existing) for existing in selected):
            continue
        selected.append(hit)
        if len(selected) == limit:
            break
    return selected


def load_cases(path: Path = DEFAULT_CASES) -> BenchmarkSet:
    return BenchmarkSet.model_validate_json(path.read_text(encoding="utf-8"))


def _word_count(text: str) -> int:
    return len(text.split())


def load_windows(target_words: int = TARGET_WORDS, overlap_words: int = OVERLAP_WORDS) -> tuple[Window, ...]:
    catalog = json.loads((BOOK.default_output / "catalog.json").read_text(encoding="utf-8"))
    source_lines = BOOK.default_source.read_text(encoding="utf-8").splitlines()
    windows: list[Window] = []
    for entry in catalog["chapters"]:
        metadata, body = parse_chapter_markdown(
            (BOOK.default_output / entry["path"]).read_text(encoding="utf-8")
        )
        paragraphs = _paragraphs(metadata, body)
        start = 0
        while start < len(paragraphs):
            end = start
            words = 0
            while end < len(paragraphs):
                paragraph_words = _word_count(paragraphs[end].text)
                if end > start and words + paragraph_words > target_words:
                    break
                words += paragraph_words
                end += 1
            if end == start:
                end += 1
            selected = paragraphs[start:end]
            line_start = selected[0].source_lines[0]
            line_end = selected[-1].source_lines[1]
            windows.append(
                Window(
                    evidence_id=f"{metadata.chapter_id}-ln{line_start:04d}-{line_end:04d}",
                    chapter=metadata.chapter_number,
                    source_lines=(line_start, line_end),
                    text="\n".join(source_lines[line_start - 1 : line_end]),
                )
            )
            if end >= len(paragraphs):
                break
            next_start = end
            overlap = 0
            while next_start > start and overlap < overlap_words:
                next_start -= 1
                overlap += _word_count(paragraphs[next_start].text)
            start = end if next_start <= start else next_start
    return tuple(windows)


def _cosine(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    query_norm = np.linalg.norm(query)
    matrix_norms = np.linalg.norm(matrix, axis=1)
    denominator = np.maximum(matrix_norms * query_norm, 1e-12)
    return matrix @ query / denominator


class BenchmarkRunner:
    def __init__(self, windows: tuple[Window, ...]) -> None:
        self.windows = windows
        self.librarian = Librarian()
        self.embedding_model = TextEmbedding(model_name=EMBEDDING_MODEL)
        self.embeddings = np.asarray(list(self.embedding_model.passage_embed([w.text for w in windows])))
        self.reranker = TextCrossEncoder(model_name=RERANKER_MODEL)
        self._bm25: dict[int, tuple[list[Window], bm25s.BM25]] = {}

    def _eligible(self, ceiling: int) -> tuple[list[Window], np.ndarray]:
        indices = [index for index, window in enumerate(self.windows) if window.chapter <= ceiling]
        return [self.windows[index] for index in indices], self.embeddings[indices]

    def _bm25_hits(self, query: str, ceiling: int, limit: int = 10) -> list[Hit]:
        if ceiling not in self._bm25:
            eligible, _ = self._eligible(ceiling)
            retriever = bm25s.BM25()
            retriever.index(
                bm25s.tokenize([window.text for window in eligible], show_progress=False),
                show_progress=False,
            )
            self._bm25[ceiling] = (eligible, retriever)
        eligible, retriever = self._bm25[ceiling]
        ids, scores = retriever.retrieve(
            bm25s.tokenize(query, show_progress=False),
            k=min(limit, len(eligible)),
            show_progress=False,
        )
        return [
            Hit(window.evidence_id, window.chapter, window.source_lines, window.text, float(score))
            for window, score in zip((eligible[int(index)] for index in ids[0]), scores[0], strict=True)
            if float(score) > 0
        ]

    def _semantic_hits(self, query: str, ceiling: int, limit: int = 10) -> list[Hit]:
        eligible, embeddings = self._eligible(ceiling)
        query_embedding = np.asarray(next(iter(self.embedding_model.query_embed(query))))
        scores = _cosine(query_embedding, embeddings)
        order = np.argsort(-scores)[:limit]
        return [
            Hit(eligible[int(index)].evidence_id, eligible[int(index)].chapter, eligible[int(index)].source_lines, eligible[int(index)].text, float(scores[index]))
            for index in order
            if float(scores[index]) >= 0.5
        ]

    @staticmethod
    def _fuse(bm25_hits: list[Hit], semantic_hits: list[Hit], limit: int = 15) -> list[Hit]:
        by_id: dict[str, Hit] = {}
        scores: dict[str, float] = {}
        for results in (bm25_hits, semantic_hits):
            for rank, hit in enumerate(results, start=1):
                by_id[hit.evidence_id] = hit
                scores[hit.evidence_id] = scores.get(hit.evidence_id, 0.0) + 1.0 / (60 + rank)
        ranked = [
            Hit(hit.evidence_id, hit.chapter, hit.source_lines, hit.text, scores[evidence_id])
            for evidence_id, hit in sorted(by_id.items(), key=lambda item: -scores[item[0]])
        ]
        return _dedupe_overlaps(ranked, limit)

    def search(self, strategy: str, case: BenchmarkCase) -> list[Hit]:
        if strategy == "direct":
            bundle = self.librarian.retrieve(
                LibrarianRequest(
                    query=case.query,
                    book_scopes=[BookScope(work_id=WORK_ID, book_version_id=BOOK_VERSION_ID, chapter_max=case.chapter_max)],
                    max_results=5,
                )
            )
            return [Hit(item.evidence_id, item.chapter, item.source_lines, item.excerpt, item.relevance) for item in bundle.items]
        bm25_hits = self._bm25_hits(case.query, case.chapter_max)
        if strategy == "bm25":
            return _dedupe_overlaps(bm25_hits, 5)
        semantic_hits = self._semantic_hits(case.query, case.chapter_max)
        if strategy == "semantic":
            return _dedupe_overlaps(semantic_hits, 5)
        fused = self._fuse(bm25_hits, semantic_hits)
        if strategy == "hybrid":
            return _dedupe_overlaps(fused, 5)
        if strategy == "hybrid_reranked":
            scores = list(self.reranker.rerank(case.query, [hit.text for hit in fused]))
            reranked = sorted(zip(fused, scores, strict=True), key=lambda pair: -pair[1])
            thresholded = [
                Hit(
                    hit.evidence_id,
                    hit.chapter,
                    hit.source_lines,
                    hit.text,
                    1 / (1 + math.exp(-float(score))),
                )
                for hit, score in reranked
                if 1 / (1 + math.exp(-float(score))) >= 0.5
            ]
            return _dedupe_overlaps(thresholded, 5)
        raise ValueError(f"unknown strategy: {strategy}")


def _overlaps(hit: Hit, gold: tuple[int, int, int]) -> bool:
    chapter, start, end = gold
    return hit.chapter == chapter and hit.source_lines[0] <= end and start <= hit.source_lines[1]


def _citation_resolves(hit: Hit, source_lines: list[str]) -> bool:
    start, end = hit.source_lines
    return hit.text == "\n".join(source_lines[start - 1 : end])


def measure(case: BenchmarkCase, hits: list[Hit], source_lines: list[str]) -> CaseMeasurement:
    matched_gold = {index for index, gold in enumerate(case.recall_ranges) if any(_overlaps(hit, gold) for hit in hits)}
    relevant_hits = [hit for hit in hits if any(_overlaps(hit, gold) for gold in case.relevant_ranges)]
    recall = len(matched_gold) / len(case.recall_ranges) if case.recall_ranges else float(not hits)
    precision = len(relevant_hits) / len(hits) if hits else 1.0
    if not relevant_hits:
        predicted_strength = "none"
    elif case.expected_strength == "weak" or recall < 1:
        predicted_strength = "weak"
    else:
        predicted_strength = "sufficient"
    return CaseMeasurement(
        recall=recall,
        precision=precision,
        strength_correct=predicted_strength == case.expected_strength,
        forbidden_exposure=any(hit.chapter > case.chapter_max for hit in hits),
        citations_resolve=all(_citation_resolves(hit, source_lines) for hit in hits),
        evidence_tokens=sum(_word_count(hit.text) for hit in hits),
    )


def percentile_95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def select_strategy(metrics: dict[str, dict[str, float | bool]]) -> str:
    eligible = [name for name, values in metrics.items() if values["safety_pass"] and values["citation_pass"]]
    if not eligible:
        raise RuntimeError("no retrieval strategy passed safety and citation gates")
    best_quality = max(float(metrics[name]["quality_score"]) for name in eligible)
    equivalent = [name for name in eligible if best_quality - float(metrics[name]["quality_score"]) <= QUALITY_EQUIVALENCE_MARGIN]
    return min(equivalent, key=lambda name: (float(metrics[name]["p95_latency_ms"]), float(metrics[name]["mean_evidence_tokens"]), float(metrics[name]["monetary_cost_usd"])))


def run_benchmark(
    repetitions: int = 3,
    *,
    target_words: int = TARGET_WORDS,
    overlap_words: int = OVERLAP_WORDS,
) -> dict[str, object]:
    benchmark_set = load_cases()
    runner = BenchmarkRunner(load_windows(target_words, overlap_words))
    source_lines = BOOK.default_source.read_text(encoding="utf-8").splitlines()
    metrics: dict[str, dict[str, float | bool]] = {}
    case_results: dict[str, list[dict[str, object]]] = {}
    for strategy in STRATEGIES:
        measurements: list[CaseMeasurement] = []
        latencies: list[float] = []
        details: list[dict[str, object]] = []
        for case in benchmark_set.cases:
            hits: list[Hit] = []
            for _ in range(repetitions):
                started = time.perf_counter()
                hits = runner.search(strategy, case)
                latencies.append((time.perf_counter() - started) * 1000)
            result = measure(case, hits, source_lines)
            measurements.append(result)
            details.append({"case_id": case.case_id, "evidence_ids": [hit.evidence_id for hit in hits], "recall": result.recall, "precision": result.precision, "strength_correct": result.strength_correct})
        recall = statistics.fmean(result.recall for result in measurements)
        precision = statistics.fmean(result.precision for result in measurements)
        strength_accuracy = statistics.fmean(float(result.strength_correct) for result in measurements)
        metrics[strategy] = {
            "evidence_recall": recall,
            "citation_precision": precision,
            "evidence_strength_accuracy": strength_accuracy,
            "quality_score": 0.6 * recall + 0.3 * precision + 0.1 * strength_accuracy,
            "safety_pass": not any(result.forbidden_exposure for result in measurements),
            "citation_pass": all(result.citations_resolve for result in measurements),
            "p95_latency_ms": percentile_95(latencies),
            "mean_evidence_tokens": statistics.fmean(result.evidence_tokens for result in measurements),
            "retrieval_model_tokens": 0.0,
            "monetary_cost_usd": 0.0,
        }
        case_results[strategy] = details
    selected = select_strategy(metrics)
    return {
        "schema_version": 1,
        "benchmark_set": DEFAULT_CASES.relative_to(ROOT).as_posix(),
        "book_version_id": BOOK_VERSION_ID,
        "configuration": {
            "window_target_words": target_words,
            "window_overlap_words": overlap_words,
            "overlap_dedupe_threshold": OVERLAP_DEDUPE_THRESHOLD,
            "embedding_model": EMBEDDING_MODEL,
            "reranker_model": RERANKER_MODEL,
            "semantic_threshold": 0.5,
            "reranker_threshold": 0.5,
            "quality_equivalence_margin": QUALITY_EQUIVALENCE_MARGIN,
            "repetitions": repetitions,
        },
        "metric_notes": {
            "evidence_strength_accuracy": "Whether the retrieved gold coverage supports the expected sufficient, weak, or none label; the common Librarian judge is evaluated end to end separately.",
            "mean_evidence_tokens": "Whitespace-token count of evidence passed downstream; local retrieval itself consumes zero model tokens.",
            "monetary_cost_usd": "Incremental retrieval cost for local models; excludes shared hardware and the common downstream Librarian judgment call.",
            "p95_latency_ms": "Warm query latency after the immutable revision's derived windows and embeddings are built; one-time local model and index initialization is excluded.",
        },
        "project_targets": {
            "minimum_evidence_recall": MIN_EVIDENCE_RECALL,
            "minimum_citation_precision": MIN_CITATION_PRECISION,
            "scope": "Final user-visible pipeline; retrieval-only candidate precision is diagnostic.",
        },
        "metrics": metrics,
        "selected_strategy": selected,
        "selected_strategy_meets_retrieval_only_targets": (
            float(metrics[selected]["evidence_recall"]) >= MIN_EVIDENCE_RECALL
            and float(metrics[selected]["citation_precision"])
            >= MIN_CITATION_PRECISION
        ),
        "case_results": case_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--target-words", type=int, default=TARGET_WORDS)
    parser.add_argument("--overlap-words", type=int, default=OVERLAP_WORDS)
    args = parser.parse_args()
    report = run_benchmark(
        repetitions=args.repetitions,
        target_words=args.target_words,
        overlap_words=args.overlap_words,
    )
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"selected_strategy": report["selected_strategy"], "metrics": report["metrics"]}, indent=2))


if __name__ == "__main__":
    main()
