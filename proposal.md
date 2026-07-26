# Project Proposal — Linger: A Personal Reading Memory Companion

**Graduate Certificate in Architecting AI Systems — Practice Module**
**Team:** _Team X (TBD)_ · **Date:** 2026-07-26 · **Status:** Draft v0.1

---

## 1. Project Title

**Linger** — a multi-agent reading memory companion that helps a reader articulate why part of a book mattered, preserves that reflection with cited textual evidence, and later proposes grounded, tentative connections between saved memories and the songs, photos, and other books the reader brings to it.

## 2. Project Sponsor

Not applicable (self-sourced project idea).

## 3. Project Members

| Member | Name | Agent / component owned |
|---|---|---|
| 1 | _Member 1 (placeholder)_ | **Muse** — reading-companion agent |
| 2 | _Member 2 (placeholder)_ | **Librarian** — retrieval-and-citations agent |
| 3 | _Member 3 (placeholder)_ | **Scribe** — memory-curator agent |
| 4 | _Member 4 (placeholder)_ | **Serendipity** — connection agent |
| 5 | _Member 5 (placeholder)_ | **Provenance** — verifier agent |

Shared platform work (memory/policy service, CI/CD, evaluation harness, UI) is distributed across all members alongside their agent ownership.

## 4. Overview

Readers rarely leave a book with only a star rating. They retain fragments — a quotation, a character, a question, a personal interpretation — and today's reading platforms discard them, offering only ratings and "next book" recommendations. There is no tool that helps a reader capture *why* a passage mattered and later rediscover that meaning through the music and media in their life.

Linger addresses this gap. A reader selects a book from a small curated Project Gutenberg corpus (75,000+ public-domain eBooks) and discusses it with **Muse**, a reading-companion agent that retrieves cited passages and helps the reader draft a structured "reading memory." Nothing is stored without explicit confirmation. Later, the reader brings a new stimulus — a song (title, artist, optional personal note), an uploaded photo, or another book — and the system proposes an explicitly tentative connection to a saved memory — grounded in cited evidence, verified by an independent agent, and always dismissible or deletable. Serendipity is deliberately user-initiated: the reader supplies the stimulus; Linger never resurfaces personal content unprompted.

The problem is a natural fit for an agentic architecture because the workflow demands distinct competencies with real autonomy: conversational reflection, evidence retrieval with citations, memory lifecycle management, cross-media connection-making that may responsibly *decline* to answer, and independent verification. It also concentrates the risks the certificate's four modules address: hallucinated quotations (explainability/grounding), personal memories as sensitive data (responsible AI), retrieved book text as an untrusted injection surface (AI security), and a multi-agent pipeline that must be reproducible and testable (integration/deployment).

## 5. General Flow

```
Reader ──────► Muse ──► Librarian ──► Gutenberg corpus (cited passages)
                │
                ▼
             Scribe ──► drafts structured memory
                │
                │   reader edits / confirms / rejects
                ▼
         Memory & Policy Service (deterministic: confirmation, isolation, deletion)
                │
                │   reader supplies a stimulus
                │   (song, photo, or another book)
                ▼
         Serendipity ──► searches authorised memories ──► proposes tentative
                │      ▲                                  link (or declines)
                │      │
                │      │   inner loop: rejection returns to
                │      │   Serendipity with a structured
                │      │   critique (bounded retries)
                ▼      │
          Provenance ──┘
                │
                │   accepted / revised
                ▼
         Result shown to reader (save, dismiss, or delete)
                │
                ▼
         Scrubbed feedback telemetry
         (draft edits, saves, dismissals, rejection reasons)
                │
                ▼
         Outer loop: versioned prompt / exemplar updates,
         CI-gated, fed back into the agents above
```

