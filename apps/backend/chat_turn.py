"""Application-owned chat-turn workflow for Linger."""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4
from urllib.parse import urlsplit

import logfire
from opentelemetry.trace import format_trace_id

from src.linger.agents.build import build_triage_model
from src.linger.agents.muse.agent import muse_chat_agent
from src.linger.agents.provenance.agent import provenance_agent
from src.linger.contracts.curation import CuratedMemory
from src.linger.contracts.emotional import EmotionalContentPolicy
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.contracts.turn import ConfirmedReading, ReleaseScope
from src.linger.contracts.reading import scope_fields
from apps.backend.contracts import BookScope
from apps.backend.librarian import RegisteredCorpusScope
from src.linger.corpus.registry import BookClarification, ResolvedBook, resolve_book_identity
from src.linger.orchestration.connection import web_reach_permitted
from src.linger.orchestration.emotional import (
    EmotionalBoundaryValidationError,
    assess_emotional_boundary,
)
from src.linger.orchestration.grounding import librarian_service
from src.linger.orchestration.language_guard import detect_non_english
from src.linger.orchestration.self_harm_detection import detect_first_person_self_harm
from src.linger.evaluation_transcript import ConnectionEvaluationEvent, record_connection_event
from src.linger.orchestration.inspection_context import (
    ConnectionRunInspection,
    begin_connection_inspection,
    connection_inspections,
    reset_connection_inspection,
    register_connection_evidence,
)
from src.linger.orchestration.conversational_memory import (
    curate_after_capture,
    prepare_surfacing_handoff,
)
from src.linger.orchestration.reflection import (
    ReflectionRelease,
    emotional_boundary_release,
    emotional_preflight_safe_decline,
    language_boundary_release,
    reflection_reply,
)
from src.linger.orchestration.triage import expose_tools, triage_turn
from src.linger.orchestration.turn_context import (
    ToolExposure,
    reset_active_memories,
    reset_public_source_urls,
    reset_confirmed_reading,
    reset_connection_book_scopes,
    reset_reader_message,
    reset_reader_statements,
    reset_routing_context,
    reset_session_id,
    reset_tool_exposure,
    reset_turn_evidence,
    set_active_memories,
    set_public_source_urls,
    set_confirmed_reading,
    set_connection_book_scopes,
    set_reader_message,
    set_reader_statements,
    set_routing_context,
    set_session_id,
    set_tool_exposure,
    set_turn_evidence,
)
from src.linger.services.memory import (
    AccountContext,
    MemoryConflictError,
    MemoryPolicyError,
    MemoryPolicyService,
    MemoryRecord,
    MemoryServiceError,
)
from src.linger.contracts.surfacing import MemorySurfacingHandoff

from . import sessions
from .chapter_reference import parse_chapter_answer
from .config import get_settings
from .contracts import (
    ContextResolution,
    MuseDraftInput,
    MuseTurn,
    ReadingContext,
    TurnPolicy,
)
from .logger import ROOT_NAME
from .schemas import (
    CaptureInspection,
    ChatRequest,
    ChatResponse,
    ConnectionDeclineInspection,
    MemoryCaptureNotice,
    ReleaseInspection,
    TraceReference,
    TurnInspection,
)
from .telemetry import record_failure, set_span_attrs

logger = logging.getLogger(f"{ROOT_NAME}.backend")

settings = get_settings()
triage_model = build_triage_model()
# Triage only narrows Muse's tools, so a slow or failed call is abandoned.
TRIAGE_TIMEOUT_SECONDS = 10.0

CHAPTER_PATTERN = re.compile(r"\b(?:chapter|ch\.?)\s*[:#]?\s*([1-9]\d*)\b", re.IGNORECASE)
BARE_CHAPTER_ANSWER_PATTERN = re.compile(
    r"(?:chapter|ch\.?)\s*[:#]?\s*([1-9]\d*)\s*[.!?]?", re.IGNORECASE
)
TITLE_PREFIX_PATTERN = re.compile(
    r"(?:\bi(?:'m| am)\s+(?:still\s+)?reading|"
    r"\bi(?:'ve|’ve| have)?\s+read(?!\s+through\b)|"
    r"^\s*(?:reading|read(?!\s+through\b)))\s+(?P<title>.+)$",
    re.IGNORECASE,
)
TITLE_SUFFIX_PATTERN = re.compile(r"^\s+(?:of|in|from)\s+(?P<title>.+)$", re.IGNORECASE)
TITLE_SUFFIX_SEARCH_PATTERN = re.compile(
    r"\b(?:of|in|from|(?:while\s+)?reading)\s+(?P<title>.+)$",
    re.IGNORECASE,
)
TITLE_REFLECTION_CLAUSE_PATTERN = re.compile(
    r"\b(?:and|but)\b|,\s*\w+ing\b", re.IGNORECASE,
)
TITLE_SCENE_LABEL_PATTERN = re.compile(r"\s*(?:,[^,]+,|\([^()]+\))\s*")
# "In <title>, I've completed chapter 8" puts the title before the chapter.
TITLE_LEAD_PATTERN = re.compile(
    r"^\s*(?:in|from)\s+(?P<title>[^,.!?]+)",
    re.IGNORECASE,
)
TITLE_END_PATTERN = re.compile(
    r"\s*(?:,|;|\band\s+i(?:'m| am| have|'ve|’ve)\s+(?:read|finished|completed|through|up to|at|on))\b",
    re.IGNORECASE,
)
COMPLETION_PATTERN = re.compile(
    r"\b(?:i(?:'ve|’ve| have)\s+(?:now\s+)?(?:finished|completed|read\s+through|got\s+through)|"
    r"i\s+(?:now\s+)?(?:finished|completed)|i(?:'m| am)\s+(?:now\s+)?done\s+with)\b",
    re.IGNORECASE,
)
COMPLETED_CHAPTER_SUBJECT_PATTERN = re.compile(
    CHAPTER_PATTERN.pattern
    + r"\s+(?:is|was)\s+(?:the\s+)?(?:last|latest|final|furthest|most\s+recent)"
    r"\s+(?:chapter\s+)?(?:that\s+)?$",
    re.IGNORECASE,
)
IN_PROGRESS_PATTERN = re.compile(
    r"\b(?:still\s+(?:in|reading)|not\s+(?:yet\s+)?(?:finished|completed|done)|"
    r"(?:have|has|had)\s+not\s+(?:finished|completed)|"
    r"(?:haven['’]?t|hasn['’]?t|hadn['’]?t)\s+(?:finished|completed)|"
    r"in\s+the\s+middle|partway\s+through)\b",
    re.IGNORECASE,
)
AFFIRMATION_PATTERN = re.compile(
    r"^\s*(?:yes|yeah|yep|correct|that(?:'s| is)\s+right)\b",
    re.IGNORECASE,
)


