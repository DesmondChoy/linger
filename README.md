# Linger

An academic prototype of a **provenance-first reflection and memory companion**.

## At a glance

- **Runtime:** Python 3.12, FastAPI, and Pydantic AI
- **Reasoning:** five reusable Agents with nine application-selected runtime skills
- **Observability:** Pydantic Logfire (OpenTelemetry-compatible)
- **Corpus:** five validated works enabled for Chat retrieval and Reader
- **Developer tooling:** corpus Reader and per-turn Inspect diagnostics
- **Synthetic evaluation:** validated scenarios, independent Ground truth review,
  chat replay, and bounded curation and surfacing evaluations
- **Issue tracking:** [Beads](https://github.com/gastownhall/beads), backed by a local Dolt database

Linger keeps authority over account boundaries, memory writes, validation, and
user-visible output in application code.

Each logical role owns one reusable PydanticAI `Agent` and an explicit skill
assignment in its package. The application selects the skill and typed contract
before a run. A run may make multiple model requests for tools or validation
retries. See the [agent runtime skills architecture](docs/agent-skills.md) for
the five-role mapping, current consumers, isolation rules, and evaluation paths.

## What the prototype does

- **Reflect:** sends each Line through a no-tool emotional-boundary preflight,
  Muse, optional specialists, Provenance, and deterministic release checks.
  Failed or rejected candidates produce application-owned responses.
- **Ground:** retrieves exact, spoiler-bounded book passages through Librarian.
  Chapter boundaries and exact-passage grants remain request-scoped. Book
  evidence declarations resolve to the canonical corpus; declarations of earlier
  reader wording must match a retained Line in the same session.
- **Reconnect:** lets Serendipity explore account-scoped curated memories,
  bounded book evidence, and configured public-web evidence through Exa.
  Private wording is blocked from web-search queries. Released connections
  resolve declared book, memory, and web evidence against exact request-scoped
  records reviewed by Provenance.
- **Capture:** supports reviewed automatic memory capture only through
  server-controlled evaluation policy. The interactive POC keeps capture
  disabled and exposes no memory-management actions.
- **Curate:** supports application-owned curation over bounded stored originals.
  Sculptor proposes summaries, duplicate links, topic groups, or retrieval
  tombstones. Provenance reviews the proposal before deterministic policy can
  apply it. Originals remain intact, and retrieval uses the curated view.
- **Evaluate:** validates synthetic scenarios, records independent
  human adoption without rewriting generated files, and replays supported
  capture, curation, book, session-continuity, connection, and restraint
  Objectives. Manual runners also cover weak-evidence reflection, cross-source
  execution, and offline surfacing decisions with the limits described in the
  evaluation guides.

## Developer tools

The local development frontend mounts Reader and Inspect for developers working
with the corpus and backend workflow. They are debugging tools, not product
frontend surfaces; a user-facing app should omit both.

- **Reader** browses enabled canonical books by chapter or named section and can
  reveal summaries after an explicit spoiler warning. It helps developers
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

`ALLOWED_BOOK_VERSION_IDS` accepts a JSON array of permitted registered corpus
revisions and defaults to `["pg11-v01b38ea4"]`. This setting restricts retrieval;
it does not register a corpus. See [app configuration](apps/README.md).

To send the backend's metadata-only telemetry and synthetic evaluation telemetry
to the Linger Logfire project:

```bash
uv run logfire --region us auth
uv run logfire --region us projects use --org desmond-choy linger
```

Use `LOGFIRE_TOKEN` instead in deployed or CI environments. The telemetry
allowlist and privacy constraints are defined in [`docs/telemetry.md`](docs/telemetry.md).
Configure Logfire before starting a provider-backed synthetic evaluation so the
accepted replay is available in Pydantic Evals and Logfire's Agents, LLMs and
providers, and Live views.

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

The repository contains five validated literary corpora. Immutable source files
live in `data/gutenberg/`; canonical chapters or sections and their derived
`catalog.json` files live in `data/corpus/<work-slug>/<book-version-id>/`.

| Work | Adapter under `src.linger.corpus` | Revision | Canonical units |
| --- | --- | --- | --- |
| *Alice's Adventures in Wonderland* | `alice` | `pg11-v01b38ea4` | 12 chapters |
| *Animal Farm* | `animal_farm` | `pga0100011-vc7ff4da7` | 10 chapters |
| *The Adventures of Pinocchio* | `pinocchio` | `pg500-v6bdc1734` | 36 chapters |
| *Narrative of the Life of Frederick Douglass, an American Slave* | `douglass` | `pg23-vd3f08ac3` | 16 sections |
| *The Story of My Life* | `story_of_my_life` | `pg2397-vb3cc1e13` | 140 sections |

All five works are registered in `src/linger/corpus/registry.py` and enabled by
the default application grant for Chat retrieval and Reader. An
`ALLOWED_BOOK_VERSION_IDS` override replaces that default grant. Chapter corpora
use schema 1; mixed works use schema 2 to preserve prefaces, letters, and chapter
titles in source order. Reviewed locations preserve natural chapter numbering:
Douglass starts at Chapter 1, Keller defaults to Part I, and Part III has its own
chapter sequence. Named letters and prefatory material use exact-unit permission.
Reader loads the same enabled registry and serves canonical text by stable unit ID.

See [Registering books and resolving their names](docs/book-registration.md)
for the shared resolver, ambiguity handling, onboarding checks, and ownership
boundaries.

The shared corpus lifecycle preserves source layout, uses compact JSON front
matter for routing, and validates canonical artifacts against their immutable
source. Each adapter defines source-specific wrappers, headings, and boundaries
while using the shared renderer, catalogue builder, and integrity checks.
BM25 paragraph windows, embeddings, and hybrid indexes are derived artifacts.

Verify the checked-in corpora and runtime registry:

```bash
for adapter in alice animal_farm pinocchio douglass story_of_my_life; do
	uv run python -m src.linger.corpus.book "src.linger.corpus.$adapter" check
done
uv run python -m src.linger.corpus.registry
```

See [canonical corpus formats](docs/corpus/canonical-sections.md) for import,
catalogue rebuild, and validation instructions.

For book questions, Linger uses supported reading progress to limit the passages
used in its answer. If the book or reading boundary is unclear, Linger asks for
clarification. Selecting a book alone does not establish reading progress.
See the [spoiler and routing contract](docs/specification.md#61-spoilers) for details.

## Skills

Ask your coding agent to use these project-local skills:

- [Format book corpus](.agents/skills/format-book-corpus/SKILL.md) converts book
  sources into Linger's canonical Markdown format and validates content integrity.
- [Plan synthetic scenarios](.agents/skills/plan-synthetic-scenarios/SKILL.md)
  plans evaluation Objectives and prepares a generator prompt without generating data.
- [Review synthetic Ground truth](.agents/skills/review-synthetic-ground-truth/SKILL.md)
  guides human review and adoption of proposed Ground truth, then runs a supported
  replay after confirmation.
- [Run scenario](.agents/skills/run-scenario/SKILL.md) runs a saved scenario selected
  from a numbered menu after provider and model confirmation and credential checks.
  It returns a Logfire link and saves an analysis report covering every Scene,
  including potentially misleading passes.

## Evaluation and validation

### Human-gated synthetic evaluation

Use the synthetic evaluation skills to prepare data, review expected results,
and test Linger's behavior:

1. Configure Logfire as described above, then ask your coding agent to use
   `plan-synthetic-scenarios`. Select evaluation Objectives to receive a
   pre-generation report.
2. Review the report and approve generation when its prerequisites are met.
   The agent generates and validates the Backstory and proposed Ground truth.
3. Ask the agent to use `review-synthetic-ground-truth`. Have an independent
   human reviewer approve or flag each Ground truth row in the review app.
4. Request changes or confirm adoption. Confirmation starts a replay for
   supported Objective selections; other selections stop after adoption.
5. Inspect replay results in Pydantic Evals and Logfire, and keep the JSON output
   as the evaluation record.

To run an already adopted scenario, use `run-scenario` and select its menu number.
Confirm the provider and model to start the replay.

See the [synthetic evaluation guide](evals/synthetic_journals/README.md) for
supported Objectives and detailed generation, review, and replay instructions.

### Automated checks and agent evaluations

Run the tests, frontend lint, and production build from the repository root:

```bash
uv run pytest
pnpm --dir apps/frontend test
pnpm --dir apps/frontend lint
pnpm --dir apps/frontend build
```

For individual agent evaluations, follow the relevant guide:

- [Librarian](evals/librarian/README.md): retrieval benchmarks and live validation.
- [Provenance](evals/provenance/README.md): emotional boundaries and risk classification.
- [Serendipity](evals/serendipity/README.md): connection discovery and cross-source evaluation.
- [Synthetic scenarios](evals/synthetic_journals/README.md): scenario validation,
  Ground truth adoption, and replay.

The guides list commands, model configuration, supported cases, and result formats.

## Repository layout

Each agent owns its prompts and reasoning logic; orchestration, typed hand-offs,
and deterministic services remain shared.

```text
linger/
├── apps/                           # Runnable backend and frontend
│   ├── backend/                    # FastAPI adapter plus application chat turn
│   └── frontend/                   # React user interface
├── src/linger/
│   ├── agents/                     # Five role Agents, runtime skills, and contracts
│   │   ├── muse/
│   │   ├── librarian/
│   │   ├── sculptor/
│   │   ├── serendipity/
│   │   └── provenance/
│   ├── corpus/                     # Canonical chapter and section processing
│   ├── orchestration/              # Reflection, capture, and connection flows
│   ├── contracts/                  # Typed agent hand-offs
│   └── services/                   # Memory policy, retrieval, and citations
├── data/                           # Corpus, manifests, and fixtures
├── evals/                          # Benchmarks, scenario validation, adoption, and replay
├── synthetic-journal-evaluation/   # Objective catalog, run configurations, and authored scenarios
├── tests/                          # Integration, security, and end-to-end tests
├── memories/                       # Git-ignored runtime Markdown memories
├── notebooks/                      # Manual Librarian and Gutenberg workflows
├── prompts/                        # Repository-owned prompt artifacts
└── docs/                           # Specification, telemetry contract, designs, and reports
```

For app-specific details, see [`apps/README.md`](apps/README.md).