1. The reader selects one of 3–5 curated Gutenberg books and discusses it with **Muse** (reading companion), which decides when to request evidence.
2. The **Librarian** plans and executes retrieval over the corpus, returning passages with stable citations, or reporting that evidence is insufficient.
3. **Scribe** (memory curator) drafts a structured memory (quotation, reader statement, generated interpretation — clearly separated) and runs the edit/confirm/reject loop. Only confirmed memories reach the **Memory & Policy Service**, which deterministically enforces user isolation, permissions, and deletion.
4. Later, the reader feeds Linger a new stimulus through a common interface: a song (title, artist, optional note — no audio or lyrics), an uploaded photo, or another book or saved memory. **Serendipity** (connection agent) first characterises the stimulus, plans an evidence-gathering strategy suited to its type, searches only authorised memory summaries and passages, then proposes a grounded, explicitly tentative connection — or returns "no responsible connection found."
5. **Provenance** (verifier) independently checks quotations against source text, evidence sufficiency, privacy scope, and interpretive overreach before anything is shown. A rejection loops back to Serendipity with a structured critique for revision (bounded retries). The reader may save, dismiss, or delete the result and the underlying memory.
6. **Improvement loop:** reader actions — edits to memory drafts, saved vs. dismissed connections, Provenance's rejection reasons — are captured as scrubbed telemetry (never raw memory content). The team aggregates these signals into versioned prompt and exemplar updates that must pass the CI evaluation suite before deployment, so the system measurably improves from human feedback within set boundaries.

Orchestration follows a graph-based **plan → act → check → refine** pattern: agents coordinate through typed tool contracts and structured inputs/outputs, each agent can respond to incomplete evidence or decline, and the policy service is application code, not an agent, so security guarantees never depend on model instructions.

## 6. Scope of Work

### 6.1 Agents

