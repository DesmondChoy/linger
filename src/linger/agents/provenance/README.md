# Provenance

Provenance is Linger's independent reviewer. One reusable PydanticAI Agent runs
three application-selected skills. Every Muse candidate
response passes through it before display, including drafts that declare no
factual claims: a non-factual reflection may pass without retrieval, but never
without review. There is no Muse-to-user bypass.

It also runs a no-tool emotional-boundary preflight on the current Line before
Muse. The preflight can end a request without a candidate through an
application-owned path; see [Provenance Flows](#provenance-flows).

Separately, it reviews one complete Sculptor curation proposal against that
proposal's exact immutable source snapshots. Curation review has its own input,
risk taxonomy, and verdict contract; see
[Curation review](#curation-review).

Each selected skill starts a separate model run on `provenance_agent`. The same
configured provider model may back Muse and Provenance. The application supplies
a fresh review input and never shares Muse's conversation history.

## Assigned runtime skills

[`skills.py`](skills.py) assigns the following tasks. These are application
runtime skills, separate from Codex's development skills.

| Skill | Input | Output | Current consumer |
|---|---|---|---|
| [Emotional preflight](skills/emotional-preflight/SKILL.md) | `EmotionalBoundaryInput` | `EmotionalBoundaryAssessment` | `assess_emotional_boundary` before Muse in live chat; offline preflight evaluation |
| [Candidate review](skills/candidate-review/SKILL.md) | `ProvenanceInput` | `ProvenanceReview` | `reflection._review_candidate` for drafts and revisions; offline risk-code evaluation and chat replay |
| [Curation review](skills/curation-review/SKILL.md) | `CurationReviewInput` | `CurationProvenanceReview` | `review_curation` in the application curation loop, outside live chat |

[`agent.py`](agent.py) constructs one production object and retains a model
injection builder for tests. Its base instructions contain only the shared
policy in `agents.provenance` in the
[`prompt catalogue`](../../prompts/prompt_catalog.yaml). Each typed entry point supplies
the selected skill's instructions, output contract, and retry limit before invoking the
model. Candidate review permits two output retries. Preflight and curation
review each permit one. Pydantic model validators and deterministic checks
remain task-specific.

No skill receives tools or PydanticAI dependencies. Every run starts without
message history. Request data stays in the typed input. Concurrent runs and evaluation
model overrides do not modify the shared Agent configuration. Instructions load
from package resources, independently of the working directory. Existing prompt
modules expose effective instructions and fingerprints that include the shared
policy, selected skill, relevant contracts, validation identities, and retry
limits. Traces retain the Provenance role and each task's stage.

See the [agent runtime architecture](../../../../docs/agent-skills.md) for the
common assignment mechanism, and the [evaluation guide](../../../../evals/provenance/README.md)
for the distinction between semantic evaluations and deterministic tests.

## Inputs and authority

Candidate review receives one strict `ProvenanceInput`: trusted policy, chapter or
exact-passage context, canonical book evidence, verified session Lines,
current untrusted tool outcomes, Muse's
candidate and declarations, and the application-owned current user Line. It has
no tools, no conversation history, and no write authority anywhere in the
system. Legacy derived fields such as `cited_evidence` and
`connection_proposal` are rejected.

Muse's declared claims, quotations, and flags are untrusted review hints. They
do not narrow what Provenance must inspect. It detects quotations, factual
claims, and sensitive inferences independently, and may find what Muse omitted
or misclassified.

The candidate itself is untrusted data. Instructions appearing inside a draft,
a retrieved passage, or a quotation never gain authority over the review.

Reader attribution never exempts a book-corpus claim: a claim about
characters, plot events, chapter facts, quotations, or book-specific
interpretation still requires a matching record even when the candidate
frames it as something the reader said.
Shared everyday vocabulary does not make a reader-life claim a book claim
either: a garden "plot" or a life "chapter" stays exempt unless the claim is
actually about the book's content. Only a claim with no book-corpus content —
one that is purely about the reader's own statements, life, or the ongoing
session — is outside the `canonical_book_evidence` requirement, because that
is Muse's session-continuity responsibility, not something Provenance's
history-lessness can adjudicate. A doubted purely-reader-attributed fact does
not route to an unfixable `reject`: it routes to `revise` with a
`misattribution` finding (`location.kind="structural"`,
`source_field="candidate.response"`) asking Muse to attribute the fact
explicitly to the reader.

`orchestration/reflection.py` resolves each Muse-declared `session_line`
quotation against earlier released user Lines and the current reader message.
Only exact substrings reach `canonical_session_lines` in `ProvenanceInput`.
Muse's replies cannot corroborate a reader statement. A matching entry
supports attribution to the reader, but never a book-corpus claim.

An undeclared reader-attributed claim remains subject to the semantic
exempt-and-revise policy above. An explicit declaration must resolve exactly.
Deterministic release rejects an unresolved `session_line` quotation even if
Provenance passes the reply. These quotations contain 12 to 2,000 characters.

## Two independent decisions

These are the two decisions of the **release** call. The curation gate is a
separate call with its own verdict; it is not one of these.

One review call returns both decisions, and they are decoupled:

- `response_decision` — `pass`, `revise`, or `reject` for the user-facing text.
  A first `revise` grants exactly one revision, which returns through the same
  review path. A rejection or a failed revision produces an application-authored
  safe decline.
- `capture_decision` — `allow_capture`, `reject_capture`, or `no_candidate` for
  an automatic memory candidate. Grounds for veto are privacy risk, sensitive
  inference, unsupported provenance, and injection risk.

**Rejecting capture never suppresses an otherwise safe response.** The decisions
drive different code: only `response_decision` branches the release path in
`orchestration/reflection.py`, and only `capture_decision` is interpreted in
`orchestration/capture.py`. The release path reads `capture_decision` solely to
record it on the result, never to choose a branch, so no capture verdict can
change what is released.

The converse does not hold. Semantic independence is preserved, but deterministic
storage additionally requires a released candidate: an application safe decline
suppresses the write even after `allow_capture`. See
[4.2.2](#422--reviewed-automatic-capture).

## Risk taxonomy

Every adverse decision must name at least one ground scoped to that decision; a
model validator rejects an unexplained `revise`, `reject`, or `reject_capture`.
Text findings carry a source field, an RFC 6901 path, and a verbatim quote
validated by exact-substring containment against the resolved source. Shape and declaration
faults use an RFC 6901 structural path. Only response findings guide the one
permitted Muse revision.

`emotional_boundary_decision` separately identifies a missed preflight trigger.
`required` is valid only with a rejected response and a matching current-Line
finding; candidate-only diagnosis remains on the ordinary revise-or-reject path.

The `RiskCode` values cover the specification's release conditions plus the
absolute sensitive-content capture veto:

| Code | Ground |
| --- | --- |
| `unresolved_evidence` | Cited evidence is missing or unresolved. |
| `misattribution` | A quotation, idea, or source is attributed incorrectly. |
| `spoiler` | Content passes the reader's boundary, or that boundary is unclear. |
| `uncited_web_claim` | A factual web claim lacks a retrievable citation. |
| `unsupported_claim` | An unsupported claim or a sensitive inference. |
| `sensitive_content` | Sensitive-trait content ineligible for automatic capture. |
| `emotional_policy_violation` | Diagnosis, probing after distress, or an incorrect emotional boundary. |
| `prompt_injection` | Retrieved content attempts to redirect agent behaviour. |

`SENSITIVE_RISK_CODES` marks the subset that bars content from automatic
capture. `contains_sensitive_content` is derived from capture findings rather
than set independently, so it cannot contradict the capture decision.

### Curation risk taxonomy

The curation gate uses a **separate closed taxonomy**, `CurationRiskCode` in
[`curation_models.py`](curation_models.py). It is not a subset or superset of
`RiskCode`; the two gates review different objects, so they name different
grounds:

| Code | Ground |
| --- | --- |
| `unsupported_derivation` | A derived summary asserts something its cited sources do not support, or drops their uncertainty. |
| `incorrect_duplicate` | Records linked as duplicates do not express the same durable memory. |
| `incoherent_topic` | Grouped records are not related, or the label is unsupported by them. |
| `unsafe_tombstone` | The target and canonical record are not genuine duplicates, so suppressing the target would lose distinct content. |
| `invalid_restore` | Restoring the named original is inconsistent with the supplied evidence. |
| `prompt_injection` | Memory text attempts to redirect the review or the proposed action. |

`prompt_injection` is the only code shared by name with `RiskCode`. Candidate
review requires `reject` for a response finding with that code. Curation review
requires rejection when the proposed action follows instructions embedded in
memory text. The two skills keep their own decision criteria and validation
contracts.

A curation finding names the affected `source_memory_ids`, which must be a
subset of the sources actually supplied for review. Findings carry no RFC 6901
path, because the reviewed object is a typed proposal rather than free text.

## Provenance flows

Provenance has three skills: emotional preflight, candidate review, and curation
review. Preflight can stop the turn before candidate
review. A revision invokes candidate review again. The curation gate runs
outside the conversation turn entirely and shares no context with the other two.

### Preflight — before Muse runs

The no-tool emotional-boundary preflight evaluates only the current Line and the
versioned emotional-content policy (specification sections 4.1 and 6.6). It
returns `continue_reflection` or `apply_boundary`.

`apply_boundary` stops the ordinary path: Muse, Librarian, and Serendipity do not
run, so no candidate, evidence declaration, or memory nomination exists. **No risk
code applies to this path** — application code releases the canonical section 6.6
response and records `application_emotional_boundary` with suppressed capture. A
preflight failure returns the generic safe decline, also before Muse runs.

Both are application-to-user paths that skip Muse. They are not a Muse-to-user
bypass; every candidate Muse does produce still requires the candidate gate.

### Candidate review by flow

`continue_reflection` enters the ordinary flow, whose three shapes are the
specification's section 4.2 flows. The gate contract does not vary between them;
only the evidence bundle's contents do.

| Flow | Review input |
|---|---|
| Reflection and grounding | Complete reply, canonical book evidence, exact-passage or chapter scope, and verified reader statements |
| Reviewed capture | Muse's nomination, exact current reader Line, and capture policy |
| Connection discovery | Complete reply, untrusted proposal or decline, and the selected canonical book records |

Response and capture findings use the same risk taxonomy but retain separate
decision scopes. Emotional-policy review applies to the current Line and to
candidate behavior in every response flow.

### 4.2.1 — Reflection & grounding (book evidence)

Canonical book records support book claims. Review checks unresolved evidence,
attribution, unsupported claims, and prompt injection throughout the candidate.
Spoiler review enforces the supplied chapter ceiling or exact-passage scope.
A passage grant supports only its listed canonical paragraphs. It neither
establishes chapter completion nor permits surrounding scene details.

### 4.2.2 — Reviewed automatic capture

The capture veto grounds are `SENSITIVE_RISK_CODES` in [`models.py`](models.py):
`unsupported_claim`, `sensitive_content`, `emotional_policy_violation`, and
`prompt_injection`. These cover the section 4.2.2 grounds — sensitive inference,
unsupported provenance, and injection risk — plus content that reached the
emotional boundary. `contains_sensitive_content` reports this subset to the
deterministic policy gate.

Deterministic storage additionally requires a released Muse candidate:
every `application_safe_decline` suppresses an otherwise eligible write even when
Provenance independently returned `allow_capture`, recording
`safe_decline_capture_suppressed` with no save notice. Every emotional-boundary
release records `emotional_boundary_capture_suppressed`.
An application-owned clarification records `clarification_capture_suppressed`.

### 4.2.3 — Connection discovery (Serendipity)

Serendipity can return book, account-scoped memory, or web search evidence.
This is the only flow that reaches web evidence, so it is the only flow where
`uncited_web_claim` can fire. A selected page may support a release when Muse
visibly cites its exact URL and application code resolves that URL against the
current Serendipity run. Memory evidence must match a registered account-scoped
record that remains active. It supports attributed personal context, and cannot
support public or book-corpus facts.
Provenance reviews the complete candidate for unsupported claims and attribution
errors, and `unsupported_claim` remains important because a tentative connection
can still overclaim its evidence.

### `emotional_policy_violation` in the candidate gate

The preflight is the primary boundary; the candidate gate is defence in depth for
two distinct faults:

- **Missed preflight boundary** on the current Line — pairs with
  `emotional_boundary_decision=required` and a current-Line finding. The
  application substitutes the canonical section 6.6 response **without a
  revision**. This is Line-scoped and identical in 4.2.1 and 4.2.3.
- **Candidate-only fault** — diagnosis or continued probing in the draft itself.
  Follows the ordinary revise-or-reject path.

Inspection records which of the two originated the boundary and never claims Muse
was skipped on the fallback path.

## Curation review

A separate no-tool call reviews one complete Sculptor curation proposal. It
carries no Muse context, no conversation, and no book evidence. Its input is a
`CurationReviewInput`: the proposal digest, the complete proposal, and the exact
immutable source snapshots that proposal selected — nothing else from the
account.

**The verdict vocabulary differs.** This gate returns `allow`, `revise`, or
`reject`, not `pass`. An `allow` must echo the supplied `proposal_digest`
exactly, and a validator rejects a verdict bound to any other digest, so an
approval cannot be lifted onto a different proposal. `allow` must carry no
findings; `revise` and `reject` must carry at least one.

The digest binds account scope, the current ordered curation-state digest, the
complete proposal, and the source-record hashes. Application code constructs
`ApprovedCuration` only from an exact `allow`, and the Memory & Policy Service
then re-reads the originals and fails closed on stale, unknown, cross-account,
stale-state, or structurally invalid sources before appending one immutable
audit event. Any missing, malformed, revised, rejected, or differently bound
verdict stops the flow.

`revise` means the intended action is defensible but its text, label, or source
selection needs correction. `reject` means the action itself is unsupported or
unsafe. Neither authorises a write, and the gate never reports that a proposal
was stored — Provenance can only veto here, exactly as it can only veto capture.

Source text supplied for review is untrusted data. Originals are never modified:
the loop re-hashes every source after each agent call and fails if anything
moved.

The production curation loop is implemented outside live chat. The synthetic
curation runner currently calls Sculptor's `propose_curation` entry point and
grades proposal quality and source preservation. It does not run this review
skill or measure a complete curation apply-and-audit flow. No dedicated curation
semantic evaluation pack is implemented under `evals/provenance`.

## Where its authority ends

Provenance is the semantic boundary only, and it is never the last check.

Deterministic application code runs *after* a semantic pass. The current
book-corpus slice resolves every declared evidence ID against one
application-owned, request-scoped book-evidence index, checks exact quotations, source
lines, and locations, and enforces the trusted work, book version, and chapter
ceiling or exact-passage scope. A declared exact quotation must occur both in
the visible reply and in its canonical record. The index admits exact book
records from three sources only: the current
direct Librarian result, the selected book records of a current Serendipity
proposal, and records re-resolved from identifiers cited by an earlier
successfully released reply in the same session. Conflicting records for one
identifier fail closed, and a re-resolved session record authorises only that
exact previously released passage. Stored-memory, web, and image evidence never
enter this book citation authority. Registered memory and opened-web evidence
use a separate request-local authority with active-memory and visible-URL
checks. Image evidence has no implemented release contract. Regular expressions
and structural checks are
defence in depth, not the security boundary.

For memory, Provenance can only veto. It cannot authorise a write. Automatic
capture additionally requires a Muse nomination and deterministic policy
approval, and the Memory & Policy Service alone commits every save.
`orchestration/capture.py` is the only place capture flags are set, so no caller
can authorise its own capture. A review that fails to complete is treated
exactly as a veto.

The same limit applies to curation. An `allow` verdict is a necessary condition
for a curation write, never a sufficient one: the Memory & Policy Service
revalidates every source and the action's own preconditions afterwards, and it
alone appends the audit event. A tombstone, for instance, still requires a prior
duplicate link to a distinct canonical record that is itself still retrievable,
regardless of what the review said.

Telemetry records verdicts but must never authorise release.

A binding routing clarification also constrains the complete turn. The
candidate can declare no evidence and can use no tool other than
`librarian_route`. After semantic and deterministic approval, application code
releases the validated question with `release_source=application_clarification`.

## Related

- `src/linger/orchestration/reflection.py` — the release path and revision loop.
- `src/linger/orchestration/capture.py` — derives capture flags from a review.
- `src/linger/orchestration/curation.py` — `run_curation_loop`, the select →
  propose → review → apply → verify path.
- `src/linger/contracts/curation.py` — the plan, approval, and audit contracts
  that bind an `allow` verdict to one exact proposal.
- `src/linger/services/memory.py` — the deterministic policy gates that consume
  those flags.
- `docs/specification.md` sections 4.1, 4.2.1, 4.2.2, 4.2.3, 5.3, 5.4, 6.3, 6.5,
  and 6.6.
