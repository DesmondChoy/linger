"""Live run of the main Muse cases against the first or the current Muse.

Both targets use the configured `LINGER_MODEL` and receive the same case tool
transcript through stubbed tools, so a difference between reports reflects
Muse's instructions, contracts, and orchestration rather than retrieval.

- `first` replays the first Muse (commit `8021b4e`): a plain-text Agent whose
  instructions are read from Git history, prompted the way that commit's chat
  endpoint prompted it.
- `current` runs production turn triage and tool exposure, then the
  `muse.reflection` skill on a `MuseDraftInput` envelope.

Earlier released turns in a case reach both targets as message history. A
case's Serendipity outcome (proposal, recall, gathered, or decline) is what
`serendipity_explore` returns if Muse calls it; the current target also wraps
web excerpts and registers connection evidence as production does.

`--pack` picks the cases: `main` (default, the 19-case pack), `review` (the
additive cases in `cases/review/`), or `all`. A case with `fixed_exposure`
skips turn triage and offers exactly its tools and pinned intent. Report
fields added for the review (retry categories, request token breakdown,
reflection modules, memory nomination, additive gates, error kinds) sit
beside the original fields and never change them.

The cases are synthetic fixtures, so replies are retained for rubric review.
It makes paid provider calls:

    uv run python -m evals.muse.baseline_run --target current --runs 3
    uv run python -m evals.muse.baseline_run --target first --runs 3
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import contextvars
import hashlib
import json
import logging
import subprocess
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Collection, Literal

from pydantic_ai import Agent, Tool, UsageLimits, capture_run_messages
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import (
    ModelMessage, ModelRequest, ModelResponse, RetryPromptPart, TextPart, ToolCallPart,
    ToolReturnPart, UserPromptPart,
)
from pydantic_ai.models import Model

from evals.muse.harness import (
    MuseEvalCase, grade_additive, grade_muse_response, load_muse_eval_cases, load_review_cases,
)

FIRST_MUSE_COMMIT = "8021b4e"
WORK_ID = "alice-adventures-in-wonderland"
BOOK_VERSION_ID = "pg11-v01b38ea4"
# The cases say "completed" without a chapter number; every case's reading
# position is the opening chapter.
CASE_CHAPTER = 1
BOUNDARY_QUESTION = "Have you finished that chapter, or are you still partway through it?"
NO_CONNECTION_STEP = "Continue the reflection without proposing a connection."
# One run at a time: at 4, gpt-6-luna hit provider rate limits and lost 30 of
# 57 runs.
CONCURRENCY = 1
PACKS = ("main", "review", "all")
# Seconds to wait before re-running a case whose run ended in HTTP 429, times
# the attempt number (only with `--retry-429`).
RATE_LIMIT_BACKOFF_SECONDS = 30


def _first_instructions() -> str:
    """Read the first Muse's INSTRUCTIONS literal without importing that commit."""
    source = subprocess.run(
        ["git", "show", f"{FIRST_MUSE_COMMIT}:src/linger/agents/muse/agent.py"],
        capture_output=True, check=True, text=True, encoding="utf-8",
        cwd=Path(__file__).resolve().parents[2],
    ).stdout
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "INSTRUCTIONS" for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise RuntimeError(f"INSTRUCTIONS not found at {FIRST_MUSE_COMMIT}")


def _boundary_known(case: MuseEvalCase) -> bool:
    context = case.input.reader_context
    return context.book_confirmed and context.chapter_state is not None


def _decline_step(case: MuseEvalCase) -> tuple[str, str]:
    tools = case.input.tools
    if tools.serendipity_outcome == "decline":
        return tools.decline_reason, tools.decline_safe_next_step or NO_CONNECTION_STEP
    return "unsupported_cue", NO_CONNECTION_STEP


def _book_id(case: MuseEvalCase, index: int) -> str:
    return f"{case.case_id}-e{index}"


def _memory_id(case: MuseEvalCase, index: int) -> str:
    return f"{case.case_id}-m{index}"


def _history(case: MuseEvalCase) -> list[ModelMessage]:
    """Released turns as production stores them: plain reader and reply text."""
    return [
        message
        for turn in case.input.history
        for message in (
            ModelRequest(parts=[UserPromptPart(content=turn.reader)]),
            ModelResponse(parts=[TextPart(content=turn.muse)]),
        )
    ]


def _tool_calls(result) -> list[str]:
    return [
        part.tool_name
        for message in result.all_messages()
        for part in getattr(message, "parts", ())
        if isinstance(part, ToolCallPart)
    ]


def _messages(result_or_messages) -> Sequence[ModelMessage]:
    """A run result's messages, or messages captured from a run that raised."""
    if isinstance(result_or_messages, Sequence):
        return result_or_messages
    return result_or_messages.all_messages()


def _serendipity_intents(result) -> list[str]:
    """The `intent` argument of every `serendipity_explore` call, in call order."""
    return [
        part.args_as_dict().get("intent")
        for message in result.all_messages()
        for part in getattr(message, "parts", ())
        if isinstance(part, ToolCallPart) and part.tool_name == "serendipity_explore"
    ]


