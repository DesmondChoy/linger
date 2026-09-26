import threading
from pathlib import Path

import pytest

from apps.backend.transcripts import (
    PREVIEW_MAX_CHARS,
    SessionOwnershipError,
    TranscriptStore,
    TurnConflictError,
)


@pytest.fixture
def store(tmp_path: Path) -> TranscriptStore:
    return TranscriptStore(tmp_path / "nested" / "transcripts.sqlite3")


def test_round_trip_preserves_turn_order(store: TranscriptStore) -> None:
    for index in range(3):
        store.append_turn("alice", "s1", f"t{index}", f"question {index}", f"answer {index}")

    turns = store.load("alice", "s1")

    assert [turn.turn_id for turn in turns] == ["t0", "t1", "t2"]
    assert turns[1].user_message == "question 1"
    assert turns[1].assistant_message == "answer 1"
    assert turns[0].created_at.endswith("+00:00")


def test_list_sessions_newest_first_with_preview(store: TranscriptStore) -> None:
    long_question = "word " * 40
    store.append_turn("alice", "old", "t1", long_question, "a")
    store.append_turn("alice", "old", "t2", "second", "b")
    store.append_turn("alice", "new", "t1", "hello", "c")

    summaries = store.list_sessions("alice")

    assert [summary.session_id for summary in summaries] == ["new", "old"]
    old = summaries[1]
    assert old.turn_count == 2
    assert len(old.preview) <= PREVIEW_MAX_CHARS
    assert old.preview.endswith("…")
    assert old.created_at <= old.updated_at

    store.append_turn("alice", "old", "t3", "third", "d")
    assert [summary.session_id for summary in store.list_sessions("alice")] == ["old", "new"]


def test_identical_retry_is_noop(store: TranscriptStore) -> None:
    store.append_turn("alice", "s1", "t1", "q", "a")
    store.append_turn("alice", "s1", "t1", "q", "a")

    assert len(store.load("alice", "s1")) == 1
    assert store.list_sessions("alice")[0].turn_count == 1


def test_conflicting_retry_raises_and_keeps_original(store: TranscriptStore) -> None:
    store.append_turn("alice", "s1", "t1", "q", "a")

    with pytest.raises(TurnConflictError):
        store.append_turn("alice", "s1", "t1", "q", "different")

    assert store.load("alice", "s1")[0].assistant_message == "a"


def test_accounts_are_isolated(store: TranscriptStore) -> None:
    store.append_turn("alice", "s1", "t1", "secret", "a")

    assert store.load("bob", "s1") == []
    assert store.list_sessions("bob") == []
    assert store.delete("bob", "s1") is False
    assert len(store.load("alice", "s1")) == 1

    assert store.delete("alice", "s1") is True
    assert store.load("alice", "s1") == []
    assert store.list_sessions("alice") == []
    assert store.owner_of("s1") is None
    assert store.delete("alice", "s1") is False


def test_cross_account_append_raises_without_writing(store: TranscriptStore) -> None:
    store.append_turn("alice", "s1", "t1", "q", "a")

    with pytest.raises(SessionOwnershipError):
        store.append_turn("bob", "s1", "t2", "hijack", "x")

    assert store.owner_of("s1") == "alice"
    assert [turn.turn_id for turn in store.load("alice", "s1")] == ["t1"]
    assert store.owner_of("unknown") is None


def test_transcripts_survive_a_new_store_instance(tmp_path: Path) -> None:
    path = tmp_path / "transcripts.sqlite3"
    TranscriptStore(path).append_turn("alice", "s1", "t1", "q", "a")

    reopened = TranscriptStore(path)

    assert [turn.turn_id for turn in reopened.load("alice", "s1")] == ["t1"]
    assert reopened.owner_of("s1") == "alice"


def test_concurrent_appends_from_threads(store: TranscriptStore) -> None:
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            for turn in range(20):
                store.append_turn(f"acct{index % 3}", f"s{index}", f"t{turn}", "q", "a")
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    for index in range(8):
        turns = store.load(f"acct{index % 3}", f"s{index}")
        assert [turn.turn_id for turn in turns] == [f"t{turn}" for turn in range(20)]


def test_turn_details_round_trip(store: TranscriptStore) -> None:
    details = {"response": {"reply": "hi"}, "progress": [{"sequence": 1}]}
    store.append_turn("alice", "s1", "t1", "hello", "hi", details=details)
    store.append_turn("alice", "s1", "t2", "again", "yes")

    turns = store.load("alice", "s1")
    assert turns[0].details == details
    assert turns[1].details is None


def test_a_database_from_before_turn_details_keeps_its_transcripts(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE transcript_sessions (session_id TEXT PRIMARY KEY, account_id TEXT NOT NULL,
                preview TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE transcript_turns (session_id TEXT NOT NULL, turn_id TEXT NOT NULL,
                seq INTEGER NOT NULL, user_message TEXT NOT NULL, assistant_message TEXT NOT NULL,
                created_at TEXT NOT NULL, PRIMARY KEY (session_id, turn_id), UNIQUE (session_id, seq));
            INSERT INTO transcript_sessions VALUES ('s1', 'alice', 'hello', 'then', 'then');
            INSERT INTO transcript_turns VALUES ('s1', 't1', 1, 'hello', 'hi', 'then');
            """
        )

    store = TranscriptStore(path)
    assert [(t.user_message, t.details) for t in store.load("alice", "s1")] == [("hello", None)]
    store.append_turn("alice", "s1", "t2", "again", "yes", details={"progress": []})
    assert store.load("alice", "s1")[1].details == {"progress": []}
