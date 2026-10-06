"""Live run of Muse's single reviewed rewrite on fixed revision fixtures.

Production revises a draft once, after Provenance asks for it
(`orchestration.reflection._reflection_reply`). The main pack exercises only
the draft, so this runner exercises the revision on its own, with everything
upstream of it held fixed:

- Each case in `cases/revision/` supplies a released conversation, a flawed
  draft, the tool calls that draft made, and the review block Provenance and
  the application would hand back (findings, `needs_source` sentences,
  accepted claims, retained sources, source-quote interiors).
- The draft is replayed through the production Muse agent by a scripted model,
  so its messages, tool results, and output validation have production shape
  at no cost. A fixture draft that fails production validation is rejected.
- Muse then revises once on `LINGER_MODEL`, with the production revision
  envelope, message history, tool exposure, run options, and output
  validators (`validate_muse_output` reads the revision envelope).
- The revised candidate is graded deterministically against rule-derived
  expectations. Output retries are counted and classified, and exhausted
  retries (`UnexpectedModelBehavior`, a safe decline in production) are
  reported separately from provider errors.

The revision run sends `reflection_run_options(revision=True, ...)`, so the
model sees the modules production would load for the case's offered tools.

    uv run python -m evals.muse.revision_run --runs 6
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any, Collection, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_ai import Tool, UsageLimits, capture_run_messages
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelMessage, ModelRequest, ModelResponse, RetryPromptPart, TextPart, ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel

CASES_DIR = Path(__file__).resolve().parent / "cases" / "revision"
WORK_ID = "revision-eval-novel"
BOOK_VERSION_ID = "revision-eval-novel-v1"
CONCURRENCY = 1

# Wording that tells the reader about the review and repair rather than the
# reading. Every pattern names a mechanic, not an ordinary reading word.
REPAIR_MECHANICS = (
    r"\bsession[ _-]?lines?\b",
    r"\bevidence[ _](?:ids?|uses?|declarations?|records?)\b",
    r"\bdeclar(?:e|ed|es|ing|ation|ations)\b",
    r"\bsupported[ _]claims?\b",
    r"\bexact[ _]quotes?\b",
    r"\blimit[ _]claims?\b",
    r"\bflagged\b",
    r"\b(?:review|reviewer|the) findings?\b",
    r"\breviewer\b",
    r"\bdraft\b",
    r"\b(?:first|earlier|previous|original) (?:version|answer|reply|response)\b",
    r"\bI(?:['’]ve| have)? (?:corrected|fixed|revised|rewritten|rewrote|removed|updated|amended|adjusted)\b",
    r"\bmapp(?:ed|ing|ings)\b",
    r"\bquotation marks?\b",
    r"\bcorrect(?:ion|ing)\b",
)


class StrictModel(BaseModel):
    """Reject unreviewed fixture schema drift."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ReleasedTurn(StrictModel):
    reader: str = Field(min_length=1)
    muse: str = Field(min_length=1)


class Reading(StrictModel):
    """A reader-confirmed book and chapter boundary for the turn."""

    work_title: str = Field(min_length=1)
    chapter_max: int = Field(ge=1)


class BookPassage(StrictModel):
    evidence_id: str = Field(min_length=1)
    chapter: int = Field(ge=1)
    location: str = Field(min_length=1)
    text: str = Field(min_length=1)


class RetainedSourceSpec(StrictModel):
    source_kind: Literal["book_corpus", "memory", "web"]
    evidence_id: str = Field(min_length=1)


class ReviewSpec(StrictModel):
    """What production derives from the first review, stated directly."""

    findings: tuple[dict[str, Any], ...] = Field(min_length=1)
    # Draft sentence indices whose unmapped text the review judged source-dependent.
    needs_source_sentences: tuple[int, ...] = ()
    previously_accepted_claims: tuple[str, ...] = ()
    retained_sources: tuple[RetainedSourceSpec, ...] = ()
    source_quote_interiors: tuple[str, ...] = ()


