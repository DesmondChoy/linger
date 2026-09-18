"""Shared scoped book retrieval and independent relevance judgment."""

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


def _search_queries(plan: BookRequestPlan, original: LibrarianBookRequestInput) -> tuple[str, ...]:
    texts = [
        " ".join(dict.fromkeys((*part.context_spans, *part.reader_spans)))
        for part in plan.parts
    ]
    texts.extend((original.current_line, *(s.text for s in original.prior_reader_statements)))
    queries = tuple(dict.fromkeys(
        text[start:start + MAX_QUERY_CHARACTERS].strip()
        for text in texts for start in range(0, len(text), MAX_QUERY_CHARACTERS)
        if text[start:start + MAX_QUERY_CHARACTERS].strip()
    ))
    if len(queries) > MAX_SEARCH_QUERIES:
        raise EvidenceJudgementError("The complete request exceeds the retrieval query budget")
    return queries


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
    queries = _search_queries(plan or BookRequestPlan(parts=()), original)
    try:
        requests = [LibrarianRequest(
            query=query, book_scopes=list(book_scopes),
            retrieval_score_threshold=retrieval_score_threshold,
            max_results=max_results, purpose=purpose,
        ) for query in queries]
    except ValueError as error:
        raise EvidenceJudgementError("Planned book request exceeds the retrieval budget") from error
    items = _merge_candidates(
        [tuple(librarian.retrieve_for_judgement(request).items) for request in requests], book_scopes,
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
