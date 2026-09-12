# Provenance agent design

This document summarizes the Provenance agent design described in
[`src/linger/agents/provenance/README.md`](../../src/linger/agents/provenance/README.md).
It is the navigation page for the detailed implementation records:

- [4.2.1 reflection and grounding](../implementation/provenance-4.2.1.md)
- [4.2.2 reviewed automatic capture and curation](../implementation/provenance-4.2.2.md)

The implementation records contain the historical analysis, evaluation gaps,
open questions, and TODO items. This page describes the current architecture.

## Role and authority

Provenance is a no-tool semantic review agent. The application gives it a
request-scoped review input and validates its typed output. The agent does not
release a response, save a memory, apply a curation action, or select evidence.

The application owns the final decisions:

| Area | Provenance provides | Application provides |
|---|---|---|
| Response release | `response_decision` and findings | Revision, rejection, evidence checks, and release |
| Automatic capture | `capture_decision` and capture findings | Candidate extraction, capture policy, and storage |
| Curation | `allow`, `revise`, or `reject` for one proposal | Digest binding, source revalidation, policy checks, apply, and audit |

The Memory & Policy Service is the only component that commits memory or
curation state. A Provenance approval is necessary but never sufficient for a
write. Missing, malformed, stale, or incorrectly bound reviews fail closed.

## Review call sites

Provenance has three call sites. The first two run during a conversation turn.
The third runs in the curation workflow outside the conversation turn.

### Emotional-boundary preflight

The application reviews the current Line before Muse runs. If the Line crosses
the emotional boundary, the application returns the canonical boundary response
and records that Muse did not run. A safe Line continues to Muse.

This preflight is application-owned. Provenance does not invent the boundary
response and does not claim that Muse reviewed a Line it never received.

### Candidate release review

Muse proposes a response and may nominate one exact span of the current Line as
a memory candidate. Provenance reviews the complete candidate and returns two
independent decisions:

- `response_decision`: `pass`, `revise`, or `reject`.
- `capture_decision`: `allow_capture`, `reject_capture`, or `no_candidate`.

The response decision controls the release loop. A revision sends the revised
candidate through review again. A capture veto never changes the user-facing
response. Conversely, an application-owned safe decline or emotional-boundary
response can suppress capture even when Provenance allows it.

Provenance findings use the closed `RiskCode` taxonomy. Findings identify the
affected object, use exact evidence spans where required, and cannot cite
capture evidence against the response. `contains_sensitive_content` is derived
from capture findings, so callers cannot set it inconsistently.

### Curation review

Sculptor selects source memories and proposes one curation action. The separate
curation Provenance call receives only the complete proposal, its digest, and
the exact immutable source snapshots named by the proposal. Source text is
untrusted data, not instructions.

The curation reviewer returns `allow`, `revise`, or `reject` and echoes the
proposal digest. An allowed review has no findings. A revised or rejected review
has at least one typed finding. Findings use the separate closed
`CurationRiskCode` taxonomy:

| Code | Meaning |
|---|---|
| `unsupported_derivation` | A derived summary is not supported by its sources or drops their uncertainty. |
| `incorrect_duplicate` | A proposed duplicate link joins different durable memories. |
| `incoherent_topic` | A proposed topic grouping is unrelated or unsupported. |
| `unsafe_tombstone` | A proposed tombstone would hide distinct content. |
| `invalid_restore` | A proposed restore is inconsistent with the supplied evidence. |
| `prompt_injection` | Memory text attempts to redirect the review or action. |

The curation loop re-reads and re-hashes sources after agent calls. It rejects
stale, unknown, cross-account, changed, or structurally invalid sources. The
Memory & Policy Service then checks action preconditions, applies an allowed
proposal, preserves originals, and appends the audit event.

## Evidence and binding

For book-grounded responses, deterministic application code resolves every
declared evidence ID against a request-scoped index. It checks exact quotations,
source locations, trusted work and version, and the applicable chapter ceiling
or passage scope. Book records from memory, web, or image evidence cannot enter
the book citation authority.

For curation, the digest chain binds account scope, the ordered curation-state
digest, the complete action, and source-record hashes. The review must echo the
proposal digest. The approval contract rejects a non-`allow` verdict or a
digest mismatch. The audit contract rebuilds the plan and verifies its digest.

These checks bind a verdict to the object and state that were reviewed. They do
not turn Provenance into a writer or a release authority.

## Component boundaries

| Component | Responsibility | Authority limit |
|---|---|---|
| Muse | Draft the response and nominate a memory span | Cannot release or store |
| Provenance | Review response, capture, and curation semantics | Cannot release or write |
| Librarian | Provide canonical book evidence | Cannot approve a response |
| Sculptor | Propose bounded memory curation | Cannot apply a proposal |
| Serendipity | Propose connection evidence | Cannot release a connection |
| Memory & Policy Service | Enforce deterministic memory and curation policy | Does not author semantic verdicts |
| Application orchestration | Run review loops and release approved outputs | Must preserve each authority boundary |

## Implementation and evaluation status

The runtime contracts, prompts, deterministic gates, and curation binding are
implemented. The detailed records describe the remaining evaluation work.

The 4.2.1 record covers reflection and grounding behavior, risk-code evaluation,
synthetic-journal package design, and the book-evidence boundary.

The 4.2.2 record covers two implemented Provenance gates. Capture still needs
live-model measurement that reaches the capture axis. Its existing risk-code
cases structurally disable capture, and its Ground truth vocabulary cannot yet
express a nominated candidate that Provenance vetoes. Curation still needs a
synthetic runner that calls `run_curation_loop` instead of grading Sculptor's
proposal directly. None of the six curation risk codes has curation-gate
live-model evidence. Generate replacement packages only after the runner and
expectation contract represent the shipped flow.

## Source of truth

Use the Provenance README for the current agent contract and this page for the
architecture overview. Use the two implementation records for detailed
findings and planned evaluation work. Update all three when an authority
boundary or runtime contract changes.
