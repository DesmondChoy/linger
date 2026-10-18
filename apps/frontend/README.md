# Linger frontend

This React and TypeScript app presents chat, its collaboration map, and turn
records on one page. Chat is the product-facing path. The map, saved
evaluations, Reader, and Inspect are developer tools for corpus interaction and
backend debugging.

The landing page offers live chat through username and password sign-in, plus
saved synthetic evaluations that require no account. The browser remembers
the login token in local storage. **Sign out** revokes that token and returns
to the landing page; an expired token also returns the reader to sign-in.

## Run browser tests

Use Node 22.12 or newer. From `apps/frontend`, install the dependencies and Chromium once:

```sh
pnpm install --frozen-lockfile
pnpm exec playwright install chromium
```

Run `pnpm test:e2e` for the Chromium suite, or `pnpm test:e2e:ui` for Playwright's
interactive runner. Playwright builds the frontend and starts its preview server
on port 4173. Keep that port free.

The tests cover typing and keyboard submission, book selection and editable
preset submission, and saved persona replay with turn inspection. Sign-in,
history, and chat responses use controlled browser routes. No backend, account,
or model credentials are required. Persona replay loads the bundled recordings.
These tests check frontend behavior; backend and model behavior have separate tests.

CI runs the suite after Vitest. Failed tests retain traces and screenshots in
`test-results/`. Run `pnpm exec playwright show-report` to open the HTML report.
CI uploads the report and failure artifacts for seven days. Test files use
`.e2e.ts` so Vitest does not discover them. The build type-checks the tests.

## Chat and live inspection

Chat sends session-scoped reflection turns and displays released replies,
capture notices, and trace-correlated errors. The **Try a conversation** tray
offers guided paths for spoiler limits, book grounding, memory recall, web
connections, comparing books, safe declines, session continuity, and safety.
The book selector filters the available wordings, and **Try another wording**
starts another variant of the selected path. Each step has a **Watch for** hint.
Selecting a line fills the editable composer. Nothing is sent until you press
**Send**. A **Start a new chat** step creates a session. You can skip steps or
type your own lines. These live suggestions have no answer key.

The frontend calls `/api/chat/stream` and uses content-free progress events to
show which agents run and which handoffs occur. It displays the whole reply
after the backend approves release. Draft replies never stream to the browser.
Replies render Markdown, quotations, and source links. Other raw HTML is
discarded. Source details belong to the released reply.

The backend replaces detected email addresses and phone numbers in incoming
chat with placeholders before agent processing and persistence. Inspect and
reloaded history use that redacted text. The current browser feed retains the
reader's submitted wording until history reloads. Detected credentials and
the application's fixed instruction patterns receive a safe decline
without a saved conversation turn or automatic memory capture. See the
[security checks](../README.md#security-checks) for the checks and their scope.

The compact collaboration map follows the turn while it runs and shows the
selected turn's outcome beneath it. Select a component or connection to open a
dialog with the contract it carried, its general role, and its authority. The
turn selector chooses which completed turn the map shows. **All turns and
contracts** opens Inspect's full timeline in a separate dialog. Opening a turn
there updates the map. Escape, **Close**, or a click on the backdrop dismisses
either dialog.

Inspect exposes the request contract, context resolution, agent timing and
handoffs, direct Librarian calls, fixed Serendipity outcomes, and release and
capture decisions. Provenance findings include plain-language explanations,
the review path, and whether the candidate was corrected or withheld.
The Memory section shows the number of available memories and identifiers for
captured or cited memories.
**Copy trace query** copies a Logfire filter for the server-generated trace ID.
The local diagnostics can contain request content. Progress events and
operational telemetry contain metadata only.

`LINGER_DEV_INSPECT=true` enables content traces for local development and demos.
Component dialogs then include each agent's input, tool calls and results, and
output. Serendipity also shows recorded searches, results, and ranked decisions.
Captured and cited memory text appears in the Memory section. The setting
defaults to `false` and must remain disabled for deployments used by real
readers. Content traces accompany account-saved turn records in
`LINGER_STATE_DIR/transcripts.sqlite3`; disabling the setting stops collection
for later turns and does not erase traces already saved. Traces never enter
the progress stream or Logfire.

With content tracing disabled, resolve memory identifiers on the server from
the repository root:

```sh
	uv run python -m apps.backend.show_memories USERNAME [MEMORY_ID ...]
```

Without identifiers, the command lists active originals and the curated
retrieval view from the repository's `memories/` directory. With identifiers,
it lists only matching records and reports any missing records for the account.

## Synthetic personas

**Replay a persona** (on the start page, or **Replay a synthetic persona** in the
chat tray) opens recorded synthetic evaluation runs without signing in. Personas
are grouped by the objective catalog's menu families. Opening one replays its
latest run in the same chat feed, compact map, turn summary, popups, and
**All turns and contracts** view as a live conversation. The **Run** selector
opens earlier recorded runs when available. The persona brief shows its
Backstory, Props placed in the account before the run, model, result totals,
and completed review verdict when recorded. Each Scene's
person-adopted answer key, its recorded result, and the completed analysis
review's assessment appear in the turn summary. Offline curation Scenes appear
as labelled tasks. Anything a run did not record shows as "Not recorded in this
run" (for example, the MuseTurn policy of an offline curation task, where Muse
never drafted). The replay is read-only: it neither starts an evaluation nor calls a model.

