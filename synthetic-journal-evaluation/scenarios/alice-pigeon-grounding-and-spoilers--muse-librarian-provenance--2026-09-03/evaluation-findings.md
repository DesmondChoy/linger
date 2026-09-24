# Book evaluation findings

## Latest status

The latest approved provider replay, `50b9bcd8614b4c448992ef86fafff894`,
passed **all four adopted judgments** after pulling upstream commit `bf0ab5f`
and preserving the local fixes. The Pigeon Scene inferred completed chapter 5
using the saved memory and both required anchors. Librarian returned only the
permitted passage. Muse completed the exact quotation after two output retries,
and Provenance passed it without requesting a revision. Both control Scenes
passed.

The [post-pull replay summary](post-pull-replay-summary.json) preserves
the grades and trace evidence. The adopted data and grading rules remain
unchanged. This run verifies the combined fixes end to end; the earlier failures
remain recorded, and these successful runs do not establish consistent model
behavior. Optional semantic review was not run.

The integrated implementation passed all 777 Python tests and 419 subtests,
five frontend tests, the frontend build, and lint before this replay. The only
merge conflict was the Beads activity log; every entry from both sides was
preserved. `linger-h4gl` and integration task `linger-hzdg` are complete. The
sections below preserve the implementation and replay history.

## Original replay result

One human-approved provider-backed replay completed on 2026-09-05 using
`openai:gpt-5.6-luna`. Two of four adopted judgments passed their deterministic
checks. The combined grounded-reflection Scene failed both of its judgments.

| Scene | Adopted expectation | Recorded behavior | Result |
|---|---|---|---|
| `pigeon-reflection` | Infer the supported reading boundary and quote the Pigeon passage. | Asked for the latest completed chapter or scene, without retrieval or quotation. | `pigeon-grounding` and `pigeon-boundary` failed. |
| `uncertain-growth` | Clarify the ambiguous reading position without retrieving a continuation. | Asked for the latest completed chapter or scene. | `growth-boundary` passed. |
| `personal-reflection` | Help with the personal concern without book retrieval. | Offered reflection and possible introductions without book tools. | `personal-grounding` passed. |

The optional semantic model review was not run. A deterministic pass does not
establish prose quality or prove the absence of paraphrased spoilers.

## Discovery: remembered context did not reach boundary inference

The failing Scene had one seeded Prop about Alice's conversation with the
Caterpillar. Its private boundary-inference input nevertheless contained zero
`relevant_memories`. Librarian proposed chapter 5 with confidence 0.99, citing
`pg11-v01b38ea4-ch05-ln1179-1219`, but labeled the basis `line_only` and cited no
memory IDs.

The application deliberately refuses to authorize reading progress from a
Line alone. In [boundary.py](../../../src/linger/orchestration/boundary.py),
`infer_spoiler_boundary` converts that basis into `progress_unverified` and a
clarification question. The recorded response was:

> What is the latest chapter or scene in Alice's Adventures in Wonderland that you have completed?

This narrows the failure: Librarian found the expected chapter, but the
memory-supported authorization required by the adopted Ground truth was absent.
Without an authorized boundary, the requested retrieval and quotation did not
happen. The quotation and support failures are consequences of that same Scene
outcome, not evidence of several independent bugs.

The trace does not yet establish why the seeded Prop was absent from the
selected memories. Follow-up `linger-h4gl` must trace memory selection and assess
the adopted assumptions. Do not weaken the authorization rule or rewrite the
approved labels merely to make this run pass. Any changed labels require fresh
human review, and another paid replay requires fresh approval.

## Evidence and scope

- [Backstory and inputs](backstory.json), [proposed Ground truth](ground-truth.json),
  and [human adoption](ground-truth-adoption.json) retain their reviewed bytes.
- [Replay summary](replay-summary.json) preserves each result, response, failure
  code, and the private boundary decision with its selected-memory count. It is
  a projection, not the complete transcript.
