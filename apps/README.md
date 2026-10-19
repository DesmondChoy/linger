# Linger chat prototype

The runnable application combines a product-facing React chat path, a local
developer harness, a thin FastAPI transport adapter, one application-owned
chat-turn boundary, and five Pydantic AI reasoning roles. The chat-turn boundary
owns session scope, specialist grants, output release, capture policy, and
application telemetry; FastAPI only supplies trusted dependencies and maps the
result to HTTP.

The landing page offers a live path (username and password sign-in) and a
synthetic path (saved persona evaluations, no sign-in). Accounts and login
tokens live in `data/accounts.sqlite3`. Passwords use salted scrypt hashes;
tokens expire after seven days and are stored as SHA-256 digests. The prototype
has no password resets, email verification, or login lockouts. Every chat,
history, and session route derives the account from the bearer token.
Released Muse replies and application clarifications are saved per account in
`data/transcripts.sqlite3`, together with their inspection details. Signing in
loads these conversations into the feed and continues the latest session.
Boundary replies and safe declines are absent from the saved transcript.
A conversation belongs to exactly one account. Explicit completed-chapter
progress is saved per account and work in `data/reading_progress.sqlite3`.
Saved progress survives new conversations, conversation deletion, sign-out,
and backend restarts. It applies after the reader identifies the book.
Automatic memory capture is enabled for interactive accounts without a stored
policy; a stored account policy takes precedence. Captures use account-scoped
Markdown storage under `memories/`. The public API exposes no memory CRUD or
capture-preference operations.

## Setup

For a single Docker image with persistent accounts, transcripts, reading
progress, and memories, use the [release and deployment guide](../docs/releasing.md).

From the repository root:

```bash
cp -f .env.example .env
uv sync --dev
pnpm install --dir apps/frontend
```

Set `LINGER_MODEL` and the matching provider key in `.env`. The checked-in
default is `openai:gpt-6-luna` with `OPENAI_API_KEY`; `google` models use
`GOOGLE_API_KEY`, and `anthropic` models use `ANTHROPIC_API_KEY`.
The standard OpenAI model defaults to low reasoning effort. Muse uses medium
effort for drafting and revision. Provenance uses medium effort for candidate
review. Muse turn triage uses
`gpt-6-luna` for OpenAI, `gemini-2.5-flash` for Google, and `LINGER_MODEL` for
Anthropic. It needs no separate credential or model setting.

The remaining backend settings are:

| Setting | Purpose | Default |
|---|---|---|
| `LINGER_ALLOWED_ORIGINS` | Comma-separated browser origins | `http://localhost:5173` |
| `LINGER_STATE_DIR` | Writable account, transcript, and reading-progress database directory | `data/` |
| `LINGER_MEMORY_DIR` | Writable account memory directory | `memories/` |
| `LINGER_STATIC_DIR` | Built frontend directory served by FastAPI; the release image sets `/app/static` | unset |
| `ALLOWED_BOOK_VERSION_IDS` | JSON array of permitted registered corpus revisions | All five revisions in [`Settings`](backend/config.py) |
| `LINGER_WEB_SEARCH_ENABLED` | Grants Serendipity public-web search when `EXA_API_KEY` is also set | `false` |
| `EXA_API_KEY` | Exa credential for Serendipity public-web search and separately invoked Sculptor retrieval research | unset |
| `LOGFIRE_TOKEN` | Logfire write token for deployed or CI runs | unset |
| `LINGER_DEV_INSPECT` | Developer or demo content traces and memory text in completed Inspect records; keep disabled for deployments used by real readers | `false` |

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

For a production-style local stack, run `docker compose up --build` from the
repository root. The UI is served at <http://localhost:5173>, Nginx proxies its
`/api` requests to the backend, and the API remains directly reachable at
<http://localhost:8000>. Compose stores writable application state and memories
in named volumes while the reviewed corpus remains immutable in the backend
image.

The separate `compose.release.yaml` runs a tested release image with the
frontend and backend together. See the [release guide](../docs/releasing.md)
for approved image deployment, backup, and rollback.

