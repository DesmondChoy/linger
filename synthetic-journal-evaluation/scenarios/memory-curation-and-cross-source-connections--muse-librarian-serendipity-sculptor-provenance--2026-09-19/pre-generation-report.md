# Memory curation and cross-source connections

## Decision

The implementation is **sufficient** for the complete [Scenario](../../../docs/specification.md#721-canonical-vocabulary) requested in [issue #57](https://github.com/DesmondChoy/linger/issues/57). Keep all five registered books available and evaluate all five agents across nine Scenes. The authorized prerequisites are implemented. The revised data is generated and awaits independent human review. Provider execution requires adoption and configured credentials.

The human requested natural shorthand in Scenes 06 and 07, plus a harder question that names no books. Scenes 06 and 07 name no authors or full titles; after review they carry brief, reader-style hints to the Caterpillar, Pinocchio's promised return to the Fairy, and Keller's lake holiday, so their exact required passages are fair. Scenes 08 and 09 ask whether anything the reader has read can illuminate a remembered promise, a tempting alternative, and an excuse for delaying preparations. Each pair contrasts a tentative connection with an unsupported claim that a changed mood cancels the promise.

| Book available in all four connection Scenes | Confirmed limit | Scenes 06–07 | Scenes 08–09 |
|---|---|---|---|
| Alice's Adventures in Wonderland | Chapter 5 | Required | Optional support |
| The Adventures of Pinocchio | Chapter 30 | Required | Required |
| The Story of My Life | Part I, Chapter 22 | Required | Optional support |
| Animal Farm | Chapter 10 | Excluded from retrieval | Search allowed; excluded from final support |
| Narrative of the Life of Frederick Douglass, an American Slave | Chapter 11 | Excluded from retrieval | Search allowed; excluded from final support |

The system receives all five book permissions and the original Line. For Scenes 06 and 07, targeted grading checks the three requested books at search, raw retrieval, exact evidence, and citation stages. For Scenes 08 and 09, exploratory grading permits searches and raw results from all five books. It requires Pinocchio's promise and rationalization for delay as exact support, alongside Maya's memory and Hume. Alice and Keller can be omitted; if used, their evidence must match the proposed permitted passages, which include both Alice's Chapter 2 and Chapter 5 reflections on being changed. Scenes 08 and 09 check Hume's bundle sentence, which their Lines echo. Selected connection evidence and final citations remain bounded in both modes. These expectations never enter runtime.

All five curation proposals, existing Scene definitions, Prop source texts, and public snapshots are preserved. The connection Scenes pair the situated-self note with the September reading-schedule revision as a near-miss distractor; the kitchen repair remains only in Scene 03. Whether the proposed source choices make a useful comparison remains an independent human judgment.

The review server now waits for a decision by default. An explicit `--timeout` remains available. Navigation preserves the session token, and a lost server connection produces a recovery message. The previous `make_changes` decision was recovered with proposals 06 and 07 flagged; its hashes identify the earlier files and authorize no adoption of this revision.

Statuses below reflect the revised implementation. Offline verification establishes execution contracts; it does not establish model quality.

| Planned Scene | Target behavior | Status | Evidence or gap |
|---|---|---|---|
| C1 | Link exact duplicates without deleting originals. | runnable | Combined contract and curation regressions pass (G1–G3). |
| C2 | Recognize paraphrased duplication without treating an update as duplication. | runnable | Existing five-behavior requirement remains enforced. |
| C3 | Summarize one evolving fact and exclude noise. | runnable | Source-grounded expectation preserved; semantics remain reviewable. |
| C4 | Group related but independently meaningful facts. | runnable | Typed grouping and source preservation checks; human semantic review. |
| C5 | Leave superficially similar, unrelated records alone. | runnable | No-change short-circuit and unchanged adopted expectations verified. |
| X1 | Compare personal memory, three requested books, and Hume tentatively. | runnable | All-five permissions, three-book selection, exact source resolution, and reviewed release are covered. |
| X2 | Inspect the same sources and qualify or decline the claim that a changed mood cancels a promise. | runnable | Required retrieval and excluded-book checks apply even when the reply declines the inference. |
| X3 | Discover a textual connection from a title-free question about postponing a promise. | runnable | All granted books may be searched; required and optional support are checked separately. |
| X4 | Explore the same clues and qualify or decline the claim that the promise no longer counts. | runnable | Broad search is allowed, while final support remains bounded. |

Curation evaluates proposals, permitted sources, original preservation, and no change. Connection evaluates supported exploration through reviewed response release. Curation application and retrieval remain recorded product outcomes; optional adopted constraints are preserved without adding hidden requirements.

## Your selection

- **Bounded memory curation** (`bounded_memory_curation`): Sculptor proposes links, groups, or summaries using supplied memories, preserves originals, and leaves unrelated records alone.
- **Cross-source tentative connection** (`cross_source_tentative_connection`): Serendipity explores authorized memories, book passages, and public evidence; Muse cites support, private wording stays out of web queries, and Provenance checks unsupported certainty.

The selector confirmed this order at `2026-09-19T14:42:55+08:00`; its catalog identifier and SHA-256 matched the inspected catalog (`494798da789f`). Later changes add replay support metadata only; the selected Objective text and scope remain unchanged.

## Target evaluation design

Use the [canonical vocabulary](../../../docs/specification.md#721-canonical-vocabulary). One corpus-backed Scenario contains the following entities.

| Term | Application to this plan |
|---|---|
| Objective | Exactly the two confirmed IDs above. All five agents participate across the evaluated paths. No capture, retrieval-ratio, spoiler-inference, or surfacing Objective is added. |
| Backstory | One person and one evaluation account, with a coherent history of reading and accumulated personal reflections. It informs authoring only. Discover current registered works, versions, structure, and evidence at generation time. |
| Prop | Separate earlier same-account originals. Supply only records needed for the five curation behaviors and connection contrasts; every record has a designated Scene and active lifecycle. Reuse appropriate originals across Scenes explicitly. Connection relevance covers every available Prop. Curation-created records are observed outcomes and are not seeded into the connection Scenes. |
| Scene | Exactly nine: C1–C5, then X1–X4. Five isolated Props-only curation Scenes cover each accepted behavior once. Two pairs of fresh-session connection Scenes contrast useful support with overreach, first with shorthand book names and then with title-free discovery. Each uses its own designated starting snapshot under one account; no observed-state dependency is asserted. |
| Line | Exactly four natural user inputs, one per connection Scene. Curation has no Lines. There are no `OfflineInput` records. Capture enablement, source grants, and session reset are workflow state. Automatic capture stays disabled during connection execution. |
| Ground truth | Nine separate proposals, one per Scene/Objective pair, anchored to exact source spans and evidence. Connection proposals include complete Prop relevance and an honest declared comparison. Curation proposals specify actions, sources, preservation, and no change. Generator proposals become adopted Ground truth only after independent human review; `run_configuration_ids` is empty. |

[`models.py`](../../../evals/synthetic_journals/models.py) defines `SyntheticBackstory`: `backstory`, `props`, `scenes`, `lines`, empty `offline_inputs`, and connection `source_setups`. Each source setup holds a `book_scopes` array with one reader-confirmed version and chapter ceiling per available work, plus complete public snapshots. `ProposedGroundTruth` separately contains the exact Backstory-file hash, `ground_truth_status: proposed`, and typed proposals. [`validate_scenario.py`](../../../evals/synthetic_journals/validate_scenario.py) checks these structures; its compiler now accepts this exact selection while validating the whole Scenario.

## Current implementation and required work

**Observed.** All five registered corpora are enabled locally and pass corpus integrity checks. Their availability grants no unrestricted reading access. The current components implement these product paths:

| Scenes | Setup, authority gates, state changes, terminal outcome, and evaluation endpoint |
|---|---|
| C1–C4 | Memory Policy resolves active same-account originals; tool-free Sculptor proposes an action; application code binds the proposal to source hashes and current state; tool-free Provenance reviews that digest; exact `allow` reaches deterministic policy/application/audit verification. Originals remain unchanged. The resulting retrieval projection is the terminal product state. Invalid sources/verdicts fail; `revise`/`reject` produce no application. The catalog endpoint is proposal quality and source preservation; explicitly supplied outcome constraints also apply, while empty outcomes stay unconstrained. Sources: [`curation.py`](../../../src/linger/orchestration/curation.py):243–298, [`memory.py`](../../../src/linger/services/memory.py):184–260, [`curation_replay.py`](../../../evals/synthetic_journals/curation_replay.py):439–510. |
| C5 | Same bounded originals reach Sculptor. No proposal verifies original preservation and returns `no_change`, skipping Provenance and application. Its terminal product state and selected endpoint both require unchanged originals. Source: `curation.py:253–261`. |
| X1–X4 | Isolated Props, one Line, five trusted book scopes, and public snapshots enter production chat with capture disabled. Provenance preflight may stop the path. Otherwise Muse requests Serendipity exploration; authorized memory search, shared Librarian planning/retrieval/assessment, and guarded public retrieval supply evidence. Serendipity proposes or declines; Muse drafts; Provenance reviews, with bounded revision; deterministic checks release a reply or fallback. No memory changes occur. The Objective endpoint is that reviewed release with correct evidence and source preservation. Preflight stops and provider/retrieval/review failures remain explicit failures for the intended connection contrast. Sources: [`chat_turn.py`](../../../apps/backend/chat_turn.py):855–890, [`connection.py`](../../../src/linger/orchestration/connection.py):111–234, [`reflection.py`](../../../src/linger/orchestration/reflection.py):568, [`connection_replay.py`](../../../evals/synthetic_journals/connection_replay.py):198–351. |

**Observed after implementation.** The following prerequisites are resolved in the working tree under Bead `linger-ak0g`.

| Resolved prerequisite | Original gap | Implementation and acceptance evidence |
|---|---|---|
| G1 — contract composition | The connection compiler rejected curation. | `connection_contract.py` accepts exactly this pair, preserves original objects and all proposal coverage, and compiles connection Scenes only. Whole-Scenario validation still enforces all five curation behaviors. Completion and invalid-input regressions pass. |
| G2 — adapter and grading | No combined replay route existed. | `connection_curation_replay.py` executes every Scene in order using shared component helpers, one account, isolated stores, original hashes/adoption, and real production Provenance. Failed Scenes receive durable error observations while later independent Scenes continue. Registry and review routes cover both selection orders. |
| G3 — source and grading authority | Compilation replaced even adopted `curation.outcome` constraints. | `curation_scene_input` preserves the stored expectation. Explicit rejection/retrieval constraints and empty outcomes have regressions. `actual_outcome` records product behavior separately and is retained by scenario analysis. Catalog scope is unchanged. |
| G4 — source input | No public snapshot had been supplied for this run. | Reuse independently adopted Hume Texts Online snapshot `https://davidhume.org/texts/t/1/4/6`, captured `2026-09-12T03:48:30.943742Z`, text SHA-256 `8cc5c9f4fc00573a39026f6a0895d91841f4bae6c317898e4141ecf44cebf97f`. The exact snapshot was extracted and hash-verified without exposing its previous Scenario to the generator. |

The additional prerequisites are implemented under `linger-snbj`. Connection compilation resolves both chapter and section catalogs through the existing corpus reader. Keller section 024 resolves to Part I, Chapter 22. Multi-book runtime permissions pass through Muse, Serendipity, Provenance, and final release without assigning a primary book. Serendipity chooses a subset using registered titles and IDs. Private retrieval observations expose wrong-book searches and raw results to grading. Irrelevant Prop evidence remains visible to reviewers without becoming mandatory retrieval.

Focused verification covers both Objective orders, interleaved Scenes, same-account isolation, exact adoption bytes, real curation agent defaults, optional outcome preservation, and failure reporting. The initial combined implementation passed 2,019 tests and 676 subtests. The revised runtime, grading, and reviewer have separate verification recorded below. Provider requests were disabled; no live combined evaluation is claimed.

| Inspected revision | Material change |
|---|---|
| `63e1834af91e6c356a1784bad82e18de4abd21e8` (planning HEAD) | Removed historical run outputs; no fresh evaluation evidence follows from that cleanup. |
| `6bed42800f5f14cb16677ff6a7f64b7dc29fc025` | Strengthened shared Librarian retrieval and evidence/release checks. |
| `4f088257da688bcfbd4fb9ab19deb1e9f5f6ad9f` | Preserved reader/book context and exact supplied public-URL privacy exceptions. |
| `493a30457b16bee2f357197f45a2ef0d951d677f` | Switched standalone curation replay to the reviewed application loop. |
| `ace8e3e0b975d61d9712318b8fef367283e9ea4e` | Added loop-outcome grading and the expectation replacement in G3. |
| `8dbcb9968e30c76b286d12d200dce802bf03ee7a` | Introduced the connection compiler and restricted replay selection. |

Relevant Beads were read individually: closed `linger-a4u.5` establishes the product curation loop; closed `linger-jra` establishes the narrower evaluation endpoint; closed `linger-r9oc` supplies composition/completion precedent. In-progress `linger-a4u.1` and open `linger-a4u.1.4` concern evaluation authority and semantic calibration. Open `linger-a4u.3` addresses retrieval benefit separately; capture/surfacing tasks `linger-a4u.4` and `linger-se5h` do not block this Props-based design.

The original planning snapshot was `63e1834`. Commit `d62a9ad9` contains the combined replay and readable reviewer. The current uncommitted revision adds book selection, retrieval observations, grading, and reviewer recovery. `HEAD` alone does not reproduce these changes. The following fingerprints and timestamp record the initial planning phase.

| Material file | SHA-256 prefix |
|---|---|
| Objective catalog | `2ec0e7963249` |
| `models.py` / `validate_scenario.py` | `c8d4d998d4cc` / `eecc9824638b` |
| `connection_contract.py` / combined replay | `7e053f26fa65` / `51027c8b6967` |
| `curation_replay.py` / completion | `de6d70b557ef` / `9dcec43607aa` |
| Replay registry | `43634daa08b2` |
| Academic briefing PDF | `1fd4ef3a561d` |

Repository snapshot: `2026-09-19T15:33:55.695575+08:00`; `main@dfe983089f6c4c1cfa7902b386f6c572f8f805cd`; dirty with authorized prerequisites and pre-existing unmerged `.beads/interactions.jsonl`; catalog `synthetic-journal-evaluation-objectives`, SHA-256 `2ec0e7963249f66b2330adec9850f763222e1a4d551b378810176329bc6f7e07`.

## Expected behavior and evaluation

These are input descriptions and response hypotheses, not authored Lines or exact-response oracles. Only X1–X4 contain Lines; curation uses Props directly, with no offline-input records.

| Scene | Representative input pattern | Likely behavior and plain-language success check |
|---|---|---|
| C1 | Two identical earlier reflections. | Link their IDs; preserve both source texts. |
| C2 | The same fact expressed differently. | Link genuine duplicates; preserve material distinctions. |
| C3 | One preference evolves across notes, alongside noise. | Summarize only that evolution using the relevant originals. |
| C4 | Several different experiences share a meaningful topic. | Group them without presenting distinct facts as duplicates. |
| C5 | Similar words describe unrelated experiences. | Return no proposal and leave originals unchanged. |
| X1 | A personal question invites a connection with a bounded book passage and supplied public context. | Inspect and cite all three source kinds; present useful interpretation tentatively without leaking private wording into search. |
| X2 | A nearby question asks more than those sources establish. | Explain the limitation, qualify, or decline while remaining helpful. Failed execution or review is not a successful decline. |
| X3 | A title-free question describes a promise, temptation, and rationalizing delay. | Find Pinocchio's promise and later excuse; use Alice or Keller only if useful. Distinguish literary support, personal memory, and Hume's observation. |
| X4 | The same clues ask whether a changed mood ends the promise. | Inspect the relevant support and qualify or decline the conclusion without forcing optional sources into the answer. |

## Original generation prompt

This prompt records the completed initial generation. Its single-book restriction is superseded by the revision brief below. Do not rerun it against the revised files. The report itself is never supplied to the generator.

```text
STATUS: Runnable after human approval — generation approval recorded

PRECONDITIONS
Stop without writing output unless all of the following are satisfied:
1. The repository's existing scenario validator and curation completion support
   the exact combined selection below without dropping either Objective or any
   of its Scenes (G1).
2. A registered combined replay preserves Scene identities, independent adoption,
   complete results, source isolation, and real review gates (G2).
3. The authorized reconciliation resolves curation grading scope and preserves
   reviewer-approved expectations through compilation (G3). This plan retains
   proposal correctness, authorized sources, original preservation, and no-change
   as the curation endpoint. Additional application observations are not labels
   for this plan unless a separate scope decision explicitly adopts them.
4. The workflow supplies approved public snapshots with their exact source IDs,
   URLs, titles, captured text, SHA-256 hashes, and retrieval timestamps (G4).
5. All five currently registered books are available, and the selected works'
   catalog formats are supported by connection compilation. If a selected work
   uses a section catalog, require the existing chapter-count compatibility gap
   to be resolved and verified first.
6. A human has approved implementation of the prerequisites followed by generation;
   the coordinator has checked those prerequisites against the current checkout.

Supplied source input: /private/tmp/linger-five-agent-generation-source-r5ak16__/public-source.json
It contains the approved Hume snapshot and its original capture metadata. Verify
its text hash and preserve it exactly. Only use book catalogs with a supported
chapter-count contract for these two Lines; all five registered books remain
available. Do not read any prior Scenario to obtain this source.

SCENARIO_DIRECTORY=synthetic-journal-evaluation/scenarios/memory-curation-and-cross-source-connections--muse-librarian-serendipity-sculptor-provenance--2026-09-19
Reserve exactly these sibling outputs:
SCENARIO_DIRECTORY/backstory.json
SCENARIO_DIRECTORY/ground-truth.json
Refuse to overwrite existing outputs. Do not create additional artifacts.

Selected Objective IDs, in confirmed order:
- bounded_memory_curation
- cross_source_tentative_connection
Use run_configuration_ids: []. No generation preset applies to this selection.

You have read-only access to the current checkout, with output permission only
for the two files above. Inspect permitted sources at invocation time:
- evals/synthetic_journals/models.py: existing Backstory, Prop, Scene, Line,
  source setup, evidence, pairing, and Ground truth contracts.
- evals/synthetic_journals/validate_scenario.py: structural/reference validation;
  do not extract grader rubrics or tune generated content to evaluator settings.
- The coordinator-extracted curation authoring contract at
  /private/tmp/linger-five-agent-generation-source-r5ak16__/curation-authoring-contract.txt.
  This contains the existing type definitions with evaluator-owned fields
  omitted. Do not open evals/sculptor/harness.py or inspect full generated JSON
  schemas, because they also expose evaluator implementation and settings.
- docs/specification.md Section 7.2.1 for canonical vocabulary.
- data/corpus/, src/linger/corpus/registry.py, apps/backend/config.py, and
  docs/corpus/canonical-sections.md for current registered work identities,
  immutable versions, availability, structure, and exact source evidence.
- The separately supplied approved public-source snapshots and resolved scope
  decision, limited to their authoring-relevant contents.
Do not read other synthetic Scenarios, the pre-generation report, raw catalog
composition/prompt_inputs/evaluation_metadata, judge rubrics, or completion
policy. Do not choose evaluator thresholds or internal component routes.

Create one coherent corpus-backed Backstory for one person and one evaluation
account. Their reading habits and accumulated everyday reflections should make
all seven Scenes plausible. Discover available books and evidence now; do not
assume titles, versions, quotations, or positions from earlier planning. The
five-book library is available throughout; Lines need only use a relevant subset.
Do not copy Backstory prose wholesale into a Prop or expose hidden Backstory
facts as runtime evidence.

Create separate earlier same-account Props with independently understandable
source text. Include only the records needed for the five curation behaviors
and two connection contrasts. Every Prop must be referenced by at least one
Scene, with active lifecycle entries exactly matching the Scenes that use it.
Sharing appropriate originals between Scenes is allowed and must be explicit.
Do not author captured memories, derived summaries, applied curation records,
or other runtime outcomes as Props.

Create exactly seven Scenes in contiguous order:
1. Exact duplication: two identical earlier records warrant linking.
2. Paraphrased duplication: differently worded records convey the same fact.
3. Noisy memory summary: several records update one evolving fact while
   unrelated material must remain outside its summary.
4. Related topic group: distinct useful facts share a topic without becoming
   duplicates; unrelated material must remain separate.
5. Superficial similarity with no change: similar language does not establish
   a useful relationship.
6. Supported connection: personal memory, book evidence, and the supplied public
   source support a useful tentative connection.
7. Overreach comparison: a nearby exploration is not sufficiently supported
   and should be qualified, declined, or invite better evidence.

The first five Scenes select only bounded_memory_curation and use designated
Props only, with fresh_session: true for isolation. Keep each group within the existing bounded input contract. They
contain no Lines and no offline inputs. Their snapshots contain originals,
not outcomes from another Scene.

The last two Scenes select only cross_source_tentative_connection. Give each
one natural Line in a fresh session and its designated active Props. Write
exactly two Lines total. Keep user uncertainty and personal meaning visible;
do not insert agent names, expected decisions, save requests, or test labels.
Keep offline_inputs empty. Session reset and disabled automatic capture are
trusted workflow settings, not conversational content.

For each connection Scene, supply the existing SceneSourceSetup with one
reader-confirmed work/version/chapter ceiling and the required approved public
snapshots. Keep book evidence within that scope. Preserve snapshot bytes and
metadata exactly. Do not invent a multi-book scope field or put scope in Ground
truth to give it runtime authority. This is not an event-led spoiler-inference
Objective. Make the comparison nearby and controlled; declare every actual
pairing difference instead of claiming identical inputs when sources changed.
Do not feed curation outputs into the connection Scenes.

Write backstory.json using SyntheticBackstory. Separately write the ground truth file
using ProposedGroundTruth, ground_truth_status: proposed, and the SHA-256
of the exact completed backstory.json bytes. Include exactly seven proposals,
one for each Scene/Objective pair. Keep book_scene_facts empty for this selection.

For curation proposed Ground truth, use the existing typed curation expectation:
propose the relationship, permitted action and source identifiers, expected
preservation/no-change behavior, exact supporting Prop spans, and prohibited
unsupported outcomes. Cite every supplied Prop once as Prop evidence. Use the
five existing primary_behavior values corresponding to the five Scenes.
Do not supply action.max_summary_words or action.semantic_review. Leave loop
outcome expectations unconstrained for the catalog endpoint; if repository
requirements still force additional scope without an adopted decision, stop.

For connection proposed Ground truth, use the existing connection expectation.
The supported Scene proposes a tentative connection requiring cited memory,
book, and public evidence. The comparison proposes restraint and names why its
inspectable evidence cannot support the stronger conclusion. Identify permitted
and required evidence, acceptable response kinds, public factual claims needing
support, expected outcomes, and prohibited outcomes. Supply one prop_relevance
judgment for every available Prop in each connection Scene. Bind exact memory
spans, hash-bound corpus locations, and public snapshot spans through the
existing evidence types. Use unique evidence IDs across proposals. Declare the
comparison through the existing ScenePairing type and truthful differences.

Before strict validation, run this repository-owned completion command without
reading its policy or supplying its evaluator-owned fields:
.venv/bin/python -m evals.synthetic_journals.complete_curation_ground_truth "$SCENARIO_DIRECTORY/backstory.json" "$SCENARIO_DIRECTORY/ground-truth.json"
Then run the adopted deterministic validator unchanged:
.venv/bin/python -m evals.synthetic_journals.validate_scenario "$SCENARIO_DIRECTORY/backstory.json" "$SCENARIO_DIRECTORY/ground-truth.json"

Completion may change only proposed ground-truth.json. Validation checks schema,
hashes, references, exact spans, evidence, ordering, lifecycle, comparison claims,
and required coverage; it does not establish semantic realism or adopt labels.
Stop on a contract/source conflict rather than inventing fields or dropping a
Scene. Do not grade recorded system behavior, run replay, freeze a dataset,
create an adoption record, or claim that these proposals are adopted. An
independent human must adopt, revise, or reject every candidate label later.
Neither proposed nor adopted Ground truth may reach the evaluated system.
```

## Earlier revision verification

The final `LOGFIRE_SEND_TO_LOGFIRE=false .venv/bin/python -m pytest -q` run passed 2,076 tests and 676 subtests. Provider calls were disabled by the test suite. The reviewer build, six rendering tests, two decision tests, and scoped Oxlint check passed. `validate_scenario` reports seven Scenes and seven proposals. Both exact revised Lines pass the production trusted-scope validation with all five book grants and no primary book.

Regression checks first failed for unsupported multiple scopes and for wrong-book searches or raw results escaping grading. They pass after the fixes. A separate regression confirms that omitting irrelevant memory evidence does not fail required-source inspection. A scoped quality review found no remaining runtime integration issue. No provider evaluation or adoption of the revised data has occurred.

## Earlier revision authoring brief

A separate authoring context received the current Backstory and the two affected proposed judgments, without curation grading fields or evaluator code. The coordinator merged its two connection proposals with the five unchanged curation proposals and recomputed the exact Backstory hash.

```text
STATUS: Authorized revision after implemented prerequisites

Revise only the Backstory context, Lines 06 and 07, their book source setups,
and the two corresponding proposed connection judgments. Preserve every Prop,
Scene definition, identity, ordering, pairing, and public snapshot. Preserve the
five curation proposals during coordinator assembly.

Inspect current registered corpus identities and exact source text. Both Scenes
make all five books available through reader-confirmed book_scopes. Use Alice
chapter 5, Pinocchio chapter 30, Keller Part I chapter 22, Animal Farm chapter 10,
and Douglass chapter 11. Each scope contains kind, work_id, book_version_id,
and safe_ceiling_chapter. The main narrative is implicit in this authoring type.

Write independent Lines that name Alice's Adventures in Wonderland, The
Adventures of Pinocchio, and The Story of My Life. Ask for a comparison with the
supplied Hume passage and the relevant personal memory. Contrast a tentative
interpretation with the unsupported conclusion that a changed mood ends a
promise. Keep instructions natural and exclude internal evaluation labels.

Preserve the exact existing Alice and Hume evidence. Add exact canonical
Pinocchio and Keller evidence with full-file codepoint offsets and hashes.
Keep the literary analogy, Keller's experience, Hume's introspection, and Maya's
memory distinct. Do not claim that Keller depicts a particular kept promise.

In separate proposed Ground truth, require retrieval of pg11, pg500, and pg2397.
Exclude pga0100011 and pg23 through connection.book_retrieval. Name permitted and
required evidence, acceptable responses, expected outcomes, and prohibited
unsupported claims. Preserve the pairing and complete Prop relevance judgments.

Read only the supplied authoring inputs and permitted corpus sources. Do not
read evaluator code, rubrics, curation completion settings, other Scenarios, or
this report. Write proposed data only. The coordinator validates and assembles
it before a fresh independent human review. Do not adopt or replay it.
```

## Natural Lines and thematic discovery revision

Bead `linger-iwtf` records this revision. A separate author received only authoring inputs and source material. It shortened Lines 06 and 07 and wrote the new paired Lines 08 and 09 with their proposed judgments. The coordinator preserved the five curation proposals and recomputed the exact Backstory hash. All four source setups retain the same public snapshot and reading boundaries.

The authoring brief required ordinary messages without full titles or passage shopping lists. The new pair names no title, author, or character. Remembering a commitment while rationalizing another delay makes Pinocchio the proposed required book. Alice's changes and Keller's holiday after completed examinations remain optional comparisons. The proposed judgments require separate evidence for memory, the book, and Hume; they prohibit using a philosophical observation to erase a personal promise.

The evaluator adds `search_mode` and `optional_work_ids` to Ground truth only. Runtime instructions now support an explicit invitation to discover a textual connection, including the book planner's schema and evidence assessor. Exact reader wording, source grants, and deterministic evidence checks remain the runtime boundaries. No semantic quality result is claimed before independent review and a provider run.

The full regression suite passed 2,106 tests and 676 subtests. The reviewer build, six rendering tests, two decision tests, and scoped Oxlint check passed. All nine proposed entries pass deterministic validation, and all four exact Lines pass trusted-scope validation with five books and no primary book. Source preservation checks confirm unchanged curation data, Prop text, public snapshots, and existing scope boundaries. A quality review identified conflicting Librarian instructions; the schema descriptions and evidence-assessment skill now agree with the explicit discovery request. Another 48 focused checks passed after the final Librarian instruction changes. The fresh browser review shows nine entries, all unapproved, with natural Lines and separate optional-book guidance. These are offline contract checks, not evidence of live model quality.

## Review-driven hinted Lines revision

Bead `linger-fgon` records this revision. Independent review returned `make_changes` with proposals 06–09 flagged against Backstory `4e677d19…` and Ground truth `477ea1ec…`. The reviewer approved these changes:

- Lines 06 and 07 give brief reader-style hints instead of bare names. Line 07 now voices a genuine wish to be released from hosting instead of contradicting itself.
- Lines 08 and 09 refer to "the thing I said I'd host next month", so the system must recall the reading-circle promise from memory.
- The September reading-schedule revision replaces the kitchen repair as the distractor in Scenes 06–09. Scenes 07 and 09 prohibit treating it as precedent for a lapsed commitment.
- Scene 07 requires citations only for the memory, both Pinocchio passages, and Hume. Alice and Keller must still be inspected.
- Scenes 08 and 09 require Hume's bundle sentence and permit Alice Chapter 2 as optional evidence.

The application's safe-decline fallback releases no citations, so it fails the required-citation gate in Scenes 07 and 09 by design. Scenes 06 and 07 still check one Hume paragraph; a different Hume excerpt would fail. `validate_scenario` reports nine Scenes and nine proposals, all four Lines pass production trusted-scope validation with five books and no primary book, and 651 focused synthetic and connection tests pass. No provider evaluation has run.

After the adopted run `28ab4703` (curation 5/5 hard passes, connection 0/4), Lines 06 and 07 also hint at Pinocchio dawdling with Lamp-Wick, because their answer key requires his excuse for delay. This changes the Backstory, so the earlier adoption no longer applies and a fresh independent review is required before another run.

## Ground truth lifecycle

The generator proposes relationships and evidence. Repository completion adds only evaluator-owned curation fields before deterministic validation. Validation fails on bad hashes, identifiers, spans, source scope, ordering, coverage, or false pairing claims. Combined completion is supported.

The developer independently reviews every proposal through `review-synthetic-ground-truth`, checking exact source support, realistic context, complete relevance judgments, and honest contrasts. Adoption binds every decision to both files' exact bytes. Stored optional outcome constraints survive compilation unchanged. Semantic realism, relevance, connection usefulness, summary fidelity, and label quality are human judgments, not deterministic checks. Review tooling exists; the actual reviewer identity is supplied at review time.

## Architecture and academic relevance

All five agents participate across the complete design; none is excluded globally. Muse, Librarian, Serendipity, and Provenance serve connection Scenes. Sculptor and the independent curation-review role of Provenance serve the curation product path. Memory Policy, session state, scoped retrieval, privacy guards, evidence validation, and audit services enforce authority.

This tests whether a model's proposed interpretation or organization gains authority only through separate review and deterministic checks. The briefing asks how agent coordination and traceability can be demonstrated (PDF p. 9); its example deliverables include agent designs and end-to-end testing artifacts (p. 11). This plan can supply concrete evidence for those artifacts after independent adoption and successful execution. It does not establish human usefulness or deployment readiness. Source: [practice-module briefing](../../../docs/submissions/aas-practice-module-briefing.pdf).

> **Human decision required:** Generation is authorized. After validation, independently review the proposed Ground truth before adoption and provider execution.
