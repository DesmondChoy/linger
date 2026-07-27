# Project Proposal - Linger: A Personal Reading Memory Companion

**Graduate Certificate in Architecting AI Systems - Practice Module**
**Team:** _Team X (TBD)_ · **Date:** 2026-07-26 · **Status:** Draft v0.1

---

## 1. Project Title

**Linger** - an academic prototype of a broader personal reflection and memory companion, scoped to reading. It helps a reader articulate why part of a book mattered, preserve that reflection with cited textual evidence, and later explore grounded, tentative connections to other books and media.

## 2. Project Sponsor

Not applicable (self-sourced project idea).

## 3. Project Members

| Member | Name | Agent / component owned |
|---|---|---|
| 1 | _Member 1 (placeholder)_ | **Muse** - reading-companion agent |
| 2 | _Member 2 (placeholder)_ | **Librarian** - retrieval-and-citations agent |
| 3 | _Member 3 (placeholder)_ | **Scribe** - memory-curator agent |
| 4 | _Member 4 (placeholder)_ | **Serendipity** - connection agent |
| 5 | _Member 5 (placeholder)_ | **Provenance** - verifier agent |

Shared platform work (memory/policy service, CI/CD, evaluation harness, UI) is distributed across all members alongside their agent ownership.

## 4. Overview

Readers often finish a book with more than a rating or highlight. A passage may raise a question, clarify a feeling, or become meaningful because of something happening in the reader's life. Existing tools can preserve what was highlighted or written, but do little to help readers articulate why it mattered or rediscover that meaning later.

Linger is a personal reflection and memory companion. During or after reading, a reader tells Linger what stayed with them. Linger helps develop the thought, retrieves relevant passages where available, separates source text from personal reflection and generated interpretation, and prepares a structured reading memory for the reader to edit and confirm. When a book is unfinished, Linger establishes a spoiler boundary from what the reader says or from the passage under discussion, asking for clarification when uncertain. Retrieval and discussion stay within that boundary; Linger does not persistently track reading progress. Later, the reader may introduce another book, a song, or a photo, and Linger can suggest a tentative connection to an existing memory. Connections remain user-initiated, evidence-aware, and dismissible; no memory or raw stimulus is stored without explicit confirmation.

The broader concept is not limited to reading: memories could also originate from films, conversations, or other meaningful experiences. To keep this academic project focused and achievable, however, the prototype will capture memories originating only from reading. Source-grounded retrieval and evaluation will use 3–5 public-domain books selected from Project Gutenberg; this is a prototype constraint, not part of the intended user experience.

The workflow benefits from an agentic architecture because it combines distinct responsibilities: reflective dialogue, evidence retrieval, memory curation, connection-making, and independent verification. These responsibilities also provide concrete ways to demonstrate explainability, responsible data handling, AI security, multi-agent orchestration, and reproducible deployment.

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
                │   accepted or returned for revision
                ▼
         Result shown to reader (save, dismiss, or delete)
                │
                ▼
         Opt-in scrubbed feedback telemetry
         (non-content edit, save, dismissal, and rejection signals)
                │
                ▼
         Outer loop: human-reviewed prompt / exemplar updates,
         CI-gated, fed back into the agents above
