# Linger chat prototype

The runnable application combines a product-facing React chat path, a local
developer harness, a thin FastAPI transport adapter, one application-owned
chat-turn boundary, and five Pydantic AI reasoning roles. The chat-turn boundary
owns session scope, specialist grants, output release, capture policy, and
application telemetry; FastAPI only supplies trusted dependencies and maps the
result to HTTP.

The landing page offers a live path (username and password sign-in) and a
synthetic path (saved persona evaluations, no sign-in). Accounts and login
tokens live in `data/accounts.sqlite3` (prototype-grade: salted scrypt
hashes, no resets or lockouts). Every chat and session route derives the
account from the bearer token. Released chat turns are saved per account in
`data/transcripts.sqlite3` and reopen from Past chats; a conversation belongs to
exactly one account. Automatic memory captures use account-scoped Markdown
storage under `memories/`. The public API exposes no memory CRUD operations.

## Setup

From the repository root:

```bash
cp -f .env.example .env
uv sync --dev
pnpm install --dir apps/frontend
```

Set `LINGER_MODEL` and the matching provider key in `.env`. The checked-in
default is `openai:gpt-6-luna` with `OPENAI_API_KEY`; `google` models use
`GOOGLE_API_KEY`, and `anthropic` models use `ANTHROPIC_API_KEY`.

The remaining backend settings are:

| Setting | Purpose | Default |
|---|---|---|
| `LINGER_ALLOWED_ORIGINS` | Comma-separated browser origins | `http://localhost:5173` |
| `ALLOWED_BOOK_VERSION_IDS` | JSON array of permitted registered corpus revisions | All five revisions in [`Settings`](backend/config.py) |
| `LINGER_WEB_SEARCH_ENABLED` | Grants Serendipity public-web search when `EXA_API_KEY` is also set | `false` |
| `EXA_API_KEY` | Exa credential for optional public-web search | unset |
| `LOGFIRE_TOKEN` | Logfire write token for deployed or CI runs | unset |

Local Logfire credentials can come from `uv run logfire projects use` instead
of `LOGFIRE_TOKEN`. Backend telemetry is metadata-only under
[`../docs/telemetry.md`](../docs/telemetry.md).

The runtime registry and default grant enable all five supplied works for chat
retrieval and Reader, including both chapter-based and section-based corpora.
An `ALLOWED_BOOK_VERSION_IDS` override replaces the default grant; it does not
register a corpus. See [book registration](../docs/book-registration.md) for
supported works, reading boundaries, and revision checks.

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

## Chat and developer tools

- **Chat** shares one page with the live collaboration map and turn records. It
  sends one Line through the emotional-boundary preflight, Muse, optional
  Librarian or Serendipity calls, Provenance, and deterministic release
  validation. The **Try a line** tray groups editable prompts by book. Selecting
  a prompt fills the composer. **Send** submits it.
- **New chat** clears backend conversation and reading-candidate state and mints
  a fresh frontend session ID. Account-scoped memories persist across sessions.

The collaboration map, saved evaluations, Reader, and Inspect are local
developer tools for corpus interaction and backend debugging. They are outside
the user-facing frontend contract.

- The **collaboration map** follows the server's content-free progress stream
  while a turn runs. A completed turn combines that stream with released
  diagnostics. Selecting a component or connection opens the contract it
  carried on that turn. The turn selector changes the mapped turn while every
  completed turn remains in the record below it.
- **Open a saved evaluation** displays recorded synthetic runs from the shared
  generated snapshot. Select a scenario, run, and Scene to inspect the fixed
  reader message, seeded memories, recorded route, expected outcomes, grades,
  and reply. These records do not execute agents. The separate
  [evaluation explorer](evaluation-explorer/README.md) describes expected
  architecture and maintains the shared snapshots.
- **Library** opens the Reader drawer with enabled canonical books by chapter
  or named section. Navigation and summary reveal remain local diagnostic
  state and never authorize book retrieval in chat.
- **Inspect** shows each completed turn's input contract, context resolution,
  agent timing and handoffs, direct Librarian calls, fixed Serendipity outcome,
  release and capture decisions, and server-generated trace ID. Provenance
  findings include explanations and the review path. **Copy trace query**
  copies a Logfire filter for that turn.

