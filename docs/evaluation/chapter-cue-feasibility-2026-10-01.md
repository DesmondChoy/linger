# Chapter-Cue Feasibility Check

Back to [Self-Improving Memory Loop](../design/self-improving-memory-loop.md#experiment-3-sculptor-chapter-cues-for-book-retrieval).

Evidence behind Experiment 3's design, gathered on 2026-10-01: existing book
retrieval headroom, the alternatives Sculptor could curate, and the half-day
feasibility check that chose chapter cues.

## Headroom

Existing book evaluations do not yet show room to improve retrieval:

| Evaluation | Result | What it shows |
|---|---|---|
| Librarian benchmark, Alice | Recall 0.917, candidate precision 0.826; 12 cases, of which 10 are answerable | Only one case misses. The report predates the current 13-case set and stricter scorer, so it needs refreshing. |
| Five-agent Scenario, stage recall | Retrieved 0.97, assessed 0.85, cited 0.53 | Most losses happen after retrieval, where better indexing may not help. |
| Part recall, 19 captured plans | 32 of 32 required passages reach assessment | Good regression coverage, no headroom. |

The 0.826 is precision of retrieved candidates, while the 0.95 target applies
to final citations, so the gap between them is not a reader-visible defect.

Experiment 3 therefore needs new reader needs and a measure on the production
path. Production keeps three passages per planned part and two per context
query, up to 20 per book, before the Librarian selects at most five
(`src/linger/orchestration/book_evidence.py`). The older benchmark scores a
different path.

## Alternatives

Passage query cards are one of several things Sculptor could curate. Each
alternative fixes a different kind of miss, and none can be chosen until the
misses are known.

| Alternative | Fixes | Cost | Notes |
|---|---|---|---|
| **A. Passage query cards** in the keyword index | The required passage is in the right chapter but outranked, because the reader's wording differs from the book's | Highest: new skill, new storage, separate indexing text | Deferred after the feasibility check |
| **B. Chapter retrieval cues** added to the keyword text of each passage in the chapter | Search picks the wrong chapter | Low: every chapter already has reviewed `retrieval_cues`, `characters`, and `routing_description` that search does not read, and book registration already lets Sculptor propose this metadata | **Chosen** after the feasibility check; weak within a chapter |
| **C. Book glossary** that expands the query with the book's own terms, such as "shrinking" to "grew smaller" | Wording mismatch across the whole book | Lowest: one small file per book, no index change | Can drift every query; needs a protected-case check |
| **D. Assessment cards** shown to the Librarian when it judges passages | Passages retrieved but rejected at assessment, the documented 0.85 loss | Medium | Not a retrieval change; the five-agent note's option 1 |

Speaker tags were also considered. They help attribution, not retrieval.

The half-day check settled the choice. Each practice miss was classified as
one of four types: wrong chapter, outranked within the right chapter,
retrieved but rejected at assessment, or not fixable by curation. Hand-written
probes then tried the cheapest alternative that matched each type. The first
draft of the design assumed A; the check chose B.

## Feasibility check (2026-10-01)

**Setup.** Twenty practice reader needs about *The Adventures of Pinocchio*
(36 chapters, about 43,000 words), each labelled with one short exact quote
from the passage that answers it. The needs and quotes were written by the
agent, not independently, and are not adopted Ground truth. Four use names from
the Disney film rather than the book: Stromboli, whale, Pleasure Island, and
Candlewick. Each need went through production Librarian request planning once;
the plans were then frozen so every condition searched the same queries. A
need counts as reached when a passage containing its quote is in the
assessment pool under production limits. Scripts and outputs are in the
session scratchpad, not the repository.

**Baseline.** A first end-to-end pass through planning, gathering, and
Librarian assessment reached and selected 15 of 20. Every need that reached
assessment was selected, so no loss came from assessment. Of the 5 misses, 4
searched the wrong chapter and 1 was outranked within the right chapter. With
frozen plans, the pool baseline was 14 of 20; one need changed between the
two planning runs, which sets run-to-run noise at about one need.

**Probes.** Each condition changes only what search reads. Quotes and
citations stay canonical.

| Condition | Reached | Misses |
|---|---|---|
| Production baseline | 14/20 | n01, n07, n08, n09, n11, n18 |
| C. Glossary query expansion | 15/20 | n01, n08, n09, n11, n18 |
| B0. Existing chapter cues, keyword index only | 16/20 | n07, n08, n09, n11 |
| B1. Hand-revised chapter cues, keyword index only | 17/20 | n01, n08, n11 |
| B0. Existing chapter cues, keyword, embedding, and reranker input | 16/20 | n07, n08, n09, n11 |
| **B1. Hand-revised chapter cues, keyword, embedding, and reranker input** | **19/20** | n11 |

No condition lost a need that the baseline reached.

**Findings.**

- **Gate passed.** Six misses were plausibly fixable, and hand-written cues
  rescued five.
- **Wiring in the existing cues helps a little.** Every chapter already
  carries reviewed `routing_description`, `characters`, and `retrieval_cues`,
  which search does not read. Reading them rescues two needs with no new
  writing.
- **Cue content matters more.** Revised cues reach 19 of 20 against 16 for
  the existing ones. That gap is what Sculptor would curate. One existing cue
  even points the wrong way: chapter 12 lists "money tree", which belongs to
  the coin-burying scene in chapter 18.
- **Cues must reach every search stage.** Added to the keyword index alone,
  revised cues reach 17; the reranker, which reads canonical text, overrides
  them. Added to the embedding and reranker input as well, they reach 19.
- **Chapter cues cannot fix a within-chapter miss.** The guard-dog need (n11)
  finds chapter 22 but not the passage. Passage cards (option A) would be
  needed; they are deferred.
- **The probe cues were written knowing the needs.** They show the mechanism
  can work, not that Sculptor will find the right cues. The sealed set
  tests that.

