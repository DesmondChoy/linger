"""Muse and Serendipity judge the same bounded canonical book evidence."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from apps.backend.config import Settings
from apps.backend.contracts import BookScope, EvidenceBundle, LibrarianRequest
from apps.backend.hybrid_librarian import HybridLibrarian
from apps.backend.librarian import Librarian
from src.linger.agents.librarian.agent import build_librarian_agent
from src.linger.agents.librarian.models import EvidenceStrengthDecision
from src.linger.agents.serendipity.models import ConnectionDiscoveryInput, ConnectionScope
from src.linger.agents.serendipity.tools import SerendipityDependencies, search_librarian
from src.linger.contracts.reading import ReadingBoundary, permits_scope
from src.linger.contracts.session import ReaderStatement
from src.linger.contracts.turn import ConfirmedReading
from src.linger.corpus.alice import BOOK_VERSION_ID
from src.linger.orchestration.grounding import _grounding_evidence, build_request
from src.linger.orchestration.turn_context import (
    reset_confirmed_reading,
    reset_reader_message,
    reset_reader_statements,
    reset_turn_evidence,
    set_confirmed_reading,
    set_reader_message,
    set_reader_statements,
    set_turn_evidence,
    turn_evidence,
)
from test_hybrid_librarian import ConstantEmbedding

QUESTION = (
    "Why does Hugh Auld’s opposition to teaching Douglass to read make Douglass "
    "more determined to learn?"
)
VERSION = "pg23-vd3f08ac3"


class LowScoringPassageReranker:
    def rerank(self, query, documents):
        return [-0.61148 if "desire and determination to learn" in text else -6 for text in documents]


def dependencies(librarian, scope, judge):
    return SerendipityDependencies(
        task=ConnectionDiscoveryInput(
            cue=QUESTION,
            intent="find_connection",
            presentation="ask_before_showing",
            scope=ConnectionScope(allowed_sources=("book_corpus",), book_scopes=(scope,)),
        ),
        librarian=librarian,
        strength_judge=judge,
    )


async def search(deps, query=None):
    if query is not None:
        deps.task = deps.task.model_copy(update={"cue": query})
    return await search_librarian(SimpleNamespace(deps=deps))


@pytest.mark.parametrize("strength", ["sufficient", "weak", "none", "failure", "unknown_id"])
def test_low_scoring_recovery_has_the_same_judgement_in_muse_and_serendipity(strength):
    librarian = HybridLibrarian(embedding_model=ConstantEmbedding(), reranker=LowScoringPassageReranker())
    scope = BookScope(work_id="pg23", book_version_id=VERSION, chapter_max=7)
    assert librarian.retrieve(LibrarianRequest(query=QUESTION, book_scopes=[scope])).items == []
    judged = []

    async def judge(query, records):
        assert query == QUESTION
        assert 1 < len(records) <= 5
        supporting = next(record for record in records if "desire and determination to learn" in record.text)
        assert supporting.chapter_number == 6
        judged.append(records)
        if strength == "failure":
            raise RuntimeError("private judge failure")
        return EvidenceStrengthDecision(
            evidence_strength="sufficient" if strength == "unknown_id" else strength,
            strength_reason="Independent answerability decision.",
            relevant_evidence_ids=("invented-id",) if strength == "unknown_id" else (
                () if strength == "none" else (supporting.evidence_id,)
            ),
            limitations=("This passage supports only the local connection.",) if strength == "weak" else (),
        )

    reading = set_confirmed_reading(ConfirmedReading(work_id="pg23", chapter_max=7))
    ledger = set_turn_evidence(())
    try:
        deps = dependencies(librarian, scope, judge)
        result = asyncio.run(search(deps))
        assert len(judged) == 1
        assert not turn_evidence(), "Discovery must not register evidence for Muse before selection."
        settings = Settings(_env_file=None, linger_model="google:gemini-2.5-flash")
        with patch("src.linger.orchestration.grounding.get_settings", return_value=settings):
            request = build_request(QUESTION, "pg23", VERSION, ReadingBoundary(chapter_number=7, chapter_state="completed"))
        grounding = asyncio.run(_grounding_evidence(request, librarian=librarian, strength_judge=judge))
        assert judged[0] == judged[1]
        if strength in {"failure", "unknown_id"}:
            assert result.outcome == "retrieval_unavailable"
            assert result.judgement is None
            assert grounding.kind == "failure"
            assert grounding.error_code == "evidence_judgement_unavailable"
        else:
            assert result.outcome == grounding.outcome
            assert result.judgement.evidence_strength == grounding.evidence_strength == strength
            assert result.judgement.strength_reason == grounding.strength_reason
            assert result.judgement.limitations == grounding.limitations
            assert tuple(item.evidence_id for item in result.evidence) == tuple(item.evidence_id for item in grounding.evidence)
        if strength in {"sufficient", "weak"}:
            assert len(result.evidence) == 1
            assert set(deps.evidence) == set(turn_evidence()) == {result.evidence[0].evidence_id}
        else:
            assert result.evidence == ()
            assert not deps.evidence
            assert not turn_evidence()
        assert len(deps.searches) == 1
        assert deps.searches[0].outcome == result.outcome
    finally:
        reset_turn_evidence(ledger)
        reset_confirmed_reading(reading)


@pytest.mark.parametrize("scope,query", [
    (BookScope(work_id="pg23", book_version_id=VERSION, chapter_max=5), QUESTION),
    (BookScope(work_id="pg2397", book_version_id="pg2397-vb3cc1e13", part_id="letters",
               unit_ids=("pg2397-vb3cc1e13-sec032",)), "Boston school"),
])
def test_recovery_never_expands_reading_or_named_unit_permission(scope, query):
    librarian = HybridLibrarian(embedding_model=ConstantEmbedding(), reranker=LowScoringPassageReranker())
    judged = []

    async def judge(_query, records):
        judged.extend(records)
        assert records
        assert all(permits_scope(scope, record) for record in records)
        if scope.work_id == "pg23":
            assert all("desire and determination to learn" not in record.text for record in records)
        return EvidenceStrengthDecision(
            evidence_strength="weak", strength_reason="Related context only.",
            relevant_evidence_ids=(records[0].evidence_id,), limitations=("Partial support.",),
        )

    deps = dependencies(librarian, scope, judge)
    ledger = set_turn_evidence(())
    try:
        result = asyncio.run(search(deps, query))
        assert judged
        assert result.outcome == "evidence_found"
        assert all(permits_scope(scope, item) for item in result.evidence)
        assert not turn_evidence()
    finally:
        reset_turn_evidence(ledger)


@pytest.mark.parametrize("named_unit", [False, True])
def test_scope_is_checked_before_judging_and_only_selected_items_enter_discovery_ledger(named_unit):
    librarian = Librarian()
    if named_unit:
        scope = BookScope(work_id="pg2397", book_version_id="pg2397-vb3cc1e13", part_id="letters",
                          unit_ids=("pg2397-vb3cc1e13-sec032",))
        query = "Boston school"
    else:
        scope = BookScope(work_id="pg11", book_version_id=BOOK_VERSION_ID, chapter_max=5)
        query = "Alice changing size identity Caterpillar"
    items = librarian.retrieve_for_judgement(LibrarianRequest(
        query=query, book_scopes=[scope], retrieval_score_threshold=0,
    )).items
    assert len(items) >= 2
    allowed, unselected = items[:2]
    outside = [
        allowed.model_copy(update={"evidence_id": "wrong-work", "work_id": "ungranted-work"}),
        allowed.model_copy(update={"evidence_id": "wrong-version", "book_version_id": "ungranted-version"}),
        allowed.model_copy(update={"evidence_id": "wrong-part", "part_id": "frontmatter"}),
        allowed.model_copy(update={"evidence_id": "outside-reading", **(
            {"chapter_id": "pg2397-vb3cc1e13-sec031"} if named_unit else {"chapter": 6}
        )}),
    ]
    judged = []

    async def judge(_query, records):
        judged.extend(records)
        assert {item.evidence_id for item in records} == {allowed.evidence_id, unselected.evidence_id}
        return EvidenceStrengthDecision(
            evidence_strength="sufficient", strength_reason="Only one passage supports this cue.",
            relevant_evidence_ids=(allowed.evidence_id,),
        )

    deps = dependencies(librarian, scope, judge)
    bundle = EvidenceBundle(items=outside + [allowed, unselected], retrieval_note="Adversarial boundary fixture.")
    ledger = set_turn_evidence(())
    try:
        with patch.object(librarian, "retrieve_for_judgement", return_value=bundle):
            result = asyncio.run(search(deps))
        assert len(judged) == 2
        assert result.evidence == (allowed,)
        assert deps.evidence == {allowed.evidence_id: allowed}
        assert not turn_evidence()
    finally:
        reset_turn_evidence(ledger)


def test_empty_scoped_retrieval_does_not_call_judge_or_create_evidence():
    librarian = Librarian()
    scope = BookScope(work_id="pg11", book_version_id=BOOK_VERSION_ID, chapter_max=5)

    async def judge(_query, _records):
        raise AssertionError("An empty scoped search must not invoke the model.")

    deps = dependencies(librarian, scope, judge)
    with patch.object(librarian, "retrieve_for_judgement", return_value=EvidenceBundle(items=[], retrieval_note="No match.")):
        result = asyncio.run(search(deps))
    assert result.outcome == "no_evidence"
    assert result.judgement.evidence_strength == "none"
    assert result.evidence == ()
    assert not deps.evidence


@pytest.mark.parametrize("route", ["muse", "serendipity"])
@pytest.mark.parametrize("custom_judge,long_reader", [(False, False), (True, False), (False, True)])
def test_original_reader_plan_drives_retrieval_and_is_reused_by_assessment(route, custom_judge, long_reader):
    original_reader = QUESTION + " My voice at the meeting felt different from dinner."
    if long_reader:
        original_reader += " Unrelated personal details." * 100
        assert 2000 < len(original_reader) < 8000
    plan = {"parts": [{"context_spans": [], "purpose": "answer", "reader_spans": [QUESTION]}]}
    expanded_query = (
        "Survey Douglass's education throughout chapters 1 through 7, including "
        "every teacher, every reading lesson, and changes in determination."
    )
    librarian = Librarian()
    scope = BookScope(work_id="pg23", book_version_id=VERSION, chapter_max=7)
    bundle = librarian.retrieve_for_judgement(LibrarianRequest(
        query=QUESTION, book_scopes=[scope], retrieval_score_threshold=0,
    ))
    assert bundle.items
    selected_id = bundle.items[0].evidence_id
    model_inputs = []
    injected_calls = []
    retrieval_inputs = []

    def retrieve_planned(request):
        retrieval_inputs.append(request)
        if not custom_judge:
            assert len(model_inputs) == 1
            assert request.query == QUESTION
        return bundle

    async def model(messages, info):
        prompts = [
            part.content for message in messages for part in message.parts
            if isinstance(part, UserPromptPart)
        ]
        assert len(prompts) == 1
        payload = json.loads(prompts[0])
        model_inputs.append(payload)
        if "current_line" in payload:
            assert not retrieval_inputs
        else:
            assert len(retrieval_inputs) == 1
        response = plan if "current_line" in payload else {
            "evidence_strength": "sufficient",
            "strength_reason": "The selected passage supports the requested book question.",
            "relevant_evidence_ids": [selected_id],
            "support": [{
                "evidence_id": selected_id, "part_index": 0,
                "necessary_support": "The passage supplies the requested reason for learning.",
            }],
        }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, response)])

    async def injected(query, records):
        injected_calls.append((query, records))
        return EvidenceStrengthDecision(
            evidence_strength="sufficient", strength_reason="Injected judgement.",
            relevant_evidence_ids=(selected_id,),
        )

    judge = injected if custom_judge else None
    reading = set_confirmed_reading(ConfirmedReading(work_id="pg23", chapter_max=7))
    ledger = set_turn_evidence(())
    # Serendipity must use its task cue, even when ambient turn context differs.
    message = set_reader_message(original_reader if route == "muse" else "An unrelated ambient reader message.")
    try:
        with (
            patch.object(librarian, "retrieve_for_judgement", side_effect=retrieve_planned) as retrieve,
            patch("src.linger.agents.librarian.agent.librarian_agent", build_librarian_agent(FunctionModel(model))),
        ):
            if route == "muse":
                settings = Settings(_env_file=None, linger_model="google:gemini-2.5-flash")
                with patch("src.linger.orchestration.grounding.get_settings", return_value=settings):
                    request = build_request(
                        original_reader if long_reader else expanded_query, "pg23", VERSION,
                        ReadingBoundary(chapter_number=7, chapter_state="completed"),
                        max_final_evidence=2,
                    )
                result = asyncio.run(_grounding_evidence(request, librarian=librarian, strength_judge=judge))
            else:
                deps = dependencies(librarian, scope, judge)
                deps.task = deps.task.model_copy(update={"cue": original_reader})
                result = asyncio.run(search_librarian(
                    SimpleNamespace(deps=deps), max_results_per_source=2,
                ))

        assert result.outcome == "evidence_found"
        assert [record.evidence_id for record in result.evidence] == [selected_id]
        assert retrieve.call_count == 1
        expected_query = original_reader if custom_judge else QUESTION
        assert retrieve.call_args.args[0].query == expected_query
        if custom_judge:
            assert not model_inputs
            assert len(injected_calls) == 1
            assert injected_calls[0][0] == expected_query
            assert selected_id in {record.evidence_id for record in injected_calls[0][1]}
        else:
            assert not injected_calls
            assert len(model_inputs) == 2
            assert model_inputs[0] == {"current_line": original_reader, "prior_reader_statements": []}
            assessment = model_inputs[1]
            assert set(assessment) == {"request", "evidence", "max_evidence_records"}
            assert assessment["request"] == plan
            assert expanded_query not in json.dumps(model_inputs)
            assert "My voice at the meeting" not in json.dumps(assessment)
            assert "An unrelated ambient reader message" not in json.dumps(model_inputs)
            assert assessment["max_evidence_records"] == 2
            assert selected_id in {record["evidence_id"] for record in assessment["evidence"]}
    finally:
        reset_reader_message(message)
        reset_turn_evidence(ledger)
        reset_confirmed_reading(reading)


def test_muse_clarification_answer_keeps_prior_reader_question_without_expanded_query():
    original_question = "Could you quote what Alice says when the Caterpillar asks who she is?"
    current_answer = "I've finished Chapter 5."
    expanded_query = (
        "Survey every identity change across chapters 1 through 5, comparing "
        "all transformations, memories, and relationships across those scenes."
    )
    prior = ReaderStatement(statement_id="reader-line-1", text=original_question)
    plan = {"parts": [{"context_spans": [], "purpose": "answer", "reader_spans": [original_question]}]}
    librarian = Librarian()
    scope = BookScope(work_id="pg11", book_version_id=BOOK_VERSION_ID, chapter_max=5)
    bundle = librarian.retrieve_for_judgement(LibrarianRequest(
        query=original_question, book_scopes=[scope], retrieval_score_threshold=0,
    ))
    assert bundle.items
    selected_id = bundle.items[0].evidence_id
    model_inputs = []

    async def model(messages, info):
        prompts = [
            part.content for message in messages for part in message.parts
            if isinstance(part, UserPromptPart)
        ]
        assert len(prompts) == 1
        payload = json.loads(prompts[0])
        model_inputs.append(payload)
        response = plan if "current_line" in payload else {
            "evidence_strength": "sufficient",
            "strength_reason": "The selected passage supports the prior reader question.",
            "relevant_evidence_ids": [selected_id],
            "support": [{
                "evidence_id": selected_id, "part_index": 0,
                "necessary_support": "The passage contains the requested dialogue.",
            }],
        }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, response)])

    reading = set_confirmed_reading(ConfirmedReading(work_id="pg11", chapter_max=5))
    ledger = set_turn_evidence(())
    message = set_reader_message(current_answer)
    statements = set_reader_statements((prior,))
    try:
        settings = Settings(_env_file=None, linger_model="google:gemini-2.5-flash")
        with (
            patch.object(librarian, "retrieve_for_judgement", return_value=bundle) as retrieve,
            patch("src.linger.agents.librarian.agent.librarian_agent", build_librarian_agent(FunctionModel(model))),
            patch("src.linger.orchestration.grounding.get_settings", return_value=settings),
        ):
            request = build_request(
                expanded_query, "pg11", BOOK_VERSION_ID,
                ReadingBoundary(chapter_number=5, chapter_state="completed"),
            )
            result = asyncio.run(_grounding_evidence(request, librarian=librarian))

        assert result.outcome == "evidence_found"
        assert [record.evidence_id for record in result.evidence] == [selected_id]
        assert retrieve.call_args.args[0].query == original_question
        assert len(model_inputs) == 2
        assert model_inputs[0] == {
            "current_line": current_answer, "prior_reader_statements": [prior.model_dump()],
        }
        assert set(model_inputs[1]) == {"request", "evidence", "max_evidence_records"}
        assert model_inputs[1]["request"] == plan
        assert selected_id in {record["evidence_id"] for record in model_inputs[1]["evidence"]}
        assert expanded_query not in json.dumps(model_inputs)
        assert current_answer not in json.dumps(model_inputs[1])
    finally:
        reset_reader_statements(statements)
        reset_reader_message(message)
        reset_turn_evidence(ledger)
        reset_confirmed_reading(reading)
