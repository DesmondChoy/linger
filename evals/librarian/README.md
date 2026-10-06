# Librarian retrieval evaluations

This directory contains the Alice retrieval benchmark, production release
validation, multi-book part recall, and offline chapter-cue and retrieval
research experiments. The versioned Alice benchmark compares five
spoiler-bounded retrieval configurations. Direct canonical reads are the
control. BM25S supplies lexical retrieval; FastEmbed supplies local dense
embeddings and the optional cross-encoder reranker.

Librarian owns one reusable Agent with four application-selected skills:
[book request planning](../../src/linger/agents/librarian/skills/book-request/SKILL.md),
[boundary inference](../../src/linger/agents/librarian/skills/boundary-inference/SKILL.md),
[independent event identification](../../src/linger/agents/librarian/skills/event-identification/SKILL.md), and [evidence assessment](../../src/linger/agents/librarian/skills/evidence-assessment/SKILL.md).
All have typed inputs and per-run outputs and expose no model tools. Retrieval,
scope filtering, fusion, and reranking remain application code. The retrieval
benchmark exercises a known boundary; production routing and book replay can
also invoke the boundary-inference skill. A role model override covers all
tasks while skill IDs and fingerprints keep their results distinguishable.

The frozen benchmark and provider-backed release report evaluate retrieval
with a known chapter ceiling. The separate
[synthetic book replay](../synthetic_journals/README.md#grounded-reflection-and-spoiler-boundary-replay)
evaluates production book routing, full-work boundary inference, clarification,
grounding, and release against typed proposed or independently adopted Ground
truth. Its chapter-scoped grades do not cover runtime passage grants. Each
report's scenario, adoption, model, and prompt identity determine its evidence
scope.

The `identity-theme` case expects sufficient evidence for a **qualified literary
interpretation**. Either Chapter 5 lines 979–981 (changing sizes confuse Alice)
or lines 1026–1027 (her changing memory and size) satisfies its required
dialogue anchor. Both together count as one required fact. Chapter 4 lines
762–766 and Chapter 2 lines 330–333 or 337–341 remain optional support; neither alone
replaces the dialogue. An unrelated Chapter 5 passage also does not qualify. The query
and Chapter 5 ceiling are unchanged. These retrieval labels do not establish
that uncertain identity causes physical growth: manual semantic review must
still distinguish a supported thematic relationship from an unsupported
reciprocal causal claim.

Required evidence uses `required_range_groups`: every group must be satisfied,
and any one listed range can satisfy a group. A returned passage must contain
the full required source-line range in the same chapter. Partial overlap does
not satisfy that range. Cases without explicit groups
require every relevant range separately. The benchmark, manual notebook,
direct evaluation and release validation share this recall calculation.
Precision counts returned passages containing at least one complete span
from `relevant_ranges`, including optional support.

The `pigeon-serpent` case requires both the unusual neck and the belief that
Alice eats eggs. One passage can support both facts, or separate passages can
support each. The `drink-me-mechanism` case expects `weak` evidence. Chapter 1
lines 191–192 establish the bottle's label, but the text gives no chemical
reaction that explains shrinking. Retrieving all available supporting spans
can earn full recall while the model must still acknowledge missing support
for part of the question.

Historical reports retain their original grades. Earlier reports used partial
overlap and a strength proxy derived from the expected label. Their scores are
not directly comparable with results from the current scorer.

## Manual notebook

[`../../notebooks/librarian_manual_evaluation.ipynb`](../../notebooks/librarian_manual_evaluation.ipynb)
provides an editable, beginner-friendly, step-by-step path for developers who
want to:

1. Run the production Librarian end to end on one query and reading boundary.
2. Inspect the clarification, failure, or result contract.
3. Follow one frozen case through boundary filtering, BM25, semantic search,
   fusion, deduplication, reranking, candidate measurement, and the final
   evidence-strength decision.
4. Compare all five retrieval configurations for that case.
5. Optionally evaluate the Librarian across the complete frozen case set.

The notebook presents the end-to-end manual run and the internal step-by-step
walkthrough as two independent routes after one shared setup; neither route is
a prerequisite for the other.

From the repository root:

```bash
uv run jupyter lab notebooks/librarian_manual_evaluation.ipynb
```

Run the cells from top to bottom. Full Librarian cells use `LINGER_MODEL` and
the matching API key from `.env`. The first local retrieval run may download
the embedding and reranking models. The notebook keeps results in memory and
does not overwrite either checked-in report.

## Reproducible aggregate benchmark

Run it with:

```bash
uv run python -m evals.librarian.benchmark
```

The benchmark options are:

- `--output <path>` selects the JSON report, defaulting to
  `evals/librarian/report.json`.
- `--repetitions <count>` sets warm-query measurement repeats, defaulting to 3.
- `--target-words <count>` sets the derived paragraph-window size, defaulting
  to 350 words.
- `--overlap-words <count>` sets adjacent-window overlap, defaulting to 60 words.

The generated `report.json` records every model and threshold, per-case evidence
IDs, safety and citation gates, evidence recall, citation precision,
p95 latency, evidence-token volume, local model-token use, incremental monetary
cost, and the predeclared selection rule. `quality_score` weights evidence
recall and citation precision 2:1: `(2 * recall + precision) / 3`. The live
validator measures the model's evidence-strength decisions separately.

The retrieval-only precision value describes the candidate passages sent to the
Librarian's set-level evidence judge. It is intentionally reported separately
from the project's final user-visible citation target: the judge may retain only
the candidate evidence IDs that actually support an answer. End-to-end
validation measures that final projection without relabelling candidate quality
as final citation quality.

## Live release validation

Run the provider-backed Librarian-to-Muse release path with:

```bash
uv run python -m evals.librarian.live_validation
```

The command uses the selected hybrid retriever, configured model, Muse,
Provenance, and deterministic release validation. `--case <id>` is repeatable,
`--limit <count>` runs the first bounded subset, and `--report <path>` chooses
the synthetic evaluation JSON report location. The default report is
`evals/librarian/live-report.json`.

The report retains synthetic replies and agent exchanges for investigation,
alongside case outcomes, release metrics, latency, and complete provider usage
when the SDK exposes it for every nested agent call. It contains no credentials.

Indexes and model caches are derived artifacts. Canonical chapter or section
Markdown remains the source of truth, and the query boundary filters eligible
windows before BM25 scoring, semantic similarity, fusion, or reranking.

## Multi-book part recall

Run frozen request plans through local candidate gathering:

```bash
uv run python -m evals.librarian.part_recall
```

The command measures whether every required book passage, including accepted
evidence alternatives, reaches the evidence-assessment pool. It prints recall,
pool size, character count, and missing evidence IDs per case. It makes no
provider calls and does not measure Librarian's final selection or the reply.
Local embedding and reranking models must be available.

| Option | Meaning |
| --- | --- |
| `--cases PATH` | Frozen plans and scenario reference; defaults to `evals/librarian/part_recall_cases.json`. |
| `--read-chapter-cues` | Includes chapter metadata in search text. The default searches passage text only. |
| `--part-candidates N` | Retains this many windows per planned part before the per-book merge. Defaults to the production value of 4. |

For the Experiment 4 retention setting, use:

```bash
uv run python -m evals.librarian.part_recall \
	--read-chapter-cues --part-candidates 20
```

The per-book pool remains capped at twenty records. Neither option changes
production configuration.

## Chapter-cue and retrieval-research experiments

`chapter_cue_recall` evaluates Pinocchio retrieval against frozen reader needs
and `BookRequestPlan` values. `score` measures whether a passage containing the
expected quote reaches the private pool. `select` asks the production Librarian
to choose at most five records, then checks whether a chosen record contains
that quote. These are separate outcomes. Neither establishes a complete chat
release result.

The command reference is:

| Command | Options and behavior |
| --- | --- |
| `freeze` | Calls the production planner once per practice and held-back need and writes `chapter_cue_plans.json`. Refuses an existing plan file. |
| `propose` | Required `--stage 2` or `--stage 3`. Calls Sculptor with chapter text, current cues, a sixty-word cue budget per chapter, and earlier practice outcomes. Writes JSON, a readable comparison, and every attempt. |
| `approve` | Required `--stage 2` or `--stage 3`. Records the owner's approval against the exact proposal hash. |
| `score` | Required `--search`; optional `--set practice` or `--set sealed`, defaulting to `practice`. Runs local retrieval without a provider call. |
| `select` | The same `--search` and `--set` options as `score`. Calls Librarian and records its selected evidence, failures, model usage, and pool size. |

The `--search` values are:

| Value | Search configuration |
| --- | --- |
| `today` | Passage text with production candidate retention. |
| `stage1` | Existing chapter cues with production candidate retention. |
| `stage2` or `stage3` | The corresponding owner-approved cue proposal, applied to a temporary corpus copy. |
| `round1` | Approved Stage 2 cues with twenty windows per planned part and the approved Round 1 research specification. |

For a condition whose prerequisites are present, score and select practice
evidence with:

```bash
uv run python -m evals.librarian.chapter_cue_recall score \
	--search round1 --set practice
uv run python -m evals.librarian.chapter_cue_recall select \
	--search round1 --set practice
```

The checked-in experiment artifacts are fixed observations. Selection refuses
an existing result, checkpoints completed needs, and resumes only when the
input identity and pool hashes match. Scoring refuses a pool that differs from
an existing selection. Identities bind the needs, plans, cue approvals,
retrieval implementation, candidate allowance, and any research specification.
Stale results cannot supply the next experiment step.

The first `score --set sealed` locks the needs, plans, and approved cue stages.
Each held-back condition is scored once. After the lock exists, cue proposals
and approvals are frozen. Stage 3 is available only if Stage 2 gains practice
recall without losing a Stage 1 success. Held-back needs never reach Sculptor.

Build practice traces from a scored and selected condition:

```bash
uv run python -m evals.librarian.chapter_cue_traces --search stage2
```

`--search` accepts the same five values. This local command writes
`chapter_cue_runs/<search>-practice-traces.json` with the question, expected
passage, chapter metadata, search ranks, pool, selected records, and failures.
It makes no provider call.

Experiment 4 uses those traces and
[`retrieval_description.md`](retrieval_description.md) for Sculptor's error
analysis and retrieval research. Each command requires `--round N`:

```bash
uv run python -m evals.librarian.research_loop analyse --round 1
```

After the owner reviews the analysis, record approval and run research:

```bash
uv run python -m evals.librarian.research_loop approve \
	--round 1 --step analysis
uv run python -m evals.librarian.research_loop research --round 1
```

After the owner reviews the specification, record its exact hash:

```bash
uv run python -m evals.librarian.research_loop approve \
	--round 1 --step specification
```

`analyse` and `research` use the configured model with high reasoning effort.
Research requires `EXA_API_KEY` and allows at most ten searches and ten page
opens, restricted to URLs found in the run. It returns a specification for a
developer to implement. The output grants no code-editing authority.
`research_runs/round-N/` retains JSON, readable reports, approvals, searches,
opened pages, retry requests, and failed attempts. Approved steps cannot be
rerun. Later rounds also require the earlier approved analyses, specifications,
and practice results.

See the [self-improving memory-loop design](../../docs/design/self-improving-memory-loop.md)
for experiment controls and interpretation. These commands do not enable
chapter cues or research retention settings in production.
