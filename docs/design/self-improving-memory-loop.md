# Self-Improving Memory Loop

Status: **Runner implemented; no graded run yet**

## Objective

Ship the smallest feature that shows recursive self-improvement (RSI) and
benefits the reader, not only the developer.

- **RSI** here means AI improving the system that produces its own later
  results, with humans still supervising.
- **ACE** ([Agentic Context Engineering](https://arxiv.org/html/2510.04618v3))
  uses task feedback to improve context for later tasks.
  The model stays fixed; its *context* improves. A Generator does tasks, a
  Reflector extracts what is worth keeping, and a Curator merges that into a
  structured store through small edits.

Linger has a related shape for a reader's memories: Muse converses and
nominates memories, and Sculptor curates them. Nothing
yet shows that curation improves later conversations. **The feature is that
evidence: one chained evaluation.**

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
| [`synthetic-journal-evaluation/scenarios/supper-club-curation-then-recall--muse-serendipity-sculptor-provenance--2026-09-30/`](../../synthetic-journal-evaluation/scenarios/supper-club-curation-then-recall--muse-serendipity-sculptor-provenance--2026-09-30/pre-generation-report.md) | **Generated, not adopted.** One Scenario, written directly without `plan-synthetic-scenarios`. It needs independent adoption with `review-synthetic-ground-truth`. |
| `synthetic-journal-evaluation/generation-presets/memory-curation-recall-loop.json`, `evals/synthetic_journals/models.py`, `evals/synthetic_journals/validate_scenario.py` | **Done.** A run configuration that pre-registers three rounds and three repetitions, with validator rules for the shared Prop bank and recall Scenes. |
| `src/linger/agents/sculptor/models.py`, `src/linger/services/memory.py`, `src/linger/orchestration/curation.py`, `src/linger/agents/sculptor/skills/memory-curation/SKILL.md` | **Done.** Supply and explain prior curation state for successive rounds. |
| `evals/synthetic_journals/replay_support.py`, `synthetic-journal-evaluation/evaluation-objectives.yaml` | **Done in `replay_support.py`.** The Scenario declares only `longitudinal_memory_retrieval` and the `memory-curation-recall-loop` run configuration, which selects the runner. Curation is the runner's treatment, not a graded Scene. The Objective catalogue is unchanged. |
| `src/linger/agents/serendipity/tools.py`, Muse `reflection` skill, Provenance review | **Not done.** Carry a derived summary's kind and source references through recall. `search_memories` returns only an ID and text today, and Muse treats recalled text as the reader's exact words. |
| `tests/test_memory_loop_replay.py` | **Done.** Runner logic with injected models, including state passed between rounds and scoring of derived evidence. |
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

## Critical notes

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
