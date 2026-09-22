"""Private full-work inference of one request-scoped spoiler ceiling."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from itertools import zip_longest
import logging
from typing import Any, Literal, Protocol

from pydantic import ValidationError
from pydantic_ai import Agent, UsageLimits

from apps.backend.contracts import BookScope, LibrarianRequest as SearchRequest
from apps.backend.librarian import Librarian, RegisteredCorpusScope
from apps.backend.telemetry import run_agent_traced
from src.linger.agents.librarian.boundary_prompt import (
    EVENT_IDENTIFICATION_PROMPT_FINGERPRINT,
    NO_HISTORY_PROMPT_FINGERPRINT,
    PROMPT_FINGERPRINT,
)
from src.linger.agents.librarian.models import (
    BoundaryEventIdentified,
    BoundaryEventUnresolved,
    BoundaryMemory,
    BookRequestPlan,
    boundary_memory_assessment_errors,
    LibrarianBoundaryDecision,
    LibrarianBoundaryInferenceInput,
    PassageInferenceDecision,
    LibrarianEventIdentification,
    LibrarianEventIdentificationInput,
    event_identification_errors,
)
from src.linger.agents.librarian.skills import BOUNDARY_INFERENCE, BOUNDARY_INFERENCE_NO_HISTORY, EVENT_IDENTIFICATION
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
from src.linger.orchestration import evidence_strength
from src.linger.services.memory import MemoryRecord

BOUNDARY_CONFIDENCE_THRESHOLD = 0.75
MAX_BOUNDARY_MEMORIES = 8
MAX_BOUNDARY_SEARCH_RESULTS = 5
MAX_BOUNDARY_CANDIDATES = 20
MAX_BOUNDARY_QUERY_CHARACTERS = 2000
# No tools reach either judgment; these bound their own structured-output repair
# attempts. A model that answers with calls to tools it was never given would
# otherwise keep earning fresh retry prompts.
BOUNDARY_INFERENCE_REQUEST_LIMIT = BOUNDARY_INFERENCE.output_retries + 1
EVENT_IDENTIFICATION_REQUEST_LIMIT = EVENT_IDENTIFICATION.output_retries + 1
logger = logging.getLogger(__name__)

RetrievalMemory = MemoryRecord | CuratedMemory

BoundaryJudge = Callable[
    [str, tuple[RetrievalMemory, ...], tuple[EvidenceRecord, ...], tuple[ReaderStatement, ...]],
    Awaitable[LibrarianBoundaryDecision],
]

EventIdentifier = Callable[
    [LibrarianEventIdentificationInput], Awaitable[LibrarianEventIdentification],
]


class BoundaryPlanner(Protocol):
    async def __call__(
        self, current_line: str, *,
        prior_reader_statements: tuple[ReaderStatement, ...],
        search_target: Literal["reading_progress"],
    ) -> BookRequestPlan: ...


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


def _has_strong_work_candidate(
    text: str,
    scope: RegisteredCorpusScope,
    librarian: Librarian,
) -> bool:
    return any(
        candidate.strength == "strong" and candidate.scope.work_id == scope.work_id
        for candidate in librarian.work_candidates(text, (scope.book_version_id,))
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
    return _has_strong_work_candidate(memory.text, scope, librarian)


def _statement_supports_work(
    statement: ReaderStatement, scope: RegisteredCorpusScope, librarian: Librarian
) -> bool:
    """Accept a reader statement only when it strongly indicates this work."""
    return _has_strong_work_candidate(statement.text, scope, librarian)


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


def _boundary_input(
    current_line: str,
    memories: tuple[RetrievalMemory, ...],
    evidence: tuple[EvidenceRecord, ...],
    prior_reader_statements: tuple[ReaderStatement, ...],
) -> LibrarianBoundaryInferenceInput:
    return LibrarianBoundaryInferenceInput(
        current_line=current_line,
        prior_reader_statements=prior_reader_statements,
        relevant_memories=tuple(
            BoundaryMemory(
                memory_id=memory.memory_id,
                text=memory.text,
                evidence_ids=memory.evidence_ids,
            )
            for memory in memories
        ),
        full_work_candidates=evidence,
    )


async def judge_spoiler_boundary(
    current_line: str,
    memories: tuple[RetrievalMemory, ...],
    evidence: tuple[EvidenceRecord, ...],
    prior_reader_statements: tuple[ReaderStatement, ...],
    *,
    agent: Agent[None, Any] | None = None,
) -> LibrarianBoundaryDecision:
    """Run Librarian's private boundary judgment without logging its content."""
    if agent is None:
        from src.linger.agents.librarian.agent import librarian_agent

        agent = librarian_agent

    task = _boundary_input(current_line, memories, evidence, prior_reader_statements)
    skill = BOUNDARY_INFERENCE if prior_reader_statements else BOUNDARY_INFERENCE_NO_HISTORY
    fingerprint = PROMPT_FINGERPRINT if prior_reader_statements else NO_HISTORY_PROMPT_FINGERPRINT
    result = await run_agent_traced(
        agent,
        task.model_dump_json(),
        span_name="librarian.boundary_inference",
        role="Librarian",
        stage="boundary_inference",
        input_contract="LibrarianBoundaryInferenceInput.v3",
        output_contract=(
            "src.linger.agents.librarian.models.LibrarianBoundaryDecision"
            if prior_reader_statements else
            "src.linger.agents.librarian.models.LibrarianChapterBoundaryDecision"
        ),
        prompt_template_id=fingerprint.template_id,
        prompt_digest=fingerprint.digest,
        failure_code="boundary_inference_model_failed",
        usage_limits=UsageLimits(request_limit=BOUNDARY_INFERENCE_REQUEST_LIMIT),
        **skill.run_options(),
    )
    return result.output