class DeclarationExpectation(StrictModel):
    """One declaration the revision must contain."""

    source_kind: Literal["book_corpus", "memory", "web", "session_line"]
    evidence_id: str | None = None
    # Case-insensitive regex that at least one supported claim must match.
    claim_pattern: str | None = None
    exact_quote: str | None = None


class RevisionExpectation(StrictModel):
    """Rule-derived outcomes; draft sentence indices follow production's splitter."""

    # Fixture self-check: the sentences production placement flags for these findings.
    flagged_sentences: tuple[int, ...]
    # Flagged sentences whose defect means they must not survive word for word.
    repaired_sentences: tuple[int, ...] = ()
    # Unflagged sentences the rules require deleting (not keeping, not rewording).
    deleted_sentences: tuple[int, ...] = ()
    forbidden_patterns: tuple[str, ...] = ()
    required_patterns: tuple[str, ...] = ()
    required_declarations: tuple[DeclarationExpectation, ...] = ()
    # Words that mark source-dependent content: in a new sentence they must sit
    # inside a mapped span.
    source_terms: tuple[str, ...] = ()


class RevisionCase(StrictModel):
    case_id: str = Field(pattern=r"^muse-revision-[a-z0-9-]+-v\d+$")
    rules: tuple[str, ...] = Field(min_length=1)
    description: str
    history: tuple[ReleasedTurn, ...] = ()
    reader_message: str = Field(min_length=1)
    reading: Reading | None = None
    exposed_tools: tuple[Literal["librarian_route", "librarian_search"], ...] = ()
    draft_tool_calls: tuple[Literal["librarian_route", "librarian_search"], ...] = ()
    book_evidence: tuple[BookPassage, ...] = ()
    draft: dict[str, Any]
    review: ReviewSpec
    expect: RevisionExpectation
    # A rule-following revision, used only offline to prove the case is satisfiable.
    reference_revision: dict[str, Any]

    @model_validator(mode="after")
    def tools_need_a_book(self) -> Self:
        if set(self.draft_tool_calls) - set(self.exposed_tools):
            raise ValueError("the draft can call only exposed tools")
        if self.exposed_tools and self.reading is None:
            raise ValueError("book tools need a confirmed reading")
        return self


