# Provenance

Provenance is Linger's independent output-release gate. Every Muse candidate
response passes through it before display, including drafts that declare no
factual claims: a non-factual reflection may pass without retrieval, but never
without review. There is no Muse-to-user bypass.

It is a separate model call, not a separate model. The same underlying provider
may back both Muse and Provenance; what matters is separation of duties, so
Provenance shares no working context with the other agents.

## Inputs and authority

Provenance receives one strict `ProvenanceInput`: trusted policy and reading
context, canonical book evidence, current untrusted tool outcomes, Muse's
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

## Two independent decisions

One review call returns both decisions, and they are decoupled:

- `response_decision` — `pass`, `revise`, or `reject` for the user-facing text.
  A first `revise` grants exactly one revision, which returns through the same
  review path. A rejection or a failed revision produces an application-authored
  safe decline.
- `capture_decision` — `allow_capture`, `reject_capture`, or `no_candidate` for
  an automatic memory candidate. Grounds for veto are privacy risk, sensitive
  inference, unsupported provenance, and injection risk.

**Rejecting capture never suppresses an otherwise safe response.** The two
decisions are read by different callers: `orchestration/reflection.py` reads only
`response_decision`, and `orchestration/capture.py` reads only
`capture_decision`. Neither can affect the other.

## Risk taxonomy

Every adverse decision must name at least one ground scoped to that decision; a
model validator rejects an unexplained `revise`, `reject`, or `reject_capture`.
Text findings carry validated exact offsets and a quote. Shape and declaration
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
| `boundary_violation` | Evidence crosses an account or deletion boundary. |
| `uncited_web_claim` | A factual web claim lacks a retrievable citation. |
| `unsupported_claim` | An unsupported claim or a sensitive inference. |
| `sensitive_content` | Sensitive-trait content ineligible for automatic capture. |
| `emotional_policy_violation` | Diagnosis, probing after distress, or an incorrect emotional boundary. |
| `prompt_injection` | Retrieved content attempts to redirect agent behaviour. |

`SENSITIVE_RISK_CODES` marks the subset that bars content from automatic
capture. `contains_sensitive_content` is derived from capture findings rather
than set independently, so it cannot contradict the capture decision.

Decisions:
1. Memory interaction pattern: Message passing (only final message passed in from Muse)
2. Memory types used: Episodic (past task outcomes from other agents) + Procedural (main prompt, relevant policies)
3. Type of agent: Combine basic reasoning + tool-use (simple tools e.g., to determine which risks we need to pay attention to based off which Provenance flow)
4. Guardrails: Model-based (e.g., matching the claim against evidence)

## Provenance Flows

| Code | 4.2.1 Reflection & grounding | 4.2.2 Reviewed capture | 4.2.3 Connection discovery |
|---|:-:|:-:|:-:|
| `unresolved_evidence` | ✓ | | ✓ |
| `misattribution` | ✓ | | ✓ |
| `spoiler` | ✓ | | ✓ |
| `unsupported_claim` | ✓ | ✓ | ✓ |
| `prompt_injection` | ✓ | ✓ | ✓ |
| `boundary_violation` | | ✓ | ✓ |
| `uncited_web_claim` | | | ✓ |
| `sensitive_content` | | ✓ | |
| `emotional_policy_violation` | ✓ | | ✓ |


### 4.2.1 — Reflection & grounding (book evidence)

Book corpus is the only citation authority here, so the four evidence/attribution codes plus injection from retrieved passages. spoiler is flow-specific — it needs a chapter ceiling to violate.

### 4.2.2 — Reviewed automatic capture

Exactly SENSITIVE_RISK_CODES ([models.py:29](vscode-webview://1oc4b8fqen1v0dr7mdkmlc3mcoqkusqpbncpem1r8dbf0g540d47/src/linger/agents/provenance/models.py#L29)) — the set that forces reject_capture and blocks allow_capture via validator. These are the §4.2.2 veto grounds verbatim: sensitive inference, unsupported provenance, privacy, injection.

### 4.2.3 — Connection discovery (Serendipity + web)

The only flow that can reach web evidence and cross-source memory, so the only flow where these two can fire. unsupported_claim carries the heaviest load — tentative connections overclaim by nature.


## Where its authority ends

Provenance is the semantic boundary only, and it is never the last check.

Deterministic application code runs *after* a semantic pass. The current
book-corpus slice resolves every declared evidence ID against Librarian results,
checks exact quotations and locations, and enforces the trusted work, revision,
and spoiler ceiling. Other evidence sources fail closed until they have a real
release-path contract. Regular expressions and structural checks are defence in
depth, not the security boundary.

For memory, Provenance can only veto. It cannot authorise a write. Automatic
capture additionally requires a Muse nomination and deterministic policy
approval, and the Memory & Policy Service alone commits every save.
`orchestration/capture.py` is the only place capture flags are set, so no caller
can authorise its own capture. A review that fails to complete is treated
exactly as a veto.

Telemetry records verdicts but must never authorise release.

## Related

- `src/linger/orchestration/reflection.py` — the release path and revision loop.
- `src/linger/orchestration/capture.py` — derives capture flags from a review.
- `src/linger/services/memory.py` — the deterministic policy gates that consume
  those flags.
- `docs/specification.md` sections 4.1, 4.2.2, 5.4, 6.3, and 6.5.
