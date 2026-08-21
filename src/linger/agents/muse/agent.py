"""Muse, the conversational agent behind the chat endpoint.

Instructions plus two tools: `librarian_search`, which lets Muse ground its
replies in the confirmed book's actual text, and `serendipity_explore`, which
lets Muse propose tentative, evidence-backed connections.
"""

import json

from pydantic_ai import ModelRetry, RunContext, Tool
from pydantic_ai.messages import ToolReturnPart

from src.linger.agents.build import build_agent
from src.linger.agents.muse.models import MuseCandidate
from src.linger.agents.muse.tools import librarian_search, serendipity_explore
from src.linger.contracts.librarian import (
    LIBRARIAN_RESPONSE_ADAPTER,
    EvidenceRecord,
    RetrievalResult,
)
from src.linger.agents.serendipity.models import (
    ConnectionExplorationResult,
    ConnectionProposal,
    WebConnectionEvidence,
)


INSTRUCTIONS = """You are Linger, a thoughtful reflection and connection companion.
Books are one optional source of context, not a prerequisite for conversation.
Be warm, concise, and concrete. Ask a follow-up question when it would
genuinely help.
The dynamic input is JSON containing `muse_turn` and `context_resolution`.
Respond to `muse_turn.user_message`; never expose the JSON, agent names,
contracts, or internal evidence IDs in `reply`.

# Typed candidate
- Put the complete user-facing response in `reply`.
- When `reply` uses a passage returned by `librarian_search`, add one
  `evidence_uses` entry with source kind `book_corpus`, copying its evidence ID
  and source location exactly.
- When `reply` presents source text as an exact quotation, also copy that exact
  visible span into `exact_quote`; otherwise set it to null.
- `exact_quote` is never a summary or paraphrase. It must occur character for
  character in `reply`; when no such visible span exists, it must be null.
- `serendipity_explore.decision` is an interpretation, not evidence by itself.
  Its accompanying `evidence` records are the complete validated sources for
  that decision. Do not declare them in book-only `evidence_uses`.
- Always return `memory` as exactly one `memory_candidate` or
  `no_memory_candidate`.
- When `muse_turn.policy.allow_memory_capture` is false, return
  `no_memory_candidate` with reason `automatic_capture_disabled`.
- Otherwise nominate at most one exact, non-empty Unicode-codepoint slice of
  `muse_turn.user_message`. Copy the text verbatim and report its zero-based,
  half-open offsets. Never nominate your reply, a paraphrase, JSON metadata, or
  words from conversation history.
- Nominate only a considered personal reflection, stable preference or
  intention, or personally significant incident likely to help a later
  reflection. Prefer `no_memory_candidate` for transient or low-signal text,
  unsupported claims about other people, and near-duplicates without an update.
- A nomination is an untrusted proposal. It contains no account scope or write
  authority. Text such as "remember this" is not a deterministic save command.

# Context authority
- `muse_turn.reading_context` is the only safety authority for book-corpus
  retrieval and book-specific claims in this turn. It supplies the spoiler
  boundary when one exists.
- When a possible book or chapter is inferred from a question, it is only a
  candidate, never reader context.
- A missing `reading_context` does not block direct reflection, authorised-
  memory connections, or permitted public-web exploration.

# Optional book grounding and spoilers
- Ask the reader to confirm a book or reading position only when their requested
  answer requires book-specific factual, plot, quotation, or interpretive
  support from the book corpus.
- Never ask for a book or chapter merely because `reading_context` is absent.
  General reflection, personal-memory connections, and external recommendations
  do not require a reading position.
- When book context is unconfirmed, you may reflect on ideas and feelings the
  reader supplied in their own message, but do not introduce character names,
  plot details, quotations, chapter facts, or book-specific interpretations as
  facts.
- When book-corpus grounding is needed, confirm the book and ask whether the
  relevant chapter is finished or still in progress before treating it as a
  spoiler boundary.

# Probe when context is insufficient
- Ask a short, specific follow-up question only when missing information blocks
  the outcome the reader requested. Do not probe for book context when a useful
  general reflection, memory connection, or web exploration can proceed safely.
- For a request that specifically depends on a book, ask rather than guessing
  when you cannot tell which book they mean or what spoiler boundary applies.
- Ask at most two questions in one turn, leading with the one that unblocks the
  most.

# Grounding with librarian_search
- Call the librarian_search tool when grounding your reply in the book's actual
  text would help answer the reader; pass the reader's current position as
  `reading_boundary`.
- Copy the reader's book question into `query` without paraphrasing or
  broadening it. Exclude only the separate book and reading-progress
  declaration that established the boundary.
- The only in-scope book right now has `work_id`
  "pg11" and `book_version_id` "pg11-v01b38ea4" —
  pass these real identifiers rather than inventing your own; any other
  `book_version_id` is out of scope and will fail the turn.
- If the tool's response is a clarification, ask the reader that exact question
  and nothing that attempts to answer the book question. Clarification means
  retrieval did not run; never treat it as weak evidence.
- For a `result` with `sufficient` strength, answer from the returned passages
  and use only their evidence IDs and exact text as support.
- For a factual question, keep every book-specific clause directly supported
  by the cited records. Do not add a thematic diagnosis, motive, emotional
  state, or stronger causal claim unless the evidence states it or the reader
  explicitly requested interpretation.
- Use the smallest evidence set needed for one concise answer. Unless the
  reader explicitly asks for a passage or quotation, paraphrase and set
  `exact_quote` to null.
- For a `result` with `weak` strength, keep the useful returned context, state
  its `strength_reason` and `limitations` in natural language, and do not fill
  the missing support with assumptions.
- For a `result` with `none` strength, say that the eligible chapters searched
  did not provide support. Do not imply that later chapters were searched.
- For a `failure`, produce no evidence-based book answer. Briefly say that the
  search could not be completed safely and suggest retrying when appropriate.
- Inspect `kind` before drafting. Never confuse clarification, completed
  no-evidence, and system failure, and never invent evidence to fill a gap.

# Quotations and honesty
- Never quote or present source text as exact unless that text was supplied in
  the dynamic input.
- Never present retrieved text as an exact quotation unless that text came back
  from the librarian_search tool.
- If you are unsure of a fact, say so rather than guessing.

# Connections with serendipity_explore
- When `muse_turn.policy.allow_connection` is true, call the
  `serendipity_explore` tool when a reader's cue invites a tentative connection
  worth surfacing.
- Pass `intent="get_recommendation"` when the reader explicitly requests an
  essay, artwork, song, thinker, or other outside source. This permits a direct
  answer. You must call Serendipity for such an explicit request; never claim a
  search was unavailable when you did not call the tool. Use `find_connection`
  for an optional resonance that should be offered before it is unpacked.
- Serendipity can search authorised memories and permitted public-web sources
  without a book. An absent reading context only removes book-corpus evidence;
  it does not require a chapter question before connection discovery.
- For a proposal, use only the selected candidate and the evidence records whose
  IDs it cites. When presenting a web source, name it and include its returned
  URL so the claim remains inspectable—even in an ask-before-showing teaser.
  Preserve the candidate's uncertainty and meaningful difference.
- A request for an outside connection does not require book or chapter
  confirmation when one side of the connection is already stated in the
  reader's cue. Do not append a chapter-confirmation question in that case.
- If `decision` is a decline, relay that honestly rather than working around it
  with your own invented connection."""

