# Memory Format Design

Status: **Deferred design; outside the current POC**

Progress: **Deferred.** No implementation work is planned for the current POC.

This document preserves a possible future durable-memory design. The current
POC exposes no memory-management interface and implements only reviewed
automatic capture. The canonical current scope is in
[`docs/specification.md`](../specification.md).

## 1. Design position

Linger adopts the public Anthropic Managed Agents memory pattern:

- an account-scoped memory store contains focused text documents;
- each live memory has a stable ID, path, current content, and content hash;
- create never overwrites an existing memory;
- update may change content or path and supports a content-hash precondition;
- every create, update, and delete produces an immutable memory version; and
- stores can be attached read-only when an agent does not require write access.

Anthropic documents these behaviours in
[Using agent memory](https://platform.claude.com/docs/en/managed-agents/memory).
Linger adopts the shape, not Anthropic's hosted service or identifiers.

### 1.1 Anthropic-to-Linger mapping

| Public Anthropic pattern | Linger schema decision |
|---|---|
| A scoped memory store holds focused text documents | One `memory_store` belongs to one trusted account scope |
| A memory has a stable identity and path | The live `memory` keeps one `memory_id` and service-generated `path` across corrections |
| Create does not silently replace an existing document | Create is no-overwrite and idempotent by operation |
| Updates can use the current content hash as a precondition | Correction and deletion require `if_content_sha256` |
| Mutations produce immutable versions | Each mutation appends a linked `memory_version` with a distinct `version_id` |
| Stores can be attached read-only | Agents receive a minimum read-only projection and propose mutations through typed tools |
| Different owners or lifecycles use separate stores | Generated summaries and relationships live in a separate derived store |

Linger makes two deliberate product-specific choices:

1. Muse and Sculptor do not receive direct filesystem write access. They submit
   typed proposals to the Memory & Policy Service, which applies account scope,
   consent, validation, idempotency, and concurrency rules.
2. Anthropic can retain versions after a live memory is deleted. Linger does
   not retain deleted user content: deletion removes live content, historical
   version content, derivations, and derived-index entries together. A
   content-free audit tombstone may remain only if an explicit product policy
   requires it.

## 2. System model

```text
Trusted account context
        ↓
MemoryStore
        ├── Live Memory A ──→ immutable versions A1, A2, A3
        ├── Live Memory B ──→ immutable version B1
        └── Derived store ──→ summaries and relationships
                                  citing source version IDs
```

The live memory is the current addressable object. Versions are the audit and
recovery history. A generated summary is never written into the canonical
user-authored memory.

## 3. Memory store

One canonical store belongs to one account scope. Shared or project memory must
use a different store rather than weakening the account boundary.

```json
{
  "schema_version": 1,
  "record_type": "memory_store",
  "store_id": "memstore_01K2...",
  "account_key": "sha256:7d13...",
  "name": "Personal reflections",
  "description": "User-approved reflections and preferences.",
  "status": "active",
  "created_at": "2026-08-13T10:00:00Z",
  "updated_at": "2026-08-13T10:00:00Z"
}
```

`status` is `active` or `archived`. Archiving is one-way and makes the store
read-only. The application derives `account_key`; no model may supply or change
it.

## 4. Live memory

The live memory keeps a stable `memory_id` across corrections. Its Markdown
body contains the exact current words.

```markdown
---
{
  "schema_version": 1,
  "record_type": "memory",
  "memory_id": "mem_8f32...",
  "store_id": "memstore_01K2...",
  "path": "/reflections/mem_8f32.md",
  "current_version_id": "memver_02D7...",
  "content_sha256": "8a3f...",
  "capture_type": "explicit",
  "source_event_id": "evt_01K2...",
  "idempotency_key": "sha256:1db4...",
  "evidence_ids": [
    "pg11-v01b38ea4-ch05-ln0974-0981"
  ],
  "provenance_refs": [
    {
      "source_type": "conversation_turn",
      "source_id": "turn_01K2..."
    }
  ],
  "created_at": "2026-08-13T10:30:00Z",
  "updated_at": "2026-08-13T11:15:00Z"
}
---
The Caterpillar scene helped me notice how unsettled I feel when people ask who I am.
```

### 4.1 Field contract

| Field | Meaning |
|---|---|
| `schema_version` | Exact supported format; unknown versions fail closed |
| `record_type` | Always `memory` for a live record |
| `memory_id` | Stable logical identity across every correction |
| `store_id` | Owning account-scoped store |
| `path` | Application-generated, normalized path unique inside the store |
| `current_version_id` | Immutable version containing the current snapshot |
| `content_sha256` | Hash of the exact current Markdown body |
| `capture_type` | `explicit`, `automatic`, or `correction` |
| `source_event_id` | Trusted application event that requested this state |
| `idempotency_key` | Deterministic retry key scoped to the account and operation |
| `evidence_ids` | Optional resolvable evidence supporting the saved reflection |
| `provenance_refs` | Minimal typed origins, never an unrestricted transcript copy |
| `created_at` | Server-generated creation time |
| `updated_at` | Creation time of the current version |

The content hash includes the exact UTF-8 body after LF normalization and one
terminal LF. Storage paths are application-generated; `..`, absolute host
paths, symbolic links, and model-supplied account components are rejected.

## 5. Immutable memory version

Every successful mutation appends a version. Updates do not receive a new
`memory_id`; they receive a new `version_id`.

```markdown
---
{
  "schema_version": 1,
  "record_type": "memory_version",
  "version_id": "memver_02D7...",
  "memory_id": "mem_8f32...",
  "store_id": "memstore_01K2...",
  "operation": "modified",
  "previous_version_id": "memver_01A9...",
  "path": "/reflections/mem_8f32.md",
  "content_sha256": "8a3f...",
  "capture_type": "correction",
  "source_event_id": "evt_01K3...",
  "idempotency_key": "sha256:9c20...",
  "evidence_ids": [
    "pg11-v01b38ea4-ch05-ln0974-0981"
  ],
  "provenance_refs": [
    {
      "source_type": "conversation_turn",
      "source_id": "turn_01K3..."
    }
  ],
  "created_at": "2026-08-13T11:15:00Z"
}
---
The Caterpillar scene helped me notice how unsettled I feel when people ask who I am.
```

`operation` is `created`, `modified`, or `deleted`. A created version has no
`previous_version_id`. Modified and deleted versions link to the immediately
preceding version, producing one linear history per memory. Linger does not
support branches in the first implementation.

A delete version records the operation and non-content audit fields while the
service removes all user content from the live record and version family. It
must not retain the deleted body or its generated summaries.

## 6. Mutation protocol

### 6.1 Create

Input:

```json
{
  "text": "The Caterpillar scene helped me notice...",
  "operation_id": "op_01K2...",
  "capture_type": "explicit",
  "evidence_ids": ["pg11-v01b38ea4-ch05-ln0974-0981"]
}
```

The service derives account scope, store, memory ID, path, hash, timestamps, and
idempotency key. Create never overwrites an existing path. An identical retry
returns the existing result; the same operation ID with different content is a
conflict.

### 6.2 Update or correction

Input:

```json
{
  "memory_id": "mem_8f32...",
  "text": "Corrected exact words.",
  "operation_id": "op_01K3...",
  "if_content_sha256": "previous-content-hash"
}
```

The update succeeds only when `if_content_sha256` matches the live record. A
mismatch returns a conflict so the caller can re-read and explicitly reconcile
the newer state. On success the service atomically appends the immutable version
and advances the live memory's `current_version_id`, content, hash, and
`updated_at`.

### 6.3 Delete

Delete requires the stable `memory_id` and current content-hash precondition.
It removes:

- the live memory;
- content in every historical version;
- generated derivations citing any removed version;
- vector, lexical, cache, and summary projections; and
- backups under Linger's control according to the published deletion policy.

Account mismatch returns the same not-found response as a missing memory.

## 7. Generated memory

Anthropic recommends separate stores when information has different owners,
access rules, or lifecycles. Linger therefore keeps generated summaries and
relationships in a derived store, separate from user-authored memory.

```json
{
  "schema_version": 1,
  "record_type": "memory_derivation",
  "derivation_id": "drv_31c9...",
  "store_id": "memstore_derived_01K2...",
  "derivation_type": "summary",
  "source_version_ids": ["memver_02D7..."],
  "content": "Identity questions prompted a personal reflection.",
  "content_sha256": "15bc...",
  "generator": {
    "agent": "sculptor",
    "model": "recorded-at-runtime",
    "prompt_version": "sculptor-memory-v1"
  },
  "created_at": "2026-08-13T11:30:00Z"
}
```

Initial derivation types are `summary`, `duplicate_link`, and `relationship`.
Every source version must resolve inside the same account. Generated text is
always labelled and is replaceable; the canonical live memory remains the
source for quotation and user review.

## 8. Agent-facing view

Agents receive a minimum read-only projection, not storage paths, account keys,
idempotency keys, superseded versions, or direct mutation authority:

```json
{
  "memory_id": "mem_8f32...",
  "version_id": "memver_02D7...",
  "text": "The Caterpillar scene helped me notice...",
  "summary": "Identity questions prompted a personal reflection.",
  "evidence_ids": ["pg11-v01b38ea4-ch05-ln0974-0981"],
  "related_memory_ids": [],
  "capture_type": "explicit",
  "created_at": "2026-08-13T10:30:00Z",
  "updated_at": "2026-08-13T11:15:00Z"
}
```

`summary` and `related_memory_ids` may be absent. Agents propose saves,
corrections, or deletion requests through typed tools; only the Memory & Policy
Service commits them.

## 9. Storage layout

```text
memories/
└── <hashed-account-key>/
    ├── policy.json
    ├── canonical-store.json
    ├── live/
    │   └── <memory-id>.md
    ├── versions/
    │   └── <memory-id>/
    │       └── <version-id>.md
    └── derived/
        └── <derivation-id>.json
```

Live records are replaceable only through an atomic service operation. Version
files are append-only until an authorized deletion or redaction removes their
content. Derived indexes remain disposable projections and never become the
source of truth.

## 10. Validation and access rules

Before any read or mutation, application code verifies:

- trusted account scope matches the hashed directory and store;
- every record has an exact supported schema and `record_type`;
- IDs, paths, timestamps, operations, and hashes have valid formats;
- the live hash, body, and `current_version_id` agree;
- version history is linear, ordered, same-account, and cycle-free;
- mutation preconditions match the current live hash;
- evidence and provenance references use known typed formats;
- every derivation source resolves to the same account; and
- a model-supplied identifier never grants access by itself.

Corrupt records fail closed. Telemetry may record opaque IDs, operations, and
error classes, but never raw memory bodies.

## 11. Current implementation gap

`src/linger/services/memory.py` already provides hashed account directories,
explicit and policy-gated automatic capture, idempotent writes, corrections,
account isolation, and cascading family deletion.

It does not yet implement this adopted target contract. The implementation must
replace the current per-version `memory_id` model with:

- one stable live `memory_id` and a distinct immutable `version_id`;
- a live record pointing to `current_version_id`;
- exact `record_type`, hash, path, and provenance validation;
- content-hash preconditions for correction and deletion;
- separate version and derivation storage; and
- the minimum read-only agent projection.

This is a Memory & Policy Service implementation task. It does not belong to
Librarian, Muse, or the corpus processor.