Playback reads [`src/replay/personas/`](src/replay/personas): a small `index.json`
for the gallery and one file per persona, loaded only when that persona opens.
The exporter reads each Scenario's `backstory.json` and `ground-truth.json`, and
its retained final run in [`results/<scenario>/result.json`](../../results).
That file embeds the run's `evaluation.json`, `summary.json`, and completed
analysis review. Scenarios without a retained result are excluded. The
snapshot contains clipped synthetic agent inputs and outputs, recorded source
details, and connection events. Full model message transcripts, system
instructions, and local paths are excluded.

From the repository root, export the snapshot or check it without writing:

```sh
uv run python apps/frontend/scripts/export_personas.py
uv run python apps/frontend/scripts/export_personas.py --check
```

`--check` exits with an error when any exported JSON differs from the available
Scenario records. Exporting writes the gallery and persona files and removes
obsolete persona JSON files. These commands do not run evaluations or call models.
If a checkout has persona files without their source run directories, `--check`
reports a mismatch and exporting removes those personas. Restore the source
runs before refreshing a snapshot whose recorded playback must be preserved.

## Library

**Library** opens the Reader drawer. Reader loads enabled books from the
backend's book registry and exact revision grants, then fetches canonical text
by chapter or named section. It reveals a summary only after an explicit
spoiler warning and hides that summary when you select another location.
Contents group units by part. A book opens at the last unit viewed in this
browser, or its first main narrative chapter when no position is saved.
The bookshelf shows each work's title, author, and saved location. **Contents**
selects a chapter or named section, and the navigation beneath the text moves
to the previous or next unit. Browser bookmarks are diagnostic state and do
not record completed reading.

Selecting or revealing a Reader location does not establish a spoiler ceiling
for chat. Diagnostic output cannot grant retrieval, release, capture, or storage
authority. The backend derives reading context from reader statements and its
validated context-resolution workflow.

Reader's default library contains Alice, Animal Farm, Pinocchio, Frederick
Douglass, and The Story of My Life. Registering and granting a supported corpus
makes it available through `/api/library`. Opening a unit fetches its canonical
text through `/api/library/{work_id}/{book_version_id}/units/{unit_id}`. Folder
contents alone do not populate the shelf.

## Commands

Run from the repository root:

```bash
pnpm install --dir apps/frontend
pnpm --dir apps/frontend dev
pnpm --dir apps/frontend test
pnpm --dir apps/frontend lint
pnpm --dir apps/frontend build
pnpm --dir apps/frontend preview
```

The development server runs at <http://localhost:5173> and proxies `/api` to
<http://127.0.0.1:8000>. Set `VITE_API_URL` before `dev` or `build` to use a
different API base URL.

Vite 8 requires Node 20.19+ or 22.12+.

## Session behavior

Entering live chat loads the signed-in account's saved conversations and
inspection records, oldest first, and continues the latest session. A reader
with no saved conversation starts with a generated UUID. Reloading restores
saved history. Released Muse replies and application clarifications persist
across backend restarts; boundary replies and safe declines do not enter the
saved transcript.

**New chat** creates another session below the earlier conversations, keeping
their messages and turn records in the feed. **Delete** removes one conversation
after confirmation, including its saved inspection details and live session
state. Deleting the active conversation starts a fresh session. Account-scoped
memories and saved chapter progress persist across sessions and conversation
deletion. If a chat request fails, the frontend removes its pending reader
message and reply placeholder.

Book identity and progress come from the reader's chat messages and validated
backend context. An active book can resolve an indirect book follow-up without
establishing completed reading progress. When identity or progress remains
unresolved, chat displays the application's reviewed clarification question.
A book the reader names or confirms stays active when a routing tool cannot
resolve a later question. Naming a different book clears the old selection,
including when the new title is unavailable. A completed chapter declaration
can advance the active book without repeating its title.
The backend carries an explicit completed chapter across ordinary follow-ups
about that book and part. A lower or unclear progress correction lowers or
retracts the carried ceiling. Released explicit chapter declarations are also
saved per account and work in `LINGER_STATE_DIR/reading_progress.sqlite3`.
The latest released declaration replaces the saved chapter, including a lower
one. A new chat or backend restart can reuse that chapter after the current
message, session selection, or routing identifies the work. Saved progress
never selects a work. During initial context resolution, the session's current
progress or retraction takes precedence for that work. A vague retraction
leaves the durable saved record intact. Later routing or a cross-book comparison
can reuse that saved chapter until a released explicit correction replaces it.
Inferred ceilings, named-unit permissions, and exact-passage
permissions remain temporary. Library navigation never supplies permission.

A connection request can compare two or more confirmed books. Each book has
its own confirmed ceiling, with a declaration in the current turn replacing
that book's saved ceiling. Ordinary questions keep the focused book path.

When the reader asks about their own earlier reflections or preferences, Muse
can ask Serendipity to recall authorized memories without a book or web access.
One matching record is enough. The reply attributes recalled material to the
reader, and a missing match does not invent a memory or count as a search
failure.

For backend setup, API behavior, and configuration, see
[`../README.md`](../README.md).
