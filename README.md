# Linger

An academic prototype of a **provenance-first reflection and memory companion**.

## At a glance

- **Runtime:** Python 3.12, FastAPI, and Pydantic AI
- **Reasoning:** five focused agents, with deterministic application control
- **Observability:** Pydantic Logfire (OpenTelemetry-compatible)
- **Corpus:** five validated works, with Alice registered for chat retrieval
- **Developer tooling:** corpus Reader and per-turn Inspect diagnostics
- **Synthetic evaluation:** validated packages, independent Ground truth review,
  chat replay, and bounded curation and surfacing evaluations
- **Issue tracking:** [Beads](https://github.com/gastownhall/beads), backed by a local Dolt database

Linger keeps authority over account boundaries, memory writes, validation, and
user-visible output in application code.

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
- **Evaluate:** validates synthetic Backstory packages, records independent
  human adoption without rewriting generated files, and replays supported
  capture, curation, book, session-continuity, connection, and restraint
  Objectives. Manual runners also cover weak-evidence reflection, cross-source
  execution, and offline surfacing decisions with the limits described in the
  evaluation guides.

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

Only Alice is registered in `src/linger/corpus/registry.py` and available to
chat retrieval and Reader. The other four works are validated formatting
artifacts. Chapter corpora use schema 1; mixed works use schema 2 to preserve
prefaces, letters, and chapter titles in source order. Section corpora require
a section-aware runtime contract before registration.

See [Registering books and resolving their names](docs/book-registration.md)
for the shared resolver, ambiguity handling, onboarding checks, and ownership
boundaries.

The shared corpus lifecycle preserves source layout, uses compact JSON front
matter for routing, and validates canonical artifacts against their immutable
source. Each adapter defines source-specific wrappers, headings, and boundaries
while using the shared renderer, catalogue builder, and integrity checks.
BM25 paragraph windows, embeddings, and hybrid indexes are derived artifacts.

Verify all checked-in corpora and the runtime registry with:

```bash
for adapter in alice animal_farm pinocchio douglass story_of_my_life; do
	uv run python -m src.linger.corpus.book "src.linger.corpus.$adapter" check
done
uv run python -m src.linger.corpus.registry
```

The shared command accepts `init`, `build-catalog`, or `check`, with optional
`--source` and `--output` paths. `init` requires an empty destination;
`build-catalog` rebuilds only the derived catalogue from reviewed canonical
metadata. For source-preservation rules, audits, and examples, see
[canonical corpus formats](docs/corpus/canonical-sections.md).

Muse routes a request when the reader's words indicate that it depends on a
book. An active book selection alone is insufficient. The shared resolver
matches reviewed names and aliases; ambiguous catalogue words require
clarification. An indirect book follow-up can use the session's active
selection, but that selection grants no passage access or reading progress.

For a book request without explicit progress, Librarian privately searches the
complete selected work with the current Line, relevant account-scoped memories,
and bounded earlier reader statements. Application code can accept a
memory-supported chapter ceiling or grant exact paragraphs supported by earlier
reading statements. A curiosity-only Line grants neither. The second retrieval
searches only the accepted chapter range or re-fetches the exact granted
paragraphs, then reviews evidence strength before returning text to Muse.

An unresolved boundary produces an application-owned clarification. A valid
chapter answer resumes the original book question. See the
[spoiler and routing contract](docs/specification.md#61-spoilers) for validation
rules and the distinction between chapter boundaries, exact-passage grants, and
previously released evidence.

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

### Human-gated synthetic evaluation

The synthetic evaluation workflow keeps planning, generation, Ground truth
adoption, and execution behind separate human decisions:

1. Configure Logfire as described above, then ask your coding agent to run the
   [`generate-synthetic-journals`](.agents/skills/generate-synthetic-journals/SKILL.md)
   skill.
2. Select one or more evaluation Objectives in the local selector and confirm
   the selection. The skill writes only `pre-generation-report.md`; confirming
   the selection does not authorize synthetic-data generation.
3. Read the report and approve its design and detached generator prompt, request
   changes, or abandon the attempt. Generate data only after separate approval
   and only when the prompt is runnable or all named preconditions have been
   met. The generator writes sibling `backstory.json` and `ground-truth.json`
   files, and the repository validator checks them.
4. Ask your coding agent to run the
   [`review-synthetic-ground-truth`](.agents/skills/review-synthetic-ground-truth/SKILL.md)
   skill. An independent human reviewer approves or flags every proposed Ground
   truth row in the local review app.
5. **Make Changes** stops without adoption or replay. Confirmation writes the
   sibling `ground-truth-adoption.json`. For an exact supported selection, the
   skill starts one provider-backed replay. Automatic routing supports capture,
   bounded curation, session continuity, either book Objective alone, both book
   Objectives in either order, either connection or weak-evidence Objective
   alone, and their combination in either order. Other selections stop after
   adoption.
6. Inspect the accepted replay in Pydantic Evals and Logfire, and retain the
   runner's JSON output as the durable evaluation record.

The browser review app never invokes a model or runner. It returns the human
decision to the coding agent, which validates the adoption and maps a supported
Objective to its runner. See the
[`evals/synthetic_journals` guide](evals/synthetic_journals/README.md) for the
package, review, replay, and telemetry contracts.

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

# Provider-backed Provenance risk-code classification
uv run python -m evals.provenance.risk_codes --report /tmp/provenance-risk-codes.json

# Provider-backed Serendipity component cases with fixture evidence
uv run python -m evals.serendipity.runner --output /tmp/serendipity-components.json

# Validate a synthetic package
uv run python -m evals.synthetic_journals.validate_package \
  path/to/backstory.json path/to/ground-truth.json

# Review proposed Ground truth and write a hash-bound adoption after confirmation
uv run python \
  .agents/skills/review-synthetic-ground-truth/scripts/ground_truth_reviewer.py \
  path/to/backstory.json path/to/ground-truth.json \
  --reviewer-id REVIEWER_ID

# Replay a capture package through the production application chat boundary
uv run python -m evals.synthetic_journals.replay \
  synthetic-journal-evaluation/packages/2026-08-23T182725+0800/backstory.json \
  synthetic-journal-evaluation/packages/2026-08-23T182725+0800/ground-truth.json \
  --output /tmp/reviewed-automatic-memory-capture-run.json

# Replay a bounded-curation package through production Sculptor
uv run python -m evals.synthetic_journals.curation_replay \
  path/to/backstory.json path/to/ground-truth.json \
  --output /tmp/bounded-memory-curation-run.json

# Replay grounded reflection, spoiler clarification, or their combined selection
uv run python -m evals.synthetic_journals.book_replay \
  path/to/backstory.json path/to/ground-truth.json \
  --adoption path/to/ground-truth-adoption.json \
  --output /tmp/book-reflection-spoiler-run.json

# Replay ordered conversation Lines and a fresh-session comparison
uv run python -m evals.synthetic_journals.continuity_replay \
  path/to/backstory.json path/to/ground-truth.json \
  --output /tmp/session-continuity-run.json

# Manually replay weak-evidence reflection Scenes
uv run python -m evals.synthetic_journals.reflection_replay \
  path/to/backstory.json path/to/ground-truth.json \
  --output /tmp/weak-evidence-reflection-run.json

# Evaluate offline Sculptor surfacing decisions over supplied Props
uv run python -m evals.synthetic_journals.surfacing_replay \
  path/to/backstory.json path/to/ground-truth.json \
  --output /tmp/offline-memory-surfacing-run.json

# Manually exercise the cross-source application path
uv run python -m evals.serendipity.objective_replay \
  evals/serendipity/objective_cases/cross-source-outside-essay-v1.json \
  --output /tmp/cross-source-run.json
```

The Librarian benchmark accepts `--output`, `--repetitions`, `--target-words`,
and `--overlap-words`. Live Librarian validation accepts repeatable `--case`,
`--limit`, and `--report`; both Provenance evaluations accept `--report`.
The Serendipity component runner requires `--output` and accepts `--no-logfire`
and `--semantic-review`. Book replay also accepts `--semantic-review` for a
separate model review that does not change deterministic grades.
Synthetic package validation accepts `--run-configuration-directory`. The
Ground truth reviewer requires `--reviewer-id`; `--adoption` selects a sibling
output path, `--ui` selects a built UI directory, and `--timeout` sets the
loopback review lifetime in seconds. The `evals.synthetic_journals` replay
commands accept an optional hash-validated `--adoption` and write JSON to stdout
unless `--output` is supplied. Cross-source `objective_replay` requires
`--output` and has no adoption option.

Without `--adoption`, replay compares observed hard gates with proposed Ground
truth. A complete independent adoption changes the dataset identity and grades
the same gates as adopted Ground truth. Capture replay accepts only the
`reviewed_automatic_memory_capture` topology; curation replay accepts only
isolated `bounded_memory_curation` Scenes containing two to twelve active Props
and no Lines or offline inputs. Book replay compiles `book_scene_facts` and
`book_expectation` for `grounded_book_reflection`,
`spoiler_boundary_clarification`, or both in either order. It grades chapter
boundaries and completed retrieval, including the final released answer's
declared support. Exact-passage grants are outside that chapter-scoped Objective.

Continuity replay keeps each Scene's ordered Lines in one session and compares
with a fresh-session Scene. Its adopted grade covers the specified session
boundary; conversational correction and leakage remain review judgments.
Reflection replay accepts only `weak_evidence_safe_decline`. Offline surfacing
replay accepts one offline input per Scene and no Lines, evaluates
`surface_now`, `defer`, or `do_not_surface`, and leaves Props unchanged.

The conversational `proactive_memory_surfacing` Objective requires reviewed
capture, triggered curation, and appropriate memory use in a later chat. That
complete path remains unimplemented. The offline runner measures only its
decision component. Adopted connection replay runs one Line per fresh-session
Scene with exact memory, book, and public-source expectations. Its hard checks
cover source resolution, typed decisions, citations, and release. Semantic
quality remains a separate review judgment. The manual Serendipity cross-source
runner exercises ordered Lines through chat and grades the final turn's recorded
connection events and release inspection; those structural checks do not
establish an adopted synthetic Objective grade. See
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
│   ├── backend/                    # FastAPI adapter plus application chat turn
│   └── frontend/                   # React user interface
├── src/linger/
│   ├── agents/                     # Agent prompts and reasoning
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
├── evals/                          # Benchmarks, package validation, adoption, and replay
├── synthetic-journal-evaluation/   # Objective catalog, run configurations, and authoring packages
├── tests/                          # Integration, security, and end-to-end tests
├── memories/                       # Git-ignored runtime Markdown memories
├── notebooks/                      # Manual Librarian and Gutenberg workflows
├── prompts/                        # Repository-owned prompt artifacts
└── docs/                           # Specification, telemetry contract, designs, and reports
```

For app-specific details, see [`apps/README.md`](apps/README.md).
