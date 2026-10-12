"""Librarian lists every answer the selected records state, without ever failing a search."""

import asyncio
import json
import zlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from apps.backend.config import get_settings
from apps.backend.contracts import BookScope, EvidenceBundle, EvidenceItem
from apps.backend.librarian import Librarian
from src.linger.agents.librarian.agent import build_librarian_agent
from src.linger.agents.librarian.models import (
    BookRequestPart,
    BookRequestPlan,
    EvidenceStrengthDecision,
    LibrarianBookRequestInput,
    LibrarianEventIdentificationInput,
)
from src.linger.agents.serendipity.models import ConnectionDiscoveryInput, ConnectionScope
from src.linger.agents.serendipity.tools import SerendipityDependencies, search_librarian
from src.linger.contracts.librarian import (
    AccessScope,
    LibrarianRequest,
    PassageGrant,
    PassageScope,
    RetrievalOptions,
    RetrievalResult,
    SearchedScope,
)
from src.linger.contracts.turn import ConfirmedReading
from src.linger.orchestration import turn_context
from src.linger.orchestration.book_evidence import evidence_record_from_item
from src.linger.orchestration.boundary import identify_reader_event, judge_spoiler_boundary
from src.linger.orchestration.evidence_strength import assess_book_evidence, plan_book_request
from src.linger.orchestration.grounding import build_request, grounding_evidence
from src.linger.orchestration.progress_context import ProgressEvent, begin_progress, reset_progress

WORK_ID = "pg11"
VERSION = get_settings().allowed_book_version_ids[0]
QUESTION = "Why does the Pigeon insist that Alice is a serpent?"
LINE = f"I've finished chapter 5. {QUESTION}"
REASON = "The selected passages give the Pigeon's reasons."


def item(identity: str, text: str) -> EvidenceItem:
    start = zlib.crc32(identity.encode()) % 100_000 * 10
    return EvidenceItem(
        evidence_id=f"{VERSION}-{identity}", work_id=WORK_ID, book_version_id=VERSION,
        chapter_id=f"{VERSION}-ch05", chapter=5, location=f"Chapter 5, {identity}",
        source_title="Alice's Adventures in Wonderland", source_sha256="a" * 64,
        source_lines=(start, start + 1), excerpt=text, relevance=0.9,
    )


HOOKAH = item("hookah", "The Caterpillar smoked its hookah in silence.")
EGGS = item(
    "eggs",
    "Alice admitted she had tasted eggs.\n“Then little girls are a kind of\nserpent,” said the Pigeon.",
)
NECK = item("neck", "The Pigeon had never seen a girl with such a   neck as that.")
EGGS_RECORD, NECK_RECORD, HOOKAH_RECORD = (evidence_record_from_item(i) for i in (EGGS, NECK, HOOKAH))
PLAN = BookRequestPlan(parts=(BookRequestPart(context_spans=(), purpose="answer", reader_spans=(QUESTION,)),))
ORIGINAL = LibrarianBookRequestInput(current_line=LINE)


def good_answers(labels: dict[str, str], attempt: int = 1) -> list[dict[str, str]]:
    """Quotes that differ from their records only in whitespace, on every attempt."""
    return [
        {"answer": "Alice has a neck no girl has", "evidence_id": labels[NECK.excerpt],
         "source_quote": "never seen a girl\nwith such a neck"},
        {"answer": "Alice admits she has eaten eggs", "evidence_id": labels[EGGS.excerpt],
         "source_quote": "Alice admitted she had tasted eggs."},
        {"answer": "Egg-eating girls are a kind of serpent", "evidence_id": labels[EGGS.excerpt],
         "source_quote": "little girls are a kind of serpent"},
    ]


