"""Practice traces for Sculptor's error analysis in Experiment 4.

Each trace shows what retrieval did for one practice need: the plan's search
queries, every passage handed to the Librarian (with text and chapter), what
the Librarian selected, and whether the answer passage was selected. For a
miss it adds the answering passage and, for each search query, where that
passage ranked in keyword and meaning-based search. Held-back needs are never
traced.
"""

from __future__ import annotations

import argparse
import json
from contextlib import nullcontext

import bm25s
import numpy as np

from apps.backend.contracts import BookScope, LibrarianRequest
from apps.backend.hybrid_librarian import HybridLibrarian, _cosine, _windows
from apps.backend.librarian import _paragraphs
from evals.librarian.chapter_cue_recall import (
    PLANS,
    RUNS,
    SEARCHES,
    _identity,
    _normalised,
    _needs,
    _read,
    approved_cues,
    cue_stage,
    part_candidates,
    revised_corpus,
)
from src.linger.agents.librarian.models import BookRequestPlan, LibrarianBookRequestInput
from src.linger.corpus import registry
from src.linger.corpus.units import read_unit
from src.linger.orchestration.book_evidence import (
    _context_queries,
    _part_queries,
    _without_author,
    gather_book_candidates,
)


def _short(evidence_id: str) -> str:
    """`pg500-v6bdc1734-ch22-ln2551-2605` becomes `ch22-ln2551-2605`."""
    return evidence_id.rsplit("-", 3)[-3] + "-" + "-".join(evidence_id.rsplit("-", 2)[-2:])


class _RecordingLibrarian(HybridLibrarian):
    """Production search that also keeps each query's intermediate rankings."""

    def __init__(self, **options) -> None:
        super().__init__(**options)
        self.steps: dict[str, dict[str, object]] = {}
        self._query = ""

    def _bm25(self, query, index):
        self._query = query
        found = super()._bm25(query, index)
        self.steps[query] = {"keyword_top10": [[_short(c.evidence_id), round(c.score, 2)] for c in found]}
        return found

    def _semantic(self, query, index, threshold):
        found = super()._semantic(query, index, threshold)
        self.steps[query]["meaning_top10"] = [[_short(c.evidence_id), round(c.score, 3)] for c in found]
        return found

    def _fuse(self, keyword, semantic):
        fused = HybridLibrarian._fuse(keyword, semantic)
        self.steps[self._query]["fused"] = [_short(c.evidence_id) for c in fused]
        return fused

    def retrieve_for_judgement(self, request):
        bundle = super().retrieve_for_judgement(request)
        self.steps[request.query]["turn_order_with_rerank_scores"] = [
            [_short(item.evidence_id), round(item.relevance, 3)] for item in bundle.items
        ]
        return bundle


def _rank_range(scores: np.ndarray, answers: np.ndarray) -> list[int] | None:
    """Rank of the best answer window as [best, worst] when other windows tie with it."""
    best = float(scores[answers].max())
    if best <= 0:
        return None
    return [int((scores > best).sum()) + 1, int((scores >= best).sum())]


def _ranks(librarian: HybridLibrarian, scope: BookScope, query: str, answers: set[str]) -> dict[str, object]:
    """Where the answer windows rank among all eligible windows, per search method."""
    index = librarian._index(LibrarianRequest(query=query, book_scopes=[scope]))
    total = len(index.candidates)
    is_answer = np.array([candidate.evidence_id in answers for candidate in index.candidates])
    ids, scores = index.bm25.retrieve(bm25s.tokenize(query, show_progress=False), k=total, show_progress=False)
    keyword = np.zeros(total)
    keyword[ids[0].astype(int)] = scores[0]
    embedding = np.asarray(next(iter(librarian._embedding_model().query_embed(query))))
    meaning = _cosine(embedding, index.embeddings)
    return {
        "query": query, "of": total,
        "keyword_rank": _rank_range(keyword, is_answer),
        "meaning_rank": _rank_range(meaning + 2, is_answer),
    }


