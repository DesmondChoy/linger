# Runtime security validation guardrails

## Focus

Add deterministic application checks at Linger's runtime trust boundaries.
The first implementation should answer two questions:

1. **Would this send a credential or personal data to an external model, or
   persist private data?** Detect secrets and personal data before model
   forwarding, release, and storage, then apply an explicit boundary-specific
   policy.
2. **Does untrusted content match an adopted injection rule?** Block the turn
   before that content enters an agent context, and record a value-free reason.
   The match does not establish intent or agent behavior.

These checks complement semantic review. They must execute in application code;
prompt wording and evaluation UI are not runtime controls.

## In scope

- A typed, value-free validation result with stable category/reason codes,
  detector identity, boundary, and disposition.
- PII redaction and secret screening of the complete text sent to each
  external model request.
- Personal-data redaction and secret blocking for generated replies and text
  proposed for persistent storage.
- Deterministic injection checks on reader, retrieved, and tool-provided text
  before that text enters an agent context. A match blocks the turn.
- Safe telemetry, focused detector tests, and representative false-positive
  evaluation before enabling blocking behavior.

## Out of scope for the first implementation

- Replacing Provenance's semantic review of prompt injection, harmful content,
  or whether an agent followed malicious text.
- Treating a phrase match as proof of malicious intent or as a semantic
  verdict. Blocking on an adopted rule is an application policy decision.
- Building a general harmful-content classifier from keyword patterns. Linger
  already has targeted first-person self-harm and non-English reader-message
  boundaries; broader harmful-content policy needs a separate decision.
- Treating the synthetic ground-truth review interface as runtime protection.

## Existing controls

- [`contracts/privacy.py`](../../src/linger/contracts/privacy.py) currently
  uses `pydantic_ai_harness` detectors for personal data and secrets, with an
  extra phone pattern, and scans original and detector-folded text. Its API
  returns a Boolean. The proposed plan replaces its PII detection backend with
  DataFog while retaining the maintained secret detector.
- [`services/memory.py`](../../src/linger/services/memory.py) vetoes private
  data and credentials in memory capture and curation. Serendipity tools also
  screen returned text. These checks protect storage/tool results; they are
  not a general provider-request gate.
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
  attacks. `evals/synthetic_journals/` and
  `tests/test_memory_injection_replay.py` provide evaluation coverage, not a
  runtime security boundary.

## Proposed runtime behavior

| Boundary | Check | Initial disposition |
| --- | --- | --- |
| Before each external model request | PII and credentials in all assembled text, including reader input, memory, web/tool excerpts, and other injected evidence | Redact PII before forwarding. Block credentials. Never log matched values |
| Before untrusted text enters an agent context | Injection patterns in reader, retrieved, and tool-provided spans | Block the turn with a standard explanation. Record category and boundary only. Do not send the detector result to Provenance |
| Before release | PII and credentials in generated reply | Redact PII. Block credentials |
| Before persistent storage | PII and credentials in transcripts, nominations, curation proposals, and derived text | Redact PII before writing new text. Block credentials and do not persist blocked turns. Leave historical records unchanged in this change |

## Policy contract for step 1

Apply these rules to the text fields below. Leave non-text fields unchanged.
Run the privacy check before each external model request, including follow-up
requests after tool results and revisions.

| Data | Fields and sources | PII action | Credential action |
| --- | --- | --- | --- |
| Model request text | Every text field in the selected role input, selected skill instructions, and `message_history`, including tool-call arguments and results. This includes `MuseDraftInput`, `MuseRevisionInput`, `ProvenanceInput`, `CurationReviewInput`, and text-bearing Librarian, Serendipity, and Sculptor inputs. | Replace detected values in the outbound copy before dispatch | Block the request before dispatch |
| Injection-bearing text | `MuseTurn.user_message`, retrieved book and memory excerpts, web excerpts, and tool-provided text before those values enter an agent context | Apply the privacy rule above | Apply the privacy rule above |
| Generated response | `MuseCandidate.reply` and `MemoryCandidate.text` before sending them to Provenance, the reader, or storage | Redact before review, release, or storage so every downstream reader sees the same redacted text | Block the candidate before Provenance, release, or storage |
| Transcript persistence | `transcript_turns.user_message`, `transcript_turns.assistant_message`, and the corresponding session history entries | Redact before persistence | Do not persist a turn blocked by this contract or any credential |
| Derived text for storage | `AutomaticMemoryCandidate.text`, `DerivedSummary.summary`, and `TopicGroup.topic_label`, before review handoff and persistence | Redact before review and storage | Block review handoff and storage |

