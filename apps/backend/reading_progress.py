"""The session's chapter ceiling, written only from the reader's own declarations."""

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace

from src.linger.contracts.librarian import EvidenceRecord
from src.linger.contracts.reading import permits_scope
from src.linger.contracts.turn import ReleaseScope, ReleaseSource
from src.linger.corpus.registry import BookClarification
from src.linger.orchestration.grounding import librarian_service

from . import sessions
from .chapter_reference import NUMBER_WORDS, parse_chapter_answer
from .config import get_settings
from .contracts import ContextResolution
from .schemas import ChatRequest

QUOTED = re.compile(
    r"(?s:```.*?```)|\"[^\"]*\"|[“«]|(?<!\w)['‘]|`[^`\n]*`|^[ \t]*>[^\n]*",
    re.MULTILINE,
)
# Closers for QUOTED's bare openers; a single quote must close on its own line.
CLOSERS = {"“": re.compile("”"), "«": re.compile("»"), "'": re.compile(r"['’](?!\w)|\n")}
A = "['’]"
NUMBER_WORD = "(?:" + "|".join(
    word.replace(" ", r"[\s-]") for word in sorted(NUMBER_WORDS, key=len, reverse=True)
) + ")"
NUMBER = re.compile(rf"\d+|\b{NUMBER_WORD}\b", re.IGNORECASE)
CHAPTER_WORD = re.compile(r"\b(?:chapters?|ch|part)\b", re.IGNORECASE)
SENTENCE = re.compile(r"[^.!?\n]+[.!?]*")
QUESTION = re.compile(
    r"^\W*(?:why|what|how|who|whom|whose|where|when|which|is|was|are|were|does|did|do|"
    r"can|could|would|should|will|has|have|had)\b",
    re.IGNORECASE,
)
# Correction and limit words: with one, a question or a bare number may restate progress.
CUE = re.compile(
    r"\b(?:nope|nah|wait|sorry|oops|meant|typo|misspoke|mistake|wrong|actually|correction|make\s+that|rather|"
    r"more\s+like|only|just|not|limit|avoid|beyond|past|keep\s+to|stick)\b",
    re.IGNORECASE,
)
# Limit words that make a question restate progress; too common to give a bare number context.
LIMIT = re.compile(r"\b(?:after|before|keep|stay|within|stop|never|further|hold\s+off)\b|n['’]t\b", re.IGNORECASE)
LOCATION = (
    rf"(?:(?:\S+\s+){{0,3}}?(?:chapter|ch\b|part|section|scene|bit|page|end|beginning|start)|\d+|{NUMBER_WORD})"
)
PROGRESS = re.compile(
    rf"\bi(?:{A}m|\s+am)\s+(?:\w+\s+){{0,2}}?(?:halfway|partway|midway|in\s+the\s+middle|starting|"
    rf"reading\s+(?:chapter|ch\b|part)|(?:on|at|in|up\s+to|past|through)\s+{LOCATION})\b"
    rf"|\bi(?:{A}ve|{A}d|\s+have|\s+had)?\s+(?:\w+\s+){{0,2}}?(?:reached|stopped|skipped|started|"
    rf"got(?:ten)?\s+(?:to|as\s+far|through|past|up\s+to)|gone\s+past|read\s+(?:up\s+to|through|as\s+far|until))\b"
    rf"|\b(?:haven{A}?t|have\s+not|hasn{A}?t|has\s+not|not\s+yet|didn{A}?t|did\s+not|i{A}ve\s+not)\s+(?:\w+\s+)?"
    rf"(?:read|reached|got(?:ten)?|gone|started|finished|completed|met|seen|happened)\b"
    rf"|\bnot\s+(?:past|there\s+yet)\b|\bthat\s+far\b|\bgot\s+there\b|\bwhere\s+i(?:{A}m|\s+am)\b|\blost\s+track\b"
    rf"|\b(?:don{A}?t|do\s+not)\s+(?:spoil|tell\s+me)\b|\bhow\s+far\b|\bmy\s+progress\b|\bearlier\s+than\s+that\b"
    rf"|\bbehind\s+where\b|\bdifferent\s+book\b|\bstill\s+before\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PendingProgress:
    expected: sessions.ReadingProgress | None
    declared: sessions.ReadingProgress


def mask_quotes(text: str) -> str:
    """Blank quoted, blockquoted, and fenced text, keeping every offset."""
    # Closers are found by a forward scan rather than regex backtracking: once an opener has no closer,
    # no later opener of its kind before the same limit can close either, so unclosed runs stay linear.
    parts, copied, position = [], 0, 0
    unclosed_until = dict.fromkeys(CLOSERS, -1)
    while match := QUOTED.search(text, position):
        start, end = match.span()
        kind = "'" if match.group() == "‘" else match.group()
        if kind in CLOSERS:
            if start < unclosed_until[kind]:
                position = end
                continue
            close = CLOSERS[kind].search(text, end)
            if close is None or close.group() == "\n":
                unclosed_until[kind] = close.start() if close else len(text)
                position = end
                continue
            end = close.end()
        parts += [text[copied:start], " " * (end - start)]
        copied = position = end
    return "".join(parts) + text[copied:]


def _words(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[-–—]", " ", text.casefold().replace("’", "'"))).strip()


def _earlier_places(slot: sessions.ReadingProgress) -> set[str]:
    """Multi-word catalog titles and locations from chapters before the slot."""
    places = set()
    for unit in librarian_service.units_for(slot.work_id, slot.book_version_id):
        if unit.part_id != slot.part_id or unit.chapter_number is None or unit.chapter_number >= slot.chapter_max:
            continue
        for text in (unit.title, *unit.locations):
            place = re.sub(r"^(?:a|an|the)\s+", "", _words(text)).strip(" ?.!")
            if len(place.split()) >= 2:
                places.add(place)
    return places


def unparsed_progress(
    message: str, slot: sessions.ReadingProgress, parser_patterns: Iterable[re.Pattern[str]],
) -> bool:
    """Whether a message that declares nothing may speak to the reader's progress; quotes do not shield it."""
    last = librarian_service.registered_scope(slot.work_id, slot.book_version_id, part_id=slot.part_id).max_chapter
    short = len(re.findall(r"\w+", message)) <= 4
    places = _earlier_places(slot)
    for sentence in SENTENCE.findall(message):
        cued = CUE.search(sentence)
        if (QUESTION.search(sentence) or sentence.rstrip().endswith("?")) and not (cued or LIMIT.search(sentence)):
            continue
        chapters = (parse_chapter_answer(match.group()) for match in NUMBER.finditer(sentence))
        if (short or cued or CHAPTER_WORD.search(sentence)) and any(
            chapter is not None and chapter <= last for chapter in chapters
        ):
            return True
        text = _words(sentence)
        if any(re.search(rf"(?<!\w){re.escape(place)}(?!\w)", text) for place in places):
            return True
    return any(pattern.search(message) for pattern in (PROGRESS, *parser_patterns))


def _retract(session_id: str, progress: sessions.ReadingProgress) -> None:
    sessions.set_reading_progress(session_id, progress)
    sessions.supersede_reader_statements(session_id)


def apply(
    request: ChatRequest,
    resolution: ContextResolution,
    *,
    parser_patterns: Iterable[re.Pattern[str]],
) -> tuple[ContextResolution, PendingProgress | None, bool]:
    """Update the slot from this turn's resolution; return it, any staged write, and whether it was carried."""
    session_id = request.session_id
    slot = sessions.reading_progress(session_id)
    if (
        resolution.status == "confirmed" and resolution.boundary_source == "reader_confirmed"
        and resolution.chapter_max is not None and not resolution.unit_ids
    ):
        declared = sessions.ReadingProgress(
            resolution.work_id, resolution.book_version_id, resolution.part_id, resolution.chapter_max,
        )
        if (
            slot is not None and slot.chapter_max is not None
            and (slot.work_id, slot.part_id) == (declared.work_id, declared.part_id)
            and declared.chapter_max < slot.chapter_max
        ):
            _retract(session_id, declared)
            return resolution, None, False
        return resolution, None if declared == slot else PendingProgress(slot, declared), False
    if slot is None or slot.chapter_max is None:
        return resolution, None, False
    if resolution.clarification_question or unparsed_progress(request.message, slot, parser_patterns):
        _retract(session_id, replace(slot, chapter_max=None))
        return resolution, None, False
    selection = sessions.book_selection(session_id)
    if selection is None or (selection.book_id, selection.part_id) != (slot.work_id, slot.part_id):
        sessions.set_reading_progress(session_id, None)
        return resolution, None, False
    if resolution.status != "inferred" or resolution.work_id != slot.work_id:
        return resolution, None, False
    route = librarian_service.route_work(request.message, get_settings().allowed_book_version_ids)
    if route is not None and (isinstance(route, BookClarification) or route.scope.work_id != slot.work_id):
        return resolution, None, False
    return ContextResolution(
        status="confirmed", work_id=slot.work_id, work_title=resolution.work_title,
        book_version_id=slot.book_version_id, chapter_max=slot.chapter_max, part_id=slot.part_id,
        boundary_source="reader_confirmed", boundary_authorization_basis="explicit_progress",
        explanation="The reader declared this completed chapter earlier in this session.",
    ), None, True


def commit(session_id: str, pending: PendingProgress | None, release_source: ReleaseSource) -> None:
    """Write a staged declaration once released, unless the slot changed since it was staged."""
    if release_source != "application_clarification":
        sessions.clear_reading_candidate(session_id)
    if (
        pending is not None
        and release_source in {"muse_candidate", "application_clarification"}
        and sessions.reading_progress(session_id) is pending.expected
    ):
        sessions.set_reading_progress(session_id, pending.declared)


def permitted_evidence(session_id: str, records: Iterable[EvidenceRecord]) -> tuple[EvidenceRecord, ...]:
    """Drop earlier evidence from the slot's book that its current ceiling no longer permits."""
    slot = sessions.reading_progress(session_id)
    if slot is None:
        return tuple(records)
    if slot.chapter_max is None:
        return tuple(record for record in records if record.work_id != slot.work_id)
    scope = ReleaseScope(
        work_id=slot.work_id, book_version_id=slot.book_version_id,
        chapter_max=slot.chapter_max, part_id=slot.part_id,
    )
    return tuple(record for record in records if record.work_id != slot.work_id or permits_scope(scope, record))
