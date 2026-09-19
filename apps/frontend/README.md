# Linger frontend

This React and TypeScript app presents chat, its collaboration map, and turn
records on one page. Chat is the product-facing path. The map, saved
evaluations, Reader, and Inspect are developer tools for corpus interaction and
backend debugging.

## Chat and live inspection

Chat sends session-scoped reflection turns and displays released replies,
capture notices, and trace-correlated errors. The **Try a line** tray groups
sample prompts by book, with examples for quotations, spoiler limits,
connections, and reflection. Selecting a prompt fills the editable composer.
Nothing is sent until you press **Send**. Sample prompts have no answer key.

The frontend calls `/api/chat/stream` and uses content-free progress events to
show which agents run and which handoffs occur. It displays the whole reply
after the backend approves release. Draft replies never stream to the browser.

The collaboration map follows the turn while it runs. For completed turns,
select a component or connection to inspect the contract it carried, alongside
its general role and authority. The turn selector chooses which completed turn
the map shows. Every completed turn remains in the Inspect timeline, and
opening a turn there updates the map.

Inspect exposes the request contract, context resolution, agent timing and
handoffs, direct Librarian calls, fixed Serendipity outcomes, and release and
capture decisions. Provenance findings include plain-language explanations,
the review path, and whether the candidate was corrected or withheld.
**Copy trace query** copies a Logfire filter for the server-generated trace ID.
The local diagnostics can contain request content. Progress events and
operational telemetry contain metadata only.

## Saved evaluations

**Open a saved evaluation** displays recorded synthetic runs in the analysis
panel. Select a scenario, a run, and a Scene to inspect the fixed reader
message, seeded memories, recorded route, answer-key expectations, objective
results, and recorded reply. Run choices carry their model and build details.
**Back to chat** returns to the live map.

Playback reads the generated
[`evaluations.json`](../../packages/architecture-map/src/evaluations.json)
snapshot. It neither starts an evaluation nor calls a model. The separate
[evaluation explorer](../evaluation-explorer/README.md) explains expected
architecture and documents the shared snapshot commands.

## Library

**Library** opens the Reader drawer. Reader loads enabled books from the
backend's book registry and exact revision grants, then fetches canonical text
by chapter or named section. It reveals a summary only after an explicit
spoiler warning and hides that summary when you select another location.
Contents group units by part, and books open at the first main narrative
chapter.

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

The browser creates one UUID-backed session per page load. Reloading starts a
fresh session. **New chat** clears the previous backend session, local
conversation, turn records, and progress before creating a new session ID.
Account-scoped memories persist across sessions. If a chat request fails, the
frontend removes its pending reader message and reply placeholder from the
local conversation.

Book identity and progress come from the reader's chat messages and validated
backend context. An active book can resolve an indirect book follow-up without
establishing completed reading progress. When identity or progress remains
unresolved, chat displays the application's reviewed clarification question.
A book the reader names or confirms stays active when a routing tool cannot
resolve a later question. Naming a different book clears the old selection,
including when the new title is unavailable. A completed chapter declaration
can advance the active book without repeating its title.

When the reader asks about their own earlier reflections or preferences, Muse
can ask Serendipity to recall authorized memories without a book or web access.
One matching record is enough. The reply attributes recalled material to the
reader, and a missing match does not invent a memory or count as a search
failure.

For backend setup, API behavior, and configuration, see
[`../README.md`](../README.md).
