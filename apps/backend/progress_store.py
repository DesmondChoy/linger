"""Per-account reading progress the reader stated or confirmed, persisted in SQLite.

Each reader declaration advances a durable revision before model work starts.
Restrictions apply immediately; a released turn can raise permission only while
its revision is current. Revision rows survive withdrawals, so an older turn
cannot restore permission after its saved chapter has been deleted.
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
CREATE TABLE IF NOT EXISTS reading_progress_revisions (
    account_id TEXT NOT NULL,
    work_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    PRIMARY KEY (account_id, work_id)
);
"""


@dataclass(frozen=True)
class SavedProgress:
    work_id: str
    part_id: str
    chapter_max: int


@dataclass(frozen=True)
class ProgressDeclaration:
    account_id: str
    progress: SavedProgress
    revision: int


@dataclass(frozen=True)
class ProgressSnapshot:
    account_id: str
    work_id: str
    revision: int
    progress: SavedProgress | None


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
        return self.snapshot(account_id, work_id).progress

    def snapshot(self, account_id: str, work_id: str) -> ProgressSnapshot:
        """Read permission and its revision together, including withdrawn or legacy rows."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(r.revision, 0), p.part_id, p.chapter_max"
                " FROM (SELECT ? AS account_id, ? AS work_id) AS requested"
                " LEFT JOIN reading_progress_revisions AS r USING (account_id, work_id)"
                " LEFT JOIN reading_progress AS p USING (account_id, work_id)",
                (account_id, work_id),
            ).fetchone()
        progress = SavedProgress(work_id, row[1], row[2]) if row[1] is not None else None
        return ProgressSnapshot(account_id, work_id, row[0], progress)

    def list_for(self, account_id: str) -> tuple[SavedProgress, ...]:
        return tuple(snapshot.progress for snapshot in self.list_snapshots(account_id) if snapshot.progress is not None)

    def list_snapshots(self, account_id: str) -> tuple[ProgressSnapshot, ...]:
        """Read all saved permissions and their revisions in one database snapshot."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT p.work_id, p.part_id, p.chapter_max, COALESCE(r.revision, 0)"
                " FROM reading_progress AS p"
                " LEFT JOIN reading_progress_revisions AS r USING (account_id, work_id)"
                " WHERE p.account_id = ? ORDER BY p.work_id",
                (account_id,),
            ).fetchall()
        return tuple(ProgressSnapshot(account_id, row[0], row[3], SavedProgress(*row[:3])) for row in rows)

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    @staticmethod
    def _advance(conn: sqlite3.Connection, account_id: str, work_id: str) -> int:
        row = conn.execute(
            "INSERT INTO reading_progress_revisions (account_id, work_id, revision) VALUES (?, ?, 1)"
            " ON CONFLICT (account_id, work_id) DO UPDATE SET revision = revision + 1"
            " RETURNING revision",
            (account_id, work_id),
        ).fetchone()
        return row[0]

    def withdraw(self, account_id: str, work_id: str) -> None:
        """Revoke permission and invalidate pending declarations, even when no chapter was saved."""
        with self._transaction() as conn:
            self._advance(conn, account_id, work_id)
            conn.execute(
                "DELETE FROM reading_progress WHERE account_id = ? AND work_id = ?",
                (account_id, work_id),
            )

    def declare(self, account_id: str, progress: SavedProgress) -> ProgressDeclaration:
        """Register a new statement and lower an existing same-part ceiling before model work."""
        with self._transaction() as conn:
            revision = self._advance(conn, account_id, progress.work_id)
            conn.execute(
                "UPDATE reading_progress SET chapter_max = ?, updated_at = ?"
                " WHERE account_id = ? AND work_id = ? AND part_id = ? AND chapter_max > ?",
                (
                    progress.chapter_max,
                    datetime.now(UTC).isoformat(),
                    account_id,
                    progress.work_id,
                    progress.part_id,
                    progress.chapter_max,
                ),
            )
        return ProgressDeclaration(account_id, progress, revision)

    def release(self, declaration: ProgressDeclaration) -> bool:
        """Save released progress only if no newer statement or withdrawal superseded it."""
        progress = declaration.progress
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO reading_progress (account_id, work_id, part_id, chapter_max, updated_at)"
                " SELECT account_id, work_id, ?, ?, ? FROM reading_progress_revisions"
                " WHERE account_id = ? AND work_id = ? AND revision = ?"
                " ON CONFLICT (account_id, work_id) DO UPDATE SET"
                " part_id = excluded.part_id, chapter_max = excluded.chapter_max, updated_at = excluded.updated_at",
                (
                    progress.part_id, progress.chapter_max, datetime.now(UTC).isoformat(),
                    declaration.account_id, progress.work_id, declaration.revision,
                ),
            )
        return cursor.rowcount == 1

    def is_current(self, snapshot: ProgressSnapshot) -> bool:
        return self.snapshot(snapshot.account_id, snapshot.work_id) == snapshot
