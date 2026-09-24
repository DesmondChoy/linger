"""Trusted comparison scopes cross chat, review, and release without a primary book."""

import asyncio
import json
from unittest.mock import patch

import pytest
from pydantic_ai.messages import UserPromptPart
from pydantic_ai.models.function import FunctionModel

from apps.backend import chat_turn, sessions
from apps.backend.contracts import BookScope, LibrarianRequest
from apps.backend.librarian import Librarian
from apps.backend.schemas import ChatRequest
from src.linger.agents.muse.agent import muse_chat_agent
from src.linger.agents.provenance.agent import provenance_agent
from src.linger.agents.serendipity.models import (
    CandidateRubric,
    ConnectionCandidate,
    ConnectionProposal,
)
from src.linger.agents.serendipity.tools import SearchTrace
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.contracts.turn import ReleaseScope
from src.linger.corpus.registry import CORPORA
from src.linger.orchestration import connection
from src.linger.orchestration import turn_context
from src.linger.orchestration.book_evidence import evidence_record_from_item
from src.linger.orchestration.grounding import _grounding_evidence, build_request
from src.linger.orchestration.reflection import ReleaseValidationError, _validate_record_scope
from src.linger.services.memory import AccountContext, MemoryPolicyService
from tests.test_chat_connection import _muse_calls_serendipity, _provenance_pass


def comparison_scopes():
    return tuple(
        ReleaseScope(
            work_id=registration.book.work_id,
            book_version_id=registration.book.book_version_id,
            chapter_max=1,
        )
        for registration in CORPORA.values()
    )


def book_record(scope):
    return Librarian().retrieve(LibrarianRequest(
        query="identity learning change", book_scopes=[BookScope(**scope.model_dump())],
        retrieval_score_threshold=0, max_results=1,
    )).items[0]


def proposal_for(task, evidence):
    ids = tuple(item.evidence_id for item in evidence)
    candidates = tuple(
        ConnectionCandidate(
            candidate_id=f"candidate-{index}", tentative_claim=(
                "A tentative connection between changes." if index == 0
                else "A different connection around uncertainty."
            ),
            evidence_ids=ids if index == 0 else ids[:1],
            shared_structure="The sources portray a change.",
            meaningful_difference="Their circumstances differ.",
            interpretation="The resemblance is tentative.", comparison_note="Compare the support.",
            rubric=CandidateRubric(
                cue_fit="direct" if index == 0 else "partial",
                reflective_value="high" if index == 0 else "medium", safety="clear",
            ),
        )
        for index in range(2)
    )
    return ConnectionProposal(
        shortlist=candidates, selected_candidate_id=candidates[0].candidate_id,
        uncertainty="medium", presentation=task.presentation,
        suggested_follow_up="Does that comparison help?", policy_flags=(),
    )