def load_revision_cases(directory: Path = CASES_DIR) -> tuple[RevisionCase, ...]:
    cases = tuple(
        RevisionCase.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.json"))
    )
    ids = [case.case_id for case in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("revision case IDs must be unique")
    return cases


# --- production-shaped inputs ------------------------------------------------


def _records(case: RevisionCase):
    from src.linger.contracts.librarian import EvidenceRecord

    return tuple(
        EvidenceRecord(
            evidence_id=passage.evidence_id, work_id=WORK_ID, book_version_id=BOOK_VERSION_ID,
            chapter_id=f"{BOOK_VERSION_ID}-ch{passage.chapter:02d}", chapter_number=passage.chapter,
            location=passage.location,
            source_sha256=hashlib.sha256(passage.text.encode("utf-8")).hexdigest(),
            source_lines=(index, index), text=passage.text,
        )
        for index, passage in enumerate(case.book_evidence, start=1)
    )


def _draft_input(case: RevisionCase):
    from apps.backend.contracts import (
        ContextResolution, MuseDraftInput, MuseTurn, ReadingContext, TurnPolicy,
    )

    reading = case.reading
    if reading is None:
        resolution = ContextResolution(
            status="unknown",
            explanation=(
                "No confirmed book or reading boundary. This describes reading "
                "state only; many messages need no book."
            ),
        )
    else:
        resolution = ContextResolution(
            status="confirmed", work_id=WORK_ID, work_title=reading.work_title,
            book_version_id=BOOK_VERSION_ID, chapter_max=reading.chapter_max,
            boundary_source="reader_confirmed", boundary_authorization_basis="explicit_progress",
            explanation="The reader confirmed the book and completed chapter.",
        )
    return MuseDraftInput(
        mode="draft",
        muse_turn=MuseTurn(
            turn_id=case.case_id,
            user_message=case.reader_message,
            reading_context=ReadingContext(
                work_id=WORK_ID, chapter_max=reading.chapter_max, boundary_source="reader_confirmed",
            ) if reading else None,
            policy=TurnPolicy(
                spoiler_ceiling=reading.chapter_max if reading else None,
                allow_retrieval=reading is not None, allow_connection=reading is not None,
            ),
        ),
        context_resolution=resolution,
    )


def _history(case: RevisionCase) -> list[ModelMessage]:
    """Released turns as production stores them: plain reader and reply text."""
    return [
        message
        for turn in case.history
        for message in (
            ModelRequest(parts=[UserPromptPart(content=turn.reader)]),
            ModelResponse(parts=[TextPart(content=turn.muse)]),
        )
    ]


def released_reader_lines(case: RevisionCase) -> tuple[str, ...]:
    """Production's `released_user_lines`: earlier reader lines plus the current message."""
    return tuple(turn.reader for turn in case.history) + (case.reader_message,)


def _candidate(data: dict[str, Any]):
    from src.linger.agents.muse.models import MuseCandidate

    return MuseCandidate.model_validate(data)


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    from src.linger.agents.muse.claim_repair import _sentence_spans as production

    return production(text)


def draft_sentences(case: RevisionCase):
    """Production placement (`draft_sentences_for_revision`) for the fixture's findings."""
    from src.linger.agents.muse.claim_repair import _finding_intervals, _overlaps
    from src.linger.agents.muse.models import DraftSentence

    draft = _candidate(case.draft)
    flagged: list[tuple[int, int]] = []
    for finding in findings(case):
        intervals = _finding_intervals(finding.location, draft)
        if intervals is None:
            raise ValueError(f"{case.case_id}: a finding cannot be placed; production would send no sentences")
        flagged.extend(intervals)
    return tuple(
        DraftSentence(
            text=draft.reply[start:end], flagged=_overlaps(start, end, flagged),
            needs_source=index in case.review.needs_source_sentences,
        )
        for index, (start, end) in enumerate(_sentence_spans(draft.reply))
    )


def findings(case: RevisionCase):
    from src.linger.agents.provenance.models import RiskFinding

    return tuple(RiskFinding.model_validate(finding) for finding in case.review.findings)


def revision_input(case: RevisionCase):
    from apps.backend.contracts import MuseRevisionInput, MuseRevisionReview
    from src.linger.agents.muse.models import RetainedSource

    draft_input = _draft_input(case)
    return MuseRevisionInput(
        mode="revision",
        muse_turn=draft_input.muse_turn,
        context_resolution=draft_input.context_resolution,
        prior_evidence=draft_input.prior_evidence,
        review=MuseRevisionReview(
            findings=findings(case),
            previously_accepted_claims=case.review.previously_accepted_claims,
            retained_sources=tuple(
                RetainedSource(source_kind=source.source_kind, evidence_id=source.evidence_id)
                for source in case.review.retained_sources
            ),
            draft_sentences=draft_sentences(case),
            source_quote_interiors=case.review.source_quote_interiors,
            released_reader_lines=released_reader_lines(case),
        ),
    )


def _tools(case: RevisionCase) -> list[Tool]:
    """Stubs with the production tools' names, signatures, and descriptions."""
    from src.linger.agents.muse import tools as production
    from src.linger.contracts.librarian import RetrievalResult, RoutedWork, SearchedScope

    reading = case.reading

    async def librarian_route():
        return RoutedWork(
            kind="routed", request_id=case.case_id, work_id=WORK_ID,
            book_version_id=BOOK_VERSION_ID, title=reading.work_title,
            routing_confidence=1.0, max_chapter_inclusive=reading.chapter_max,
            boundary_confidence=1.0, selection_basis="session_selection",
        )

    async def librarian_search(work_id: str, book_version_id: str, max_final_evidence: int = 5):
        evidence = _records(case)
        return RetrievalResult(
            kind="result", request_id=case.case_id,
            outcome="evidence_found" if evidence else "no_evidence",
            evidence_strength="sufficient" if evidence else "none",
            strength_reason="Case-supplied evidence.",
            searched_scope=SearchedScope(
                work_id=WORK_ID, book_version_id=BOOK_VERSION_ID,
                max_chapter_inclusive=reading.chapter_max,
            ),
            evidence=evidence,
        )

    stubs = []
    for stub, real in (
        (librarian_route, production.librarian_route),
        (librarian_search, production.librarian_search),
    ):
        stub.__doc__ = real.__doc__
        stubs.append(Tool(stub))
    return stubs


class FixtureError(RuntimeError):
    """The fixture's draft does not pass production validation, so production could not review it."""


def _scripted_draft(case: RevisionCase) -> FunctionModel:
    """Call the fixture's tools in order, then return the fixture draft once."""
    calls = list(case.draft_tool_calls)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        retry = next((part for part in messages[-1].parts if isinstance(part, RetryPromptPart)), None)
        if retry is not None:
            raise FixtureError(f"{case.case_id}: fixture draft failed validation: {retry.content}")
        if calls:
            tool = calls.pop(0)
            args = {} if tool == "librarian_route" else {
                "work_id": WORK_ID, "book_version_id": BOOK_VERSION_ID,
            }
            return ModelResponse(parts=[ToolCallPart(tool, args)])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, case.draft)])

    return FunctionModel(respond)


