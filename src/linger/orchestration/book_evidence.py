"""Shared scoped book retrieval and independent relevance judgment."""

from dataclasses import dataclass
from typing import Literal

from apps.backend.contracts import BookScope, EvidenceItem, LibrarianRequest
from apps.backend.hybrid_librarian import MAX_JUDGEMENT_CANDIDATES
from apps.backend.librarian import Librarian
from src.linger.agents.librarian.models import BookRequestPlan, EvidenceStrengthDecision
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.contracts.reading import permits_scope
from src.linger.contracts.session import ReaderStatement
from src.linger.orchestration.evidence_strength import (
    StrengthJudge, assess_book_evidence, judge_evidence_strength, plan_book_request,
)


class EvidenceJudgementError(ValueError):
    """No evidence can be admitted when judgment fails or selects unknown records."""


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
) -> EvidenceStrengthDecision:
    if not records:
        return EvidenceStrengthDecision(
            evidence_strength="none",
            strength_reason="No matching passages were found within the confirmed boundary.",
        )
    try:
        if request_plan is not None:
            output = await assess_book_evidence(
                request_plan, records, max_evidence_records=max_evidence_records,
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
    plan = None
    retrieval_query = reader_question
    if strength_judge is None:
        try:
            plan = await plan_book_request(
                reader_question,
                prior_reader_statements=prior_reader_statements,
            )
        except Exception as error:
            raise EvidenceJudgementError("Book request planning unavailable") from error
        if not plan.parts:
            return JudgedBookEvidence(items=(), judgement=EvidenceStrengthDecision(
                evidence_strength="none",
                strength_reason="No book question was identified in the supplied reader context.",
            ))
        retrieval_query = " ".join(dict.fromkeys(
            span for field in ("context_spans", "reader_spans")
            for part in plan.parts for span in getattr(part, field)
        ))
    try:
        retrieval_request = LibrarianRequest(
            query=retrieval_query, book_scopes=list(book_scopes),
            retrieval_score_threshold=retrieval_score_threshold,
            max_results=MAX_JUDGEMENT_CANDIDATES, purpose=purpose,
        )
    except ValueError as error:
        raise EvidenceJudgementError("Planned book request exceeds the retrieval budget") from error
    bundle = librarian.retrieve_for_judgement(retrieval_request)
    items = tuple(
        item for item in bundle.items
        if any(permits_scope(scope, item) for scope in book_scopes)
    )[:MAX_JUDGEMENT_CANDIDATES]
    records = tuple(evidence_record_from_item(item) for item in items)
    if len({record.evidence_id for record in records}) != len(records):
        raise ValueError("retrieved evidence IDs must be unique")
    decision = await judge_records(
        retrieval_query, records, strength_judge=strength_judge,
        max_evidence_records=max_results, request_plan=plan,
    )
    selected = set(decision.relevant_evidence_ids)
    return JudgedBookEvidence(
        items=tuple(item for item in items if item.evidence_id in selected),
        judgement=decision,
    )
