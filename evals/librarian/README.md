# Librarian retrieval benchmark

This versioned benchmark compares the five required spoiler-bounded retrieval
configurations on the same Alice query set. Direct canonical reads are the
control. BM25S supplies lexical retrieval; FastEmbed supplies local dense
embeddings and the optional cross-encoder reranker.

Run it with:

```bash
uv run python -m evals.librarian.benchmark
```

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

Indexes and model caches are derived artifacts. Canonical chapter Markdown
remains the source of truth, and the query boundary filters eligible windows
before BM25 scoring, semantic similarity, fusion, or reranking.