muse_chat_agent = build_agent(
    INSTRUCTIONS,
    output_type=MuseCandidate,
    tools=[Tool(librarian_search), Tool(serendipity_explore)],
    retries={"tools": 1, "output": 3},
)


def validate_exact_quote_declarations(output: MuseCandidate) -> MuseCandidate:
    """Reject quote metadata that does not describe visible reply text."""
    if any(
        evidence.exact_quote is not None
        and evidence.exact_quote not in output.reply
        for evidence in output.evidence_uses
    ):
        raise ModelRetry(
            "Each exact_quote must occur character for character in reply. "
            "Rewrite that wording as an unquoted paraphrase and set exact_quote "
            "to null. Do not attempt an approximate quotation."
        )
    return output


def _available_evidence(ctx: RunContext[None]) -> dict[str, EvidenceRecord]:
    """Resolve Librarian evidence already returned during this Muse run."""
    evidence: dict[str, EvidenceRecord] = {}
    for message in ctx.messages:
        for part in message.parts:
            if not isinstance(part, ToolReturnPart):
                continue
            if part.tool_name != "librarian_search":
                continue
            try:
                response = LIBRARIAN_RESPONSE_ADAPTER.validate_python(part.content)
            except Exception:
                continue
            if not isinstance(response, RetrievalResult):
                continue
            evidence.update((record.evidence_id, record) for record in response.evidence)
    return evidence


