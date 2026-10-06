# Security validation guardrails implementation plan

## Goal

Move deterministic, pattern-shaped security and privacy checks into reusable
application validators at trust boundaries. Keep Provenance responsible for
semantic judgments that regular expressions cannot establish. Validators must
run in application code and make release/forwarding decisions; prompt wording
alone is not a security control.

## Current behavior

- `src/linger/contracts/privacy.py` wraps the maintained
  `pydantic_ai_harness.guardrails.detectors.personal_data` and
  `redact_secrets` detectors. It also checks a detector-only folded copy using
  `fold_for_detection` from `contracts/text_folding.py`.
- `services/memory.py` vetoes personal data or secrets in captured and curated
  memory. `agents/serendipity/tools.py` also screens returned text. Existing
  callers use a Boolean policy helper; they do not redact text in place.
- Candidate prompt-injection review is currently semantic: Provenance uses the
  `prompt_injection` risk code during the candidate review in
  `orchestration/reflection.py`. The candidate-review skill distinguishes
  reader instructions from malicious instructions embedded in retrieved text.
- `orchestration/instruction_leak_detection.py` is a separate deterministic
  release backstop. It detects long verbatim runs of Muse's own instructions,
  including punctuation/case changes, ROT13, and long base64-encoded runs. It
  does not detect generic injection phrases.
- `reflection.py` calls Provenance after the draft and then performs release
  validation. The exact instruction-leak check is in `_validate_release`.
  Memory and curation privacy checks protect storage; the existing privacy
  helper is not currently a general pre-provider request gate.

## Proposed boundary model

Implement one typed, deterministic validation result with category, matched
pattern identifier, action, and safe diagnostic metadata. Do not include the
matched value in logs, traces, exception strings, or user-visible messages.
Actions should be policy-specific: `block` for secrets before a third-party
model call, `redact` only where preserving the request is explicitly allowed,
and `flag` for content that requires a semantic or application policy decision.
Keep category-level reason codes stable for telemetry.

Apply the validators at these boundaries:

1. **Before external model forwarding:** inspect all assembled untrusted text
   that will be sent to a third-party provider (reader message, retrieved
   memory, web/tool excerpts, and other injected evidence) for credentials.
   Fail closed on a secret match. Do not silently send a redacted variant to a
   model unless the caller explicitly opts into redaction and can preserve
   evidence/source bindings.
2. **Before untrusted text enters an agent context:** run injection phrase
   patterns on reader content and retrieved/tool content as an application
   signal. Preserve the original text and source identity. The signal may
   guide isolation or review, but must not alone reject a reader's ordinary
   request or establish that the generated answer followed the attack.
3. **Before release/storage:** screen generated replies, memory nominations,
   curation proposals, and stored derived text for credentials and PII. Apply
   the existing veto behavior where the destination is persistent storage;
   define a separate reply policy (block or redact) before implementation.
   Retain Provenance review and exact instruction-leak release validation.
4. **Harmful requests:** use patterns as a deterministic signal on the reader
   request and generated response, with policy disposition decided by the
   application. Do not equate a literal keyword match with harmful intent; a
   refusal, safety discussion, or quoted example can contain these phrases.

## Work sequence

1. **Define and review the policy contract.** Specify which exact fields cross
   provider, release, and storage boundaries; the action per category and
   boundary; whether PII is blocked or redacted; and the handling of quoted,
   negated, or educational text. Keep results value-free and typed. Record
   validator identities in the selected `RuntimeSkill` fingerprints when a
   skill run uses them; keep provider dispatch and storage policy in the
   application.
2. **Add a shared detector module.** Place compiled expressions and category
   definitions under `src/linger/contracts/` (or extend `privacy.py` if the
   API remains cohesive). Provide separate functions for input screening,
   generated-output validation, secret blocking, and PII detection/redaction;
   do not expose one ambiguous `is_safe` Boolean. Keep maintained detectors
   for PII/secrets where they provide broader coverage, and use custom patterns
   only for gaps demonstrated by tests.
