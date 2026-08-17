# Provenance

Provenance is Linger's independent output-release gate. Every Muse candidate
response passes through it before display, including drafts that declare no
factual claims: a non-factual reflection may pass without retrieval, but never
without review. There is no Muse-to-user bypass.

It is a separate model call, not a separate model. The same underlying provider
may back both Muse and Provenance; what matters is separation of duties, so
Provenance shares no working context with the other agents.

## Inputs and authority

Provenance receives the complete candidate response, any proposed memory, the
cited evidence, and the applicable policy constraints — nothing else. It has no
tools, no conversation history, and no write authority anywhere in the system.

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

Every adverse decision must name at least one ground; a model validator rejects
an unexplained `revise`, `reject`, or `reject_capture`. Each finding quotes the
exact offending span, which makes per-category detection recall measurable and
gives the one permitted revision something specific to act on.

The seven `RiskCode` values transcribe the specification's block conditions
one-for-one:

| Code | Ground |
| --- | --- |
| `unresolved_evidence` | Cited evidence is missing or unresolved. |
| `misattribution` | A quotation, idea, or source is attributed incorrectly. |
| `spoiler` | Content passes the reader's boundary, or that boundary is unclear. |
| `boundary_violation` | Evidence crosses an account or deletion boundary. |
| `uncited_web_claim` | A factual web claim lacks a retrievable citation. |
| `unsupported_claim` | An unsupported claim or a sensitive inference. |
| `prompt_injection` | Retrieved content attempts to redirect agent behaviour. |

`SENSITIVE_RISK_CODES` marks the subset that bars content from automatic
capture. `contains_sensitive_content` is derived from the findings rather than
set independently, so it cannot contradict them.

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
