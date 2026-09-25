"""Live run of the five main Muse cases against the first or the current Muse.

Both targets use the configured `LINGER_MODEL` and receive the same case tool
transcript through stubbed tools, so a difference between reports reflects
Muse's instructions, contracts, and orchestration rather than retrieval.

- `first` replays the first Muse (commit `8021b4e`): a plain-text Agent whose
  instructions are read from Git history, prompted the way that commit's chat
  endpoint prompted it.
- `current` runs production turn triage and tool exposure, then the
  `muse.reflection` skill on a `MuseDraftInput` envelope.

The cases are synthetic fixtures, so replies are retained for rubric review.
It makes paid provider calls:

    uv run python -m evals.muse.baseline_run --target current --runs 3
    uv run python -m evals.muse.baseline_run --target first --runs 3
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import hashlib
import json
import subprocess
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Literal

from pydantic_ai import Agent, Tool, UsageLimits
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models import Model

from evals.muse.harness import MuseEvalCase, grade_muse_response, load_muse_eval_cases

FIRST_MUSE_COMMIT = "8021b4e"
WORK_ID = "alice-adventures-in-wonderland"
BOOK_VERSION_ID = "pg11-v01b38ea4"
# The cases say "completed" without a chapter number; every case's reading
# position is the opening chapter.
CASE_CHAPTER = 1
BOUNDARY_QUESTION = "Have you finished that chapter, or are you still partway through it?"
NO_CONNECTION_STEP = "Continue the reflection without proposing a connection."


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
        return "insufficient_evidence", tools.decline_safe_next_step or NO_CONNECTION_STEP
    return "unsupported_cue", NO_CONNECTION_STEP


def _tool_calls(result) -> list[str]:
    return [
        part.tool_name
        for message in result.all_messages()
        for part in getattr(message, "parts", ())
        if isinstance(part, ToolCallPart)
    ]


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
                {"evidence_id": f"{case.case_id}-e{index}", "chapter": CASE_CHAPTER, "excerpt": text}
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
        reason, step = _decline_step(case)
        return {"status": "decline", "reason": reason, "safe_next_step": step}

    return Agent(
        model, instructions=instructions, output_type=str,
        tools=[Tool(librarian_search), Tool(serendipity_explore)],
    )


async def _run_first(case: MuseEvalCase, model: Model, instructions: str) -> dict:
    result = await _first_agent(case, model, instructions).run(_first_prompt(case))
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
                allow_retrieval=confirmed, allow_connection=confirmed,
            ),
        ),
        context_resolution=resolution,
    )


def _current_evidence(case: MuseEvalCase):
    from src.linger.contracts.librarian import EvidenceRecord

    return tuple(
        EvidenceRecord(
            evidence_id=f"{case.case_id}-e{index}", work_id=WORK_ID,
            book_version_id=BOOK_VERSION_ID, chapter_id=f"{BOOK_VERSION_ID}-ch01",
            chapter_number=CASE_CHAPTER, location=f"Chapter I, passage {index}",
            source_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            source_lines=(index, index), text=text,
        )
        for index, text in enumerate(case.input.tools.librarian_evidence, start=1)
    )


def _current_tools(case: MuseEvalCase) -> list[Tool]:
    """Stubs with the production tools' names, signatures, and descriptions."""
    from src.linger.agents.muse import tools as production
    from src.linger.agents.serendipity.models import ConnectionDecline, ConnectionExplorationResult
    from src.linger.contracts.librarian import (
        ClarificationRequest, ExpectedAnswer, NoMatch, RetrievalResult, RoutedWork, SearchedScope,
    )

    context = case.input.reader_context

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
        if not _boundary_known(case):
            return pending()
        return RoutedWork(
            kind="routed", request_id=case.case_id, work_id=WORK_ID,
            book_version_id=BOOK_VERSION_ID, title=context.candidate_book or WORK_ID,
            routing_confidence=1.0, max_chapter_inclusive=CASE_CHAPTER,
            boundary_confidence=1.0, selection_basis="session_selection",
        )

    async def librarian_search(work_id: str, book_version_id: str, max_final_evidence: int = 5):
        if not _boundary_known(case):
            return pending()
        evidence = _current_evidence(case)
        return RetrievalResult(
            kind="result", request_id=case.case_id,
            outcome="evidence_found" if evidence else "no_evidence",
            evidence_strength="sufficient" if evidence else "none",
            strength_reason="Case-supplied evidence.",
            searched_scope=SearchedScope(
                work_id=WORK_ID, book_version_id=BOOK_VERSION_ID,
                max_chapter_inclusive=CASE_CHAPTER,
            ),
            evidence=evidence,
        )

    async def serendipity_explore(
        intent: Literal["find_connection", "get_recommendation", "recall_memory"],
    ):
        reason, step = _decline_step(case)
        return ConnectionExplorationResult(
            decision=ConnectionDecline(reason=reason, safe_next_step=step)
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
    from src.linger.agents.muse.skills import REFLECTION
    from src.linger.orchestration.reflection import MUSE_REQUEST_LIMIT, MUSE_TOOL_CALL_LIMIT
    from src.linger.orchestration.triage import expose_tools, triage_turn
    from src.linger.orchestration.turn_context import (
        reset_tool_exposure, set_reader_message, set_tool_exposure, set_turn_evidence,
    )

    muse = build_muse_agent(model)
    message = case.input.reader_message
    try:
        needs = await triage_turn(message, muse=muse)
    except Exception:
        needs = None
    exposure = expose_tools(needs, previously_called=frozenset(), book_override=False)
    # Each case runs in its own task, so these context variables stay per-case.
    set_reader_message(message)
    set_turn_evidence(_current_evidence(case))
    token = set_tool_exposure(exposure)
    try:
        with muse.override(tools=_current_tools(case)):
            result = await muse.run(
                _current_input(case).model_dump_json(),
                usage_limits=UsageLimits(
                    request_limit=MUSE_REQUEST_LIMIT, tool_calls_limit=MUSE_TOOL_CALL_LIMIT,
                ),
                **REFLECTION.run_options(),
            )
    finally:
        reset_tool_exposure(token)
    return {
        "reply": result.output.reply,
        "tool_calls": _tool_calls(result),
        "usage": result.usage,
        "triage": needs.model_dump(mode="json") if needs else None,
        "exposed_tools": sorted(exposure.tools),
    }


# --- measurement ------------------------------------------------------------


async def _one(case: MuseEvalCase, target: str, model: Model, instructions: str | None) -> dict:
    started = perf_counter()
    try:
        outcome = (
            await _run_first(case, model, instructions)
            if target == "first" else await _run_current(case, model)
        )
    except Exception as error:  # a failed call is a measured outcome, not a crash
        return {"error": f"{type(error).__name__}: {error}"[:300], "seconds": perf_counter() - started}
    usage = outcome.pop("usage")
    grade = grade_muse_response(case, outcome["reply"])
    return {
        **outcome,
        "hard_pass": grade.hard_pass,
        "failures": list(grade.failures),
        "words": len(outcome["reply"].split()),
        "seconds": round(perf_counter() - started, 2),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
    }


async def measure(target: str, model: Model, runs: int) -> dict:
    cases = load_muse_eval_cases()
    instructions = _first_instructions() if target == "first" else None
    per_run = [
        await asyncio.gather(*(_one(case, target, model, instructions) for case in cases))
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
        "hard_pass_rate": round(sum(call["hard_pass"] for call in answered) / len(calls), 3),
        "latency_seconds": {"median": round(median(call["seconds"] for call in answered), 2)}
        if answered else None,
        "mean_input_tokens": round(sum(c["input_tokens"] for c in answered) / len(answered))
        if answered else None,
        "mean_output_tokens": round(sum(c["output_tokens"] for c in answered) / len(answered))
        if answered else None,
        "per_case": {
            case.case_id: {
                "primary_behavior": case.primary_behavior,
                "hard_pass": f"{sum(o.get('hard_pass', False) for o in outcomes)}/{runs}",
                "semantic_criteria": list(case.expected.semantic_review.criteria),
                "runs": list(outcomes),
            }
            for case, *outcomes in zip(cases, *per_run)
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("first", "current"), required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    from src.linger.agents.build import build_model

    report = asyncio.run(measure(args.target, build_model(), args.runs))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
