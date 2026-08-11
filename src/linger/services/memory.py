"""Account-scoped Markdown memory storage and deterministic capture policy."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

CaptureType = Literal["explicit", "automatic", "correction"]


class MemoryServiceError(Exception):
    """Base class for deterministic memory service failures."""


class MemoryNotFoundError(MemoryServiceError):
    """Raised when an active memory is unavailable to the requesting account."""


class MemoryConflictError(MemoryServiceError):
    """Raised when one source event is reused for different memory content."""


class MemoryPolicyError(MemoryServiceError):
    """Raised when an automatic capture fails deterministic policy."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class MemoryStorageError(MemoryServiceError):
    """Raised when a stored memory cannot be parsed or validated."""


@dataclass(frozen=True)
class AccountContext:
    """Trusted account identity supplied by application request context."""

    account_id: str

    def __post_init__(self) -> None:
        _require_text(self.account_id, "account_id")


@dataclass(frozen=True)
class AutomaticMemoryCandidate:
    """Untrusted automatic-capture input with no account or write authority."""

    text: str
    source_event_id: str
    review_allows_capture: bool
    contains_sensitive_content: bool
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class MemoryRecord:
    """One immutable version of a stored memory."""

    memory_id: str
    account_key: str
    text: str
    capture_type: CaptureType
    source_event_id: str
    idempotency_key: str
    root_memory_id: str
    supersedes_memory_id: str | None
    evidence_ids: tuple[str, ...]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SaveResult:
    """A save result that distinguishes a new commit from an idempotent retry."""

    record: MemoryRecord
    created: bool