These developer tools cannot authorize retrieval, release, capture, or storage.

Muse invokes `librarian_route` when the reader's words depend on a book. An
active book can resolve an indirect follow-up, but does not require a lookup
for an unrelated personal reflection. Routing returns a chapter ceiling,
permission for exact passages, a clarification, or no match. A subsequent
`librarian_search` supplies source text. Exact passage permission requires
earlier reader statements that support having read the scene and does not
authorize its whole chapter or Serendipity book search. A book the reader names
or confirms remains active when a routing tool is uncertain. Naming a different
book or removing its revision from the permitted scope clears that selection.

Serendipity can search active account-scoped curated memories, a permitted
chapter range, and optional public-web sources. Its search grants do not widen
the release contract. Selected book, memory, and opened public-page records
must satisfy their source-specific attribution and citation checks before a
reply can be released.

For a question about the reader's earlier reflections, decisions, or
preferences, Muse can request `recall_memory`. Serendipity searches only the
account's authorized memories and returns one to three matching records. One
matching record is a complete recall. Muse attributes those records to the
reader's earlier words. Memories do not support claims about the world. A
`no_matching_memory` decline lets Muse answer without inventing a prior record.
Recall needs neither a book selection nor public-web access.

When the reader names the sources to consider together (scenes from their
books, a named public text, their own earlier note), triage pins
`gather_sources`. Serendipity inspects each named source and returns one bundle
with every supporting record and the named sources it could not find; Muse
writes the comparison. A request that names no sources ("anything I've read")
uses `find_connection`.

The application returns whole replies only after release approval. Clear
first-person disclosures of intense distress receive the fixed application-owned
emotional boundary.
When the preflight requires that boundary, the pipeline skips memory loading
and downstream agent calls. Rejected, failed, or deterministically invalid
candidates receive the generic application safe decline. Neither
application-owned response can commit an automatic memory or display a save
notice.

Muse returns a typed candidate with a complete reply, source-specific evidence
declarations, and one memory nomination or no-nomination reason.
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
| `POST` | `/api/chat/stream` | Content-free progress events followed by the released chat result or an error |
| `DELETE` | `/api/sessions/{session_id}` | Clear one in-process conversation and reading state |
| `GET` | `/api/library` | Registered and granted books, their reading locations, and starting locations |
| `GET` | `/api/library/{work_id}/{book_version_id}/units/{unit_id}` | Canonical text for a granted Reader location |

Both chat endpoints accept `session_id`, optional `turn_id`, and `message`.
Session and turn IDs contain 1 to 200 characters. Messages contain 1 to 8000
characters. The API strips surrounding whitespace and rejects unexpected
fields. The server supplies account identity and all authority-bearing policy
state.

The frontend uses `/api/chat/stream`, which returns server-sent events.
`progress` events contain stage, status, timing, and handoff metadata.
The final `result` contains the same complete response as `/api/chat`.
An `error` event contains a safe error message and trace reference when one is
available. Reply text appears only after release approval. Progress events
contain no draft tokens, prompts, queries, or evidence. Completed local
inspection records can contain request and source content.

Synthetic replay calls the same `run_chat_turn` application boundary directly,
without constructing an HTTP request or translating a FastAPI exception.

## Validation

```bash
uv run pytest
pnpm --dir apps/frontend test
pnpm --dir apps/frontend lint
pnpm --dir apps/frontend build
```

The standalone explorer carries the shared map's own tests and lint:

```bash
pnpm --dir apps/evaluation-explorer test
pnpm --dir apps/evaluation-explorer lint
pnpm --dir apps/evaluation-explorer build
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
├── frontend/
│   └── src/
│       ├── api.ts
│       ├── types.ts
│       └── components/       # Product chat plus local Architecture, Reader, and Inspect tools
│           └── architecture/ # Maps one real turn onto the shared collaboration map
└── evaluation-explorer/      # Standalone architecture explorer on its own port
```

Both frontends render the shared collaboration map in
[`../packages/architecture-map`](../packages/architecture-map): the component
registry, graph rendering, curated Scenes, and the detail drawer. It is
source-only and resolves through the `@linger/architecture-map` alias, so each
app keeps its own lockfile and dev server and needs no extra install.
