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
from src.linger.corpus import registry
from src.linger.evaluation_transcript import ConnectionEvaluationEvent, record_connection_event
from src.linger.orchestration.evidence_strength import (
    StrengthJudge, assess_book_evidence, judge_evidence_strength, plan_book_request,
)


class EvidenceJudgementError(ValueError):
    """No evidence can be admitted when judgment fails or selects unknown records."""


MAX_SEARCH_QUERIES = 16
MAX_BOOK_CANDIDATES = 20
MAX_QUERY_CHARACTERS = 2000


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


def _author_names(scope: BookScope) -> tuple[str, ...]:
    corpus = registry.CORPORA.get(scope.work_id)
    author = getattr(getattr(corpus, "book", None), "author", None)
    return (author.strip(), author.split()[-1]) if author else ()


def _names_pattern(names: set[str]) -> re.Pattern[str] | None:
    if not names:
        return None
    alternatives = "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    return re.compile(rf"\b(?:{alternatives})(?:['’]s)?\b", re.IGNORECASE)


def _named_scopes(text: str, book_scopes: tuple[BookScope, ...]) -> tuple[BookScope, ...]:
    """The granted books a planned part names by author or full title."""
    named = []
    for scope in book_scopes:
        corpus = registry.CORPORA.get(scope.work_id)
        title = getattr(getattr(corpus, "book", None), "title", None)
        names = set(_author_names(scope)) | ({title} if title else set())
        pattern = _names_pattern(names)
        if pattern is not None and pattern.search(text):
            named.append(scope)
    return tuple(named)


def _search_requests(
    plan: BookRequestPlan,
    original: LibrarianBookRequestInput,
    book_scopes: tuple[BookScope, ...],
) -> tuple[tuple[str, tuple[BookScope, ...]], ...]:
    """Pair each search text with the books it searches.

    An author's name says which book the reader means, not what happens in it,
    and it rarely appears in the author's own text: left in a query it ranks
    passages that merely mention it (Keller's ancestry, say) above the passage
    the reader described. So a planned part that names a granted book's author
    or title searches only that book, and the author's name is removed from the
    search text. The reader's own words are still searched intact across every
    granted book.
    """
    authors = _names_pattern({name for scope in book_scopes for name in _author_names(scope)})
    pairs: list[tuple[str, tuple[BookScope, ...]]] = []
    for part in plan.parts:
        text = " ".join(dict.fromkeys((*part.context_spans, *part.reader_spans)))
        scopes = _named_scopes(text, book_scopes) or book_scopes
        if authors is not None:
            text = " ".join(authors.sub(" ", text).split())
        pairs.append((text, scopes))
    pairs.extend(
        (text, book_scopes)
        for text in (original.current_line, *(s.text for s in original.prior_reader_statements))
    )
    requests = tuple(dict.fromkeys(
        (text[start:start + MAX_QUERY_CHARACTERS].strip(), scopes)
        for text, scopes in pairs for start in range(0, len(text), MAX_QUERY_CHARACTERS)
        if text[start:start + MAX_QUERY_CHARACTERS].strip()
    ))
    if len(requests) > MAX_SEARCH_QUERIES:
        raise EvidenceJudgementError("The complete request exceeds the retrieval query budget")
    return requests


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
    return tuple(by_id.values())[:MAX_BOOK_CANDIDATES]


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
    searches = _search_requests(plan or BookRequestPlan(parts=()), original, tuple(book_scopes))
    try:
        requests = [LibrarianRequest(
            query=query, book_scopes=list(scopes),
            retrieval_score_threshold=retrieval_score_threshold,
            max_results=max_results, purpose=purpose,
        ) for query, scopes in searches]
    except ValueError as error:
        raise EvidenceJudgementError("Planned book request exceeds the retrieval budget") from error
    streams = []
    for request in requests:
        requested_work_ids = tuple(scope.work_id for scope in request.book_scopes)
        if purpose == "connection_discovery":
            record_connection_event(ConnectionEvaluationEvent(
                kind="book_retrieval", status="attempted", source="book_corpus",
                operation="search_librarian", requested_work_ids=requested_work_ids,
            ))
        candidates = tuple(librarian.retrieve_for_judgement(request).items)
        if purpose == "connection_discovery":
            record_connection_event(ConnectionEvaluationEvent(
                kind="book_retrieval", status="ok", source="book_corpus",
                operation="search_librarian", requested_work_ids=requested_work_ids,
                retrieved_work_ids=tuple(item.work_id for item in candidates),
            ))
        streams.append(candidates)
    items = _merge_candidates(streams, book_scopes)
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