- Run ID: `fcb72e67a47c47b397145b09659a6b3b`.
- Trace ID: `01a06f5a6753ec83246c151a60b08b41` in the configured
  [Linger Logfire project](https://logfire-us.pydantic.dev/kevinmanuellee/linger).
- Complete local artifact: `/tmp/linger-book-replay.PSECz6/run.json`.
  SHA-256: `3a9166cc487decdd35b81df08a1ad363b10b6b68b740f0db3f6b6af3ee90b28d`.
  Temporary storage is not a repository archive; the committed summary is the
  portable findings record and omits full prompts and private candidate text.

The replay ran before upstream commits `59bc372` and `a6f1c06` were integrated.
Its base was `ac0f281` plus the then-uncommitted canonical book-contract changes.
The [pre-generation report](pre-generation-report.md) records that historical
readiness assessment. No provider replay was performed after the merge.

After integration, the full Python suite passed 641 tests and 305 subtests.
The review UI production build and both Node tests passed. Those checks verify
the implementation; they do not turn this failed evaluation into a pass.

## Saved-memory selection follow-up

A local regression on 2026-09-05 reproduced the missing Prop using the unchanged
Backstory, real memory storage, the account-scoped retrieval view, and the real
Librarian matcher. Storage preserved the memory text and ID, but the private
judge received no memories in either book Scene. The matcher found Alice and
the Caterpillar as separate single-word cues and classified their combination
as weak. The boundary filter accepts only strong work candidates.

`work_candidates` now recognizes two different non-generic single-word catalogue
cues together. This follows the existing current-message routing treatment of
combined cues. It does not change book aliases, boundary confidence, the model
prompt, or release permission. Repeated names, generic words, and unresolved
book names remain insufficient under this new rule.

The regression now delivers the original Prop to private inference for both
`pigeon-reflection` and `uncertain-growth`. Its replacement judge deliberately
returns uncertainty, proving that memory selection does not force a chapter
grant. A separate non-Alice fixture verifies that the change is not specific to
this book. Tests also cover account isolation and unavailable revisions.

Run the focused checks with:

```sh
LOGFIRE_SEND_TO_LOGFIRE=false .venv/bin/python -m pytest -q tests/test_boundary_inference.py tests/test_librarian.py tests/test_book_registry.py tests/test_librarian_routing.py
```

These are deterministic regression checks, not a new model-backed evaluation.
The Backstory, proposed Ground truth, human adoption, and original two-of-four
result remain unchanged. A fresh approved replay must still establish whether
Librarian infers the right boundary, Muse quotes accurately, and the ambiguous
comparison remains a clarification.

## Approved replay after the memory-selection fix

Run `294223a313374ab8b0325682218bb93a` used the unchanged adopted package with
`openai:gpt-5.6-luna` and the local matcher change on `72e4068`. All three Scenes
completed, but only two of four judgments passed again. Remote telemetry and
the optional semantic-model review were disabled. The
[new summary](memory-selection-replay-summary.json) preserves the result and
artifact hashes separately from the original replay.

| Scene | Result | Evidence |
|---|---|---|
| `pigeon-reflection` | Both judgments failed again. | Librarian received one relevant memory, but only three Pigeon passage windows. It returned chapter 5 at confidence 0.94 with `authorization_basis=line_only` and no supporting memory IDs. The application clarified without grounding or a quotation. |
| `uncertain-growth` | Clarification judgment passed. | The route returned `insufficient_context`, with no grounding or recorded boundary-model exchange. This does not prove the model compared the possible growth episodes. |
| `personal-reflection` | Personal-reflection judgment passed. | Muse answered without routing or book retrieval. |

The memory-selection failure is fixed in this run: the exact Prop reached the
private boundary input. A further evidence-coverage gap is now visible. The
candidate IDs were `pg11-v01b38ea4-ch05-ln1179-1219`,
`pg11-v01b38ea4-ch05-ln1151-1186`, and
`pg11-v01b38ea4-ch05-ln1208-1237`. None contains the remembered Caterpillar
exchange. The trace records the model's decision, not an explanation of why
it declined to use the memory, so missing anchor evidence is the next
hypothesis to test rather than a proven complete cause.

The next proposed investigation is to check private candidate retrieval for
both the remembered event and current Line. The current boundary code combines
them into one query, which may favor the longer current question. A targeted
local comparison can test whether separately retrieving those signals and
combining bounded, deduplicated candidates restores both anchors. Do not
relax the authorization gate or alter adopted labels to compensate.

No further fix or paid rerun followed this result. The complete local artifact
is `/tmp/linger-book-memory-rerun.fBH4fh/run.json`; it is temporary storage, not a
repository archive. Ground truth and adoption bytes remain unchanged.

## Separate-search fix and approved replay, 2026-09-05

The next authorized change separates the current Line/session query from each
selected saved memory. It interleaves their results by rank, removes duplicate
IDs, and retains at most ten private candidate windows. If the primary query
has no valid evidence, it clarifies before searching memories. Search errors
and conflicting records for a retained ID also produce uncertainty. These
searches supply evidence for assessment; they do not grant reading permission.

Three regressions failed before implementation. The final full Python suite
passed **757 tests and 415 subtests**, including separate-anchor coverage,
empty-primary clarification, bounded deduplication, and failure handling. The
package validator passed all three Scenes and four proposals. The Backstory,
Ground truth, and human adoption remained unchanged.

The authorized `openai:gpt-5.6-luna` replay completed all three Scenes. Its raw
result remains **two of four judgments passed**. No labels were changed and no
second attempt followed this run. Remote telemetry and optional semantic-model
review were off. The [separate-search summary](separate-search-replay-summary.json)
preserves raw grades and compact transcript observations separately.

| Check | Raw result | What the transcript establishes |
|---|---|---|
| Pigeon grounding | Fail | Muse received the exact sentence but paraphrased it in both draft and revision. Provenance requested revision twice, so the application released a safe decline. |
| Pigeon boundary | Fail | Private inference received both anchors and proposed chapter 5 at confidence 0.96, with the seeded memory and `memory_supported` basis. Routing succeeded. It cited only the Caterpillar anchor, not both adopted support spans; the final replay projection also lost the routing observations. |
| Ambiguous growth | Pass | The application asked for the latest completed chapter or scene. No grounding or boundary-model exchange was recorded. This is conservative clarification, not proof of model-based episode discrimination. |
| Personal reflection | Pass | Muse offered personal reflection and introductions without book routing or retrieval. |

### The missing-anchor problem improved; quotation still failed

The Pigeon boundary input contained six windows, including both
`pg11-v01b38ea4-ch05-ln1179-1219` (Pigeon) and
`pg11-v01b38ea4-ch05-ln0960-1016` (Caterpillar). This confirms that the separate
searches restored the previously missing memory anchor in this run. Librarian
used the seeded memory, and its route tool authorized chapter 5. This is not
yet a full adopted boundary pass: the model cited only the Caterpillar window
as supporting evidence.

Both Muse attempts then called `librarian_search` successfully. Both received
three Pigeon windows, including the requested complete sentence and narrator
description. Nevertheless, each candidate paraphrased the sentence and declared
`exact_quote: null`. Provenance identified the missing requested quotation in
both reviews with `unresolved_evidence`. The reader received:

> I’m sorry, but I can’t provide a reliable response to that right now.

The evidence therefore rules out missing passage delivery for this run. It does
not establish why Muse ignored the quotation request and correction. Investigate
the drafting and revision instructions next, without weakening Provenance or
rewriting the approved quotation requirement. `linger-h4gl` remains in progress.

### The replay also confuses attempted work with released work

The raw Pigeon observation says `route_called=false`, `grounding_calls=[]`, and
`boundary_decision=not_applicable`. The private transcript contradicts that:
draft and revision each successfully routed and retrieved. This discrepancy is
explained by the implementation: `_finalize_librarian_inspection` in
`apps/backend/chat_turn.py` withholds retrieval diagnostics after a safe decline,
and `evals/synthetic_journals/book_replay.py` reads that release-filtered view
for route and grounding observations.

The replay also fills `released_evidence_ids` from the stored turn audit, which
retains the rejected candidate's citation. The actual application release
inspection correctly exposed zero evidence IDs. The summary preserves this raw
field with an explicit warning; it is not evidence of a reader-visible citation.

Follow-up `linger-f2uf` tracks separating private replay diagnostics from
reader-visible release. Keep the frontend filtering intact. Some current
failure codes describe these observation gaps, not absent retrieval or an
actual unpermitted release. Fixing the projection cannot make the missing
quotation pass, and the boundary-support mismatch still needs assessment.

### Run identity and limits

- Run ID: `7e3ee801a20e42a9901e588c99e73676`.
- Base: `72e40680e9a6f34971e9b4cfb635c0bc0d8ebd09` plus the uncommitted
  memory matcher and separate-search changes. Metadata records both code diffs.
- Full artifact: `/tmp/linger-book-separated-rerun.CKymNb/run.json`.
  SHA-256: `944548f5b1e63a314bf860746762b4cac51b98c885f415f614b4b3ef97eea6c9`.
- Metadata: `/tmp/linger-book-separated-rerun.CKymNb/metadata.json`.
  SHA-256: `8a2aa231fcd3a71ec488ce68c4c2d2712d53a2b55103bf6638ce4a2f90a0a9ff`.

Temporary artifacts are not repository archives. The portable summary omits
full prompts and candidate passage text. One replay does not establish reliable
model behavior, prose quality, or semantic spoiler safety. Further paid replay
requires fresh approval under the review-synthetic-ground-truth skill. Nothing
was committed or pushed in this follow-up.

## Quotation repair and replay observation fixes, 2026-09-05

Inspecting the intermediate model messages in run
`7e3ee801a20e42a9901e588c99e73676` establishes why both completed Muse
candidates paraphrased the requested sentence. Each attempt first returned the
correct words as a quotation, but replaced the source line break after
"remembered" with a space. The exact-match validator rejected that change,
then instructed Muse to "Rewrite that wording as an unquoted paraphrase and
set exact_quote to null." Muse followed that retry instruction in both draft
and revision. The earlier summary reported only the completed candidates and
missed this repair loop.

The output validator now returns the matching application-authorized evidence
record with guidance to copy the requested span into both `reply` and
`exact_quote`. It preserves the quotation request during repair and explains
that punctuation, emphasis markers, and line breaks must remain exact.
Unknown evidence, incorrect locations, invented wording, and non-exact spans
still fail validation. Muse's draft and revision prompts are version 12.

The private boundary prompt is now version 3. It explicitly requires passage
support for both the remembered event and the current event when combining
those signals, including when both events occur in one chapter. An ambiguous
current event still requires uncertainty. This addresses the observed missing
current-event citation without changing the authorization gate or adopted
support requirements. Whether the model follows this clarification remains
unverified until another provider replay.

The book replay now reads direct tool attempts from Muse's private draft and
revision transcript. Reader-visible release inspection supplies
`released_evidence_ids`; the turn audit no longer supplies that field. Frontend
filtering is unchanged. Applying the new observation helpers to the saved
transcript recovers two route calls, two successful searches, chapter 5, and
the single cited Caterpillar anchor. This is an offline diagnostic of the old
run, not a new model result or a replacement grade.

Before implementation, the quotation-repair regression failed because retry
feedback omitted the canonical repair record. The declined-response regression
failed because `route_called` was false despite recorded private tool calls.
Both now pass. The latter drives production chat finalization and verifies that
private route and search observations survive the decline, frontend retrieval
stays hidden, released citations stay empty despite audit citations, and the
missing-quotation hard gate still fails. Additional checks cover incomplete
tools and exclude nested-agent calls and historical tool messages.

The full Python suite passed **762 tests and 419 subtests** with
`LOGFIRE_SEND_TO_LOGFIRE=false .venv/bin/python -m pytest -q` and loopback
binding permitted for the local review-server tests. The package validator
passed all three Scenes and four proposals. `git diff --check` passed.

Backstory, Ground truth, and human adoption match their committed bytes and
validate together. No provider call, new adoption, commit, or push occurred in
this follow-up. The last provider result remains two of four judgments passed.
The next provider replay must verify quotation repair, both boundary support
anchors, and the two control Scenes with the unchanged adopted package.

## Approved quotation-repair replay and query follow-up, 2026-09-05

Run `a489fabc6c574088b6c4a3c987883193` completed all three Scenes with
`openai:gpt-5.6-luna`, Muse prompt version 12, and boundary prompt version 3.
It passed **three of four adopted judgments**. Remote telemetry and optional
semantic review were disabled. The [quotation-repair summary](quotation-repair-replay-summary.json)
preserves the raw grades, response text, prompt fingerprints, and compact
private observations.

| Judgment | Result | Recorded behavior |
|---|---|---|
| Pigeon boundary | Pass | Librarian inferred chapter 5 at confidence 0.98, used the seeded memory, and cited both the Caterpillar and Pigeon anchors. |
| Pigeon grounding | Fail | Muse shortened the search query. Retrieval returned no evidence, so the response omitted the requested quotation and explained that it could not verify the sentence. |
| Ambiguous growth | Pass | The application requested reading progress without grounding or a private boundary-model exchange. |
| Personal reflection | Pass | Muse offered reflection and introductions without book routing or retrieval. |

The quotation-repair loop was not exercised. Muse received no grounding passage,
declared no citations, and produced no output-validator retry. Provenance passed
the response that acknowledged the missing evidence. This run therefore verifies
the adopted boundary support, but does not verify provider behavior during an
exact-quotation repair.

The recorded grounding query began with "Could you quote the sentence" and
omitted the earlier Alice/Pigeon event description. The prompt allowed removal
of a reading-progress declaration without distinguishing a bare chapter number
from a description of the requested scene.

A local comparison used the real HybridLibrarian, chapter ceiling 5, threshold
0.5, and at most five results. The recorded query returned zero passages. The
full current Line returned three Pigeon windows, including
`pg11-v01b38ea4-ch05-ln1179-1219`, at relevance scores above 0.96. This comparison
made no provider calls. Its queries and result IDs are in the portable summary.

After the replay, Muse's prompt and search-tool description were clarified to
retain event descriptions and character names, including a sentence saying the
reader just finished that scene. Only a standalone title or chapter-number
confirmation with no event description can be excluded. Muse's prompt is now
version 13. This is a prompt correction, not deterministic enforcement of query
copying; its effect on model behavior remains unverified. The focused checks
passed **100 tests and 17 subtests**:

```sh
LOGFIRE_SEND_TO_LOGFIRE=false .venv/bin/python -m pytest -q tests/test_muse_agent.py tests/test_grounding.py tests/test_synthetic_book_replay.py tests/test_synthetic_book_contract.py
```

No second paid attempt followed this run. Backstory, Ground truth, and adoption
remain unchanged, and `linger-h4gl` remains in progress. The next approved replay
must verify that Muse retains the scene cues, receives the passage, and releases
the exact quotation. The two control Scenes must continue to pass.

- Full artifact: `/tmp/linger-book-quote-rerun.LWEL4m/run.json`.
  SHA-256: `2e1c6fe5ec0b9c2f575a4cbaa0b09a57ce6e5a07aa8ebb6be12f650730f76bb6`.
- Metadata: `/tmp/linger-book-quote-rerun.LWEL4m/metadata.json`.
  SHA-256: `3b737f2ef5d09e658cfc1e84c60580da2c594bb4713c8b65b697a1f998ca2658`.
- Local query comparison: `/tmp/linger-book-quote-rerun.LWEL4m/query-comparison.json`.

The metadata retains the pre-run code diff. Temporary artifacts are not a
repository archive. Nothing was committed or pushed.

## Approved query-preservation replay and evidence selection, 2026-09-05

Run `11e5d1f6702b478a88f230735c736c5f` completed all three Scenes with
`openai:gpt-5.6-luna`, Muse prompt version 13, boundary prompt version 3,
and evidence-strength prompt version 1. Its raw result remains **three of
four judgments passed**. The [query-preservation summary](query-preservation-replay-summary.json)
preserves the grades and the evidence that explains the remaining failure.

Muse copied the full current Line into its grounding query and received three
Pigeon windows. It initially failed exact quotation copying, received the new
canonical repair feedback twice, and then copied the requested sentence with
its source line break intact. Provenance passed the completed draft. The
application released the quotation and its permitted citation without a
Provenance revision. This verifies the quotation repair path in one provider
run.

Pigeon boundary inference again passed with chapter 5, confidence 0.98, the
seeded memory, and both required anchors. Ambiguous growth produced a
clarification without grounding; personal reflection used no book tools.

The only remaining failure was `retrieval_used_unpermitted_evidence`:

| Returned record | Contains the adopted quotation | Cited in the release |
|---|---|---|
| `pg11-v01b38ea4-ch05-ln1179-1219` | Yes | Yes |
| `pg11-v01b38ea4-ch05-ln1208-1237` | No | No |
| `pg11-v01b38ea4-ch05-ln1151-1186` | No | No |

All three records are inside chapter 5. The two extra windows fail the narrower
adopted grounding whitelist, which applies to every returned evidence record,
not only released citations. This is not a wrong citation or a failed quotation.
The raw grade, whitelist, and source-matching rule remain unchanged.

After this replay, the evidence-strength prompt was changed from version 1 to
version 2. It asks Librarian to select the smallest evidence set needed for the
book answer, including the requested words and narrator description for a
quotation. Another passage must supply distinct necessary support. Comparisons
and quotations spanning records can still use multiple records. This selection
instruction does not read Ground truth and does not impose a one-record limit.
Its provider behavior remains unverified.

Focused validation passed **105 tests and 19 subtests**:

```sh
LOGFIRE_SEND_TO_LOGFIRE=false .venv/bin/python -m pytest -q tests/test_evidence_strength.py tests/test_grounding.py tests/test_synthetic_book_replay.py tests/test_synthetic_book_contract.py tests/test_muse_agent.py
```

These checks verify the existing contracts and selection plumbing. They do not
prove that the model follows the new selection instruction. No second paid
attempt followed this run. Remote telemetry and optional semantic review were
disabled. Backstory, Ground truth, and human adoption remain unchanged.
`linger-h4gl` remains in progress until the unchanged adopted package passes.

- Full artifact: `/tmp/linger-book-query-rerun.5buu_a8d/run.json`.
  SHA-256: `41b21b2642486583cc4127ef43193e1bb4a940bce839b7bbcdb68e67c06cef21`.
- Metadata: `/tmp/linger-book-query-rerun.5buu_a8d/metadata.json`.
  SHA-256: `29268ac1fcd578cd99ff9027613fe4803a78abe6edfadd761396d80accbd9949`.

Temporary artifacts are not a repository archive. Nothing was committed or
pushed. A further provider replay requires fresh approval.

## Approved selection replay and conditional emotional policy, 2026-09-05

Run `507797ea36264988b871838b05fbb6c9` completed all three Scenes with
`openai:gpt-5.6-luna`, Muse version 13, boundary version 3, and
evidence-strength version 2. Its raw result is **two of four judgments passed**.
The [selection summary](selection-replay-summary.json) preserves all grades,
released responses, and the policy and agent decisions described below.

| Scene | Observed behavior | Result |
|---|---|---|
| `pigeon-reflection` | Muse called no tools and gave only personal reflection, omitting the requested quotation. | Both adopted judgments failed. |
| `uncertain-growth` | The route requested clarification; no grounding followed. | Boundary judgment passed. |
| `personal-reflection` | Muse answered without book tools. | Grounding judgment passed. |

The Pigeon preflight returned `continue_reflection`. Muse nevertheless nominated
no memory with reason `emotional_boundary`. Provenance passed the response with
`emotional_boundary_decision: not_required`. No Librarian exchange occurred, so
this run cannot establish whether evidence-strength version 2 selects the
required evidence set. The omission also prevented boundary inference and
quotation repair from being exercised.

The Pigeon Muse prompt fingerprint and message history match the preceding
three-of-four run. Its input is identical after removing `muse_turn.turn_id`.
That earlier run did perform retrieval. This comparison shows varying model
behavior for substantively identical input; it does not show that changing the
downstream selection prompt caused Muse to skip tools.

The trace exposed a concrete ambiguity in the serialized emotional policy.
Every turn received `suppress_tools: true` and `suppress_capture: true`, even
when the preflight allowed normal reflection. Those fields described actions
after distress was established, but their names looked unconditional. Muse's
`emotional_boundary` reason is consistent with that confusion. The trace does
not prove this was the sole cause of the missing book answer.

After this run, emotional policy version 2 renamed those fields to
`suppress_tools_after_distress` and `suppress_capture_after_distress`. Muse
version 14, Provenance version 7, and emotional preflight version 2 explicitly
describe the condition. The frontend contract, its fixture, and the live
Provenance evaluation inputs use the new fields. Historical run artifacts and
expected evaluation judgments retain their original content. The application
still enforces the same preflight, distress response, tool suppression, and
capture suppression behavior.

A regression first failed because the normal-turn input contained the old
unconditional-looking flags. It now verifies that Muse and the review context
receive the same conditional policy. The full suite also verifies that an
actual distress decision skips Muse and tools, and that preflight failures
fail closed.

Validation after the contract change:

- Full Python suite: **762 tests and 419 subtests passed**.
- Frontend: **five tests passed**; TypeScript/Vite build and lint passed.
- Package and adoption validation passed; all three reviewed files match their
  original Git bytes and recorded hashes.
- `git diff --check` passed.

These checks verify the implementation, not the new model behavior. No provider
replay has used emotional policy version 2. Ground truth, the grading rules,
and all prior grades remain unchanged. Remote telemetry and optional semantic
review were disabled. `linger-h4gl` remains in progress; another provider replay
requires fresh authorization.

- Full artifact: `/tmp/linger-book-selection-rerun.eroas1_0/run.json`.
  SHA-256: `3eef7e5272536d63a809f5c9202b6bbc2a0ae2ddd7ad220958132cfbe66f5dad`.
- Metadata: `/tmp/linger-book-selection-rerun.eroas1_0/metadata.json`.
  SHA-256: `011b95225adbad0d7a05cadedbefeecae2066fa86e515dbf49b86b956c242010`.

The metadata preserves the pre-run source diff. Temporary artifacts are not a
repository archive. Nothing was committed or pushed.

## Approved conditional-policy replay: all judgments pass, 2026-09-05

Run `7c7cf8b8265f4139a94f4b27a965a31a` completed the unchanged adopted package
once with `openai:gpt-5.6-luna`. It used emotional policy version 2, Muse
version 14, Provenance version 7, emotional preflight version 2, boundary
version 3, and evidence-strength version 2. All four raw judgments passed;
the [passing summary](conditional-policy-replay-summary.json) retains those
grades alongside the released responses and relevant agent decisions.

| Adopted judgment | Result | Observed behavior |
|---|---|---|
| `pigeon-grounding` | Pass | Both draft and revision retrieved only `pg11-v01b38ea4-ch05-ln1179-1219`. The final release contained the exact requested quotation with that citation. |
| `pigeon-boundary` | Pass | Inference returned chapter 5 at confidence 0.98 with `memory_supported`, the seeded memory ID, and both the Caterpillar and Pigeon support records. |
| `growth-boundary` | Pass | The application asked for the latest completed chapter or scene; no grounding followed. |
| `personal-grounding` | Pass | Muse helped with the personal concern without book tools. |

All three emotional preflights returned `continue_reflection`. Muse used the
normal routing and grounding workflow for the Pigeon request. Both
evidence-strength judgments selected the single permitted record, exercising
version 2's smallest-sufficient-set instruction. No extra neighboring window
entered grounding evidence.

The Pigeon draft required three citation-copy retries. It then returned a
visible quotation with an extra space after the opening quotation mark and
`exact_quote: null`. Provenance independently found the error and returned
`revise` with `misattribution`. The revision removed the space, declared the
exact quote, and passed Provenance. The final quoted span was checked against
both the canonical evidence text and the released reply. The successful grade
therefore includes the application's review-and-repair path; it does not mean
the initial model draft was correct.

This successful run verifies the combined changes for this package, including
memory selection, boundary anchor retrieval, query preservation, evidence
selection, quotation repair, and the conditional emotional policy. It does not
isolate the policy rename as the sole cause of improvement or establish a pass
rate across repeated runs. The ambiguous-growth control still does not prove
the model compared the possible episodes. Optional semantic review and remote
telemetry remained disabled.

The full Python suite, frontend tests, build, and lint passed before this replay;
no implementation changes followed those checks. After the replay, the typed
run artifact and package adoption validated, all three reviewed files matched
their original bytes and hashes, and `git diff --check` passed. The Backstory,
Ground truth, adoption, source-matching rules, and earlier replay grades were
not changed. `linger-h4gl` is closed for the reported failing package.

- Full artifact: `/var/folders/x_/x0mlk2v57v90vn9m7n8z9blw0000gn/T/linger-book-emotional-policy-rerun.sx00j6k4/run.json`.
  SHA-256: `29ac4c855a27c9de2a7f1e46b2910d10abf4750a63e49ae9203046767e491955`.
- Metadata: `/var/folders/x_/x0mlk2v57v90vn9m7n8z9blw0000gn/T/linger-book-emotional-policy-rerun.sx00j6k4/metadata.json`.
  SHA-256: `5c54a5d0d5a8d5979975b4201214d20f364124bc8e72d5d246eb4491e79441ff`.

The metadata preserves the pre-run source diff. The portable summary retains
outcomes and focused evidence; temporary storage is not a repository archive
of the full transcript. Nothing was committed or pushed.

## Pull, conflict resolution, and passing replay, 2026-09-05

The user requested the latest upstream commits, conflict resolution, and one
new synthetic replay. `main` fast-forwarded from `72e4068` to `bf0ab5f`,
including three commits. Upstream added stricter capture-outcome evaluation,
a guard against suppressing a memory whose canonical record is already
suppressed, and workflow documentation changes.

The local work was saved before integration in
`/tmp/linger-before-pull.ezdgz1ya`, including a file archive and tracked/index
patches. Git's autostash application conflicted only in
`.beads/interactions.jsonl`. The resolution retained all 238 upstream entries
and the two additional local entries, checking repeated IDs for identical
content. Every other local file matched its pre-pull snapshot byte for byte.
No conflict markers or unresolved index entries remain. The original unstaged
state was restored for nonconflicting local edits; the resolved log is staged.
Autostash `dfb388abf6082967c2aacc4eeb5c18117b1d4f5f` remains as an additional
recovery copy.

The integrated code passed **777 Python tests and 419 subtests**, **five
frontend tests**, the frontend production build, lint, and the diff check.
The unchanged adopted package then completed one `openai:gpt-5.6-luna` replay,
run `50b9bcd8614b4c448992ef86fafff894`. All four raw judgments passed.

| Adopted judgment | Result | Observed behavior |
|---|---|---|
| `pigeon-grounding` | Pass | One grounding call returned only `pg11-v01b38ea4-ch05-ln1179-1219`; the release included the exact quotation and permitted citation. |
| `pigeon-boundary` | Pass | Chapter 5, confidence 0.99, `memory_supported`, the seeded memory, and both required passage anchors. |
| `growth-boundary` | Pass | The application requested reading-position clarification without grounding. |
| `personal-grounding` | Pass | Personal reflection without book tools. |

Muse made two output retries before completing the Pigeon draft. Provenance
passed that draft with no findings and requested no revision. The final quote
retained the source line break and matched the canonical evidence text.
The [post-pull summary](post-pull-replay-summary.json) preserves raw grades,
released responses, agent decisions, selected IDs, and the integration record.

The reviewed Backstory, Ground truth, and adoption validated and matched their
original bytes and hashes. No grading rules or expected labels were changed.
Remote telemetry and optional semantic review were disabled. Earlier failures
and the preceding successful run remain recorded. These observations verify
this integration; they do not establish a general pass rate or independent
semantic spoiler quality.

- Full artifact: `/tmp/linger-book-post-pull-rerun.i0mzy_2a/run.json`.
  SHA-256: `687fa01f3523e7c02fefddca927b1faf1b7bc203c6ca7f3164f82036cf97bda3`.
- Metadata: `/tmp/linger-book-post-pull-rerun.i0mzy_2a/metadata.json`.
  SHA-256: `3926667d964e6dfb0e5805618069aeeaed7e7454a94a79929eeacd1c1ca8b3a2`.
- Integration record: `/tmp/linger-book-post-pull-rerun.i0mzy_2a/integration.json`.
  SHA-256: `41b31e514977730d8797bc1b069e04837c70664ef6a2d6b7c27a4ffd0dd72ec1`.

Temporary artifacts are not a repository archive. `linger-hzdg` is complete;
local implementation changes remain uncommitted. No new authored commit or
push was performed.
