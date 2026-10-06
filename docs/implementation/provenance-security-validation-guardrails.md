# Runtime security validation guardrails

## Focus

Apply DataFog's default regex PII redaction once to the incoming chat message,
before Muse receives it. Block credentials in that message and at model and
storage boundaries. Check the current user message for adopted injection
patterns before Provenance's emotional-boundary preflight. An injection match
blocks the turn with a standard message and a value-free reason.

Provenance still reviews generated candidates and retrieved content in context.
The synthetic evaluation UI displays expectations; it is not a runtime check.

## In scope

- A typed, value-free validation result with stable category/reason codes,
  detector identity, boundary, and disposition.
- PII redaction of the incoming chat message before Muse or another agent runs.
- Credential blocking for incoming messages, each model request, generated
  output, and new storage writes.
- Deterministic injection checks on the current user message before the
  emotional-boundary preflight. Retrieved passages and tool results do not
  trigger this block.
- Safe telemetry, focused detector tests, and representative false-positive
  evaluation for enabled rules and before expanding them.

## Out of scope for the first implementation

- Replacing Provenance's semantic review of prompt injection, harmful content,
  or whether an agent followed malicious text.
- Treating a phrase match as proof of malicious intent or as a semantic
  verdict. Blocking on an adopted rule is an application policy decision.
- Building a general harmful-content classifier from keyword patterns. Linger
  already has targeted first-person self-harm and non-English reader-message
  boundaries; broader harmful-content policy needs a separate decision.
- Treating the synthetic ground-truth review interface as runtime protection.
- DataFog scans of assembled agent prompts, retrieved passages, tool results,
  generated replies, or stored memories. These sources are not rescanned for
  PII after the incoming chat message is redacted.

## Existing controls

- [`contracts/privacy.py`](../../src/linger/contracts/privacy.py) retains the
  existing Boolean personal-data check for synthetic outbound-query evaluation.
  It is not part of the chat PII redaction path.
- [`services/memory.py`](../../src/linger/services/memory.py) blocks
  credentials in capture and curation writes. Serendipity's Exa boundary
  blocks credentials and queries that copy private reader or memory wording.
- Provenance reviews candidate replies semantically, including
  `prompt_injection` findings. The application retains release authority.
- [`instruction_leak_detection.py`](../../src/linger/orchestration/instruction_leak_detection.py)
  blocks replies that reproduce long runs of Muse's own instructions. It does
  not detect generic injection phrases.
- [`chat_turn.py`](../../apps/backend/chat_turn.py) applies a targeted
  first-person self-harm check and non-English language guard to the reader's
  current message. These do not scan assembled context or generated replies.
- `.agents/skills/review-synthetic-ground-truth/ui/src/InjectionExpectation.jsx`
  displays synthetic attack expectations and review criteria. It is not
  imported by the production reader UI and does not inspect or block runtime
  attacks. `chat_turn.py` now has a separate, narrow check on current user
  input before Provenance's emotional-boundary preflight. `evals/synthetic_journals/` and
  `tests/test_memory_injection_replay.py` provide evaluation coverage, not a
  runtime security boundary.

## Runtime behavior

| Boundary | Check | Disposition |
| --- | --- | --- |
| Incoming chat message, before Muse | DataFog regex PII scan and credential scan | Redact detected PII in the message passed to the pipeline. Block credentials before any agent runs |
| Before each external model request | Credentials in assembled messages and parameters | Block credentials. Keep PII from internal prompts and retrieved content unchanged |
| Before Provenance's emotional-boundary preflight | Injection patterns in the current user message only | Block the turn with a standard explanation. Record category, boundary, detector, and pattern IDs. Skip the preflight and all later agents for this turn |
| Before release and storage | Credentials in generated replies, nominations, curation text, session history, and transcripts | Block credentials. Do not run DataFog on these fields |
| Before Exa requests | Credentials and copied private reader or memory wording | Block the external request. Do not run DataFog on Exa parameters |

## Policy contract for step 1

The chat entry point calls `validate_user_input` on `ChatRequest.message` once.
It passes the redacted value to Muse and to later agents. It persists that
redacted user message in released session history. Other text fields are not
PII-redacted by this guardrail.

| Data | PII action | Credential action |
| --- | --- | --- |
| Current user message | Redact with DataFog's default regex engine before Muse | Block before the pipeline |
| Assembled model requests and generated output | No additional PII scan | Block before dispatch or release |
| Session, transcript, and derived-memory writes | Persist the already-redacted incoming message; do not rescan other fields | Block the write |

Use DataFog's regex engine with `EMAIL` and `PHONE` entities for this minimal
PII check. Use the existing maintained secret detector for credentials.
Replace each PII match with DataFog's entity-labelled redaction token. Do not
rewrite canonical book corpora, retrieved records, or historical memories.

Each validation decision has a stable category (`pii`, `credential`, or
`prompt_injection`), detector identity and version, pattern ID when applicable,
boundary, and disposition (`redact` or `block`). Results never contain matched
text. Findings may contain transient source offsets but no matched values.
Do not log or persist the unredacted incoming message or offsets.
When a credential blocks a request, return a standard safe decline that names
the credential category but never the value or provider-specific token shape.