class LibrarianScript:
    """One scripted Librarian model: plans, assesses, and lists stated answers."""

    def __init__(self, *, strength="sufficient", selected=(EGGS, NECK), answers=good_answers,
                 plan=PLAN, fail_listing=False):
        self.strength, self.selected, self.answers, self.plan = strength, selected, answers, plan
        self.fail_listing = fail_listing
        self.calls: list[tuple[str, dict]] = []
        self.efforts: list[object] = []
        self.retries: list[dict] = []

    def kinds(self) -> list[str]:
        return [kind for kind, _ in self.calls]

    def payloads(self, kind: str) -> list[dict]:
        return [payload for called, payload in self.calls if called == kind]

    def respond(self, messages, info):
        payload = json.loads(next(
            part.content for message in messages for part in message.parts
            if isinstance(part, UserPromptPart)
        ))
        kind = "plan" if "current_line" in payload else "assessment" if "evidence" in payload else "listing"
        self.calls.append((kind, payload))
        self.efforts.append((info.model_settings or {}).get("openai_reasoning_effort"))
        if kind == "plan":
            if self.plan is None:
                raise RuntimeError("planning unavailable")
            output = self.plan.model_dump(mode="json")
        elif kind == "assessment":
            labels = {record["text"]: record["evidence_id"] for record in payload["evidence"]}
            chosen = [labels[selected.excerpt] for selected in self.selected] if self.strength != "none" else []
            output = {
                "evidence_strength": self.strength, "strength_reason": REASON,
                "relevant_evidence_ids": chosen,
                "limitations": ["Only part of the reasoning is present."] if self.strength == "weak" else [],
                "support": [{"evidence_id": label, "part_index": 0, "necessary_support": "States a reason."}
                            for label in chosen],
                # Without a plan the assessment recovers the need from the reader's own words.
                "additional_parts": [] if payload["request"]["parts"] else PLAN.model_dump(mode="json")["parts"],
            }
        else:
            if self.fail_listing:
                raise RuntimeError("provider unavailable")
            self.retries.extend(
                # The quote check returns JSON text; a schema rejection returns its error list.
                json.loads(part.content) if isinstance(part.content, str) else part.content
                for part in messages[-1].parts if isinstance(part, RetryPromptPart)
            )
            labels = {record["text"]: record["evidence_id"] for record in payload["records"]}
            output = {"answers": self.answers(labels, len(self.payloads("listing")))}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    def agent(self):
        return build_librarian_agent(FunctionModel(self.respond))


class StalledListing(LibrarianScript):
    """A Librarian whose listing request never returns."""

    def __init__(self):
        super().__init__()
        self.stalled = asyncio.Event()

    async def respond_or_stall(self, messages, info):
        response = self.respond(messages, info)
        if self.kinds()[-1] == "listing":
            self.stalled.set()
            await asyncio.sleep(60)
        return response

    def agent(self):
        return build_librarian_agent(FunctionModel(self.respond_or_stall))


def list_answers(script: LibrarianScript, records=(EGGS_RECORD, NECK_RECORD), plan=PLAN):
    from src.linger.orchestration.evidence_strength import list_stated_answers

    return asyncio.run(list_stated_answers(plan, records, original_request=ORIGINAL, agent=script.agent()))


# --- The skill and its quote check -------------------------------------------------


def test_listing_returns_each_answer_bound_to_the_real_record_it_quotes():
    script = LibrarianScript()

    answers = list_answers(script)

    assert [(a.answer, a.evidence_id, a.source_quote) for a in answers] == [
        ("Alice has a neck no girl has", NECK.evidence_id, "never seen a girl\nwith such a neck"),
        ("Alice admits she has eaten eggs", EGGS.evidence_id, "Alice admitted she had tasted eggs."),
        ("Egg-eating girls are a kind of serpent", EGGS.evidence_id, "little girls are a kind of serpent"),
    ]
    assert script.kinds() == ["listing"]
    # The model sees the question and the supplied records under short labels, nothing else.
    assert script.payloads("listing")[0] == {
        "book_question": QUESTION,
        "records": [
            {"evidence_id": "E1", "location": EGGS.location, "text": EGGS.excerpt},
            {"evidence_id": "E2", "location": NECK.location, "text": NECK.excerpt},
        ],
    }