def _declared_title(message: str, chapter_match: re.Match[str] | None) -> str | None:
    if chapter_match:
        after = message[chapter_match.end():]
        before = message[:chapter_match.start()]
        title_match = TITLE_SUFFIX_PATTERN.match(after)
        if title_match is None:
            title_match = TITLE_PREFIX_PATTERN.search(before)
        if title_match is None:
            suffix = re.split(r"[.!?]", after, maxsplit=1)[0]
            candidate = TITLE_SUFFIX_SEARCH_PATTERN.search(suffix)
            if candidate:
                prefix = suffix[:candidate.start()]
                # Conjunctions inside a delimited scene label belong to the
                # label; otherwise a new reflection clause ends the declaration.
                if TITLE_SCENE_LABEL_PATTERN.fullmatch(prefix) or not (
                    TITLE_REFLECTION_CLAUSE_PATTERN.search(prefix)
                ):
                    title_match = candidate
        if title_match is None:
            title_match = TITLE_LEAD_PATTERN.match(before)
    else:
        title_match = TITLE_PREFIX_PATTERN.search(message)
    if title_match is None:
        return None
    title = TITLE_END_PATTERN.split(title_match.group("title"), maxsplit=1)[0].strip(
        " \"'“”.,:;"
    )
    title = re.sub(r"^part\s+(?:[ivxlcdm]+|\d+)\s+of\s+", "", title, flags=re.IGNORECASE)
    return title or None


PART_PATTERN = re.compile(r"\bpart\s+([ivxlcdm]+|\d+)\b", re.IGNORECASE)
NAMED_LOCATION_KINDS = {
    "letter": "letter", "letters": "letter", "preface": "preface",
    "dedication": "dedication", "appendix": "appendix",
    "biographical introduction": "biography", "introduction to the letters": "introduction",
    "parody": "poem",
}
NAMED_LOCATION = "(?:" + "|".join(NAMED_LOCATION_KINDS) + ")"
NAMED_LOCATION_PATTERN = re.compile(rf"\b{NAMED_LOCATION}\b", re.IGNORECASE)
DECLARATION_END_PATTERN = re.compile(
    r"(?<!\bMr)(?<!\bMrs)(?<!\bDr)(?<!\bMs)(?<!\bSt)(?<!\bEsq)(?<!\bCh)[.!?;](?:\s|$)|"
    r"(?:[,—]\s*|\s+(?:and|but)\s+)"
    r"(?=(?:i|it|this|that|they|there|the\s+\w+\s+(?:stayed|stuck)"
    r"|what|why|how|tell|can|could|would|please)\b)",
    re.IGNORECASE,
)
READ_NAMED_PATTERN = re.compile(
    rf"\bi (?:have )?read\s+(?=(?:the\s+)?(?:editor['’]s\s+)?{NAMED_LOCATION}\b)",
    re.IGNORECASE,
)


def _completed_location(message: str) -> str | None:
    completion = COMPLETION_PATTERN.search(message) or READ_NAMED_PATTERN.search(message)
    if completion is None:
        return None
    location = DECLARATION_END_PATTERN.split(message[completion.end():], maxsplit=1)[0].strip()
    if not re.match(
        rf"(?:reading\s+)?(?:(?:the|that|this)\s+)?(?:editor['’]s\s+)?(?:part|chapter|ch\.?|scene|it|{NAMED_LOCATION})\b",
        location, re.IGNORECASE,
    ):
        # An earlier chapter grants progress only when it is the subject of
        # this completion, as in "Chapter 8 is the last chapter I've finished".
        if COMPLETED_CHAPTER_SUBJECT_PATTERN.search(message[:completion.start()]) and (
            location.casefold() in {"", "so far"}
            or re.match(r"(?:of|in|from)\s+\S", location, re.IGNORECASE)
        ):
            return _declaration_sentence(message, completion)
        return None
    return location


def _declaration_sentence(message: str, match: re.Match[str]) -> str:
    """Return the sentence containing a matched progress declaration."""
    start = max(message.rfind(mark, 0, match.start()) for mark in ".!?") + 1
    endings = tuple(
        index for mark in ".!?"
        if (index := message.find(mark, match.end())) >= 0
    )
    end = min(endings) + 1 if endings else len(message)
    return message[start:end].strip()


def _location_words(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.casefold())
    return " ".join(word for word in words if word not in {"mr", "mrs", "miss", "dr"})


def _named_book_title(location: str, selection: sessions.BookSelection | None) -> str | None:
    message = _location_words(location)
    names = list(NAMED_LOCATION_PATTERN.finditer(message))
    if len(names) != 1:
        return None
    name = names[0]
    end = name.end()
    if selection:
        version = librarian_service.version_for(selection.book_id)
        for unit in librarian_service.units_for(selection.book_id, version):
            if unit.kind != NAMED_LOCATION_KINDS[name.group().lower()]:
                continue
            for label in (unit.label, unit.title, unit.recipient, unit.date):
                if label:
                    match = re.search(rf"\b{re.escape(_location_words(label))}\b", message)
                    if match:
                        end = max(end, match.end())
    qualifier = re.search(r"\b(?:of|in)\s+(.+)$", message[end:])
    return qualifier.group(1) if qualifier else None


