"""Later reader statements win even when replies finish in the opposite order."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from apps.backend import chat_turn, sessions
from apps.backend.progress_store import ReadingProgressStore, SavedProgress
from apps.backend.schemas import ChatRequest
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.contracts.triage import TurnNeeds
from src.linger.orchestration.conversational_memory import ConversationalCurationOutcome
from src.linger.orchestration.reflection import ReflectionRelease
from src.linger.services.memory import AccountContext, AutomaticMemoryCandidate, MemoryPolicyService

ALICE = "pg11"
IDENTIFY = "I'm reading Alice's Adventures in Wonderland."
WITHDRAW = "Wait, I haven't finished chapter 5 of Alice's Adventures in Wonderland yet."


def declaration(chapter):
    return f"I have finished chapter {chapter} of Alice's Adventures in Wonderland."


@pytest.fixture
def run_overlap(tmp_path, monkeypatch):
    account = AccountContext("progress-ordering")
    store = ReadingProgressStore(tmp_path / "progress.sqlite3")
    service = MemoryPolicyService(tmp_path / "memory")
    service.set_capture_enabled(account, True)
    session_ids = set()
    monkeypatch.setattr(chat_turn, "assess_emotional_boundary", AsyncMock(
        return_value=EmotionalBoundaryAssessment(decision="continue_reflection"),
    ))
    monkeypatch.setattr(chat_turn, "triage_turn", AsyncMock(
        return_value=TurnNeeds(book_content="no", memory="none"),
    ))

    async def run(
        messages, *, expected, outcome="released", stage="reflection", seed=5, carry=False,
        withdraw_before=False, superseded=True, older_outcome="released",
    ):
        waiting, resume = asyncio.Event(), asyncio.Event()
        paused = False
        fail_later = False

        async def reflection(*args, capture_source_text, **kwargs):
            nonlocal paused
            older = not paused and capture_source_text == (IDENTIFY if carry else declaration(7))
            if older:
                paused = True
                if stage == "reflection":
                    waiting.set()
                    await resume.wait()
                    if older_outcome == "declined":
                        return ReflectionRelease(reply="A decline.", release_source="application_safe_decline")
                else:
                    return ReflectionRelease(
                        reply="A reflection.", release_source="muse_candidate",
                        capture_decision="allow_capture",
                        automatic_capture_candidate=AutomaticMemoryCandidate(
                            text="I prefer quiet mornings for reading.", source_event_id="older-turn",
                            review_allows_capture=True, contains_sensitive_content=False,
                        ),
                    )
            if fail_later:
                if outcome == "failed":
                    raise RuntimeError("provider unavailable")
                if outcome == "cancelled":
                    raise asyncio.CancelledError()
                if outcome == "declined":
                    return ReflectionRelease(reply="A decline.", release_source="application_safe_decline")
            return ReflectionRelease(reply="A reflection.", release_source="muse_candidate")

        async def curate(*args, **kwargs):
            waiting.set()
            await resume.wait()
            return ConversationalCurationOutcome(status="no_change", memory_ids=())

        monkeypatch.setattr(chat_turn, "reflection_reply", reflection)
        monkeypatch.setattr(chat_turn, "curate_after_capture", curate)

        async def turn(session, message):
            session_id = "progress-ordering-" + session
            session_ids.add(session_id)
            return await chat_turn.run_chat_turn(
                ChatRequest(session_id=session_id, message=message),
                service, account, progress_store=store,
            )

        if seed is not None:
            await turn("seed" if carry == "saved" else "older", declaration(seed))
        if withdraw_before:
            await turn("later", WITHDRAW)
        earlier = asyncio.create_task(turn("older", IDENTIFY if carry else declaration(7)))
        try:
            await asyncio.wait_for(waiting.wait(), timeout=5)
            fail_later = outcome != "released"
            for message in messages:
                if outcome in {"failed", "cancelled"}:
                    with pytest.raises(chat_turn.ChatTurnError if outcome == "failed" else asyncio.CancelledError):
                        await turn("later", message)
                else:
                    await turn("later", message)
            fail_later = False
        finally:
            resume.set()
            await asyncio.wait_for(earlier, timeout=5)

        current = store.get(account.account_id, ALICE)
        assert (current.chapter_max if current else None) == expected
        local = sessions.reading_progress_for("progress-ordering-older", ALICE)
        assert local is None or local.chapter_max is None or (expected is not None and local.chapter_max <= expected)
        # The completed older turn must not re-authorize its declaration from session history.
        if superseded:
            assert declaration(7) not in {
                statement.text for statement in sessions.reader_statements("progress-ordering-older")
            }
        followup = await turn("older", IDENTIFY)
        assert followup.inspection.context_resolution["chapter_max"] == expected
        fresh = await turn("fresh", IDENTIFY)
        assert fresh.inspection.context_resolution["chapter_max"] == expected

    yield run
    for session_id in session_ids:
        sessions.clear(session_id)


@pytest.mark.parametrize("outcome", ["released", "declined", "failed", "cancelled"])
@pytest.mark.parametrize("message, expected", [(declaration(2), 2), (WITHDRAW, None)])
def test_an_older_raise_cannot_restore_newer_restricted_permission(run_overlap, outcome, message, expected):
    asyncio.run(run_overlap([message], expected=expected, outcome=outcome))


def test_deleting_and_recreating_the_same_permission_invalidates_the_older_raise(run_overlap):
    asyncio.run(run_overlap([WITHDRAW, declaration(5)], expected=5))


@pytest.mark.parametrize("chapter", [5, 9])
def test_a_later_unreleased_declaration_invalidates_an_older_raise_without_granting_more(run_overlap, chapter):
    asyncio.run(run_overlap([declaration(chapter)], expected=5, outcome="failed"))


def test_a_later_failed_first_declaration_does_not_allow_an_older_raise_to_create_permission(run_overlap):
    asyncio.run(run_overlap([declaration(2)], expected=None, outcome="failed", seed=None))


def test_a_withdrawal_before_any_saved_permission_invalidates_the_pending_first_declaration(run_overlap):
    asyncio.run(run_overlap([WITHDRAW], expected=None, seed=None))


@pytest.mark.parametrize("message, expected", [(declaration(2), 2), (WITHDRAW, None)])
def test_a_correction_during_memory_curation_also_invalidates_the_older_turn(run_overlap, message, expected):
    asyncio.run(run_overlap([message], expected=expected, stage="curation"))


@pytest.mark.parametrize("carry", ["saved", "session"])
def test_permission_cannot_be_carried_into_a_session_after_an_overlapping_withdrawal(run_overlap, carry):
    asyncio.run(run_overlap([WITHDRAW], expected=None, carry=carry))


@pytest.mark.parametrize("message, expected", [(declaration(2), 2), (WITHDRAW, None)])
def test_an_absent_account_row_still_guards_an_existing_session_during_overlap(run_overlap, message, expected):
    asyncio.run(run_overlap([message], expected=expected, carry="session", withdraw_before=True))


@pytest.mark.parametrize("message, expected", [(declaration(2), 2), (WITHDRAW, None)])
def test_an_older_declined_reply_cannot_restore_its_declaration_in_reader_history(run_overlap, message, expected):
    asyncio.run(run_overlap([message], expected=expected, older_outcome="declined"))


@pytest.mark.parametrize("message", [
    "The Mad Tea-Party in Alice's Adventures in Wonderland makes me think about belonging.",
    "The pool of tears in Alice's Adventures in Wonderland reminds me of feeling overwhelmed.",
    "Alice's Adventures in Wonderland and the rabbit hole remind me of moving somewhere new.",
])
def test_an_ordinary_reflection_cannot_invalidate_another_conversations_first_declaration(run_overlap, message):
    asyncio.run(run_overlap([message], expected=7, seed=None, superseded=False))


def test_one_withdrawal_cannot_delete_a_newer_update_between_preparation_steps(tmp_path, monkeypatch):
    account = AccountContext("withdrawal-interleave")
    store = ReadingProgressStore(tmp_path / "progress.sqlite3")
    other_process = ReadingProgressStore(tmp_path / "progress.sqlite3")
    service = MemoryPolicyService(tmp_path / "memory")
    session_id = "withdrawal-interleave"
    monkeypatch.setattr(chat_turn, "assess_emotional_boundary", AsyncMock(
        return_value=EmotionalBoundaryAssessment(decision="continue_reflection"),
    ))
    monkeypatch.setattr(chat_turn, "triage_turn", AsyncMock(
        return_value=TurnNeeds(book_content="no", memory="none"),
    ))
    monkeypatch.setattr(chat_turn, "reflection_reply", AsyncMock(
        return_value=ReflectionRelease(reply="A reflection.", release_source="muse_candidate"),
    ))

    async def run():
        async def turn(message):
            return await chat_turn.run_chat_turn(
                ChatRequest(session_id=session_id, message=message), service, account, progress_store=store,
            )

        await turn(declaration(5))
        withdraw = store.withdraw
        injected = False

        def withdraw_then_newer_declaration(account_id, work_id):
            nonlocal injected
            withdraw(account_id, work_id)
            if not injected:
                injected = True
                other_process.release(other_process.declare(account_id, SavedProgress(work_id, "main", 2)))

        monkeypatch.setattr(store, "withdraw", withdraw_then_newer_declaration)
        await turn(WITHDRAW)
        assert store.get(account.account_id, ALICE) == SavedProgress(ALICE, "main", 2)

    try:
        asyncio.run(run())
    finally:
        sessions.clear(session_id)
