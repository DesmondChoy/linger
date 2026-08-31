"""Private full-work inference of one request-scoped spoiler ceiling."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from apps.backend.contracts import BookScope, LibrarianRequest as SearchRequest
from apps.backend.librarian import Librarian, RegisteredCorpusScope
from apps.backend.telemetry import run_agent_traced
from src.linger.agents.librarian.boundary_prompt import PROMPT_FINGERPRINT
from src.linger.agents.librarian.models import BoundaryInferenceDecision
from src.linger.contracts.librarian import (
    BoundaryCandidate,
    BoundaryInferenceResult,
    BoundarySupportLocation,
    BoundaryUncertain,
    EvidenceRecord,
)
from src.linger.contracts.curation import CuratedMemory
from src.linger.services.memory import MemoryRecord

BOUNDARY_CONFIDENCE_THRESHOLD = 0.75
MAX_BOUNDARY_MEMORIES = 8
MAX_BOUNDARY_CANDIDATES = 10

RetrievalMemory = MemoryRecord | CuratedMemory

BoundaryJudge = Callable[
    [str, tuple[RetrievalMemory, ...], tuple[EvidenceRecord, ...]],
    Awaitable[BoundaryInferenceDecision],
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
    routed = librarian.route_work(memory.text, (scope.book_version_id,))
    return routed is not None and routed.scope.work_id == scope.work_id


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
) -> BoundaryInferenceDecision:
    """Run Librarian's private boundary judgment without logging its content."""
    from src.linger.agents.librarian.agent import librarian_boundary_agent

    payload = json.dumps(
        {
            "current_line": current_line,
            "relevant_memories": [
                {"memory_id": memory.memory_id, "text": memory.text}
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
        input_contract="LibrarianBoundaryInferenceInput.v1",
        output_contract=(
            "src.linger.agents.librarian.models.BoundaryInferenceDecision"
        ),
        prompt_template_id=PROMPT_FINGERPRINT.template_id,
        prompt_version=PROMPT_FINGERPRINT.version,
        prompt_digest=PROMPT_FINGERPRINT.digest,
        failure_code="boundary_inference_model_failed",
    )
    return result.output


async def infer_spoiler_boundary(
    current_line: str,
    *,
    work_id: str,
    book_version_id: str,
    memories: tuple[RetrievalMemory, ...],
    librarian: Librarian,
    judge: BoundaryJudge | None = None,
    confidence_threshold: float = BOUNDARY_CONFIDENCE_THRESHOLD,
) -> BoundaryInferenceResult:
    """Search a complete work privately, then return no story text."""
    scope = librarian.registered_scope(work_id, book_version_id)
    if scope is None:
        raise ValueError("boundary inference requires a registered corpus revision")
    selected_memories = relevant_memories(memories, scope, librarian)
    search_query = "\n\n".join(
        (current_line, *(memory.text for memory in selected_memories))
    )
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
        decision = await (judge or judge_spoiler_boundary)(
            current_line,
            selected_memories,
            evidence,
        )
    except Exception:
        return BoundaryUncertain(
            kind="uncertain",
            work_id=scope.work_id,
            book_version_id=scope.book_version_id,
            reason_code="inference_unavailable",
            clarification_question=_clarification(scope),
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
    if decision.confidence < confidence_threshold:
        return BoundaryUncertain(
            kind="uncertain",
            work_id=scope.work_id,
            book_version_id=scope.book_version_id,
            reason_code="low_confidence",
            confidence=decision.confidence,
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
        supporting_locations=locations,
    )
