"""Per-account reading progress the reader stated or confirmed, persisted in SQLite.

One row per account and book holds the latest chapter the reader said they
completed. The newest statement wins, including a lower chapter, so a reader
who restarts or corrects themselves is believed. Application inferences are
never stored here: only explicit reader progress may outlive its conversation.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reading_progress (
    account_id TEXT NOT NULL,
    work_id TEXT NOT NULL,
    part_id TEXT NOT NULL,
    chapter_max INTEGER NOT NULL CHECK (chapter_max >= 1),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (account_id, work_id)
);
"""


@dataclass(frozen=True)
class SavedProgress:
    work_id: str
    part_id: str
    chapter_max: int


class ReadingProgressStore:
    """Opens one connection per operation, so it is safe to share across threads."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._path, timeout=5.0, isolation_level=None)
        try:
            yield conn
        finally:
            conn.close()

    def get(self, account_id: str, work_id: str) -> SavedProgress | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT part_id, chapter_max FROM reading_progress"
                " WHERE account_id = ? AND work_id = ?",
                (account_id, work_id),
            ).fetchone()
        return SavedProgress(work_id, row[0], row[1]) if row else None

    def list_for(self, account_id: str) -> tuple[SavedProgress, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT work_id, part_id, chapter_max FROM reading_progress"
                " WHERE account_id = ? ORDER BY work_id",
                (account_id,),
            ).fetchall()
        return tuple(SavedProgress(*row) for row in rows)

    def record(self, account_id: str, progress: SavedProgress) -> None:
        """Replace the book's progress with the reader's latest statement."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO reading_progress"
                " (account_id, work_id, part_id, chapter_max, updated_at)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT (account_id, work_id) DO UPDATE SET"
                " part_id = excluded.part_id, chapter_max = excluded.chapter_max,"
                " updated_at = excluded.updated_at",
                (
                    account_id,
                    progress.work_id,
                    progress.part_id,
                    progress.chapter_max,
                    datetime.now(UTC).isoformat(),
                ),
            )
