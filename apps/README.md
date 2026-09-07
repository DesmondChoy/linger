# Linger chat prototype

The runnable application combines a product-facing React chat path, a local
developer harness, a thin FastAPI transport adapter, one application-owned
chat-turn boundary, and five Pydantic AI reasoning roles. The chat-turn boundary
owns session scope, specialist grants, output release, capture policy, and
application telemetry; FastAPI only supplies trusted dependencies and maps the
result to HTTP.

The prototype has no end-user authentication or database. Conversation sessions
live in the backend process and disappear on restart. Automatic evaluation
captures use account-scoped Markdown storage under `memories/`; the public API
exposes no memory CRUD operations.

## Setup

From the repository root:

```bash
cp -f .env.example .env
uv sync --dev
pnpm install --dir apps/frontend
```

Set `LINGER_MODEL` and the matching provider key in `.env`. The checked-in
default is `openai:gpt-5.6-luna` with `OPENAI_API_KEY`; `google` models use
`GOOGLE_API_KEY`, and `anthropic` models use `ANTHROPIC_API_KEY`.

The remaining backend settings are:

| Setting | Purpose | Default |
|---|---|---|
| `LINGER_ACCOUNT_ID` | Server-owned account for the single-user prototype | `local-prototype-user` |
| `LINGER_ALLOWED_ORIGINS` | Comma-separated browser origins | `http://localhost:5173` |
| `ALLOWED_BOOK_VERSION_IDS` | JSON array of permitted registered corpus revisions | `["pg11-v01b38ea4"]` |
| `LINGER_WEB_SEARCH_ENABLED` | Grants Serendipity public-web search when `EXA_API_KEY` is also set | `false` |
| `EXA_API_KEY` | Exa credential for optional public-web search | unset |
| `LOGFIRE_TOKEN` | Logfire write token for deployed or CI runs | unset |

Local Logfire credentials can come from `uv run logfire projects use` instead
of `LOGFIRE_TOKEN`. Backend telemetry is metadata-only under
[`../docs/telemetry.md`](../docs/telemetry.md).

The runtime registry and default grant contain *Alice's Adventures in
Wonderland*. Corpus files for other works do not enable chat retrieval. See
[book registration](../docs/book-registration.md) for the registration and
revision checks. Section-based corpora are outside the chapter-based runtime.

## Running

Use two terminals from the repository root:

```bash
# API on http://127.0.0.1:8000
uv run uvicorn apps.backend.main:app --reload
```

```bash
# UI on http://localhost:5173
pnpm --dir apps/frontend dev
```

The Vite development server proxies `/api` to the backend. Set `VITE_API_URL`
when the frontend should call another API origin. Interactive API documentation
is available at <http://127.0.0.1:8000/docs>.

## Surfaces

- **Chat** sends one Line through the emotional-boundary preflight, Muse,
  optional Librarian or Serendipity calls, Provenance, and deterministic release
  validation.
- **New chat** clears backend conversation and reading-candidate state and mints
  a fresh frontend session ID.

Reader and Inspect are developer-only tools mounted in the local frontend for
convenience. They support corpus interaction and backend debugging and are not
part of the user-facing frontend contract. A product frontend should omit them.

- **Reader** opens the public Project Gutenberg Alice corpus by chapter so a
  developer can exercise corpus behavior. Navigation and summary reveal remain
  local diagnostic state and never authorize book retrieval in chat.
- **Inspect** records each released turn's input contract, context resolution,
  agent status, direct Librarian calls, fixed Serendipity outcome, release and
  capture decisions, and server-generated trace ID. These diagnostics cannot
  authorize retrieval, release, capture, or storage.

Muse invokes `librarian_route` when the reader's words depend on a book. An
active book can resolve an indirect follow-up, but does not require a lookup
for an unrelated personal reflection. Routing returns a chapter ceiling,
permission for exact passages, a clarification, or no match. A subsequent
`librarian_search` supplies source text. Exact passage permission requires
earlier reader statements that support having read the scene and does not
authorize its whole chapter or Serendipity book search.

Serendipity can search active account-scoped curated memories, a permitted
chapter range, and optional public-web sources. Its search grants do not widen
the release contract. Only proposals supported entirely by canonical book
records can pass deterministic release validation.

The application returns whole replies only after release approval. Distressing
first-person disclosures receive the fixed application-owned emotional boundary.
Rejected, failed, or deterministically invalid candidates receive the generic
application safe decline. Neither application-owned response can commit an
automatic memory or display a save notice.

Muse returns a typed candidate with a complete reply, book or session-Line
evidence declarations, and one memory nomination or no-nomination reason.
Application code verifies declared source locations, quotations, and exact
reader wording after Provenance review. A validated routing clarification is
released as the application's own question after safety review. Such a turn
cannot declare evidence or call tools other than `librarian_route`.
It also suppresses automatic capture and displays no save notice.

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness and configured model |
| `POST` | `/api/chat` | Released reply, developer diagnostics, trace correlation, and optional capture notice |
| `DELETE` | `/api/sessions/{id}` | Clear one in-process conversation and reading state |

`POST /api/chat` accepts `session_id`, optional `turn_id`, and `message`.
Unexpected fields fail validation. The server supplies account identity and all
authority-bearing policy state. Synthetic replay calls the same
`run_chat_turn` application boundary directly, without constructing an HTTP
request or translating a FastAPI exception.

## Validation

```bash
uv run pytest
pnpm --dir apps/frontend test
pnpm --dir apps/frontend lint
pnpm --dir apps/frontend build
```

Vite 8 requires Node 20.19+ or 22.12+.

## Layout

```text
apps/
├── backend/
│   ├── main.py       # FastAPI routes and HTTP outcome mapping
│   ├── chat_turn.py  # complete application-owned chat-turn workflow
│   ├── config.py     # repository-root .env settings
│   ├── contracts.py  # typed turn and context envelopes
│   ├── schemas.py    # public request and response bodies
│   ├── sessions.py   # in-process conversation and reading state
│   └── telemetry.py  # allowlisted backend and evaluation tracing
└── frontend/
    └── src/
        ├── api.ts
        ├── types.ts
        └── components/  # Product chat plus local Reader and Inspect developer tools
```