def _bind_turn(case: RevisionCase):
    """Set the per-turn context production binds; returns the reset callbacks."""
    from src.linger.orchestration.inspection_context import (
        begin_connection_inspection, reset_connection_inspection,
    )
    from src.linger.orchestration.turn_context import (
        ToolExposure, reset_reader_message, reset_tool_exposure, reset_turn_evidence,
        set_reader_message, set_tool_exposure, set_turn_evidence,
    )

    tokens = (
        (reset_reader_message, set_reader_message(case.reader_message)),
        (reset_turn_evidence, set_turn_evidence(_records(case))),
        (reset_connection_inspection, begin_connection_inspection()),
        (reset_tool_exposure, set_tool_exposure(ToolExposure(tools=frozenset(case.exposed_tools)))),
    )
    return lambda: [reset(token) for reset, token in reversed(tokens)]


async def draft_messages(case: RevisionCase) -> list[ModelMessage]:
    """Replay the fixture draft through production Muse; its new messages, as production keeps them."""
    from src.linger.agents.muse.agent import build_muse_agent
    from src.linger.agents.muse.skills import reflection_run_options
    from src.linger.orchestration.reflection import MUSE_REQUEST_LIMIT, MUSE_TOOL_CALL_LIMIT

    muse = build_muse_agent(_scripted_draft(case))
    with muse.override(tools=_tools(case)):
        result = await muse.run(
            _draft_input(case).model_dump_json(),
            message_history=_history(case),
            usage_limits=UsageLimits(request_limit=MUSE_REQUEST_LIMIT, tool_calls_limit=MUSE_TOOL_CALL_LIMIT),
            **reflection_run_options(revision=False, tools=case.exposed_tools),
        )
    if result.output.model_dump(mode="json") != _candidate(case.draft).model_dump(mode="json"):
        raise FixtureError(f"{case.case_id}: production validation changed the fixture draft")
    return result.new_messages()


# --- grading -----------------------------------------------------------------


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _similarity(first: str, second: str) -> float:
    return SequenceMatcher(None, first.lower().split(), second.lower().split(), autojunk=False).ratio()


def _mapped_mask(candidate) -> bytearray:
    """Reply characters inside any supported, limit, or quoted span."""
    reply = candidate.reply
    covered = bytearray(len(reply))
    for use in candidate.evidence_uses:
        quote = getattr(use, "exact_quote", None)
        for text in (*use.supported_claims, *getattr(use, "limit_claims", ()), *((quote,) if quote else ())):
            start = reply.find(text)
            while start >= 0:
                covered[start:start + len(text)] = b"\1" * len(text)
                start = reply.find(text, start + 1)
    return covered


