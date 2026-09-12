# Provenance agent design

This document summarizes the Provenance agent design described in
[`src/linger/agents/provenance/README.md`](../../src/linger/agents/provenance/README.md).
It is the navigation page for the detailed implementation records:

- [4.2.1 reflection and grounding](../implementation/provenance-4.2.1.md)
- [4.2.2 reviewed automatic capture and curation](../implementation/provenance-4.2.2.md)

The implementation records retain historical analysis and evaluation proposals.
This page describes the current architecture; current code and maintained
evaluation documentation take precedence over older gap descriptions.

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

## One Agent with three assigned skills

[`agent.py`](../../src/linger/agents/provenance/agent.py) constructs one reusable
production `provenance_agent`. Application code selects a skill from
[`skills.py`](../../src/linger/agents/provenance/skills.py) before each model run.
An Agent object is reusable configuration. A model run processes one selected
task and may include output-validation retries.

| Skill | Typed input | Typed output | Entry point |
|---|---|---|---|
| [Emotional preflight](../../src/linger/agents/provenance/skills/emotional-preflight/SKILL.md) | `EmotionalBoundaryInput` | `EmotionalBoundaryAssessment` | `assess_emotional_boundary` |
| [Candidate review](../../src/linger/agents/provenance/skills/candidate-review/SKILL.md) | `ProvenanceInput` | `ProvenanceReview` | `reflection._review_candidate` |
| [Curation review](../../src/linger/agents/provenance/skills/curation-review/SKILL.md) | `CurationReviewInput` | `CurationProvenanceReview` | `review_curation` |

The base Agent contains only the role and trust policy in `agents.provenance`
in the [`prompt catalogue`](../../src/linger/prompts/prompt_catalog.yaml). Task
instructions are additive per-run instructions, so only the selected skill
reaches the model.
No task inherits another task's policy or output schema. Candidate review
allows two output retries; the other skills allow one. Output schemas retain
their Pydantic validators, and orchestration retains its deterministic checks.
No skill receives tools, PydanticAI dependencies, or conversation history.
Request inputs and evaluation overrides remain local to each run.

Package resources load without relying on the working directory. Fingerprints
identify effective shared and selected instructions, relevant schemas, declared
validation, and retry limits. Role and task tracing remain separate. See the
[common agent architecture](../agent-skills.md) for the assignment mechanism.

## Review call sites

The first two skills run during a conversation turn. Preflight may stop the
turn before Muse runs, and a Muse revision requires a second candidate review.
Curation review runs outside the conversation turn.

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

Application code selects an account-scoped pool of immutable memories. Sculptor
proposes one curation action using sources from that pool. The curation review
run receives only the complete proposal, its digest, and
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
or passage scope. Memory and opened-web records use a separate request-local
authority, including active-memory and visible-URL checks. They never become
book evidence. Image evidence has no implemented release contract.

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

The three skills, deterministic gates, and curation binding are implemented.
Chat consumes preflight and candidate review. The application curation loop
consumes curation review outside chat.

The [Provenance evaluation guide](../../evals/provenance/README.md) describes an
eight-case emotional pack and a 24-case candidate-review pack. Twelve candidate
cases cover release and twelve cover capture, including nominated memories that
Provenance vetoes. Saved reports remain evidence for their recorded provider
run and prompt fingerprint.

Synthetic capture expectations now represent nomination and independent
Provenance decisions. Replay grades review, exact binding, storage, record
preservation, and the supported capture retry behavior. These capabilities do
not establish new live-model results or adoption of a synthetic package.

Synthetic curation replay still calls `propose_curation`, not
`run_curation_loop`. It measures Sculptor proposal quality and source
preservation. A curation-review semantic pack and a full curation-loop synthetic
evaluation remain unimplemented targets. Historical submission PDFs and prior
reports retain their original evidence scope.

## Source of truth

Use the Provenance README for the current agent contract and this page for the
architecture overview. Use the evaluation guide for current runners and case
packs, and the two implementation records for historical findings and proposals.
Update maintained descriptions when an authority boundary or runtime contract
changes.
