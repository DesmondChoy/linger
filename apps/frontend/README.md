# Linger frontend

This React and TypeScript app is a local development harness. Chat represents
the product-facing path. Reader and Inspect are developer-only tools for corpus
interaction and backend debugging; a user-facing frontend should omit both.

- Chat sends session-scoped reflection turns and displays released replies,
  capture notices, and trace-correlated errors.
- Reader lets developers browse enabled canonical books by chapter or named section and
  exercise corpus behavior. It loads the shelf from the backend's book registry
  and exact revision grants, with local canonical text and an expandable panel.
  It reveals a summary only after an explicit spoiler warning and hides the
  summary when the developer selects another location. Contents group units by
  part, and books open at the first main narrative chapter.
- Inspect lets developers trace request contracts, context resolution, agent
  hand-offs, direct Librarian calls, fixed Serendipity outcomes, and actual
  release decisions for completed turns. Its raw diagnostics are not intended
  for end users.

Reader navigation and Inspect output are deliberately non-authoritative.
Selecting or revealing a location does not establish a spoiler ceiling for chat,
and diagnostic output cannot grant retrieval, release, capture, or storage
authority. The backend accepts only the request-scoped reading context described
in the system specification.

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

The browser creates one UUID-backed session per page load. Reloading or choosing
**New chat** starts a fresh session. A failed chat request is removed from the
local timeline because the backend commits no conversation turn on failure.

Book identity and progress come from the reader's chat messages and validated
backend context. An active book can resolve an indirect book follow-up without
establishing completed reading progress. When identity or progress remains
unresolved, chat displays the application's reviewed clarification question.

For backend setup, API behavior, and configuration, see
[`../README.md`](../README.md).
