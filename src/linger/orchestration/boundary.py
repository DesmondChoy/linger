"""Private full-work inference of one request-scoped spoiler ceiling."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from apps.backend.contracts import BookScope, LibrarianRequest as SearchRequest
from apps.backend.librarian import Librarian, RegisteredCorpusScope
from apps.backend.telemetry import run_agent_traced
from src.linger.agents.librarian.boundary_prompt import PROMPT_FINGERPRINT
from src.linger.agents.librarian.models import (
    LibrarianBoundaryDecision,
    PassageInferenceDecision,
)
from src.linger.contracts.librarian import (
    BoundaryCandidate,
    BoundaryInferenceResult,
    BoundaryPassages,
    BoundarySupportLocation,
    BoundaryUncertain,
    EvidenceRecord,
    PassageGrant,
)
from src.linger.contracts.curation import CuratedMemory
from src.linger.contracts.session import ReaderStatement
from src.linger.services.memory import MemoryRecord

BOUNDARY_CONFIDENCE_THRESHOLD = 0.75
MAX_BOUNDARY_MEMORIES = 8
MAX_BOUNDARY_CANDIDATES = 10

RetrievalMemory = MemoryRecord | CuratedMemory

BoundaryJudge = Callable[
    [str, tuple[RetrievalMemory, ...], tuple[EvidenceRecord, ...], tuple[ReaderStatement, ...]],
    Awaitable[LibrarianBoundaryDecision],
]


def _clarification(scope: RegisteredCorpusScope, *, chapter: int | None = None) -> str:
    if chapter is not None:
        return (
            f"Have you completed Chapter {chapter} of {scope.title}, "
            "or are you still earlier in the book?"
        )
    return (
        f"What is the latest chapter or scene in {scope.title} "
        "that you have completed?"
    )


def _memory_mentions_work(
    memory: RetrievalMemory,
    scope: RegisteredCorpusScope,
    librarian: Librarian,
) -> bool:
    for evidence_id in memory.evidence_ids:
        try:
            record = librarian.fetch_by_id(evidence_id)
        except Exception:
            continue
        if (
            record is not None
            and record.work_id == scope.work_id
            and record.book_version_id == scope.book_version_id
        ):
            return True
    return any(
        candidate.strength == "strong" and candidate.scope.work_id == scope.work_id
        for candidate in librarian.work_candidates(
            memory.text,
            (scope.book_version_id,),
        )
    )


def relevant_memories(
    memories: tuple[RetrievalMemory, ...],
    scope: RegisteredCorpusScope,
    librarian: Librarian,
) -> tuple[RetrievalMemory, ...]:
    """Return a bounded account-scoped subset that references this work."""
    matching = [
        memory
        for memory in reversed(memories)
        if _memory_mentions_work(memory, scope, librarian)
    ]
    return tuple(reversed(matching[:MAX_BOUNDARY_MEMORIES]))


async def judge_spoiler_boundary(
    current_line: str,
    memories: tuple[RetrievalMemory, ...],
    evidence: tuple[EvidenceRecord, ...],
    prior_reader_statements: tuple[ReaderStatement, ...],
) -> LibrarianBoundaryDecision:
    """Run Librarian's private boundary judgment without logging its content."""
    from src.linger.agents.librarian.agent import librarian_boundary_agent

    payload = json.dumps(
        {
            "current_line": current_line,
            "prior_reader_statements": [
                statement.model_dump(mode="json") for statement in prior_reader_statements
            ],
            "relevant_memories": [
                {
                    "memory_id": memory.memory_id,
                    "text": memory.text,
                    "evidence_ids": list(memory.evidence_ids),
                }
                for memory in memories
            ],
            "full_work_candidates": [
                record.model_dump(mode="json") for record in evidence
            ],
        },
        ensure_ascii=False,
    )
    result = await run_agent_traced(
        librarian_boundary_agent,
        payload,
        span_name="librarian.boundary_inference",
        role="Librarian",
        stage="boundary_inference",
        input_contract="LibrarianBoundaryInferenceInput.v2",
        output_contract=(
            "src.linger.agents.librarian.models.LibrarianBoundaryDecision"
        ),
        prompt_template_id=PROMPT_FINGERPRINT.template_id,
        prompt_version=PROMPT_FINGERPRINT.version,
        prompt_digest=PROMPT_FINGERPRINT.digest,
        failure_code="boundary_inference_model_failed",
    )
    return result.output