The Vite development server proxies `/api` to the backend. Set `VITE_API_URL`
when the frontend should call another API origin. Interactive API documentation
is available at <http://127.0.0.1:8000/docs>.

## Chat and developer tools

- **Chat** shares one page with the live collaboration map and turn records. It
  sends one Line through the emotional-boundary preflight, Muse, optional
  Librarian or Serendipity calls, Provenance, and deterministic release
  validation. The **Try a conversation** tray offers eight guided paths for
  spoilers, grounding, memory, web, cross-book connections, declines, sessions,
  and safety. Paths include steps and **Watch for** hints, with an optional book
  filter and **Try another wording**. A Line step fills the editable composer.
  **Send** submits it.
- **New chat** creates a fresh session ID and clears the current activity and
  error display. Earlier conversations and their turn records remain in the feed.
  Saved reading progress remains available when the reader identifies a book.
- **Delete** removes the selected conversation's saved transcript, inspection
  details, and in-process session state after confirmation. Deleting the active
  conversation starts a fresh session. Account-scoped memories and saved
  reading progress persist.
- **Sign out** revokes the current token and clears the browser's remembered
  account. Saved conversations remain available on the next sign-in.

The collaboration map, saved evaluations, Reader, and Inspect are local
developer tools for corpus interaction and backend debugging. They are outside
the user-facing frontend contract. Rules:
[Specification §4.2.4](../docs/specification.md#424-developer-corpus-and-inspection-tools).

- The **collaboration map** follows the server's content-free progress stream
  while a turn runs. A completed turn combines that stream with released
  diagnostics. Selecting a component or connection opens its turn contract in
  a dialog. **All turns and contracts** opens the conversation timeline. Escape,
  **Close**, and the backdrop dismiss these dialogs.
- The **synthetic persona gallery** displays checked-in persona JSON snapshots.
  A persona opens its recorded conversation and turn map, with the latest run
  selected first and a selector for earlier runs. Each Scene includes its
  adopted answer key, deterministic grade, and saved review assessment when
  present. Offline memory-curation records have a separate presentation.
  These records do not execute agents. The separate
  [evaluation explorer](evaluation-explorer/README.md) describes expected
  architecture; persona export belongs to the
  [frontend workflow](frontend/README.md).
- **Library** opens the Reader drawer with enabled canonical books by chapter
  or named section. Navigation and summary reveal remain local diagnostic
  state and never authorize book retrieval in chat.
- **Inspect** shows each completed turn's input contract, context resolution,
  agent timing and handoffs, direct Librarian calls, fixed Serendipity outcome,
  release and capture decisions, and server-generated trace ID. Provenance
  findings include explanations and the review path. Memory details include
  the active count, captured memory ID, and cited memory IDs. **Copy trace query**
  copies a Logfire filter for that turn. With `LINGER_DEV_INSPECT=true`, completed
  records also contain agent task inputs, tool calls and results, outputs,
  Serendipity search events, and captured or cited memory text. The account's
  saved turn retains this content in `LINGER_STATE_DIR/transcripts.sqlite3`.
  The trace reuses the evaluation transcript hooks, which observe without
  changing agent behaviour, and is never sent to telemetry. Disabling the
  setting stops future collection and does not redact earlier saved records.
  For a failed stage, Inspect records whether the failure came from
  application code, a model call, or deterministic validation, and whether it
  is retryable. Stage durations come from paired start and completion events;
  an unpaired event leaves its duration unavailable.

These developer tools cannot authorize retrieval, release, capture, or storage.

To resolve memory IDs on the server, use the account's lowercase username:

```bash
	uv run python -m apps.backend.show_memories USERNAME
	uv run python -m apps.backend.show_memories USERNAME MEMORY_ID [MEMORY_ID ...]
```

Without IDs, the command prints active original records and the curated
retrieval view. With IDs, it filters both lists and reports missing records.
It reads the repository-root `memories/` directory; it does not use a
`LINGER_MEMORY_DIR` override. The command is a local developer tool and prints
private memory text.

Muse invokes `librarian_route` when the reader's words depend on a book. An
active book can resolve an indirect follow-up, but does not require a lookup
for an unrelated personal reflection. Routing returns a chapter ceiling,
permission for exact passages, a clarification, or no match. A subsequent
`librarian_search` supplies source text. Exact passage permission requires
earlier reader statements that support having read the scene and does not
authorize its whole chapter or Serendipity book search. A book the reader names
or confirms remains active when a routing tool is uncertain. Naming a different
book or removing its revision from the permitted scope clears that selection.

The reader's explicit completed chapter carries across ordinary follow-ups
about the same book and part. A lower declaration applies to the session
immediately, including when the reply fails. A higher declaration takes effect
after a released Muse reply or application clarification. An unclear correction
retracts the session ceiling and excludes earlier statements and passages that
could restore the carried permission. During context preparation, routing, and
comparisons, a session declaration or retraction takes precedence over saved
progress for that work. Questions, conditions, and explicit uncertainty about
completion do not grant chapter progress.

After a released Muse reply or application clarification, the interactive
application saves explicit completed-chapter progress. The latest saved
statement wins, including a lower chapter or a different part. Saved progress
never selects a book, grants a named unit or exact passage, or stores a
Librarian inference. A failed or declined correction affects the session but
does not replace the saved account record. An unclear retraction stays local
to the session. It withholds that work's saved chapter from later routing and
comparisons. A released explicit correction can replace the retracted
permission. Changing book or part clears active chapter carry.
Corrections for each work remain for the rest
of the session, including when the reader returns to a previous book. Deleting
the session or restarting the backend clears those corrections; the saved
account record remains.
Saved conversation text does not establish reading permission after a restart.

When triage selects `find_connection`, the application combines saved progress
with any confirmed permission in the current turn. If that covers at least two
books, the application supplies every book at its own ceiling, with no single primary book. A confirmed boundary in the current turn
replaces that book's saved ceiling for the comparison. Ordinary book questions
and single-book requests retain their focused context.

Muse receives at most eight recent released turns and 16,000 characters of
conversation history, dropping whole oldest turns. A separate no-tool triage
call classifies the current Line. Application code combines that result with
reading context and validated source grants to expose specialist tools and
load the corresponding reflection modules. See the
[Muse guide](../src/linger/agents/muse/README.md) for the routing and revision rules.

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
uses `find_connection`, including "Does anything I've read speak to this?".
A request for an unfamiliar outside work selects `get_recommendation`.

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
| `GET` | `/api/ready` | Offline deployment readiness; returns `200` when ready or `503` with the failed check |
| `POST` | `/api/auth/signup` | Create an account and return a login token |
| `POST` | `/api/auth/login` | Check credentials and return a login token |
| `GET` | `/api/auth/me` | Identify the signed-in account |
| `POST` | `/api/auth/logout` | Revoke the supplied login token |
| `POST` | `/api/chat` | Released reply, developer diagnostics, trace correlation, and optional capture notice |
| `POST` | `/api/chat/stream` | Content-free progress events followed by the released chat result or an error |
| `GET` | `/api/history` | Saved conversations, turns, and inspection details for the signed-in account, oldest first |
| `DELETE` | `/api/sessions/{session_id}` | Delete the account's saved conversation and clear its in-process state |
| `GET` | `/api/library` | Registered and granted books, their reading locations, and starting locations |
| `GET` | `/api/library/{work_id}/{book_version_id}/units/{unit_id}` | Canonical text for a granted Reader location |

Sign-up and login accept `username` and `password`. Usernames have 3 to 32
letters, digits, underscores, periods, or hyphens and are case-insensitive.
Passwords have 6 to 200 characters. Both routes return `username` and `token`.
Send `Authorization: Bearer <token>` with chat, history, session deletion, and
`/api/auth/me` requests. Logout revokes that supplied token. Missing or expired
authentication returns `401`; another account's conversation returns `404`.
The health, readiness, and read-only library routes require no sign-in.

Both chat endpoints accept `session_id`, optional `turn_id`, and `message`.
Session and turn IDs contain 1 to 200 characters and reject control characters.
Messages contain 1 to 8000 characters after normalisation. The API strips
surrounding whitespace, normalises line endings and Unicode, removes hidden
control characters, and rejects unexpected fields. The server supplies account
identity and all authority-bearing policy state. The [security checks](#security-checks)
describe redaction before agent processing and storage.

A successful saved turn can be retried with the same session, turn ID, and
normalised message. The application returns its saved response without running
the agents again, including after a restart. Reusing a turn ID with different
input returns a conflict. A request fingerprint distinguishes messages whose
contact details redact to the same placeholders without storing those details.
Older turns without a complete saved response require a new turn ID.

One operation can change a session at a time. An overlapping chat request or
deletion returns a conflict, and the reader can retry after the active request
finishes. Atomic chat and deletion return `409`. Streaming chat emits its
existing `error` event with no `result` event.
The guard follows the backend's existing in-process session storage.

The two chat endpoints share a limit of 10 requests per rolling 60 seconds per
authenticated account. Exceeding it returns `429` with `Retry-After` before a
stream opens or a model runs. Counters are local to the backend process.
The English-language guard returns a fixed notice for confidently non-English
messages without invoking agents. The deterministic self-harm check takes
priority over that guard. See the [safeguards](../docs/specification.md#6-safeguards)
for message, privacy, and output-release rules.

Readiness checks provider configuration, writable storage and SQLite integrity,
registered corpus files, and local embedding and reranker models. A combined
release image also checks its model manifest and built frontend. Readiness
makes no model-provider request and does not verify that the configured API key
works with the provider.

The frontend uses `/api/chat/stream`, which returns server-sent events.
`progress` events contain stage, status, timing, and handoff metadata.
The final `result` contains the same complete response as `/api/chat`.
An `error` event contains a safe error message and trace reference when one is
available. Reply text appears only after release approval. Progress events
contain no draft tokens, prompts, queries, or evidence. Completed local
inspection records can contain request and source content.

Synthetic replay calls the same `run_chat_turn` application boundary directly,
without constructing an HTTP request or translating a FastAPI exception.

## Security checks

At chat entry, DataFog's local regex detector replaces email addresses and
phone numbers with placeholders such as `[EMAIL_1]` and `[PHONE_1]`. Agents,
saved conversation text, inspection, and automatic-capture offsets use that
redacted message. This detector leaves names, addresses, employers, and health
conditions unchanged. DataFog telemetry is disabled by the application.
Legacy saved reader messages and their session previews are redacted before
history restoration. Generated replies and other saved context receive no
additional PII scan.

Detected credentials receive a fixed safe decline before any agent runs.
The user-input injection check also blocks three fixed patterns: requests to
ignore application instructions, disclose hidden prompts or instructions, or
follow replacement instructions. It runs before the emotional-boundary agent
when the language guard permits the message. Security blocks do not enter
conversation history or commit reading progress or memories.
`inspection.release.security_block_category` identifies `credential` or
`prompt_injection`; `security_pattern_ids` lists matched injection rules.
These regex rules cover their stated patterns and do not establish resistance
to other attack wording.

All five reusable agents check messages, tool history, and request schemas for
credentials before each provider request. Generated Muse replies and memory
nominations, curation text, and conversation and memory storage also reject
detected credentials. These internal checks preserve other personal text.

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
│   ├── auth.py       # bearer authentication and account routes
│   ├── accounts.py   # SQLite accounts and expiring login tokens
│   ├── chat_turn.py  # complete application-owned chat-turn workflow
│   ├── config.py     # repository-root .env settings
│   ├── contracts.py  # typed turn and context envelopes
│   ├── schemas.py    # public request and response bodies
│   ├── sessions.py   # in-process conversation and reading state
│   ├── reading_progress.py # reader-declared chapter carry and retraction
│   ├── progress_store.py # account-scoped explicit reading progress in SQLite
│   ├── dev_trace.py   # opt-in developer content trace for completed turns
│   ├── show_memories.py # local memory-ID lookup command
│   ├── transcripts.py # SQLite released conversations and inspection records
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
registry, graph rendering, curated Scenes, and component and handoff details.
It is source-only and resolves through the `@linger/architecture-map` alias, so each
app keeps its own lockfile and dev server and needs no extra install.
