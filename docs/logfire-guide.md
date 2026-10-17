# Using Logfire with Linger: a plain-language guide

Status: **Practical guide.** The rules about what may and may not be recorded
live in [`docs/telemetry.md`](telemetry.md). This document only explains how to
*use* what that contract produces.

Audience: anyone who wants to look at what Linger did, including people who do
not write code.

---

## 1. What Logfire actually is

When Linger answers a reader, a lot happens that nobody sees: it checks whether
the message is emotionally sensitive, drafts a reply, looks things up in a book,
maybe searches the web, reviews its own draft, then decides whether the reply is
safe to release.

**Logfire is the flight recorder for that process.** Every step writes a small
timed entry. Afterwards you open a website and read the recording back — which
steps ran, in what order, how long each took, what each decided, and where
things went wrong.

A few words you will see, in plain terms:

| Word | What it means here |
|---|---|
| **span** | One step, with a start and end time. "Muse wrote a draft" is a span. |
| **trace** | All the spans from one request, nested like a folder tree. One reader message = one trace. |
| **trace ID** | A 32-character code naming one trace, e.g. `4f9c…`. It is how you find a specific turn. |
| **attribute** | A labelled fact attached to a span, like `status = success`. |
| **service** | Which part of Linger produced the recording. **This is the important one — see next section.** |
| **project** | The container in the Logfire website holding all of it. Ours is called `linger`. |

---

## 2. The one thing that explains most confusion

Linger sends recordings to **one Logfire project under two different service
names**, and those two services follow **deliberately opposite privacy rules**.

### `linger-backend` — the real chat interface

This is what runs when you or a reader type into the app.

It records **where and how**, never **what**. It notes "Muse produced a draft,
it succeeded, it took 1.4 seconds." It does **not** record the reader's message,
the instructions sent to the model, the draft, or the final reply.

This is intentional. Real people's journal entries are private, so the privacy
is built into the code rather than trusted to a setting. Automatic
instrumentation — the convenient feature that normally captures prompts and
replies for you — is switched **off** for this service and cannot be switched on
by configuration.

### `linger-evals` — the replay runners

These are offline test runs using **made-up journal entries written by us**, not
real reader content. Because nothing private is involved, these runs record
everything: the full instructions, the model's messages, tool calls, the typed
result, token counts and cost.

### Why this matters to you

> **You cannot see a prompt or a reply by using the chat app.**
> Not because something is broken or misconfigured — because the chat service
> never sends them. To inspect actual wording, you must use a replay run.

This also explains why several panels on the Logfire website look empty. The
**Agents**, **LLMs and providers**, and **Evals** panels are built from
content-bearing recordings, so only replay fills them. Chat traffic shows up
only in **Live** and the trace explorer.

| What you want to know | Where to look |
|---|---|
| Did the turn fail, and at which step? | Chat interface trace |
| How long did it take, what did it cost? | Either |
| Which book, which evidence, which decisions? | Either (as IDs and labels) |
| What exactly did the model read and write? | **Replay only** |
| Comparing quality across runs | **Replay only** (Evals panel) |

---

## 3. One-time setup

You only do this once per computer.

```bash
uv run logfire --region us auth
```

This opens a browser and logs you in. Then point this folder at the project:

```bash
uv run logfire --region us projects use linger
```

Check it worked:

```bash
uv run logfire --region us whoami
```

You should see your username and a project URL. On this machine it currently
reports:

```
Logged in as: jrlyy
Credentials loaded from data dir: .../Linger/.logfire
Logfire project URL: https://logfire-us.pydantic.dev/jrlyy/linger
```

**That URL is the website you open to read recordings.** Bookmark it.

