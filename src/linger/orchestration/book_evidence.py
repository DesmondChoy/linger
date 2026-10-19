"""Shared scoped book retrieval and independent relevance judgment."""

import re
from dataclasses import dataclass
from itertools import zip_longest
from typing import Literal

import logfire

from apps.backend.contracts import BookScope, EvidenceItem, LibrarianRequest
from apps.backend.librarian import Librarian
from src.linger.agents.librarian.models import (
    BookRequestPlan, EvidenceStrengthDecision, LibrarianBookRequestInput,
)
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.contracts.reading import permits_scope
from src.linger.contracts.session import ReaderStatement
from src.linger.corpus.registry import CORPORA
from src.linger.evaluation_transcript import ConnectionEvaluationEvent, record_connection_event
from src.linger.orchestration.evidence_strength import (
    StrengthJudge, assess_book_evidence, judge_evidence_strength, plan_book_request,
)


class EvidenceJudgementError(ValueError):
    """No evidence can be admitted when judgment fails or selects unknown records."""


MAX_SEARCH_QUERIES = 16
MAX_BOOK_CANDIDATES = 20
MAX_QUERY_CHARACTERS = 2000
# Keep a full round of the keyword, fused, semantic, and reranker streams.
# Their interleaved order is not a descending relevance-score order.
PART_CANDIDATES = 4
# The whole Line and prior statements stay as a small safety net for a need
# the planner missed.
CONTEXT_CANDIDATES = 2
# A part is searched only in the book whose best match clearly dominates;
# otherwise, as for an unnamed theme, it is searched in every granted book.
ROUTING_FLOOR = 0.05
ROUTING_MARGIN = 10.0


@dataclass(frozen=True)
class JudgedBookEvidence:
    items: tuple[EvidenceItem, ...]
    judgement: EvidenceStrengthDecision


def evidence_record_from_item(item: EvidenceItem) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=item.evidence_id,
        work_id=item.work_id,
        book_version_id=item.book_version_id,
        chapter_id=item.chapter_id,
        chapter_number=item.chapter,
        part_id=item.part_id,
        location=item.location,
        source_sha256=item.source_sha256,
        source_lines=item.source_lines,
        text=item.excerpt,
    )


async def judge_records(
    query: str,
    records: tuple[EvidenceRecord, ...],
    *,
    strength_judge: StrengthJudge | None = None,
    max_evidence_records: int = 5,
    request_plan: BookRequestPlan | None = None,
    original_request: LibrarianBookRequestInput | None = None,
) -> EvidenceStrengthDecision:
    if not records:
        return EvidenceStrengthDecision(
            evidence_strength="none",
            strength_reason="No matching passages were found within the confirmed boundary.",
        )
    try:
        if request_plan is not None:
            if original_request is None:
                raise ValueError("planned evidence assessment requires original reader context")
            output = await assess_book_evidence(
                request_plan, records, max_evidence_records=max_evidence_records,
                original_request=original_request,
            )
        elif strength_judge is None:
            output = await judge_evidence_strength(
                query, records, max_evidence_records=max_evidence_records,
            )
        else:
            output = await strength_judge(
                query, records, max_evidence_records=max_evidence_records,
            )
        decision = EvidenceStrengthDecision.model_validate(output)
        if not set(decision.relevant_evidence_ids).issubset(
            record.evidence_id for record in records
        ):
            raise ValueError("evidence-strength judge selected an unavailable record")
        selected_ids = decision.relevant_evidence_ids
        if len(selected_ids) != len(set(selected_ids)) or len(selected_ids) > max_evidence_records:
            raise ValueError("evidence-strength judge exceeded the unique evidence selection budget")
        return decision
    except Exception as error:
        raise EvidenceJudgementError("Evidence judgment unavailable") from error


def _chunks(text: str) -> tuple[str, ...]:
    return tuple(
        chunk for start in range(0, len(text), MAX_QUERY_CHARACTERS)
        if (chunk := text[start:start + MAX_QUERY_CHARACTERS].strip())
    )


def _part_queries(plan: BookRequestPlan) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        chunk
        for part in plan.parts
        for chunk in _chunks(" ".join(dict.fromkeys((*part.context_spans, *part.reader_spans))))
    ))


