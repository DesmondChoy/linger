# Experiment 4: Sculptor's self-directed retrieval research

Run on 2026-10-01. **Pass mark met in round 1**, at a higher reading cost.
Design and context: [self-improving loop](../design/self-improving-memory-loop.md);
previous step: [Experiment 3](chapter-cue-experiment-3-2026-10-01.md).

## Question

Can Sculptor improve *how* the Librarian retrieves, not only the data it
reads? In each round Sculptor studies its own retrieval failures, researches
a remedy on the web, and specifies a change. The developer builds it, and the
owner approves every step.

## Method

- **Data.** *Pinocchio* (36 chapters, 166 windows of about 350 words); the
  20 practice and 20 held-back needs and the frozen Librarian plans from
  Experiment 3. Sculptor saw full practice traces, including the passages
  that answer practice needs. It never saw held-back needs, their quotes, or
  their results. The held-back set had already run once in Experiment 3, so
  its results are **reused, not untouched**.
- **Measure.** A need passes when a passage the Librarian finally selects
  (at most five) contains its quote. The Librarian runs once per need per
  condition, and the result is stored. Cost is words handed to the Librarian,
  input tokens, and model calls per need.
- **Starting point and pass mark.** The starting point was Experiment 3's Stage 2
  chapter tags: 17 of 20 practice and 16 of 20 held-back. A round passes with
  at least 3 more practice passes and no losses, which here means 20 of 20.
  The mark was fixed before any round ran.
- **Round.** Error analysis, then owner approval; web research and a
  specification, then owner approval; a build behind an opt-in switch with an
  Astra review; scoring. The owner reviewed each Sculptor prompt before it
  ran, and no prompt changed in response to its own output. Up to 3 rounds.
- **Sculptor.** `gpt-6-luna` at high reasoning effort. The research step
  used Exa web search, limited to 10 searches and 10 opened pages, could open
  only URLs its own searches returned, and could cite only pages it opened.
- **Tooling.** `evals/librarian/research_loop.py` (`analyse`, `approve`,
  `research`), `evals/librarian/chapter_cue_recall.py` (`score`, `select`),
  `evals/librarian/chapter_cue_traces.py`. Records are in
  `evals/librarian/research_runs/round-1/` and
  `evals/librarian/chapter_cue_runs/round1-*.json`.

## Round 1

1. **Error analysis.** Sculptor read all 20 practice traces and put the 3
   misses in two categories. "Answer window falls beyond the
   returned-passage cutoff" held n07 and n11. "Exact answer window absent
   from the candidate turn order" held n09. n09 was misfiled: one of its
   two answer windows was fifth in the turn order. The owner approved the
   analysis as written.
2. **Research and specification.** Sculptor targeted the larger category. It
   specified keeping the first 20 windows of each planned part's search
   results instead of 3, with everything else unchanged: ranking, the
   20-window pool cap, the overlap filter, and the 5-window selection cap. It
   rejected changing the ranking, because both answer windows were already
   among the candidates. It cited two retrieve-then-rerank papers on larger
   candidate pools. It expected to fix n07 and n11, and, trusting the
   analysis, not n09. The owner approved it.
3. **Build.** `gather_book_candidates(part_candidates=...)` defaults to 3,
   so production is unchanged; the `round1` search condition uses 20 on
   Stage 2's tags. Multi-book part recall stayed 32 of 32 at 20 per part.
4. **Score.** No tuning step, because the approach writes no Sculptor data.

## Results

| Search | Practice: selected (in pool) | Held-back, reused: selected (in pool) | Mean words handed over (practice / held-back) | Mean windows in pool (practice) | Input tokens per need (practice) |
|---|---|---|---|---|---|
| Stage 2: Sculptor's tags | 17 (17) | 16 (16) | 1,278 / 958 | 4.2 | 4,571 |
| Round 1: 20 per part | **20** (20) | **20** (20) | 4,837 / 4,811 | 15.5 | 11,399 |

