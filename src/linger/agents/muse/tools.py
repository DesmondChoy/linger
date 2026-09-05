"""Muse's tool adapters onto the grounding and connection pipelines.

A thin adapter and nothing else: all safety logic (authority checks, the
access scope, the spoiler ceiling, fail-closed behaviour) lives in
`grounding.py` and `connection.py`, where Muse cannot reach or influence it.
This module only forwards Muse's arguments into a request the orchestration
module validates.
"""

from __future__ import annotations

from typing import Literal

from apps.backend.contracts import ConnectionBrief
from src.linger.agents.serendipity.models import ConnectionExplorationResult
from src.linger.contracts.librarian import LibrarianResponse, LibrarianRoutingResponse
from src.linger.contracts.reading import ReadingBoundary
from src.linger.orchestration.connection import connection_exploration
from src.linger.orchestration.grounding import build_request, grounding_evidence
from src.linger.orchestration.routing import route_reader_message
from src.linger.orchestration.turn_context import reader_message


async def librarian_search(
    query: str,
    work_id: str,
    book_version_id: str,
    reading_boundary: ReadingBoundary | None,
    max_final_evidence: int = 5,
) -> LibrarianResponse:
    """Search application-authorized book text for passages relevant to `query`.

    Use this when answering would benefit from grounding in the book's actual
    text rather than general knowledge. `work_id` and `book_version_id` must
    match the application-validated request scope. Pass the validated current
    chapter position from `reading_context` as `reading_boundary` (its
    `chapter_state` of "started" or "completed" determines how far into the
    book the search is allowed to look — never chapters beyond what the
    reader is known to have reached). After a `passages` route, pass
    `reading_boundary=None` to fetch only the granted exact passages; this does
    not establish chapter completion or allow neighboring text. Without either
    permission, `reading_boundary=None` returns a clarification instead of search
    results. The response may be a
    clarification request, a retrieval result (with or without evidence), or
    a retrieval failure — handle all three without assuming evidence exists.
    For a clarification, ask its exact question without evidence or other tools.
    """
    request = build_request(query, work_id, book_version_id, reading_boundary, max_final_evidence)
    return await grounding_evidence(request)


async def librarian_route() -> LibrarianRoutingResponse:
    """Identify whether the reader's message depends on a specific confirmed book.

    Call this only when the request appears to depend on a specific book — an
    explicit title, a character, or an evident continuation of a book already
    in progress. Never call it for an incidental word inside otherwise
    personal reflection. The application supplies the exact current reader
    message and earlier reader statements; the model cannot replace them.
    Returns a chapter-scoped `routed` work, exact `passages` permission,
    a clarification, or no match. Call `librarian_search` with the returned
    `work_id` and `book_version_id`. For `routed`, build `reading_boundary` from
    `max_chapter_inclusive`; for `passages`, pass `reading_boundary=None`.
    Routing returns no source text and grants no write authority. If clarification
    is needed, stop book answering and other tools; after safety review the
    application sends the validated question without requiring a verbatim copy.
    """
    message = reader_message()
    if message is None:
        # Unreachable in production: the application always binds this before
        # Muse runs. Not a ModelRetry — no argument Muse could change would
        # fix a missing application-side turn context.
        raise RuntimeError("librarian_route requires an active reader turn")
    return await route_reader_message(message)


async def serendipity_explore(
    intent: Literal["find_connection", "get_recommendation"] = "find_connection",
) -> ConnectionExplorationResult:
    """Explore a reader's cue for a tentative, evidence-backed connection worth surfacing.

    Use this when the reader shares a feeling, question, or recurring idea and
    an unexpected connection to a confirmed book or a wider public resonance
    might deepen their reflection — not for routine grounding, which
    `librarian_search` already covers. The application supplies the exact current
    reader message as the cue; the model cannot replace it. The book, chapter,
    and source scope are also fixed by the application. Passage-only permission
    does not grant Serendipity book search. Serendipity chooses bounded Librarian
    and optional Exa searches within its authorized sources,
    compares a shortlist, and returns a validated proposal or decline together
    with its request-local evidence. Use `get_recommendation` when the reader
    explicitly asks for an essay, artwork, song, thinker, or other outside
    source; use `find_connection` for an optional reflective resonance. Never
    invent a connection when the decision is a decline — relay the safe next
    step instead.
    """
    cue = reader_message()
    if cue is None:
        raise RuntimeError("serendipity_explore requires an active reader turn")
    return await connection_exploration(ConnectionBrief(cue=cue, intent=intent))