@pytest.mark.parametrize("fault,error", [
    ("quote_not_in_record", "source_quote is not a contiguous span of this record's text."),
    ("unknown_evidence_id", "evidence_id is not one of the supplied records."),
    ("quote_from_another_record", "source_quote is not a contiguous span of this record's text."),
    ("blank_quote", "source_quote is shorter than 10 characters."),
    ("quote_too_short", "source_quote is shorter than 10 characters."),
])
def test_an_item_that_does_not_quote_its_named_record_is_returned_for_one_repair(fault, error):
    def answers(labels, attempt):
        good = good_answers(labels)
        if attempt > 1:
            return good
        bad = {
            "quote_not_in_record": {**good[1], "source_quote": "Alice confessed that she ate eggs."},
            "unknown_evidence_id": {**good[1], "evidence_id": "E9"},
            "quote_from_another_record": {**good[1], "evidence_id": labels[NECK.excerpt]},
            "blank_quote": {**good[1], "source_quote": " \n "},
            "quote_too_short": {**good[1], "source_quote": "ted\n   eggs"},
        }[fault]
        return [good[0], bad]

    script = LibrarianScript(answers=answers)

    answers_listed = list_answers(script)

    assert script.kinds() == ["listing", "listing"]
    assert len(answers_listed) == 3
    repair, = script.retries
    assert repair["error"] == "Some items do not quote the record they name."
    assert [(found["index"], found["error"]) for found in repair["errors"]] == [(1, error)]


@pytest.mark.parametrize("field,limit", [("answer", 300), ("source_quote", 600)])
def test_an_overlong_answer_or_quote_is_returned_for_one_repair(field, limit):
    def answers(labels, attempt):
        good = good_answers(labels)
        return good if attempt > 1 else [{**good[0], field: "a" * (limit + 1)}]

    script = LibrarianScript(answers=answers)

    assert len(list_answers(script)) == 3
    assert script.kinds() == ["listing", "listing"]
    rejected, = script.retries
    assert [error["loc"][-1] for error in rejected] == [field]


def test_record_labels_are_stripped_from_answer_text_and_a_label_only_answer_is_dropped():
    def answers(labels, attempt):
        neck, admits, serpent = good_answers(labels)
        eggs, necks = labels[EGGS.excerpt], labels[NECK.excerpt]
        return [
            {**neck, "answer": f"{necks}: Alice has a neck no girl has"},
            {**admits, "answer": f"Alice admits she has eaten eggs ({eggs})."},
            {**admits, "answer": f"Alice has tasted eggs [{eggs}, {necks}] before"},
            # A label no supplied record carries is the book's own wording.
            {**serpent, "answer": "Egg-eating girls are a kind of serpent (see E9)"},
            # Removing these labels would leave a clause that no longer reads.
            {**serpent, "answer": eggs},
            {**serpent, "answer": f"({eggs} and {necks})"},
            {**serpent, "answer": f"{eggs}'s text says girls are serpents"},
            {**neck, "answer": f"Alice's neck (see {necks}) is long"},
        ]

    script = LibrarianScript(answers=answers)

    assert [(a.answer, a.evidence_id) for a in list_answers(script)] == [
        ("Alice has a neck no girl has", NECK.evidence_id),
        ("Alice admits she has eaten eggs.", EGGS.evidence_id),
        ("Alice has tasted eggs before", EGGS.evidence_id),
        ("Egg-eating girls are a kind of serpent (see E9)", EGGS.evidence_id),
    ]
    assert script.kinds() == ["listing"]


def test_repeated_unquoted_items_exhaust_the_single_repair_and_raise():
    script = LibrarianScript(answers=lambda labels, attempt: [
        {"answer": "She wants eggs", "evidence_id": labels[EGGS.excerpt], "source_quote": "You are after my eggs"},
    ])

    with pytest.raises(UnexpectedModelBehavior):
        list_answers(script)

    assert script.kinds() == ["listing", "listing"]


def test_records_that_state_no_answer_yield_an_empty_list():
    script = LibrarianScript(answers=lambda labels, attempt: [])

    assert list_answers(script) == ()
    assert script.kinds() == ["listing"]


