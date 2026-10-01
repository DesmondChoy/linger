# Experiment 3: Sculptor chapter cues for book retrieval

Run on 2026-10-01. **Decision rule not met.** Design and context:
[self-improving loop](../design/self-improving-memory-loop.md); preparation:
[chapter-cue feasibility check](chapter-cue-feasibility-2026-10-01.md).

## Question

Can Sculptor improve *Pinocchio* retrieval by rewriting each chapter's search
aids (`routing_description`, `characters`, `retrieval_cues`), then improve
again from its own first rewrite's failures?

## Method

- **Search wiring.** Each roughly 350-word search window gets a search-only
  text: the window, then its chapter's aids. Keyword search, embeddings, and
  the reranker read it; quoted excerpts and citations stay canonical. Placing
  aids before the window instead pushed long windows past the embedding
  model's 512-token limit and lost a required Keller passage in part recall
  (32 to 29 of 32); placed after, part recall stays 32 of 32. The switch is
  `HybridLibrarian(read_chapter_cues=True)`, off in production.
- **Data.** 20 practice needs (visible to Sculptor as questions and outcomes,
  never quotes) and 20 sealed needs written by gpt-6-astra, in
  `evals/librarian/chapter_cue_needs.json`. One production Librarian planning
  pass per need is frozen in `evals/librarian/chapter_cue_plans.json`.
- **Measure.** A need is reached when a passage in the Librarian's assessment
  pool contains its quote, under production limits.
- **Stages.** Stage 1: existing aids. Stage 2: Sculptor's first rewrite.
  Stage 3: Sculptor's second rewrite from Stage 2's outcomes and its own named
  failure patterns. 60 words per chapter; every chapter revised. The owner
  reviews each Sculptor prompt before it runs and approves each proposal. The
  loop stops when a stage brings no net practice gain or loses a Stage 1
  success; then the sealed set runs once per stage.
- **Tooling.** `evals/librarian/chapter_cue_recall.py` (`freeze`, `propose`,
  `approve`, `score`); Sculptor skill `sculptor.chapter-cues`; artifacts in
  `evals/librarian/chapter_cue_runs/`.

## Results

| Search | Practice reached | Sealed reached (run once) |
|---|---|---|
| Today's search | 15/20 | 14/20 |
| Stage 1: existing aids | 17/20 | 14/20 |
| Stage 2: Sculptor's first rewrite | 17/20 | 16/20 |

- Stage 2 gained practice n08 and lost n11 (within chapter 22), so the stop
  rule ended the loop and Stage 3 did not run.
- On sealed needs, Stage 2 gained s03 and s16 over Stage 1 with no losses.
- Every remaining sealed miss at Stage 2 has the right chapter in the pool but
  not the passage. Chapter-level recall at Stage 2: practice 18/20, sealed
  20/20.
- Stage 2 aids averaged 38 words per chapter against 34, so longer aids may
  contribute to the gain.

**Decision rule:** sealed gain (Stage 3 at least 3 above Stage 1) and
recursion (Stage 3 above Stage 2) were not met, because Stage 3 did not run.
Reader replies were not checked. Integrity held: quotes and citations stayed
canonical, and the reading-scope test passed. Approved aids are not active.

## Process record

- A first Stage 2 run was discarded by the owner: its skill instructions were
  changed after seeing its first draft (which halved the aids) without the
  owner's review. From then on the owner reviewed every Sculptor prompt before
  it ran, and no prompt changed in response to its own output.
- The approved Stage 2 prompt kept three rules added after that draft: keep
  accurate aids, aim for about three quarters of the budget, and apply every
  named fix. Attempt 1 ran out of retries unrecorded; attempt 2's first answer
  exceeded the budget in many chapters and its retry passed.
- Sculptor did not add "Stromboli" (practice n07) and kept chapter 12's
  misleading "money tree". Its approved proposal was not fact-checked in full.
- gpt-6-astra reviewed the Stage 1 wiring and the Stage 2 machinery; its
  findings were fixed before the runs.

## Lessons for the next experiment

- **The passage, not the chapter, is the bottleneck.** Chapter aids cannot
  separate windows within one chapter.
- **The pool measure depends on chunking.** A method that hands the Librarian
  whole chapters would reach nearly every need by choosing chapters alone, so
  a fair comparison must score the evidence the Librarian finally selects.
- **Twenty practice needs leave few failures** to learn from: three misses at
  Stage 1.