def _retry_prompts(result) -> list[dict]:
    """Why each retry happened: a tool's `ModelRetry`, or a schema validation error.

    `tool_name` is None for a plain-text-instead-of-structured-output retry.
    """
    prompts = []
    for message in _messages(result):
        for part in getattr(message, "parts", ()):
            if isinstance(part, RetryPromptPart):
                content = (
                    part.content if isinstance(part.content, str)
                    else json.dumps(part.content, default=str)
                )
                prompts.append({"tool_name": part.tool_name, "content": _retry_reason(content)})
    return prompts


def _retry_reason(content: str) -> str:
    """Keep a citation retry's listed errors; its fixed repair advice is the same every time."""
    try:
        errors = json.loads(content).get("errors")
    except (ValueError, AttributeError):
        errors = None
    return json.dumps(errors)[:1500] if errors else content[:400]


def _retry_categories(result, tool_names: Collection[str]) -> list[dict]:
    """Which check fired for each retry: a stable category plus the fields it named.

    - `tool:<name>`: that tool raised `ModelRetry` (e.g. a pinned-intent mismatch).
    - `output_validation`: Muse's output check (`validate_muse_output`) listed
      citation errors; `fields` are the last path segments it named.
    - `output_schema`: the typed output failed schema validation.
    - `text_instead_of_output`: plain text where structured output was due.
    """
    categories = []
    for message in _messages(result):
        for part in getattr(message, "parts", ()):
            if not isinstance(part, RetryPromptPart):
                continue
            if part.tool_name in tool_names:
                categories.append({"category": f"tool:{part.tool_name}", "fields": []})
            elif part.tool_name is None:
                categories.append({"category": "text_instead_of_output", "fields": []})
            elif isinstance(part.content, str):
                try:
                    errors = json.loads(part.content).get("errors") or []
                except (ValueError, AttributeError):
                    errors = []
                fields = {
                    str(error.get("path", "")).rsplit(".", 1)[-1].split("[", 1)[0]
                    for error in errors if isinstance(error, dict)
                }
                categories.append(
                    {"category": "output_validation", "fields": sorted(fields - {""})}
                )
            else:
                fields = {
                    next((str(loc) for loc in reversed(error.get("loc", ())) if isinstance(loc, str)), "")
                    for error in part.content
                }
                categories.append({"category": "output_schema", "fields": sorted(fields - {""})})
    return categories


def _request_breakdown(messages: Sequence[ModelMessage]) -> list[dict]:
    """Input tokens of each model request in this run, by what prompted it.

    `initial` carries the instructions, input, and history; every later
    request resends all of that plus what came since: `tool_return` after tool
    results, `retry` after a retry prompt (a tool's `ModelRetry` or the output
    check).
    """
    requests = []
    cause = "initial"
    for message in messages:
        if isinstance(message, ModelRequest):
            if any(isinstance(part, RetryPromptPart) for part in message.parts):
                cause = "retry"
            elif any(isinstance(part, ToolReturnPart) for part in message.parts):
                cause = "tool_return"
            elif any(isinstance(part, UserPromptPart) for part in message.parts):
                cause = "initial"
        elif isinstance(message, ModelResponse) and message.usage.input_tokens:
            requests.append({
                "cause": cause,
                "input_tokens": message.usage.input_tokens,
                "cache_read_tokens": message.usage.cache_read_tokens,
                "output_tokens": message.usage.output_tokens,
            })
    return requests


def _o200k_tokens(text: str) -> int | None:
    try:
        import tiktoken
    except ImportError:
        return None
    return len(tiktoken.get_encoding("o200k_base").encode(text))


# --- provider rate limits and errors ---------------------------------------

# The OpenAI SDK retries a 429 itself (twice, with backoff) before an error
# reaches Muse; count those hidden retries per case run from its debug log.
_SDK_RETRIES: contextvars.ContextVar[Counter | None] = contextvars.ContextVar(
    "muse_eval_sdk_retries", default=None,
)


