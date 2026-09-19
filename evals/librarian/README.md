# Librarian retrieval benchmark

This versioned benchmark compares the five required spoiler-bounded retrieval
configurations on the same Alice query set. Direct canonical reads are the
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