def _unmapped_text(reply: str, covered: bytearray, start: int, end: int) -> str:
    return "".join(" " if covered[index] else reply[index] for index in range(start, end))


def grade_revision(case: RevisionCase, output) -> dict[str, Any]:
    """Deterministic rule checks on one revised candidate; `failures` names each broken rule."""
    sentences = draft_sentences(case)
    drafted = [_normalized(sentence.text) for sentence in sentences]
    reply = output.reply
    spans = _sentence_spans(reply)
    revised = [_normalized(reply[start:end]) for start, end in spans]
    covered = _mapped_mask(output)
    failures: list[str] = []
    expect = case.expect

    for index in expect.repaired_sentences:
        if drafted[index] in revised:
            failures.append(f"repaired: flagged sentence {index} kept word for word")
    for index in expect.deleted_sentences:
        if drafted[index] in revised or any(_similarity(drafted[index], text) >= 0.5 for text in revised):
            failures.append(f"deleted: unflagged sentence {index} kept or reworded instead of deleted")

    # Unflagged sentences stay word for word or go.
    for text in revised:
        if text in drafted:
            continue
        best = max(range(len(drafted)), key=lambda i: _similarity(drafted[i], text))
        if not sentences[best].flagged and _similarity(drafted[best], text) >= 0.5:
            failures.append(f"unflagged_reworded: sentence {best} reworded as {text!r}")

    declared = {(use.source_kind, use.evidence_id) for use in output.evidence_uses
                if use.source_kind != "session_line"}
    for source in case.review.retained_sources:
        if (source.source_kind, source.evidence_id) not in declared:
            failures.append(f"retained_source_dropped: {source.evidence_id}")

    for claim in case.review.previously_accepted_claims:
        start = reply.find(claim)
        while start >= 0:
            if any(not covered[i] and not reply[i].isspace() for i in range(start, start + len(claim))):
                failures.append(f"accepted_claim_unmapped: {claim!r}")
                break
            start = reply.find(claim, start + 1)

    for sentence in sentences:
        if not sentence.needs_source:
            continue
        for (start, end), text in zip(spans, revised):
            if text.endswith("?"):
                continue
            if text == _normalized(sentence.text) or _similarity(_normalized(sentence.text), text) >= 0.5:
                words = re.findall(r"\w+", _unmapped_text(reply, covered, start, end))
                if len(words) > 3:
                    failures.append(f"needs_source_unmapped: {text!r}")

    lines = released_reader_lines(case)
    for use in output.evidence_uses:
        if use.source_kind == "session_line" and not any(use.quote in line for line in lines):
            failures.append(f"session_line_not_verbatim: {use.quote!r}")

    for wanted in expect.required_declarations:
        if not any(_declaration_matches(use, wanted) for use in output.evidence_uses):
            failures.append(f"missing_declaration: {wanted.model_dump(exclude_none=True)}")

    for pattern in expect.required_patterns:
        if not re.search(pattern, reply, re.IGNORECASE):
            failures.append(f"required_missing: {pattern}")
    for pattern in expect.forbidden_patterns:
        if match := re.search(pattern, reply, re.IGNORECASE):
            failures.append(f"forbidden_present: {match.group(0)!r}")
    for pattern in REPAIR_MECHANICS:
        if match := re.search(pattern, reply, re.IGNORECASE):
            failures.append(f"repair_mechanics: {match.group(0)!r}")

    # A new sentence may carry source content only inside a mapped span.
    terms = [re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE) for term in expect.source_terms]
    for (start, end), text in zip(spans, revised):
        if text in drafted or text.endswith("?"):
            continue
        unmapped = _unmapped_text(reply, covered, start, end)
        for term in terms:
            if match := term.search(unmapped):
                failures.append(f"new_unmapped_source_content: {match.group(0)!r} in {text!r}")
                break

    return {"hard_pass": not failures, "failures": failures}