def _context_queries(original: LibrarianBookRequestInput) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        chunk
        for text in (original.current_line, *(s.text for s in original.prior_reader_statements))
        for chunk in _chunks(text)
    ))


def _without_author(query: str, work_id: str) -> str:
    """Drop the searched book's author name, which reader text uses only to name the book.

    Name words that also appear in the book's title or aliases are kept, so a
    title mention such as "Narrative of the Life of Frederick Douglass" survives.
    """
    registration = CORPORA.get(work_id)
    if registration is None:
        return query
    title_words = {
        word.casefold()
        for name in (registration.book.title, *registration.aliases)
        for word in re.findall(r"\w+", name)
    }
    names = [
        word for word in re.findall(r"\w+", registration.book.author)
        if len(word) > 2 and word.casefold() not in title_words
    ]
    if not names:
        return query
    stripped = re.sub(
        r"\b(?:" + "|".join(map(re.escape, names)) + r")(?:['’]s)?\b", "", query, flags=re.IGNORECASE,
    )
    stripped = re.sub(r"\s{2,}", " ", stripped).strip()
    return stripped or query


def _merge_candidates(
    streams: list[tuple[EvidenceItem, ...]], book_scopes: tuple[BookScope, ...],
) -> tuple[EvidenceItem, ...]:
    by_id: dict[str, EvidenceItem] = {}
    for ranked in zip_longest(*streams):
        for item in ranked:
            if item is None or not any(permits_scope(scope, item) for scope in book_scopes):
                continue
            prior = by_id.get(item.evidence_id)
            if prior is not None and evidence_record_from_item(prior) != evidence_record_from_item(item):
                raise EvidenceJudgementError("Conflicting retrieved content for one evidence ID")
            by_id.setdefault(item.evidence_id, item)
    return tuple(by_id.values())


def _routed_books(streams: dict[str, tuple[EvidenceItem, ...]]) -> tuple[str, ...]:
    """Keep a part to one book only when that book's best match clearly dominates."""
    tops = sorted(
        ((max((item.relevance for item in items), default=0.0), work_id)
         for work_id, items in streams.items()),
        reverse=True,
    )
    if len(tops) > 1 and tops[0][0] >= ROUTING_FLOOR and tops[0][0] >= ROUTING_MARGIN * tops[1][0]:
        return (tops[0][1],)
    return tuple(streams)


def _without_contained_windows(items: tuple[EvidenceItem, ...]) -> tuple[EvidenceItem, ...]:
    """Drop a window only when an earlier record contains all of its source lines."""
    kept: list[EvidenceItem] = []
    for item in items:
        start, end = item.source_lines
        if not any(
            (other.work_id, other.book_version_id, other.part_id, other.chapter_id, other.source_sha256)
            == (item.work_id, item.book_version_id, item.part_id, item.chapter_id, item.source_sha256)
            and other.source_lines[0] <= start <= end <= other.source_lines[1]
            for other in kept
        ):
            kept.append(item)
    return tuple(kept)


