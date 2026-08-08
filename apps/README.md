# Linger chat prototype

A minimal chat app: React frontend, FastAPI backend, PydanticAI agent on Gemini.
No authentication, no database — sessions live in the backend process and are
lost on restart.

## Setup

From the repository root:

```bash
# Update the .env with your model provider + API key accordingly. 
# Check `src/linger/agents/build.py` to update providers supported.

cp .env.example .env       
uv sync
pnpm install --dir apps/frontend
```

### Providers

- Gemini: Get a Gemini key at <https://aistudio.google.com/apikey>.

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
| POST   | `/api/chat`                | `{session_id, message}` → `{reply}` |
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
- Replies are returned whole rather than streamed. Streaming is a contained
  change: `agent.run_stream()` behind an SSE endpoint, plus one frontend
  function.
- Vite 8 wants Node 20.19+ or 22.12+. It runs on 20.18 but prints a warning;
  `nvm install 22` clears it.
