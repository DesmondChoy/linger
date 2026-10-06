"""Muse's tool adapters onto the grounding and connection pipelines.

A thin adapter and nothing else: all safety logic (authority checks, the
access scope, the spoiler ceiling, fail-closed behaviour) lives in
`grounding.py` and `connection.py`, where Muse cannot reach or influence it.
This module only forwards Muse's arguments into a request the orchestration
module validates.
"""

from __future__ import annotations

from typing import Literal

from pydantic_ai import ModelRetry

from apps.backend.contracts import ConnectionBrief
from src.linger.agents.serendipity.models import ConnectionEvidence, ConnectionExplorationResult
from src.linger.contracts.connection_evidence import WebConnectionEvidence, wrap_untrusted_web_excerpt
from src.linger.contracts.librarian import LibrarianResponse, LibrarianRoutingResponse
from src.linger.orchestration.connection import connection_exploration
from src.linger.orchestration.grounding import build_request, grounding_evidence
from src.linger.orchestration.routing import route_reader_message
from src.linger.orchestration.turn_context import reader_message, tool_exposure


def _spotlight_web_evidence(evidence: tuple[ConnectionEvidence, ...]) -> tuple[ConnectionEvidence, ...]:
    """Wrap web excerpts in untrusted-page delimiters for Muse's view (OWASP LLM01); memory and book evidence pass through unchanged."""
    return tuple(
        item.model_copy(update={"excerpt": wrap_untrusted_web_excerpt(item.excerpt)})
        if isinstance(item, WebConnectionEvidence)
        else item
        for item in evidence
    )


async def librarian_search(
    work_id: str,
    book_version_id: str,
    max_final_evidence: int = 5,
) -> LibrarianResponse:
    """Retrieve permitted book evidence for the reader's current request.

    Use this when the answer needs the book's actual text rather than general
    knowledge. A direct search finds the book's own content, not a judged link,
    and an empty search is not a declined connection. `work_id` and
    `book_version_id` must match the application-validated request scope, whose
    exact inclusive chapter ceiling or named units you must not reinterpret.
    After a `passages` route only the granted exact passages are eligible,
    without neighboring text or implied chapter completion. Without permission
    the application returns a clarification instead of searching. The response
    is a clarification request, a retrieval result (with or without evidence),
    or a retrieval failure: handle all three without assuming evidence exists.
    """
    message = reader_message()
    if message is None:
        raise RuntimeError("librarian_search requires an active reader turn")
    request = build_request(message, work_id, book_version_id, max_final_evidence)
    return await grounding_evidence(request)


async def librarian_route() -> LibrarianRoutingResponse:
    """Resolve the book and spoiler boundary for a request answered from a book's text.

    Call this only when the answer the reader asked for must come from a book's
    text (a fact, plot point, quotation, or interpretation of the book), or when
    they ask to resume or locate their reading. The test is what the answer
    needs, not which words appear in the message. A title, character, or scene
    named as the occasion for a personal memory, feeling, or decision is not a
    book request: "Finishing Walden made me wonder whether my own move is
    running away." does not route; "What does Thoreau say about solitude?" does.
    An incidental word inside otherwise personal reflection, a lone ambiguous
    word, or an active session book alone is not a cue. A pronoun or reference
    that only makes sense as a follow-up to the book conversation still routes:
    "Why did she do that?" right after discussing the book routes; "Help me
    repair my bicycle." does not. It takes no arguments and returns a
    chapter-scoped `routed` work, exact `passages` permission, a clarification,
    or no match, never source text. If clarification is needed, stop book
    answering and other tools.
    """
    message = reader_message()
    if message is None:
        # Unreachable in production: the application always binds this before
        # Muse runs. Not a ModelRetry — no argument Muse could change would
        # fix a missing application-side turn context.
        raise RuntimeError("librarian_route requires an active reader turn")
    return await route_reader_message(message)


async def serendipity_explore(
    intent: Literal["find_connection", "gather_sources", "get_recommendation", "recall_memory"],
) -> ConnectionExplorationResult:
    """Recall stored reflections, gather named sources, or explore a connection.

    Call this only when `muse_turn.policy.allow_connection` is true, and pass
    only the intent. Within that grant, call it when answering requires
    comparing named sources or assessing whether they support a proposed
    conclusion, including when the likely answer is that they cannot. Also call
    it, before drafting, when the reader asks whether their own experience,
    feeling, or something they keep noticing is like or connects to what they
    are reading, or whether anything has been written about it: use
    `gather_sources` when they name the book, character, or scene,
    `find_connection` for an unnamed link, or `get_recommendation` for outside
    writing. Serendipity searches the permitted book itself, so a separate book
    search is not needed for that comparison. Direct book retrieval cannot
    inspect a named memory or public text, and passage-only permission does not
    grant Serendipity book search or chapter access.

    Choose the intent by what the reader asks:
    - `recall_memory`: they return to an ongoing personal theme, decision, or
      preference their own stored reflections could inform, or ask what they
      told you before, even when no book or outside source is named. It
      searches only the account's authorized memories and returns a recall of
      the reader's exact earlier records (one matching record is a complete
      recall) or a `no_matching_memory` decline.
    - `gather_sources`: they name the specific sources to consider together
      (books or scenes, a named public text, their own earlier writing) and ask
      how they relate or whether they support a conclusion. It returns one
      bundle of records for the named sources it found and names any it could
      not find; you write the comparison, including any qualification or
      refusal of their conclusion.
    - `find_connection`: they ask whether anything connects without naming the
      sources, or a connection to a confirmed book or wider public resonance
      could deepen the reflection, including when the supported answer may be a
      decline. It also fits an optional connection worth surfacing and a
      reader asking whether anything they have read could illuminate their
      situation or idea, even when they name no book. The supplied
      `connection_book_scopes` authorize which books may be explored. Preserve
      the reader's uncertainty; do not invent a title, character, or passage.
    - `get_recommendation`: they explicitly ask for an essay, artwork, song,
      thinker, or other outside source. Call it for such a request, and never
      claim a search was unavailable when you did not call the tool.

    The grant alone never requires a search. Do not call it for a
    self-contained remark, a question about the world that does not return to
    the reader's own themes (a stored memory sharing its vocabulary is no
    reason to search), a personal wording request without source comparison, or
    merely mentioning a book or thinker. Routine book grounding uses
    `librarian_search`.
    """
    cue = reader_message()
    if cue is None:
        raise RuntimeError("serendipity_explore requires an active reader turn")
    exposure = tool_exposure()
    # Narrowing the offered enum does not stop a call with another value.
    if exposure is not None and exposure.pinned_intent not in (None, intent):
        raise ModelRetry(
            f"This turn permits only intent={exposure.pinned_intent!r}. "
            "Call serendipity_explore again with that intent."
        )
    result = await connection_exploration(ConnectionBrief(cue=cue, intent=intent))
    return result.model_copy(update={"evidence": _spotlight_web_evidence(result.evidence)})