def gather_book_candidates(
    plan: BookRequestPlan,
    original: LibrarianBookRequestInput,
    *,
    book_scopes: tuple[BookScope, ...],
    librarian: Librarian,
    purpose: Literal["evidence_retrieval", "connection_discovery"] = "evidence_retrieval",
    retrieval_score_threshold: float = 0.5,
    max_results: int = 5,
    part_candidates: int = PART_CANDIDATES,
) -> tuple[EvidenceItem, ...]:
    """Search each planned part in its own book, plus a small whole-request safety net.

    `part_candidates` is an opt-in experiment switch; production keeps `PART_CANDIDATES`.
    """
    part_queries = _part_queries(plan)
    context_queries = _context_queries(original)
    if len(set((*part_queries, *context_queries))) > MAX_SEARCH_QUERIES:
        raise EvidenceJudgementError("The complete request exceeds the retrieval query budget")

    searched: dict[tuple[BookScope, str], tuple[EvidenceItem, ...]] = {}

    def search(scope: BookScope, query: str) -> tuple[EvidenceItem, ...]:
        query = _without_author(query, scope.work_id)
        key = (scope, query)
        if key in searched:
            return searched[key]
        try:
            request = LibrarianRequest(
                query=query, book_scopes=[scope],
                retrieval_score_threshold=retrieval_score_threshold,
                max_results=max_results, purpose=purpose,
            )
        except ValueError as error:
            raise EvidenceJudgementError("Planned book request exceeds the retrieval budget") from error
        if purpose == "connection_discovery":
            record_connection_event(ConnectionEvaluationEvent(
                kind="book_retrieval", status="attempted", source="book_corpus",
                operation="search_librarian", requested_work_ids=(scope.work_id,),
            ))
        raw = tuple(librarian.retrieve_for_judgement(request).items)
        if purpose == "connection_discovery":
            record_connection_event(ConnectionEvaluationEvent(
                kind="book_retrieval", status="ok", source="book_corpus",
                operation="search_librarian", requested_work_ids=(scope.work_id,),
                retrieved_work_ids=tuple(item.work_id for item in raw),
            ))
        searched[key] = _merge_candidates([raw], (scope,))
        return searched[key]

    per_book: dict[str, list[tuple[EvidenceItem, ...]]] = {scope.work_id: [] for scope in book_scopes}
    for query in part_queries:
        streams = {scope.work_id: search(scope, query) for scope in book_scopes}
        for work_id in _routed_books(streams):
            per_book[work_id].append(streams[work_id][:part_candidates])
    # Without a plan the whole request is the only query, so it keeps the full budget.
    context_budget = CONTEXT_CANDIDATES if part_queries else MAX_BOOK_CANDIDATES
    for scope in book_scopes:
        for query in context_queries:
            # Routing can omit this book's planned results even for an identical
            # query. Reuse the search, but retain its fallback independently.
            per_book[scope.work_id].append(search(scope, query)[:context_budget])
    merged = tuple(
        _without_contained_windows(_merge_candidates(per_book[scope.work_id], (scope,)))[:MAX_BOOK_CANDIDATES]
        for scope in book_scopes
    )
    return _merge_candidates(list(merged), book_scopes)


async def retrieve_book_evidence(
    reader_question: str,
    *,
    book_scopes: tuple[BookScope, ...],
    librarian: Librarian,
    retrieval_score_threshold: float = 0.5,
    max_results: int = 5,
    purpose: Literal["evidence_retrieval", "connection_discovery"] = "evidence_retrieval",
    strength_judge: StrengthJudge | None = None,
    prior_reader_statements: tuple[ReaderStatement, ...] = (),
) -> JudgedBookEvidence:
    """Recover, scope, and judge candidates before exposing selected evidence."""
    if not book_scopes:
        return JudgedBookEvidence(items=(), judgement=EvidenceStrengthDecision(
            evidence_strength="none", strength_reason="No book scope is authorized for retrieval.",
        ))
    original = LibrarianBookRequestInput(
        current_line=reader_question, prior_reader_statements=prior_reader_statements,
    )
    plan = None
    if strength_judge is None:
        try:
            plan = await plan_book_request(
                reader_question,
                prior_reader_statements=prior_reader_statements,
            )
        except Exception:
            logfire.warning("librarian.book_request_fallback", reason="planning_unavailable")
            plan = BookRequestPlan(parts=())
    items = gather_book_candidates(
        plan or BookRequestPlan(parts=()), original,
        book_scopes=book_scopes, librarian=librarian, purpose=purpose,
        retrieval_score_threshold=retrieval_score_threshold, max_results=max_results,
    )
    records = tuple(evidence_record_from_item(item) for item in items)
    if len({record.evidence_id for record in records}) != len(records):
        raise ValueError("retrieved evidence IDs must be unique")
    decision = await judge_records(
        reader_question, records, strength_judge=strength_judge,
        max_evidence_records=max_results, request_plan=plan,
        original_request=original,
    )
    selected = set(decision.relevant_evidence_ids)
    return JudgedBookEvidence(
        items=tuple(item for item in items if item.evidence_id in selected),
        judgement=decision,
    )
