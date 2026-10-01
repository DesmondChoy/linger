# Memory Loop Experiment 2

Back to [Self-Improving Memory Loop](../design/self-improving-memory-loop.md). Previous:
[Memory loop design and Experiment 1](memory-loop-experiment-1-2026-10-01.md).

The offline Sculptor-only search loop: pre-registration, result, and an
independent review. Superseded on 2026-10-01 by Experiment 3 in the design
document.

## Design

Status: **run on 2026-10-01; not positive; superseded.**

The follow-up runs the same Scenario as a strictly offline loop in which
Sculptor is the only agent. The runner, `evals/synthetic_journals/offline_search_loop.py`,
its tests, and the pre-registration were committed in `3926c86` and removed
after the experiment was superseded; restore them from that commit to rerun.

- **Curation without Provenance.** Each round applies Sculptor's proposal
  directly, with no curation review. This is an ablation: production never
  applies unreviewed curation, so the artifact is labelled
  `curation_review: "ablated"` and must not be read as production behaviour.
- **Recall without agents.** No turn triage, Muse, Serendipity, or release
  review. Each frozen query runs through production memory search
  (the same scoring as `search_memories`) over the curated
  retrieval view.
- **Repetitions.** Search is a fixed function of the query and the retrieval
  view, so repetitions sample only Sculptor's choices.

This isolates the question curation can answer: does it make the right memory
easier to find? Whether replies improve, and whether summaries are presented
honestly, remain separate end-to-end checks.

### Queries

The Line alone is the wrong query. Search scores records by shared words, and
a whole Line shares many common words with most memories. With each Line as
the query, raw search already ranks the relevant memory first for the night,
recipe, and nut-allergy Scenes, which leaves curation nothing to improve.
Experiment 1's misses came from the shorter queries Serendipity wrote.

