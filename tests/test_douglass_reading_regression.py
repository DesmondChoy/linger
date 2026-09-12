"""The literacy question must preserve Douglass identity and confirmed progress."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from apps.backend import chat_turn, sessions
from apps.backend.config import Settings
from apps.backend.contracts import BookScope, LibrarianRequest
from apps.backend.librarian import Librarian
from apps.backend.schemas import ChatRequest
from src.linger.contracts.librarian import BoundaryUncertain
from src.linger.contracts.turn import ConfirmedReading
from src.linger.orchestration import routing
from src.linger.orchestration.turn_context import set_confirmed_reading, reset_confirmed_reading
from src.linger.orchestration.turn_context import set_turn_evidence, reset_turn_evidence, turn_evidence
from apps.backend.hybrid_librarian import HybridLibrarian
from src.linger.agents.librarian.models import EvidenceStrengthDecision
from src.linger.contracts.reading import ReadingBoundary
from src.linger.orchestration.grounding import _grounding_evidence, build_request
from test_hybrid_librarian import ConstantEmbedding


QUESTION = (
    "Why does Hugh Auld’s opposition to teaching Douglass to read make Douglass "
    "more determined to learn?"
)
DECLARATION = "I have completed Chapter 7 of Narrative of the Life of Frederick Douglass."
VERSION = "pg23-vd3f08ac3"
SESSION = "douglass-literacy-regression"


@pytest.fixture(autouse=True)
def isolated_context():
    settings = Settings(_env_file=None, linger_model="google:gemini-2.5-flash")
    with patch.object(chat_turn, "settings", settings), patch.object(routing, "get_settings", return_value=settings):
        yield
    sessions.clear(SESSION)


def test_question_about_reading_does_not_become_a_new_book_title():
    first = chat_turn.resolve_reading_context(ChatRequest(session_id=SESSION, message=DECLARATION))
    assert first.chapter_max == 7
    followup = chat_turn.resolve_reading_context(ChatRequest(session_id=SESSION, message=QUESTION))
    assert followup.work_id == "pg23"
    assert followup.clarification_question is None
    assert sessions.book_selection(SESSION).book_id == "pg23"


def test_confirmed_chapter_seven_routes_without_reinferring_permission():
    message = f"{DECLARATION} {QUESTION}"
    resolution = chat_turn.resolve_reading_context(ChatRequest(session_id=SESSION, message=message))
    assert resolution.chapter_max == 7
    token = set_confirmed_reading(ConfirmedReading(work_id="pg23", chapter_max=resolution.chapter_max))
    uncertain = BoundaryUncertain(
        kind="uncertain", work_id="pg23", book_version_id=VERSION,
        reason_code="insufficient_context", clarification_question="What have you completed?",
    )
    try:
        with patch.object(routing, "infer_spoiler_boundary", new=AsyncMock(return_value=uncertain)) as infer:
            route = asyncio.run(routing.route_reader_message(message, librarian=Librarian()))
        assert route.kind == "routed"
        assert route.max_chapter_inclusive == 7
        infer.assert_not_awaited()
        evidence = Librarian().retrieve(LibrarianRequest(query=QUESTION, book_scopes=[BookScope(
            work_id=route.work_id, book_version_id=route.book_version_id,
            chapter_max=route.max_chapter_inclusive, part_id=route.part_id,
        )]))
        assert any(item.chapter == 6 and "determination" in item.excerpt for item in evidence.items)
        assert all(item.part_id == "main" and item.chapter <= 7 for item in evidence.items)
    finally:
        reset_confirmed_reading(token)


class LowScoringPassageReranker:
    """Reproduce the real reranker's false negative without downloading models."""

    def rerank(self, query, documents):
        return [-0.61148 if "desire and determination to learn" in text else -6 for text in documents]


def test_recovery_cannot_open_the_answer_beyond_the_completed_chapters():
    librarian = HybridLibrarian(embedding_model=ConstantEmbedding(), reranker=LowScoringPassageReranker())
    result = librarian.retrieve_for_judgement(LibrarianRequest(query=QUESTION, book_scopes=[
        BookScope(work_id="pg23", book_version_id=VERSION, chapter_max=5),
    ]))
    assert len(result.items) == 1
    assert result.items[0].chapter <= 5
    assert "desire and determination to learn" not in result.items[0].excerpt


@pytest.mark.parametrize("judgement", ["sufficient", "none", "failure"])
def test_low_scoring_match_reaches_judge_before_it_can_be_released(judgement):
    librarian = HybridLibrarian(embedding_model=ConstantEmbedding(), reranker=LowScoringPassageReranker())
    normal = librarian.retrieve(LibrarianRequest(query=QUESTION, book_scopes=[
        BookScope(work_id="pg23", book_version_id=VERSION, chapter_max=7),
    ]))
    assert normal.items == []
    seen = []

    async def judge(query, records):
        seen.extend(records)
        assert len(records) == 1
        assert records[0].chapter_number == 6
        assert "desire and determination to learn" in records[0].text
        if judgement == "failure":
            raise RuntimeError("Judge unavailable")
        return EvidenceStrengthDecision(
            evidence_strength=judgement, strength_reason="Independent answerability decision.",
            relevant_evidence_ids=(records[0].evidence_id,) if judgement == "sufficient" else (),
        )

    token = set_confirmed_reading(ConfirmedReading(work_id="pg23", chapter_max=7))
    ledger = set_turn_evidence(())
    try:
        request = build_request(QUESTION, "pg23", VERSION,
            ReadingBoundary(chapter_number=7, chapter_state="completed"))
        result = asyncio.run(_grounding_evidence(request, librarian=librarian, strength_judge=judge))
        assert len(seen) == 1
        if judgement == "sufficient":
            assert result.outcome == "evidence_found"
            assert result.evidence[0].chapter_number == 6
            assert set(turn_evidence()) == {seen[0].evidence_id}
        else:
            assert not turn_evidence()
            if judgement == "none":
                assert result.outcome == "no_evidence"
                assert not result.evidence
            else:
                assert result.kind == "failure"
                assert result.error_code == "evidence_judgement_unavailable"
    finally:
        reset_turn_evidence(ledger)
        reset_confirmed_reading(token)
