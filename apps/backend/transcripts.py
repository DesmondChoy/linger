"""Per-account chat transcripts persisted in SQLite.

Each session belongs to exactly one account, and every read and write is
scoped by account. A session owned by another account looks the same as a
missing one, so callers never learn whether it exists.
"""

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.linger.contracts.security_validation import check_storage_credentials, validate_user_input

from .message_normalization import normalize_reader_message

PREVIEW_MAX_CHARS = 80

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transcript_sessions (
    session_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    preview TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS transcript_sessions_by_account
    ON transcript_sessions (account_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS transcript_turns (
    session_id TEXT NOT NULL
        REFERENCES transcript_sessions (session_id) ON DELETE CASCADE,
    turn_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    user_message TEXT NOT NULL,
    assistant_message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    details TEXT,
    request_fingerprint TEXT,
    reader_input_version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, turn_id),
    UNIQUE (session_id, seq)
);
"""


class SessionOwnershipError(Exception):
    """The session id already belongs to a different account."""


class TurnConflictError(Exception):
    """A turn id was reused with different content."""


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    preview: str
    turn_count: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class TranscriptTurn:
    turn_id: str
    user_message: str
    assistant_message: str
    created_at: str
    # What the turn exposed for inspection (response contracts and progress), if saved.
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class TranscriptReplay:
    user_message: str
    request_fingerprint: str | None
    response: dict[str, Any] | None


def request_fingerprint(message: str) -> str:
    return hashlib.sha256(normalize_reader_message(message).encode()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _preview(message: str) -> str:
    text = " ".join(message.split())
    if len(text) <= PREVIEW_MAX_CHARS:
        return text
    return text[: PREVIEW_MAX_CHARS - 1].rstrip() + "…"


class TranscriptStore:
    """Opens one connection per operation, so it is safe to share across threads."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(transcript_turns)")}
            if "details" not in columns:
                conn.execute("ALTER TABLE transcript_turns ADD COLUMN details TEXT")
            if "request_fingerprint" not in columns:
                conn.execute("ALTER TABLE transcript_turns ADD COLUMN request_fingerprint TEXT")
            if "reader_input_version" not in columns:
                conn.execute(
                    "ALTER TABLE transcript_turns ADD COLUMN reader_input_version"
                    " INTEGER NOT NULL DEFAULT 0",
                )
            self._migrate_reader_input(conn)
            conn.commit()

    def _migrate_reader_input(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            "SELECT session_id, turn_id, user_message, details FROM transcript_turns"
            " WHERE reader_input_version = 0",
        ).fetchall()
        for session_id, turn_id, message, raw_details in rows:
            sanitized = validate_user_input(normalize_reader_message(message)).text
            details = None if raw_details is None else json.loads(raw_details)
            if isinstance(details, dict):
                response = details.get("response")
                inspection = response.get("inspection") if isinstance(response, dict) else None
                muse_turn = inspection.get("muse_turn") if isinstance(inspection, dict) else None
                if isinstance(muse_turn, dict):
                    muse_turn["user_message"] = sanitized
            conn.execute(
                "UPDATE transcript_turns SET user_message = ?, details = ?,"
                " request_fingerprint = ?, reader_input_version = 1"
                " WHERE session_id = ? AND turn_id = ?",
                (sanitized, None if details is None else json.dumps(details),
                 request_fingerprint(message), session_id, turn_id),
            )
        for session_id in {row[0] for row in rows}:
            first = conn.execute(
                "SELECT user_message FROM transcript_turns WHERE session_id = ? ORDER BY seq LIMIT 1",
                (session_id,),
            ).fetchone()
            conn.execute(
                "UPDATE transcript_sessions SET preview = ? WHERE session_id = ?",
                (_preview(first[0]), session_id),
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # Autocommit mode; writers open an explicit BEGIN IMMEDIATE transaction.
        conn = sqlite3.connect(self._path, timeout=5.0, isolation_level=None)
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
        finally:
            conn.close()

    def append_turn(
        self,
        account_id: str,
        session_id: str,
        turn_id: str,
        user_message: str,
        assistant_message: str,
        details: dict[str, Any] | None = None,
        *,
        request_fingerprint: str | None = None,
    ) -> None:
        """Record a turn; replaying an identical turn is a no-op."""
        user_message = check_storage_credentials(user_message)
        assistant_message = check_storage_credentials(assistant_message)
        details = check_storage_credentials(details)
        assert isinstance(user_message, str) and isinstance(assistant_message, str)
        assert details is None or isinstance(details, dict)
        now = _now()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT account_id FROM transcript_sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO transcript_sessions VALUES (?, ?, ?, ?, ?)",
                        (session_id, account_id, _preview(user_message), now, now),
                    )
                elif row[0] != account_id:
                    raise SessionOwnershipError(session_id)

                existing = conn.execute(
                    "SELECT user_message, assistant_message FROM transcript_turns"
                    " WHERE session_id = ? AND turn_id = ?",
                    (session_id, turn_id),
                ).fetchone()
                if existing is not None:
                    if existing != (user_message, assistant_message):
                        raise TurnConflictError(turn_id)
                    conn.execute("COMMIT")
                    return

                conn.execute(
                    "INSERT INTO transcript_turns (session_id, turn_id, seq,"
                    " user_message, assistant_message, created_at, details,"
                    " request_fingerprint, reader_input_version) VALUES (?, ?,"
                    " (SELECT COALESCE(MAX(seq), 0) + 1 FROM transcript_turns"
                    "  WHERE session_id = ?), ?, ?, ?, ?, ?, 1)",
                    (
                        session_id,
                        turn_id,
                        session_id,
                        user_message,
                        assistant_message,
                        now,
                        None if details is None else json.dumps(details),
                        request_fingerprint,
                    ),
                )
                conn.execute(
                    "UPDATE transcript_sessions SET updated_at = ? WHERE session_id = ?",
                    (now, session_id),
                )
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    def list_sessions(self, account_id: str) -> list[SessionSummary]:
        """The account's sessions, most recently updated first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT s.session_id, s.preview, COUNT(t.turn_id),"
                " s.created_at, s.updated_at"
                " FROM transcript_sessions s"
                " LEFT JOIN transcript_turns t ON t.session_id = s.session_id"
                " WHERE s.account_id = ?"
                " GROUP BY s.session_id"
                " ORDER BY s.updated_at DESC, s.rowid DESC",
                (account_id,),
            ).fetchall()
        return [SessionSummary(*row) for row in rows]

    def load(self, account_id: str, session_id: str) -> list[TranscriptTurn]:
        """Ordered turns, or [] when the session is missing or not the account's."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT t.turn_id, t.user_message, t.assistant_message, t.created_at,"
                " t.details"
                " FROM transcript_turns t"
                " JOIN transcript_sessions s ON s.session_id = t.session_id"
                " WHERE s.account_id = ? AND t.session_id = ?"
                " ORDER BY t.seq",
                (account_id, session_id),
            ).fetchall()
        return [
            TranscriptTurn(*row[:4], details=None if row[4] is None else json.loads(row[4]))
            for row in rows
        ]

    def replay(self, account_id: str, session_id: str, turn_id: str) -> TranscriptReplay | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT t.user_message, t.request_fingerprint, t.details"
                " FROM transcript_turns t JOIN transcript_sessions s USING (session_id)"
                " WHERE s.account_id = ? AND t.session_id = ? AND t.turn_id = ?",
                (account_id, session_id, turn_id),
            ).fetchone()
        if row is None:
            return None
        details = None if row[2] is None else json.loads(row[2])
        response = details.get("response") if isinstance(details, dict) else None
        return TranscriptReplay(row[0], row[1], response if isinstance(response, dict) else None)

    def owner_of(self, session_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT account_id FROM transcript_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return None if row is None else row[0]

    def delete(self, account_id: str, session_id: str) -> bool:
        """Delete the account's own session; False if absent or not theirs."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM transcript_sessions WHERE session_id = ? AND account_id = ?",
                (session_id, account_id),
            )
        return cursor.rowcount > 0
