# Self-Improving Memory Loop

Status: **Experiment 3 has run; its decision rule is not met.** On practice,
Stage 1 reached 17 of 20 (today's search 15) and Stage 2 also 17, so the stop
rule ended the loop before Stage 3. On the 20 sealed needs, run once: today 14,
Stage 1 14, Stage 2 16. The owner decides what follows. The memory-curation
Experiments 1 and 2 are superseded. Start at [Where things stand](#where-things-stand-2026-10-01).**

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

## Where things stand (2026-10-01)

A fresh session should start here, then read
[Experiment 3](#experiment-3-sculptor-chapter-cues-for-book-retrieval).

### Direction

- The feature must ship by about **2026-10-22**, show a visible element of
  recursive self-improvement, and benefit the reader. Keep it simple.
- **Memory curation is superseded.** See [Experiment history](#experiment-history).
- **A developer playbook was rejected.** A lessons file that improves
  Sculptor's instructions mainly helps the developer.
- **Experiment 3 is the plan.** Sculptor rewrites each book chapter's search
  tags. Search reads them beside each passage, and Sculptor's second rewrite
  learns from the first one's failures. Every reader asking about the book
  benefits.

### Findings so far

The [chapter-cue feasibility check](../evaluation/chapter-cue-feasibility-2026-10-01.md)
ran 20 practice needs about *Pinocchio* through production search:

| Search reads | Needs reaching the Librarian's assessment |
|---|---|
| Today's search | 14 of 20 |
| Existing chapter tags | 16 of 20 |
| Hand-revised tags, in keyword, embedding, and reranker input | 19 of 20 |

No condition lost a need. All but one miss were search choosing the wrong
chapter. Tags only help when every search stage reads them, and existing tags
can mislead. The probe tags were written knowing the needs, so they show the
mechanism can work, not that Sculptor will find good tags. Planning varies by
about one need between runs.

Where the tags sit beside the passage matters. With tags placed before each
passage, the multi-book part recall check lost one required passage (32 of 32
fell to 29 of 32, all three Scene 06 plans): the Keller passage about the
Wrentham lake summer, whose section's tags describe rowing and theatre, not
the lake. Mean pool size also grew from about 24 to 27 records. Tags before
the passage push the passage's tail past the embedding model's 512-token
limit; Astra measured 59 of 166 Pinocchio windows truncated with them
against 3 without. Placed after the passage, as doc2query does, the tags keep part
recall at 32 of 32 with an unchanged pool of about 24 records. Stage 1 uses
that placement. Its effect on the Pinocchio practice needs is not yet
measured.

### Decisions by the owner

- Stages are named **Stage 1: baseline**, **Stage 2: Sculptor's first
  rewrite**, and **Stage 3: Sculptor's second rewrite**.
- **20 practice and 20 sealed needs.** Five of each would leave about one miss,
  the size of run-to-run noise.
- **Sealed labels are accepted without prior review.** The owner reviews
  questions, quotes, and results afterwards and triggers any change.
- **No spoiler or no-answer safety set.** It is outside the self-improvement
  question. One automated reading-scope test covers the risk the tags add.
- **The owner approves each Sculptor rewrite** at Stages 2 and 3, which is the
  human supervision in the claim. The owner may drop this.
- Astra (gpt-6-astra) runs at **max** reasoning effort.
- **The owner reviews the exact Sculptor prompt before each stage**
  (2026-10-01). Once a stage runs, its prompt is not changed in response to
  that stage's output; a bad output is approved and measured, or rejected.
- **Chapter tags are opt-in until activation** (2026-10-01). Search reads
  them only when constructed with `HybridLibrarian(read_chapter_cues=True)`.
  Production search is unchanged until the sealed run passes and the owner
  approves activation. The owner chose this when tags placed before the
  passage lost the Keller passage; the after-passage placement no longer
  loses it.

### Stage 1 on practice needs

Scored on 2026-10-01 with request plans frozen from one production planning
pass (`openai:gpt-6-luna`), so search is the only difference:

| Search | Practice needs reached | Misses |
|---|---|---|
| Today's search | 15/20 | n01, n07, n08, n09, n18 |
| **Stage 1: existing chapter cues** | **17/20** | n07, n08, n09 |

Stage 1 gains n01 and n18 and loses nothing, in line with the feasibility
check (14 to 16; plans differ slightly between planning passes). The three
remaining misses are what Sculptor's first rewrite sees:

- **n07** (chapter 11): the question names "Stromboli", a name the book never
  uses for Fire Eater; search chooses chapters 24, 10, and 6.
- **n08** (chapter 12): every pool passage is from chapter 18. Chapter 12's
  cue "money tree" belongs to chapter 18's coin-burying scene.
- **n09** (chapter 18): chapter 18 is in the pool, but its coin-burying
  passage is not; chapter 12 also competes.

Per-need pools are in `evals/librarian/chapter_cue_runs/`.

### Done

| Item | Where |
|---|---|
| Experiments 1 and 2 (superseded). Experiment 1's runner stays; Experiment 2's runner was removed and is recoverable from commit `3926c86` | [Experiment 1](../evaluation/memory-loop-experiment-1-2026-10-01.md), [Experiment 2](../evaluation/memory-loop-experiment-2-2026-10-01.md) |
| Feasibility check; probe scripts were in a session scratchpad and are not kept | [Chapter-cue feasibility](../evaluation/chapter-cue-feasibility-2026-10-01.md) |
| Frozen practice and sealed needs | `evals/librarian/chapter_cue_needs.json` |
| Stage 1 search wiring, opt-in: separate search text, cue digest in the index cache key, reading-scope test | `apps/backend/hybrid_librarian.py`, `tests/test_hybrid_librarian.py` |
| Frozen request plans for all 40 needs, the recall runner, and Stage 1 practice scores | `evals/librarian/chapter_cue_plans.json`, `evals/librarian/chapter_cue_recall.py`, `evals/librarian/chapter_cue_runs/` |

Stage 1 wiring is pushed on `main` at `09cf01a`.

### Beads

- Epic `linger-g3rw`: Experiment 3, in dependency order. `linger-g3rw.1`
  sealed set, `linger-g3rw.2` Stage 1 wiring, and `linger-g3rw.4` frozen
  plans and Stage 1 practice score are **closed**; `linger-g3rw.3`, the
  Sculptor chapter-cue skill and the Stage 2 and 3 runner, is **in
  progress**: Stage 2 is scored and the stop rule has fired.
- Experiment 2 follow-ups: `linger-p9iw` (derived summaries competing in
  memory search), `linger-4uix` (Cyrillic in a topic label), `linger-9j42`
  (capture time turned into an event date).

### Next steps

1. **Stage 1 wiring (`linger-g3rw.2`), done.** Each candidate has a search
   text (the passage, then its chapter's `routing_description`, `characters`,
   and `retrieval_cues`) used by the keyword index, embeddings, and reranker;
   excerpts and citations stay canonical. It is off unless
   `read_chapter_cues=True`. Part recall is 32 of 32 both ways
   (`uv run python -m evals.librarian.part_recall [--read-chapter-cues]`).
   Astra reviewed the wiring; its cache, test, and placement findings are
   fixed.
2. **Frozen request plans (`linger-g3rw.4`), done.** One production planning
   pass for all 40 needs, in `evals/librarian/chapter_cue_plans.json`.
   `uv run python -m evals.librarian.chapter_cue_recall freeze` refuses to
   overwrite them.
3. **Stage 1 practice score, done.** `uv run python -m
   evals.librarian.chapter_cue_recall score [--read-chapter-cues]` replays
   the frozen plans locally: 15 of 20 today, 17 of 20 at Stage 1. The sealed
   set has not been scored.
4. **Sculptor chapter-cue skill (`linger-g3rw.3`), built.** One typed
   skill, `sculptor.chapter-cues`, on Sculptor's existing Agent. Input: every
   chapter's text and current tags, a 60-word budget per chapter, and each
   earlier stage's practice outcomes with the failure patterns Sculptor named.
   Output: failure patterns and revised tags for every chapter. Coverage and
   budget errors are retried in-run (two retries). Sculptor's shared
   instructions now name this task beside memory curation and surfacing.
5. **Stage 2, done: 17 of 20, no net gain.** The owner reviewed and approved
   the prompt (`chapter_cue_runs/stage2-prompt.md`, kept with the ⚠ paragraph,
   two retries, and the production model). Attempt 1 ran out of retries and
   its details were not recorded; the runner now keeps every attempt in
   `chapter_cue_runs/stage2-attempts/`. Attempt 2's first answer exceeded the
   budget in many chapters (up to 87 words) and its first retry passed. The
   owner approved the proposal as written: mean 38 words per chapter (30 to
   59), against 34 at Stage 1. Sculptor named three patterns: chapter 11's
   pity sneeze and Harlequin's pardon, chapter 12's first meeting confused
   with chapter 18, and chapter 18's miss being within the chapter. It did not
   add "Stromboli", and it kept chapter 12's "money tree".

   | Search | Practice reached | Misses |
   |---|---|---|
   | Today's search | 15/20 | n01, n07, n08, n09, n18 |
   | Stage 1: existing cues | 17/20 | n07, n08, n09 |
   | Stage 2: Sculptor's first rewrite | 17/20 | n07, n09, n11 |

   Stage 2 gains n08 and loses n11. The n11 pool still holds a chapter 22
   window, but not the one with the quote, so the loss is within the chapter.
   No net gain and a lost Stage 1 success trigger the stop rule, and
   `propose --stage 3` refuses to run. Under the decision rule, the
   recursion criterion (Stage 3 beats Stage 2) can no longer be met.
6. **Sealed run, done (owner decision: follow the rule and report).** Each
   search ran once on the 20 sealed needs; `sealed-lock.json` freezes the
   approved Stage 2 proposal, the plans, and the needs.

   | Search | Sealed reached | Misses |
   |---|---|---|
   | Today's search | 14/20 | s01, s02, s03, s10, s18, s20 |
   | Stage 1: existing cues | 14/20 | s01, s02, s03, s10, s16, s20 |
   | Stage 2: Sculptor's first rewrite | 16/20 | s01, s02, s10, s20 |

   Against Stage 1, Stage 2 gains s03 and s16 and loses nothing. Against
   today's search, it gains s03 and s18 and loses nothing. Stage 1 alone
   trades s16 for s18. All four remaining Stage 2 misses (s01, s02, s10, s20)
   find the right chapter but not the passage, which chapter cues cannot fix.

   **Decision rule outcome: not met.** Sealed gain needs Stage 3 at least 3
   above Stage 1; Stage 2 is 2 above, and Stage 3 did not run. Recursion
   needs Stage 3 to beat Stage 2; it did not run. Reader benefit was not
   checked, since the retrieval criteria already fail. Integrity holds:
   quotes and citations stay canonical, and the reading-scope test passes.

   What the evidence supports: one owner-approved Sculptor rewrite raised
   sealed retrieval from 14 to 16 of 20 with no losses, while practice stayed
   flat (17 to 17). With about one need of run-to-run noise and 20 needs per
   set, this is a weak positive signal for a single supervised rewrite, not
   evidence of recursive improvement. Stage 2 cues average 38 words against
   34, so longer cues may contribute. Approved cues are not activated.
7. **Paired reader replies** were not run (see above).
   An earlier Stage 2 run on 2026-10-01 was discarded by the owner, because
   the skill instructions were changed after seeing its first output without
   the owner's review. Its results were deleted and Stage 1 was rescored
   (unchanged: 15 and 17 of 20).

   Astra reviewed the Stage 2 machinery on 2026-10-01. Its fixes stand: each
   score records the needs, plans, and approved proposal it used, and the next
   stage refuses stale feedback; Stage 3 refuses to start without a net Stage
   2 gain or after any lost Stage 1 success; approval and scoring re-check
   coverage, budget, and blank fields; the first sealed score locks every
   stage, and each sealed score runs once.


## Experiment history

| Experiment | Result | Record |
|---|---|---|
| 1. End-to-end memory curation, then recall through chat (supper-club Scenario) | Null: Muse, Serendipity, and Provenance added more variation than curation removed | [Memory loop design and Experiment 1](../evaluation/memory-loop-experiment-1-2026-10-01.md) |
| 2. Offline, Sculptor only: unreviewed curation, then memory search over frozen queries | Not positive: a summary that left its sources searchable made the recipe memory harder to find | [Experiment 2](../evaluation/memory-loop-experiment-2-2026-10-01.md) |
| 3. Sculptor chapter cues for book retrieval | In progress | [Below](#experiment-3-sculptor-chapter-cues-for-book-retrieval), [feasibility check](../evaluation/chapter-cue-feasibility-2026-10-01.md) |

The memory line stopped because its Scenario had little room to show a
benefit: the remaining gain depended on Sculptor choosing duplicate hiding
over summaries in one constructed case. Better book passages, by contrast,
improve the answers every reader gets about that book.

## Experiment 3: Sculptor chapter cues for book retrieval

Status: **Run on 2026-10-01. Practice: 17 and 17 of 20 at Stages 1 and 2, so
the stop rule ended the loop. Sealed: 14, 14, and 16 of 20 for today's search,
Stage 1, and Stage 2. The decision rule is not met.**

Sculptor improves the data the Librarian searches, measures whether book
retrieval improves, and uses the remaining failures to revise its work once
more:

- **Sculptor writes reading aids, not book text.** It revises each chapter's
  descriptive metadata: a short description, the characters, and retrieval
  cues. The book text, quotes, and citations never change, as
  [book registration](../book-registration.md) requires.
- **Retrieval reads the aids.** Each passage is searched together with its
  chapter's cues.
- **A human approves each rewrite.** Sculptor proposes, a human reviews the
  diff, and application code activates it.
- **Failures drive the next rewrite.** After each stage, Sculptor sees which
  practice needs still fail and why. Sealed needs stay unseen until every
  stage is frozen.

The method is document expansion. [Doc2query](https://arxiv.org/abs/1904.08375)
(Nogueira et al., 2019) adds generated text to passages to improve retrieval,
and [LongMemEval](https://arxiv.org/abs/2410.10813) reports that
fact-augmented memory keys raise recall@k by about 9%. Neither paper predicts
Linger's gain, and neither covers a repeated loop. Why chapter cues rather
than passage cards, a glossary, or assessment cards is in the
[feasibility check](../evaluation/chapter-cue-feasibility-2026-10-01.md#alternatives).

### Evaluation set

Both sets are frozen in `evals/librarian/chapter_cue_needs.json`, with author,
visibility to Sculptor, and label status.

- **Practice:** the 20 needs written for the feasibility check. Sculptor may
  see their outcomes. The hand-revised probe cues are discarded and never
  reach Sculptor.
- **Sealed:** 20 needs written by gpt-6-astra at max reasoning effort in a
  fresh read-only session limited to the chapter files, given only the
  practice passages to avoid. Every quote matches the book exactly once, the
  needs span 20 chapters, and none lies within about 1,500 characters of a
  practice passage. Sculptor never sees them.
- **Flagged for review:** sealed need s11 (chapter 21) comes from the same
  episode as practice need n11 (chapter 22).

Twenty sealed needs should hold about 4 misses at Stage 1, an estimate from
the practice baseline, enough room for the
decision rule. They support a transparent case study with paired wins and
losses, not a precise general improvement rate. Labels are accepted without
prior human review by owner decision, which departs from the usual rule that
Ground truth is adopted before graded runs.

### Measure

The primary measure is the share of needs whose passage, identified by its
quote, reaches the Librarian's assessment pool under production limits: three
passages per planned part, two per context query, up to 20 per book
(`src/linger/orchestration/book_evidence.py`). Request plans are frozen, so
the cues are the only change. Selected evidence and reader replies are checked
separately, because retrieval alone does not show that the reader benefits.

### Reading aid

| Decision | Plan |
|---|---|
| Aid | Revised chapter `routing_description`, `characters`, and `retrieval_cues`, within a fixed word budget per chapter. |
| Storage | The existing reviewed chapter metadata, which book registration already lets Sculptor propose. No new file type. |
| Retrieval | Each passage's keyword text, embedding text, and reranker input include its chapter's cues, placed after the passage. Excerpts and citations stay canonical. |
| Activation | A human approves the metadata diff. The corpus validator checks it, and the cue digest joins the index cache key. Production reads cues only after the sealed run passes, part recall with cues stays 32 of 32, no sealed need that today's search reaches is lost, and the owner approves; until then the experiment opts in with `read_chapter_cues=True`. |
| Scope | Cues describe only their own chapter, which reading permissions already bound. |

Search reads a separate `Candidate.search_text`, while `Candidate.text`
remains the quoted excerpt (`apps/backend/hybrid_librarian.py`). Wiring in the
existing cues is Stage 1, so the self-improvement claim rests only on
Sculptor's rewrites beyond it.

### The loop

1. **Stage 1: baseline.** Existing cues wired in. Record each practice miss,
   the chapter search chose, and the passages that outranked the required one.
2. **Stage 2: Sculptor's first rewrite.** Sculptor revises cues for every
   chapter, a human approves them, and the practice needs run again.
3. **Stage 3: Sculptor's second rewrite.** Sculptor receives the Stage 2
   outcomes and its own Stage 2 cues, names the remaining failure patterns,
   and revises the cues. A human approves, and the practice needs run again.

The word budget stays fixed, and every chapter is revised, not only chapters
behind practice answers. The loop stops after Stage 3, or earlier when a stage
brings no net practice gain or loses a need found at Stage 1. Then the sealed
needs run once against today's search (for reference) and each stage.

**Expectations.** Sealed needs that miss at Stage 1 because search picks the
wrong chapter should improve. Needs found at Stage 1 must hold. Within-chapter
misses are reported, since chapter cues cannot fix them.

### Decision rule

| Parameter | Value |
|---|---|
| Sealed gain | Stage 3 reaches at least 3 more of the 20 sealed needs than Stage 1, and no need found at Stage 1 is lost. |
| Recursion | Stage 3 reaches at least 1 more sealed need than Stage 2, with no offsetting loss. |
| Reader benefit | Paired reader replies show at least 2 improved, correctly sourced answers. |
| Integrity | Quotes and citations stay canonical, and the reading-scope test passes. |

If only Stage 2 helps, the benefit of the second, recursive rewrite is
unproven. A pass supports a bounded claim: a supervised loop improved
retrieval data and reader answers on one book and one frozen evaluation set.

### Plan

| Period | Deliverable |
|---|---|
| 1 October, **done** | Feasibility check passed; chapter cues chosen; both question sets written and frozen. |
| 2–7 October | Stage 1 wiring, the reading-scope test, frozen request plans, and Stage 1 practice score (**done** 1 October); the chapter-cue skill and the approval step. |
| 8–14 October | Stages 2 and 3 on practice feedback. Record proposals, approvals, revisions, scores, and cost. |
| 15–21 October | Sealed run against every frozen stage, paired reader replies, then the owner's review. Activate the approved cues if the rule passes. 22 October is buffer. |

### Risks

- **Gains may vanish after assessment.** Paired replies check what the pool
  measure cannot.
- **Cues may overfit known answers.** Every chapter is revised, the word
  budget is fixed, and the sealed set stays unseen.
- **Cues may invent facts or reveal later chapters.** Each cue must be
  supported by its own chapter, and reading permissions bound which chapters
  are searched. One exception is declared: a widely used alternate name for a
  character in the chapter. Factual errors in an approved proposal are
  recorded as findings and corrected before any activation.
- **Longer cues may explain a gain.** Stage 1 cues average 34 words per
  chapter. If a stage's cues are longer, the design cannot separate the
  effect of feedback from the effect of more cue text without a matched
  control, so each stage reports its mean cue length.
- **The expected gain is close to noise.** Planning varied by one need between
  runs, so comparisons use frozen plans.

### Cross-agent impact

- **Muse:** different passages can change answers. Check
  `tests/test_muse_source_boundary_checks.py` and paired replies.
- **Librarian:** ranking, scope, and caching change directly. Check
  `tests/test_hybrid_librarian.py`, part recall, and new cue and cache tests.
- **Serendipity:** connection discovery receives different evidence. Check
  `tests/test_serendipity_source_gathering.py`.
- **Provenance:** reviews different canonical passages. Check
  `tests/test_provenance_quote_checks.py` and attribution in paired replies.
- **Sculptor:** gains an offline chapter-cue skill. Extend
  `tests/test_sculptor_runtime_skills.py` and rerun memory-curation cases.

Until activation, search reads chapter cues only in the experiment, so no
agent's production behavior changes. Activation must run
`uv run python -m evals.librarian.part_recall --read-chapter-cues` against the
approved metadata and keep all 32 required passages, must not lose a sealed
need that today's search reaches, and must rerun the checks above. The
decision rule compares stages with each other, so these conditions guard what
production already finds.

Astra reviewed the plan on 2026-10-01 and shaped the measure, the set sizes,
and the decision rule.
