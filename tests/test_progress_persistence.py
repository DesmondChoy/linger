"""Current reader statements persist without replaying older session permissions."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from apps.backend import chat_turn, sessions
from apps.backend.progress_store import ReadingProgressStore, SavedProgress
from apps.backend.schemas import ChatRequest
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.contracts.triage import TurnNeeds
from src.linger.orchestration.reflection import ReflectionRelease
from src.linger.services.memory import AccountContext, MemoryPolicyService

ALICE = "pg11"
PINOCCHIO = "pg500"
IDENTIFY = "I'm reading Alice's Adventures in Wonderland."
WITHDRAW = "Wait, I haven't finished chapter 5 of Alice's Adventures in Wonderland yet."


def declaration(chapter: int) -> str:
    return f"I have finished chapter {chapter} of Alice's Adventures in Wonderland."


class Reader:
    def __init__(self, directory):
        self.account = AccountContext("progress-persistence")
        self.store = ReadingProgressStore(directory / "progress.sqlite3")
        self.service = MemoryPolicyService(directory / "memory")
        self.session_ids: set[str] = set()

    def turn(self, session: str, message: str, outcome: str = "released"):
        session_id = "progress-persistence-" + session
        self.session_ids.add(session_id)
        reflection = AsyncMock(return_value=ReflectionRelease(
            reply="A reflection.",
            release_source="application_safe_decline" if outcome == "declined" else "muse_candidate",
        ))
        if outcome in {"failed", "cancelled"}:
            reflection.side_effect = (
                RuntimeError("provider unavailable") if outcome == "failed" else asyncio.CancelledError()
            )
        with patch.object(chat_turn, "reflection_reply", reflection):
            run = chat_turn.run_chat_turn(
                ChatRequest(session_id=session_id, message=message),
                self.service, self.account, progress_store=self.store,
            )
            if outcome in {"failed", "cancelled"}:
                with pytest.raises(chat_turn.ChatTurnError if outcome == "failed" else asyncio.CancelledError):
                    asyncio.run(run)
                return None
            return asyncio.run(run)

    def saved(self, work_id: str = ALICE) -> int | None:
        saved = self.store.get(self.account.account_id, work_id)
        return saved.chapter_max if saved is not None else None


@pytest.fixture
def reader(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_turn, "assess_emotional_boundary", AsyncMock(
        return_value=EmotionalBoundaryAssessment(decision="continue_reflection"),
    ))
    monkeypatch.setattr(chat_turn, "triage_turn", AsyncMock(
        return_value=TurnNeeds(book_content="no", memory="none"),
    ))
    reader = Reader(tmp_path)
    yield reader
    for session_id in reader.session_ids:
        sessions.clear(session_id)


@pytest.mark.parametrize("outcome", ["declined", "failed", "cancelled"])
@pytest.mark.parametrize("fresh_session", [False, True])
@pytest.mark.parametrize("message, expected", [(declaration(2), 2), (WITHDRAW, None)])
def test_restrictions_survive_unreleased_turns(reader, outcome, fresh_session, message, expected):
    reader.turn("original", declaration(5))
    reader.turn("fresh" if fresh_session else "original", message, outcome)

    assert reader.saved() == expected
    response = reader.turn("later", IDENTIFY)
    assert response.inspection.context_resolution["chapter_max"] == expected


def test_restriction_is_persisted_before_the_first_model_await(reader, monkeypatch):
    reader.turn("original", declaration(5))
    observed = []

    async def boundary(*args, **kwargs):
        observed.append(reader.saved())
        return EmotionalBoundaryAssessment(decision="continue_reflection")

    monkeypatch.setattr(chat_turn, "assess_emotional_boundary", boundary)
    reader.turn("original", declaration(2))
    assert observed == [2]


@pytest.mark.parametrize("outcome", ["declined", "failed", "cancelled"])
def test_an_unreleased_raise_cannot_create_or_raise_saved_progress(reader, outcome):
    reader.turn("new", declaration(5), outcome)
    assert reader.saved() is None
    reader.turn("known", declaration(2))
    reader.turn("known", declaration(5), outcome)
    assert reader.saved() == 2


@pytest.mark.parametrize("old_chapter, new_chapter", [(None, 2), (5, 2), (2, 5)])
def test_carried_old_session_progress_cannot_overwrite_a_newer_statement(reader, old_chapter, new_chapter):
    reader.turn("old", declaration(old_chapter or 5))
    if old_chapter is None:
        reader.turn("old", WITHDRAW)
    reader.turn("new", declaration(new_chapter))
    reader.turn("old", "Thank you.")

    assert reader.saved() == new_chapter


def test_a_new_withdrawal_in_an_already_retracted_session_clears_newer_progress(reader):
    reader.turn("old", declaration(5))
    reader.turn("old", WITHDRAW)
    reader.turn("new", declaration(5))
    reader.turn("old", WITHDRAW, "failed")

    assert reader.saved() is None


@pytest.mark.parametrize("session_chapter, account_chapter, expected", [(2, 5, 3), (5, 2, 2), (3, 5, 3)])
def test_restrictions_compare_account_and_session_ceilings_independently(
    reader, session_chapter, account_chapter, expected,
):
    reader.turn("old", declaration(session_chapter))
    reader.turn("new", declaration(account_chapter))
    reader.turn("old", declaration(3), "failed")

    assert reader.saved() == expected


def test_withdrawal_preserves_other_books_and_accounts(reader):
    reader.turn("old", declaration(5))
    reader.turn("old", "I have finished chapter 4 of Pinocchio.")
    reader.store.record("other", SavedProgress(ALICE, "main", 7))
    reader.turn("old", WITHDRAW, "failed")

    assert reader.saved() is None
    assert reader.saved(PINOCCHIO) == 4
    assert reader.store.get("other", ALICE).chapter_max == 7


def test_a_released_explicit_raise_replaces_saved_progress(reader):
    reader.turn("old", declaration(2))
    reader.turn("old", declaration(5))
    assert reader.saved() == 5
