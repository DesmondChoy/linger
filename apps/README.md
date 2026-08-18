# Linger chat prototype

A minimal chat app: React frontend, FastAPI backend, and a PydanticAI agent on
Google, OpenAI, or Anthropic. No authentication, no database — sessions live in
the backend process and are lost on restart.

## Setup

From the repository root:

```bash
cp .env.example .env
# In .env, choose LINGER_MODEL and set its provider-specific API key.
uv sync
pnpm install --dir apps/frontend
```

### Providers

- Google: `google:gemini-2.5-flash` with `GOOGLE_API_KEY`.
- OpenAI: `openai:gpt-5` with `OPENAI_API_KEY`.
- Anthropic: `anthropic:claude-sonnet-4-5` with `ANTHROPIC_API_KEY`.

Only the key for the selected provider is required.

## Running

Two terminals, both from the repository root:

```bash
# Terminal 1 — API on http://127.0.0.1:8000
uv run uvicorn apps.backend.main:app --reload

# Terminal 2 — UI on http://localhost:5173
pnpm --dir apps/frontend dev
```

Open <http://localhost:5173>. The Vite dev server proxies `/api` to the
backend, so the browser sees one origin and CORS never applies in development.

Interactive API docs: <http://127.0.0.1:8000/docs>.

## API

| Method | Path                       | Purpose                            |
| ------ | -------------------------- | ---------------------------------- |
| GET    | `/api/health`              | Liveness plus the configured model |
| POST   | `/api/chat`                | Reviewed reply plus capture outcome |
| DELETE | `/api/sessions/{id}`       | Drop a conversation's history      |

## Layout

```text
apps/
├── backend/
│   ├── main.py       # FastAPI app, CORS, routes
│   ├── config.py     # settings from the root .env
│   ├── schemas.py    # request/response bodies
│   └── sessions.py   # in-memory conversation history
└── frontend/
    └── src/
        ├── api.ts            # the single fetch call
        ├── types.ts
        └── components/       # Chat, MessageList, Composer
```

## Notes

- The frontend mints a `session_id` with `crypto.randomUUID()` per page load.
  Reloading, or pressing "New chat", starts a fresh conversation.
- Replies are returned whole only after an isolated Provenance call approves
  the complete Muse candidate. Rejected or failed reviews return an
  application-authored safe decline instead.
- Vite 8 wants Node 20.19+ or 22.12+. It runs on 20.18 but prints a warning;
  `nvm install 22` clears it.
