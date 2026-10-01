# Memory Loop Design and Experiment 1

Back to [Self-Improving Memory Loop](../design/self-improving-memory-loop.md). Next:
[Experiment 2](memory-loop-experiment-2-2026-10-01.md).

The memory-curation design, dated memories, and the first graded end-to-end
run. Superseded on 2026-10-01 by Experiment 3 in the design document.

## Implementation

The runner reuses Sculptor `memory-curation`, Provenance `curation-review`, and
Serendipity memory recall. Successive rounds needed one adjustment: Sculptor
used to receive original IDs and texts without earlier curation decisions.
Its typed input and skill instructions now include that state as
`existing_curation`, which is omitted while no curation exists. Each memory
also carries `recorded_at` when known, which Provenance's curation review sees
too, so Sculptor can order an evolving fact without relying on wording.

| File | Change |
|---|---|
| `evals/synthetic_journals/memory_loop_replay.py` | **Done.** Per repetition, seeds Props, sends the recall Lines, then alternates one production `run_curation_loop` round with the Lines again, for 0 to 3 cumulative rounds. Reuses `retrieval_replay.py`. |
| [`synthetic-journal-evaluation/scenarios/supper-club-curation-then-recall--muse-serendipity-sculptor-provenance--2026-09-30/`](../../synthetic-journal-evaluation/scenarios/supper-club-curation-then-recall--muse-serendipity-sculptor-provenance--2026-09-30/pre-generation-report.md) | **Adopted 2026-10-01.** One Scenario, written directly without `plan-synthetic-scenarios`, then independently adopted with `review-synthetic-ground-truth`. |
| `synthetic-journal-evaluation/generation-presets/memory-curation-recall-loop.json`, `evals/synthetic_journals/models.py`, `evals/synthetic_journals/validate_scenario.py` | **Done.** A run configuration that pre-registers three rounds and three repetitions, with validator rules for the shared Prop bank and recall Scenes. |
| `src/linger/agents/sculptor/models.py`, `src/linger/services/memory.py`, `src/linger/orchestration/curation.py`, `src/linger/agents/sculptor/skills/memory-curation/SKILL.md` | **Done.** Supply and explain prior curation state for successive rounds. |
| `evals/synthetic_journals/replay_support.py`, `synthetic-journal-evaluation/evaluation-objectives.yaml` | **Done in `replay_support.py`.** The Scenario declares only `longitudinal_memory_retrieval` and the `memory-curation-recall-loop` run configuration, which selects the runner. Curation is the runner's treatment, not a graded Scene. The Objective catalogue is unchanged. |
| `src/linger/agents/serendipity/tools.py`, Muse `reflection` skill, Provenance review | **Not done.** Carry a derived summary's kind and source references through recall. `search_memories` returns only an ID and text today, and Muse treats recalled text as the reader's exact words. |
| `tests/test_memory_loop_replay.py` | **Done.** Runner logic with injected models, including state passed between rounds and scoring of derived evidence. |
| `evals/synthetic_journals/offline_search_loop.py`, `tests/test_offline_search_loop.py`, the Scenario's `offline-search-preregistration.json` | **Run 2026-10-01, removed after.** Experiment 2: unreviewed Sculptor rounds and production memory search over frozen queries. Recoverable from commit `3926c86`. |
| `docs/specification.md` §7.2.2 and §9, `evals/synthetic_journals/README.md` | The README describes the runner. The specification waits for a measured result. |

## How it works

The new Scenario holds ten memories for one reader: a fact that changed, a
set of duplicates, a memory those duplicates crowd out of search, a memory
reachable only by paraphrase, a memory curation should preserve, and a
question no memory answers. Five recall Lines are held out from Sculptor.

- **Arm A:** recall against the raw memories.
- **Arm B:** the same Lines after one, two, and three curation rounds. Each
  round builds on the previous curation state.

Code, model, prompts, and Lines are frozen, and each arm runs three times.
Each repetition starts from identical originals; recall uses fresh sessions.
Measures are fixed beforehand: the right evidence is cited, the reply states
the current fact, and hard gates still pass.

The existing retrieval grader expects original record IDs. The new runner
also reduces summaries and topic groups to their source references, applies
the same relevance rules to those sources as to directly cited records, and
lets a retrievable duplicate stand in for a copy hidden from retrieval. A
separate human review checks whether the sources support the summary and
answer. Generated wording must remain distinguishable from the reader's exact
words; production recall does not yet carry that distinction, so the runner
lists every cited summary with its sources for that review.

**Before.** The reader said "I host on Thursdays", later "it moved to
Tuesdays", and repeated one reflection three times. A memory search returns
at most five records, matched by shared words; recall selects up to three.
Duplicates can occupy those slots, and Muse may repeat the stale day.

**After.** The intended result is that Sculptor links duplicates, hides
extra copies from retrieval, and writes a summary that keeps the correction.
Each round proposes one action, and hiding a copy takes a link and then a
tombstone, so three rounds complete only part of this work. The evaluation
checks whether recall returns the current fact and fewer duplicates.

## Dated memories

Memories originally carried no date that any agent could see: Sculptor
received only each memory's ID and text. During Ground truth review, the
reviewer asked how Sculptor could tell which of two conflicting notes came
later, such as "I host supper club on Thursdays" and "Supper club has moved to
Tuesdays". It could only infer the order from wording such as "has moved" or
"from now on", and two notes without such wording could not be ordered at all.

Memories now carry the time each one was captured:

- **Scenario format.** A Prop may have an optional, timezone-aware
  `recorded_at`. The ten supper-club Props are dated from 5 February to
  7 July 2026. They are listed out of date order, so list position does not
  reveal which note came first. The review app shows each Prop's date.