def _named_reading(request: ChatRequest, selection: sessions.BookSelection, location: str) -> ContextResolution:
    version = librarian_service.version_for(selection.book_id)
    units = librarian_service.units_for(selection.book_id, version)
    message = _location_words(location)
    names = NAMED_LOCATION_PATTERN.findall(location)
    kind = NAMED_LOCATION_KINDS[names[0].lower()] if len(names) == 1 else None
    explicit_part = PART_PATTERN.search(location) is not None
    candidates = []
    for unit in units:
        if unit.chapter_number is not None or unit.kind != kind or (explicit_part and unit.part_id != selection.part_id):
            continue
        labels = [unit.title, unit.label]
        if unit.recipient:
            labels.append(unit.recipient)
        if unit.kind in {"preface", "dedication", "appendix"}:
            labels.append(unit.kind)
        if any(_location_words(label) and _location_words(label) in message for label in labels):
            candidates.append(unit)
    dated = [unit for unit in candidates if unit.date and _location_words(unit.date) in message]
    if dated or re.search(r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b.*\b[12]\d{3}\b", message):
        candidates = dated
    if len(candidates) != 1:
        return ContextResolution(status="inferred", work_id=selection.book_id,
            work_title=selection.book_title, book_version_id=version,
            clarification_question="Which named section or letter did you finish? Please include the letter's recipient and date.",
            explanation="The named reading location is ambiguous; no reading permission was granted.")
    unit = candidates[0]
    sessions.set_book_selection(request.session_id, selection.model_copy(update={"part_id": unit.part_id}))
    return ContextResolution(status="confirmed", work_id=selection.book_id,
        work_title=selection.book_title, book_version_id=version,
        part_id=unit.part_id, unit_ids=(unit.chapter_id,), boundary_source="reader_confirmed",
        boundary_authorization_basis="explicit_progress",
        explanation="The reader explicitly completed this named unit; earlier units are not included.")


def _chapter_reading(selection: sessions.BookSelection, chapter: int) -> dict[str, object]:
    version = librarian_service.version_for(selection.book_id)
    scope = librarian_service.registered_scope(selection.book_id, version, part_id=selection.part_id)
    if scope is None or chapter > scope.max_chapter:
        return {"status": "inferred", "work_id": selection.book_id, "work_title": selection.book_title,
            "book_version_id": version, "clarification_question": "Which part and chapter have you completed?",
            "explanation": "That chapter does not exist in the selected part; no reading permission was granted."}
    return {"status": "confirmed", "work_id": selection.book_id, "work_title": selection.book_title,
        "book_version_id": version, "chapter_max": chapter, "part_id": selection.part_id,
        "boundary_source": "reader_confirmed", "boundary_authorization_basis": "explicit_progress",
        "explanation": "The reader explicitly confirmed this completed chapter in the current message."}


def resolve_reading_context(request: ChatRequest) -> ContextResolution:
    """Resolve reading context from explicit reader declarations only.

    Regexes validate direct declarations. Librarian routing no longer runs
    here: Muse decides when a request depends on a book and calls the
    `librarian_route` tool during its own turn, inside the validated
    Provenance and release pipeline.
    """
    candidate = sessions.reading_candidate(request.session_id)
    selection = sessions.book_selection(request.session_id)
    if selection and librarian_service.version_for(selection.book_id) not in settings.allowed_book_version_ids:
        sessions.clear_book_selection(request.session_id, cause="out_of_scope")
        selection = None
        candidate = None
    if candidate and librarian_service.version_for(candidate.book_id) not in settings.allowed_book_version_ids:
        sessions.clear_reading_candidate(request.session_id)
        candidate = None
    pending = sessions.pending_clarification(request.session_id)
    if pending and librarian_service.version_for(pending.book_id) not in settings.allowed_book_version_ids:
        sessions.clear_pending_clarification(request.session_id)
        pending = None
    in_progress = IN_PROGRESS_PATTERN.search(request.message) is not None
    completed_location = _completed_location(request.message) if not in_progress else None
    completed = completed_location is not None


    candidate_confirmed = bool(
        candidate and not in_progress and AFFIRMATION_PATTERN.search(request.message)
    )
    if candidate and candidate_confirmed:
        selection = sessions.BookSelection(book_id=candidate.book_id, book_title=candidate.book_title,
            part_id=candidate.part_id, source="reader_stated")
        sessions.set_book_selection(request.session_id, selection)

    progress_message = completed_location if completed_location is not None else request.message
    chapter_match = CHAPTER_PATTERN.search(progress_message)
    explicit_title = _declared_title(progress_message, chapter_match)
    if explicit_title is None:
        explicit_title = _declared_title(request.message, CHAPTER_PATTERN.search(request.message))
    named_location = NAMED_LOCATION_PATTERN.search(progress_message) is not None
    if named_location and completed:
        mentioned = resolve_book_identity(progress_message, settings.allowed_book_version_ids)
        named_selection = selection
        if isinstance(mentioned, ResolvedBook):
            named_selection = sessions.BookSelection(book_id=mentioned.registration.book.work_id)
        explicit_title = _named_book_title(progress_message, named_selection)

    identity = resolve_book_identity(
        explicit_title or request.message, settings.allowed_book_version_ids,
        exact=bool(explicit_title) or not (named_location and completed),
    )
    if explicit_title or identity is not None:
        if not isinstance(identity, ResolvedBook):
            sessions.clear_book_selection(request.session_id, cause="reader_named_other_book")
            clarification = identity if isinstance(identity, BookClarification) else BookClarification()
            return ContextResolution(
                status="unknown",
                clarification_question=clarification.question,
                explanation="The book identity is unresolved; no chapter progress is authorized.",
            )
        book = identity.registration.book
        if candidate and candidate.book_id != book.work_id:
            sessions.clear_reading_candidate(request.session_id)
            candidate = None
        selection = sessions.BookSelection(book_id=book.work_id, book_title=book.title,
            part_id=selection.part_id if selection and selection.book_id == book.work_id else "main",
            # A title the reader declared is theirs; a fuzzy match on the whole
            # message is the application's guess and must stay retractable.
            source="reader_stated" if explicit_title else "inferred")
        sessions.set_book_selection(request.session_id, selection)

    if completed and selection and (
        len(CHAPTER_PATTERN.findall(progress_message)) > 1 or (named_location and chapter_match is not None)
    ):
        return ContextResolution(
            status="inferred", work_id=selection.book_id, work_title=selection.book_title,
            book_version_id=librarian_service.version_for(selection.book_id),
            clarification_question="Which single chapter or named reading location have you completed?",
            explanation="The declaration contains multiple reading locations; no reading permission was granted.",
        )

    part_declaration = completed_location or (
        request.message if re.search(r"\bi(?:'m| am)\s+(?:in|reading)\s+part\b", request.message, re.IGNORECASE) else ""
    )
    parts = PART_PATTERN.findall(part_declaration)
    if selection and parts:
        part_id = {"i": "main", "1": "main", "ii": "letters", "2": "letters", "iii": "part-iii", "3": "part-iii"}.get(parts[0].lower())
        if part_id is None or len({value.lower() for value in parts}) != 1:
            return ContextResolution(status="inferred", work_id=selection.book_id,
                work_title=selection.book_title, book_version_id=librarian_service.version_for(selection.book_id),
                clarification_question="Which part and chapter have you completed?",
                explanation="The declared part is unsupported or ambiguous; no reading permission was granted.")
        selection = selection.model_copy(update={"part_id": part_id})
        sessions.set_book_selection(request.session_id, selection)
    if completed and named_location and selection and chapter_match is None:
        return _named_reading(request, selection, completed_location)

    if completed and chapter_match and selection:
        chapter = int(chapter_match.group(1))
        sessions.clear_pending_clarification(request.session_id)
        if candidate and selection.book_id == candidate.book_id:
            sessions.clear_reading_candidate(request.session_id)
        return ContextResolution(**_chapter_reading(selection, chapter))

    if (
        chapter_match is None
        and candidate
        and selection
        and selection.book_id == candidate.book_id
        and (completed or candidate_confirmed)
    ):
        sessions.clear_reading_candidate(request.session_id)
        sessions.clear_pending_clarification(request.session_id)
        return ContextResolution(
            status="confirmed",
            work_id=candidate.book_id,
            work_title=candidate.book_title,
            book_version_id=librarian_service.version_for(candidate.book_id),
            chapter_max=candidate.chapter,
            part_id=candidate.part_id,
            boundary_source="reader_confirmed",
            boundary_authorization_basis="explicit_progress",
            explanation="The reader confirmed the candidate book and completed scene in the current message.",
        )

    answered_chapter = parse_chapter_answer(request.message)
    if (
        pending
        and answered_chapter is not None
        and (selection is None or selection.book_id == pending.book_id)
    ):
        # A reply that is only a chapter reference answers the pending question,
        # whatever its lexical form ("6", "six", "chapter 6").
        chapter = answered_chapter
        selection = sessions.BookSelection(book_id=pending.book_id, book_title=pending.book_title,
            part_id=selection.part_id if selection else pending.part_id, source="reader_stated")
        sessions.set_book_selection(request.session_id, selection)
        reading = _chapter_reading(selection, chapter)
        # An answer the work cannot support leaves the question open, so the next
        # clarification still knows it is a repeat.
        if reading["status"] == "confirmed":
            sessions.clear_pending_clarification(request.session_id)
            sessions.clear_reading_candidate(request.session_id)
        return ContextResolution(**reading)

    if selection:
        return ContextResolution(
            status="inferred",
            work_id=selection.book_id,
            work_title=selection.book_title,
            book_version_id=librarian_service.version_for(selection.book_id),
            explanation="The active book is known, but this request has no validated spoiler boundary yet.",
        )

    return ContextResolution(
        status="unknown",
        explanation=(
            "No confirmed book or reading boundary. This describes reading "
            "state only; many messages need no book."
        ),
    )


def prepare_reflection_turn(
    request: ChatRequest,
    *,
    allow_memory_capture: bool,
    has_active_memories: bool = False,
    prior_evidence: tuple[EvidenceRecord, ...] = (),
    resolution: ContextResolution | None = None,
    memory_surfacing: MemorySurfacingHandoff | None = None,
    connection_book_scopes: tuple[ReleaseScope, ...] = (),
) -> tuple[TurnInspection, str, dict[str, object]]:
    """Build the request-scoped Muse input and Provenance policy context."""
    resolution = resolution or resolve_reading_context(request)
    context = (
        ReadingContext(
            work_id=resolution.work_id,
            **scope_fields(resolution),
            boundary_source=resolution.boundary_source,
        )
        if resolution.status == "confirmed" and resolution.work_id
        else None
    )
    turn_id = request.turn_id or str(uuid4())
    book_connection_permitted = (
        context is not None and librarian_service.has_corpus(context.work_id)
    )
    muse_turn = MuseTurn(
        turn_id=turn_id,
        user_message=request.message,
        reading_context=context,
        connection_book_scopes=connection_book_scopes,
        policy=TurnPolicy(
            spoiler_ceiling=context.chapter_max if context else None,
            allow_retrieval=book_connection_permitted,
            allow_connection=(
                book_connection_permitted or bool(connection_book_scopes)
                or web_reach_permitted() or has_active_memories
            ),
            allow_memory_capture=allow_memory_capture,
        ),
    )
    traces = [{
        "agent": "Router",
        "status": "complete",
        "detail": resolution.explanation,
    }]
    traces.extend([
        {"agent": "Librarian", "status": "waiting", "detail": "Waiting to see whether Muse requests bounded retrieval."},
        {"agent": "Serendipity", "status": "waiting", "detail": "Waiting to see whether Muse requests connection discovery."},
    ])

    muse_payload = MuseDraftInput(
        mode="draft",
        muse_turn=muse_turn,
        context_resolution=resolution,
        prior_evidence=prior_evidence,
        memory_surfacing=memory_surfacing,
    )
    inspection_prompt = json.dumps(
        muse_payload.model_dump(
            mode="json",
            exclude={"prior_evidence", "memory_surfacing"},
        ),
        ensure_ascii=False,
    )
    # Keep the optional hand-off out of ordinary turns while preserving the
    # established null-bearing shape of the other Muse input fields.
    muse_input_payload = muse_payload.model_dump(mode="json")
    if memory_surfacing is None:
        muse_input_payload.pop("memory_surfacing", None)
    muse_input = json.dumps(muse_input_payload, ensure_ascii=False)
    review_context: dict[str, object] = {
        "policy_constraints": muse_turn.policy.model_dump(mode="json"),
        "reading_context": context.model_dump(mode="json") if context else None,
        "connection_book_scopes": [scope.model_dump(mode="json") for scope in connection_book_scopes],
    }
    traces.append({"agent": "Muse", "status": "running", "detail": "Drafting a candidate response."})
    return TurnInspection(
        muse_turn=muse_turn.model_dump(mode="json"),
        context_resolution=resolution.model_dump(mode="json"),
        traces=traces,
        # Re-resolved passages are supplied to Muse but not duplicated into the
        # developer-only Inspect diagnostics.
        prompt=inspection_prompt,
    ), muse_input, review_context


@dataclass(frozen=True)
class AutomaticCaptureExecution:
    """Internal storage outcome; candidate text never enters inspection."""

    inspection: CaptureInspection
    record: MemoryRecord | None = None
    created: bool = False


def _commit_automatic_capture(
    release: ReflectionRelease,
    service: MemoryPolicyService,
    context: AccountContext,
) -> AutomaticCaptureExecution:
    """Apply deterministic policy without changing the response decision."""
    decision = release.capture_decision
    nomination = release.capture_nomination or "unavailable"
    if release.release_source == "application_language_boundary":
        return AutomaticCaptureExecution(
            inspection=CaptureInspection(
                nomination="unavailable",
                provenance_decision=None,
                binding="not_applicable",
                storage="suppressed",
                reason_code="language_boundary_capture_suppressed",
            )
        )
    if release.release_source == "application_emotional_boundary":
        preflight = release.boundary_origin == "preflight"
        return AutomaticCaptureExecution(
            inspection=CaptureInspection(
                nomination="unavailable" if preflight else nomination,
                provenance_decision=None if preflight else decision,
                binding="not_applicable",
                storage="suppressed",
                reason_code="emotional_boundary_capture_suppressed",
            )
        )
    if release.capture_failure is not None:
        return AutomaticCaptureExecution(
            inspection=CaptureInspection(
                nomination=nomination,
                provenance_decision=decision,
                binding="invalid",
                storage="refused",
                reason_code=release.capture_failure,
            )
        )
    candidate = release.automatic_capture_candidate
    if candidate is None:
        return AutomaticCaptureExecution(
            inspection=CaptureInspection(
                nomination=nomination,
                provenance_decision=decision,
                binding="not_applicable",
                storage="not_applicable",
                reason_code="not_applicable" if decision == "no_candidate" else None,
            )
        )
    if release.release_source in {"application_safe_decline", "application_clarification"}:
        return AutomaticCaptureExecution(
            inspection=CaptureInspection(
                nomination=nomination,
                provenance_decision=decision,
                binding="exact",
                storage="suppressed",
                reason_code=(
                    "clarification_capture_suppressed"
                    if release.release_source == "application_clarification"
                    else "safe_decline_capture_suppressed"
                ),
            )
        )
    try:
        result = service.save_automatic(context, candidate)
    except MemoryPolicyError as error:
        return AutomaticCaptureExecution(
            inspection=CaptureInspection(
                nomination="candidate",
                provenance_decision=decision,
                binding="exact",
                storage="refused",
                reason_code=error.reason,
            )
        )
    except MemoryConflictError:
        return AutomaticCaptureExecution(
            inspection=CaptureInspection(
                nomination="candidate",
                provenance_decision=decision,
                binding="exact",
                storage="refused",
                reason_code="source_event_conflict",
            )
        )
    except MemoryServiceError:
        return AutomaticCaptureExecution(
            inspection=CaptureInspection(
                nomination="candidate",
                provenance_decision=decision,
                binding="exact",
                storage="refused",
                reason_code="storage_unavailable",
            )
        )
    return AutomaticCaptureExecution(
        inspection=CaptureInspection(
            nomination="candidate",
            provenance_decision=decision,
            binding="exact",
            storage="committed",
            reason_code=None if result.created else "idempotent_replay",
        ),
        record=result.record,
        created=result.created,
    )


def _replace_trace(
    inspection: TurnInspection,
    agent: str,
    *,
    status: str,
    detail: str,
) -> None:
    """Replace one preallocated agent trace with fixed application metadata."""
    for index, trace in enumerate(inspection.traces):
        if trace.get("agent") == agent:
            inspection.traces[index] = {
                "agent": agent,
                "status": status,
                "detail": detail,
            }
            return


def _apply_connection_inspection(
    inspection: TurnInspection,
    run: ConnectionRunInspection,
) -> tuple[str, ...]:
    """Project one nested Serendipity run as fixed metadata only."""
    book_outcomes = run.book_search_outcomes

    if run.status == "decline":
        inspection.connection_decline = ConnectionDeclineInspection(
            reason=run.reason or "retrieval_unavailable",
            failure_code=(
                "connection_discovery_failed" if run.failure_code else None
            ),
        )
        _replace_trace(
            inspection,
            "Serendipity",
            status="failed" if run.failure_code else "declined",
            detail=(
                "Connection discovery failed closed; no diagnostic content was exposed."
                if run.failure_code
                else "Serendipity returned a typed decline; no diagnostic content was exposed."
            ),
        )
        return book_outcomes

    _replace_trace(
        inspection,
        "Serendipity",
        status="complete",
        detail=(
            f"Serendipity returned a validated {run.status}; release still depends "
            "on the shared evidence and Provenance gates."
        ),
    )
    return book_outcomes


def _mark_connection_skipped(inspection: TurnInspection) -> None:
    _replace_trace(
        inspection,
        "Serendipity",
        status="skipped",
        detail="Muse did not call serendipity_explore for this turn.",
    )


def _finalize_librarian_inspection(
    inspection: TurnInspection,
    release: ReflectionRelease,
    *,
    connection_book_outcomes: tuple[str, ...],
) -> None:
    """Surface successful direct grounding without leaking rejected content."""
    direct_calls = release.librarian_grounding_calls
    direct_kinds = tuple(
        response.get("kind")
        for call in direct_calls
        if isinstance((response := call.get("response")), dict)
    )
    connection_failed = "retrieval_unavailable" in connection_book_outcomes
    direct_failed = any(
        call.get("outcome") != "success" for call in direct_calls
    ) or "failure" in direct_kinds
    direct_clarified = "clarification" in direct_kinds
    direct_no_match = direct_kinds and all(kind == "no_match" for kind in direct_kinds)
    released = release.release_source in {"muse_candidate", "application_clarification"}
    inspection.librarian_grounding = (
        list(direct_calls) if released else []
    )

    if not released and (connection_book_outcomes or direct_calls):
        status = "declined"
        detail = "Retrieval diagnostics were withheld because no Muse candidate was released."
    elif connection_failed or direct_failed:
        status = "failed"
        detail = "A Librarian call failed; no failed-retrieval content was exposed."
    elif connection_book_outcomes and direct_calls:
        status = "complete"
        detail = (
            "Librarian completed bounded connection retrieval and direct Muse "
            f"grounding ({len(direct_calls)} call(s))."
        )
    elif connection_book_outcomes:
        status = "complete"
        detail = "Librarian completed bounded book-corpus retrieval for Serendipity."
    elif direct_clarified:
        status = "declined"
        detail = "Librarian requested clarification instead of searching the corpus."
    elif direct_no_match:
        status = "complete"
        detail = "Muse asked Librarian to route this request; no book match was found."
    elif direct_calls:
        status = "complete"
        detail = f"Muse called Librarian directly {len(direct_calls)} time(s) for book grounding."
    else:
        status = "skipped"
        detail = "No Librarian retrieval was requested for this turn."

    _replace_trace(
        inspection,
        "Librarian",
        status=status,
        detail=detail,
    )


def _rehydrate_session_evidence(session_id: str) -> tuple[EvidenceRecord, ...]:
    """Resolve exact IDs cited by earlier released replies; never persist text."""
    records: dict[str, EvidenceRecord] = {}
    for evidence_id in sessions.released_evidence_ids(session_id):
        try:
            record = librarian_service.fetch_by_id(evidence_id)
        except Exception:
            continue
        if record is None:
            continue
        existing = records.get(record.evidence_id)
        if existing is not None and existing != record:
            raise ValueError("a released evidence ID resolved ambiguously")
        records[record.evidence_id] = record
    return tuple(records.values())


def _require_fresh_reading_setup(request: ChatRequest) -> None:
    if (
        sessions.history(request.session_id)
        or sessions.turn_records(request.session_id)
        or sessions.book_selection(request.session_id) is not None
        or sessions.reading_candidate(request.session_id) is not None
        or sessions.pending_clarification(request.session_id) is not None
    ):
        raise ValueError("initial reading requires a fresh session")


def _registered_reading_scope(scope: ReleaseScope) -> RegisteredCorpusScope:
    """Validate a trusted book revision and selector before granting its text."""
    scope = ReleaseScope.model_validate(scope.model_dump())
    registered = librarian_service.registered_scope(
        scope.work_id, scope.book_version_id,
        part_id=scope.part_id if not scope.unit_ids else "main",
    )
    if (
        registered is None
        or scope.book_version_id not in settings.allowed_book_version_ids
        or (scope.chapter_max is not None and scope.chapter_max > registered.max_chapter)
    ):
        raise ValueError("initial reading exceeds the registered application book scope")
    librarian_service.eligible_units(BookScope(**scope.model_dump()))
    return registered


def _apply_connection_book_scopes(
    request: ChatRequest, scopes: tuple[ReleaseScope, ...],
) -> ContextResolution:
    """Use confirmed comparison permissions without inventing a primary book."""
    _require_fresh_reading_setup(request)
    works = {scope.work_id for scope in scopes}
    if not scopes or len(works) != len(scopes):
        raise ValueError("connection book scopes require nonempty, unique works")
    for scope in scopes:
        _registered_reading_scope(scope)
    progress_statements = (
        _declaration_sentence(request.message, match)
        for pattern in (COMPLETION_PATTERN, IN_PROGRESS_PATTERN)
        for match in pattern.finditer(request.message)
    )
    declares_book_progress = any(
        CHAPTER_PATTERN.search(statement) or NAMED_LOCATION_PATTERN.search(statement)
        or resolve_book_identity(statement, settings.allowed_book_version_ids) is not None
        for statement in progress_statements
    )
    if (
        declares_book_progress
        or READ_NAMED_PATTERN.search(request.message)
        or BARE_CHAPTER_ANSWER_PATTERN.fullmatch(request.message.strip())
        or (TITLE_PREFIX_PATTERN.search(request.message) and (
            CHAPTER_PATTERN.search(request.message) or NAMED_LOCATION_PATTERN.search(request.message)
        ))
    ):
        raise ValueError("connection setup cannot override a reader's progress declaration")
    identity = resolve_book_identity(request.message, settings.allowed_book_version_ids)
    mentioned = (
        (identity.registration,) if isinstance(identity, ResolvedBook)
        else identity.candidates if isinstance(identity, BookClarification) else ()
    )
    if (isinstance(identity, BookClarification) and not mentioned) or any(
        item.book.work_id not in works for item in mentioned
    ):
        raise ValueError("connection setup conflicts with the reader's named sources")
    return ContextResolution(
        status="unknown",
        explanation=(
            "The application supplied independently confirmed book scopes for this "
            "connection comparison. No single book is active."
        ),
    )


def _apply_initial_reading(
    request: ChatRequest,
    initial_reading: ReleaseScope,
) -> ContextResolution:
    """Apply trusted reader setup only to a fresh session and coherent Line."""
    _require_fresh_reading_setup(request)
    registered = _registered_reading_scope(initial_reading)
    identity = resolve_book_identity(request.message, settings.allowed_book_version_ids)
    if (isinstance(identity, BookClarification) and (
        len(identity.candidates) != 1
        or identity.candidates[0].book.work_id != initial_reading.work_id
    )) or (
        isinstance(identity, ResolvedBook)
        and identity.registration.book.work_id != initial_reading.work_id
    ):
        raise ValueError("initial reading conflicts with the reader's book declaration")
    if IN_PROGRESS_PATTERN.search(request.message) is not None:
        raise ValueError("initial reading conflicts with the reader's unfinished progress")
    chapter = CHAPTER_PATTERN.search(request.message)
    declares_progress = (
        COMPLETION_PATTERN.search(request.message) is not None
        or IN_PROGRESS_PATTERN.search(request.message) is not None
        or BARE_CHAPTER_ANSWER_PATTERN.fullmatch(request.message.strip()) is not None
    )
    if chapter is not None and declares_progress and (
        int(chapter.group(1)) != initial_reading.chapter_max
        or IN_PROGRESS_PATTERN.search(request.message)
    ):
        raise ValueError("initial reading conflicts with the reader's chapter declaration")
    sessions.set_book_selection(request.session_id, sessions.BookSelection(
        book_id=registered.work_id, book_title=registered.title, part_id=initial_reading.part_id,
        source="reader_stated",
    ))
    resolved = resolve_reading_context(request)
    if resolved.clarification_question or (
        resolved.work_id is not None and resolved.work_id != initial_reading.work_id
    ) or (resolved.status == "confirmed" and scope_fields(resolved) != scope_fields(initial_reading)):
        raise ValueError("initial reading conflicts with unresolved reader context")
    return ContextResolution(
        status="confirmed", work_id=registered.work_id, work_title=registered.title,
        book_version_id=registered.book_version_id, **scope_fields(initial_reading),
        boundary_source="reader_confirmed", boundary_authorization_basis="explicit_progress",
        explanation="The application supplied the reader's confirmed initial book scope.",
    )


async def _turn_tool_exposure(
    request: ChatRequest,
    inspection: TurnInspection,
) -> ToolExposure:
    """Triage the reader message once and fix the tools Muse is offered this turn."""
    started = perf_counter()
    with logfire.span("chat.tool_exposure") as span:
        try:
            needs = await asyncio.wait_for(
                triage_turn(request.message, muse=muse_chat_agent, model=triage_model),
                timeout=TRIAGE_TIMEOUT_SECONDS,
            )
        except Exception:
            # A triage fault must never fail the reader's turn; `expose_tools`
            # narrows rather than widens exposure when it has no needs.
            needs = None
        exposure = expose_tools(
            needs,
            previously_called=sessions.called_tools(request.session_id),
            book_override=(
                inspection.muse_turn.get("reading_context") is not None
                or sessions.pending_clarification(request.session_id) is not None
            ),
        )
        tools = sorted(exposure.tools)
        set_span_attrs(span, {
            "triage.failed": needs is None,
            "triage.book_content": needs.book_content if needs else None,
            "triage.memory": needs.memory if needs else None,
            "triage.override_attempt": needs.override_attempt if needs else None,
            "triage.exposed_tools": tools,
            "triage.pinned_intent": exposure.pinned_intent,
        })
    elapsed = perf_counter() - started
    inspection.tool_exposure = {
        "triage": needs.model_dump(mode="json") if needs else None,
        "triage_failed": needs is None,
        "tools": tools,
        "pinned_intent": exposure.pinned_intent,
    }
    inspection.traces.insert(1, {
        "agent": "Router",
        "status": "complete" if needs else "failed",
        "detail": (
            (
                f"Turn triage: book_content={needs.book_content}, "
                f"memory={needs.memory}, override_attempt={needs.override_attempt}."
                if needs
                else (
                    "Turn triage failed, so exposure falls back to the book tools "
                    "and this session's earlier tools."
                )
            )
            + f" Tools offered to Muse: {', '.join(tools) or 'none'}"
            + (f" (intent {exposure.pinned_intent})." if exposure.pinned_intent else ".")
        ),
    })
    logger.info(
        "Turn triage elapsed=%.2fs failed=%s book_content=%s memory=%s "
        "override_attempt=%s exposed_tools=%s pinned_intent=%s",
        elapsed,
        str(needs is None).lower(),
        needs.book_content if needs else "none",
        needs.memory if needs else "none",
        needs.override_attempt if needs else "none",
        ",".join(tools) or "none",
        exposure.pinned_intent or "none",
    )
    return exposure


async def _run_chat_pipeline(
    request: ChatRequest,
    reading_state: sessions.ReadingStateSnapshot,
    service: MemoryPolicyService,
    account: AccountContext,
    *,
    initial_reading: ReleaseScope | None = None,
    connection_book_scopes: tuple[ReleaseScope, ...] | None = None,
    public_source_urls: tuple[str, ...] | None = None,
) -> tuple[TurnInspection, ReflectionRelease, AutomaticCaptureExecution]:
    """Run the agent pipeline without adding request content to telemetry."""
    prior_evidence = _rehydrate_session_evidence(request.session_id)
    if connection_book_scopes is not None:
        resolution = _apply_connection_book_scopes(request, connection_book_scopes)
    else:
        resolution = (
            _apply_initial_reading(request, initial_reading)
            if initial_reading is not None else resolve_reading_context(request)
        )
    release: ReflectionRelease | None = None
    # Self-harm always wins: a first-person self-harm phrase skips the
    # language guard so the emotional-boundary preflight below still applies.
    language_verdict = (
        None
        if detect_first_person_self_harm(request.message)
        else detect_non_english(request.message)
    )
    if language_verdict is not None:
        release = language_boundary_release()
    else:
        try:
            boundary = await assess_emotional_boundary(
                request.message,
                EmotionalContentPolicy(),
                provenance=provenance_agent,
            )
        except asyncio.CancelledError:
            raise
        except EmotionalBoundaryValidationError:
            release = emotional_preflight_safe_decline(
                failure_type="validation",
                retryable=False,
            )
        except Exception:
            release = emotional_preflight_safe_decline()
        else:
            if boundary.decision in ("apply_boundary", "apply_self_harm_boundary"):
                release = emotional_boundary_release(
                    origin="preflight", decision=boundary.decision
                )

    active_memories: tuple[CuratedMemory, ...] = ()
    if release is None:
        try:
            active_memories = tuple(service.list_for_retrieval(account))
        except MemoryServiceError:
            pass

    memory_surfacing: MemorySurfacingHandoff | None = None
    if release is None and active_memories:
        try:
            memory_surfacing = await prepare_surfacing_handoff(
                account_scope=account.account_id,
                current_context=request.message,
                memories=active_memories,
                now=datetime.now(UTC),
            )
        except Exception:
            # Surfacing is proposal-only. Failure must not block the ordinary
            # conversation or manufacture a suggestion.
            memory_surfacing = None

    inspection, muse_input, review_context = prepare_reflection_turn(
        request,
        allow_memory_capture=service.capture_enabled(account),
        has_active_memories=bool(active_memories),
        prior_evidence=prior_evidence,
        resolution=resolution,
        memory_surfacing=memory_surfacing,
        connection_book_scopes=connection_book_scopes or (),
    )

    context = inspection.muse_turn.get("reading_context")
    book_version_id = (
        librarian_service.version_for(context["work_id"]) if context else None
    )
    release_scope = (
        ReleaseScope(
            work_id=context["work_id"],
            book_version_id=book_version_id,
            chapter_max=context["chapter_max"], part_id=context.get("part_id", "main"),
            unit_ids=context.get("unit_ids", ()),
        )
        if context and book_version_id
        else None
    )
    nested_connections: tuple[ConnectionRunInspection, ...] = ()
    if release is None:
        # The revision reuses the draft's exposure: triage runs once per reader turn.
        exposure = await _turn_tool_exposure(request, inspection)
        review_context["override_attempt"] = exposure.override_attempt
        token = set_confirmed_reading(
            ConfirmedReading(
                work_id=context["work_id"], chapter_max=context["chapter_max"],
                part_id=context.get("part_id", "main"), unit_ids=context.get("unit_ids", ())
            )
            if context
            else None
        )
        evidence_token = set_turn_evidence(prior_evidence)
        reader_message_token = set_reader_message(request.message)
        statements_token = set_reader_statements(sessions.reader_statements(request.session_id))
        routing_token = set_routing_context()
        session_id_token = set_session_id(request.session_id)
        memories_token = set_active_memories(active_memories)
        connection_token = begin_connection_inspection()
        public_sources_token = set_public_source_urls(public_source_urls)
        exposure_token = set_tool_exposure(exposure)
        connection_scopes_token = set_connection_book_scopes(connection_book_scopes or ())
        try:
            if memory_surfacing is not None:
                register_connection_evidence(memory_surfacing.sources)
            release = await reflection_reply(
                muse_input,
                sessions.muse_history(request.session_id),
                muse=muse_chat_agent,
                provenance=provenance_agent,
                review_context=review_context,
                release_scope=release_scope,
                previously_released_evidence_ids=frozenset(
                    record.evidence_id for record in prior_evidence
                ),
                capture_source_text=request.message,
                source_event_id=inspection.muse_turn["turn_id"],
            )
        finally:
            nested_connections = connection_inspections()
            reset_connection_inspection(connection_token)
            reset_tool_exposure(exposure_token)
            reset_public_source_urls(public_sources_token)
            reset_connection_book_scopes(connection_scopes_token)
            reset_active_memories(memories_token)
            reset_reader_message(reader_message_token)
            reset_reader_statements(statements_token)
            reset_routing_context(routing_token)
            reset_session_id(session_id_token)
            reset_turn_evidence(evidence_token)
            reset_confirmed_reading(token)
    record_connection_event(ConnectionEvaluationEvent(
        kind="release",
        status="released" if release.release_source == "muse_candidate" else "declined",
        release_source=release.release_source,
        failure_stage=release.failure_stage,
        provenance_verdicts=release.provenance_verdicts,
        released_evidence_ids=release.released_evidence_ids,
    ))
    connection_book_outcomes: tuple[str, ...] = ()
    if nested_connections:
        connection_book_outcomes = _apply_connection_inspection(
            inspection,
            nested_connections[-1],
        )
    else:
        _mark_connection_skipped(inspection)
    _finalize_librarian_inspection(
        inspection,
        release,
        connection_book_outcomes=connection_book_outcomes,
    )
    if release.release_source not in {"muse_candidate", "application_clarification"}:
        sessions.restore_reading_state(request.session_id, reading_state)
    capture = _commit_automatic_capture(release, service, account)
    curation_outcome = None
    if capture.record is not None:
        curation_outcome = await curate_after_capture(
            account,
            capture.record,
            created=capture.created,
            service=service,
        )
        capture = replace(
            capture,
            inspection=capture.inspection.model_copy(
                update={"curation_status": curation_outcome.status}
            ),
        )
    sessions.append_turn(
        request.session_id,
        request.message,
        release.reply,
        turn_id=inspection.muse_turn["turn_id"],
        release_source=release.release_source,
        evidence_ids=release.evidence_ids,
        review_finding_codes=release.review_finding_codes,
        tool_names=release.tool_names,
    )
    return inspection, release, capture


class ChatTurnError(RuntimeError):
    """Stable application failure exposed to transport adapters."""

    def __init__(self, trace: TraceReference) -> None:
        super().__init__("chat turn failed")
        self.trace = trace


async def run_chat_turn(
    request: ChatRequest,
    service: MemoryPolicyService,
    account: AccountContext,
    *,
    initial_reading: ReleaseScope | None = None,
    connection_book_scopes: tuple[ReleaseScope, ...] | None = None,
    public_source_urls: tuple[str, ...] | None = None,
) -> ChatResponse:
    """Run a turn with optional trusted setup; transport payloads cannot grant it."""
    if initial_reading is not None and connection_book_scopes is not None:
        raise ValueError("choose a focused initial reading or connection book scopes")
    if public_source_urls is not None:
        if len(public_source_urls) != len(set(public_source_urls)):
            raise ValueError("public source URLs must be unique")
        for url in public_source_urls:
            parsed = urlsplit(url)
            if (
                parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or len(url) > 2_000
            ):
                raise ValueError("public sources require bounded HTTP URLs without credentials")
    started = perf_counter()
    reading_state = sessions.snapshot_reading_state(request.session_id)
    cancelled = False
    failure: Exception | None = None
    inspection: TurnInspection | None = None
    release: ReflectionRelease | None = None
    capture: AutomaticCaptureExecution | None = None
    with logfire.span(
        "chat.turn",
        status="started",
    ) as span:
        span_context = span.get_span_context()
        trace = TraceReference(
            trace_id=format_trace_id(span_context.trace_id),
        )
        try:
            inspection, release, capture = await _run_chat_pipeline(
                request,
                reading_state,
                service,
                account,
                initial_reading=initial_reading,
                connection_book_scopes=connection_book_scopes,
                public_source_urls=public_source_urls,
            )
        except asyncio.CancelledError:
            cancelled = True
            sessions.restore_reading_state(request.session_id, reading_state)
            record_failure(
                span,
                stage="chat_turn",
                code="request_cancelled",
                retryable=False,
                failure_type="application",
            )
            set_span_attrs(
                span,
                {
                    "request.outcome": "cancelled",
                },
            )
        except Exception as exc:
            failure = exc
            sessions.restore_reading_state(request.session_id, reading_state)
            record_failure(
                span,
                stage="chat_turn",
                code="chat_turn_failed",
                retryable=True,
                failure_type="application",
            )
            set_span_attrs(
                span,
                {
                    "request.outcome": "failed",
                },
            )
        else:
            set_span_attrs(
                span,
                {
                    "status": "success",
                    "request.outcome": (
                        "declined"
                        if release.release_source == "application_safe_decline"
                        else "completed"
                    ),
                    "release.source": release.release_source,
                    "release.boundary_origin": release.boundary_origin,
                },
            )

    if cancelled:
        logger.info(
            "Agent run cancelled elapsed=%.2fs failure_stage=chat_turn "
            "failure_code=request_cancelled retryable=false",
            perf_counter() - started,
        )
        raise asyncio.CancelledError

    if failure is not None:
        logger.error(
            "Agent run failed elapsed=%.2fs failure_stage=chat_turn "
            "failure_code=chat_turn_failed retryable=true",
            perf_counter() - started,
        )
        raise ChatTurnError(trace) from None

    assert inspection is not None and release is not None and capture is not None

    logger.info(
        "Agent run completed elapsed=%.2fs release_source=%s "
        "provenance_path=%s findings=%s revisions=%d failure_stage=%s",
        perf_counter() - started,
        release.release_source,
        ",".join(release.provenance_verdicts) or "none",
        # Risk codes only. The matching critique text quotes rejected candidate
        # content and is intentionally absent from logs and API responses.
        ",".join(release.finding_codes) or "none",
        release.revision_count,
        release.failure_stage or "none",
    )
    inspection.release = ReleaseInspection(
        release_source=release.release_source,
        boundary_origin=release.boundary_origin,
        provenance_verdicts=release.provenance_verdicts,
        finding_codes=release.finding_codes,
        # A rejected draft still declares evidence, so report handles only for a
        # reply that actually reached the reader.
        released_evidence_ids=(
            release.evidence_ids
            if release.release_source == "muse_candidate"
            else ()
        ),
        revision_count=release.revision_count,
        failure_stage=release.failure_stage,
        failure_type=release.failure_type,
        failure_retryable=release.failure_retryable,
        capture=capture.inspection,
    )
    verdict_path = " → ".join(release.provenance_verdicts)
    if release.release_source == "muse_candidate":
        inspection.traces[-1] = {
            "agent": "Muse",
            "status": "complete",
            "detail": (
                "Provenance and deterministic release validation approved the "
                "candidate that was released."
            ),
        }
        provenance_status = "complete"
        provenance_detail = f"Recorded review path: {verdict_path}."
    elif release.release_source == "application_clarification":
        inspection.traces[-1] = {
            "agent": "Muse",
            "status": "complete",
            "detail": "The application released Librarian's validated clarification question.",
        }
        provenance_status = "complete"
        provenance_detail = f"Recorded review path: {verdict_path}."
    elif release.release_source == "application_emotional_boundary":
        if release.boundary_origin == "preflight":
            inspection.traces[-1] = {
                "agent": "Muse",
                "status": "skipped",
                "detail": (
                    "The emotional boundary was applied before Muse or its tools ran."
                ),
            }
            provenance_detail = (
                "The no-tool preflight required the application-owned emotional boundary."
            )
        else:
            inspection.traces[-1] = {
                "agent": "Muse",
                "status": "declined",
                "detail": (
                    "Muse ran, but its candidate was replaced by the fixed "
                    "application-owned emotional boundary."
                ),
            }
            provenance_detail = (
                "Candidate review caught a preflight miss and required the fixed "
                f"boundary; recorded review path: {verdict_path}."
            )
        provenance_status = "complete"
    elif release.release_source == "application_language_boundary":
        inspection.traces[-1] = {
            "agent": "Muse",
            "status": "skipped",
            "detail": (
                "The English-only language guard released the fixed notice "
                "before Muse, Librarian, Serendipity, or Provenance ran."
            ),
        }
        provenance_status = "skipped"
        provenance_detail = (
            "The language guard applied before any model ran; Provenance was "
            "not invoked."
        )
    else:
        inspection.traces[-1] = {
            "agent": "Muse",
            "status": (
                "skipped"
                if release.failure_stage == "emotional_boundary_preflight"
                else "declined"
            ),
            "detail": (
                "The emotional-boundary preflight failed closed before Muse ran."
                if release.failure_stage == "emotional_boundary_preflight"
                else "No Muse candidate was released; the application supplied its safe decline."
            ),
        }
        if release.failure_stage == "deterministic_validation":
            provenance_status = "complete"
            provenance_detail = (
                f"Recorded review path: {verdict_path}; deterministic release "
                "validation failed closed."
            )
        else:
            if release.failure_stage in {
                "emotional_boundary_preflight",
                "provenance_review",
            }:
                provenance_status = "failed"
                provenance_detail = (
                    "The emotional-boundary preflight failed; no candidate was produced."
                    if release.failure_stage == "emotional_boundary_preflight"
                    else "Provenance review failed; no candidate was released."
                )
            elif release.failure_stage:
                provenance_status = "declined"
                provenance_detail = (
                    f"Candidate production failed at {release.failure_stage}; no "
                    "candidate was released."
                )
            else:
                provenance_status = "declined"
                provenance_detail = (
                    f"Recorded review path: {verdict_path}; no Muse candidate was released."
                )
    inspection.traces.append({
        "agent": "Provenance",
        "status": provenance_status,
        "detail": provenance_detail,
    })
    inspection.traces.append(
        {
            "agent": "Memory & Policy",
            "status": (
                "complete"
                if capture.inspection.storage == "committed"
                else (
                    "declined"
                    if capture.inspection.storage in {"refused", "suppressed"}
                    else "not_run"
                )
            ),
            "detail": (
                "A reviewed candidate was committed by deterministic policy."
                if capture.inspection.storage == "committed"
                else (
                    f"No write occurred: {capture.inspection.reason_code}."
                    if capture.inspection.reason_code
                    else "No reviewed memory candidate reached storage."
                )
            ),
        }
    )
    notice = (
        MemoryCaptureNotice()
        if capture.record is not None and capture.inspection.storage == "committed"
        else None
    )
    return ChatResponse(
        reply=release.reply,
        inspection=inspection,
        trace=trace,
        memory_capture=notice,
    )
