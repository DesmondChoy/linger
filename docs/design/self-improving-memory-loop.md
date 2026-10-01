# Self-Improving Memory Loop

Status: **Experiment 3 in progress: feasibility check passed and both question
sets frozen; Stage 1 is next. The memory-curation Experiments 1 and 2 are
superseded. Start at [Where things stand](#where-things-stand-2026-10-01).**

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

### Done

| Item | Where |
|---|---|
| Experiments 1 and 2 (superseded). Experiment 1's runner stays; Experiment 2's runner was removed and is recoverable from commit `3926c86` | [Experiment 1](../evaluation/memory-loop-experiment-1-2026-10-01.md), [Experiment 2](../evaluation/memory-loop-experiment-2-2026-10-01.md) |
| Feasibility check; probe scripts were in a session scratchpad and are not kept | [Chapter-cue feasibility](../evaluation/chapter-cue-feasibility-2026-10-01.md) |
| Frozen practice and sealed needs | `evals/librarian/chapter_cue_needs.json` |

All of the above is committed on `main` (`3926c86` to the Experiment 2 removal
commit), not pushed.

### Beads

- Epic `linger-g3rw`: Experiment 3. `linger-g3rw.1` sealed set is **closed**;
  `linger-g3rw.2` Stage 1 is **next**; `linger-g3rw.3` is the Sculptor
  chapter-cue skill and the Stage 2 and 3 runner.
- Experiment 2 follow-ups: `linger-p9iw` (derived summaries competing in
  memory search), `linger-4uix` (Cyrillic in a topic label), `linger-9j42`
  (capture time turned into an event date).

### Next steps

1. **Stage 1 (`linger-g3rw.2`, about a day).** In
   `apps/backend/hybrid_librarian.py`, give each candidate a search text
   (passage plus its chapter's `routing_description`, `characters`, and
   `retrieval_cues`) separate from the canonical excerpt. Use it for the
   keyword index, embeddings, and reranker input; keep excerpts and citations
   canonical. Add the tag digest to the index cache key, and a test that no
   passage beyond the reader's chapter is returned. Run
   `tests/test_hybrid_librarian.py` and `uv run python -m evals.librarian.part_recall`.
2. **Freeze request plans** for every practice and sealed need with one
   production Librarian planning pass, stored beside
   `evals/librarian/chapter_cue_needs.json`.
3. **Score Stage 1 on the practice set** with a small runner that records, per
   need, whether a passage containing its quote reaches the assessment pool.
   Do not run the sealed set yet.
4. **Sculptor chapter-cue skill (`linger-g3rw.3`).** One typed skill on
   Sculptor's existing Agent. Input: the book's chapters, their current tags,
   and the practice failures. Output: revised tags for every chapter within a
   fixed word budget. Add the owner approval step.
5. **Stages 2 and 3 on practice needs**, then run the sealed set once against
   today's search and each stage. Check paired reader replies and apply the
   [decision rule](#decision-rule).

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

Status: **feasibility check passed and question sets frozen on 2026-10-01;
stages not built.**

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

Twenty sealed needs hold about 4 misses at Stage 1, enough room for the
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
| Retrieval | Each passage's keyword text, embedding text, and reranker input include its chapter's cues. Excerpts and citations stay canonical. |
| Activation | A human approves the metadata diff. The corpus validator checks it, and the cue digest joins the index cache key. |
| Scope | Cues describe only their own chapter, which reading permissions already bound. |

Search needs a separate search text beside the canonical excerpt, because
`Candidate.text` currently feeds indexing, embeddings, reranking, and quoted
excerpts (`apps/backend/hybrid_librarian.py`). Wiring in the existing cues is
an ordinary improvement every reader gets on its own. It becomes Stage 1, so
the self-improvement claim rests only on Sculptor's rewrites beyond it.

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
| 2–7 October | Stage 1 wiring, frozen request plans, Stage 1 practice score, the chapter-cue skill, the approval step, and the reading-scope test. |
| 8–14 October | Stages 2 and 3 on practice feedback. Record proposals, approvals, revisions, scores, and cost. |
| 15–21 October | Sealed run against every frozen stage, paired reader replies, then the owner's review. Activate the approved cues if the rule passes. 22 October is buffer. |

### Risks

- **Gains may vanish after assessment.** Paired replies check what the pool
  measure cannot.
- **Cues may overfit known answers.** Every chapter is revised, the word
  budget is fixed, and the sealed set stays unseen.
- **Cues may invent facts or reveal later chapters.** Each cue must be
  supported by its own chapter, and reading permissions bound which chapters
  are searched.
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

Astra reviewed the plan on 2026-10-01 and shaped the measure, the set sizes,
and the decision rule.