Use DataFog's default regex engine and entity set for PII. Use the existing
maintained secret detector for credentials. Replace each PII match with
DataFog's entity-labelled redaction token. Keep the match-to-source offset map
only in memory so the application can retain source IDs and evidence bindings
after redaction. Do not store or export that map. Do not rewrite canonical book
corpora or historical records as part of this change. Redact existing stored
text in an ephemeral copy before sending it to a model. New transcript and
derived-memory writes contain only redacted text.

Each validation decision has a stable category (`pii`, `credential`, or
`prompt_injection`), detector identity and version, pattern ID when applicable,
boundary, and disposition (`redact` or `block`). Results never contain matched
text. Redaction returns a transformed copy and an ephemeral mapping to the
original source spans. Do not log or persist the mapping or unredacted copy.
When a credential blocks a request, return a standard safe decline that names
the credential category but never the value or provider-specific token shape.

An enabled injection rule blocks the current turn before the matched text enters
an agent context. This policy applies to reader text and retrieved or
tool-provided text. Do not call Provenance because of the match. Return this
standard message without naming or quoting the matched content:

> This turn was blocked because instruction-like content was detected in the
> request or its source material. Rephrase the request or remove the affected
> source and try again.

Record the stable category, detector and pattern IDs, boundary, and disposition
for each block. Keep the source identity only in the in-memory decision context
unless a later telemetry policy approves a non-sensitive identifier. Never
record matched text, a secret, PII, the redaction offset map, or an untrusted
excerpt. Quoted, negated, and educational text follows the same block rule when
it matches an enabled injection rule. Evaluate paired benign examples before
enabling each rule and measure its false-positive rate.

Provenance continues its normal semantic review of generated candidates,
including malicious influence from retrieved content and the behavior of the
response. An injection detector match does not add or trigger a Provenance
review. When a match blocks a turn before generation, no candidate reaches
Provenance. Keep the instruction-leak release check active.

## Implementation sequence

1. **Record the policy contract.** The boundary table above defines the text
   fields, PII redaction, credential blocking, injection disposition, and safe
   telemetry. Record validator identities in `RuntimeSkill` fingerprints when
   a skill run uses them. Keep provider dispatch and storage policy
   application-owned.
2. **Install the provider-request guard on every role Agent.** The locked
   PydanticAI `2.26.0` provides `AbstractCapability.before_model_request`;
   its `ModelRequestContext` exposes the current request messages and model
   parameters, and the capability documentation permits modifying that
   context. The hook runs for each model request, including requests after a
   tool result, so it can redact PII and block credentials on the assembled
   outbound request. Attach the capability to Muse, Librarian, Serendipity,
   Provenance, and Sculptor Agents; their separate role builders mean this
   must be explicit or factored through a shared Agent-construction helper.
   Keep the guard at the request boundary rather than relying on
   `apps/backend/telemetry.py::run_agent_traced`, which only wraps the overall
   `agent.run` call. Verify with the locked dependency that the hook sees the
   full text-bearing request, including instructions, history, tool results,
   and output-repair requests, before provider dispatch. Cover an initial
   request and follow-up requests in a tool loop and output repair. The
   inventory found all orchestration model calls use `run_agent_traced` and
   found no separate direct PydanticAI request path under `apps/backend` or
   `src/linger`; the PydanticAI hook is still needed to cover each request
   within a run. It does not cover other external APIs such as Exa, which
   require their own boundary checks.
   **Cross-agent impact:** Muse, Librarian, Serendipity, Provenance, and
   Sculptor all gain the same outbound privacy check. Preserve each role's
   tools, instructions, output validation, and authority boundaries. Check
   role behavior with `tests/test_muse_agent.py`,
   `tests/test_librarian.py`, `tests/test_serendipity.py`,
   `tests/test_provenance_agent.py`, and `tests/test_sculptor_agent.py`, plus
   focused request-hook tests for tool loops and output repair.
