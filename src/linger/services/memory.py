"""Account-scoped Markdown memory storage and deterministic capture policy."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from src.linger.agents.sculptor.models import (
    DerivedSummary,
    DuplicateLink,
    RetrievalRestore,
    RetrievalTombstone,
    TopicGroup,
)
from src.linger.contracts.curation import (
    AppliedCuration,
    ApprovedCuration,
    CuratedMemory,
    CurationApplyResult,
    CurationVerification,
    canonical_digest,
)

CaptureType = Literal["automatic"]


class MemoryServiceError(Exception):
    """Base class for deterministic memory service failures."""


class MemoryConflictError(MemoryServiceError):
    """Raised when one source event is reused for different memory content."""


class MemoryPolicyError(MemoryServiceError):
    """Raised when an automatic capture fails deterministic policy."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class MemoryStorageError(MemoryServiceError):
    """Raised when a stored memory cannot be parsed or validated."""


class CurationPolicyError(MemoryServiceError):
    """Raised when reviewed curation fails deterministic application policy."""


class CurationConflictError(MemoryServiceError):
    """Raised when an immutable curation event conflicts with an existing event."""


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
    """One immutable automatic capture."""

    memory_id: str
    account_key: str
    text: str
    capture_type: CaptureType
    source_event_id: str
    idempotency_key: str
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
        """Persist server-controlled capture policy for one evaluation account."""
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
                raise MemoryPolicyError("sensitive_content_not_allowed")
            return self._save(
                context,
                text=candidate.text,
                source_event_id=candidate.source_event_id,
                evidence_ids=candidate.evidence_ids,
            )

    def list_active(self, context: AccountContext) -> list[MemoryRecord]:
        """List immutable automatic captures owned by this account."""
        with self._lock:
            records = self._records_by_id(context)
            return sorted(
                records.values(),
                key=lambda record: (record.created_at, record.memory_id),
            )

    def select_for_curation(
        self,
        context: AccountContext,
        memory_ids: tuple[str, ...],
    ) -> tuple[MemoryRecord, ...]:
        """Resolve one bounded, ordered, account-scoped set of originals."""

        if not 2 <= len(memory_ids) <= 12:
            raise CurationPolicyError("curation_requires_2_to_12_memories")
        if len(memory_ids) != len(set(memory_ids)):
            raise CurationPolicyError("curation_memory_ids_must_be_unique")
        with self._lock:
            records = self._records_by_id(context)
            missing = tuple(memory_id for memory_id in memory_ids if memory_id not in records)
            if missing:
                raise CurationPolicyError("curation_source_not_found")
            return tuple(records[memory_id] for memory_id in memory_ids)

    def apply_curation(
        self,
        context: AccountContext,
        approved: ApprovedCuration,
    ) -> CurationApplyResult:
        """Atomically append one reviewed, narrowly typed curation event."""

        with self._lock:
            self._validate_approved_sources(context, approved)
            curation_dir = self._ensure_curation_dir(context)
            current_events = self._curation_events(context)
            event_id = f"cur_{approved.plan.digest}"
            event_path = curation_dir / f"{event_id}.json"
            if event_path.exists():
                existing = _read_curation_event(event_path)
                self._require_matching_curation_retry(existing, approved)
                verification = self.verify_curation(context, approved.plan.digest)
                return CurationApplyResult(
                    event=existing,
                    created=False,
                    verification=verification,
                )

            if (
                _curation_state_sha256(current_events)
                != approved.plan.base_state_sha256
            ):
                raise CurationPolicyError("curation_state_stale")
            self._validate_action_state(approved, current_events)
            event = AppliedCuration(
                event_id=event_id,
                account_key=approved.plan.account_key,
                base_state_sha256=approved.plan.base_state_sha256,
                proposal_digest=approved.plan.digest,
                provenance_review_digest=approved.review_digest,
                provenance_review=approved.review,
                proposal=approved.plan.proposal,
                source_snapshots=approved.plan.source_snapshots,
                applied_at=datetime.now(UTC).isoformat(),
            )
            try:
                _create_atomically(
                    event_path,
                    event.model_dump_json(indent=2) + "\n",
                )
                created = True
            except FileExistsError:
                event = _read_curation_event(event_path)
                self._require_matching_curation_retry(event, approved)
                created = False

            verification = self.verify_curation(context, approved.plan.digest)
            if not verification.verified:
                raise MemoryStorageError("persisted curation event failed verification")
            return CurationApplyResult(
                event=event,
                created=created,
                verification=verification,
            )

    def verify_curation(
        self,
        context: AccountContext,
        proposal_digest: str,
    ) -> CurationVerification:
        """Verify an audit event and its immutable source snapshots."""

        event_id = f"cur_{proposal_digest}"
        with self._lock:
            path = self._curation_dir(context) / f"{event_id}.json"
            if not path.exists():
                return CurationVerification(
                    event_id=event_id,
                    verified=False,
                    failures=("curation_event_not_found",),
                )
            event = _read_curation_event(path)
            failures: list[str] = []
            if event.account_key != _account_key(context.account_id):
                failures.append("curation_event_account_mismatch")
            if event.proposal_digest != proposal_digest:
                failures.append("curation_event_digest_mismatch")
            records = self._records_by_id(context)
            for snapshot in event.source_snapshots:
                record = records.get(snapshot.memory_id)
                if record is None:
                    failures.append(f"missing_source:{snapshot.memory_id}")
                elif memory_record_sha256(record) != snapshot.record_sha256:
                    failures.append(f"stale_source:{snapshot.memory_id}")
            return CurationVerification(
                event_id=event_id,
                verified=not failures,
                failures=tuple(failures),
            )

    def list_curation_audit(
        self,
        context: AccountContext,
    ) -> tuple[AppliedCuration, ...]:
        """Return immutable curation events in their application order."""

        with self._lock:
            return self._curation_events(context)

    def curation_state_sha256(self, context: AccountContext) -> str:
        """Return the immutable identity of the current ordered curation state."""

        with self._lock:
            return _curation_state_sha256(self._curation_events(context))

    def list_for_retrieval(self, context: AccountContext) -> list[CuratedMemory]:
        """Materialize the account's retrieval view from originals and events."""

        with self._lock:
            records = self._records_by_id(context)
            events = self._curation_events(context)
            state = _materialize_curation(events)
            return _retrieval_view(records, state)

    def _save(
        self,
        context: AccountContext,
        *,
        text: str,
        source_event_id: str,
        evidence_ids: tuple[str, ...],
    ) -> SaveResult:
        _require_text(text, "text")
        _require_text(source_event_id, "source_event_id")
        with self._lock:
            idempotency_key = _idempotency_key(
                context.account_id,
                source_event_id,
            )
            existing = self._existing_idempotent(context, idempotency_key)
            if existing is not None:
                self._require_matching_retry(
                    existing,
                    text=text,
                    source_event_id=source_event_id,
                    evidence_ids=evidence_ids,
                )
                return SaveResult(record=existing, created=False)

            record = _new_record(
                account_key=_account_key(context.account_id),
                text=text,
                source_event_id=source_event_id,
                idempotency_key=idempotency_key,
                evidence_ids=evidence_ids,
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
                evidence_ids=record.evidence_ids,
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
        evidence_ids: tuple[str, ...],
    ) -> None:
        expected = (
            text,
            source_event_id,
            evidence_ids,
        )
        actual = (
            record.text,
            record.source_event_id,
            record.evidence_ids,
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

    def _curation_dir(self, context: AccountContext) -> Path:
        return self._account_dir(context) / "curation"

    def _ensure_curation_dir(self, context: AccountContext) -> Path:
        curation_dir = self._ensure_account_dir(context) / "curation"
        curation_dir.mkdir(mode=0o700, exist_ok=True)
        return curation_dir

    def _curation_events(
        self,
        context: AccountContext,
    ) -> tuple[AppliedCuration, ...]:
        curation_dir = self._curation_dir(context)
        if not curation_dir.exists():
            return ()
        events = tuple(
            _read_curation_event(path) for path in curation_dir.glob("cur_*.json")
        )
        return tuple(sorted(events, key=lambda item: (item.applied_at, item.event_id)))

    def _validate_approved_sources(
        self,
        context: AccountContext,
        approved: ApprovedCuration,
    ) -> None:
        expected_account_key = _account_key(context.account_id)
        if approved.plan.account_key != expected_account_key:
            raise CurationPolicyError("curation_account_scope_mismatch")
        records = self._records_by_id(context)
        for snapshot in approved.plan.source_snapshots:
            record = records.get(snapshot.memory_id)
            if record is None:
                raise CurationPolicyError("curation_source_not_found")
            if memory_record_sha256(record) != snapshot.record_sha256:
                raise CurationPolicyError("curation_source_stale")

    def _validate_action_state(
        self,
        approved: ApprovedCuration,
        current_events: tuple[AppliedCuration, ...],
    ) -> None:
        action = approved.plan.proposal.action
        state = _materialize_curation(current_events)
        if isinstance(action, RetrievalTombstone):
            linked = state.duplicate_links.get(action.memory_id, set())
            if action.canonical_memory_id not in linked:
                raise CurationPolicyError("tombstone_requires_duplicate_link")
            if action.memory_id in state.tombstones:
                raise CurationPolicyError("memory_already_tombstoned")
        elif isinstance(action, RetrievalRestore):
            if action.memory_id not in state.tombstones:
                raise CurationPolicyError("memory_is_not_tombstoned")

    def _require_matching_curation_retry(
        self,
        event: AppliedCuration,
        approved: ApprovedCuration,
    ) -> None:
        expected = (
            approved.plan.account_key,
            approved.plan.base_state_sha256,
            approved.plan.digest,
            approved.review_digest,
            approved.review,
            approved.plan.proposal,
            approved.plan.source_snapshots,
        )
        actual = (
            event.account_key,
            event.base_state_sha256,
            event.proposal_digest,
            event.provenance_review_digest,
            event.provenance_review,
            event.proposal,
            event.source_snapshots,
        )
        if actual != expected:
            raise CurationConflictError("curation proposal digest already exists")


@dataclass
class _CuratedState:
    duplicate_links: dict[str, set[str]]
    summaries: dict[tuple[str, ...], AppliedCuration]
    topics: dict[tuple[str, ...], AppliedCuration]
    tombstones: dict[str, str]


def memory_record_sha256(record: MemoryRecord) -> str:
    """Hash every immutable field of one original memory record."""

    return canonical_digest(
        {
            "memory_id": record.memory_id,
            "account_key": record.account_key,
            "text": record.text,
            "capture_type": record.capture_type,
            "source_event_id": record.source_event_id,
            "idempotency_key": record.idempotency_key,
            "evidence_ids": record.evidence_ids,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }
    )


def _curation_state_sha256(events: tuple[AppliedCuration, ...]) -> str:
    return canonical_digest(
        [event.model_dump(mode="json") for event in events]
    )


def _materialize_curation(events: tuple[AppliedCuration, ...]) -> _CuratedState:
    duplicate_links: defaultdict[str, set[str]] = defaultdict(set)
    summaries: dict[tuple[str, ...], AppliedCuration] = {}
    topics: dict[tuple[str, ...], AppliedCuration] = {}
    tombstones: dict[str, str] = {}
    for event in events:
        action = event.proposal.action
        source_key = tuple(sorted(action.source_memory_ids))
        if isinstance(action, DuplicateLink):
            for memory_id in action.source_memory_ids:
                duplicate_links[memory_id].update(
                    source_id
                    for source_id in action.source_memory_ids
                    if source_id != memory_id
                )
        elif isinstance(action, DerivedSummary):
            summaries[source_key] = event
        elif isinstance(action, TopicGroup):
            topics[source_key] = event
        elif isinstance(action, RetrievalTombstone):
            tombstones[action.memory_id] = action.canonical_memory_id
        elif isinstance(action, RetrievalRestore):
            tombstones.pop(action.memory_id, None)
    return _CuratedState(
        duplicate_links=dict(duplicate_links),
        summaries=summaries,
        topics=topics,
        tombstones=tombstones,
    )


def _retrieval_view(
    records: dict[str, MemoryRecord],
    state: _CuratedState,
) -> list[CuratedMemory]:
    items: list[CuratedMemory] = []

    def labels_for(source_ids: tuple[str, ...]) -> tuple[str, ...]:
        labels = {
            event.proposal.action.topic_label
            for source_key, event in state.topics.items()
            if set(source_key).intersection(source_ids)
            and isinstance(event.proposal.action, TopicGroup)
        }
        return tuple(sorted(labels))

    def evidence_for(source_ids: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    evidence_id
                    for source_id in source_ids
                    if source_id in records
                    for evidence_id in records[source_id].evidence_ids
                }
            )
        )

    for record in records.values():
        if record.memory_id in state.tombstones:
            continue
        items.append(
            CuratedMemory(
                memory_id=record.memory_id,
                kind="original",
                text=record.text,
                source_memory_ids=(record.memory_id,),
                evidence_ids=record.evidence_ids,
                duplicate_memory_ids=tuple(
                    sorted(state.duplicate_links.get(record.memory_id, set()))
                ),
                topic_labels=labels_for((record.memory_id,)),
                created_at=record.created_at,
            )
        )

    for event in state.summaries.values():
        action = event.proposal.action
        if not isinstance(action, DerivedSummary):
            continue
        if all(source_id in state.tombstones for source_id in action.source_memory_ids):
            continue
        items.append(
            CuratedMemory(
                memory_id=f"summary_{event.proposal_digest}",
                kind="derived_summary",
                text=action.summary,
                source_memory_ids=action.source_memory_ids,
                evidence_ids=evidence_for(action.source_memory_ids),
                topic_labels=labels_for(action.source_memory_ids),
                created_at=event.applied_at,
            )
        )

    for event in state.topics.values():
        action = event.proposal.action
        if not isinstance(action, TopicGroup):
            continue
        if all(source_id in state.tombstones for source_id in action.source_memory_ids):
            continue
        items.append(
            CuratedMemory(
                memory_id=f"topic_{event.proposal_digest}",
                kind="topic_group",
                text=action.topic_label,
                source_memory_ids=action.source_memory_ids,
                evidence_ids=evidence_for(action.source_memory_ids),
                topic_labels=(action.topic_label,),
                created_at=event.applied_at,
            )
        )

    return sorted(items, key=lambda item: (item.created_at, item.memory_id))


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must not be blank")


