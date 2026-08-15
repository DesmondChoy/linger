"""Muse's tool adapter onto the grounding pipeline.

A thin adapter and nothing else: all safety logic (authority checks, the
access scope, the spoiler ceiling, fail-closed behaviour) lives in
`grounding.py`, where Muse cannot reach or influence it. This module only
forwards Muse's arguments into a request the orchestration module validates.
"""

from __future__ import annotations

from src.linger.contracts.librarian import LibrarianResponse
from src.linger.contracts.reading import ReadingBoundary
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
