"""A conversation has one active operation and one execution per client turn."""

import asyncio
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import UserPromptPart

from apps.backend import chat_turn, main, sessions
from apps.backend.transcripts import TranscriptStore
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.contracts.security_validation import validate_user_input
from src.linger.orchestration.reflection import ReflectionRelease
from src.linger.services.memory import MemoryPolicyService


@pytest.fixture
def reader(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "memory_service", MemoryPolicyService(tmp_path / "memory"))
    monkeypatch.setattr(chat_turn, "assess_emotional_boundary", AsyncMock(
        return_value=EmotionalBoundaryAssessment(decision="continue_reflection"),
    ))
    agent = AsyncMock(return_value=ReflectionRelease(
        reply="Approved reply", release_source="muse_candidate", provenance_verdicts=("pass",),
    ))
    monkeypatch.setattr(chat_turn, "reflection_reply", agent)
    yield agent
    for session_id in ("retry", "overlap", "private", "legacy", "independent"):
        sessions.clear(session_id)


def client():
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app, raise_app_exceptions=False),
        base_url="http://test",
    )


def body(session_id="retry", turn_id="turn", message="Hello"):
    return {"session_id": session_id, "turn_id": turn_id, "message": message}


def result(response, endpoint):
    assert response.status_code == 200, response.text
    if endpoint == "/api/chat":
        return response.json()
    frames = [frame for frame in response.text.split("\n\n") if frame.startswith("event: result\n")]
    assert len(frames) == 1, response.text
    return json.loads(frames[0].split("\ndata: ", 1)[1])


def conflict(response, endpoint):
    if endpoint == "/api/chat":
        assert response.status_code == 409, response.text
    else:
        assert response.status_code == 200
        assert "event: error\n" in response.text
        assert "event: result\n" not in response.text


@pytest.mark.parametrize("first_endpoint,retry_endpoint", [
    ("/api/chat", "/api/chat/stream"), ("/api/chat/stream", "/api/chat"),
])
@pytest.mark.parametrize("message", ["Hello", "Email me at alice@example.com"])
def test_retry_replays_saved_response_without_another_execution(reader, first_endpoint, retry_endpoint, message):
    async def run():
        async with client() as api:
            first = result(await api.post(first_endpoint, json=body(message=message)), first_endpoint)
            retried = await api.post(retry_endpoint, json=body(message=f"  {message}  "))
            repeated = result(retried, retry_endpoint)
            if retry_endpoint == "/api/chat/stream":
                assert "event: progress\n" not in retried.text
            assert repeated == first
            assert reader.await_count == 1
            assert len(sessions.history("retry")) == 2
            assert len(sessions.turn_records("retry")) == 1
            sessions.clear("retry")
            main.transcript_store = TranscriptStore(main.transcript_store._path)
            restarted = result(await api.post(first_endpoint, json=body(message=message)), first_endpoint)
            assert restarted == first
            assert reader.await_count == 1
            assert len(sessions.history("retry")) == 2
    asyncio.run(run())


@pytest.mark.parametrize("endpoint", ["/api/chat", "/api/chat/stream"])
@pytest.mark.parametrize("original,changed", [
    ("Hello", "Something different"),
    ("Email me at alice@example.com", "Email me at bob@example.com"),
])
def test_reused_turn_id_with_changed_input_is_refused_before_execution(reader, endpoint, original, changed):
    async def run():
        async with client() as api:
            result(await api.post(endpoint, json=body(message=original)), endpoint)
            conflict(await api.post(endpoint, json=body(message=changed)), endpoint)
            assert reader.await_count == 1
            assert len(sessions.history("retry")) == 2
            assert len(main.transcript_store.load("user:test-reader", "retry")) == 1
    asyncio.run(run())


def test_retry_without_original_fingerprint_does_not_guess_pii_equivalence(reader):
    async def run():
        async with client() as api:
            result(await api.post("/api/chat", json=body(message="Email me at alice@example.com")), "/api/chat")
            with sqlite3.connect(main.transcript_store._path) as connection:
                connection.execute("UPDATE transcript_turns SET request_fingerprint = NULL")
            conflict(await api.post("/api/chat", json=body(message="Email me at bob@example.com")), "/api/chat")
            assert reader.await_count == 1
    asyncio.run(run())


@pytest.mark.parametrize("endpoint", ["/api/chat", "/api/chat/stream"])
def test_new_transcript_uses_sanitized_reader_input(reader, endpoint):
    message = "Email me at alice@example.com and call +65 8123 4567."
    sanitized = validate_user_input(message).text

    async def run():
        async with client() as api:
            response = result(await api.post(endpoint, json=body("private", message=message)), endpoint)
            assert response["inspection"]["muse_turn"]["user_message"] == sanitized
            saved = main.transcript_store.load("user:test-reader", "private")[0]
            assert saved.user_message == sanitized
            with sqlite3.connect(main.transcript_store._path) as connection:
                stored, preview = connection.execute(
                    "SELECT t.user_message, s.preview FROM transcript_turns t"
                    " JOIN transcript_sessions s USING (session_id)",
                ).fetchone()
            assert stored == sanitized
            assert "alice@example.com" not in preview
            assert "+65 8123 4567" not in preview
    asyncio.run(run())