> ⚠️ **Known wrong instruction.** [`README.md`](../README.md) tells you to run
> `projects use --org desmond-choy linger`. That will not work on this machine:
> `uv run logfire projects list` shows the only project this account can write
> to is `jrlyy/linger`. Drop the `--org desmond-choy` part, or pass
> `--org jrlyy`. See [Fix 4](#fix-4-the-readmes-setup-command-fails) below.

You do **not** need a `LOGFIRE_TOKEN` on your own laptop — the login above is
enough. Tokens are for deployed servers and automated CI, which cannot open a
browser.

---

## 4. Using it from the chat interface

### Step 1 — start the two halves of the app

Two terminals, both from the project folder:

```bash
# Terminal 1 — the backend (the thinking part)
uv run uvicorn apps.backend.main:app --reload
```

```bash
# Terminal 2 — the frontend (the part you type into)
pnpm --dir apps/frontend dev
```

Then open the address Terminal 2 prints, normally `http://localhost:5173`.

### Step 2 — send a message and find its trace ID

After Linger replies, open the **Inspector** panel beside the conversation. It
has a section titled **Operational trace** containing a long code and a **Copy
trace query** button.

That code is the trace ID. The button copies a ready-made search line that looks
like this:

```
trace_id = '4f9c2a7b1e8d40f3a6c5b2e1d09f8a3c'
```

The panel also reminds you, correctly, that reader messages and prompts are not
sent to Logfire.

### Step 3 — look it up

Open your project URL, go to **Live**, paste the copied line into the query box,
and run it.

Why this roundabout route? Because no session ID, account ID or turn ID is ever
recorded, **the trace ID is the only link between a conversation you can see and
its recording.** If you do not copy it, that turn becomes effectively
unfindable. Copy it before moving on.

### Step 4 — read the tree

A normal turn looks like this, each line nested under the one above:

```
chat.request                                    ← the web request arriving
  chat.turn                                     ← the whole turn's bookkeeping
    provenance.emotional_boundary  → Provenance run → model call
    muse.draft                     → Muse run       → model call
    provenance.review              → Provenance run → model call
```

Read it top to bottom as the order things happened. The five named agents are
Muse (writes), Provenance (reviews and gatekeeps), Librarian (searches the
registered books), Serendipity (finds connections), and Sculptor (curates
memories). Not every turn uses all of them.

Click a span to see its attributes. The useful ones:

| Attribute | Question it answers |
|---|---|
| `status` | Did this step succeed, decline, or fail? |
| `agent.role`, `agent.stage` | Who was acting, and at which point? |
| `failure.stage`, `failure.code` | Where did it break, and which known failure was it? |
| `failure.type` | Whose fault: `model`, `validation`, or `application`? |
| `failure.retryable` | Would trying again plausibly help? |
| `provenance.response_decision` | Was the reply allowed out? |
| `provenance.finding_codes` | Which specific objections did the reviewer raise? |
| `retrieval.evidence_ids` | Which exact passages were used? |
| `scope.work_id`, `scope.chapter_max` | Which book, and how far in was the reader allowed to see? |
| `serendipity.shortlist_size` | How many candidate connections were compared? |

Notice the shape of these: codes, labels, counts and IDs. Never sentences. That
is the privacy contract showing through. `failure.code` is a fixed code from a
known list rather than an error message, because error messages routinely quote
the content that caused them.

### What "useful" looks like in practice

A reader says Linger refused to answer. With the trace ID you can establish, in
under a minute, that `provenance.emotional_boundary` returned `apply_boundary`
and the trace stopped before Muse ever ran — so a fixed supportive response was
released deliberately, and nothing failed. You learn *that* without ever reading
what the reader wrote.

---

## 5. Using it from replay

"Replay" means: feed made-up journal entries through Linger on purpose and grade
what comes out. Because the input is invented, these runs record full content.

There are **two** replay commands for Serendipity and they are easy to mix up.

### 5a. Component replay — fast, offline, one agent

```bash
uv run python -m evals.serendipity.runner \
  --output evals/serendipity/reports/latest.json
```

- Only **Serendipity** runs for real. Its searching tools are fakes that hand
  back prepared evidence, so there is no internet access and no search
  costs.
- Purpose: test Serendipity's *judgment* in isolation. If it fails, the fault is
  Serendipity's reasoning, not a flaky web search.
- In Logfire: environment `synthetic-component-evaluation`. The **Agents** panel
  shows only **Serendipity run**.
- Needs: `LINGER_MODEL` and the matching provider API key in `.env`.
- `--no-logfire` skips uploading. The run still works and still writes the JSON
  report.

### 5b. Production replay — the "live" one

```bash
uv run python -m evals.serendipity.objective_replay \
  evals/serendipity/objective_cases/cross-source-outside-essay-v1.json \
  --output /tmp/cross-source-production-run.json
```

- Drives made-up messages through **the real chat code**, end to end, with
  **real web searches**, in a throwaway account and memory store that are
  deleted afterwards.
- Purpose: confirm the whole pipeline delivers, not just that one agent thinks
  correctly. All five agents are recorded with full content.
- In Logfire: environment `synthetic-evaluation`.
- Needs, in addition to the model key: `LINGER_WEB_SEARCH_ENABLED=true` and
  `EXA_API_KEY` in `.env`, or the web tools are simply not granted.
- `--output` is required. There is no `--adoption` argument on this command.

### Which one to run

| Situation | Command |
|---|---|
| Changed Serendipity's instructions or logic | **5a** component — faster, cheaper, isolates the cause |
| Asking "does this actually work for a reader?" | **5b** production |
| No `EXA_API_KEY` available | **5a** only |
| Want to compare against previous runs in the Evals panel | Either; both publish experiments |

### Reading a replay in Logfire

Both commands submit their cases through **Pydantic Evals**, so they appear in
the **Evals** panel as an experiment — one row per case, with the input, the
expected output, the actual output, pass/fail labels, and timing. This is the
view for comparing two runs after a change.

To see the actual wording, open a trace and click a span named **Muse run**,
**Serendipity run**, and so on. Its message panel shows the ordered
conversation with the model and the typed result. **Details** or **Raw Data**
shows the underlying technical name and attributes.

The JSON file you passed to `--output` is the authoritative record. Logfire is
the comfortable place to *browse*; the JSON is what you keep, check in, and
compare later. Everything still works with Logfire switched off — you just lose
the browsing.

### One honest caveat on grading

A passing component run means Serendipity made the right local decision under
prepared evidence. It does **not** mean a reader got a good answer. The READMEs
in `evals/` are firm about never adding these up into an overall score, and
`semantic_review_required` staying true means a human still has to read the
output and judge whether it was actually any good.

---

## 6. Fixing it when it looks broken

### Fix 1: "I ran the app but Logfire shows nothing at all"

Almost always missing credentials, and it fails **silently** — this is the
single most common cause of confusion.

The code is configured with `send_to_logfire="if-token-present"` and
`console=False`. In plain terms: *if there are no credentials, send nothing and
say nothing.* No warning, no error, no local printout. An unconfigured Linger
looks exactly like a working one.

Check and repair:

```bash
uv run logfire --region us whoami      # expect a username and project URL
```

If that errors or shows no project, redo [section 3](#3-one-time-setup). Then
**restart the backend** — credentials are read once at startup, so a server
already running will not pick them up.

Also confirm you are reading the project the URL names. Having two Logfire
projects open in different browser tabs and searching the wrong one produces
identical symptoms.

### Fix 2: "The Agents / LLMs / Evals panels are empty"

Working as designed, if you have only used the chat app. Those panels need
content-bearing recordings, which only replay produces. Run a replay from
[section 5](#5-using-it-from-replay) and they fill in.

If they are empty *after* a replay, check in order:

1. Did the run print an output path and finish without an error?
2. Did you pass `--no-logfire`? That disables uploading.
3. Does the time range in the Logfire UI include the run? The default window is
   narrow; widen it.
4. Is the environment filter set? Try `synthetic-evaluation` and
   `synthetic-component-evaluation` — a component run will not appear under the
   production-replay environment.

### Fix 3: "I can't find the prompt / the reader's message / the reply"

If you are looking at a chat-interface trace, stop looking — it is not there and
will not be. Reproduce the situation as a replay case and read it there. This is
the documented route: a real failure produces only a metadata signature, and a
person then writes a made-up case that triggers the same problem.

### Fix 4: "The README's setup command fails"

[`README.md`](../README.md) says:

```bash
uv run logfire --region us projects use --org desmond-choy linger   # ✗ wrong org here
```

This machine's account cannot write to `desmond-choy`. Verify with:

```bash
uv run logfire projects list
```

which currently lists only `jrlyy / linger`. Use instead:

```bash
uv run logfire --region us projects use linger
```

The README line is a genuine bug — it presumably documents a different
contributor's organisation. Worth fixing in the README rather than working
around repeatedly.

### Fix 5: "Replay crashes, or behaves oddly, when the backend is running"

Run replay in **its own terminal, as its own process**. Logfire's configuration
is set once per running program, and the replay commands reconfigure it to the
`linger-evals` service. Starting a replay inside the live backend process would
fight over that single setting.

Two separate terminals is fine and normal. Just do not try to trigger a replay
from inside the running server.

### Fix 6: "My replay trace has a `chat.request` span but the contract says it shouldn't"

You found a real discrepancy, not a mistake of your own.

[`docs/telemetry.md`](telemetry.md) §5.2 states "Direct evaluation replay creates
no request span." That is true of
[`evals/synthetic_journals/replay.py`](../evals/synthetic_journals/replay.py),
which calls the inner `run_chat_turn` function directly.

But [`evals/serendipity/objective_replay.py`](../evals/serendipity/objective_replay.py)
calls the outer web-route function `chat`, which creates a `chat.request` span
on its way through. So its traces really do look like:

```
case
  chat.request
    chat.turn
      ...
  proposal_comparison / adopted_hard_gate_grade
```

Nothing is leaking — `chat.request` only ever holds the route template, the
method, and the response status. But either the document or the runner should
change so they agree. **This is unresolved and has not been fixed.**

### Fix 7: "Web search isn't happening in production replay"

Both of these must be true in `.env`, and they are independent:

```
LINGER_WEB_SEARCH_ENABLED=true
EXA_API_KEY=<your key>
```

A key alone does nothing without the flag, and the flag alone does nothing
without a key. The web tools are not granted unless both are set.

---

## 7. Quick reference

```bash
# Setup, once
uv run logfire --region us auth
uv run logfire --region us projects use linger
uv run logfire --region us whoami          # verify; prints your project URL

# Run the chat app (two terminals)
uv run uvicorn apps.backend.main:app --reload
pnpm --dir apps/frontend dev

# Replay: component, offline, Serendipity only
uv run python -m evals.serendipity.runner \
  --output evals/serendipity/reports/latest.json

# Replay: production, live web, all five agents
uv run python -m evals.serendipity.objective_replay \
  evals/serendipity/objective_cases/cross-source-outside-essay-v1.json \
  --output /tmp/cross-source-production-run.json

# Check the case definitions and graders still pass
uv run pytest tests/test_serendipity_evals.py
```

| Symptom | First thing to check |
|---|---|
| Nothing in Logfire at all | `logfire whoami`, then restart the backend |
| Agents/LLMs/Evals panels empty | You need a replay, not chat traffic |
| No prompts or replies visible | Expected from chat; use replay |
| Setup command rejected | Drop `--org desmond-choy` |
| Can't find a specific turn | Copy its trace ID from the Inspector *before* navigating away |
| No web search during replay | Both `LINGER_WEB_SEARCH_ENABLED` and `EXA_API_KEY` |

---

## 8. Where to read more

- [`docs/telemetry.md`](telemetry.md) — the binding rules on what may be
  recorded. Read this before adding any new recorded field; doing so requires
  changing the contract, the code, and a test together.
- [`README.md`](../README.md) — project setup and the evaluation workflow.
- [`apps/README.md`](../apps/README.md) — backend and frontend configuration.
- [`evals/serendipity/README.md`](../evals/serendipity/README.md) — what the
  Serendipity runs do and, importantly, what they do not prove.