class MemoryPolicyService:
    """Sole authority for local memory policy, reads, and writes."""

    def __init__(self, root: Path | str = Path("memories")) -> None:
        self.root = Path(root)
        self._lock = threading.RLock()

    def capture_enabled(self, context: AccountContext) -> bool:
        """Return whether automatic capture is enabled for this account."""
        with self._lock:
            policy_path = self._account_dir(context) / "policy.json"
            if not policy_path.exists():
                return False
            try:
                policy = json.loads(policy_path.read_text(encoding="utf-8"))
                if policy.get("schema_version") != 1 or not isinstance(
                    policy.get("capture_enabled"), bool
                ):
                    raise ValueError("unsupported policy")
                return policy["capture_enabled"]
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise MemoryStorageError(
                    f"Invalid memory policy: {policy_path}"
                ) from exc

    def set_capture_enabled(
        self,
        context: AccountContext,
        enabled: bool,
    ) -> None:
        """Persist this account's automatic-capture preference atomically."""
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        with self._lock:
            account_dir = self._ensure_account_dir(context)
            payload = json.dumps(
                {"schema_version": 1, "capture_enabled": enabled},
                indent=2,
                sort_keys=True,
            )
            _replace_atomically(account_dir / "policy.json", payload + "\n")

    def save_explicit(
        self,
        context: AccountContext,
        *,
        text: str,
        source_event_id: str,
        evidence_ids: tuple[str, ...] = (),
    ) -> SaveResult:
        """Save a user-requested memory without automatic-capture policy."""
        return self._save_root(
            context,
            text=text,
            source_event_id=source_event_id,
            capture_type="explicit",
            evidence_ids=evidence_ids,
        )

    def save_automatic(
        self,
        context: AccountContext,
        candidate: AutomaticMemoryCandidate,
    ) -> SaveResult:
        """Save a candidate only after every automatic policy rule passes."""
        with self._lock:
            if not self.capture_enabled(context):
                raise MemoryPolicyError("automatic_capture_disabled")
            if not candidate.review_allows_capture:
                raise MemoryPolicyError("upstream_review_rejected_capture")
            if candidate.contains_sensitive_content:
                raise MemoryPolicyError("sensitive_content_requires_explicit_save")
            return self._save_root(
                context,
                text=candidate.text,
                source_event_id=candidate.source_event_id,
                capture_type="automatic",
                evidence_ids=candidate.evidence_ids,
            )

    def correct(
        self,
        context: AccountContext,
        memory_id: str,
        *,
        text: str,
        source_event_id: str,
    ) -> SaveResult:
        """Create an immutable version linked to one active memory."""
        _require_text(text, "text")
        _require_text(source_event_id, "source_event_id")
        with self._lock:
            records = self._records_by_id(context)
            target = records.get(memory_id)
            if target is None:
                raise MemoryNotFoundError(memory_id)

            idempotency_key = _idempotency_key(
                context.account_id,
                source_event_id,
                "correction",
            )
            correction = self._existing_idempotent(context, idempotency_key)
            if correction is not None:
                self._require_matching_retry(
                    correction,
                    text=text,
                    source_event_id=source_event_id,
                    capture_type="correction",
                    evidence_ids=target.evidence_ids,
                    root_memory_id=target.root_memory_id,
                    supersedes_memory_id=target.memory_id,
                )
                return SaveResult(record=correction, created=False)

            if target.memory_id not in _active_ids(records.values()):
                raise MemoryNotFoundError(memory_id)

            record = _new_record(
                account_key=_account_key(context.account_id),
                text=text,
                capture_type="correction",
                source_event_id=source_event_id,
                idempotency_key=idempotency_key,
                evidence_ids=target.evidence_ids,
                root_memory_id=target.root_memory_id,
                supersedes_memory_id=target.memory_id,
            )
            return self._commit(context, record)

    def list_active(self, context: AccountContext) -> list[MemoryRecord]:
        """List only current memory versions owned by this account."""
        with self._lock:
            records = self._records_by_id(context)
            active_ids = _active_ids(records.values())
            return sorted(
                (record for key, record in records.items() if key in active_ids),
                key=lambda record: (record.created_at, record.memory_id),
            )

    def get_active(
        self,
        context: AccountContext,
        memory_id: str,
    ) -> MemoryRecord:
        """Return an active account-owned memory without leaking its existence."""
        for record in self.list_active(context):
            if record.memory_id == memory_id:
                return record
        raise MemoryNotFoundError(memory_id)

    def delete(self, context: AccountContext, memory_id: str) -> int:
        """Delete every stored version belonging to one active memory family."""
        with self._lock:
            records = self._records_by_id(context)
            target = records.get(memory_id)
            if target is None or target.memory_id not in _active_ids(records.values()):
                raise MemoryNotFoundError(memory_id)

            family = [
                record
                for record in records.values()
                if record.root_memory_id == target.root_memory_id
            ]
            account_dir = self._account_dir(context)
            for record in family:
                (account_dir / f"{record.idempotency_key}.md").unlink(
                    missing_ok=True
                )
            return len(family)

    def _save_root(
        self,
        context: AccountContext,
        *,
        text: str,
        source_event_id: str,
        capture_type: Literal["explicit", "automatic"],
        evidence_ids: tuple[str, ...],
    ) -> SaveResult:
        _require_text(text, "text")
        _require_text(source_event_id, "source_event_id")
        with self._lock:
            idempotency_key = _idempotency_key(
                context.account_id,
                source_event_id,
                capture_type,
            )
            existing = self._existing_idempotent(context, idempotency_key)
            if existing is not None:
                self._require_matching_retry(
                    existing,
                    text=text,
                    source_event_id=source_event_id,
                    capture_type=capture_type,
                    evidence_ids=evidence_ids,
                    root_memory_id=existing.memory_id,
                    supersedes_memory_id=None,
                )
                return SaveResult(record=existing, created=False)

            memory_id = _memory_id(idempotency_key)
            record = _new_record(
                account_key=_account_key(context.account_id),
                text=text,
                capture_type=capture_type,
                source_event_id=source_event_id,
                idempotency_key=idempotency_key,
                evidence_ids=evidence_ids,
                root_memory_id=memory_id,
                supersedes_memory_id=None,
            )
            return self._commit(context, record)

    def _commit(self, context: AccountContext, record: MemoryRecord) -> SaveResult:
        account_dir = self._ensure_account_dir(context)
        path = account_dir / f"{record.idempotency_key}.md"
        try:
            _create_atomically(path, _serialize(record))
            return SaveResult(record=record, created=True)
        except FileExistsError:
            existing = _read_record(path)
            self._require_matching_retry(
                existing,
                text=record.text,
                source_event_id=record.source_event_id,
                capture_type=record.capture_type,
                evidence_ids=record.evidence_ids,
                root_memory_id=record.root_memory_id,
                supersedes_memory_id=record.supersedes_memory_id,
            )
            return SaveResult(record=existing, created=False)

    def _existing_idempotent(
        self,
        context: AccountContext,
        idempotency_key: str,
    ) -> MemoryRecord | None:
        path = self._account_dir(context) / f"{idempotency_key}.md"
        return _read_record(path) if path.exists() else None

    def _records_by_id(self, context: AccountContext) -> dict[str, MemoryRecord]:
        account_dir = self._account_dir(context)
        if not account_dir.exists():
            return {}
        records = (_read_record(path) for path in account_dir.glob("*.md"))
        return {record.memory_id: record for record in records}

    def _require_matching_retry(
        self,
        record: MemoryRecord,
        *,
        text: str,
        source_event_id: str,
        capture_type: CaptureType,
        evidence_ids: tuple[str, ...],
        root_memory_id: str,
        supersedes_memory_id: str | None,
    ) -> None:
        expected = (
            text,
            source_event_id,
            capture_type,
            evidence_ids,
            root_memory_id,
            supersedes_memory_id,
        )
        actual = (
            record.text,
            record.source_event_id,
            record.capture_type,
            record.evidence_ids,
            record.root_memory_id,
            record.supersedes_memory_id,
        )
        if actual != expected:
            raise MemoryConflictError(
                f"Source event {source_event_id!r} was already used"
            )

    def _account_dir(self, context: AccountContext) -> Path:
        return self.root / _account_key(context.account_id)

    def _ensure_account_dir(self, context: AccountContext) -> Path:
        account_dir = self._account_dir(context)
        account_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        return account_dir


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must not be blank")