- **Production.** A stored memory's `created_at`, set when Linger captures it,
  is its capture time. `MemoryPolicyService.recorded_at` returns it, or nothing
  when the stored value is not a valid timezone-aware time.
- **Replays.** The curation replays and the memory loop report a Prop's own
  `recorded_at`, never the synthetic record's placeholder or seeding time. A
  Prop without a date reaches agents without one.

Dates reach two agents:

- **Sculptor** receives `recorded_at` on each memory in its curation input,
  when known. Its skill treats it as capture time, not event time. Dates
  stated in a note's text come first. Capture order decides only when every
  cited note has a distinct time. Otherwise the wording decides, or the
  conflict stays unresolved.
- **Provenance** receives the same `recorded_at` on each source in curation
  review. It checks that a summary's claim that one version replaced another
  follows the same rules.

Muse, Serendipity, and Librarian do not receive dates. Recall still returns only
a memory's ID and text, so Muse orders recalled notes from their wording.
Carrying dates and derived-record labels through recall is tracked in
`linger-gn7a`.

## Experiment 1: first graded run (2026-10-01)

**Setup.** The run used adopted Ground truth for the supper-club Scenario, the
`memory-curation-recall-loop` run configuration, and `openai:gpt-6-luna` for
every agent. Each of three repetitions sent the five recall Lines through
production chat on raw memories and after one, two, and three cumulative
production curation rounds with real Provenance review: 60 recall turns and 9
curation rounds in total. Run `41689cbd`;
[Logfire experiment](https://logfire-us.pydantic.dev/desmond-choy/linger/evals/memory_curation_recall_loop/compare?experiment=01a0f4b0f74248691761a2d69b0606ad-fe6452080c9f650c).

**Curation.** Every summary Sculptor wrote stated the Thursday-to-Tuesday move
correctly.

| Repetition | Round 1 | Round 2 | Round 3 |
|---|---|---|---|
| 1 | Night summary applied | All three reflection copies linked | One copy hidden |
| 2 | Night summary sent back for revision | Night summary sent back for revision | Night summary applied |
| 3 | Night summary applied | Two identical copies linked | One copy hidden |

**Recall.** Hard-gate passes out of three repetitions:

| Scene | Raw | 1 round | 2 rounds | 3 rounds |
|---|---|---|---|---|
| Which night now, and before (changed fact) | 3/3 | 2/3 | 3/3 | 1/3 |
| Tried several new recipes before (crowded out) | 0/3 | 1/3 | 1/3 | 1/3 |
| What helped with nerves (paraphrase only) | 0/3 | 0/3 | 0/3 | 0/3 |
| Nut allergy (preservation check) | 2/3 | 3/3 | 3/3 | 3/3 |
| Charging guests (no relevant memory) | 2/3 | 3/3 | 3/3 | 3/3 |

**Analysis.** The result is null: no change in the table can be attributed to
curation.

- **The night summary was never used.** In all seven arms where it existed,
  Serendipity recalled the two original notes instead. The four night
  failures were not recall failures. Provenance sent each reply back twice
  because the Thursday note does not itself say that Thursday was the former
  night, and the application then declined to answer. Several passing replies
  hedged for the same reason. Provenance's strictness about "used to"
  inferences caused more failures than anything curation changed.
- **The recipe improvement does not follow the curation.** Two of the three
  passes came in arms where no reflection copy had been hidden; only one came
  after a copy was hidden. Which memories search returned varied with how
  Serendipity worded each query.
- **The paraphrase-only memory was never found**, as the search dry run
  predicted. Two of those twelve turns also hit Muse model failures.
- **The nut-allergy and charging Scenes** each had one miss on raw memories and
  none afterwards, which is within run-to-run variation.
- **No reply cited a summary**, so the misattribution risk in `linger-gn7a`
  was not exercised.

No pass threshold was written down before the run. The threshold proposed
during review is not met: the night and recipe Scenes passing in at least two
of three repetitions after three rounds but not on raw memories, with the
nut-allergy and charging Scenes holding at 3/3.

The end-to-end design measured too much at once. Turn triage, Serendipity's
query and record choices, Muse's wording, and Provenance's release review each
added more variation than curation removed. Curation acts on what memory search
can find, so the next experiment measures that directly.

## Critical notes for the memory experiments

- **The result may be null.** Report every repetition, including no-change,
  rejected, and failed curation outcomes.
- **Claim only what the results support.** A positive result shows improved
  recall in this Scenario. Improvement "with use" still needs evidence through
  ordinary conversation and capture. This experiment does not feed recall
  outcomes back into future curation, so stronger RSI claims remain unproven.
- **Capture is off by default**, so the benefit is shown in controlled
  evaluation. The runner calls `run_curation_loop` directly, not the
  capture-triggered chat path.
- **Human adoption of Ground truth** is required before graded runs. Start
  the Scenario first.
- **Cross-agent impact:**
  - Muse: answers may change, and recalled summaries must not be presented as the reader's words; check the recall runs.
  - Librarian: no effect in this memory-only Scenario.
  - Serendipity: retrieved evidence may change; check recall runs and `tests/test_serendipity_memory_recall.py`.
  - Provenance: reviews changed proposals and replies, and sees each source's `recorded_at` in curation review; check recall runs and `tests/test_curation_provenance.py`.
  - Sculptor: receives prior curation state once any exists, in chat-triggered curation as well; first-round input is unchanged. Check `tests/test_memory_loop_replay.py`, `tests/test_synthetic_curation_replay.py`, and the bounded-curation replay.
- **Deferred:** the developer playbook (§9.2). Track this choice in
  `linger-heza`.