async def identify_reader_event(
    task: LibrarianEventIdentificationInput, *, agent: Agent[None, Any] | None = None,
) -> LibrarianEventIdentification:
    """Independently locate the current event with no proposed grant or stored memory."""
    if agent is None:
        from src.linger.agents.librarian.agent import librarian_agent

        agent = librarian_agent
    fingerprint = EVENT_IDENTIFICATION_PROMPT_FINGERPRINT
    result = await run_agent_traced(
        agent, task.model_dump_json(),
        span_name="librarian.event_identification", role="Librarian", stage="event_identification",
        input_contract="LibrarianEventIdentificationInput.v1",
        output_contract="src.linger.agents.librarian.models.LibrarianEventIdentification",
        prompt_template_id=fingerprint.template_id, prompt_digest=fingerprint.digest,
        failure_code="event_identification_model_failed",
        usage_limits=UsageLimits(request_limit=EVENT_IDENTIFICATION_REQUEST_LIMIT),
        **EVENT_IDENTIFICATION.run_options(),
    )
    return result.output


def _same_stopping_occurrence(
    identified: tuple[EvidenceRecord, ...], selected: tuple[EvidenceRecord, ...], chapter: int,
) -> bool:
    """Different canonical windows may describe the same final occurrence."""
    if not identified or any(record.chapter_number != chapter for record in identified):
        return False
    latest = tuple(record for record in selected if record.chapter_number == chapter)
    return all(any(
        record.work_id == other.work_id
        and record.book_version_id == other.book_version_id
        and record.chapter_id == other.chapter_id
        and record.source_sha256 == other.source_sha256
        and max(record.source_lines[0], other.source_lines[0])
        <= min(record.source_lines[1], other.source_lines[1])
        for other in latest
    ) for record in identified)


