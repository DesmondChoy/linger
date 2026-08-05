# Linger: System Specification

Status: **Draft implementation specification**

This document is the canonical source for product scope, architecture, implementation rules, and acceptance criteria. The submitted project proposal remains available as an immutable PDF under `docs/submissions/`.

## 1. Purpose and positioning

Linger is an academic prototype of a personal reflection and memory companion, grounded initially in a small literary corpus. It helps a user articulate why an idea or experience mattered, preserve it as a structured memory, and later explore grounded, tentative connections across conversations, books, photographs, and evidence found through general web search.

General-purpose AI agents already offer memory, image understanding, web search, and delegated tasks. Linger is not trying to be another general personal agent. It is a purpose-built reflection and memory application: a **provenance-first reflection companion** that keeps the user's words, source evidence, and generated interpretation distinct. Before any Muse-generated response reaches the user, a separate Provenance invocation semantically reviews the complete draft for quotations, factual claims, sensitive inferences, attribution, privacy, spoiler, and prompt-injection risks. Application code then performs deterministic checks where applicable. A non-factual reflection may pass without retrieval, but never without review.

[Project Gutenberg](https://www.gutenberg.org/) supplies the initial corpus of 3–5 deliberately selected public-domain books. The prototype records source metadata and discloses that this small, older corpus may contain dated cultural perspectives.

## 2. Product hypothesis and journey

Linger tests whether a reflection companion becomes more useful and trustworthy when it can:

1. help the user articulate why a fragment mattered;
2. preserve that reflection with inspectable provenance;
3. retrieve exact supporting passages without crossing a spoiler boundary; and
4. reconnect the reflection to later experiences without inventing meaning or becoming intrusive.

The core journey is:

| Stage | Required behaviour |
|---|---|
| **Reflect** | Muse drafts responses to text or a photograph and asks a small number of useful follow-up questions. Provenance reviews every complete draft before display, including drafts with no declared factual claims. |
| **Ground** | Librarian retrieves authorised book passages and memories. Muse drafts a response separating quotations, user statements, and generated interpretation; Provenance checks the complete draft and its claimed support. |
| **Preserve** | After explicit onboarding opt-in, Sculptor captures and organises useful memories automatically. Each save is disclosed with immediate undo; the user may pause, review, correct, or delete memories. |
| **Reconnect** | Muse may ask Serendipity to explore a cue across memories, books, photographs, and general web evidence. Muse drafts the tentative connection, and Provenance reviews the whole reply and its evidence before release. |

Automatic capture does not require per-memory approval once enabled. Content about sensitive traits is excluded from automatic capture and may be saved only through an explicit user action.

## 3. Prototype scope

### 3.1 In scope

- ongoing Muse conversations using text and user-supplied photographs, with semantic Provenance review of every candidate response;
- cited retrieval across 3–5 Project Gutenberg books and structured memories;
- keyword, semantic, hybrid, fusion, and reranked retrieval strategies;
- request-specific spoiler filtering and deterministic quotation validation;
- opt-in automatic memory capture with notice, undo, pause, review, correction, and cascading deletion;
- original memories, generated summaries, duplicate links, topic groups, and progressive disclosure;
- conversation- or photograph-triggered connections using internal evidence and optional general web search;
- a mandatory, context-restricted output gate, deterministic post-checks, one bounded revision, and an application-authored safe decline;
- a simple web interface, multiple test accounts, CI/CD, and reproducible test deployment;
- adversarial, output-gate, reflection, retrieval, memory-quality, connection-quality, cost, and latency evaluation.

### 3.2 Stretch

- voice-note transcription, including audio-borne prompt-injection tests;
- cross-book, memory-to-memory, and song-to-memory connections;
- comparison of a revisited pairing with an earlier reflection; and
- a synthetic exercise of an opt-in feedback pipeline.

### 3.3 Out of scope

- persistent reading-progress tracking;
- live music, photo-library, messaging, or social integrations;
- the full Project Gutenberg catalogue;
- copyrighted books, lyrics, or copyrighted-audio analysis without permission;
- general shell, browser-control, or external-action capabilities;
- continuous monitoring or unsolicited resurfacing;
- mental-health profiling, diagnosis, or crisis-resource routing;
- autonomous prompt or skill self-modification;
- production scale, availability, compliance, or regulatory claims; and
- any claim that prototype telemetry measurably improved the system.

## 4. Architecture and authority

The system contains five reasoning agents and one deterministic service:

| Component | Responsibility | Write authority |
|---|---|---|
| **Muse** | Maintains the reflection conversation, handles photographs and spoiler uncertainty, routes work, and produces candidate responses that cannot be sent directly to the user. | None |
| **Librarian** | Plans, executes, fuses, and reranks retrieval across the corpus and authorised memories. | None |
| **Sculptor** | Proposes structured memories, summaries, duplicate links, groups, and derived-record updates while preserving originals. | May request memory writes |
| **Serendipity** | Searches internal and optional web evidence and proposes or declines tentative connections. | None |
| **Provenance** | Semantically reviews every complete Muse candidate response and passes, requests one revision, or rejects it based on evidence, attribution, privacy, spoiler, sensitive-inference, and injection checks. | None |
| **Memory & Policy Service** | Authenticates account scope and deterministically enforces access, storage, versioning, review, and cascading deletion. | Commits validated writes |

The Memory & Policy Service derives account identity from authenticated request context and never accepts it from model output; agents cannot choose or widen account scope. User review, correction, and deletion actions go directly from the web interface to the service and are not mediated by a model.

Agents are logical roles, not necessarily separate models or processes. Muse handles the main interaction; Librarian, Sculptor, and Serendipity are invoked only when their specialised work is needed; Provenance runs for every Muse candidate response.

The five roles separate conversation, retrieval, memory curation, connection generation, and independent verification. Scoped hand-offs keep each invocation within a bounded task context; deterministic application code enforces access, writes, and output release.

Each hand-off carries only the candidate response, claims, evidence identifiers, confidence, and policy flags required by the next step. Full transcripts and unrestricted working context are not passed between agents.

Provenance is a separate, context-isolated model invocation. It receives the complete candidate response, cited evidence, and applicable policy constraints, but neither unrestricted agent working context nor write tools. It independently detects quotations, factual claims, and sensitive inferences instead of trusting Muse's declarations. This provides separation of duties, not model independence, because the same underlying model may be used.

### 4.1 Output release contract

Every Muse invocation returns a typed candidate containing the complete response text plus its declared claims, quotations, evidence identifiers, and sensitive-inference flags. Those fields assist review but do not authorise release: Provenance examines the entire draft and may identify items Muse omitted or misclassified. Regular expressions and structural checks may provide defence in depth, but they are not the semantic security boundary.

Provenance returns `pass`, `revise`, or `reject`. After a semantic pass, application code validates exact quotations, citation locations, account scope, and spoiler constraints where applicable. Only approved output is displayed. A first `revise` verdict gives Muse one bounded revision that returns through the same review path; a rejection or failed revision produces an application-authored safe decline.

### 4.2 End-to-end flows

#### 4.2.1 Reflection and grounding

Muse asks Librarian for evidence only when grounding is needed, but every path produces a candidate response for Provenance review. There is no Muse-to-user bypass.

![Reflection and grounding flow](images/reflection-and-grounding.png)

#### 4.2.2 Opt-in memory capture and control

Sculptor may propose a memory change, but the Memory & Policy Service owns access control and every write. The application-generated save notice reports the committed operation; it is not an unreviewed Muse response or a model-generated paraphrase.

![Opt-in memory capture and control flow](images/opt-in-memory-capture-and-control.png)

#### 4.2.3 Connection discovery and verification

Serendipity supplies a proposed connection and evidence identifiers to Muse. Muse drafts the user-facing reply, which uses the same mandatory Provenance gate and deterministic checks as an ordinary reflection.

![Connection discovery and verification flow](images/connection-discovery-and-verification.png)

## 5. Core records

### 5.1 Session state

Working context contains only:

- server-supplied `account_id`;
- `memory_capture_enabled`;
- the current `spoiler_boundary`;
- the active topic; and
- a compact conversation summary.

The complete memory archive is never injected into every prompt.

### 5.2 Memory record

An active memory is owned by the requesting account and not deleted. It may have been captured automatically while memory capture was enabled or saved explicitly by the user.

Each active memory contains:

- stable `memory_id` and server-supplied `account_id`;
- the user's original words;
- cited source-evidence identifiers, when applicable;
- a generated summary stored separately from the original;
- provenance linking the originating conversation or photograph;
- links to related, duplicate, or parent memories;
- an idempotency key derived from account, source event, and capture type;
- version and derivation metadata for generated records;
- created and updated timestamps; and
- active or deleted status.

Original user records are immutable. A user correction creates a linked active version while preserving the prior record for provenance. Sculptor may add or replace versioned derived summaries and links but cannot delete an original. User deletion cascades through all versions, derived summaries, links, embeddings, indexes, and application traces controlled by Linger.

### 5.3 Evidence record

Every retrieved item carries:

- stable evidence identifier;
- source type and source location;
- owner or account scope where applicable;
- trust level and verification state;
- spoiler position for book evidence; and
- the minimum excerpt required for the current task.

### 5.4 Muse candidate response

Every candidate response contains:

- the complete proposed user-facing text;
- declared claims and quotations;
- cited evidence identifiers;
- sensitive-inference and policy flags; and
- revision metadata, when applicable.

Muse's declarations are untrusted review hints. They do not narrow what Provenance must inspect or what application code must validate.

### 5.5 Connection proposal

A connection proposal contains:

- a tentative claim;
- cited evidence identifiers;
- an explanation that distinguishes evidence from interpretation;
- uncertainty and policy flags; and
- Provenance's decision and structured critique, if any.

## 6. Safeguards

### 6.1 Spoilers

At the start of each book-related session, the user states their position in the book. If unstated, Muse assumes no content beyond the opening and asks for the current chapter before Librarian retrieves unfinished text.

### 6.2 Citations and attribution

Whenever an exact quotation is displayed or stored, application code verifies its text, source, and location against the corpus. Muse separates evidence from interpretation; Provenance reviews every complete draft for undeclared or mislabelled quotations and factual claims and checks their semantic support.

### 6.3 Memory and media control

- Automatic capture requires explicit onboarding opt-in.
- Every capture produces a visible notice and immediate undo.
- Before a long opted-in conversation is compacted or closed, one bounded Sculptor pass checks for an important uncaptured reflection under the same notice, undo, and sensitive-content rules.
- Raw photographs remain transient unless the user explicitly saves them.
- Derived memories from photographs may be captured only while opt-in remains active.
- Sensitive-trait content is never captured automatically.
- Logs and general telemetry exclude raw personal memories.

### 6.4 Untrusted content and privacy

Book text, web results, photographs, media descriptions, and candidate model responses are untrusted input. Private memory text is never copied verbatim into a web-search query. Evidence supplied to each agent is minimised, account-scoped, and labelled by trust level. Prompt instructions contained in evidence never gain tool authority.

### 6.5 Verification

Every Muse candidate requires a recorded approving Provenance verdict before release. Provenance may pass, reject, or request one revision. A candidate is not released when:

- cited evidence is missing or unresolved;
- attribution is incorrect;
- the spoiler boundary is unclear;
- evidence crosses account or deletion boundaries;
- a factual web claim lacks a retrievable citation;
- the candidate contains an unsupported claim or sensitive inference;
- retrieved content attempts to redirect agent behaviour.

Rejected and superseded drafts are never displayed. Deterministic validation runs after semantic approval and fails closed to the application-authored safe decline.

### 6.6 Emotional content

Muse is a reflection companion, not a wellbeing tool. It does not diagnose or label mental state and stops reflective probing after a distressing disclosure. It uses a fixed boundary response encouraging appropriate human support; crisis assessment and resource routing remain out of scope.

## 7. Evaluation and acceptance

### 7.1 Retrieval and memory quality

- Citation-labelled book and memory queries compare keyword, semantic, hybrid, and reranked retrieval using Recall@5 and nDCG@5.
- The same set tests whether Librarian's strategy selection improves relevance or latency over the strongest fixed strategy.
- Seeded duplicate and noisy memories test Sculptor's linking and grouping precision and their effect on Recall@5 and nDCG@5.
- Every derived record must resolve to its originals, and Sculptor must never delete an original.

### 7.2 Fixed evaluation set

Before implementation, the repository will contain 40 versioned JSON or YAML cases. Each case has one primary behaviour and records its inputs, expected outputs or evidence identifiers, and forbidden outputs as applicable:

- 15 safety or adversarial cases;
- 5 reflection cases;
- 5 memory-capture cases;
- 10 expected-connection cases; and
- 5 weak-evidence cases.

Shared deterministic checks validate citations, evidence identifiers, disclosure boundaries, and Provenance verdict coverage across the set. The harness reports reflection-action accuracy; semantic detection recall for quotations, factual claims, and sensitive inferences; unsupported-claim block rate; non-factual pass rate; memory-capture precision and recall; target-connection hit rate; evidence recall; citation precision; exact-quotation accuracy; weak-evidence decline rate; latency; and cost.

Required outcomes:

- at least 80% reflection-action accuracy;
- at least 80% memory-capture precision and recall;
- at least 80% target-connection hits;
- at least 90% evidence recall;
- at least 95% citation precision;
- at least 95% semantic detection recall for seeded quotations, factual claims, and sensitive inferences;
- 100% exact-quotation accuracy;
- 100% Provenance verdict coverage for user-visible Muse responses;
- 100% suppression of rejected and superseded drafts;
- at least 80% weak-evidence declines;
- no cross-account, deleted, or post-boundary disclosure;
- all seeded text-, web-, and image-borne injections blocked or safely ignored;
- no automatic capture of sensitive-trait content; and
- clarification whenever the spoiler boundary is ambiguous.

Every factual web claim must include a retrievable citation, and every evidence identifier must resolve. Any LLM-as-judge result is secondary and labelled non-independent.

### 7.3 Deployment checks

The test deployment supports multiple accounts and up to five concurrent sessions. A basic load test reports success rate, p95 latency, and per-session model cost.

## 8. Operations and change control

The stack decision remains open between TypeScript with Pi Agent Core and Python with PydanticAI core and FastAPI. OpenAI model calls use the Responses API so reasoning can be retained across tool calls and long-running conversations can be compacted. Agent contexts remain separate and bounded; API conversation state is working context, not durable product memory. The remaining stack is a lightweight web UI, Docker, and GitHub Actions.

Prompts, corpus builds, policies, tool contracts, schemas, and evaluation cases are versioned. Fast mocked contract tests run in CI, while live-model evaluations separately measure output-gate recall, quality, cost, and latency. Prompt changes remain human-reviewed and must pass CI gates. Tracing records Provenance verdicts, decisions, and evidence identifiers without logging raw personal memories. The running test deployment, not only unit tests, is used to exercise rejected-draft suppression, output-gate bypass, account isolation, deletion, spoiler filters, forbidden memory requests, and prompt-injection defences.