def test_a_plan_with_several_parts_asks_about_all_of_them_and_no_plan_asks_the_reader_line():
    second = "What does Alice admit?"
    plan = BookRequestPlan(parts=(
        *PLAN.parts, BookRequestPart(context_spans=("the Pigeon",), purpose="answer", reader_spans=(second,)),
    ))
    several, fallback = LibrarianScript(), LibrarianScript()

    list_answers(several, plan=plan)
    list_answers(fallback, plan=BookRequestPlan(parts=()))

    assert several.payloads("listing")[0]["book_question"] == f"{QUESTION} {second}"
    assert fallback.payloads("listing")[0]["book_question"] == LINE


def test_only_the_listing_asks_for_medium_reasoning_effort_and_it_stops_at_its_request_budget():
    """Every Librarian entry point, driven until its own request budget ends the run."""
    from src.linger.agents.librarian.skills import STATED_ANSWERS
    from src.linger.orchestration.evidence_strength import list_stated_answers

    runs = {
        "boundary_inference": lambda agent: judge_spoiler_boundary(LINE, (), (), (), agent=agent),
        "event_identification": lambda agent: identify_reader_event(
            LibrarianEventIdentificationInput(
                current_line=LINE, prior_reader_statements=(), full_work_candidates=(),
            ), agent=agent,
        ),
        "book_request": lambda agent: plan_book_request(LINE, agent=agent),
        "evidence_assessment": lambda agent: assess_book_evidence(
            PLAN, (EGGS_RECORD,), original_request=ORIGINAL, agent=agent,
        ),
        "stated_answers": lambda agent: list_stated_answers(
            PLAN, (EGGS_RECORD,), original_request=ORIGINAL, agent=agent,
        ),
    }
    efforts: dict[str, list[object]] = {}
    for name, run in runs.items():
        requested = efforts.setdefault(name, [])

        def ghost_tools(messages, info, requested=requested):
            requested.append((info.model_settings or {}).get("openai_reasoning_effort"))
            return ModelResponse(parts=[ToolCallPart(f"ghost_{len(requested)}", {})])

        with pytest.raises(UsageLimitExceeded):
            asyncio.run(run(build_librarian_agent(FunctionModel(ghost_tools))))

    assert efforts.pop("stated_answers") == ["medium"] * (STATED_ANSWERS.output_retries + 1)
    assert all(requested and set(requested) == {None} for requested in efforts.values())


# --- Muse's search path ------------------------------------------------------------


def search(script: LibrarianScript, *, items=(HOOKAH, EGGS, NECK), strength_judge=None, run=asyncio.run):
    librarian = MagicMock()
    librarian.retrieve_for_judgement.return_value = EvidenceBundle(items=list(items), retrieval_note="")
    request = build_request(LINE, WORK_ID, VERSION)
    reading = turn_context.set_confirmed_reading(ConfirmedReading(work_id=WORK_ID, chapter_max=5))
    ledger = turn_context.set_turn_evidence(())
    try:
        with patch("src.linger.agents.librarian.agent.librarian_agent", script.agent()):
            response = run(grounding_evidence(request, librarian=librarian, strength_judge=strength_judge))
        return request, response, dict(turn_context.turn_evidence())
    finally:
        turn_context.reset_turn_evidence(ledger)
        turn_context.reset_confirmed_reading(reading)


def judged_today(request, strength="sufficient") -> RetrievalResult:
    """The search result exactly as it is without any stated answers."""
    return RetrievalResult(
        kind="result", request_id=request.request_id, outcome="evidence_found",
        evidence_strength=strength, strength_reason=REASON,
        searched_scope=SearchedScope(work_id=WORK_ID, book_version_id=VERSION, max_chapter_inclusive=5),
        evidence=(EGGS_RECORD, NECK_RECORD),
        limitations=("Only part of the reasoning is present.",) if strength == "weak" else (),
    )