def _declaration_matches(use, wanted: DeclarationExpectation) -> bool:
    if use.source_kind != wanted.source_kind:
        return False
    if wanted.evidence_id is not None and getattr(use, "evidence_id", None) != wanted.evidence_id:
        return False
    if wanted.exact_quote is not None and getattr(use, "exact_quote", None) != wanted.exact_quote:
        return False
    if wanted.claim_pattern is not None and not any(
        re.search(wanted.claim_pattern, claim, re.IGNORECASE) for claim in use.supported_claims
    ):
        return False
    return True


# Output-validation feedback, by the rule each error enforces.
_RETRY_CATEGORIES = (
    ("rewrites a draft sentence that no finding names", "unflagged_rewrite"),
    ("new sentence is not beside", "misplaced_new_sentence"),
    ("unmapped content source-dependent", "needs_source_unmapped"),
    ("no longer declares it", "retained_source_dropped"),
    ("had accepted source mappings", "accepted_claim_unmapped"),
    ("identified this retained text as a source quotation", "retained_quote_unbound"),
    ("reads as a source quotation", "unbound_quote"),
    ("addresses the reader", "source_application"),
    ("stored note", "memory_attribution"),
    ("supported_claims entry", "claim_span"),
    ("limit_claims entry", "claim_span"),
    ("visible Markdown citation", "web_citation"),
)


def retry_categories(messages: list[ModelMessage]) -> list[list[str]]:
    """Each output retry's error categories, in order; a schema error is `schema`."""
    attempts = []
    for message in messages:
        for part in getattr(message, "parts", ()):
            if not isinstance(part, RetryPromptPart):
                continue
            if not isinstance(part.content, str):
                attempts.append(["schema"])
                continue
            try:
                errors = json.loads(part.content).get("errors") or []
            except (ValueError, AttributeError):
                attempts.append(["other"])
                continue
            categories = []
            for error in errors:
                text, path = str(error.get("error", "")), str(error.get("path", ""))
                category = next((name for marker, name in _RETRY_CATEGORIES if marker in text), None)
                if category is None:
                    category = "exact_quote" if "exact_quote" in path else (
                        "evidence_id" if "evidence_id" in path or "source_location" in path else "other"
                    )
                categories.append(category)
            attempts.append(categories or ["other"])
    return attempts


def _tool_calls(messages: list[ModelMessage]) -> list[str]:
    return [
        part.tool_name for message in messages for part in getattr(message, "parts", ())
        if isinstance(part, ToolCallPart) and part.tool_name != "final_result"
    ]


# --- measurement -------------------------------------------------------------


async def run_case(case: RevisionCase, model: Model) -> dict[str, Any]:
    """Replay the draft, run one live revision, and grade it."""
    from src.linger.agents.muse.agent import build_muse_agent
    from src.linger.agents.muse.skills import reflection_modules, reflection_run_options
    from src.linger.orchestration.reflection import MUSE_REQUEST_LIMIT, MUSE_TOOL_CALL_LIMIT

    reset = _bind_turn(case)
    try:
        history = [*_history(case), *await draft_messages(case)]
        options = reflection_run_options(revision=True, tools=case.exposed_tools)
        muse = build_muse_agent(model)
        started = perf_counter()
        with capture_run_messages() as messages, muse.override(tools=_tools(case)):
            try:
                result = await muse.run(
                    revision_input(case).model_dump_json(),
                    message_history=history,
                    usage_limits=UsageLimits(
                        request_limit=MUSE_REQUEST_LIMIT, tool_calls_limit=MUSE_TOOL_CALL_LIMIT,
                    ),
                    **options,
                )
            except UnexpectedModelBehavior:
                # Exhausted output retries: production releases a safe decline.
                new = messages[len(history):]
                return {
                    "error": "UnexpectedModelBehavior",
                    "retry_exhausted": True,
                    "retries": sum(isinstance(p, RetryPromptPart) for m in new for p in m.parts),
                    "retry_categories": retry_categories(new),
                    "seconds": round(perf_counter() - started, 2),
                }
    finally:
        reset()
    new = result.new_messages()
    grade = grade_revision(case, result.output)
    categories = retry_categories(new)
    return {
        "reply": result.output.reply,
        "evidence_uses": [use.model_dump(mode="json") for use in result.output.evidence_uses],
        **grade,
        "retries": len(categories),
        "retry_categories": categories,
        "tool_calls": _tool_calls(new),
        "modules": list(reflection_modules(revision=True, tools=case.exposed_tools)),
        "instructions_sha256": hashlib.sha256(options["instructions"].encode("utf-8")).hexdigest(),
        "seconds": round(perf_counter() - started, 2),
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
    }


