# Linger

An academic prototype of a **provenance-first reflection and memory companion**.

## At a glance

- **Runtime:** Python 3.12, FastAPI, and Pydantic AI
- **Reasoning:** five focused agents, with deterministic application control
- **Observability:** Pydantic Logfire (OpenTelemetry-compatible)
- **Corpus milestone:** *Alice's Adventures in Wonderland* from Project Gutenberg
- **Developer tooling:** corpus Reader and per-turn Inspect diagnostics
- **Synthetic evaluation:** validated packages, independent Ground truth review,
  and production-boundary capture and curation replay
- **Issue tracking:** [Beads](https://github.com/gastownhall/beads), backed by a local Dolt database

Linger keeps authority over account boundaries, memory writes, validation, and
user-visible output in application code—not in an agent.

## What the prototype does

- **Reflect:** sends each Line through a no-tool emotional-boundary preflight,
  Muse, optional specialists, Provenance, and deterministic release checks.
  Failed or rejected candidates produce application-owned responses.
- **Ground:** retrieves exact, spoiler-bounded book passages through Librarian.
  Evidence remains request-scoped and every released quotation must resolve to
  the canonical corpus.
- **Reconnect:** lets Serendipity explore bounded book evidence and, when
  explicitly configured, public web evidence through Exa. Private wording is
  blocked from web-search queries.
- **Capture:** supports reviewed automatic memory capture only through
  server-controlled evaluation policy. The interactive POC keeps capture
  disabled and exposes no memory-management actions.
- **Evaluate:** validates synthetic Backstory packages, records independent
  human adoption without rewriting generated files, and replays supported
  capture and bounded-curation Objectives through their production boundaries.

## Developer tools

The local development frontend mounts Reader and Inspect for developers working
with the corpus and backend workflow. They are debugging tools, not product
frontend surfaces; a user-facing app should omit both.

- **Reader** browses the public-domain Alice corpus by chapter and can reveal
  chapter summaries after an explicit spoiler warning. It helps developers
  exercise corpus behavior. Its local navigation never establishes reading
  progress, evidence authority, or a chat spoiler boundary.
- **Inspect** projects each completed turn's request contract, context
  resolution, specialist outcomes, Provenance release path, capture outcome,
  and server-generated Logfire trace ID. It helps developers trace backend
  hand-offs and decisions; its diagnostic data grants no runtime authority.

## Startup

### Prerequisites

- [Python](https://www.python.org/) 3.12 or later
- [uv](https://docs.astral.sh/uv/) for Python environments and locked dependencies
- [Node.js](https://nodejs.org/) 20.19+ or 22.12+ and [pnpm](https://pnpm.io/) for the frontend
- An API key for the model provider you choose: Google, OpenAI, or Anthropic

### Install the project libraries

From the repository root:

```bash
# Create local configuration and choose a model provider
cp -f .env.example .env

# Install Python application and development dependencies from uv.lock
uv sync --dev

# Install frontend dependencies
pnpm install --dir apps/frontend
```

Edit `.env` to set `LINGER_MODEL` and the matching API key. The checked-in
default is `openai:gpt-5.6-luna`; supported provider prefixes are `google`,
`openai`, and `anthropic`. Only the selected provider's key is needed.

- `google:gemini-2.5-flash` → `GOOGLE_API_KEY`
- `openai:gpt-5.6-luna` → `OPENAI_API_KEY`
- `anthropic:claude-sonnet-4-5` → `ANTHROPIC_API_KEY`

Optional public-web connection discovery requires both settings:

```dotenv
EXA_API_KEY=...
LINGER_WEB_SEARCH_ENABLED=true
```

`LINGER_ACCOUNT_ID` supplies the server-owned account for the single-user
prototype. `LINGER_ALLOWED_ORIGINS` accepts a comma-separated list of browser
origins and defaults to `http://localhost:5173`.

To send the backend's metadata-only telemetry to the Linger Logfire project:

```bash
uv run logfire --region us auth
uv run logfire --region us projects use --org desmond-choy linger
```

Use `LOGFIRE_TOKEN` instead in deployed or CI environments. The telemetry
allowlist and privacy constraints are defined in [`docs/telemetry.md`](docs/telemetry.md).

### Start the app

Run these commands in two terminals from the repository root:

```bash
# Terminal 1: API at http://127.0.0.1:8000
uv run uvicorn apps.backend.main:app --reload
```

```bash
# Terminal 2: UI at http://localhost:5173
pnpm --dir apps/frontend dev
```

Open <http://localhost:5173>. Interactive API documentation is available at
<http://127.0.0.1:8000/docs>.

The frontend can call a separately hosted API by setting `VITE_API_URL` before
starting or building it. Without that variable, Vite proxies `/api` to the
local backend.

### Get Beads working

For Beads setup and usage, ask your coding agent to consult the
[official Beads GitHub page](https://github.com/gastownhall/beads).

## Corpus

The first corpus contains one book: Lewis Carroll's *Alice's
Adventures in Wonderland* ([Project Gutenberg ebook 11](https://www.gutenberg.org/ebooks/11)).

- Immutable source: `data/gutenberg/alice-in-wonderland.txt`
- Immutable revision: `data/corpus/alice-in-wonderland/pg11-v01b38ea4/`
- Canonical chapters: `data/corpus/alice-in-wonderland/pg11-v01b38ea4/chapters/`
- Derived routing catalogue: `data/corpus/alice-in-wonderland/pg11-v01b38ea4/catalog.json`

The shared corpus lifecycle preserves chapter layout, adds compact JSON front
matter for routing, and validates every canonical artifact before publication.
Alice supplies a small Gutenberg-specific adapter for its wrapper, contents,
headings, and boundaries. Each future book supplies its own source-specific
adapter while reusing the same renderer, catalogue builder, and integrity
checks. BM25 paragraph windows, embeddings, and hybrid indexes may be generated
as derived artifacts; none is a source of truth or a publication requirement.

Verify the checked-in corpus or rebuild its derived catalogue with:

```bash
uv run python -m src.linger.corpus.book src.linger.corpus.alice check
uv run python -m src.linger.corpus.book src.linger.corpus.alice build-catalog
```

For a book-related request without explicit progress, the Librarian privately
searches the complete selected work using the current Line and relevant
account-scoped memories. It returns only a candidate chapter ceiling,
confidence, and content-free supporting locations. After application
validation—or after a focused reader clarification when confidence is too
low—the Librarian runs a separate BM25 and semantic search bounded to that
ceiling. Later chapters never enter the answer-evidence candidate set. The
eligible candidates are fused, reranked, resolved against the immutable corpus,
and returned to Muse as a typed evidence response.

## Librarian notebook

[`notebooks/librarian_manual_evaluation.ipynb`](notebooks/librarian_manual_evaluation.ipynb)
supports an editable end-to-end Librarian run and a step-by-step evaluation of
boundary filtering, keyword and semantic retrieval, fusion, reranking,
evidence strength, spoiler safety, and citation resolution.

Launch it from the repository root after installing development dependencies:

```bash
uv run jupyter lab notebooks/librarian_manual_evaluation.ipynb
```

Full Librarian cells use the model and matching API key configured in `.env`.

## Evaluation and validation

Run the complete automated suite and frontend gates from the repository root:

```bash
uv run pytest
pnpm --dir apps/frontend test
pnpm --dir apps/frontend lint
pnpm --dir apps/frontend build
```

The evaluation entry points are:

```bash
# Deterministic five-strategy Librarian benchmark
uv run python -m evals.librarian.benchmark

# Provider-backed Librarian release validation
uv run python -m evals.librarian.live_validation

# Provider-backed emotional-boundary classification
uv run python -m evals.provenance.emotional_boundary

# Validate a synthetic package
uv run python -m evals.synthetic_journals.validate_package \
  path/to/backstory.json path/to/ground-truth.json

# Review proposed Ground truth and write a hash-bound adoption after confirmation
uv run python \
  .agents/skills/review-synthetic-ground-truth/scripts/ground_truth_reviewer.py \
  path/to/backstory.json path/to/ground-truth.json \
  --reviewer-id REVIEWER_ID

# Replay a capture package through the production chat boundary
uv run python -m evals.synthetic_journals.replay \
  synthetic-journal-evaluation/packages/2026-08-23T182725+0800/backstory.json \
  synthetic-journal-evaluation/packages/2026-08-23T182725+0800/ground-truth.json \
  --output /tmp/reviewed-automatic-memory-capture-run.json

# Replay a bounded-curation package through production Sculptor
uv run python -m evals.synthetic_journals.curation_replay \
  synthetic-journal-evaluation/packages/2026-08-25T092910+0800/backstory.json \
  synthetic-journal-evaluation/packages/2026-08-25T092910+0800/ground-truth.json \
  --output /tmp/bounded-memory-curation-run.json
```

The Librarian benchmark accepts `--output`, `--repetitions`, `--target-words`,
and `--overlap-words`. Live Librarian validation accepts repeatable `--case`,
`--limit`, and `--report`; the Provenance evaluation accepts `--report`.
Synthetic package validation accepts `--run-configuration-directory`. The
Ground truth reviewer requires `--reviewer-id`; `--adoption` selects a sibling
output path, `--ui` selects a built UI directory, and `--timeout` sets the
loopback review lifetime in seconds. Both replay commands accept an optional
hash-validated `--adoption` and write JSON to stdout unless `--output` is
supplied.

Without `--adoption`, replay compares observed hard gates with proposed Ground
truth. A complete independent adoption changes the dataset identity and grades
the same gates as adopted Ground truth. Capture replay accepts only the
`reviewed_automatic_memory_capture` topology; curation replay accepts only
isolated `bounded_memory_curation` Scenes containing two to twelve active Props
and no Lines or offline inputs. See
[`evals/synthetic_journals/README.md`](evals/synthetic_journals/README.md) and
the README in each `evals/` subdirectory for the complete contracts and
artifact boundaries.

Every production agent invocation carries a template-specific prompt ID,
version, and static-artifact digest. Synthetic replay records the complete
runtime fingerprint set in its durable JSON transcript and uses the separate
content-bearing `linger-evals` Logfire service. Normal `linger-backend` traffic
remains metadata-only.

## Project Gutenberg notebook

[`notebooks/project_gutenberg_query_workflow.ipynb`](notebooks/project_gutenberg_query_workflow.ipynb)
guides an English-only, public-domain selection workflow:

1. Search the catalogue.
2. Shortlist and profile candidates using configurable word-count limits.
3. Record a content-versioned manifest.

Launch JupyterLab after installing dependencies:

```bash
uv run jupyter lab
```

Open the notebook and run its cells from top to bottom.

## Repository layout

Each agent owns its prompts and reasoning logic; orchestration, typed hand-offs,
and deterministic services remain shared.

```text
linger/
├── apps/                           # Runnable backend and frontend
│   ├── backend/                    # FastAPI entry point
│   └── frontend/                   # React user interface
├── src/linger/
│   ├── agents/                     # Agent prompts and reasoning
│   │   ├── muse/
│   │   ├── librarian/
│   │   ├── sculptor/
│   │   ├── serendipity/
│   │   └── provenance/
│   ├── corpus/                     # Canonical chapter processing and checks
│   ├── orchestration/              # Reflection, capture, and connection flows
│   ├── contracts/                  # Typed agent hand-offs
│   └── services/                   # Memory policy, retrieval, and citations
├── data/                           # Corpus, manifests, and fixtures
├── evals/                          # Benchmarks, package validation, adoption, and replay
├── synthetic-journal-evaluation/   # Objective catalog, run configurations, and authoring packages
├── tests/                          # Integration, security, and end-to-end tests
├── memories/                       # Git-ignored runtime Markdown memories
├── notebooks/                      # Manual Librarian and Gutenberg workflows
├── prompts/                        # Repository-owned prompt artifacts
└── docs/                           # Specification, telemetry contract, designs, and reports
```

For app-specific details, see [`apps/README.md`](apps/README.md).