def _validated_passages(
    decision: PassageInferenceDecision,
    scope: RegisteredCorpusScope,
    evidence: tuple[EvidenceRecord, ...],
    prior_reader_statements: tuple[ReaderStatement, ...],
    confidence_threshold: float,
    librarian: Librarian,
) -> BoundaryPassages | BoundaryUncertain:
    by_statement_id = {statement.statement_id: statement for statement in prior_reader_statements}
    statement_ids = set(by_statement_id)
    by_id = {record.evidence_id: record for record in evidence}
    selections = (
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
    if (
        decision.authorization_basis == "line_only"
        or not all(
            _statement_supports_work(by_statement_id[statement_id], scope, librarian)
            for statement_id in decision.supporting_statement_ids
        )
    ):
        return BoundaryUncertain(
            kind="uncertain", work_id=scope.work_id, book_version_id=scope.book_version_id,
            reason_code="progress_unverified", clarification_question=_clarification(scope),
        )
    if decision.confidence < confidence_threshold:
        return BoundaryUncertain(
            kind="uncertain", work_id=scope.work_id, book_version_id=scope.book_version_id,
            reason_code="low_confidence", confidence=decision.confidence,
            clarification_question=_clarification(scope),
        )
    try:
        grant = PassageGrant(
            records=tuple(by_id[evidence_id] for evidence_id in decision.passage_evidence_ids),
            supporting_statement_ids=decision.supporting_statement_ids,
        )
    except ValidationError:
        return BoundaryUncertain(
            kind="uncertain", work_id=scope.work_id, book_version_id=scope.book_version_id,
            reason_code="inference_unavailable", clarification_question=_clarification(scope),
        )
    return BoundaryPassages(
        grant=grant, confidence=decision.confidence, authorization_basis="session_supported",
    )


def _search_boundary_signal(
    query: str, scope: RegisteredCorpusScope, librarian: Librarian,
) -> tuple[EvidenceRecord, ...]:
    if len(query) > MAX_BOUNDARY_QUERY_CHARACTERS:
        return _interleave_evidence([
            _search_boundary_signal(query[start:start + MAX_BOUNDARY_QUERY_CHARACTERS], scope, librarian)
            for start in range(0, len(query), MAX_BOUNDARY_QUERY_CHARACTERS)
            if query[start:start + MAX_BOUNDARY_QUERY_CHARACTERS].strip()
        ])
    bundle = librarian.retrieve_for_judgement(
        SearchRequest(
            query=query,
            book_scopes=[BookScope(
                work_id=scope.work_id, book_version_id=scope.book_version_id,
                chapter_max=scope.max_chapter,
            )],
            retrieval_score_threshold=0.5,
            max_results=MAX_BOUNDARY_SEARCH_RESULTS,
            purpose="boundary_inference",
        )
    )
    return tuple(
        EvidenceRecord(
            evidence_id=item.evidence_id, work_id=item.work_id,
            book_version_id=item.book_version_id, chapter_id=item.chapter_id,
            chapter_number=item.chapter, part_id=item.part_id, location=item.location,
            source_sha256=item.source_sha256, source_lines=item.source_lines,
            text=item.excerpt,
        )
        for item in bundle.items
        if item.work_id == scope.work_id
        and item.book_version_id == scope.book_version_id
        and item.part_id == "main" and item.chapter is not None
        and item.chapter <= scope.max_chapter
    )


async def _progress_search_queries(
    current_line: str,
    prior_reader_statements: tuple[ReaderStatement, ...],
    planner: BoundaryPlanner,
) -> tuple[str, ...]:
    try:
        plan = await planner(
            current_line, prior_reader_statements=prior_reader_statements,
            search_target="reading_progress",
        )
        queries = tuple(dict.fromkeys(
            " ".join(dict.fromkeys((*part.context_spans, *part.reader_spans)))
            for part in plan.parts
        ))
    except Exception:
        logger.warning("Reading-progress planning failed; using original boundary search.")
        return ()
    if not queries:
        logger.info("Reading-progress planning returned no queries; using original boundary search.")
    return queries


def _interleave_evidence(
    streams: list[tuple[EvidenceRecord, ...]],
) -> tuple[EvidenceRecord, ...]:
    by_id: dict[str, EvidenceRecord] = {}
    for ranked_records in zip_longest(*streams):
        for record in ranked_records:
            if record is None:
                continue
            if record.evidence_id in by_id and by_id[record.evidence_id] != record:
                raise ValueError("Conflicting boundary evidence for one ID")
            if len(by_id) < MAX_BOUNDARY_CANDIDATES:
                by_id.setdefault(record.evidence_id, record)
    return tuple(by_id.values())


async def infer_spoiler_boundary(
    current_line: str,
    *,
    work_id: str,
    book_version_id: str,
    memories: tuple[RetrievalMemory, ...],
    librarian: Librarian,
    prior_reader_statements: tuple[ReaderStatement, ...] = (),
    judge: BoundaryJudge | None = None,
    event_identifier: EventIdentifier | None = None,
    planner: BoundaryPlanner | None = None,
    confidence_threshold: float = BOUNDARY_CONFIDENCE_THRESHOLD,
) -> BoundaryInferenceResult:
    """Privately validate chapter progress or a grant for exact known passages."""
    scope = librarian.registered_scope(work_id, book_version_id)
    if scope is None:
        raise ValueError("boundary inference requires a registered corpus revision")
    selected_memories = relevant_memories(memories, scope, librarian)
    search_signals = (
        current_line,
        *(statement.text for statement in reversed(prior_reader_statements)),
    )
    focused_queries = await _progress_search_queries(
        current_line, prior_reader_statements, planner or evidence_strength.plan_book_request,
    )
    try:
        streams = [
            _search_boundary_signal(query, scope, librarian)
            for query in dict.fromkeys((*focused_queries, *search_signals))
            if query.strip()
        ]
        if not any(streams):
            return BoundaryUncertain(
                kind="uncertain", work_id=scope.work_id,
                book_version_id=scope.book_version_id,
                reason_code="insufficient_context",
                clarification_question=_clarification(scope),
            )
        streams.extend(
            _search_boundary_signal(memory.text, scope, librarian)
            for memory in selected_memories
        )
        evidence = _interleave_evidence(streams)
    except Exception:
        return BoundaryUncertain(
            kind="uncertain",
            work_id=scope.work_id,
            book_version_id=scope.book_version_id,
            reason_code="inference_unavailable",
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

    try:
        decision = type(decision).model_validate_json(decision.model_dump_json())
    except (ValueError, TypeError, AttributeError):
        return BoundaryUncertain(
            kind="uncertain", work_id=scope.work_id, book_version_id=scope.book_version_id,
            reason_code="inference_unavailable", clarification_question=_clarification(scope),
        )

    if isinstance(decision, PassageInferenceDecision):
        return _validated_passages(
            decision, scope, evidence, prior_reader_statements, confidence_threshold, librarian
        )

    if boundary_memory_assessment_errors(
        decision, _boundary_input(current_line, selected_memories, evidence, prior_reader_statements),
    ):
        return BoundaryUncertain(
            kind="uncertain", work_id=scope.work_id, book_version_id=scope.book_version_id,
            reason_code="inference_unavailable", clarification_question=_clarification(scope),
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

    support_ids = tuple(anchor.evidence_id for anchor in decision.supporting_evidence)
    if len(set(support_ids)) != len(support_ids):
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
        supporting = tuple(by_id[evidence_id] for evidence_id in support_ids)
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

    if any(record.chapter_number is None or record.part_id != "main" for record in supporting):
        return BoundaryUncertain(
            kind="uncertain", work_id=scope.work_id, book_version_id=scope.book_version_id,
            reason_code="conflicting_context", clarification_question="Which part and chapter or named section have you completed?",
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
    task = LibrarianEventIdentificationInput(
        current_line=current_line, prior_reader_statements=prior_reader_statements,
        full_work_candidates=evidence,
    )
    try:
        identification = await (event_identifier or identify_reader_event)(task)
        if not isinstance(identification, (BoundaryEventIdentified, BoundaryEventUnresolved)):
            raise ValueError("Invalid event-identification result")
        identification = type(identification).model_validate_json(identification.model_dump_json())
        if event_identification_errors(identification, task):
            raise ValueError("Invalid event-identification anchors")
    except Exception:
        return BoundaryUncertain(
            kind="uncertain", work_id=scope.work_id, book_version_id=scope.book_version_id,
            reason_code="inference_unavailable", clarification_question=_clarification(scope),
        )
    if isinstance(identification, BoundaryEventUnresolved):
        return BoundaryUncertain(
            kind="uncertain", work_id=scope.work_id, book_version_id=scope.book_version_id,
            reason_code=identification.reason_code, clarification_question=_clarification(scope),
        )
    identified = tuple(by_id[identity] for identity in identification.evidence_ids)
    selected = tuple(
        by_id[identity]
        for occurrence in decision.event_resolution.occurrences
        if occurrence.disposition == "selected"
        for identity in occurrence.evidence_ids
    )
    if not _same_stopping_occurrence(identified, selected, derived_chapter):
        return BoundaryUncertain(
            kind="uncertain", work_id=scope.work_id, book_version_id=scope.book_version_id,
            reason_code="conflicting_context", clarification_question=_clarification(scope),
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