async def _one(case: RevisionCase, model: Model, gate: asyncio.Semaphore) -> dict[str, Any]:
    async with gate:
        try:
            return await run_case(case, model)
        except FixtureError:
            raise
        except Exception as error:  # a failed call is a measured outcome, not a crash
            # Provider error bodies can carry account identifiers; keep the type only.
            status = getattr(error, "status_code", "")
            return {"error": f"{type(error).__name__}{status}"}


def select_cases(
    cases: tuple[RevisionCase, ...], case_ids: Collection[str] | None,
) -> tuple[RevisionCase, ...]:
    if case_ids is None:
        return cases
    known = {case.case_id for case in cases}
    unknown = sorted(set(case_ids) - known)
    if unknown:
        raise ValueError(f"unknown case ID(s) {unknown}; valid IDs: {sorted(known)}")
    return tuple(case for case in cases if case.case_id in set(case_ids))


async def measure(
    model: Model, runs: int, case_ids: Collection[str] | None = None,
    cases: tuple[RevisionCase, ...] | None = None,
) -> dict[str, Any]:
    from src.linger.agents.muse.prompt import REVISION_PROMPT_FINGERPRINT

    selected = select_cases(cases if cases is not None else load_revision_cases(), case_ids)
    gate = asyncio.Semaphore(CONCURRENCY)
    per_run = [
        await asyncio.gather(*(_one(case, model, gate) for case in selected))
        for _ in range(runs)
    ]
    calls = [call for run in per_run for call in run]
    answered = [call for call in calls if "error" not in call]
    return {
        "target": "current",
        "model": model.model_name,
        "prompt": REVISION_PROMPT_FINGERPRINT.model_dump(mode="json"),
        "runs": runs,
        "cases": len(selected),
        "errors": sum("error" in call for call in calls),
        # Exhausted output retries are Muse behaviour, unlike provider errors.
        "retry_exhausted": sum(bool(call.get("retry_exhausted")) for call in calls),
        "hard_pass_rate": round(sum(c["hard_pass"] for c in answered) / len(answered), 3)
        if answered else None,
        "first_attempt_clean_rate": round(sum(c["retries"] == 0 for c in answered) / len(answered), 3)
        if answered else None,
        "mean_retries": round(mean(c["retries"] for c in answered), 2) if answered else None,
        "mean_input_tokens": round(mean(c["input_tokens"] for c in answered)) if answered else None,
        "mean_output_tokens": round(mean(c["output_tokens"] for c in answered)) if answered else None,
        "per_case": {
            case.case_id: {
                "rules": list(case.rules),
                "hard_pass": f"{sum(o.get('hard_pass', False) for o in outcomes)}/{runs}",
                "errors": sum("error" in o for o in outcomes),
                "runs": list(outcomes),
            }
            for case, *outcomes in zip(selected, *per_run)
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--case", dest="cases", action="append", metavar="CASE_ID",
        help="Run only this case ID (repeatable). Defaults to every revision case.",
    )
    args = parser.parse_args()

    from src.linger.agents.build import build_model

    report = asyncio.run(measure(build_model(), args.runs, case_ids=args.cases))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
