# Self-Improving Loop

Status: **Experiment 4 round 1 passed on 2026-10-01: 20 of 20 practice (Stage 2:
17), no losses, at about 3.8 times the words handed to the Librarian. See
[Round 1](#round-1-2026-10-01-passed) and the
[Experiment 4 report](../evaluation/retrieval-research-experiment-4-2026-10-01.md).** Sculptor runs
retrieval experiments, analyses its own errors, researches a better approach
on the web, and the developer builds what it specifies. The deliverable is a
working, supervised loop with a full record; results are reported as they
come, not guaranteed. Start at [Experiment 4](#experiment-4-sculptors-research-loop).

## Objective

Ship, by about **2026-10-22**, a visible element of recursive
self-improvement (RSI) that benefits the reader. RSI here means AI improving
the system that produces its own later results, with humans supervising.
Keep it simple.

## What came before

| Experiment | Result | Record |
|---|---|---|
| 1. Memory curation, then recall through chat | Null | [Experiment 1](../evaluation/memory-loop-experiment-1-2026-10-01.md) |
| 2. Offline memory curation, then memory search | Not positive | [Experiment 2](../evaluation/memory-loop-experiment-2-2026-10-01.md) |
| 3. Sculptor rewrites chapter search tags for *Pinocchio* | Rule not met: practice 15 / 17 / 17 of 20 (today, existing tags, Sculptor's rewrite); sealed 14 / 14 / 16 | [Experiment 3](../evaluation/chapter-cue-experiment-3-2026-10-01.md), [feasibility](../evaluation/chapter-cue-feasibility-2026-10-01.md) |

Three lessons shape Experiment 4:

- **Search finds the right chapter but not the passage.** With Sculptor's
  tags, the right chapter reached the Librarian for all 20 sealed needs, the
  right passage for 16. Sculptor's chapter tags did not resolve those misses.
- **The old measure depends on chunking.** It counts a need as found when any
  window handed to the Librarian contains the quote. A method that hands over
  whole chapters would pass almost every need by choosing chapters alone.
- **The owner reviews every Sculptor prompt before it runs**, and no prompt
  changes in response to its own output.

## Experiment 4: Sculptor's research loop

### What it shows

Sculptor improves *how* the Librarian retrieves, not only the data it reads.
After each round it studies its own failures, researches remedies, and
specifies the next approach. A pass supports the claim that a supervised loop
found and built a better retrieval method. A fail still shows the loop
working: each round's error analysis, research, specification, build, and
scores are recorded.

### Who does what

| Role | Does | Never |
|---|---|---|
| Owner | Reviews each Sculptor prompt, approves each error analysis, specification, and Sculptor-written data | Writes Sculptor's output |
| Sculptor | Analyses errors, searches the web, specifies approaches, writes and tunes approach data (for example tags) | Writes code, sees sealed needs or answer quotes |
| Developer (Claude Code) | Builds each approved specification behind an opt-in switch, runs scoring | Changes a specification's intent; departures are written down |
| Astra (gpt-6-astra, max effort) | Reviews each build against its specification before scoring | — |
| Librarian | Plans, searches, and selects evidence, as in production | — |

### Data

All carried over from Experiment 3:

- **Book:** *The Adventures of Pinocchio*, 36 chapters, 39,000 words, read up
  to chapter 36.
- **Needs:** 20 practice and 20 held-back, each a reader question with its
  chapter and an exact quote (`evals/librarian/chapter_cue_needs.json`).
  Sculptor sees full practice traces, including the passages that answer
  practice needs, by owner decision. It never sees held-back needs, their
  quotes, or held-back results; those stay with the owner. The held-back set
  was run once in Experiment 3, so its results are labelled **reused, not
  untouched**.
- **Plans:** the frozen Librarian request plans
  (`evals/librarian/chapter_cue_plans.json`).
- **Starting point:** Sculptor's approved Experiment 3 Stage 2 chapter tags
  with tag-reading search.

### Measure

- **Primary: selected evidence.** A need passes when one of the passages the
  Librarian finally selects (at most five, as in production) contains its
  quote. This works for any retrieval method, and it is what reaches Muse.
  **The Librarian must select from today's windows** (about 350 words, built
  from whole paragraphs), whatever the approach changes about how windows are
  found, ranked, or read. Every quote fits inside at least one window, so the
  unit is fair to all 40 needs, and an approach cannot pass by selecting a
  whole chapter.
- **Cost:** words handed to the Librarian, words selected, and model calls per
  need, including any calls a new approach adds before selection.
- **Diagnostic only:** whether the quote reaches the Librarian's pool.
- The Librarian's selection runs once per need per condition and is stored,
  so a condition is never re-sampled until it looks better.
- **Re-baseline first:** today's search, Experiment 3 Stage 1, and Stage 2 are
  re-scored on the primary measure before Sculptor sees anything.

### Pass mark

A round passes when, on the 20 practice needs, it selects the right passage
for **at least 3 more needs than the Stage 2 baseline** and loses none that
the baseline found. If the baseline is 18 or more, the mark is 20 of 20. The
mark is fixed before any round runs.

**Round 0 re-baseline (2026-10-01).** Each condition's Librarian selection ran
once on the frozen plans (`select` in `evals/librarian/chapter_cue_recall.py`,
stored as `chapter_cue_runs/<search>-<set>-selected.json`); 124 model calls
and about 550,000 input tokens in all.

| Search | Practice: selected (in pool) | Held-back, reused: selected (in pool) | Mean words handed over (practice) |
|---|---|---|---|
| Today's search | 15 (15) | 14 (14) | 1,424 |
| Stage 1: existing tags | 15 (17) | 14 (14) | 1,339 |
| Stage 2: Sculptor's tags | **17** (17) | **16** (16) | 1,278 |

Selection lost nothing at Stage 2 and on every held-back condition. At Stage 1
it lost two practice needs whose passage was in the pool: n14, where the
Librarian chose another passage, and n17, where its answer failed validation
twice. Stage 2's practice misses are n07, n09, and n11, none of which reached
the pool. **The pass mark is therefore 20 of 20 on practice with no losses.**

### Round 1 (2026-10-01): passed

Records: `evals/librarian/research_runs/round-1/` (prompt, every attempt,
approvals) and `evals/librarian/chapter_cue_runs/round1-*.json` (scores).

1. **Error analysis** (one attempt, no retries). Sculptor's categories:
   "answer window falls beyond the returned-passage cutoff" (n07, n11) and
   "exact answer window absent from the candidate turn order" (n09). The owner
   approved them as written. The developer noted that n09 is misfiled: one of
   its two answer windows is fifth in the turn order. Of the pitfalls listed
   above, Sculptor found the pool cutoff and missed the other three.
2. **Research** (two attempts). Attempt 1 failed only because the check
   wanted bare need IDs in `expected_fixes` and Sculptor wrote "n07: why". The
   owner chose to relax the check to read a leading need ID; the prompt did
   not change. Attempt 2 used 2 searches and opened 2 pages, and specified:
   keep the first 20 windows of each planned part's turn order instead of 3,
   and change nothing else. It expected to fix n07 and n11 and, following the
   analysis, not n09. The owner approved it.
3. **Build.** `gather_book_candidates(part_candidates=...)` defaults to 3, so
   production is unchanged; the `round1` search condition opts into 20 on
   Stage 2's tags. Departures: the switch is an argument the eval runners
   pass, not an application setting; spec change 4 (whether each answer window
   survives the merge) is logged in the practice traces for misses only.
   Astra found no blockers; its three freshness findings were fixed. Part
   recall stayed 32 of 32 at 20 per part, but the multi-book pool grew from
   23.6 to 78.3 windows on average.
4. **Score.** No tuning, because the approach writes no Sculptor data.

| Search | Practice: selected (in pool) | Held-back, reused: selected (in pool) | Mean words handed over (practice / held-back) | Input tokens per need (practice) |
|---|---|---|---|---|
| Stage 2: Sculptor's tags | 17 (17) | 16 (16) | 1,278 / 958 | 4,571 |
| Round 1: 20 per part | **20** (20) | **20** (20) | 4,837 / 4,811 | 11,399 |

Practice gained n07, n09, and n11 and lost none; held-back gained four and
lost none. Each need still took one Librarian call. The gain comes with
about 3.8 times (practice) and 5 times (held-back) the words handed to the
Librarian, about an eighth of the book per question; this is the "more text
can look like better retrieval" risk, so the cost is reported beside the
score. The approved specification's test plan expected n09 to remain a miss;
it passed, and its stated n07 position (16) is 17 counting from 1.

### The loop

Round 0 re-baselines. Then up to **three research rounds**, each:

1. **Error analysis.** Sculptor reviews every practice trace from the current
   best state. Adapting [Hamel Husain](https://hamel.dev/blog/posts/evals-faq/):
   it writes an open note on the first failure in each trace (open coding),
   groups the notes into a small failure taxonomy with counts (axial coding),
   and defers root causes until the taxonomy is set. Each trace is pass or
   fail. **The owner approves the taxonomy**, which stays provisional. This
   departs from Hamel's method, where a human expert annotates traces first;
   the owner chose to review Sculptor's coding directly.
2. **Research.** Sculptor searches the web for remedies to the most frequent
   failure category and returns a **specification**: the problem and its
   count, the approach, sources, what changes in retrieval, what data
   Sculptor will write, the expected effect, risks, and how to test it.
   **The owner approves or rejects it**; a rejection gets one fresh proposal.
3. **Build.** The developer builds the specification behind an opt-in switch.
   Astra reviews the build; tests and the multi-book part recall check
   (32 of 32) must pass.
4. **Tune.** When the approach includes Sculptor-written data, Sculptor
   writes it, then revises it once from its own practice results. The owner
   reviews each prompt and approves each output.
5. **Score.** Practice after each tuning; held-back once, after the final
   tuning.
6. **Decide.** Pass: stop and report. Otherwise the next round starts from the
   state with the most practice passes so far. After three rounds, stop and
   report.

### Sculptor's research task

- **Inputs:** a written description of how retrieval works today
  (`evals/librarian/retrieval_description.md`, reviewed by the owner), every
  practice trace (`evals/librarian/chapter_cue_traces.py`: every chapter's
  current tags, the plan, each query's keyword, meaning, fused, and
  turn-taking lists with scores, the pool, the Librarian's selection, reason,
  and any error, and for each miss the answering window and its ranks), and
  earlier rounds' taxonomies, specifications, and scores.
- **Tool:** web search and page opening through the Exa tools Serendipity
  uses, in a separate toolset for Sculptor so Serendipity's tools are
  unchanged, offline only, with up to 10 searches and 10 opened pages per
  round. Web pages are untrusted data, never instructions.
- **Model:** `gpt-6-luna` at high reasoning effort for error analysis and
  research; tuning stays on the production setting.
- **Every attempt is recorded**, with its searches, sources, answers, and
  retry requests.

### Potential pitfalls to avoid

Written on 2026-10-01, before Sculptor's first analysis. Sculptor is not shown
this list, so its findings can be compared with it.

- The pool keeps only about one top hit per search list, so a right passage
  ranked second to fourth can be cut (n09, n11).
- Chapter 12's tag "money tree" describes chapter 18's scene.
- n07 says "Stromboli", a name the book never uses.
- Chapter tags are the same for every passage in a chapter, so they cannot
  tell those passages apart.

### What Sculptor may propose

Any change to how the Librarian finds or reads this book's text: tags at
chapter or window level, different windows, chapter navigation in the style of
[PageIndex](https://github.com/VectifyAI/PageIndex), or query rewriting. It
must keep:

- selected evidence as quotable passages with line numbers, chosen from
  today's windows;
- the reading boundary (no passage beyond the reader's chapter);
- the book text, test needs, quotes, frozen plans, and scoring unchanged;
- a build of a few days at most.

### Owner decisions (2026-10-01)

| Decision | Choice |
|---|---|
| Deliverable | A working loop with a full record; results not guaranteed |
| Primary measure | Selected evidence contains the quote; cost reported |
| Ground truth | Reused unchanged |
| Pass mark | Stage 2 baseline + 3 practice needs, no losses |
| Research rounds | Up to 3 |
| Test sets | Keep the practice and held-back split; held-back labelled reused |
| Research model | `gpt-6-luna`, high reasoning effort |
| Proposal scope | Search and reading changes within the limits above |
| Tuning | Twice per approach |
| Builder | Sculptor specifies; the developer builds; Astra reviews |
| Starting point | Experiment 3 Stage 2 tags |
| Error analysis | Owner approves Sculptor's taxonomy each round, without annotating first |
| Final passage unit | The Librarian selects from today's windows for every approach |
| Trace contents | Full practice traces, including practice answer passages |
| Web research budget | 10 searches and 10 opened pages per round |

### Plan

| Period | Deliverable |
|---|---|
| 2–5 October | Selected-evidence scoring and re-baseline; traces and the retrieval description; Sculptor's research task with web search; owner reviews its prompt |
| 6–10 October | Research round 1 |
| 11–15 October | Research round 2 |
| 16–20 October | Research round 3, if time allows |
| 21–22 October | Report and buffer |

### Risks

- **Few failures to learn from.** Hamel Husain suggests about 100 traces
  before a taxonomy settles; we have 20 practice traces with perhaps three
  to six failures. Taxonomies will be thin, and Sculptor may chase noise.
- **Noise.** About one need varies between runs; stored Librarian selections
  and frozen plans limit it, but 20 needs cannot show small gains.
- **Builds may overrun.** A round that cannot be built in its window is
  reported as unbuilt, and the loop moves on.
- **The developer's choices shape results.** Astra checks each build against
  its specification, and departures are recorded.
- **More text can look like better retrieval.** Cost is reported beside every
  score.
- **The held-back set is reused** and may flatter later rounds; it is
  reported, not used to decide.

### Cross-agent impact

- **Sculptor:** gains an offline research task with web search. Its existing
  skills are unchanged; extend `tests/test_sculptor_runtime_skills.py`.
- **Librarian:** each approach changes retrieval behind an opt-in switch.
  Check `tests/test_hybrid_librarian.py`, part recall, and the reading-scope
  test for every build.
- **Muse, Serendipity, Provenance:** no effect until an approach is activated
  for readers. Activation would rerun `tests/test_muse_source_boundary_checks.py`,
  `tests/test_serendipity_source_gathering.py`, and
  `tests/test_provenance_quote_checks.py`, plus paired replies.