```

1. During or after reading, the reader tells **Muse** what stayed with them. For an unfinished book, Muse asks where they are in the book or infers a provisional spoiler boundary from the conversation, asking for clarification if confidence is low.
2. The **Librarian** plans and executes retrieval over the 3–5 ingested Gutenberg books, returning passages with stable citations or reporting that evidence is insufficient. It filters retrieval to the request's spoiler boundary; Muse must not discuss later events.
3. **Scribe** (memory curator) drafts a structured memory, clearly separating quotations, the reader's own words, and generated interpretation. The reader may edit, confirm, or reject it. Only confirmed memories are stored through the **Memory & Policy Service**, which deterministically enforces user isolation, permissions, and deletion.
4. Later, the reader supplies a new stimulus through a common interface: a song (title, artist, optional note - no audio or lyrics), an uploaded photo, another supported book, or a saved memory. **Serendipity** (connection agent) characterises the stimulus, searches only authorised memory summaries and passages, and proposes a grounded, explicitly tentative connection - or returns "no responsible connection found."
5. **Provenance** (verifier) independently checks quotations against source text, evidence sufficiency, privacy scope, and interpretive overreach before any proposed connection is shown. A rejection loops back to Serendipity with a structured critique for revision (bounded retries). The reader may save or dismiss the connection and may separately delete it or any underlying memory.
6. **Improvement loop:** if the reader opts in, non-content signals - whether a draft was edited, a connection was saved or dismissed, and Provenance's rejection category - are captured as scrubbed telemetry. The team reviews aggregate signals and updates versioned prompts; exemplars use only synthetic or separately consented, sanitised cases. Every change must pass the CI evaluation suite before deployment.

Orchestration follows a graph-based **plan → act → check → refine** pattern: agents coordinate through typed tool contracts and structured inputs/outputs, each agent can respond to incomplete evidence or decline, and the policy service is application code, not an agent, so security guarantees never depend on model instructions.

## 6. Scope of Work

### 6.1 Agents

| Agent | Responsibility and autonomy | Why an agent, not a single LLM call |
|---|---|---|
| **Muse** (reading companion) | Conducts the reflection dialogue; asks for or infers a request-specific spoiler boundary; chooses when to retrieve evidence, which follow-up questions to ask, and when to hand off to Scribe. It must not reveal events beyond that boundary. | Maintains conversation state across turns and plans each next action: clarify an uncertain boundary, retrieve permitted evidence, ask a follow-up, or hand off. Invokes the Librarian as a tool and adapts when retrieved passages contradict the reader's recollection. |
| **Librarian** (retrieval & citations) | Plans multi-step retrieval over the ingested corpus (query reformulation, passage selection); applies the request's spoiler boundary; returns stable citations; and flags insufficient or conflicting evidence rather than guessing. | Runs an iterative search loop - query, assess relevance, reformulate, re-query - rather than one-shot vector lookup. Decides when permitted evidence suffices, when to reformulate within the boundary, and when to report failure instead of searching later content. |
| **Scribe** (memory curator) | Converts conversation into a structured memory draft with clear source attribution (quotation vs. user statement vs. generated interpretation); manages the confirmation loop and memory summaries used downstream. | Executes a draft → present → incorporate-edits → re-draft cycle with the reader, tracking what changed between revisions. Calls verification tools to attribute each fragment to its source, and only invokes the policy service's storage tool after explicit confirmation. |
| **Serendipity** (connection agent) | Given a user-supplied stimulus - a song (metadata only), an uploaded photo, another supported book, or a saved memory - selects relevant authorised memories, weighs evidence, and proposes an explicitly tentative link - or declines. Never accesses unconfirmed or deleted content. | Must first characterise an open-ended stimulus, then plan a different evidence-gathering strategy per type (song metadata and the reader's note; image content via multimodal understanding; cross-book thematic search): which memory summaries to request, which passages to re-fetch for grounding, whether the evidence clears the bar. Revises against Provenance's critiques (bounded retries) and can conclude that no responsible connection exists. |
| **Provenance** (verifier) | Independent gate: verifies quotations against source, checks privacy boundaries, detects prompt injection carried in retrieved text, and rejects unsupported sensitive inferences. | Independently re-derives evidence using its own tool calls (quote lookup against source text, policy-scope checks) rather than trusting upstream claims. Chooses which checks a given proposal warrants, and decides between accept, revise-with-critique, and reject - a judgement loop, not a classifier. |

### 6.2 How the implementation demonstrates key considerations

| Consideration | Implementation |
|---|---|
| **Explainability & trust** | Book quotations and factual source claims carry inspectable citations; quotations, user statements, and generated interpretations are visually and structurally separated; connections are presented as hypotheses with visible uncertainty; workflow tracing records why each step happened. |
| **Responsible AI & governance** | Explicit confirmation before storing any memory or raw stimulus; opt-in scrubbed telemetry; explicit consent before any analysis of an uploaded photo; user-controlled correction and deletion; data minimisation (agents receive only task-relevant context); no inference of sensitive traits (health, religion, sexuality, ethnicity, politics) - a risk photos particularly invite; documented corpus limitations; alignment with IMDA Model AI Governance Framework in the final report. |
| **Security** | Retrieved book text, uploaded images, and media notes treated as untrusted input; deterministic application code enforces isolation, permissions, deletion, and request-specific spoiler filters; AI security risk register covering prompt injection (including instructions embedded in uploaded photos), fabricated quotations, spoiler leakage, forbidden memory requests, log leakage, and deleted-data retrieval - each with automated adversarial test cases. |
| **Agent autonomy & orchestration** | Graph-based orchestration implementing plan → act → check → refine: agents select tools, respond to incomplete evidence, decline unsafe actions, and coordinate through typed contracts. The same evaluation cases run against a single-agent baseline to justify (or remove) each agent boundary. |
| **Self-improvement loop** | Inner loop: Provenance's rejections return structured critiques for bounded revision. Outer loop: opt-in, non-content telemetry informs human-reviewed prompt updates; exemplars are synthetic or separately consented and sanitised. Each version is gated by the CI evaluation suite - controlled improvement, never silent behaviour drift. |
| **MLOps / LLMSecOps** | Versioned prompts, corpus builds, tool contracts, and policies; automated contract, retrieval, security, and end-to-end tests in CI/CD; cost and latency measurement; logs scrubbed of raw personal memories. The system is deployed to a reproducible test environment so user isolation, prompt-injection defences, forbidden memory requests, and deletion are exercised against a running system, not just unit tests. |

**Proposed stack (subject to team confirmation):** Python, LangGraph for orchestration, a hosted LLM API, FastAPI backend, lightweight web UI, Docker, GitHub Actions CI/CD.

### 6.3 In scope / stretch / out of scope

The following boundaries define what the academic prototype will implement and evaluate; they are not limitations of the broader product concept.

- **In scope:** 3–5 Gutenberg books ingested with metadata; cited retrieval with request-specific spoiler filtering; reading-memory conversation with confirmation; a common stimulus interface supporting song-to-memory (song metadata only - no audio or lyrics, for copyright reasons), photo-to-memory (user-uploaded or synthetic images), and cross-book/memory-to-memory connections; verification gate; deletion; adversarial security cases including image-borne injection; single-agent baseline comparison; simple web UI; CI/CD and test deployment.
- **Stretch:** recommending a song from a reading memory (the reverse of the in-scope song-to-memory flow); comparing a revisited pairing with the earlier confirmed reflection.
- **Out of scope:** persistent reading-progress tracking; memories originating from films, conversations, or other non-reading experiences; live music/photo/social integrations; full Gutenberg catalogue; copyrighted books or lyrics; production scale or compliance claims; mental-health profiling.

### 6.4 Stakeholders, trade-offs, and validation

| Question | Proposal |
|---|---|
| **Stakeholders and value** | Readers are the primary users. The project team operates the prototype and is accountable for its data handling; NUS-ISS lecturers evaluate the project outcomes. The intended value is to reduce the effort of creating evidence-backed reflections and make saved insights easier to rediscover. |
| **Benefits and trade-offs** | Specialised agents improve separation of duties, traceability, and independent verification, but add latency, cost, orchestration complexity, and new failure paths. The single-agent baseline will test whether the added complexity is justified. |
| **Scale** | The prototype targets up to five concurrent reader sessions, not production scale. A basic load test will report success rate, p95 latency, and per-session model cost. |
| **Demo success criteria** | On a fixed evaluation set: all displayed quotations must exactly match their cited source; no unauthorised or deleted memory may be retrieved; all seeded prompt-injection cases must be blocked or safely ignored; and no test with a stated or implied spoiler boundary may retrieve or reveal later content, including when the reader explicitly asks for it. Ambiguous cases must trigger clarification rather than retrieval. A comparison with the single-agent baseline will measure evidence sufficiency, traceability, task completion, latency, and cost. |
| **Lifecycle automation** | CI automatically runs contract, retrieval, security, and end-to-end tests for every versioned prompt, policy, or corpus change, reducing manual regression effort and preventing failed changes from deployment. |

## 7. Effort Estimates

The WBS below lists the top-level work packages and rough estimates in person-days. Each package will be broken into assignable tasks at kick-off, with actual effort tracked in the fortnightly progress reports.

Guideline: 5 members × 15 person-days ≈ **75 person-days**.

| # | WBS work package | Est. (person-days) |
|---|---|---|
| 1 | Corpus ingestion, chunking, citation scheme (3–5 Gutenberg books) | 5 |
| 2 | Memory & policy service (confirmation, isolation, deletion) + data model | 7 |
| 3 | Muse - reading-companion agent (dialogue, follow-ups, retrieval decisions) | 7 |
| 4 | Librarian - retrieval agent (search planning, citations, insufficiency handling) | 7 |
| 5 | Scribe - memory-curator agent (structured drafts, source attribution, confirmation loop) | 7 |
| 6 | Serendipity - connection agent (stimulus interface: song / photo / cross-book; decline behaviour; revision loop) | 7 |
| 7 | Provenance - verifier agent (quote checking, privacy/injection/overreach gates, critiques) | 7 |
| 8 | Feedback telemetry & improvement loop (scrubbed signals, prompt versioning) | 3 |
| 9 | Security test suite & AI risk register (text and image-borne injection, fabrication, deletion) | 7 |
| 10 | Evaluation harness incl. single-agent baseline comparison | 6 |
| 11 | Web UI for end-to-end demo | 5 |
| 12 | CI/CD, tracing, cost/latency measurement, test deployment | 5 |
| 13 | Reports, architecture documentation, presentation | 2 |
| | **Total** | **75** |

Effort will be tracked and reported in fortnightly progress reports per the module schedule (proposal due 31 Jul 26; project conduct 10 Aug – 9 Oct 26; presentations from 12 Oct 26; final reports 30 Oct 26).