@pytest.mark.parametrize("strength", ["sufficient", "weak"])
def test_a_judged_search_hands_muse_every_stated_answer_with_real_evidence_ids(strength):
    script = LibrarianScript(strength=strength)

    request, response, ledger = search(script)

    assert script.kinds() == ["plan", "assessment", "listing"]
    assert [(a.answer, a.evidence_id) for a in response.stated_answers] == [
        ("Alice has a neck no girl has", NECK.evidence_id),
        ("Alice admits she has eaten eggs", EGGS.evidence_id),
        ("Egg-eating girls are a kind of serpent", EGGS.evidence_id),
    ]
    assert response.model_copy(update={"stated_answers": ()}) == judged_today(request, strength)
    assert set(ledger) == {EGGS.evidence_id, NECK.evidence_id}
    # Muse reads the tool result as JSON.
    assert response.model_dump(mode="json")["stated_answers"][1] == {
        "answer": "Alice admits she has eaten eggs", "evidence_id": EGGS.evidence_id,
        "source_quote": "Alice admitted she had tasted eggs.",
    }

    listing, = script.payloads("listing")
    assessment, = script.payloads("assessment")
    # Only the selected records are read, and for the question the assessment judged.
    assert [record["text"] for record in assessment["evidence"]] == [HOOKAH.excerpt, EGGS.excerpt, NECK.excerpt]
    assert [record["text"] for record in listing["records"]] == [EGGS.excerpt, NECK.excerpt]
    assert listing["book_question"] == assessment["request"]["parts"][0]["reader_spans"][0] == QUESTION
    assert VERSION not in json.dumps(listing)


def test_a_search_judged_none_never_asks_for_stated_answers():
    script = LibrarianScript(strength="none")

    _, response, ledger = search(script)

    assert script.kinds() == ["plan", "assessment"]
    assert (response.outcome, response.evidence, response.stated_answers) == ("no_evidence", (), ())
    assert ledger == {}


@pytest.mark.parametrize("script,listing_requests", [
    (LibrarianScript(fail_listing=True), 1),
    (LibrarianScript(answers=lambda labels, attempt: [
        {"answer": "She wants eggs", "evidence_id": labels[EGGS.excerpt], "source_quote": "You are after my eggs"},
    ]), 2),
    (LibrarianScript(answers=lambda labels, attempt: [{"answer": "", "evidence_id": "E1", "source_quote": ""}] * 9), 2),
], ids=["model-raises", "quote-check-exhausted", "schema-exhausted"])
def test_a_failed_listing_leaves_the_search_result_exactly_as_judged(script, listing_requests):
    request, response, ledger = search(script)

    assert script.kinds() == ["plan", "assessment", *["listing"] * listing_requests]
    assert response == judged_today(request)
    assert response.stated_answers == ()
    assert set(ledger) == {EGGS.evidence_id, NECK.evidence_id}


def test_a_listing_that_outlasts_its_time_limit_leaves_the_search_result_exactly_as_judged():
    script = StalledListing()

    with patch("src.linger.orchestration.evidence_strength.STATED_ANSWERS_TIMEOUT_SECONDS", 0.05):
        request, response, ledger = search(script)

    assert script.kinds() == ["plan", "assessment", "listing"]
    assert response == judged_today(request)
    assert set(ledger) == {EGGS.evidence_id, NECK.evidence_id}


def test_cancelling_a_search_during_the_listing_cancels_the_search():
    script = StalledListing()

    async def cancel_during_listing(searching):
        task = asyncio.ensure_future(searching)
        await script.stalled.wait()
        task.cancel()
        await task

    with pytest.raises(asyncio.CancelledError):
        search(script, run=lambda searching: asyncio.run(cancel_during_listing(searching)))


def test_a_failed_listing_reports_its_own_progress_stage():
    events: list[ProgressEvent] = []
    token = begin_progress(events.append)
    try:
        search(LibrarianScript(fail_listing=True))
    finally:
        reset_progress(token)

    assert [(e.agent, e.stage, e.status, e.detail) for e in events][-2:] == [
        ("Librarian", "stated_answers", "running", "Librarian stated-answer listing is in progress."),
        ("Librarian", "stated_answers", "failed", "Librarian stated-answer listing could not complete safely."),
    ]
    assert [e.status for e in events if e.stage == "evidence_strength"] == ["running", "complete"]