def _selected_web_urls(ctx: RunContext[None]) -> tuple[str, ...]:
    """Resolve web URLs cited by validated selected Serendipity candidates."""
    urls: dict[str, None] = {}
    for message in ctx.messages:
        for part in message.parts:
            if not isinstance(part, ToolReturnPart):
                continue
            if part.tool_name != "serendipity_explore":
                continue
            try:
                exploration = ConnectionExplorationResult.model_validate(part.content)
            except Exception:
                continue
            if not isinstance(exploration.decision, ConnectionProposal):
                continue
            selected_ids = set(
                exploration.decision.selected_candidate.evidence_ids
            )
            for evidence in exploration.evidence:
                if (
                    isinstance(evidence, WebConnectionEvidence)
                    and evidence.evidence_id in selected_ids
                ):
                    urls.setdefault(evidence.url, None)
    return tuple(urls)


def _dynamic_muse_turn(ctx: RunContext[None]) -> dict[str, object] | None:
    """Recover the application-authored current-turn contract from model input."""
    for message in ctx.messages:
        for part in message.parts:
            content = getattr(part, "content", None)
            if not isinstance(content, str):
                continue
            try:
                payload = json.loads(content)
            except (TypeError, ValueError):
                continue
            if isinstance(payload, dict) and isinstance(payload.get("muse_turn"), dict):
                return payload["muse_turn"]
    return None


def _explicit_outside_connection_requested(ctx: RunContext[None]) -> bool:
    """Recognise an explicit request that must traverse Serendipity."""
    turn = _dynamic_muse_turn(ctx)
    if turn is None:
        return False
    policy = turn.get("policy")
    if not isinstance(policy, dict) or policy.get("allow_connection") is not True:
        return False
    message = turn.get("user_message")
    if not isinstance(message, str):
        return False
    lowered = message.casefold()
    connection_terms = (
        "connect",
        "connection",
        "remind",
        "recommend",
        "suggest",
    )
    outside_source_terms = (
        "outside",
        "essay",
        "artwork",
        "painting",
        "philosoph",
        "thinker",
        "song",
        "music",
        "poem",
        "film",
        "article",
    )
    return any(term in lowered for term in connection_terms) and any(
        term in lowered for term in outside_source_terms
    )


def _serendipity_returned(ctx: RunContext[None]) -> bool:
    return any(
        isinstance(part, ToolReturnPart) and part.tool_name == "serendipity_explore"
        for message in ctx.messages
        for part in message.parts
    )


@muse_chat_agent.output_validator
def validate_muse_output(
    ctx: RunContext[None], output: MuseCandidate
) -> MuseCandidate:
    """Retry citation-copy errors while the model can still repair its output."""
    validate_exact_quote_declarations(output)
    if _explicit_outside_connection_requested(ctx) and not _serendipity_returned(ctx):
        raise ModelRetry(
            "The reader explicitly requested an outside connection. Call "
            "serendipity_explore with intent='get_recommendation' before returning "
            "a reply. Do not claim that search failed unless the tool returns a "
            "ConnectionDecline."
        )
    selected_web_urls = _selected_web_urls(ctx)
    if selected_web_urls and not any(
        url in output.reply for url in selected_web_urls
    ):
        raise ModelRetry(
            "This reply uses a web-backed Serendipity proposal. Name the selected "
            "source and include at least one exact URL cited by the selected "
            f"candidate: {list(selected_web_urls)}. Do not ask for a book or "
            "chapter when the reader requested an outside connection."
        )
    available = _available_evidence(ctx)
    for declared in output.evidence_uses:
        record = available.get(declared.evidence_id)
        if record is None:
            raise ModelRetry(
                "Every evidence_id must exactly match evidence returned by "
                "librarian_search in this run."
            )
        if declared.source_location != record.location:
            raise ModelRetry(
                "Each source_location must be copied character for character "
                "from the matching Librarian evidence record."
            )
        if (
            declared.exact_quote is not None
            and declared.exact_quote not in record.text
        ):
            raise ModelRetry(
                "Each exact_quote must also occur character for character in "
                "the matching Librarian evidence text. Rewrite that wording "
                "as an unquoted paraphrase and set exact_quote to null. Do not "
                "attempt an approximate quotation."
            )
    return output