def _validated_passages(
    decision: PassageInferenceDecision,
    scope: RegisteredCorpusScope,
    evidence: tuple[EvidenceRecord, ...],
    prior_reader_statements: tuple[ReaderStatement, ...],
    confidence_threshold: float,
) -> BoundaryPassages | BoundaryUncertain:
    statement_ids = {statement.statement_id for statement in prior_reader_statements}
    by_id = {record.evidence_id: record for record in evidence}
    selections = (
        decision.supporting_statement_ids,
        decision.supporting_evidence_ids,
        decision.passage_evidence_ids,
    )
    if (
        not prior_reader_statements
        or len(statement_ids) != len(prior_reader_statements)
        or decision.work_id != scope.work_id
        or decision.book_version_id != scope.book_version_id
        or any(not ids or len(ids) != len(set(ids)) for ids in selections)
        or len(decision.passage_evidence_ids) > 5
        or not set(decision.supporting_statement_ids) <= statement_ids
        or not set(decision.supporting_evidence_ids) <= by_id.keys()
        or not set(decision.passage_evidence_ids) <= by_id.keys()
    ):
        return BoundaryUncertain(
            kind="uncertain", work_id=scope.work_id, book_version_id=scope.book_version_id,
            reason_code="inference_unavailable", clarification_question=_clarification(scope),
        )
    if decision.confidence < confidence_threshold:
        return BoundaryUncertain(
            kind="uncertain", work_id=scope.work_id, book_version_id=scope.book_version_id,
            reason_code="low_confidence", confidence=decision.confidence,
            clarification_question=_clarification(scope),
        )
    return BoundaryPassages(
        grant=PassageGrant(
            records=tuple(by_id[evidence_id] for evidence_id in decision.passage_evidence_ids),
            supporting_statement_ids=decision.supporting_statement_ids,
        ),
        confidence=decision.confidence,
    )