def test_legacy_reader_input_is_migrated_before_history_and_restart(reader, tmp_path, monkeypatch):
    path = tmp_path / "legacy.sqlite3"
    TranscriptStore(path)
    raw = "Email me at alice@example.com."
    assistant = "Generated contact editor@example.com."
    details = {"response": {"inspection": {"muse_turn": {"user_message": raw}}},
               "generated_context": assistant}
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO transcript_sessions VALUES (?, ?, ?, ?, ?)",
                           ("legacy", "user:test-reader", raw, "then", "then"))
        connection.execute(
            "INSERT INTO transcript_turns (session_id, turn_id, seq, user_message, assistant_message, created_at, details)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("legacy", "old", 1, raw, assistant, "then", json.dumps(details)),
        )
    monkeypatch.setattr(main, "transcript_store", TranscriptStore(path))
    sanitized = validate_user_input(raw).text

    async def run():
        async with client() as api:
            history = (await api.get("/api/history")).json()
            assert history[0]["turns"][0]["user_message"] == sanitized
            assert history[0]["turns"][0]["assistant_message"] == assistant
            assert history[0]["turns"][0]["details"]["response"]["inspection"]["muse_turn"]["user_message"] == sanitized
            assert history[0]["turns"][0]["details"]["generated_context"] == assistant
            conflict(await api.post("/api/chat", json=body("legacy", "old", raw)), "/api/chat")
            assert reader.await_count == 0
            result(await api.post("/api/chat", json=body("legacy", "new")), "/api/chat")
            restored = next(part.content for part in sessions.history("legacy")[0].parts
                            if isinstance(part, UserPromptPart))
            assert restored == sanitized
    asyncio.run(run())
    with sqlite3.connect(path) as connection:
        stored, preview = connection.execute(
            "SELECT t.user_message, s.preview FROM transcript_turns t"
            " JOIN transcript_sessions s USING (session_id) WHERE t.turn_id = 'old'",
        ).fetchone()
    assert stored == sanitized
    assert preview == sanitized
    def unexpected_scan(*_args, **_kwargs):
        pytest.fail("Already migrated reader input was scanned again")
    monkeypatch.setattr("apps.backend.transcripts.validate_user_input", unexpected_scan)
    assert TranscriptStore(path).load("user:test-reader", "legacy")[0].assistant_message == assistant


@pytest.mark.parametrize("endpoint", ["/api/chat", "/api/chat/stream"])
@pytest.mark.parametrize("cancel", [False, True])
def test_overlapping_turn_and_delete_are_refused_until_operation_ends(reader, monkeypatch, endpoint, cancel):
    async def run():
        entered, resume = asyncio.Event(), asyncio.Event()

        async def delayed(*args, **kwargs):
            if kwargs["source_event_id"] == "older":
                entered.set()
                await resume.wait()
                raise RuntimeError("provider unavailable")
            return ReflectionRelease(reply="Approved reply", release_source="muse_candidate", provenance_verdicts=("pass",))

        monkeypatch.setattr(chat_turn, "reflection_reply", AsyncMock(side_effect=delayed))
        async with client() as api:
            request = asyncio.create_task(api.post(endpoint, json=body("overlap", "older")))
            await asyncio.wait_for(entered.wait(), timeout=2)
            try:
                newer = await api.post(endpoint, json=body(
                    "overlap", "newer", "I am reading Alice in Wonderland and I have finished Chapter 5.",
                ))
                conflict(newer, endpoint)
                assert (await api.delete("/api/sessions/overlap")).status_code == 409
                assert (await api.post("/api/chat", json=body("independent"))).status_code == 200
            finally:
                if cancel:
                    request.cancel()
                else:
                    resume.set()
                await asyncio.gather(request, return_exceptions=True)
            completed = result(await api.post(endpoint, json=body(
                "overlap", "newer", "I am reading Alice in Wonderland and I have finished Chapter 5.",
            )), endpoint)
            assert completed["inspection"]["muse_turn"]["policy"]["spoiler_ceiling"] == 5
            assert sessions.book_selection("overlap").book_id == "pg11"
            assert sessions.reading_progress("overlap").chapter_max == 5
            assert (await api.delete("/api/sessions/overlap")).status_code == 204
            assert sessions.history("overlap") == []
            assert main.transcript_store.load("user:test-reader", "overlap") == []
    asyncio.run(run())


def test_delete_is_refused_while_another_loop_commits_the_turn(reader, monkeypatch):
    entered, resume = threading.Event(), threading.Event()
    append_turn = main.transcript_store.append_turn

    def delayed_commit(*args, **kwargs):
        entered.set()
        assert resume.wait(timeout=3)
        append_turn(*args, **kwargs)

    monkeypatch.setattr(main.transcript_store, "append_turn", delayed_commit)
    with ThreadPoolExecutor(max_workers=1) as workers, TestClient(main.app) as api:
        request = workers.submit(api.post, "/api/chat", json=body("overlap"))
        assert entered.wait(timeout=3)
        try:
            with TestClient(main.app) as other_loop:
                assert other_loop.delete("/api/sessions/overlap").status_code == 409
        finally:
            resume.set()
        assert request.result(timeout=3).status_code == 200
        assert api.delete("/api/sessions/overlap").status_code == 204
    assert main.transcript_store.load("user:test-reader", "overlap") == []