def _account_key(account_id: str) -> str:
    return hashlib.sha256(account_id.encode("utf-8")).hexdigest()


def _idempotency_key(
    account_id: str,
    source_event_id: str,
) -> str:
    material = "\0".join((account_id, source_event_id, "automatic"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _memory_id(idempotency_key: str) -> str:
    return f"mem_{idempotency_key}"


def _new_record(
    *,
    account_key: str,
    text: str,
    source_event_id: str,
    idempotency_key: str,
    evidence_ids: tuple[str, ...],
) -> MemoryRecord:
    timestamp = datetime.now(UTC).isoformat()
    return MemoryRecord(
        memory_id=_memory_id(idempotency_key),
        account_key=account_key,
        text=text,
        capture_type="automatic",
        source_event_id=source_event_id,
        idempotency_key=idempotency_key,
        evidence_ids=tuple(evidence_ids),
        created_at=timestamp,
        updated_at=timestamp,
    )


def _serialize(record: MemoryRecord) -> str:
    metadata = {
        "schema_version": 1,
        "memory_id": record.memory_id,
        "account_key": record.account_key,
        "capture_type": record.capture_type,
        "source_event_id": record.source_event_id,
        "idempotency_key": record.idempotency_key,
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
        if metadata.get("capture_type") != "automatic":
            raise ValueError("invalid capture type")
        record = MemoryRecord(
            memory_id=metadata["memory_id"],
            account_key=metadata["account_key"],
            text=text.removesuffix("\n"),
            capture_type=metadata["capture_type"],
            source_event_id=metadata["source_event_id"],
            idempotency_key=metadata["idempotency_key"],
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


def _read_curation_event(path: Path) -> AppliedCuration:
    try:
        event = AppliedCuration.model_validate_json(path.read_text(encoding="utf-8"))
        if path.name != f"{event.event_id}.json":
            raise ValueError("curation event filename does not match its ID")
        if path.parent.parent.name != event.account_key:
            raise ValueError("curation event account does not match its directory")
        if event.event_id != f"cur_{event.proposal_digest}":
            raise ValueError("curation event ID does not match its proposal")
        return event
    except (OSError, ValueError, ValidationError) as exc:
        raise MemoryStorageError(f"Invalid curation event: {path}") from exc


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