class _SdkRetryCounter(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        counter = _SDK_RETRIES.get()
        if counter is None or not str(record.msg).startswith("Retrying due to status code"):
            return
        counter[str(record.args[0]) if record.args else "unknown"] += 1


def _install_sdk_retry_counter() -> None:
    logger = logging.getLogger("openai._base_client")
    if any(isinstance(handler, _SdkRetryCounter) for handler in logger.handlers):
        return
    logger.addHandler(_SdkRetryCounter(level=logging.DEBUG))
    if logger.getEffectiveLevel() > logging.DEBUG:
        # Debug records feed only the counter, never the console.
        logger.setLevel(logging.DEBUG)
        logger.propagate = False


def _error_kind(error: BaseException) -> str:
    """Keep exhausted output retries apart from provider and other errors."""
    if isinstance(error, UnexpectedModelBehavior):
        return "output_retries_exhausted"
    if isinstance(error, UsageLimitExceeded):
        return "usage_limit"
    status = getattr(error, "status_code", None)
    if status == 429:
        return "rate_limit"
    return "provider_http" if status is not None else "other"


class _RunFailed(Exception):
    """A case run that raised, carrying what was observed before it did."""

    def __init__(self, error: Exception, partial: dict) -> None:
        super().__init__(type(error).__name__)
        self.error = error
        self.partial = partial


# --- first Muse -------------------------------------------------------------


def _first_prompt(case: MuseEvalCase) -> str:
    """The prompt `8021b4e`'s chat endpoint built for the same reader state."""
    context = case.input.reader_context
    if not context.book_confirmed and context.candidate_book:
        return (
            "A possible reading context was detected, but the reader has not confirmed the book. "
            "Do not use character names, plot details, quotations, chapter information, or facts from any book. "
            "Offer only a general reflection based on the reader's wording, then ask whether they mean "
            f"{context.candidate_book}.\n\nUser message: {case.input.reader_message}"
        )
    return case.input.reader_message


def _first_agent(case: MuseEvalCase, model: Model, instructions: str) -> Agent[None, str]:
    async def librarian_search(
        query: str,
        work_id: str,
        book_version_id: str,
        reading_boundary: dict | None,
        max_final_evidence: int = 5,
    ) -> dict:
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

        Args:
            query: What to search for.
            work_id: The confirmed book's work ID.
            book_version_id: The confirmed book's version ID.
            reading_boundary: `{"chapter_number": int, "chapter_state": "started" | "completed"}`.
            max_final_evidence: Maximum passages to return.
        """
        if not _boundary_known(case):
            return {"kind": "clarification", "question": BOUNDARY_QUESTION}
        evidence = case.input.tools.librarian_evidence
        return {
            "kind": "result",
            "outcome": "evidence_found" if evidence else "no_evidence",
            "evidence": [
                {"evidence_id": _book_id(case, index), "chapter": CASE_CHAPTER, "excerpt": text}
                for index, text in enumerate(evidence, start=1)
            ],
        }

    async def serendipity_explore(cue: str) -> dict:
        """Explore a reader's cue for a tentative, evidence-backed connection worth surfacing.

        Use this when the reader shares a feeling, question, or recurring idea and
        an unexpected connection back to the confirmed book (or a wider resonance)
        might deepen their reflection — not for routine grounding, which
        `librarian_search` already covers. Pass only the reader's cue; the book,
        chapter, and source scope are fixed by the application and cannot be set
        here. The response is either a proposal (a tentative claim with supporting
        evidence and an uncertainty level) or a decline (a reason and a safe next
        step). Never invent a connection when the result is a decline — relay the
        safe next step instead.
        """
        tools = case.input.tools
        if tools.serendipity_outcome == "recall":
            return {"status": "recall", "memories": [
                {"evidence_id": _memory_id(case, index), "excerpt": text}
                for index, text in enumerate(tools.memory_records, start=1)
            ]}
        if tools.serendipity_outcome == "proposal":
            return {
                "status": "proposal",
                "tentative_claim": tools.connection_claim,
                "uncertainty": "medium",
                "suggested_follow_up": tools.connection_follow_up,
                "evidence": [
                    *({"evidence_id": _book_id(case, index), "source": "book", "chapter": CASE_CHAPTER,
                       "excerpt": text}
                      for index, text in enumerate(tools.librarian_evidence, start=1)),
                    *({"evidence_id": source.url, "source": "web", "title": source.title,
                       "excerpt": source.excerpt}
                      for source in tools.web_sources),
                ],
            }
        reason, step = _decline_step(case)
        return {"status": "decline", "reason": reason, "safe_next_step": step}

    return Agent(
        model, instructions=instructions, output_type=str,
        tools=[Tool(librarian_search), Tool(serendipity_explore)],
    )


async def _run_first(case: MuseEvalCase, model: Model, instructions: str) -> dict:
    result = await _first_agent(case, model, instructions).run(
        _first_prompt(case), message_history=_history(case),
    )
    return {"reply": result.output, "tool_calls": _tool_calls(result), "usage": result.usage}


# --- current Muse -----------------------------------------------------------


def _current_input(case: MuseEvalCase):
    from apps.backend.contracts import (
        ContextResolution, MuseDraftInput, MuseTurn, ReadingContext, TurnPolicy,
    )

    context = case.input.reader_context
    if _boundary_known(case):
        resolution = ContextResolution(
            status="confirmed", work_id=WORK_ID, work_title=context.candidate_book,
            book_version_id=BOOK_VERSION_ID, chapter_max=CASE_CHAPTER,
            boundary_source="reader_confirmed", boundary_authorization_basis="explicit_progress",
            explanation="The reader confirmed the book and completed chapter.",
        )
    elif context.candidate_book:
        # Production's wording for a known or detected book without a validated boundary.
        resolution = ContextResolution(
            status="inferred", work_id=WORK_ID, work_title=context.candidate_book,
            book_version_id=BOOK_VERSION_ID,
            explanation=(
                "The active book is known, but this request has no validated spoiler boundary yet."
                if context.book_confirmed else
                "A possible book was detected, but the reader has not confirmed it."
            ),
        )
    else:
        resolution = ContextResolution(
            status="unknown",
            explanation=(
                "No confirmed book or reading boundary. This describes reading "
                "state only; many messages need no book."
            ),
        )
    confirmed = resolution.status == "confirmed"
    # Production grants connection for a confirmed book, web reach, or any
    # active memory; a case with a Serendipity outcome has one of those.
    connection = confirmed or case.input.tools.serendipity_outcome is not None
    reading = ReadingContext(
        work_id=WORK_ID, chapter_max=CASE_CHAPTER, boundary_source="reader_confirmed",
    ) if confirmed else None
    return MuseDraftInput(
        mode="draft",
        muse_turn=MuseTurn(
            turn_id=case.case_id,
            user_message=case.input.reader_message,
            reading_context=reading,
            policy=TurnPolicy(
                spoiler_ceiling=CASE_CHAPTER if confirmed else None,
                allow_retrieval=confirmed, allow_connection=connection,
                **({"allow_memory_capture": True} if case.input.allow_memory_capture else {}),
            ),
        ),
        context_resolution=resolution,
        **({"prior_evidence": _prior_evidence(case)} if case.input.prior_evidence else {}),
    )


def _evidence_records(texts: Sequence[str], prefix: str, location: str, first_line: int):
    from src.linger.contracts.librarian import EvidenceRecord

    return tuple(
        EvidenceRecord(
            evidence_id=f"{prefix}{index}", work_id=WORK_ID,
            book_version_id=BOOK_VERSION_ID, chapter_id=f"{BOOK_VERSION_ID}-ch01",
            chapter_number=CASE_CHAPTER, location=f"{location} {index}",
            source_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            source_lines=(first_line + index - 1, first_line + index - 1), text=text,
        )
        for index, text in enumerate(texts, start=1)
    )


def _current_evidence(case: MuseEvalCase):
    return _evidence_records(
        case.input.tools.librarian_evidence, f"{case.case_id}-e", "Chapter I, passage", 1,
    )


def _prior_evidence(case: MuseEvalCase):
    """Book records an earlier released reply cited; production also seeds turn evidence with them."""
    return _evidence_records(
        case.input.prior_evidence, f"{case.case_id}-p", "Chapter I, earlier passage", 101,
    )


def _current_tools(case: MuseEvalCase) -> list[Tool]:
    """Stubs with the production tools' names, signatures, and descriptions."""
    from pydantic_ai import ModelRetry

    from apps.backend.contracts import EvidenceItem
    from src.linger.agents.muse import tools as production
    from src.linger.agents.serendipity.models import (
        CandidateRubric, ConnectionCandidate, ConnectionDecline, ConnectionExplorationResult,
        ConnectionProposal, MemoryRecall, SourceBundle,
    )
    from src.linger.contracts.connection_evidence import (
        MemoryConnectionEvidence, WebConnectionEvidence,
    )
    from src.linger.contracts.librarian import (
        ClarificationRequest, ExpectedAnswer, NoMatch, PassageScope, RetrievalFailure,
        RetrievalResult, RoutedPassages, RoutedWork, SearchedScope,
    )
    from src.linger.orchestration.inspection_context import register_connection_evidence
    from src.linger.orchestration.turn_context import tool_exposure

    context = case.input.reader_context
    tools = case.input.tools
    routed_this_run: list[bool] = []

    def clarification(question: str, values: tuple[str, ...] = ()) -> ClarificationRequest:
        return ClarificationRequest(
            kind="clarification", request_id=case.case_id, clarification_id=f"{case.case_id}-q",
            reason_code="boundary_unknown" if context.book_confirmed else "book_unconfirmed",
            question=question,
            expected_answer=ExpectedAnswer(type="one_of", values=values) if values
            else ExpectedAnswer(type="free_text"),
        )

    def pending():
        if not context.candidate_book:
            return NoMatch(kind="no_match", request_id=case.case_id)
        if not context.book_confirmed:
            return clarification(f"Do you mean {context.candidate_book}?", ("yes", "no"))
        return clarification(BOUNDARY_QUESTION)

    async def librarian_route():
        if tools.route_outcome == "passages":
            routed_this_run.append(True)
            return RoutedPassages(
                kind="passages", request_id=case.case_id, work_id=WORK_ID,
                book_version_id=BOOK_VERSION_ID,
                evidence_ids=tuple(record.evidence_id for record in _current_evidence(case)),
                title=context.candidate_book or WORK_ID, routing_confidence=1.0,
                boundary_confidence=1.0, selection_basis="session_selection",
                authorization_basis="session_supported",
            )
        if tools.route_outcome == "routed":
            routed_this_run.append(True)
        elif not _boundary_known(case):
            return pending()
        return RoutedWork(
            kind="routed", request_id=case.case_id, work_id=WORK_ID,
            book_version_id=BOOK_VERSION_ID, title=context.candidate_book or WORK_ID,
            routing_confidence=1.0, max_chapter_inclusive=CASE_CHAPTER,
            boundary_confidence=1.0, selection_basis="session_selection",
        )

    async def librarian_search(work_id: str, book_version_id: str, max_final_evidence: int = 5):
        if tools.route_outcome is not None:
            # Permission comes only from this run's route call, as in production.
            if not routed_this_run:
                return pending()
        elif not _boundary_known(case):
            return pending()
        strength = tools.search_outcome
        if strength == "failure":
            return RetrievalFailure(
                kind="failure", request_id=case.case_id,
                error_code="retrieval_unavailable", retryable=True,
            )
        evidence = () if strength == "none" else _current_evidence(case)
        return RetrievalResult(
            kind="result", request_id=case.case_id,
            outcome="evidence_found" if evidence else "no_evidence",
            evidence_strength=strength or ("sufficient" if evidence else "none"),
            strength_reason=tools.strength_reason or "Case-supplied evidence.",
            searched_scope=(
                PassageScope(
                    work_id=WORK_ID, book_version_id=BOOK_VERSION_ID,
                    evidence_ids=tuple(record.evidence_id for record in _current_evidence(case)),
                )
                if tools.route_outcome == "passages" else SearchedScope(
                    work_id=WORK_ID, book_version_id=BOOK_VERSION_ID,
                    max_chapter_inclusive=CASE_CHAPTER,
                )
            ),
            evidence=evidence,
            limitations=tools.search_limitations,
        )

    def memory_evidence():
        return tuple(
            MemoryConnectionEvidence(evidence_id=_memory_id(case, index), excerpt=text)
            for index, text in enumerate(case.input.tools.memory_records, start=1)
        )

    def book_evidence():
        return tuple(
            EvidenceItem(
                evidence_id=record.evidence_id, work_id=WORK_ID,
                book_version_id=BOOK_VERSION_ID, chapter_id=record.chapter_id,
                source_title=context.candidate_book or WORK_ID, location=record.location,
                chapter=CASE_CHAPTER, source_sha256=record.source_sha256,
                source_lines=record.source_lines, excerpt=record.text, relevance=0.9,
            )
            for record in _current_evidence(case)
        )

    def web_evidence():
        return tuple(
            WebConnectionEvidence(evidence_id=source.url, title=source.title, excerpt=source.excerpt)
            for source in case.input.tools.web_sources
        )

    def exploration() -> ConnectionExplorationResult:
        tools = case.input.tools
        if tools.serendipity_outcome == "recall":
            memories = memory_evidence()
            register_connection_evidence(memories)
            return ConnectionExplorationResult(
                decision=MemoryRecall(
                    evidence_ids=tuple(item.evidence_id for item in memories),
                    relevance_note="These saved notes are the reader's own words on the cue.",
                ),
                evidence=memories,
            )
        if tools.serendipity_outcome == "gathered":
            book, web, memories = book_evidence(), web_evidence(), memory_evidence()
            register_connection_evidence((*web, *memories))
            return ConnectionExplorationResult(
                decision=SourceBundle(
                    evidence_ids=tuple(item.evidence_id for item in (*book, *web, *memories)),
                    unfound_sources=tools.unfound_sources,
                    relevance_note="Records for the sources the reader named.",
                ),
                evidence=(*book, *web, *memories),
            )
        if tools.serendipity_outcome == "proposal":
            book, web, memories = book_evidence(), web_evidence(), memory_evidence()
            register_connection_evidence((*web, *memories))
            evidence_ids = tuple(item.evidence_id for item in (*book, *web, *memories))
            proposal = ConnectionProposal(
                shortlist=(
                    ConnectionCandidate(
                        candidate_id="candidate-selected", tentative_claim=tools.connection_claim,
                        evidence_ids=evidence_ids,
                        shared_structure="A sense of not fitting a space and what changes that.",
                        meaningful_difference="The book's situation is literal and chosen; the reader's is felt.",
                        interpretation=tools.connection_claim,
                        rubric=CandidateRubric(cue_fit="direct", reflective_value="high", safety="clear"),
                        comparison_note="Fits the reader's cue more directly than the alternative.",
                    ),
                    ConnectionCandidate(
                        candidate_id="candidate-alternative",
                        tentative_claim="The feeling may reflect being overlooked rather than size.",
                        evidence_ids=evidence_ids[:1],
                        shared_structure="Being unnoticed in a larger setting.",
                        meaningful_difference="Rests on one record and a looser reading.",
                        interpretation="A weaker, more general resonance.",
                        rubric=CandidateRubric(cue_fit="partial", reflective_value="medium", safety="clear"),
                        comparison_note="Less specific to the reader's words.",
                    ),
                ),
                selected_candidate_id="candidate-selected",
                uncertainty="medium", presentation="direct",
                suggested_follow_up=tools.connection_follow_up,
                policy_flags=("contains_web_claim",) if web else (),
            )
            return ConnectionExplorationResult(decision=proposal, evidence=(*book, *web, *memories))
        reason, step = _decline_step(case)
        return ConnectionExplorationResult(
            decision=ConnectionDecline(reason=reason, safe_next_step=step)
        )

    async def serendipity_explore(
        intent: Literal["find_connection", "gather_sources", "get_recommendation", "recall_memory"],
    ):
        exposure = tool_exposure()
        if exposure is not None and exposure.pinned_intent not in (None, intent):
            raise ModelRetry(
                f"This turn permits only intent={exposure.pinned_intent!r}. "
                "Call serendipity_explore again with that intent."
            )
        result = exploration()
        return result.model_copy(
            update={"evidence": production._spotlight_web_evidence(result.evidence)}
        )

    stubs = []
    for stub, real in (
        (librarian_route, production.librarian_route),
        (librarian_search, production.librarian_search),
        (serendipity_explore, production.serendipity_explore),
    ):
        stub.__doc__ = real.__doc__
        stubs.append(Tool(stub, sequential=stub is serendipity_explore))
    return stubs


async def _run_current(case: MuseEvalCase, model: Model) -> dict:
    from src.linger.agents.muse.agent import build_muse_agent
    from src.linger.agents.muse import skills
    from src.linger.orchestration.inspection_context import begin_connection_inspection
    from src.linger.orchestration.reflection import MUSE_REQUEST_LIMIT, MUSE_TOOL_CALL_LIMIT
    from src.linger.orchestration.triage import expose_tools, triage_turn
    from src.linger.orchestration.turn_context import (
        ToolExposure, reset_tool_exposure, set_reader_message, set_tool_exposure,
        set_turn_evidence,
    )

    muse = build_muse_agent(model)
    message = case.input.reader_message
    if case.fixed_exposure is not None:
        # The case fixes the offered tools, so triage cannot confound Muse's behaviour.
        needs = None
        exposure = ToolExposure(
            tools=frozenset(case.fixed_exposure.tools),
            pinned_intent=case.fixed_exposure.pinned_intent,
        )
    else:
        try:
            needs = await triage_turn(message, muse=muse)
        except Exception:
            needs = None
        exposure = expose_tools(needs, previously_called=frozenset(), book_override=False)
    run_options = skills.reflection_run_options(revision=False, tools=exposure.tools)
    modules = list(skills.reflection_modules(revision=False, tools=exposure.tools))
    observed = {
        "triage": needs.model_dump(mode="json") if needs else None,
        "fixed_exposure": case.fixed_exposure is not None,
        "exposed_tools": sorted(exposure.tools),
        "pinned_intent": exposure.pinned_intent,
        "reflection_modules": modules,
        "instructions_tokens": _o200k_tokens(
            "\n\n".join([skills.SHARED_INSTRUCTIONS, run_options["instructions"]])
        ),
    }
    tool_names = ("librarian_route", "librarian_search", "serendipity_explore")
    history = _history(case)
    # Each case runs in its own task, so these context variables stay per-case.
    set_reader_message(message)
    set_turn_evidence((*_current_evidence(case), *_prior_evidence(case)))
    begin_connection_inspection()
    token = set_tool_exposure(exposure)
    try:
        with capture_run_messages() as captured, muse.override(tools=_current_tools(case)):
            result = await muse.run(
                _current_input(case).model_dump_json(),
                message_history=history,
                usage_limits=UsageLimits(
                    request_limit=MUSE_REQUEST_LIMIT, tool_calls_limit=MUSE_TOOL_CALL_LIMIT,
                ),
                **run_options,
            )
    except Exception as error:
        # What the run did before it raised, e.g. which checks exhausted its retries.
        new_messages = list(captured[len(history):])
        raise _RunFailed(error, {
            **observed,
            "tool_calls": _tool_calls_in(new_messages),
            "retry_prompts": _retry_prompts(new_messages),
            "retry_categories": _retry_categories(new_messages, tool_names),
            "requests": _request_breakdown(new_messages),
        }) from error
    finally:
        reset_tool_exposure(token)
    return {
        "reply": result.output.reply,
        "tool_calls": _tool_calls(result),
        "usage": result.usage,
        "triage": observed["triage"],
        "exposed_tools": observed["exposed_tools"],
        "pinned_intent": observed["pinned_intent"],
        "serendipity_intents": _serendipity_intents(result),
        "retry_prompts": _retry_prompts(result),
        # Review additions; the fields above keep their original meaning.
        "fixed_exposure": observed["fixed_exposure"],
        "reflection_modules": modules,
        "retry_categories": _retry_categories(result, tool_names),
        "memory": result.output.memory.model_dump(mode="json"),
        "evidence_uses": [use.model_dump(mode="json") for use in result.output.evidence_uses],
        "instructions_tokens": observed["instructions_tokens"],
        "requests": _request_breakdown(result.new_messages()),
    }


def _tool_calls_in(messages: Sequence[ModelMessage]) -> list[str]:
    return [
        part.tool_name
        for message in messages
        for part in getattr(message, "parts", ())
        if isinstance(part, ToolCallPart)
    ]


# --- measurement ------------------------------------------------------------


async def _attempt(
    case: MuseEvalCase, target: str, model: Model, instructions: str | None,
) -> dict:
    started = perf_counter()
    try:
        outcome = (
            await _run_first(case, model, instructions)
            if target == "first" else await _run_current(case, model)
        )
    except Exception as raised:  # a failed call is a measured outcome, not a crash
        failed = raised if isinstance(raised, _RunFailed) else None
        error = failed.error if failed else raised
        # Provider error bodies can carry account identifiers; keep the type only.
        status = getattr(error, "status_code", "")
        return {
            "error": f"{type(error).__name__}{status}",
            "seconds": perf_counter() - started,
            "error_kind": _error_kind(error),
            **(failed.partial if failed else {}),
        }
    usage = outcome.pop("usage")
    grade = grade_muse_response(case, outcome["reply"])
    extra = grade_additive(
        case, outcome["reply"], tool_calls=outcome["tool_calls"],
        serendipity_intents=outcome.get("serendipity_intents", ()),
        evidence_uses=outcome.get("evidence_uses", ()), memory=outcome.get("memory"),
    )
    return {
        **outcome,
        "hard_pass": grade.hard_pass,
        "failures": list(grade.failures),
        "words": len(outcome["reply"].split()),
        "seconds": round(perf_counter() - started, 2),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        # Additive, stricter columns; `hard_pass` above is unchanged by them.
        "leak_pass": not extra.leak_failures,
        "leak_failures": list(extra.leak_failures),
        "tool_pass": not extra.tool_failures,
        "tool_failures": list(extra.tool_failures),
        "reply_gates_pass": not extra.reply_failures,
        "reply_gate_failures": list(extra.reply_failures),
        "memory_pass": not extra.memory_failures,
        "memory_failures": list(extra.memory_failures),
        "retry_count": len(outcome.get("retry_prompts", ())),
    }


async def _one(
    case: MuseEvalCase, target: str, model: Model, instructions: str | None,
    gate: asyncio.Semaphore, retry_429: int = 0,
) -> dict:
    async with gate:
        sdk_retries: Counter = Counter()
        _SDK_RETRIES.set(sdk_retries)
        rate_limited_attempts = 0
        while True:
            outcome = await _attempt(case, target, model, instructions)
            if outcome.get("error_kind") != "rate_limit" or rate_limited_attempts >= retry_429:
                break
            rate_limited_attempts += 1
            await asyncio.sleep(RATE_LIMIT_BACKOFF_SECONDS * rate_limited_attempts)
    if retry_429:
        # Attempts lost to HTTP 429 and re-run by `--retry-429`; the kept outcome is the last.
        outcome["rate_limited_attempts"] = rate_limited_attempts
    outcome["sdk_retries"] = dict(sdk_retries)
    return outcome


def _select_cases(
    cases: tuple[MuseEvalCase, ...], case_ids: Collection[str] | None,
) -> tuple[MuseEvalCase, ...]:
    """Filter to the requested `--case` IDs, keeping pack order; reject unknown IDs."""
    if case_ids is None:
        return cases
    known = {case.case_id for case in cases}
    unknown = sorted(set(case_ids) - known)
    if unknown:
        raise ValueError(f"unknown case ID(s) {unknown}; valid IDs: {sorted(known)}")
    wanted = set(case_ids)
    return tuple(case for case in cases if case.case_id in wanted)


def load_pack(pack: str) -> tuple[MuseEvalCase, ...]:
    """The main pack, the additive review cases, or both (main first)."""
    if pack not in PACKS:
        raise ValueError(f"unknown pack {pack!r}; choose one of {PACKS}")
    cases = (
        *(load_muse_eval_cases() if pack in {"main", "all"} else ()),
        *(load_review_cases() if pack in {"review", "all"} else ()),
    )
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("case IDs must be unique across packs")
    return cases


def _rate(values: list[bool]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _review_summary(calls: list[dict], answered: list[dict]) -> dict:
    """Aggregates of the review additions; none replaces an original field."""
    retry_categories = Counter(
        entry["category"] for call in calls for entry in call.get("retry_categories", ())
    )
    retry_fields = Counter(
        field
        for call in calls for entry in call.get("retry_categories", ())
        for field in entry["fields"]
    )
    causes: Counter = Counter()
    for call in answered:
        for request in call.get("requests", ()):
            causes[request["cause"]] += request["input_tokens"]
    requests = [len(call["requests"]) for call in answered if "requests" in call]
    sdk_retries: Counter = Counter()
    for call in calls:
        sdk_retries.update(call.get("sdk_retries", {}))
    return {
        "error_kinds": dict(Counter(call["error_kind"] for call in calls if "error_kind" in call)),
        "output_retry_exhausted": sum(
            call.get("error_kind") == "output_retries_exhausted" for call in calls
        ),
        "leak_pass_rate": _rate([call["leak_pass"] for call in answered if "leak_pass" in call]),
        "tool_pass_rate": _rate([call["tool_pass"] for call in answered if "tool_pass" in call]),
        "reply_gates_pass_rate": _rate(
            [call["reply_gates_pass"] for call in answered if "reply_gates_pass" in call]
        ),
        "memory_pass_rate": _rate(
            [call["memory_pass"] for call in answered if "memory_pass" in call]
        ),
        "mean_retries": round(
            sum(len(call.get("retry_prompts", ())) for call in answered) / len(answered), 2
        ) if answered else None,
        # Every retry prompt, including those in runs that later errored.
        "retries": sum(retry_categories.values()),
        "retry_categories": dict(retry_categories),
        "retry_fields": dict(retry_fields),
        "mean_requests": round(sum(requests) / len(requests), 2) if requests else None,
        # Summed input tokens by what prompted each request (answered runs only).
        "input_tokens_by_request_cause": dict(causes),
        "sdk_retries_by_status": dict(sdk_retries),
        "rate_limited_attempts": sum(call.get("rate_limited_attempts", 0) for call in calls),
    }


async def measure(
    target: str, model: Model, runs: int, case_ids: Collection[str] | None = None,
    pack: str = "main", retry_429: int = 0,
) -> dict:
    cases = _select_cases(load_pack(pack), case_ids)
    instructions = _first_instructions() if target == "first" else None
    gate = asyncio.Semaphore(CONCURRENCY)
    _install_sdk_retry_counter()
    per_run = [
        await asyncio.gather(
            *(_one(case, target, model, instructions, gate, retry_429) for case in cases)
        )
        for _ in range(runs)
    ]
    calls = [call for run in per_run for call in run]
    answered = [call for call in calls if "error" not in call]
    if target == "first":
        prompt_identity = {
            "commit": FIRST_MUSE_COMMIT,
            "instructions_sha256": hashlib.sha256(instructions.encode("utf-8")).hexdigest(),
        }
    else:
        from src.linger.agents.muse.prompt import DRAFT_PROMPT_FINGERPRINT
        prompt_identity = DRAFT_PROMPT_FINGERPRINT.model_dump(mode="json")
    return {
        "target": target,
        "model": model.model_name,
        "prompt": prompt_identity,
        "runs": runs,
        "cases": len(cases),
        "errors": sum("error" in call for call in calls),
        # Errored calls are excluded: a provider rate limit is not a Muse failure.
        "hard_pass_rate": round(sum(call["hard_pass"] for call in answered) / len(answered), 3)
        if answered else None,
        "latency_seconds": {"median": round(median(call["seconds"] for call in answered), 2)}
        if answered else None,
        "mean_input_tokens": round(sum(c["input_tokens"] for c in answered) / len(answered))
        if answered else None,
        "mean_output_tokens": round(sum(c["output_tokens"] for c in answered) / len(answered))
        if answered else None,
        "pack": pack,
        "concurrency": CONCURRENCY,
        "retry_429": retry_429,
        "review": _review_summary(calls, answered),
        "per_case": {
            case.case_id: {
                "primary_behavior": case.primary_behavior,
                "hard_pass": f"{sum(o.get('hard_pass', False) for o in outcomes)}/{runs}",
                "semantic_criteria": list(case.expected.semantic_review.criteria),
                "runs": list(outcomes),
                "forbidden_semantic_claims": list(case.expected.semantic_review.forbidden_claims),
                "leak_pass": f"{sum(o.get('leak_pass', False) for o in outcomes)}/{runs}",
                "tool_pass": f"{sum(o.get('tool_pass', False) for o in outcomes)}/{runs}",
                "reply_gates_pass": f"{sum(o.get('reply_gates_pass', False) for o in outcomes)}/{runs}",
                "memory_pass": f"{sum(o.get('memory_pass', False) for o in outcomes)}/{runs}",
                "errors": sum("error" in o for o in outcomes),
            }
            for case, *outcomes in zip(cases, *per_run)
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("first", "current"), required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--case", dest="cases", action="append", metavar="CASE_ID",
        help="Run only this case ID (repeatable). Defaults to every case in --pack.",
    )
    parser.add_argument(
        "--pack", choices=PACKS, default="main",
        help="main: the 19-case pack; review: cases/review/; all: both.",
    )
    parser.add_argument(
        "--retry-429", type=int, default=0, metavar="N",
        help="Re-run a case up to N times after HTTP 429, with linear backoff; reported per run.",
    )
    args = parser.parse_args()

    from src.linger.agents.build import build_model

    report = asyncio.run(measure(
        args.target, build_model(), args.runs, case_ids=args.cases,
        pack=args.pack, retry_429=args.retry_429,
    ))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