def build(search: str) -> list[dict[str, object]]:
    document, needs = _needs("practice")
    selection = _read(RUNS / f"{search}-practice-selected.json")
    if selection["identity"] != _identity(search):
        raise SystemExit(f"{search}-practice-selected.json is stale.")
    selected = {result["id"]: result for result in selection["needs"]}
    scored = {result["id"]: result["pool"] for result in _read(RUNS / f"{search}-practice.json")["needs"]}
    plans = json.loads(PLANS.read_text(encoding="utf-8"))["plans"]
    work_id = document["work_id"]
    scope = BookScope(work_id=work_id, book_version_id=document["book_version_id"],
                      chapter_max=document["chapter_max"])
    librarian = _RecordingLibrarian(read_chapter_cues=search != "today")
    stage = cue_stage(search)
    cues = approved_cues(stage) if stage else None
    traces = []
    with revised_corpus(work_id, cues) if cues else nullcontext():
        registration = registry.CORPORA[work_id]
        units = {unit.chapter_number: unit for unit in librarian.units_for(work_id, document["book_version_id"])}
        chapter_tags = {
            number: {"routing_description": unit.routing_description, "characters": list(unit.characters),
                     "retrieval_cues": list(unit.retrieval_cues)}
            for number, unit in units.items()
        } if search != "today" else {}
        for need in needs:
            plan = BookRequestPlan.model_validate(plans[need["id"]])
            request = LibrarianBookRequestInput(current_line=need["question"])
            pool = gather_book_candidates(
                plan, request, book_scopes=(scope,), librarian=librarian,
                part_candidates=part_candidates(search),
            )
            record = selected[need["id"]]
            if [item.evidence_id for item in pool] != (record.get("pool") or scored[need["id"]]):
                raise SystemExit(f"{need['id']}: retrieval differs from the pool the Librarian selected from.")
            trace = {
                "need_id": need["id"],
                "question": need["question"],
                "answering_chapter": need["chapter"],
                "passed": record["passed"],
                "plan": plan.model_dump(mode="json"),
                "librarian_judgement": record["evidence_strength"],
                "librarian_reason": record.get("strength_reason", "not captured"),
                "librarian_limitations": record.get("limitations", "not captured"),
                "librarian_error": record.get("error"),
                "search_queries": [
                    _without_author(query, work_id)
                    for query in dict.fromkeys((*_part_queries(plan), *_context_queries(request)))
                ],
                "passages_returned": [
                    {"evidence_id": item.evidence_id, "chapter": item.chapter,
                     "selected": item.evidence_id in record["selected"], "text": item.excerpt}
                    for item in pool
                ],
            }
            trace["search_steps"] = [
                {"query": query, **librarian.steps[query]} for query in trace["search_queries"]
            ]
            if not record["passed"]:
                metadata, markdown = read_unit(registration, units[need["chapter"]])
                quote = _normalised(need["quote"])
                answers = [
                    window for window in _windows(metadata, _paragraphs(metadata, markdown))
                    if quote in _normalised(window.text)
                ]
                trace["answer_passages"] = [
                    {"evidence_id": window.evidence_id, "chapter": need["chapter"], "text": window.text}
                    for window in answers
                ]
                trace["answer_ranks"] = [
                    _ranks(librarian, scope, query, {window.evidence_id for window in answers})
                    for query in trace["search_queries"]
                ] if answers else "no single window holds the answer"
                # Tells a miss cut before the pool from one the Librarian did not select.
                trace["answer_turn_order"] = [
                    {"query": step["query"], "evidence_id": window.evidence_id,
                     "position": next((position for position, (short, _) in enumerate(
                         step["turn_order_with_rerank_scores"], 1) if short == _short(window.evidence_id)), None),
                     "in_pool": window.evidence_id in {item.evidence_id for item in pool}}
                    for step in trace["search_steps"] for window in answers
                ]
            traces.append(trace)
    output = RUNS / f"{search}-practice-traces.json"
    output.write_text(json.dumps({
        "search": search, "identity": _identity(search),
        "selection_recorded_at": selection["recorded_at"],
        "chapter_tags": chapter_tags, "traces": traces,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return traces


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search", choices=SEARCHES, required=True)
    traces = build(parser.parse_args().search)
    for trace in traces:
        if trace["passed"]:
            continue
        ranks = "; ".join(
            f"keyword {rank['keyword_rank'] or '-'}, meaning {rank['meaning_rank']} of {rank['of']}"
            for rank in trace["answer_ranks"]
        ) if isinstance(trace["answer_ranks"], list) else trace["answer_ranks"]
        print(f"{trace['need_id']} ch{trace['answering_chapter']:02d} missed: {ranks}")
    print(f"{sum(trace['passed'] for trace in traces)}/{len(traces)} passed; traces written.")


if __name__ == "__main__":
    main()