3. **Add DataFog and define the shared validator API.** Use the `datafog`
   package from [DataFog Python](https://github.com/DataFog/datafog-python) as
   the PII detector. Select its local `regex` engine and default structured
   entity set. Do not enable optional NER engines. Pin a tested package
   version, verify its supported API and license, and disable its optional
   telemetry in Linger's runtime configuration. The initial adapter pins
   `datafog==4.9.0`, uses `scan(engine="regex")` and `redact(...)`, and sets
   `DATAFOG_NO_TELEMETRY=1`. The wheel includes an MIT license file, while its
   package metadata lists an Apache license classifier; resolve this metadata
   mismatch before release. The shared text-only API is in
   [`security_validation.py`](../../src/linger/contracts/security_validation.py).
   Its `ValidationFinding` and `ValidationResult` types carry safe findings,
   and its separate operations cover provider requests, untrusted spans,
   generated output, and storage text. Injection rules are supplied by the
   caller; the module does not invent or enable a pattern set before review.
   Check its entity coverage
   against Linger's current international phone cases. Add a project-specific
   detector only for a demonstrated gap. Keep
   `pydantic_ai_harness`'s secret detector for credentials. Wrap both behind
   typed results and separate operations for provider-input redaction,
   untrusted-span injection checks, generated-output redaction, and storage
   redaction. For an injection match, return a typed block reason and the
   standard user-facing explanation. Do not call Provenance because of that
   match. Use this standard explanation without quoting the match: "This turn
   was blocked because instruction-like content was detected in the request or
   its source material. Rephrase the request or remove the affected source and
   try again." DataFog findings contain matched values, so the Linger
   adapter must remove those values from telemetry, exceptions, and
   user-visible output. Redact copies of text sent to models or stored as
   derived text. Preserve source IDs and enough span information to keep
   evidence bound to the original. Never rewrite original source records.
4. **Integrate and preserve controls.** Implemented across the five reusable
   Agents and the chat, storage, and evaluation-transcript boundaries. Each
   Agent's `before_model_request` capability redacts PII from the assembled
   request and blocks credentials; Muse's output validation redacts replies
   before Provenance and the reader, and drops a memory nomination if
   redaction would invalidate its source offsets. Automatic memory, curation
   text, session history, and transcript writes redact PII and block
   credentials. A curation change that would invalidate already-reviewed text
   requires a new review. Blocked chat turns are not appended to session
   history or reading progress. Transcript input, model messages, and output
   are sanitized before entering the synthetic evaluation sink. The old
   Boolean privacy helper now delegates to DataFog while Serendipity's
   existing result screening remains in place. Provenance semantic review and
   the instruction-leak release check remain active. The Exa request boundary
   still needs a separate privacy check, and no injection rule set has been
   enabled because the candidate expressions are absent and unreviewed; thus
   runtime injection blocking remains pending. Regression coverage should
   include the five role suites, memory and transcript persistence, request
   tool loops/output repair, and injection block-without-Provenance cases.
5. **Verify before enabling blocks.** Initial focused coverage is in
   [`test_security_validation.py`](../../tests/test_security_validation.py),
   `test_chat_endpoint.py`, `test_sessions.py`, `test_transcripts.py`, and
   `test_memory_service.py`. It exercises all five Agent registrations,
   initial requests, tool follow-ups, output repair, credential blocking
   before agent review, storage redaction, and evaluation transcript
   sanitization. The role, memory, persistence, and telemetry suites passed
   together (191 tests and 91 subtests). The agreed default DataFog rules
   redact ISBN fragments as ZIP codes and one ISO-formatted date as a date;
   these known false positives are captured in `test_memory_service.py` and
   need policy review before release. Broader near-miss, quoted/educational,
   Unicode, multiline, web-text, and enabled-injection-rule coverage remains
   open. Injection blocking cannot be verified until adopted rules are
   available. Continue checking that logs, traces, and errors never contain
   matched content.
6. **Instrument safely.** Record stable category, boundary, detector identity,
   and disposition only. Never export matched substrings, credential
   fragments, PII, or untrusted excerpts. Ensure error reporting does not
   serialize validator inputs.

## Detector review notes

The candidate regex snippet that motivated this plan is not included here.
Recover and review its exact expressions before implementation; the following
are reported concerns, not verified defects in a repository pattern set:

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
- PII is redacted from provider inputs, released replies, and derived text
  before storage, including new transcript writes. Credentials remain blocked
  at provider and storage boundaries.
- Injection matches produce stable, value-free block reasons and the standard
  explanation. They do not invoke Provenance. Paired benign and attack cases
  measure false positives before blocking rules are enabled.
- Provenance semantic review and the exact instruction-leak release check
  remain active.
- Detector tests and representative false-positive evaluation pass before
  blocking behavior is enabled.
- Skill fingerprints and telemetry identify validator versions/categories
  without exposing match contents.

## Remaining implementation checks

- Verify the locked PydanticAI hook behavior with request-level tests for all
  five role Agents, especially tool-loop and output-repair requests.
- Inventory and apply privacy checks at non-PydanticAI external API boundaries
  such as Exa.
- Which PII patterns does DataFog's default regex engine miss in
  representative Linger text? Add a project-specific detector only for a
  demonstrated gap.
- Does rollout require a migration to redact PII from historical transcripts
  and stored memories, or is redaction on read and for all new writes enough?