| Agent | Responsibility and autonomy | Why an agent, not a single LLM call |
|---|---|---|
| **Muse** (reading companion) | Conducts the reflection dialogue; chooses when to retrieve evidence, which follow-up questions to ask, and when to hand off to Scribe. Handles uncertainty and incomplete answers. | Maintains conversation state across turns and plans each next action: retrieve evidence, ask a follow-up, probe an ambiguous answer, or hand off. Invokes the Librarian as a tool and adapts when retrieved passages contradict the reader's recollection. |
| **Librarian** (retrieval & citations) | Plans multi-step retrieval over the ingested corpus (query reformulation, passage selection); returns stable citations; flags insufficient or conflicting evidence rather than guessing. | Runs an iterative search loop — query, assess relevance, reformulate, re-query — rather than one-shot vector lookup. Decides when evidence suffices, when to widen or narrow the search, and when to report failure instead of returning weak matches. |
| **Scribe** (memory curator) | Converts conversation into a structured memory draft with clear source attribution (quotation vs. user statement vs. generated interpretation); manages the confirmation loop and memory summaries used downstream. | Executes a draft → present → incorporate-edits → re-draft cycle with the reader, tracking what changed between revisions. Calls verification tools to attribute each fragment to its source, and only invokes the policy service's storage tool after explicit confirmation. |
| **Serendipity** (connection agent) | Given a user-supplied stimulus — a song (metadata only), an uploaded photo, or another book or saved memory — selects relevant authorised memories, weighs evidence, and proposes an explicitly tentative link — or declines. Never accesses unconfirmed or deleted content. | Must first characterise an open-ended stimulus, then plan a different evidence-gathering strategy per type (song metadata and the reader's note; image content via multimodal understanding; cross-book thematic search): which memory summaries to request, which passages to re-fetch for grounding, whether the evidence clears the bar. Revises against Provenance's critiques (bounded retries) and can conclude that no responsible connection exists. |
| **Provenance** (verifier) | Independent gate: verifies quotations against source, checks privacy boundaries, detects prompt injection carried in retrieved text, and rejects unsupported sensitive inferences. | Independently re-derives evidence using its own tool calls (quote lookup against source text, policy-scope checks) rather than trusting upstream claims. Chooses which checks a given proposal warrants, and decides between accept, revise-with-critique, and reject — a judgement loop, not a classifier. |

### 6.2 How the implementation demonstrates key considerations

| Consideration | Implementation |
|---|---|
| **Explainability & trust** | Every claim carries inspectable citations; quotations, user statements, and generated interpretations are visually and structurally separated; connections are presented as hypotheses with visible uncertainty; workflow tracing records why each step happened. |
| **Responsible AI & governance** | Explicit confirmation before any storage; explicit consent before any analysis of an uploaded photo; user-controlled correction and deletion; data minimisation (agents receive only task-relevant context); no inference of sensitive traits (health, religion, sexuality, ethnicity, politics) — a risk photos particularly invite; documented corpus limitations; alignment with IMDA Model AI Governance Framework in the final report. |
| **Security** | Retrieved book text, uploaded images, and media notes treated as untrusted input; deterministic policy service enforces isolation, permissions, and deletion in code; AI security risk register covering prompt injection (including instructions embedded in uploaded photos), fabricated quotations, forbidden memory requests, log leakage, and deleted-data retrieval — each with automated adversarial test cases. |
| **Agent autonomy & orchestration** | Graph-based orchestration implementing plan → act → check → refine: agents select tools, respond to incomplete evidence, decline unsafe actions, and coordinate through typed contracts. The same evaluation cases run against a single-agent baseline to justify (or remove) each agent boundary. |
| **Self-improvement loop** | Inner loop: Provenance's rejections return structured critiques for bounded revision. Outer loop: scrubbed feedback telemetry (draft edits, saves/dismissals, rejection reasons) drives versioned prompt/exemplar updates, each gated by the CI evaluation suite — controlled improvement from human feedback, never silent behaviour drift. |
| **MLOps / LLMSecOps** | Versioned prompts, corpus builds, tool contracts, and policies; automated contract, retrieval, security, and end-to-end tests in CI/CD; cost and latency measurement; logs scrubbed of raw personal memories. The system is deployed to a reproducible test environment so user isolation, prompt-injection defences, forbidden memory requests, and deletion are exercised against a running system, not just unit tests. |

**Proposed stack (subject to team confirmation):** Python, LangGraph for orchestration, a hosted LLM API, FastAPI backend, lightweight web UI, Docker, GitHub Actions CI/CD.

### 6.3 In scope / stretch / out of scope

- **In scope:** 3–5 Gutenberg books ingested with metadata; cited retrieval; reading-memory conversation with confirmation; a common stimulus interface supporting song-to-memory (song metadata only — no audio or lyrics, for copyright reasons), photo-to-memory (user-uploaded or synthetic images), and cross-book/memory-to-memory connections; verification gate; deletion; adversarial security cases including image-borne injection; single-agent baseline comparison; simple web UI; CI/CD and test deployment.
- **Stretch:** reading-soundtrack (memory-to-song) direction; comparing a revisited pairing with the earlier confirmed reflection.
- **Out of scope:** live music/photo/social integrations; full Gutenberg catalogue; copyrighted books or lyrics; production scale or compliance claims; mental-health profiling.

## 7. Effort Estimates

A **work breakdown structure (WBS)** decomposes the total project into discrete work packages that can be estimated, assigned, and tracked independently. The table below lists Linger's top-level work packages with rough estimates in person-days; each will be broken into finer tasks at kick-off, and actual effort will be tracked against these estimates in the fortnightly progress reports.

Guideline: 5 members × 15 person-days ≈ **75 person-days**.

| # | WBS work package | Est. (person-days) |
|---|---|---|
| 1 | Corpus ingestion, chunking, citation scheme (3–5 Gutenberg books) | 5 |
| 2 | Memory & policy service (confirmation, isolation, deletion) + data model | 7 |
| 3 | Muse — reading-companion agent (dialogue, follow-ups, retrieval decisions) | 7 |
| 4 | Librarian — retrieval agent (search planning, citations, insufficiency handling) | 7 |
| 5 | Scribe — memory-curator agent (structured drafts, source attribution, confirmation loop) | 7 |
| 6 | Serendipity — connection agent (stimulus interface: song / photo / cross-book; decline behaviour; revision loop) | 7 |
| 7 | Provenance — verifier agent (quote checking, privacy/injection/overreach gates, critiques) | 7 |
| 8 | Feedback telemetry & improvement loop (scrubbed signals, prompt versioning) | 3 |
| 9 | Security test suite & AI risk register (text and image-borne injection, fabrication, deletion) | 7 |
| 10 | Evaluation harness incl. single-agent baseline comparison | 6 |
| 11 | Web UI for end-to-end demo | 5 |
| 12 | CI/CD, tracing, cost/latency measurement, test deployment | 5 |
| 13 | Reports, architecture documentation, presentation | 2 |
| | **Total** | **75** |

Effort will be tracked and reported in fortnightly progress reports per the module schedule (proposal due 31 Jul 26; project conduct 10 Aug – 9 Oct 26; presentations from 12 Oct 26; final reports 30 Oct 26).
