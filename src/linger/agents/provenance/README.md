# Provenance

Provenance is Linger's independent output-release gate. Every Muse candidate
response passes through it before display, including drafts that declare no
factual claims: a non-factual reflection may pass without retrieval, but never
without review. There is no Muse-to-user bypass.

It also runs a no-tool emotional-boundary preflight on the current Line before
Muse. The preflight can end a request without a candidate through an
application-owned path; see [Provenance Flows](#provenance-flows).

It is a separate model call, not a separate model. The same underlying provider
may back both Muse and Provenance. The application constructs a separate review
input instead of sharing another agent's conversation history.

## Inputs and authority

Provenance receives one strict `ProvenanceInput`: trusted policy, chapter or
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

## Provenance flows

Provenance has separate emotional-preflight and candidate-review call sites.
Preflight can stop the turn before candidate review. A revision invokes
candidate review again.

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
current Serendipity run. A proposal citing memory records still fails
deterministic release because those records are outside the citation contract.
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


## Where its authority ends

Provenance is the semantic boundary only, and it is never the last check.

Deterministic application code runs *after* a semantic pass. The current
book-corpus slice resolves every declared evidence ID against one
application-owned, request-scoped evidence index, checks exact quotations, source
lines, and locations, and enforces the trusted work, book version, and chapter
ceiling or exact-passage scope. A declared exact quotation must occur both in
the visible reply and in its canonical record. The index admits exact book
records from three sources only: the current
direct Librarian result, the selected records of a current book-only Serendipity
proposal, and records re-resolved from identifiers cited by an earlier
successfully released reply in the same session. Conflicting records for one
identifier fail closed, and a re-resolved session record authorises only that
exact previously released passage. Stored-memory, web, and image evidence never
enter this citation authority. Regular expressions and structural checks are
defence in depth, not the security boundary.

For memory, Provenance can only veto. It cannot authorise a write. Automatic
capture additionally requires a Muse nomination and deterministic policy
approval, and the Memory & Policy Service alone commits every save.
`orchestration/capture.py` is the only place capture flags are set, so no caller
can authorise its own capture. A review that fails to complete is treated
exactly as a veto.

Telemetry records verdicts but must never authorise release.

A binding routing clarification also constrains the complete turn. The
candidate can declare no evidence and can use no tool other than
`librarian_route`. After semantic and deterministic approval, application code
releases the validated question with `release_source=application_clarification`.

## Related

- `src/linger/orchestration/reflection.py` — the release path and revision loop.
- `src/linger/orchestration/capture.py` — derives capture flags from a review.
- `src/linger/services/memory.py` — the deterministic policy gates that consume
  those flags.
- `docs/specification.md` sections 4.1, 4.2.1, 4.2.2, 4.2.3, 5.3, 5.4, 6.3, 6.5,
  and 6.6.