An enabled injection rule checks only the current reader message, immediately
before Provenance's emotional-boundary preflight. A match blocks the turn
before any agent call. Retrieved book or memory excerpts, web excerpts, and tool
results are outside this injection check. Do not call Provenance because of a
user-message match. Return this standard message without naming or quoting the
matched content:

> This turn was blocked because instruction-like content was detected in the
> request or its source material. Rephrase the request or remove the affected
> source and try again.

Record the stable category, detector and pattern IDs, boundary, and disposition
for each block. Keep the source identity only in the in-memory decision context
unless a later telemetry policy approves a non-sensitive identifier. Never
record matched text, a secret, PII, or an excerpt.
Quoted, negated, and educational user text follows the same block rule when it
matches an enabled injection rule. Evaluate paired benign examples and measure
false positives for every rule.

Provenance continues its normal semantic review of generated candidates,
including malicious influence from retrieved content and the behavior of the
response. An injection detector match does not add or trigger a Provenance
review. When a match blocks a turn before generation, no candidate reaches
Provenance. Keep the instruction-leak release check active.

## Implementation sequence

1. **Set the policy contract.** Use typed, value-free validation results for
   PII, credentials, and adopted injection rules. DataFog applies only to the
   incoming user message. Keep credential checks at model, release, and storage
   boundaries.
2. **Redact incoming PII.** `run_chat_turn` calls `validate_user_input` before
   the chat pipeline. The validator uses DataFog's `regex` engine for `EMAIL`
   and `PHONE`. It returns a redacted message for Muse and blocks detected
   credentials. The pinned package is `datafog==4.9.0`; Linger disables its
   optional telemetry with `DATAFOG_NO_TELEMETRY=1` before import.
3. **Block user-input injection patterns.** After the existing language guard,
   the backend checks the current, PII-redacted user message immediately
   before Provenance's emotional-boundary preflight. The adopted rules cover
   explicit instruction overrides, hidden-instruction requests, and requests
   to follow replacement instructions. A match returns the standard message,
   records pattern IDs without matched text, and skips all agents for the turn.
4. **Keep credentials separate.** `ProviderCredentialGuard` runs before every
   model request for Muse, Librarian, Serendipity, Provenance, and Sculptor.
   Generated text and new storage writes also block credentials. These checks
   do not call DataFog or rewrite ordinary prompt, evidence, or output text.
   Serendipity's Exa boundary keeps its credential and copied-wording checks.
5. **Verify each boundary.** `test_chat_endpoint.py` checks redaction before
   Muse and the no-agent injection block. `test_security_validation.py` checks
   the DataFog result, credential guard, and injection rules. The Librarian,
   Provenance mapping, Muse skill, capture, curation, Serendipity, and synthetic
   replay suites check that internal JSON and evidence remain usable.

The role impact is limited: Muse receives the redacted incoming message.
Librarian, Serendipity, Provenance, and Sculptor receive that value through
normal handoffs, while their own assembled prompts retain original book,
memory, and tool text. All five roles keep the credential request guard.

## Detector review notes

The original candidate regex snippet is not included here. The runtime uses a
small explicit-rule baseline derived from Muse's current override examples;
the broader patterns below remain proposals and are not enabled. They are
reported concerns, not verified defects in an adopted pattern set:

- Possible formatting/escaping corruption (`\\s\\*`, `[*-]?`, `[INST]`,
  `+?1`); `[INST]` is a character class unless escaped as a literal token.
- Email dots, phone grouping, digit boundaries, optional separators, and
  checksum validation need review. Broad eight-digit or US-only phone rules
  can miss valid numbers or match dates and identifiers.
- Phrases such as “you are now” and “jailbreak” are noisy without context.
  Literal `[INST]` and `<system>` markup need literal matching. Phrase patterns
  cannot detect every indirect attack or establish that an agent obeyed it.
- Shaped secret patterns will miss provider formats and custom credentials;
  use the maintained detector as the baseline.

## Acceptance criteria

- A synthetic credential in any text sent to an external model is blocked
  before that provider request, with no value in logs, traces, or errors.
- DataFog redacts detected PII in the incoming chat message before Muse sees
  it. Internal model prompts, generated replies, and storage writes do not
  apply a second PII scan. Credentials remain blocked at provider, release,
  and storage boundaries.
- Injection matches in the current user message produce stable, value-free
  block reasons and the standard explanation before Provenance's
  emotional-boundary preflight. Retrieved text and tool results do not trigger
  this check. Paired benign and attack cases measure false positives before
  adding or broadening rules.
- Provenance semantic review and the exact instruction-leak release check
  remain active.
- Detector tests and representative false-positive evaluation pass before
  adding or broadening blocking rules.
- Skill fingerprints and telemetry identify validator versions/categories
  without exposing match contents.

## Remaining checks

- Measure DataFog's false positives and missed PII in representative incoming
  chat messages before changing the email and phone regex policy.
- Resolve the DataFog wheel's MIT license file and Apache package metadata
  mismatch before release.