def test_planning_failure_still_lists_answers_to_the_reader_line():
    script = LibrarianScript(plan=None)

    _, response, _ = search(script)

    assert script.kinds() == ["plan", "assessment", "listing"]
    assert script.payloads("listing")[0]["book_question"] == LINE
    assert len(response.stated_answers) == 3


def test_an_injected_strength_judge_replaces_every_librarian_model_run():
    script = LibrarianScript()

    async def judge(query, records, *, max_evidence_records):
        return EvidenceStrengthDecision(
            evidence_strength="sufficient", strength_reason=REASON,
            relevant_evidence_ids=(EGGS.evidence_id, NECK.evidence_id),
        )

    request, response, _ = search(script, strength_judge=judge)

    assert script.calls == []
    assert response == judged_today(request)


def test_exact_passage_grants_list_stated_answers_for_the_granted_records_only():
    script = LibrarianScript()
    grant = PassageGrant(records=(EGGS_RECORD, NECK_RECORD), supporting_statement_ids=("reader-1",))
    librarian = MagicMock(spec=Librarian)
    librarian.supports_revision.return_value = True
    librarian.fetch_by_id.side_effect = {r.evidence_id: r for r in grant.records}.__getitem__
    request = LibrarianRequest(
        request_id="passage-search", query=LINE, work_id=WORK_ID, book_version_id=VERSION,
        access_scope=AccessScope(allowed_book_version_ids=(VERSION,)), options=RetrievalOptions(),
    )
    reading = turn_context.set_confirmed_reading(None)
    routing = turn_context.set_routing_context()
    ledger = turn_context.set_turn_evidence(())
    turn_context.bind_passage_grant(grant)
    try:
        with patch("src.linger.agents.librarian.agent.librarian_agent", script.agent()):
            response = asyncio.run(grounding_evidence(request, librarian=librarian))
    finally:
        turn_context.reset_turn_evidence(ledger)
        turn_context.reset_routing_context(routing)
        turn_context.reset_confirmed_reading(reading)

    assert script.kinds() == ["plan", "assessment", "listing"]
    assert isinstance(response.searched_scope, PassageScope)
    assert response.evidence == grant.records
    assert {a.evidence_id for a in response.stated_answers} == {EGGS.evidence_id, NECK.evidence_id}
    assert script.payloads("listing")[0]["book_question"] == QUESTION
    librarian.retrieve_for_judgement.assert_not_called()


# --- Serendipity's search path -----------------------------------------------------


def test_serendipity_book_search_plans_and_assesses_without_listing_stated_answers():
    script = LibrarianScript()
    scope = BookScope(work_id=WORK_ID, book_version_id=VERSION, chapter_max=5)
    librarian = MagicMock()
    librarian.retrieve_for_judgement.return_value = EvidenceBundle(items=[HOOKAH, EGGS, NECK], retrieval_note="")
    deps = SerendipityDependencies(
        task=ConnectionDiscoveryInput(
            cue=LINE, intent="find_connection", presentation="ask_before_showing",
            scope=ConnectionScope(allowed_sources=("book_corpus",), book_scopes=(scope,)),
        ),
        librarian=librarian,
    )

    with patch("src.linger.agents.librarian.agent.librarian_agent", script.agent()):
        result = asyncio.run(search_librarian(SimpleNamespace(deps=deps)))

    assert script.kinds() == ["plan", "assessment"]
    assert result.outcome == "evidence_found"
    assert [found.evidence_id for found in result.evidence] == [EGGS.evidence_id, NECK.evidence_id]
    assert "stated_answers" not in result.model_dump()
    assert {call.args[0].purpose for call in librarian.retrieve_for_judgement.call_args_list} == {
        "connection_discovery"
    }