@pytest.mark.parametrize("thematic", [False, True])
def test_three_books_release_from_five_trusted_scopes_without_a_primary_book(tmp_path, thematic):
    scopes = comparison_scopes()
    selected = tuple(book_record(scope) for scope in scopes[:3])
    titles = [CORPORA[scope.work_id].book.title for scope in scopes[:3]]
    request = ChatRequest(
        session_id="connection-comparison-scopes",
        message=(
            "Does anything I've read help me think about feeling different at work and with old friends?"
            if thematic else f"Compare {', '.join(titles)} and assess their tentative connection."
        ),
    )
    muse_inputs, review_inputs, discovered = [], [], []
    captured = []
    muse = _muse_calls_serendipity(captured)

    def draft(messages, info):
        if len(messages) == 1:
            muse_inputs.append(json.loads(next(
                part.content for message in messages for part in message.parts
                if isinstance(part, UserPromptPart)
            )))
        return muse(messages, info)

    def review(messages, info):
        review_inputs.append(json.loads(next(
            part.content for message in messages for part in message.parts
            if isinstance(part, UserPromptPart)
        )))
        return _provenance_pass(messages, info)

    async def explore(task, *, librarian):
        discovered.append(task)
        return connection.ExplorationResult(
            response=proposal_for(task, selected), evidence=selected,
            searches=(SearchTrace(source="book_corpus", operation="search_librarian", outcome="evidence_found"),),
        )

    async def run():
        response = await chat_turn.run_chat_turn(
            request, MemoryPolicyService(tmp_path), AccountContext("comparison-test"),
            connection_book_scopes=scopes, public_source_urls=(),
        )
        assert turn_context.connection_book_scopes() == ()
        assert turn_context.confirmed_reading() is None
        return response

    try:
        with (
            patch.object(chat_turn, "assess_emotional_boundary", return_value=EmotionalBoundaryAssessment(decision="continue_reflection")),
            patch.object(connection, "_agent_explorer", side_effect=explore),
            muse_chat_agent.override(model=FunctionModel(draft)),
            provenance_agent.override(model=FunctionModel(review)),
        ):
            response = asyncio.run(run())
        assert response.inspection.release.release_source == "muse_candidate"
        assert discovered[0].cue == request.message
        assert {scope.work_id for scope in discovered[0].scope.book_scopes} == {scope.work_id for scope in scopes}
        assert muse_inputs[0]["muse_turn"]["reading_context"] is None
        assert muse_inputs[0]["muse_turn"]["connection_book_scopes"] == [scope.model_dump(mode="json") for scope in scopes]
        assert muse_inputs[0]["muse_turn"]["policy"]["allow_connection"] is True
        assert muse_inputs[0]["muse_turn"]["policy"]["allow_retrieval"] is False
        assert review_inputs[-1]["context"]["reading_context"] is None
        assert review_inputs[-1]["context"]["connection_book_scopes"] == [scope.model_dump(mode="json") for scope in scopes]
        assert {item["work_id"] for item in review_inputs[-1]["canonical_book_evidence"]} == {scope.work_id for scope in scopes[:3]}
        assert len(response.inspection.release.released_evidence_ids) == 3
        assert sessions.book_selection(request.session_id) is None
        assert len(sessions.reader_statements(request.session_id)) == 1
    finally:
        sessions.clear(request.session_id)


@pytest.fixture
def fresh_request():
    value = ChatRequest(session_id="connection-scope-validation", message="Compare the named sources.")
    yield value
    sessions.clear(value.session_id)


@pytest.mark.parametrize("message", [
    "Reading Alice's Adventures in Wonderland alongside Animal Farm raises an interesting comparison.",
    "Compare Alice's Adventures in Wonderland and Animal Farm around the language of identity.",
    "I'm in the middle of a career change. Compare Alice's Adventures in Wonderland and Animal Farm.",
    "I've completed a project. Compare Alice's Adventures in Wonderland and Animal Farm.",
])
def test_named_comparison_does_not_require_a_primary_book(fresh_request, message):
    result = chat_turn._apply_connection_book_scopes(
        fresh_request.model_copy(update={"message": message}), comparison_scopes(),
    )
    assert result.work_id is None
    assert result.clarification_question is None
    assert sessions.book_selection(fresh_request.session_id) is None


@pytest.mark.parametrize("message", [
    "I've completed Chapter 2 of Alice's Adventures in Wonderland.",
    "I haven't finished Alice's Adventures in Wonderland yet.",
    "I have read the letter to Miss Sullivan.",
    "I'm reading Alice's Adventures in Wonderland and I'm at Chapter 2.",
    "Chapter 2",
])
def test_comparison_setup_cannot_override_new_progress_declarations(fresh_request, message):
    with pytest.raises(ValueError, match="progress declaration"):
        chat_turn._apply_connection_book_scopes(
            fresh_request.model_copy(update={"message": message}), comparison_scopes(),
        )


@pytest.mark.parametrize("scopes", [(), comparison_scopes()[:1] * 2])
def test_comparison_requires_distinct_book_permissions(fresh_request, scopes):
    with pytest.raises(ValueError, match="nonempty, unique"):
        chat_turn._apply_connection_book_scopes(fresh_request, scopes)


@pytest.mark.parametrize("update", [
    {"book_version_id": "unregistered-revision"},
    {"chapter_max": 999},
    {"chapter_max": None, "unit_ids": ("unregistered-unit",)},
    {"part_id": "unregistered-part"},
])
def test_comparison_rejects_unregistered_or_out_of_boundary_permissions(fresh_request, update):
    scope = comparison_scopes()[0].model_copy(update=update)
    with pytest.raises(ValueError):
        chat_turn._apply_connection_book_scopes(fresh_request, (scope,))