Each Scene's query set is therefore its Line followed by every distinct query
Serendipity sent to `search_memories` for that Scene in Experiment 1: 13 to 17
queries per Scene. Using several real phrasings of one need follows the query
variation approach of [UQV100](https://www.microsoft.com/en-us/research/publication/uqv100-a-test-collection-with-query-variability/)
(Bailey, Moffat, Scholer and Thomas, SIGIR 2016). The set was frozen in
`offline-search-preregistration.json` in the Scenario directory (commit `3926c86`). Sculptor
never sees it.

### Measure

The measure is Recall@5, which is the retrieval measure
[LongMemEval](https://arxiv.org/abs/2410.10813) reports for memory systems.
For one query, it is the mean over relevant Props of the chance that one of
the top five results stands for that Prop: the Prop itself, its retrievable
copy if hidden, or a derived summary of either. A topic group does not count,
because its searchable text is only a label.

Search breaks score ties by memory ID, which is arbitrary per run, and most
scores here are ties. Recall is therefore averaged over every tie order, the
method of [McSherry and Najork](https://link.springer.com/chapter/10.1007/978-3-540-78646-7_38)
(ECIR 2008). This replaces rank, which ties leave undefined.

Raw recall, measured before any treatment arm, is:

| Scene | Queries | Raw Recall@5 | Role |
|---|---|---|---|
| Which night now, and before | 13 | 1.00 | hold |
| Tried several new recipes before | 17 | 0.26 | improve |
| What helped with nerves | 17 | 0.04 | report |
| Nut allergy | 13 | 0.97 | hold |
| Charging guests | 13 | none relevant | report |

### Expectations per Scene

Each Scene declares in advance what curation should do to it, so the result
cannot be read selectively afterwards.

- **Improve.** The recipe Scene is the only one where curation can plausibly
  help. Three copies of the seating reflection share "supper club", "new", and
  "menu" with the recipe queries and fill the top five. Hiding copies or
  summarising them frees those places.
- **Hold.** The night and nut-allergy Scenes are already found. Curation must
  not make them harder to find, for example by hiding an original behind a
  summary that shares fewer words with the query.
- **Report.** The nerves memory shares almost no words with any query, and
  curation cannot add words to an original, so no change is expected. Whether
  the ablation was needed is visible in the logs, not graded. The charging
  Scene has no relevant memory, and declining is a reply decision that search
  does not measure.

### Pre-registered decision rule

| Parameter | Value | Basis |
|---|---|---|
| Unit of analysis | Query, nested in Scene | Paired per-query comparison, as in IR significance testing |
| Primary test | Exact one-sided paired sign-flip randomization test, raw against three rounds, recipe Scene | [Smucker, Allan and Carterette](https://www.semanticscholar.org/paper/A-comparison-of-statistical-significance-tests-for-Smucker-Allan/3bf42fdbe24fe5aaa491266006d89bae53e99552) (CIKM 2007) recommend randomization over sign and Wilcoxon tests |
| Alpha | 0.05 | Conventional |
| Replication | Passes in at least 2 of 3 Sculptor repetitions | Repetitions sample the curation, not the queries, so each is tested separately rather than pooled; see [Miller](https://arxiv.org/abs/2411.00640) (2024) on clustered samples |
| Hold margin | Mean recall never more than 0.10 below raw, after any round, in every repetition | Non-inferiority margin, per [Lakens, Scheel and Isager](https://journals.sagepub.com/doi/10.1177/2515245918770963) (2018); its size is a practical choice and permits some harm |
| Result | Positive only if the improve Scene and both hold Scenes pass | |

The test treats the 17 phrasings of one need as exchangeable, which is not
established, so its p-value is a fixed-Scenario diagnostic rather than
evidence about other needs. A significant result also does not guarantee a
meaningful one: five small gains and no losses already give p = 0.031.

Writing the rule down before running follows
[Nosek et al.](https://www.pnas.org/doi/10.1073/pnas.1708274114) (PNAS 2018).
Two departures should be disclosed with the result. The queries come from
Experiment 1, so they are not independent of the earlier run. Raw recall was
measured before the roles were set, which is pre-treatment information, but
Experiment 1's curation actions were also known.

A positive result would show only that unreviewed curation made one kind of
memory easier for lexical search to find in one constructed Scenario.

### Result (2026-10-01)

The user approved the rule above before the run. Run `c534fb98`, trace
`01a0f52920f44d4f7da180018375497a`, `openai:gpt-6-luna`, three repetitions of
three unreviewed rounds. **The result is not positive.** The recipe Scene
failed in all three repetitions; both hold Scenes passed.

| Repetition | Round 1 | Round 2 | Round 3 |
|---|---|---|---|
| 1 | Night summary | Seating notes topic group | Two seating copies linked |
| 2 | Night summary | Seating notes topic group | Three seating copies linked |
| 3 | Night summary | Two seating copies linked | One seating copy hidden |

Mean Recall@5:

| Scene | Role | Raw | 1 round | 2 rounds | 3 rounds | Verdict |
|---|---|---|---|---|---|---|
| Recipes | improve | 0.26 | 0.12 to 0.14 | 0.12 to 0.14 | 0.12, 0.14, 0.27 | fail (p = 1.0, 1.0, 0.5) |
| Night | hold | 1.00 | 1.00 | 1.00 | 1.00 | pass |
| Nut allergy | hold | 0.97 | 0.91 | 0.91 | 0.91, 0.91, 0.98 | pass |
| Nerves | report | 0.04 | 0.03 | 0.03 | 0.03 | reported |

**Curation made the recipe memory harder to find.** Every repetition's first
action was the night summary, which adds a record without hiding the two
originals. Search counts shared words, including common ones, and the long
summary shares "supper", "club", "the", "at", "on", and "to" with the recipe
queries. It lowers the recipe memory's chance of reaching the top five on five
of the 17 queries; removing only the summary restores raw recall. The
nut-allergy dip, from 0.97 to 0.91, has the same cause. It passed the hold
margin, but it is a real loss. Only repetition 3 hid a seating copy, and that only restored raw
recall.

Further observations, several from an independent review by gpt-6-astra:

- **Action choice, not budget, limited the result.** Hiding a copy takes a
  link and then a tombstone, so three rounds could have done it. Sculptor
  spent the first round on the night summary in every repetition. Hiding one
  exact seating duplicate would raise recipe recall from 0.26 to 0.53 with the
  current search. Hiding the paraphrased third copy as well would reach 0.85,
  but it is not an exact duplicate. These are counterfactual calculations,
  not observed outcomes.
- **The recall measure does not check what a summary says.** Repetition 2's
  night summary states the move happened "from June 16, 2026", a date taken
  from the capture time, which the Sculptor skill forbids treating as event
  time. Night recall still scored 1.0 because a summary is credited through
  its sources.
- **One topic label contained Cyrillic characters** ("menu новelties"). The
  review that might catch it was ablated.

What this means for the design: under word-count search, every derived record
competes with the originals for the same five places, so a summary that leaves
its sources retrievable can make other memories harder to find. Duplicate
hiding, which current search already rewards, is where curation can help
without changing retrieval.
