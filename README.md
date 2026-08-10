# Linger

An academic prototype of a provenance-first reflection and memory companion.

## Selected implementation direction

Linger uses Python 3.12, Pydantic AI for the five reasoning agents, and FastAPI for the application API and deterministic orchestration. Pydantic Logfire is the OpenTelemetry-compatible telemetry backend. Application code—not an agent—retains authority over account scope, memory writes, deterministic validation, and release of user-visible output.

## First corpus milestone

The first end-to-end corpus contains one book: Lewis Carroll's *Alice's Adventures in Wonderland* (Project Gutenberg ebook 11). Its checked-in text, download metadata, and content-versioned corpus definition are `data/gutenberg/alice-in-wonderland.txt`, `data/gutenberg/alice-in-wonderland.metadata.json`, and `data/gutenberg/corpus_manifest-76bc215970bb.json`. After the one-book ingestion, retrieval, spoiler-filtering, citation, and evaluation path works end to end, the corpus expands to the planned total of 3–5 books.

## Project Gutenberg notebook

[`notebooks/project_gutenberg_query_workflow.ipynb`](notebooks/project_gutenberg_query_workflow.ipynb) guides a three-stage selection workflow for an exclusively English, public-domain Project Gutenberg corpus: search the catalogue, shortlist and profile candidates with configurable word-count limits, then record a content-versioned manifest. Alice is the first one-book integration milestone; the workflow supports the later 3–5-book corpus.

From the repository root, install the locked dependencies and launch JupyterLab:

```bash
uv sync --dev
uv run jupyter lab
```

Then open the notebook and run its cells from top to bottom.

## Proposed repository layout

Each agent owns its prompts and reasoning logic, while orchestration, typed hand-offs, and deterministic services remain shared.

```text
linger/
├── apps/                           # Refer to the README here to run the app
│   ├── backend/                    # Backend entry point
│   └── frontend/                   # User interface
├── src/linger/
│   ├── agents/
│   │   ├── muse/
│   │   ├── librarian/
│   │   ├── sculptor/
│   │   ├── serendipity/
│   │   └── provenance/
│   │       # Each agent: agent.py, prompts/, tests/, README.md
│   ├── orchestration/
│   │   ├── workflow.py         # Reflection, capture, and connection flows
│   │   └── state.py            # Shared workflow state
│   ├── contracts/
│   │   └── models.py           # Typed agent hand-offs
│   └── services/
│       ├── memory_policy/      # Scoped reads, writes, and deletion
│       ├── retrieval/          # Corpus and memory retrieval
│       └── citation/           # Deterministic quotation checks
├── data/                       # Corpus, manifests, and fixtures
├── evals/                      # Fixed evaluation cases and scorers
├── tests/                      # Integration, security, and end-to-end tests
├── docs/                       # Architecture, reports, and risk register
└── deploy/                     # Containers and deployment configuration
```
