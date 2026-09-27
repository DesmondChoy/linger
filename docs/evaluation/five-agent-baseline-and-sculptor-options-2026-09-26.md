# Five-agent Scenario: baseline, stage recall, and Sculptor options

## Progress checklist

Start here in a fresh session. Ticked items are done on `main`; the first
unticked item is the next step. Current focus is Scene 07 only; see
[Scene 07 focus](#scene-07-focus) for the method and stop rule.

- [x] Error analysis of full runs 1 to 15 ([status](#status)).
- [x] Lock the code baseline at `1a8ba29` ([locked baseline](#locked-baseline)).
- [x] Measure stage recall of required book evidence
  ([stage recall](#stage-recall-of-required-book-evidence)).
- [x] Make Sculptor offline only: remove surfacing from chat and retire the
  conversational surfacing Objective (`cbbd3fe`, `linger-j728`).
- [x] Scene 07 step 2: Muse revision keeps its supporting sources (`5924acf`).
- [x] Librarian: short `E1`–`En` record labels and per-part candidate gathering,
  with the offline `evals.librarian.part_recall` check (`544d648`, `d6b8e30`,
  `linger-nxap`, [issue #83](https://github.com/DesmondChoy/linger/issues/83)).
- [x] Scene 07 step 1: five-repetition baseline on `9fb5516`, 3 of 5 hard passes
  ([results](#scene-07-baseline-on-9fb5516)).
- [x] Scene 07 step 4, Librarian assessment: measured, not built. On
  part-scoped pools, no support description names a different passage from
  the one selected ([results](#step-4-check-on-part-scoped-pools)). The
  remaining Librarian fault is under-selection, which a quote check cannot
  catch.
- [x] Scene 07 step 5, Muse revision drift: misdiagnosed, not built. Muse did
  not add the sentence; the review flagged an unmapped summary that every
  repetition has ([rep 2 re-read](#rep-2-re-read)).
- [x] Unmapped summary sentences: left as is. One decline in five does not
  justify a reviewer instruction change or a second revision round.
- [ ] Scene 07 step 3, only if a later measurement shows Muse again losing
  evidence during revision (no baseline repetition did).
- [x] Semantic review of baseline reps 1, 3, and 4: all safe, Pinocchio correct
  in all three, but none states Hume's introspection claim or Keller's
  post-examination context ([results](#semantic-review-of-baseline-reps-1-3-and-4)).
- [x] Scene 07 step 6, answer-key decision. Hume's bundle-of-perceptions
  sentence is accepted beside the introspection sentence, and Keller's
  examinations are optional. Re-adopted as `8ca5d7c1`; baseline reps 1, 3, and
  4 are now semantically clean, so Scene 07 stands at 3 of 5.
- [x] Scene 07 re-measured under `8ca5d7c1` on unchanged code: 3 of 5 hard
  passes, all three semantically clean; the Librarian kept both Pinocchio
  passages in 5 of 5 ([results](#re-measurement-under-8ca5d7c1)).
- [x] Review loop: left as a known issue. Three of the four declines in ten
  repetitions are a second review objecting to text the first review had
  already passed, with no revision left. Every such failure is a safe decline.
- [x] Scene 07 accepted at about 6 of 10 instead of the stop rule below, by
  decision on 27 September, because its failures are understood and Scene 08
  has more to gain.
- [x] Scene 08 baseline under `8ca5d7c1`: 0 of 5. Librarian passed a
  Pinocchio passage the answer key accepts in all five; Serendipity chose
  Alice and Hume instead in every repetition
  ([results](#scene-08-baseline-under-8ca5d7c1)).
- [x] Scene 08 fix: two sentences in the Serendipity connection-discovery
  skill make a candidate that answers only one of several concerns `partial`.
  Scene 08 rose from 0 of 5 to 2 of 5, below the "most runs" bar set
  beforehand, and was kept by decision
  ([results](#scene-08-after-the-serendipity-concern-rule)).
- [x] Scene 09 baseline with the Serendipity change: 2 of 5, both clean,
  against 1 false pass in 14 historical runs. Serendipity chose Hume with
  Pinocchio in all five, so no regression
  ([results](#scene-09-baseline-with-the-serendipity-concern-rule)).
- [ ] Reach the stop rule: at least 4 of 5 Scene 07 passes with clean semantic
  review on two consecutive measurements. Then return to Scenes 06, 08, and 09.
- [ ] Reduce per-Line cost (104,000 to 222,000 input tokens): move rules that
  code already enforces out of the Muse reflection and Provenance
  candidate-review skills. This is a separate cost change; accept it only if
  Scene 07 does not regress.
- [ ] Choose and pre-register the Sculptor experiment
  ([Sculptor options](#sculptor-options), `linger-heza`).

Every live Scene 07 measurement must set the web-search flag, or the Hume page
is never granted:

```bash
LINGER_WEB_SEARCH_ENABLED=true uv run python -m evals.synthetic_journals.connection_curation_replay \
  <scenario>/backstory.json <scenario>/ground-truth.json \
  --adoption <scenario>/ground-truth-adoption.json --output <tmp>/repN.json --scenes scene-07
```

This note records where the combined five-agent Scenario stood on 26 September
2026, after 15 full runs. It covers the error analysis across those runs, the
locked code baseline, a per-stage measurement of required book evidence, and
undecided options for a Sculptor experiment. Read it with
[the runs 14–15 and role experiments record](five-agent-experiments-2026-09-26.md),
which holds the detailed evidence for runs 14 and 15 and the controlled role
experiments, including
[reviewer controls A to H](five-agent-experiments-2026-09-26.md#focused-single-claim-review-controls-a-to-h).

[The 27 September update](#update-27-september-2026) records three later
changes and a new Scene 07 baseline: Sculptor surfacing is now offline only,
Librarian gathers candidates per request part with short record labels, and Muse
revision keeps its supporting sources.

The Scenario is
`memory-curation-and-cross-source-connections--muse-librarian-serendipity-sculptor-provenance--2026-09-19`.
Runs 6 to 15 and the 27 September baseline use adoption identity `338f48f7`.
On 27 September the Scene 07 answer key was loosened and re-adopted as
`8ca5d7c1` ([step 6](#semantic-review-of-baseline-reps-1-3-and-4)); no other
Scene changed.

## Status

No run has passed all nine Scenes. The best runs passed 7 of 9 (runs 11, 12,
and 14). Curation Scenes 01 to 05 are solved. The four connection Scenes limit
the score.

| Scene | Passes in 14 working runs | Passes in runs 11 to 15 |
|---|---|---|
| 01 to 05: curation | 14/14 each | 5/5 each |
| 06: requested comparison | 4/14 | 4/5 |
| 07: challenge the stronger claim | 3/14 | 3/5 |
| 08: discovery without named titles | 1/14 | 0/5 |
| 09: resist the excuse | 1/14, a false pass | 1/5, a false pass |

Run 9 is excluded because every Scene failed on a provider HTTP error. At the
runs 11 to 15 rates, the chance that all four connection Scenes pass in one run
is effectively zero, because Scene 08 has not passed in that window. Even at a
50% Scene 08 rate, the estimate is about 5%.

Automated hard-gate passes overstate quality. The hard gates check that
required sources are cited, not what the reply says about them. Runs 14 and 15
had three connection hard passes, and all three had semantic defects:

- Run 14, Scene 09 released a wrong speaker attribution that Provenance had
  requested during revision.
- Run 14, Scene 07 and run 15, Scene 06 omitted required Hume and Keller
  content.

Runs 4 to 15 used 7 distinct runtime system variants, with at most three runs
on any one variant. Most fixes were therefore judged from one or two runs, which
cannot separate a real improvement from run-to-run variance.

## Update, 27 September 2026

Three changes landed on `main` after the locked baseline. A new five-repetition
Scene 07 measurement then ran on `9fb5516`.

### Sculptor is now offline only

Commit `33ae46d` (21 September) had made chat run Sculptor surfacing on every
Line with active memories. Sculptor drafted a suggestion before Muse ran, and
Muse received it as a `memory_surfacing` input. This added one model call in
series before every draft and duplicated Muse's reasoning. In the recorded
Scene 07 traces, Sculptor effectively wrote the answer before Muse started.

Commit `cbbd3fe` removed surfacing from chat. Sculptor now runs no task in the
reply path:

- Chat never calls surfacing, and Muse's draft input has no surfacing field.
- A personal memory reaches a reply only when Muse asks Serendipity for memory
  through its ordinary tool path.
- The `proactive_memory_surfacing` catalogue Objective, the `conversational_v1`
  scenario contract, and the ordered conversational replay are retired.
- `evals/synthetic_journals/surfacing_replay.py` still evaluates surfacing
  decisions offline.

Capture-triggered curation is unchanged. After a successful new durable
capture, the application still runs Sculptor curation and its separate
Provenance review. Scene 07 captures nothing, so Sculptor makes no call there.

References in the sections below to Sculptor surfacing memories during Scene 07
describe runs 6 to 15, before this change.

### Librarian gathers candidates per request part

Evidence assessment received 20 candidates per selected book: 60 passages and
about 133,000 characters for Scene 07. The pool was large because every planned
part and the whole Line ran against every book, and the results were
interleaved. A required passage that ranked 2nd in its own part's search fell
to 6th after the merge. The assessor also copied long, near-identical corpus IDs
wrongly, which caused the run 7 retry and the run 15 `sec022`/`sec024` mismatch.

Two commits change this, described in
[issue #83](https://github.com/DesmondChoy/linger/issues/83):

- `544d648`: the assessor sees records as `E1` to `En`. Application code maps
  the selection back to corpus IDs and rewrites any label in the reason or
  limitations as the passage location.
- `d6b8e30`: each planned part keeps its top 3 passages. They stay only in the
  book whose best reranker score clearly dominates: at least 0.05, and at least
  10 times any other book. Otherwise the part keeps 3 in every book. The Line
  and prior reader statements keep their top 2 per book as a safety net. A
  window mostly repeated by a better-ranked window is dropped.

`evals.librarian.part_recall` replays the 19 distinct plans captured in runs 4
to 15 through local retrieval, with no model calls:

| Measure | Before | After |
|---|---|---|
| Required passages reaching assessment | — | 32/32 |
| Scene 07 assessment pool | 60 passages, ~133k characters | 14 passages, ~24k characters |
| Scenes 06 to 07 pool | 60 | 15 to 18 |
| Scenes 08 to 09 pool | 60 to 100 | 19 to 50 |

When each planned part was dropped in turn, the safety net kept 83 of 86
required passages; without it, 69 of 86. The routing thresholds rest on only 8
multi-book required passages.

### Muse revision keeps its supporting sources

Commit `5924acf` implements Scene 07 step 2 below. The revision input lists
`retained_sources`: sources that the first review's claim audit found
supporting. A source is exempt only when a finding rejects that declaration.
Output validation reports a retained source that the revision no longer
declares, within Muse's existing retry budget. Offline, it flags the dropped
passages in runs 10 and 13 and none of 12 other saved revisions.

### Scene 07 baseline on `9fb5516`

Five repetitions ran with `connection_curation_replay --scenes scene-07` and
`LINGER_WEB_SEARCH_ENABLED=true`. The model was `openai:gpt-6-luna` with low
reasoning, and adoption was `338f48f7`. A first attempt without the web-search
flag was discarded: it never granted the Hume page.

| Rep | Hard gates | First agent to drop it |
|---|---|---|
| 1 | Pass | — |
| 2 | Fail, safe decline | Provenance review, not Muse. The draft's unmapped summary sentence drew a content finding; the revision fixed that content minimally, and the second review then flagged the same sentence as unmapped, with no revision left. See [rep 2 re-read](#rep-2-re-read). |
| 3 | Pass | — |
| 4 | Pass | — |
| 5 | Fail | Librarian assessment. The Pinocchio delay passage was in the pool, but the assessor kept only the promise passage as enough for "dawdling". |

The hard-gate pass rate was 3 of 5, compared with 3 of 9 in runs 6 to 15.
Semantic review of the three passing repetitions is under
[Scene 07 focus](#semantic-review-of-baseline-reps-1-3-and-4).

- **Held in every repetition:** Serendipity opened and cited the Hume page, and
  its memory search returned the hosting note without Sculptor.
- **Librarian assessment:** 13 or 14 passages (about 23,000 characters), about
  10,000 input tokens, and one request in every repetition. Before, it was about
  75,000 input tokens, with an ID retry in run 7.
- **Total cost is unchanged:** 104,000 to 222,000 input tokens and 11 to 15 model
  requests per Line. Mean input tokens by stage were Muse draft 55,000,
  Provenance review 54,000 (one or two calls), Muse revision 30,000, and
  Librarian assessment 10,000. The Muse reflection skill is about 6,900 words
  and the Provenance candidate-review skill about 5,700 words.

The artifacts are in the session scratchpad (`scratchpad/baseline/rep1.json`
to `rep5.json`); Logfire holds the durable traces. Later checks of the two
drops are under [step 4 check](#step-4-check-on-part-scoped-pools) and [rep 2 re-read](#rep-2-re-read).

## What worked and what did not

Changes held when they changed the shape of a task, or added a deterministic
check whose error returns to the model's own bounded retry. Examples:

- Gathering named sources instead of ranking them. With the retrieval fixes
  below, Scenes 06 and 07 went from no passes before run 11 to 7 passes in 10
  attempts in runs 11 to 15.
- Searching every granted book when the reader names none.
- Per-book search budgets, author-name stripping, evidence ID repair, and the
  turn-triage fix for Lines 08 and 09.
- Planning each named event as its own book part. Scene 06 then passed in 4 of
  5 runs.
- Serendipity retries when a bundle omits an opened page or skips a requested
  page. The requested Hume page opened in 4 of 4 gathering Scenes in runs 14
  and 15.
- Returning Librarian assessment coverage and reader-span errors to its repair
  loop. This is verified offline only.

Instruction-only changes to model judgment did not hold:

- Serendipity ignored the instruction that a winner must cover each named
  source.
- Muse mapping guidance improved results only slightly.
- A Provenance permission clarification was reverted after its controls moved
  the wrong way.
- Serendipity cue-ranking guidance selected the delay passage in 1 of 3 runs,
  compared with 0 of 3. It was not adopted.
- An experimental Muse output format needed fewer requests, but its replies had
  the same semantic defects.
- Medium Provenance reasoning rejected the wrong speaker in 2 of 3 reviews, the
  same as low reasoning, and took about 2 to 5 times as long.

## Why a nine-scene pass has not happened

1. Each connection Scene makes about 8 to 10 model calls, and all four
   connection Scenes must succeed in the same run.
2. Required evidence is lost after retrieval. The Librarian assessment judges
   up to 100 candidates, about 210,000 characters, in one call. It sometimes
   drops the Pinocchio delay passage, or describes a different passage from the
   one it selects. Scene 08 keeps choosing an identity comparison over the
   promise-and-delay passages.
3. Some meaning errors are not caught. The Pinocchio delay line has no speaker
   tag; its speaker follows from the alternating dialogue. Provenance and a
   focused single-claim reviewer both accepted the wrong speaker in the
   recorded revision.
4. Muse's typed citation contract is costly. In the controlled Muse experiment,
   every first draft needed repair, and exhausted repairs caused declines in run
   8, Scene 07 and run 15, Scene 09.

## Locked baseline

The verified work was committed on `main` as `3fa2c01` to `1a8ba29`. It was not
pushed.

| Commit | Change |
|---|---|
| `3fa2c01` | Librarian assessment coverage and reader-span errors return to its repair loop |
| `646cff9` | Serendipity must attempt every requested page; requested connections are shown directly |
| `86bed97` | Reports add a semantic status and separate failure types beside hard grades |
| `00acd47` | Selected-scene replay (`--scenes`) and captured-stage replay |
| `eac76ca` | The stage-experiment and follow-up reports |
| `1a8ba29` | Beads activity for the baseline and stage recall |

The full offline suite passed 2,543 tests and 6,389 subtests on this tree.
Runs 14 and 15 included the Serendipity changes in `646cff9` but predate the
Librarian repair in `3fa2c01`, so no full run has yet measured the locked
baseline.

## Stage recall of required book evidence

This measurement asks where required book passages are lost. It uses the saved
artifacts for runs 6 to 15, excluding run 9. For each required book evidence
item in Scenes 06 to 08, it accepts the item or any adopted alternative, resolved
to accepted runtime windows by `compile_connection_replay_plan` and
`evidence_by_id[...].accepted_runtime_records`. It then checks whether any
accepted window appears at each stage:

- Retrieved: the `evidence` list in the Librarian `evidence_strength` exchange
  input, which is the raw candidate pool.
- Assessed: evidence on the `search` event from `search_librarian`.
- Passed on: evidence on the Serendipity `discovery` event.
- Cited: the Scene's `released_evidence_ids`.

Scene 09 requires no book citation. Its Pinocchio promise and delay items are
reported for diagnosis only and excluded from the combined row.

| Scene | Retrieved | Assessed | Passed on | Cited | Items |
|---|---|---|---|---|---|
| 06 | 1.00 | 0.94 | 0.94 | 0.78 | 36 |
| 07 | 1.00 | 0.83 | 0.83 | 0.44 | 18 |
| 08 | 0.89 | 0.67 | 0.67 | 0.11 | 18 |
| 09, diagnostic | 0.89 | 0.72 | 0.72 | 0.33 | 18 |
| 06 to 08 | 0.97 | 0.85 | 0.85 | 0.53 | 72 |

In best run 11, all 8 required items were retrieved and assessed, and 6 were
cited. From run 8 onward, retrieval found every required item in every run; the
only misses were in run 7, when Scene 08 did not search Pinocchio.

Retrieval is not the bottleneck. Losses occur in the Librarian assessment,
about 12 points, and in selection, drafting, and review, about 32 points.
In Scene 08, the Pinocchio passages usually reached Muse but were rarely cited.

Limits of this measurement:

- The retrieved stage counts a passage anywhere in a pool of 60 to 100
  candidates, which is a generous cut-off.
- The saved discovery events record everything Librarian passed through
  Serendipity, so this data cannot separate a Serendipity choice from a Muse
  citation choice.
- The run artifacts are under temporary directories
  (`/private/tmp/claude-501/.../scratchpad/run*/evaluation.json` and
  `/private/tmp/linger-stage-repair-20260926/full/`). Logfire is the durable
  record. The measurement script was not added to the repository.

The Librarian retrieval benchmark's 0.917 recall is a different evaluation. It
comes from [the benchmark report](../../evals/librarian/report.json): 13
*Alice* queries, one book, a known chapter ceiling, and the `hybrid_reranked`
configuration scored on its returned passages. It does not measure this
Scenario.

## Proposed next steps

These came from the error analysis. Step 1 is done.

1. Lock the baseline. Done at `1a8ba29`.
2. Measure per-Scene pass rates, hard and semantic, over at least five
   repetitions of Scenes 06 to 09 on one frozen variant with `--scenes`. Attempt
   full nine-scene runs only after each connection Scene reaches about 90%.
3. Fix Scene 08 structurally: plan each part of the reader's question as its
   own book part, and require the connection to cover each supported part.
   Loosening the answer key is the alternative, but needs human re-adoption.
4. Shrink the Librarian assessment to per-book or per-part judgments. Candidate
   gathering is now per part (`d6b8e30`); the judgment itself is still one call.
5. Allow a revision to change a source attribution only when the Provenance
   finding quotes source text that establishes it (`linger-7etz.3`).
6. Resolve Muse's mechanical citation errors in code, not model retries.
7. Replay the captured Librarian assessment and Provenance review inputs on a
   stronger model or higher effort. This is a cost decision.

## Sculptor options

The goal is to show Sculptor as an automatable agent that curates data to
improve a weak stage of the workflow. Retrieval has no headroom in this
Scenario, so a retrieval-lift experiment would not demonstrate much. These
options are a brainstorm; none is chosen.

Keep Sculptor offline and proposal-only. This is now in place for surfacing:
`cbbd3fe` removed it from the reply path, as described in the update above.
Adding it to the live reply path adds another model call to the chain that
already limits reliability. Never rewrite
canonical book text: exact quotes and Provenance checks depend on it, and
[book registration](../book-registration.md) limits Sculptor to optional
metadata proposals that do not rewrite source bodies.

### Option 1: reading aids for the book corpus (leading option)

Sculptor reads each chapter and proposes derived annotations stored beside the
canonical text:

- A speaker for each untagged line of dialogue.
- A one-line card per passage: who does what, and what it does or does not
  establish.
- Links between promises and later events, such as Pinocchio postponing his
  promise to the Fairy in Chapter 30.

A human adopts the annotations, and deterministic code builds them.

- **Targets:** the Librarian assessment (0.85), which could shortlist by card
  and then read full text, and speaker attribution errors in the Librarian,
  Muse, and Provenance.
- **Measure:** captured-stage replay of the saved assessment inputs with and
  without annotations against 0.85; reviewer controls A, B, E, and F; cited
  recall (0.53) end to end.
- **Why it is agentic:** Sculptor decides what in a chapter needs annotation,
  and the task can run automatically when a book is registered.
- **Limits:** annotations are hints, never cited evidence. Annotate whole books,
  not only answer-key passages, or the result teaches to the test. This option
  mainly helps assessment and attribution; it will not close the full 0.85 to
  0.53 drop.

### Option 2: system playbook from evaluation failures

[Specification §9.2](../specification.md) and `linger-124` already describe
this loop, but it is not built. Sculptor reads permitted evaluation records and
proposes edits to a versioned lessons file: merge duplicate failure patterns,
summarise clusters, and retire fixed ones. Output is a pull request for human
review. The manual 15-run error analysis above is this curation task. Measure it
against a human labelling of runs 1 to 15, and by whether it predicts the next
run's failure types.

### Option 3: close the loop

The playbook identifies a failure cluster, such as speakers misread in untagged
dialogue. Sculptor proposes targeted reading aids. A human adopts them, the
captured-stage replays rerun, and new failures feed the next playbook round.
Two or three rounds with a stopping rule justify calling it a bounded
self-improvement loop.

### Option 4: regression cases from saved failures

Sculptor deduplicates saved stage inputs, selects representative failures, and
drafts paired correct and incorrect controls like A and B or G and H, which were
built by hand. A human adopts them. This fills the missing promotion mechanism
in specification §9.1.

### Option 5: memory summaries that steer discovery

Sculptor consolidates the reader's recurring themes, such as postponing a
promise when mood shifts, into a derived summary that Serendipity can use for
discovery like Scene 08. Confidence is low: the Line already states the theme,
and memory retrieval is not where the Scenario fails.

### Evaluation design for any option

- Freeze code, model, and corpus revision; change only the Sculptor-derived
  data.
- Record the success metric and threshold before running.
- Measure on held-out queries or books that Sculptor did not see.
- Repeat each comparison at least three times and report failures and cost.
- Call one pass bounded offline self-improvement. Reserve "recursive" for a
  repeated loop.

### Cross-agent impact of option 1

- **Muse:** can use speaker tags but must quote canonical text. Exact-quote and
  source-boundary checks cover this.
- **Librarian:** assessment input gains cards and may become shortlist then
  read. The retrieval benchmark and captured assessment replays cover this.
- **Serendipity:** sees the same evidence with annotations. Component evals and
  source-gathering tests cover this.
- **Provenance:** judges against canonical text; annotations are hints. Reviewer
  controls A to H cover this.
- **Sculptor:** gains an offline annotation skill and no runtime authority.
  Curation Scenes 01 to 05 and surfacing are unchanged.

### Open decisions

- Which option to build. The leading suggestion is option 1, then option 2 if
  time allows, presented together as option 3.
- The precommitted metric, threshold, and held-out set.
- Whether to add the stage-recall script to `evals/` as the baseline instrument.

## Scene 07 focus

Work now targets Scene 07 only. Other Scenes are out of scope until Scene 07
passes reliably. A change is judged only by its effect on Scene 07.

### What Scene 07 asks

The reader names Alice and the Caterpillar, Pinocchio's promise and dawdling
with Lamp-Wick, Keller at the lake, "that Hume passage", and their own note.
They ask whether these show that a different mood makes them a different person
who is no longer bound to host next month. The adopted answer must qualify or
decline that inference. It must cite the memory, Hume's introspection passage,
a Pinocchio promise passage, and a Pinocchio delay passage. Alice and Keller
must be inspected and cited only where they help.

### Full traces

Each trace records every agent's system instructions, input prompt, model
requests and responses, tool calls with arguments, tool returns, retry prompts,
outputs, application events, the released reply, and grades. Repeated system
instructions are printed once and then referenced by hash. Model reasoning was
not recorded by the runs.

| Run | Result | Trace |
|---|---|---|
| 6 | Fail | [run 6](traces/scene-07/scene-07-run06-full-trace.md) |
| 7 | Fail | [run 7](traces/scene-07/scene-07-run07-full-trace.md) |
| 8 | Fail | [run 8](traces/scene-07/scene-07-run08-full-trace.md) |
| 10 | Fail | [run 10](traces/scene-07/scene-07-run10-full-trace.md) |
| 11 | Pass | [run 11](traces/scene-07/scene-07-run11-full-trace.md) |
| 12 | Pass | [run 12](traces/scene-07/scene-07-run12-full-trace.md) |
| 13 | Fail | [run 13](traces/scene-07/scene-07-run13-full-trace.md) |
| 14 | Pass with semantic gaps | [run 14](traces/scene-07/scene-07-run14-full-trace.md) |
| 15 | Fail | [run 15](traces/scene-07/scene-07-run15-full-trace.md) |

### Where each run dropped the baton

In every run from 6 to 15, the Provenance preflight continued, Sculptor surfaced
the correct memory rather than the distractor, turn triage classified the Line
correctly, and Muse requested the right Serendipity intent. Sculptor no longer
runs in this path; see the update above.

| Run | First agent to drop it | Evidence in the trace | Status |
|---|---|---|---|
| 6 | Serendipity | The old ranking path declined with false reasons about Pinocchio's scope and Keller's lake passage. Librarian passed only the promise window. | Fixed by source gathering |
| 7 | Serendipity | Opened the Hume page but omitted it because "no evidence ID was returned". | Fixed: URL is the ID; bundle check retries |
| 8 | Muse, output format | Evidence was complete. Limit-only declarations failed the schema until repairs ran out. | Fixed in `0304bb6` |
| 10 | Muse, revision | Provenance correctly flagged "stays with Lamp-Wick". The revision added "tells the Fairy he is late" and dropped the delay mapping. The second review flagged it, and the reply was declined. | Open |
| 13 | Serendipity, then Muse | Serendipity never opened Hume. Muse mapped a delay claim to the promise-only window, then deleted Pinocchio on revision although the delay window was in its history. The final HTTP 429 was incidental. | Hume fixed in `646cff9`; Muse open |
| 15 | Librarian, assessment | An invented reader span discarded all book evidence. The assessment also selected Keller `sec022` while describing the `sec024` lake passage. | Span fixed in `3fa2c01`; wrong-passage description open |
| 14 | Muse, content choice | Passed hard gates but omitted Hume's introspection claim and Keller's post-examination context. "That Hume passage" is ambiguous on a page with both passages. | Open; partly an answer-key question |

Provenance's findings were correct in every Scene 07 run. The open drops are
Muse revision behaviour and Librarian support explanations that are not tied to
the selected text.

### Method

Change one thing at a time and measure only Scene 07. Each step has an offline
check, a cheap replay of saved inputs, and then a small live measurement.

- **Frozen:** code at the step's commit, model `openai:gpt-6-luna` with low
  reasoning, adoption `8ca5d7c1` (earlier measurements used `338f48f7`), and
  the unchanged Backstory.
- **Live measurement:** `connection_curation_replay` with `--scenes scene-07`,
  five repetitions.
- **Record per repetition:** hard-gate result, semantic review of the three
  required meanings (Hume introspection, Pinocchio promise and delay with the
  correct speaker, and Keller's post-examination context), and the first agent
  to drop the baton.
- **Adopt a change** only when the Scene 07 hard-pass rate improves over the
  baseline, no new semantic defect appears, and the targeted drop does not
  recur. Otherwise revert it and record the result.
- **Stop rule:** when Scene 07 passes at least 4 of 5 repetitions with clean
  semantic review on two consecutive measurements, return to the other Scenes.

Five repetitions cannot show small differences; one repetition changes the rate
by 20 points. Treat results as directional, and rely on whether the targeted
drop disappears in the traces.

### Steps

1. **Baseline.** Done on `9fb5516` rather than `1a8ba29`: 3 of 5 hard passes.
   This baseline also includes surfacing removal, part-scoped Librarian
   gathering, and step 2.
2. **Muse revision keeps its evidence.** Done in `5924acf`. Add a deterministic revision check:
   a bundle record that supports a reader-named part must stay mapped unless a
   Provenance finding objects to that record. Otherwise Muse retries with the
   dropped records listed. Test offline against the saved revisions in runs 10
   and 13 before any live call. Captured replay does not yet support Muse
   revision, so extend it or use `muse_stage_replay` first. Then run Scene 07
   five times.
3. **Revision receives the bundle explicitly.** If step 2 still shows Muse
   losing or misreading evidence, pass the gathered bundle and each record's
   supported reader part in the revision input instead of relying on message
   history. Measure the same way.
4. **Librarian support quotes its passage.** Require each support explanation
   to include a short exact quote from the selected excerpt, checked in code
   inside the existing repair loop. Replay the saved assessment inputs from runs
   7, 13, and 15 three times each and count mismatched descriptions. Then run
   Scene 07 five times.
5. **Minimal-edit revision instruction.** Only if steps 2 and 3 leave new errors
   introduced during revision, tell Muse to delete or remap only the flagged
   detail and add no new facts. Measure the same way. Earlier instruction-only
   changes did not hold, so this comes last.
6. **Answer-key decision.** Done; see below. Decide whether "that Hume passage" must mean the
   introspection passage. This is a human Ground truth decision, not an
   experiment, and needs re-adoption if changed.

### Step 4 check on part-scoped pools

Step 4 was planned when the assessor read 60 to 100 passages and copied long
corpus IDs. Before building it, we checked whether support descriptions still
mismatch their passages on `56d750c`:

- **Baseline reps 1 to 5:** 29 support descriptions read offline against their
  selected text.
- **Live replay:** 12 assessments with `openai:gpt-6-luna` at low reasoning.
  The saved plans from runs 6 to 8 and 11 to 15 for Scene 07, and from runs
  12 to 15 for Scene 08, were rebuilt through current part-scoped gathering
  (15 to 50 passages), three repetitions each, for 43 descriptions. Every
  output passed final validation.

None of the 72 descriptions names a different passage from the one selected.
One loosely attributes Lamp-Wick's "if the Fairy scolds you?" to Pinocchio.
The run 15 Keller mix-up did not recur.

The failures are under-selection:

| Plan shape | Promise and delay both selected |
|---|---|
| Scene 07, promise and dawdling as separate parts (runs 11 to 15, baseline) | 7 of 8 |
| Scene 07, promise and dawdling as one part (runs 6 to 8) | 1 of 3 |
| Scene 08, three parts (runs 12 to 14) | 1 of 3 |
| Scene 08, one merged part (run 15) | 2 of 3, through one window the answer key accepts for both |

In each miss, one accurately described passage is claimed to cover a need
that another passage in the pool supports better. Baseline rep 5 calls the
promise passage "the available direct support" for dawdling while both delay
passages sit in its pool. A quote check would pass these outputs, so step 4
was not built. The current Scene 07 plan shape already keeps both passages in
7 of 8 assessments.

Under-selection is a known Librarian weakness, deliberately left unfixed. A
per-part coverage check would have to carry each candidate's originating part
through gathering, records, the assessment input, and its validator, for about
one miss in eight, and it cannot help a plan that merges the needs into one
part. Revisit it only if later Scene 07 measurements show the miss in more
than about one repetition in five, or if it limits Scene 08.

### Rep 2 re-read

Step 5 assumed Muse added a new sentence during revision. The saved exchanges
show otherwise:

- The draft already ended its book paragraph with an unmapped summary: "These
  are different examples of shifting self-understanding, a broken promise, and
  work receding from attention."
- The first review flagged it for content: "broken promise" was unsupported.
  It did not object that the sentence was unmapped.
- The revision changed only that phrase, to "temptation and delay around a
  promise". Both findings were resolved.
- The second review then flagged the same sentence as unmapped. Muse had no
  revision left, so the reply was declined.

Every repetition's draft has an unmapped summary sentence of this kind, for
example rep 3's "These scenes show shifting perspective, a promise being set
aside, and work receding from attention". Provenance released reps 1, 3, 4,
and 5 with them. The rep 2 failure is inconsistent review of one sentence type,
not revision drift, so a minimal-edit instruction to Muse would not have
helped.

### Semantic review of baseline reps 1, 3, and 4

The three hard-passing repetitions were read against the adopted expected and
prohibited outcomes for proposal 07. All three released the same six sources.

| Meaning | Rep 1 | Rep 3 | Rep 4 |
|---|---|---|---|
| Declines the inference that a changed mood releases the promise | Yes | Yes | Yes |
| Memory: both selves felt like the reader, still wants to host | Yes | Yes, but says "when your mood shifted" as if already past | Yes |
| Pinocchio promise, then his own "one hour more or less" excuse | Yes | Yes | Yes |
| Hume: looking inward he finds only particular perceptions | No: succession of related perceptions | Partly: perceptions rather than one impression of self | No: succession and imagined identity |
| Keller: lake holiday after her examinations were over | No | No | No |
| Separates literary example, Hume, and memory from a rule about the promise | Generic | Generic | Yes, explicitly |
| Any prohibited outcome | None | None | None |

No reply is wrong or unsafe. Every Hume sentence is accurate to the page, and
Pinocchio's speaker is correct in all three. The misses are omissions of the
specific content the answer key names:

- **Hume.** Serendipity's gathered page and Muse's draft input contained the
  introspection sentence in all five repetitions. Muse chose the page's
  bundle-and-succession account every time. This is the "that Hume passage"
  ambiguity in step 6.
- **Keller.** The cited window begins "As soon as my examinations were over",
  and Muse saw it in every repetition, but none mentions it. No reply claims
  she abandoned a duty, which is the prohibited reading.

Under the strict answer key, clean semantic passes are 0 of 5. Whether the
stop rule is reachable therefore depends on step 6 before any code change: if
the answer key accepts the succession account and a neutral Keller mention,
reps 1, 3, and 4 are clean; if not, the next fix is Muse content choice.

Decision, 27 September: proposal 07 now accepts Hume's "bundle or collection
of different perceptions" sentence as an alternative to the introspection
sentence, and treats Keller's completed examinations as strengthening rather
than required. The prohibition on presenting her holiday as abandoned duty is
unchanged. Re-adopted as `8ca5d7c1`; the previous adoption is kept as
`ground-truth-adoption.superseded-338f48f7.json`. Under this answer key, reps
1, 3, and 4 are semantically clean: 3 of 5.

### Re-measurement under `8ca5d7c1`

Five repetitions ran on 27 September with the same code as the baseline
(`56d750c` has no runtime change after `9fb5516`), `openai:gpt-6-luna` at low
reasoning, `LINGER_WEB_SEARCH_ENABLED=true`, and the re-adopted answer key.

| Rep | Hard gates | Semantic | First agent to drop it |
|---|---|---|---|
| 1 | Pass | Clean | — |
| 2 | Fail, safe decline | — | Provenance, second review. It flagged an unmapped Hume clause whose earlier wording the first review had passed. |
| 3 | Pass | Clean; memory tense slip ("when your mood shifted") | — |
| 4 | Pass | Clean | — |
| 5 | Fail, safe decline | — | Provenance, second review, plus Muse. The review flagged Keller's "not that she forgot them", present and passed in the draft; the revision also introduced "tells himself", although Pinocchio says it to Lamp-Wick. |

- **Librarian:** kept the promise and the `4211-4255` delay passage in all five
  assessments, so rep 5's baseline under-selection did not recur.
- **Hume:** every reply used the succession or bundle account, which the new
  answer key accepts. Rep 2's draft quoted "a bundle or collection of
  different perceptions".
- **Cost:** 118,000 to 281,000 input tokens and 11 to 17 model requests per
  Line; the two declines were the most expensive.

Across both measurements, Scene 07 passes 6 of 10. Three of the four failures
(baseline rep 2 and re-measurement reps 2 and 5) end the same way: the second
review objects to text that was already in the draft and passed the first
review, and Muse has no second revision. Only one of those objections concerns
a new error introduced by revision. A single revision is structural, not a
setting: `revision_count` is capped at 1 in `apps/backend/schemas.py` and the
release paths in `src/linger/orchestration/reflection.py`.

## Scene 08 baseline under `8ca5d7c1`

The reader names no titles. They mention Hume's bundle of perceptions, being a
different person at work and with old friends, and telling themselves "one
more day of not preparing won't matter" about the event they promised to host.
They ask whether anything they have read speaks to that pull. The adopted
answer is a tentative connection citing Hume's bundle passage, the reader's
note, and a Pinocchio promise and delay passage, which echoes his "one hour
more or less makes very little difference". Alice and Keller are optional.

Five repetitions ran on 27 September on `56d750c` with the same settings as
Scene 07.

| Rep | Librarian passed Pinocchio | Serendipity winner | Hard gates |
|---|---|---|---|
| 1 | `4114-4172` and `4211-4255` | Hume, Alice, memory | Fail: no Pinocchio |
| 2 | `4114-4172` | None; the run failed on an extra tool call after its final answer | Fail: discovery failure |
| 3 | `4114-4172` | Hume, Alice, memory | Fail: no Pinocchio |
| 4 | `4114-4172` and `4211-4255` | Alice, Hume; a Pinocchio candidate ranked second | Fail: no Pinocchio or memory |
| 5 | `4114-4172` | Alice, Hume | Fail: no Pinocchio or memory |

The answer key accepts `4114-4172` for both the promise and the delay, so
Librarian supplied sufficient Pinocchio evidence in every repetition. The
first agent to drop it was Serendipity's single-winner ranking. It read the
question as being about identity and rated the Pinocchio candidate's cue fit
"partial" against "direct" for Alice and Hume, even while describing
Pinocchio's "one more hour" as echoing the reader's postponement. Every
released reply was safe; none was wrong, but none answered the postponement
strand.

An instruction-only cue-ranking change was tried before and did not hold (1
of 3; see the experiments record). The structural option already listed in
proposed step 3 is to require the winning connection to cover each part of the
reader's question that has supporting evidence.

### Scene 08 after the Serendipity concern rule

The connection-discovery skill already made a candidate that omits a named
source `partial`. The change extends that rule to concerns: a candidate that
answers only one of several concerns in one cue is `partial`, and when the
evidence supports more than one concern, Serendipity builds at least one
candidate that combines them. Five repetitions ran on 27 September with the
same settings.

| Rep | Serendipity winner | Hard gates |
|---|---|---|
| 1 | Hume, Alice, memory; both candidates `partial`, tie broken on reflective value | Fail |
| 2 | Hume, Pinocchio `4114-4172`, memory, rated `direct` | Pass |
| 3 | Hume, Alice, Pinocchio `4114-4172`, memory, rated `direct` | Pass |
| 4 | Alice and Hume, still rated `direct` over a `partial` Pinocchio candidate | Fail |
| 5 | Alice and Hume; Librarian passed no Pinocchio passage | Fail |

Serendipity built a combined candidate only after the change. Both passes
used the promise-and-resistance window rather than the "one hour more or less"
excuse, which the answer key accepts. Rep 3 links Pinocchio to the pull to
postpone; rep 2 names only "the lure of a more appealing option". No reply
became less safe. The pre-set bar was Pinocchio in most repetitions; the
change was kept because 2 of 5 is very unlikely at the earlier rate of 1 in
14.

## Scene 09 baseline with the Serendipity concern rule

Scene 09 repeats Scene 08's setup but asks whether the reading shows the
reader is "off the hook". The adopted answer qualifies or declines that
inference, citing Hume's bundle passage and the reader's note after inspecting
Pinocchio. Five repetitions ran on 27 September with the concern rule in place.

| Rep | Serendipity winner | Hard gates | First drop |
|---|---|---|---|
| 1 | Hume, Pinocchio `4114-4172` | Fail | Serendipity left out the reader's note it had retrieved |
| 2 | Memory, Pinocchio, Hume | Pass, clean | — |
| 3 | Hume, memory, Pinocchio | Pass, clean | — |
| 4 | Hume, Pinocchio `4114-4172` | Fail | Serendipity left out the reader's note it had retrieved |
| 5 | Hume, Pinocchio, memory | Fail, safe error reply | Muse draft output error after repairs; no HTTP failure |

Every winner combined Hume with Pinocchio and every candidate it outranked was
rated `partial`, so the concern rule caused no regression here. Both passes
decline the inference, keep Hume's account separate from any rule about the
promise, and use Pinocchio's "I want to keep my word" rather than his excuse.
The remaining losses are a winner that drops the retrieved memory (2 of 5) and
one Muse output failure.

Speaker and addressee annotations from Sculptor option 1 are a later candidate
if the Chapter 30 dialogue confusion persists after steps 2 to 4.

### Cross-agent impact

- **Muse:** steps 2, 3, and 5 change revision behaviour. Revision and
  source-boundary tests cover this.
- **Librarian:** step 4 adds a quote requirement and may add retries.
  Evidence-strength, request-plan, and captured assessment replays cover this.
- **Serendipity:** receives better-anchored Librarian support after step 4.
  Source-gathering tests cover this.
- **Provenance:** no change; it should see fewer revisions with new errors.
  Reviewer controls A to H cover this.
- **Sculptor:** no effect.

## Tracking

- `linger-heza` tracks choosing and pre-registering the Sculptor experiment.
- `linger-7etz` holds the baseline commit and stage-recall notes.
- `linger-j728` (closed) retired conversational surfacing; `linger-nxap`
  (closed) delivered part-scoped Librarian gathering.
- `linger-7etz.1` and `linger-7etz.3` track controlled repair and reviewer
  attribution work.
- `linger-d4o4` tracks Serendipity ranking restraint.
- `linger-124` tracks the system playbook, and `linger-a4u.3` tracks proving one
  curated result improves a retrieval consumer.