def test_disabled_book_cannot_be_granted_for_a_comparison(fresh_request):
    scopes = comparison_scopes()
    with patch.object(chat_turn.settings, "allowed_book_version_ids", (scopes[0].book_version_id,)):
        with pytest.raises(ValueError, match="registered"):
            chat_turn._apply_connection_book_scopes(fresh_request, scopes)


def test_comparison_rejects_a_reader_source_outside_its_grants(fresh_request):
    message = f"Compare {CORPORA[comparison_scopes()[-1].work_id].book.title} with Alice."
    with pytest.raises(ValueError, match="named sources"):
        chat_turn._apply_connection_book_scopes(
            fresh_request.model_copy(update={"message": message}), comparison_scopes()[:1],
        )


def test_comparison_permissions_require_a_fresh_session(fresh_request):
    sessions.set_book_selection(fresh_request.session_id, sessions.BookSelection(book_id="pg11"))
    with pytest.raises(ValueError, match="fresh session"):
        chat_turn._apply_connection_book_scopes(fresh_request, comparison_scopes())


def test_comparison_and_single_book_setup_cannot_be_combined(fresh_request, tmp_path):
    scopes = comparison_scopes()
    with pytest.raises(ValueError, match="focused initial reading"):
        asyncio.run(chat_turn.run_chat_turn(
            fresh_request, MemoryPolicyService(tmp_path), AccountContext("comparison-test"),
            initial_reading=scopes[0], connection_book_scopes=scopes,
        ))


@pytest.mark.parametrize("update", [
    {"work_id": "ungranted-work"},
    {"book_version_id": "another-revision"},
    {"chapter_number": 2},
    {"part_id": "another-part"},
])
def test_each_released_book_obeys_its_own_revision_and_boundary(update):
    scopes = comparison_scopes()
    record = evidence_record_from_item(book_record(scopes[1]))
    _validate_record_scope(record, None, frozenset(), connection_scopes=scopes)
    with pytest.raises(ReleaseValidationError, match="release scope"):
        _validate_record_scope(record.model_copy(update=update), None, frozenset(), connection_scopes=scopes)


def test_named_unit_permission_does_not_release_an_adjacent_letter(fresh_request):
    scope = ReleaseScope(
        work_id="pg2397", book_version_id=CORPORA["pg2397"].book.book_version_id,
        part_id="letters", unit_ids=(f"{CORPORA['pg2397'].book.book_version_id}-sec032",),
    )
    chat_turn._apply_connection_book_scopes(fresh_request, (scope,))
    record = evidence_record_from_item(book_record(scope))
    _validate_record_scope(record, None, frozenset(), connection_scopes=(scope,))
    with pytest.raises(ReleaseValidationError):
        _validate_record_scope(
            record.model_copy(update={"chapter_id": f"{scope.book_version_id}-sec031"}),
            None, frozenset(), connection_scopes=(scope,),
        )


def test_connection_scope_cannot_override_a_focused_release_boundary():
    scope = comparison_scopes()[0]
    record = evidence_record_from_item(book_record(scope))
    with pytest.raises(ReleaseValidationError):
        _validate_record_scope(
            record, scope, frozenset(), connection_scopes=(scope,),
        )


def test_connection_permission_does_not_grant_direct_librarian_search():
    scope = comparison_scopes()[0]
    token = turn_context.set_connection_book_scopes((scope,))
    reading_token = turn_context.set_confirmed_reading(None)
    try:
        librarian = Librarian()
        with patch.object(librarian, "retrieve_for_judgement") as retrieve:
            response = asyncio.run(_grounding_evidence(
                build_request("Compare the books.", scope.work_id, scope.book_version_id),
                librarian=librarian,
            ))
        assert response.kind == "clarification"
        assert response.reason_code == "reading_boundary_unconfirmed"
        retrieve.assert_not_called()
    finally:
        turn_context.reset_confirmed_reading(reading_token)
        turn_context.reset_connection_book_scopes(token)