- Practice gained n07, n09, and n11 and lost none. Held-back gained s01,
  s02, s10, and s20 and lost none.
- Both conditions used the same Librarian model (`gpt-6-luna`) and prompt
  digest, one call per need, with no errors. Round 1 selected 403 words per
  practice need on average. Stage 2's records predate that field.
- The Librarian read about 3.8 times as many words per practice need
  (5 times on held-back), roughly an eighth of the book per question. Input
  tokens rose 2.5 times.
- In the multi-book scenario used for part recall, 20 per part would grow
  the pool from 23.6 to 78.3 windows on average.

**Decision:** round 1 meets the pass mark, so the loop stopped after one
round. The 20-per-part setting is not active for readers.

## Spend

- Sculptor: 11 model requests. The analysis took 1. Research took 5 in each
  of 2 attempts, with 5 Exa searches and 5 opened pages in total.
- Librarian selection: 40 calls (20 practice, 20 held-back) and about
  455,000 input tokens.
- One Astra review.

## Process record

- The owner approved both round 1 prompts before any call. The error
  analysis succeeded on its first attempt with no retries.
- **Research attempt 1 failed on our contract, not its content.** The check
  wanted bare need IDs in `expected_fixes`; Sculptor wrote "n07: why" each
  time, and the retry message never said "IDs only". The owner chose to
  relax the check to read a leading need ID, with the prompt unchanged.
  Attempt 2 then passed with no retries. Both attempts are recorded.
- **Developer departures**, recorded for review:
  - The switch is an argument the eval runners pass, not an application
    setting.
  - Specification change 4, which logs whether each answer window survives
    into the pool, is recorded in the practice traces for misses only.
- **Astra review:** no blockers, and production unchanged with the switch
  off. Three freshness gaps were fixed before scoring, two of them older
  than this build: stored scores, resumed selections, and Sculptor's traces
  are now refused when needs, plans, or approvals change. Astra also noted
  that the specification's test plan expected n09 to stay a miss, and that
  the specification put n07's answer 16th where the trace shows 17th.
- The full suite passed (2,623 tests) before Astra's fixes, and the
  affected tests passed after them.

## Interpretation

- **The loop worked end to end.** Sculptor found the cause, proposed a fix
  within the limits, and the fix met a pass mark set in advance, with no
  losses on either set. Every Sculptor step is recorded with the owner's
  approval.
- **Sculptor found the main pitfall independently.** The developer's
  pitfalls list, written before the analysis and never shown to Sculptor,
  named the pool cutoff first. Sculptor missed the other three: chapter
  12's misleading "money tree" tag, "Stromboli" (a name the book never
  uses) in n07, and chapter tags being identical across a chapter's windows.
  None of the three stopped a need from passing this round.
- **The value came from reading traces, not from the web.** Sculptor used
  2 of 10 searches. Its sources support larger candidate pools in general,
  not 20 in particular.
- **Better retrieval here means reading more.** This is the "more text can
  look like better retrieval" risk the design named, so cost is reported
  beside every score. At 20 a part keeps every candidate its search returns
  (at most 20); whether a smaller value keeps the gains is untested.
- **Small samples.** 20 practice needs, about one of which varies between
  runs, and a reused held-back set. The held-back gain is supporting
  evidence, not proof.

## Lessons for the next experiment

- **State output formats in the contract and the retry message.** One
  research run was lost because neither said "need IDs only".
- **Give Sculptor positions, not just lists.** It misread n09 in a long JSON
  trace. Round 2 traces would carry `answer_turn_order`, which states each
  answer window's position and whether it reached the pool.
- **Measure the cost-recall trade-off before activation.** Scoring the
  local pool at 5 and 10 per part needs no model calls. Activation for
  readers would also need the multi-book cost decision and the Muse,
  Serendipity, and Provenance checks listed in the design's cross-agent
  impact section.
