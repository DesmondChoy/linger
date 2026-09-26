"""Username/password accounts and login tokens, persisted in SQLite.

Prototype-grade sign-in: passwords are salted scrypt hashes and tokens are
random, stored only as SHA-256 digests. There are no password resets, lockouts,
or email verification.
"""

import hashlib
import hmac
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

TOKEN_LIFETIME = timedelta(days=7)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    username TEXT PRIMARY KEY,
    password_salt BLOB NOT NULL,
    password_hash BLOB NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS login_tokens (
    token_digest TEXT PRIMARY KEY,
    username TEXT NOT NULL REFERENCES accounts (username) ON DELETE CASCADE,
    expires_at TEXT NOT NULL
);
"""


class UsernameTakenError(Exception):
    """Another account already uses this username."""


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AccountStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path, timeout=5)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            with connection:
                yield connection

    def create_account(self, username: str, password: str) -> str:
        """Create the account and return a login token for it."""
        salt = secrets.token_bytes(16)
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO accounts VALUES (?, ?, ?, ?)",
                    (username, salt, _hash_password(password, salt), _now()),
                )
        except sqlite3.IntegrityError:
            raise UsernameTakenError(username) from None
        return self._issue_token(username)

    def login(self, username: str, password: str) -> str | None:
        """Return a new login token, or None when the username or password is wrong."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT password_salt, password_hash FROM accounts WHERE username = ?",
                (username,),
            ).fetchone()
        if row is None:
            return None
        salt, expected = row
        if not hmac.compare_digest(_hash_password(password, salt), expected):
            return None
        return self._issue_token(username)

    def username_for(self, token: str) -> str | None:
        """Return the username a live token belongs to."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT username FROM login_tokens WHERE token_digest = ? AND expires_at > ?",
                (_digest(token), _now()),
            ).fetchone()
        return row[0] if row else None

    def logout(self, token: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM login_tokens WHERE token_digest = ?", (_digest(token),)
            )

    def _issue_token(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(UTC) + TOKEN_LIFETIME).isoformat()
        with self._connect() as connection:
            connection.execute("DELETE FROM login_tokens WHERE expires_at <= ?", (_now(),))
            connection.execute(
                "INSERT INTO login_tokens VALUES (?, ?, ?)",
                (_digest(token), username, expires_at),
            )
        return token


def _now() -> str:
    return datetime.now(UTC).isoformat()