def _account_key(account_id: str) -> str:
    return hashlib.sha256(account_id.encode("utf-8")).hexdigest()


def _idempotency_key(
    account_id: str,
    source_event_id: str,
    capture_type: CaptureType,
) -> str:
    material = "\0".join((account_id, source_event_id, capture_type))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _memory_id(idempotency_key: str) -> str:
    return f"mem_{idempotency_key}"


def _new_record(
    *,
    account_key: str,
    text: str,
    capture_type: CaptureType,
    source_event_id: str,
    idempotency_key: str,
    evidence_ids: tuple[str, ...],
    root_memory_id: str,
    supersedes_memory_id: str | None,
) -> MemoryRecord:
    timestamp = datetime.now(UTC).isoformat()
    return MemoryRecord(
        memory_id=_memory_id(idempotency_key),
        account_key=account_key,
        text=text,
        capture_type=capture_type,
        source_event_id=source_event_id,
        idempotency_key=idempotency_key,
        root_memory_id=root_memory_id,
        supersedes_memory_id=supersedes_memory_id,
        evidence_ids=tuple(evidence_ids),
        created_at=timestamp,
        updated_at=timestamp,
    )


def _active_ids(records: Iterable[MemoryRecord]) -> set[str]:
    record_list = list(records)
    superseded = {
        record.supersedes_memory_id
        for record in record_list
        if record.supersedes_memory_id is not None
    }
    return {record.memory_id for record in record_list} - superseded


def _serialize(record: MemoryRecord) -> str:
    metadata = {
        "schema_version": 1,
        "memory_id": record.memory_id,
        "account_key": record.account_key,
        "capture_type": record.capture_type,
        "source_event_id": record.source_event_id,
        "idempotency_key": record.idempotency_key,
        "root_memory_id": record.root_memory_id,
        "supersedes_memory_id": record.supersedes_memory_id,
        "evidence_ids": list(record.evidence_ids),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }
    front_matter = json.dumps(metadata, indent=2, sort_keys=True)
    return f"---\n{front_matter}\n---\n{record.text}\n"


def _read_record(path: Path) -> MemoryRecord:
    try:
        raw = path.read_text(encoding="utf-8")
        if not raw.startswith("---\n"):
            raise ValueError("missing JSON front matter")
        front_matter, text = raw[4:].split("\n---\n", maxsplit=1)
        metadata = json.loads(front_matter)
        if metadata.get("schema_version") != 1:
            raise ValueError("unsupported schema")
        if metadata.get("capture_type") not in {
            "explicit",
            "automatic",
            "correction",
        }:
            raise ValueError("invalid capture type")
        record = MemoryRecord(
            memory_id=metadata["memory_id"],
            account_key=metadata["account_key"],
            text=text.removesuffix("\n"),
            capture_type=metadata["capture_type"],
            source_event_id=metadata["source_event_id"],
            idempotency_key=metadata["idempotency_key"],
            root_memory_id=metadata["root_memory_id"],
            supersedes_memory_id=metadata["supersedes_memory_id"],
            evidence_ids=tuple(metadata["evidence_ids"]),
            created_at=metadata["created_at"],
            updated_at=metadata["updated_at"],
        )
        if path.name != f"{record.idempotency_key}.md":
            raise ValueError("filename does not match idempotency key")
        if path.parent.name != record.account_key:
            raise ValueError("record account does not match its directory")
        if record.memory_id != _memory_id(record.idempotency_key):
            raise ValueError("memory ID does not match idempotency key")
        return record
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MemoryStorageError(f"Invalid memory record: {path}") from exc


def _create_atomically(path: Path, content: str) -> None:
    """Publish a complete immutable file without overwriting an existing one."""
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".memory-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _replace_atomically(path: Path, content: str) -> None:
    """Replace a mutable policy file with a complete file in one operation."""
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".policy-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
