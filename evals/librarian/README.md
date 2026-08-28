# Librarian retrieval benchmark

This versioned benchmark compares the five required spoiler-bounded retrieval
configurations on the same Alice query set. Direct canonical reads are the
control. BM25S supplies lexical retrieval; FastEmbed supplies local dense
embeddings and the optional cross-encoder reranker.

The frozen benchmark and provider-backed release report evaluate the second
phase with a known chapter ceiling. The request-scoped full-work inference
phase is covered by deterministic and integration tests, but it does not yet
have adopted typed Ground truth or a provider-backed live scorecard. That
evaluation contract remains tracked by `linger-kow`.

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

- `--output <path>` for the JSON report;
- `--repetitions <count>` for warm-query measurement repeats;
- `--target-words <count>` for derived paragraph-window size; and
- `--overlap-words <count>` for adjacent-window overlap.

The generated `report.json` records every model and threshold, per-case evidence
IDs, safety and citation gates, evidence recall, citation precision,
evidence-strength support accuracy, p95 latency, evidence-token volume, local
model-token use, incremental monetary cost, and the predeclared selection rule.

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
the metadata-only JSON report location. The default report is
`evals/librarian/live-report.json`.

The report excludes prompts, replies, evidence text, and credentials. It records
case outcomes, release metrics, latency, and any provider usage the SDK exposes.

Indexes and model caches are derived artifacts. Canonical chapter Markdown
remains the source of truth, and the query boundary filters eligible windows
before BM25 scoring, semantic similarity, fusion, or reranking.
