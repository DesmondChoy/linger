"""Muse's tool adapters onto the grounding and connection pipelines.

A thin adapter and nothing else: all safety logic (authority checks, the
access scope, the spoiler ceiling, fail-closed behaviour) lives in
`grounding.py` and `connection.py`, where Muse cannot reach or influence it.
This module only forwards Muse's arguments into a request the orchestration
module validates.
"""

from __future__ import annotations

from typing import Literal

from src.linger.agents.serendipity.models import ConnectionExplorationResult
from src.linger.contracts.librarian import LibrarianResponse
from src.linger.contracts.reading import ReadingBoundary
from src.linger.orchestration.connection import build_brief, connection_exploration
from src.linger.orchestration.grounding import build_request, grounding_evidence


async def librarian_search(
    query: str,
    work_id: str,
    book_version_id: str,
    reading_boundary: ReadingBoundary | None,
    max_final_evidence: int = 5,
) -> LibrarianResponse:
    """Search the confirmed book's text for passages relevant to `query`.

    Use this when answering would benefit from grounding in the book's actual
    text rather than general knowledge. `work_id` and `book_version_id` must
    match the book the reader has confirmed they are discussing. Pass the
    reader's current chapter position as `reading_boundary` (its
    `chapter_state` of "started" or "completed" determines how far into the
    book the search is allowed to look — never chapters beyond what the
    reader has confirmed reading). If the reader's reading position hasn't
    been confirmed yet, you may still call this tool with
    `reading_boundary=None`; you will get back a clarification question to
    ask the reader instead of search results. The response may be a
    clarification request, a retrieval result (with or without evidence), or
    a retrieval failure — handle all three without assuming evidence exists.
    """
    request = build_request(query, work_id, book_version_id, reading_boundary, max_final_evidence)
    return await grounding_evidence(request)


async def serendipity_explore(
    cue: str,
    intent: Literal["find_connection", "get_recommendation"] = "find_connection",
) -> ConnectionExplorationResult:
    """Explore a reader's cue for a tentative, evidence-backed connection worth surfacing.

    Use this when the reader shares a feeling, question, or recurring idea and
    an unexpected connection to an authorised memory, a confirmed book, or a
    wider resonance might deepen their reflection — not for routine grounding,
    which `librarian_search` already covers. Pass only the reader's cue; the
    book, chapter, account, and source scope are fixed by the application and
    cannot be set here. No book is required for an authorised-memory
    connection. Serendipity chooses bounded Librarian and optional Exa searches,
    compares a shortlist, and returns a validated proposal or decline together
    with the exact request-local evidence bundle. Use `get_recommendation` when
    the reader explicitly asks for an essay, artwork, song, thinker, or other
    outside source; use `find_connection` for an optional reflective resonance.
    Never invent a connection when the decision is a decline — relay the safe
    next step instead.
    """
    brief = build_brief(cue).model_copy(update={"intent": intent})
    return await connection_exploration(brief)