async def infer_spoiler_boundary(
    current_line: str,
    *,
    work_id: str,
    book_version_id: str,
    memories: tuple[RetrievalMemory, ...],
    librarian: Librarian,
    prior_reader_statements: tuple[ReaderStatement, ...] = (),
    judge: BoundaryJudge | None = None,
    confidence_threshold: float = BOUNDARY_CONFIDENCE_THRESHOLD,
) -> BoundaryInferenceResult:
    """Privately validate chapter progress or a grant for exact known passages."""
    scope = librarian.registered_scope(work_id, book_version_id)
    if scope is None:
        raise ValueError("boundary inference requires a registered corpus revision")
    selected_memories = relevant_memories(memories, scope, librarian)
    search_signals = (
        current_line,
        *(memory.text for memory in selected_memories),
    )
    if prior_reader_statements:
        search_signals = (
            current_line[:1000],
            *(statement.text for statement in reversed(prior_reader_statements)),
            *(memory.text for memory in selected_memories),
        )
    search_query = "\n\n".join(search_signals)[:2000]
    try:
        bundle = librarian.retrieve(
            SearchRequest(
                query=search_query,
                book_scopes=[
                    BookScope(
                        work_id=scope.work_id,
                        book_version_id=scope.book_version_id,
                        chapter_max=scope.max_chapter,
                    )
                ],
                retrieval_score_threshold=0.5,
                max_results=MAX_BOUNDARY_CANDIDATES,
                purpose="boundary_inference",
            )
        )
    except Exception:
        return BoundaryUncertain(
            kind="uncertain",
            work_id=scope.work_id,
            book_version_id=scope.book_version_id,
            reason_code="inference_unavailable",
            clarification_question=_clarification(scope),
        )

    evidence = tuple(
        EvidenceRecord(
            evidence_id=item.evidence_id,
            work_id=item.work_id,
            book_version_id=item.book_version_id,
            chapter_id=item.chapter_id,
            chapter_number=item.chapter,
            location=item.location,
            source_sha256=item.source_sha256,
            source_lines=item.source_lines,
            text=item.excerpt,
        )
        for item in bundle.items
        if item.work_id == scope.work_id
        and item.book_version_id == scope.book_version_id
        and item.chapter <= scope.max_chapter
    )
    if not evidence:
        return BoundaryUncertain(
            kind="uncertain",
            work_id=scope.work_id,
            book_version_id=scope.book_version_id,
            reason_code="insufficient_context",
            clarification_question=_clarification(scope),
        )

    try:
        if prior_reader_statements:
            evidence = librarian.candidate_paragraphs(evidence)
        decision = await (judge or judge_spoiler_boundary)(
            current_line,
            selected_memories,
            evidence,
            prior_reader_statements,
        )
    except Exception:
        return BoundaryUncertain(
            kind="uncertain",
            work_id=scope.work_id,
            book_version_id=scope.book_version_id,
            reason_code="inference_unavailable",
            clarification_question=_clarification(scope),
        )

    if isinstance(decision, PassageInferenceDecision):
        return _validated_passages(
            decision, scope, evidence, prior_reader_statements, confidence_threshold
        )

    if decision.outcome == "uncertain":
        return BoundaryUncertain(
            kind="uncertain",
            work_id=scope.work_id,
            book_version_id=scope.book_version_id,
            reason_code=decision.reason_code or "insufficient_context",
            confidence=decision.confidence,
            clarification_question=_clarification(scope),
        )

    if len(set(decision.supporting_evidence_ids)) != len(
        decision.supporting_evidence_ids
    ):
        return BoundaryUncertain(
            kind="uncertain",
            work_id=scope.work_id,
            book_version_id=scope.book_version_id,
            reason_code="inference_unavailable",
            clarification_question=_clarification(scope),
        )

    if len(set(decision.supporting_memory_ids)) != len(
        decision.supporting_memory_ids
    ):
        return BoundaryUncertain(
            kind="uncertain",
            work_id=scope.work_id,
            book_version_id=scope.book_version_id,
            reason_code="inference_unavailable",
            clarification_question=_clarification(scope),
        )

    selected_memory_ids = {memory.memory_id for memory in selected_memories}
    if not set(decision.supporting_memory_ids) <= selected_memory_ids:
        return BoundaryUncertain(
            kind="uncertain",
            work_id=scope.work_id,
            book_version_id=scope.book_version_id,
            reason_code="inference_unavailable",
            clarification_question=_clarification(scope),
        )

    by_id = {record.evidence_id: record for record in evidence}
    try:
        supporting = tuple(by_id[evidence_id] for evidence_id in decision.supporting_evidence_ids)
    except KeyError:
        return BoundaryUncertain(
            kind="uncertain",
            work_id=scope.work_id,
            book_version_id=scope.book_version_id,
            reason_code="inference_unavailable",
            clarification_question=_clarification(scope),
        )
    if (
        decision.work_id != scope.work_id
        or decision.book_version_id != scope.book_version_id
        or not supporting
    ):
        return BoundaryUncertain(
            kind="uncertain",
            work_id=scope.work_id,
            book_version_id=scope.book_version_id,
            reason_code="inference_unavailable",
            clarification_question=_clarification(scope),
        )

    derived_chapter = max(record.chapter_number for record in supporting)
    if decision.chapter_number != derived_chapter:
        return BoundaryUncertain(
            kind="uncertain",
            work_id=scope.work_id,
            book_version_id=scope.book_version_id,
            reason_code="inference_unavailable",
            clarification_question=_clarification(scope),
        )
    locations = tuple(
        BoundarySupportLocation(
            evidence_id=record.evidence_id,
            chapter_number=record.chapter_number,
            location=record.location,
        )
        for record in supporting
    )
    if decision.authorization_basis == "line_only":
        return BoundaryUncertain(
            kind="uncertain",
            work_id=scope.work_id,
            book_version_id=scope.book_version_id,
            reason_code="progress_unverified",
            confidence=decision.confidence,
            authorization_basis="line_only",
            candidate_chapter=derived_chapter,
            supporting_locations=locations,
            clarification_question=_clarification(scope),
        )
    if decision.confidence < confidence_threshold:
        return BoundaryUncertain(
            kind="uncertain",
            work_id=scope.work_id,
            book_version_id=scope.book_version_id,
            reason_code="low_confidence",
            confidence=decision.confidence,
            authorization_basis="memory_supported",
            supporting_memory_ids=decision.supporting_memory_ids,
            candidate_chapter=derived_chapter,
            supporting_locations=locations,
            clarification_question=_clarification(scope, chapter=derived_chapter),
        )
    return BoundaryCandidate(
        kind="candidate",
        work_id=scope.work_id,
        book_version_id=scope.book_version_id,
        max_chapter_inclusive=derived_chapter,
        confidence=decision.confidence,
        authorization_basis="memory_supported",
        supporting_memory_ids=decision.supporting_memory_ids,
        supporting_locations=locations,
    )