3. **Validate before provider calls.** Identify the common provider dispatch
   and every model path, then guard at the narrowest shared application
   boundary before serialization/network dispatch. Ensure secrets in assembled
   context are caught, not just secrets in the reader's current message.
   Return a typed safe decline/error and record category-level telemetry only.
4. **Add deterministic attack signals.** Apply injection and harmful-content
   detectors to untrusted spans before agent context construction and to
   candidate output before Provenance/release as appropriate. Pass only a
   bounded, application-created signal into the typed Provenance input when
   useful. Do not add raw regex matches as model instructions or treat them as
   Provenance verdicts.
5. **Preserve and adapt existing controls.** Keep the instruction-leak check
   because it detects actual instruction reproduction, not merely an attack
   phrase. Consolidate privacy callers on the shared contract without
   weakening current memory, curation, or Serendipity vetoes. Review whether
   the current helper's doubled scan of raw and folded text remains needed
   once all detectors share normalization.
6. **Instrument safely.** Add reason codes and counts for detector category,
   boundary, and disposition. Never emit matched substrings, credential
   fragments, PII, or untrusted excerpts in telemetry. Ensure error reporting
   does not serialize validator inputs.
7. **Migrate and remove obsolete internal paths.** Update every controlled
   caller together, then remove superseded bespoke detection only if the new
   validator demonstrably preserves its behavior. Preserve public APIs and
   stored data contracts unless a migration is explicitly designed.

## Pattern set review before adoption

The supplied snippet needs correction and policy review before it can be
compiled as Python:

- Several expressions appear to have formatting/escaping corruption (for
  example `\s\*`, `[*-]?`, `[INST]`, and `+?1`); `[INST]` is a character class,
  not a literal token. The email dot should be escaped, and phone grouping
  syntax needs valid parentheses/quantifiers.
- The phone pattern is US-specific; the separate eight-digit telephone rule
  can match dates, IDs, and other non-telephone values. Credit-card matching
  needs digit-boundary and optional-separator review, and none of the PII
  patterns validate actual number checksums.
- Injection strings such as “you are now” or “jailbreak” are high-noise signals
  without context. Literal `[INST]` and `<system>` markup should be matched as
  literals. The patterns cannot identify indirect injection expressed without
  these phrases or establish that an agent obeyed it.
- Harmful-content patterns are narrow and can match benign discussion. They
  do not provide a complete safety classifier.
- Secret patterns are intentionally shaped and will miss many provider formats
  and custom credentials. Use the maintained secret detector as the baseline,
  with reviewed additions and secret-safe fixtures.

Create fixtures with positive, negative, near-miss, quoted/educational, Unicode
folded, and multiline examples for each detector. Store only synthetic
credentials. Measure false positives against representative Linger reader,
book, memory, and web text before enabling blocking behavior.

## Acceptance criteria

- A synthetic credential in any text destined for an external model is
  rejected before provider invocation, with no secret in logs or traces.
- PII and credentials remain vetoed from memory capture and curation, and all
  existing retrieval screening behavior is preserved.
- Injection and harmful-content matches create deterministic signals with
  stable reason codes; ordinary quoted or educational mentions do not cause
  an unconditional user-facing refusal.
- Provenance continues to review semantic policy, malicious retrieved-content
  influence, and response behavior; the exact instruction-leak release check
  remains active.
- Regex corrections and detector behavior are covered by focused tests and
  representative false-positive evaluation before rollout.
- Agent skill fingerprints and inspection telemetry identify validator
  versions/categories without exposing match contents.

## Open implementation decisions

- Should reply PII be redacted, blocked, or handled by existing product policy?
- Which provider dispatch function is the universal pre-forwarding boundary,
  and do any direct model calls bypass it?
- Which PII/secret patterns are intentionally project-specific versus already
  covered by the maintained detector dependency?
- Should high-confidence injection signals alter tool exposure, trigger
  Provenance review, or only be recorded for evaluation? Choose using paired
  false-positive/attack evaluations; do not widen or suppress tools based on
  the phrase list alone.
