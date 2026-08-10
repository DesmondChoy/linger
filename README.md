# Linger

An academic prototype of a **provenance-first reflection and memory companion**.

## At a glance

- **Runtime:** Python 3.12, FastAPI, and Pydantic AI
- **Reasoning:** five focused agents, with deterministic application control
- **Observability:** Pydantic Logfire (OpenTelemetry-compatible)
- **Corpus milestone:** *Alice's Adventures in Wonderland* from Project Gutenberg
- **Issue tracking:** [Beads](https://github.com/gastownhall/beads), backed by a local Dolt database

Linger keeps authority over account boundaries, memory writes, validation, and
user-visible output in application code—not in an agent.

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
cp .env.example .env

# Install Python application and development dependencies from uv.lock
uv sync --dev

# Install frontend dependencies
pnpm install --dir apps/frontend
```

Edit `.env` to set `LINGER_MODEL` and the matching API key. Only the selected
provider's key is needed:

- `google:gemini-2.5-flash` → `GOOGLE_API_KEY`
- `openai:gpt-5` → `OPENAI_API_KEY`
- `anthropic:claude-sonnet-4-5` → `ANTHROPIC_API_KEY`

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

### Get Beads working

For Beads setup and usage, ask your coding agent to consult the
[official Beads GitHub page](https://github.com/gastownhall/beads).

## Corpus

The first end-to-end corpus contains one book: Lewis Carroll's *Alice's
Adventures in Wonderland* ([Project Gutenberg ebook 11](https://www.gutenberg.org/ebooks/11)).

- Text: `data/gutenberg/alice-in-wonderland.txt`

This milestone proves ingestion, retrieval, spoiler filtering, citation, and
evaluation end to end. The corpus can then grow to the planned 3–5 books.

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
│   ├── orchestration/              # Reflection, capture, and connection flows
│   ├── contracts/                  # Typed agent hand-offs
│   └── services/                   # Memory policy, retrieval, and citations
├── data/                           # Corpus, manifests, and fixtures
├── evals/                          # Fixed evaluation cases and scorers
├── tests/                          # Integration, security, and end-to-end tests
├── docs/                           # Architecture, reports, and risk register
└── deploy/                         # Containers and deployment configuration
```

For app-specific details, see [`apps/README.md`](apps/README.md).
