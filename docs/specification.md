# Linger: System Specification

Status: **Draft implementation specification**

This document is the canonical source for product scope, architecture, implementation rules, and acceptance criteria. The submitted project proposal remains available as an immutable PDF under `docs/submissions/`.

Academic, frontier-lab, and expert sources for the final project report are maintained in [Sources for the Final Project Report](report-sources.md).

The architecture and acceptance criteria below describe the target prototype.
Delivery is staged: the current output-release slice uses a typed Muse candidate
containing the complete reply, declared book-corpus evidence uses, and
`MemoryCandidate | NoMemoryCandidate`. Provenance reviews both response and
nomination; application code binds a nomination to an exact source-turn span,
validates book evidence against trusted Librarian results, and lets the
deterministic Memory & Policy Service enforce automatic capture. Serendipity-
only, stored-memory, web, and image evidence are not citation authorities in
this slice and therefore fail closed. Declared claims, richer sensitive-
inference flags, and account-scoped memory retrieval remain later slices.

## 1. Purpose and positioning

Linger is an academic prototype of a personal reflection and memory companion, grounded initially in a small literary corpus. It helps a user articulate why an idea or experience mattered, preserve it as a structured memory, and later explore grounded, tentative connections across conversations, books, photographs, and evidence found through general web search.

General-purpose AI agents already offer memory, image understanding, web search, and delegated tasks. Linger is not trying to be another general personal agent. It is a purpose-built reflection and memory application: a **provenance-first reflection companion** that keeps the user's words, source evidence, and generated interpretation distinct. Before any Muse-generated response reaches the user, Provenance — a separate model call — reviews the complete draft for quotations, factual claims, sensitive inferences, attribution, privacy, spoiler, and prompt-injection risks. Application code then performs deterministic checks where applicable. A non-factual reflection may pass without retrieval, but never without review.

[Project Gutenberg](https://www.gutenberg.org/) supplies the literary corpus. Implementation begins with a one-book corpus containing Lewis Carroll's *Alice's Adventures in Wonderland* (Project Gutenberg ebook 11). Once ingestion, retrieval, spoiler filtering, citation validation, and evaluation work end to end for that book, the corpus expands to the planned total of 3–5 deliberately selected public-domain books. The prototype records source metadata and discloses that this small, older corpus may contain dated cultural perspectives.

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
| **Preserve** | During controlled evaluation, Muse may nominate a useful reflection for automatic capture. Provenance may veto an unsafe candidate, and the deterministic Memory & Policy Service alone validates and commits approved captures. The interactive POC exposes no memory-management drawer or explicit save, correction, or deletion actions. Sculptor may later curate existing memories for retrieval. |
| **Reconnect** | Muse may ask Serendipity to explore a cue across memories, books, photographs, and general web evidence. Muse drafts the tentative connection, and Provenance reviews the whole reply and its evidence before release. |

Automatic capture is disabled by default in the interactive POC. Controlled
evaluation may enable it as server-side workflow state; every capture still
requires a Muse nomination, no Provenance veto, and deterministic policy
approval. Content about sensitive traits is never captured.

## 3. Prototype scope

### 3.1 In scope

- ongoing Muse conversations using text and user-supplied photographs, with semantic Provenance review of every candidate response;
- cited retrieval across the initial *Alice's Adventures in Wonderland* corpus and structured memories, followed by expansion to a total of 3–5 Project Gutenberg books;
- keyword, semantic, hybrid, fusion, and reranked retrieval strategies;
- request-specific spoiler filtering and deterministic quotation validation;
- reviewed automatic memory capture as a controlled evaluation capability, with a visible notice for any committed capture;
- original memories, generated summaries, duplicate links, topic groups, and progressive disclosure;
- conversation- or photograph-triggered connections using internal evidence and optional general web search;
- a mandatory, context-restricted output gate, deterministic post-checks, at most one revision, and an application-authored safe decline;
- a simple web interface, multiple test accounts, CI/CD, and reproducible test deployment;
- adversarial, output-gate, reflection, retrieval, memory-quality, connection-quality, cost, and latency evaluation;
- two bounded recursive self-improvement loops — failure-to-eval promotion and a Sculptor-curated system playbook (Section 9).

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
- end-user memory-management settings and explicit save, review, correction, or deletion controls;
- mental-health profiling, diagnosis, or crisis-resource routing;
- autonomous prompt or skill self-modification — the self-improvement loops in Section 9 produce human-reviewed proposals only and never apply changes themselves;
- production scale, availability, compliance, or regulatory claims; and
- any claim that prototype telemetry measurably improved the system.

## 4. Architecture and authority

The system contains five reasoning agents and one deterministic service:

| Component | Responsibility | Write authority |
|---|---|---|
| **Muse** | Maintains the reflection conversation, handles photographs and spoiler clarification, routes work, and produces candidate responses that cannot be sent directly to the user. Its typed output may also nominate one `MemoryCandidate` for automatic capture or return `NoMemoryCandidate`. | None |
| **Librarian** | Infers request-scoped reading boundaries by cross-referencing authorised memories with the complete corpus, then plans, executes, fuses, and reranks evidence retrieval within the inferred ceiling. | None |
| **Sculptor** | Curates bounded sets of existing memories for retrieval by proposing derived summary or formatting updates, duplicate links, and topic groups while preserving originals. A scheduled Sculptor task, run outside user conversations, also curates the system playbook of operational lessons (Section 9.2). | May propose curation changes and playbook pull requests; no direct writes |
| **Serendipity** | Searches internal and optional web evidence and proposes or declines tentative connections. | None |
| **Provenance** | Semantically reviews every complete Muse candidate response and passes, requests one revision, or rejects it based on evidence, attribution, privacy, spoiler, sensitive-inference, and injection checks. In the same review call, it may independently veto an unsafe automatic `MemoryCandidate`. | None |
| **Memory & Policy Service** | Authenticates account scope and deterministically enforces automatic-capture policy, access, storage, idempotency, and review. It accepts automatic candidates only after the required review. | Commits validated writes |

The Memory & Policy Service derives account identity from authenticated request
context and never accepts it from model output; agents cannot choose or widen
account scope. The interactive web application exposes only Muse conversation
and session reset. It provides no memory-management UI or public memory CRUD
API.

**Tool implementation policy.** Pydantic AI's maintained tools, capabilities, and toolsets are the default implementation, not examples to recreate locally. The implementation must first use an [official Pydantic AI tool or capability](https://pydantic.dev/docs/ai/tools-toolsets/common-tools/), a provider-native tool supported by Pydantic AI, or a supported external toolset such as MCP. A custom Pydantic AI function tool is permitted only for Linger-specific domain operations for which no maintained implementation exists, such as enforcing account-scoped memory retrieval or the book spoiler boundary. Such tools must be thin adapters over application services; they must not reimplement generic search clients, page fetching, tool schema generation, dispatch, or retries already supplied by Pydantic AI.

The allowed tool surface is deliberately smaller than each agent's responsibility:

| Agent | Allowed tools or capabilities | Implementation source |
|---|---|---|
| **Muse** | No general-purpose tools. Photographs use Pydantic AI's model input support; specialist calls and memory nomination are typed, application-controlled hand-offs rather than model-controlled tools. | Pydantic AI multimodal input and typed outputs; Linger orchestration |
| **Librarian** | Search the complete public-domain work and authorised memories for boundary inference; search only the inferred scope for evidence retrieval; resolve selected evidence records. | Thin Linger function-tool adapters over the retrieval and Memory & Policy services; Pydantic AI generates and validates their tool schemas |
| **Sculptor** | No retrieval or write tools. It receives a bounded input set and returns a typed `CurationProposal` or `NoCurationProposal`. | Pydantic AI typed input and output contracts |
| **Serendipity** | Search internal evidence through the same bounded Librarian adapters; search and retrieve public web evidence with Exa. | Internal Linger adapters plus the maintained [`pydantic_ai_harness.exa.ExaSearch`](https://pydantic.dev/docs/ai/tools-toolsets/common-tools/#exa-search-tool) capability |
| **Provenance** | No tools. It reviews only the complete candidate, supplied evidence, and policy constraints. | Pydantic AI typed input and output contracts |

Exa is the sole general web-search integration for the prototype. Install the `pydantic-ai-harness[exa]` extra and register `ExaSearch()` in Serendipity's `capabilities`; do not implement an Exa client or web-search tool locally. The older `exa_search_tool`, related Exa common tools, and `ExaToolset` are deprecated and must not be introduced. Exa results remain untrusted evidence and are still subject to Sections 6.4 and 6.5. This allocation does not authorise browser control, arbitrary URL fetching, shell access, or any external action excluded by Section 3.

Agents are logical roles, not necessarily separate models or processes. Muse handles the main interaction; Librarian, Sculptor, and Serendipity are invoked only when their specialised work is needed; Provenance runs for every Muse candidate response.

The five roles separate conversation and optional memory nomination, retrieval, post-capture memory curation, connection generation, and independent verification. Each agent is handed only the task in front of it, never the whole conversation; deterministic application code enforces access, capture, writes, and output release.

Each hand-off carries only the candidate response, optional memory candidate, claims, evidence identifiers, confidence, and policy flags required by the next step. Full transcripts and unrestricted working context are not passed between agents.

Provenance is a separate model call that shares no working context with the other agents. It receives the complete candidate response, any optional `MemoryCandidate`, the cited evidence, and the applicable policy constraints — nothing else, and no write tools. It independently detects quotations, factual claims, and sensitive inferences instead of trusting Muse's declarations. This provides separation of duties, not model independence, because the same underlying model may be used.

### 4.1 Output release contract

At target completion, every Muse invocation returns a typed candidate containing the complete response text plus its declared claims, quotations, evidence identifiers, sensitive-inference flags, and `MemoryCandidate | NoMemoryCandidate`. Those fields assist review but do not authorise release or capture: Provenance examines the entire draft and any proposed memory and may identify items Muse omitted or misclassified. Regular expressions and structural checks may provide defence in depth, but they are not the semantic security boundary.

The current book-corpus slice implements the smallest release contract needed by its active consumer: the complete response text plus declared evidence identifiers, exact quotations, and source locations. After each passing original or revised Provenance verdict, application code resolves every declaration against Librarian results from the current Muse invocation and validates the trusted work, book version, chapter ceiling, source lines, and exact quotation before release. Unsupported or unverifiable evidence fails closed to the application-authored safe decline. This staged contract does not remove the remaining target fields above.

Provenance returns `pass`, `revise`, or `reject` for the user-facing response and, when a `MemoryCandidate` is present, an independent `allow_capture` or `reject_capture` decision. Rejecting capture does not suppress an otherwise safe response. After a semantic pass, application code validates exact quotations, citation locations, account scope, and spoiler constraints where applicable. Only approved output is displayed. A first `revise` verdict gives Muse one revision, which returns through the same review path; a rejection or failed revision produces an application-authored safe decline.

### 4.2 End-to-end flows

#### 4.2.1 Reflection and grounding

Muse asks Librarian for evidence only when grounding is needed, but every path produces a candidate response for Provenance review. There is no Muse-to-user bypass.

![Reflection and grounding flow](images/reflection-and-grounding.png)

#### 4.2.2 Reviewed automatic memory capture

During controlled evaluation, Muse may nominate one typed `MemoryCandidate`;
Provenance may veto it for privacy, sensitive inference, unsupported provenance,
or injection risk. The Memory & Policy Service derives account scope, checks the
server-side evaluation policy and idempotency, validates the request, and owns
every write. The application reports a committed capture but offers no
memory-management action.

Sculptor is not part of capture. It later receives a bounded, account-scoped set of existing memories and may return a `CurationProposal | NoCurationProposal`; the Memory & Policy Service validates and applies permitted derived changes without modifying originals.

#### 4.2.3 Connection discovery and verification

Serendipity supplies a proposed connection and evidence identifiers to Muse. Muse drafts the user-facing reply, which uses the same mandatory Provenance gate and deterministic checks as an ordinary reflection.

![Connection discovery and verification flow](images/connection-discovery-and-verification.png)

## 5. Core records

### 5.1 Session state

Working context contains only:

- server-supplied `account_id`;
- `memory_capture_enabled`;
- the request-scoped `spoiler_boundary` inferred by Librarian from authorised
  memories, the current message, and the complete immutable work, or established
  through clarification;
- the active topic; and
- a compact conversation summary.

The complete memory archive is never injected into every prompt. Reading
progress is not stored as durable user state; Librarian resolves a temporary
spoiler boundary anew for each book-related request.

### 5.2 Memory record

An active memory belongs to the requesting account and was captured through the
reviewed automatic-capture path.

Each active memory contains:

- stable `memory_id` and server-supplied `account_id`;
- the user's original words;
- cited source-evidence identifiers, when applicable;
- a generated summary stored separately from the original;
- provenance linking the originating conversation or photograph;
- links to related, duplicate, or parent memories;
- an idempotency key derived from account, source event, and capture type;
- derivation metadata for generated records; and
- created and updated timestamps.

Original captured records are immutable. Sculptor may add or replace versioned
derived summaries and links but cannot modify an original. The interactive POC
does not expose correction or deletion.

For the prototype, the Memory & Policy Service stores each immutable capture as
a Markdown file with JSON front matter under a Git-ignored
`memories/<hashed-account-id>/` directory. Controlled evaluation may set capture
policy server-side; the interactive UI cannot change it. No embedding,
search-index, telemetry-memory, or vector-database layer is created until
retrieval requires one.

### 5.3 Evidence record

Every retrieved item carries:

- stable evidence identifier;
- source type and source location;
- owner or account scope where applicable;
- trust level and verification state;
- spoiler position for book evidence; and
- the minimum excerpt required for the current task.

### 5.4 Muse candidate response

At target completion, every candidate response contains:

- the complete proposed user-facing text;
- declared claims and quotations;
- cited evidence identifiers;
- sensitive-inference and policy flags; and
- `MemoryCandidate | NoMemoryCandidate`; and
- revision metadata, when applicable.

Muse's declarations and memory nomination are untrusted review hints. They do not narrow what Provenance must inspect or what application code must validate.

### 5.5 Memory candidate

An automatic `MemoryCandidate` contains only:

- the user's original words proposed for capture;
- the source turn and evidence identifiers, when applicable;
- a concise nomination reason; and
- sensitive-inference and policy flags.

`NoMemoryCandidate` contains a machine-checkable reason code. Neither type
contains account scope or write authority. The POC has no separate explicit-save
path.

### 5.6 Connection proposal

A connection proposal contains:

- a tentative claim;
- cited evidence identifiers;
- an explanation that distinguishes evidence from interpretation;
- uncertainty and policy flags; and
- Provenance's decision and structured critique, if any.

## 6. Safeguards

### 6.1 Spoilers

For each book-related request, Librarian first performs boundary inference. The
complete immutable work is its search scope: Librarian cross-references all
chapters against relevant, account-scoped memories and the current Line to
localize the latest event the person appears to know. This inference phase
returns a typed candidate boundary, confidence, and supporting locations for
the trace; it must not return
post-boundary story content to Muse. If the evidence is ambiguous or confidence
is insufficient, Muse asks a focused clarification before book evidence is
retrieved.

After inference, application code validates the work and version and propagates
the candidate as a request-scoped ceiling. Librarian then performs a separate
retrieval bounded to that ceiling, and application code rejects evidence outside
it before Muse can use it. Linger stores memories of what the person discussed,
not a durable chapter-progress field; the boundary is derived anew for each
request. This separation lets evaluation compare Librarian's inferred ceiling
with event-derived Ground truth while preventing full-work inference access from
becoming full-work disclosure authority.

The current implementation has only the second phase: it requires a
reader-confirmed `ConfirmedReading` ceiling before Librarian dispatch and fails
closed when that ceiling is absent. Full-work boundary inference from memories
is the next implementation gap, not shipped behavior.

### 6.2 Citations and attribution

Whenever an exact quotation is displayed or stored, application code verifies its text, source, and location against the corpus. Muse separates evidence from interpretation; Provenance reviews every complete draft for undeclared or mislabelled quotations and factual claims and checks their semantic support.

### 6.3 Memory and media control

- Automatic capture is disabled by default in the interactive POC and may be enabled only as controlled server-side evaluation state.
- Every committed capture produces a visible notice without exposing a management action.
- Before a long capture-enabled evaluation conversation is compacted or closed, Muse may make one final memory nomination through the same Provenance review and deterministic capture path.
- The interactive application exposes no explicit save, review, correction, or deletion controls.
- Raw photographs remain transient.
- Derived memories from photographs may be captured only while controlled capture policy is enabled.
- Sensitive-trait content is never captured automatically.
- Logs and telemetry follow the canonical [telemetry data contract](telemetry.md).

### 6.4 Untrusted content and privacy

Book text, web results, photographs, media descriptions, and candidate model responses are untrusted input. Private memory text is never copied verbatim into a web-search query. Evidence supplied to each agent is minimised, account-scoped, and labelled by trust level. Prompt instructions contained in evidence never gain tool authority.

### 6.5 Verification

Every Muse candidate requires a recorded approving Provenance verdict before release. Provenance may pass, reject, or request one revision. A candidate is not released when:

- cited evidence is missing or unresolved;
- attribution is incorrect;
- the spoiler boundary is unclear;
- evidence crosses account boundaries;
- a factual web claim lacks a retrievable citation;
- the candidate contains an unsupported claim or sensitive inference;
- retrieved content attempts to redirect agent behaviour.

Rejected and superseded drafts are never displayed. Deterministic validation runs after semantic approval and fails closed to the application-authored safe decline.

### 6.6 Emotional content

Muse is a reflection companion, not a wellbeing tool. It does not diagnose or label mental state and stops reflective probing after a distressing disclosure. It uses a fixed boundary response encouraging appropriate human support; crisis assessment and resource routing remain out of scope.

## 7. Evaluation and acceptance

### 7.1 Product evaluation requirements

Evaluation must test the product behaviour and authority boundaries in Sections 4–6. Retrieval and memory quality evaluation covers the following requirements:

- Compare keyword, semantic, hybrid, and reranked book and memory retrieval using measures such as Recall@5 and nDCG@5.
- Test whether Librarian's strategy selection improves relevance or latency over the strongest fixed strategy.
- Measure Sculptor's linking and grouping quality without allowing it to modify or delete an original memory.
- Verify that every derived record resolves to its originals.

The suggested measures in the [synthetic journal evaluation-objective catalog](../synthetic-journal-evaluation/evaluation-objectives.yaml) identify relevant signals. They are not adopted thresholds, aggregate scores, or release gates. Every factual web claim must include a retrievable citation, every evidence identifier must resolve, and any LLM-as-judge result is secondary and labelled non-independent.

### 7.2 Scenario-first synthetic journal evaluation

#### 7.2.1 Canonical vocabulary

Synthetic journal evaluation uses the following six terms. Documentation, skills, and future designs must use these terms instead of ad hoc synonyms such as *artifact*, *world*, *case*, *action*, or *fixture*. The vocabulary, v1 content and authoring-manifest contracts, and deterministic package validator adopt the Ground truth authority lifecycle below. Generation, independent adoption tooling, dataset freezing, and replay remain downstream decisions.

| Term | Definition |
|---|---|
| **Objective** | One of the ten catalog entries in [`evaluation-objectives.yaml`](../synthetic-journal-evaluation/evaluation-objectives.yaml). An objective specifies the behavior that a group of scenes must demonstrate. |
| **Backstory** | The generated history for one person, plus reading history only when relevant, that makes scenes coherent. One backstory represents one person and one evaluation account. The backstory informs generation only; the running system never receives it. |
| **Prop** | A generated memory record pre-positioned in Linger's storage and available to the evaluation before a scene runs. Each prop belongs to the backstory's person and evaluation account. When lines are fed to Muse, a prop may be used or remain untouched; Ground truth records the expected use or non-use for that scene. |
| **Scene** | One bounded test of one primary behavior, tied to an objective. A scene runs in a fresh session with its designated props and is graded as a unit. Objectives typically require paired scenes, such as a grounded scene and a non-grounded comparison scene. |
| **Line** | One generated user input that is sent to Muse within a scene. Most scenes contain one line; some contain an ordered sequence of lines. |
| **Ground truth** | The answer-key data for a scene: intended relationships, expected outcomes, permitted evidence identifiers, exact spans, and failure conditions. The generator writes **proposed Ground truth** in a separate authoring manifest while creating the content. Deterministic validation checks objective facts, then an independent reviewer adopts, revises, or rejects the proposal. Only **adopted Ground truth** is canonical for grading. Neither state is exposed to the running system. |

The vocabulary encodes these boundaries:

- One backstory represents one person and one evaluation account. Every prop, scene, and line belongs to that backstory.
- The backstory never enters the running system, and no backstory content becomes a prop by copying. A prop whose use or non-use is under evaluation must be generated as separate source text.
- Props are placed before a scene runs. Memory records that the system creates while a scene runs are recorded outcomes, not props, and are never hand-authored.
- Lines are conversational input only. Session reset and evaluation-controlled capture policy are workflow state, not Lines.
- The generator writes content and a separate authoring manifest together. The manifest records proposed Ground truth, including exact spans, intended relationships, Scene pairings, and expected or prohibited outcomes needed to preserve the generator's intent.
- Deterministic validation checks facts that can be resolved without judging Linger, such as identifiers, references, span boundaries, pairwise differences, and schema constraints. It does not adopt behavioral judgments.
- An independent reviewer adopts, revises, or rejects the proposed Ground truth. The system under evaluation receives neither the authoring manifest nor adopted Ground truth.

Synthetic authoring is intentionally evaluation-aware. The generator receives the selected, resolved Objective requirements and writes both content and proposed Ground truth so that intended contrasts and exact source spans are preserved. This is authoring, not grading: the generator does not observe Linger's recorded output and cannot adopt its own labels. Raw developer metadata and judge rubrics remain outside the generator prompt, and an independent reviewer still owns adoption.

The adopted v1 models are in [`evals/synthetic_journals/models.py`](../evals/synthetic_journals/models.py); [`evals/synthetic_journals/validate_package.py`](../evals/synthetic_journals/validate_package.py) validates the exact content-file hash, identifiers, references, ordering, spans, evidence, declared Scene differences, and resolved run-configuration counts. One validated package contains one Backstory, person, and evaluation account. A full dataset may combine multiple separately validated packages with different Backstories.

A Backstory may be memory-only or corpus-backed. In a corpus-backed spoiler scene, a
Prop and Line may refer naturally to events the person has already discussed;
the corresponding corpus position becomes Ground truth for grading Librarian's
boundary inference. Memory-only Backstories do not inspect or depend on the book corpus.

Everything after a line is handed to Muse — routing, agent hand-offs, telemetry — uses the architecture vocabulary in Sections 4–6 and the [telemetry data contract](telemetry.md), not this vocabulary.

#### 7.2.2 Objective selection and downstream boundary

The [`evaluation-objectives.yaml`](../synthetic-journal-evaluation/evaluation-objectives.yaml) catalog is the authority for the ten synthetic journal evaluation objectives, scenario descriptions, composition constraints, generation briefs, prompt boundaries, and selection rules.

The [`generate-synthetic-journals`](../.agents/skills/generate-synthetic-journals/SKILL.md) skill lets a developer select objectives, review the applicable scenarios and composition constraints, and confirm the selection. It then inspects the current repository and academic briefing and writes one timestamped Markdown pre-generation report for human review. The report assesses current execution readiness per Scene, describes the complete target evaluation design, uses the adopted v1 content and authoring-manifest contracts, and identifies the required implementation work. A current implementation gap does not weaken a confirmed Objective: the report instead includes a target-state generator prompt with explicit non-runnable preconditions. The prompt instructs a future generator to create Backstories, Props, Scenes, Lines or offline inputs, and proposed Ground truth together. The deterministic package validator checks objective facts before an independent reviewer can adopt Ground truth. The system under evaluation receives neither the authoring manifest nor adopted Ground truth. A future generator receives read-only repository paths, including `data/corpus/` only when book material is useful, and discovers current content there instead of receiving a hardcoded book. The report is never passed to a generator and creates no synthetic evaluation data.

Human approval of the report and implementation of the downstream workflow remain undefined. The project has adopted the three-stage Ground truth authority lifecycle, v1 package contracts, and deterministic package validation, but not decisions for:

- backstory generation;
- prop generation;
- scene composition;
- line generation;
- Ground truth review ownership and adoption tooling;
- package-directory and full-dataset layout;
- freezing; or
- replay.

The generation briefs and prompt boundaries describe requirements that a future design must preserve. A pre-generation report may propose a target-state stage sequence or unresolved workflow decision, but it must use the adopted v1 package contract rather than inventing another schema. Every remaining proposal must be labelled as proposed, compared with current repository facts, and approved by a human before use. The earlier inventory of 40 proposed scenes, category allocation, numeric thresholds, and frozen-baseline policy remain unadopted and do not constrain a new proposal.

Resolved run configurations keep each imbalance tied to the entity and Objective it tests. [`reviewed-automatic-memory-capture-10-to-1.json`](../synthetic-journal-evaluation/run-configurations/reviewed-automatic-memory-capture-10-to-1.json) applies a 1:10 capture-candidate/no-candidate **Scene** mix to one `reviewed_automatic_memory_capture` package. [`longitudinal-memory-retrieval-10-to-1.json`](../synthetic-journal-evaluation/run-configurations/longitudinal-memory-retrieval-10-to-1.json) applies a 1:10 relevant/distractor **Prop** mix to the target Scene for `longitudinal_memory_retrieval`; its paired comparison Scene uses the same 11 active Props with none relevant. Neither configuration is a universal Objective minimum. A full dataset repeats these patterns across multiple Backstories because one positive example cannot support stable recall measurement.

### 7.3 Deployment checks

The test deployment supports multiple accounts and up to five concurrent sessions. A basic load test reports success rate, p95 latency, and per-session model cost.

## 8. Operations and change control

The implementation stack is Python 3.12 with Pydantic AI for the five reasoning agents and FastAPI for the application API and deterministic orchestration. Agent-to-agent transitions that affect access, writes, validation, revision, or output release are programmatic hand-offs controlled by application code; no model controls its own authority or release path. OpenAI model calls use the Responses API so reasoning can be retained across tool calls and long-running conversations can be compacted. Agent contexts remain separate and bounded; API conversation state is working context, not durable product memory. Pydantic Logfire is the selected OpenTelemetry-compatible telemetry backend; its data and storage rules are defined exclusively by the [telemetry data contract](telemetry.md). The remaining stack is a lightweight web UI, Docker, and GitHub Actions.

Prompt templates, corpus builds, policies, tool contracts, schemas, evaluation scenes, and the system playbook are versioned. Fast mocked contract tests run in CI, while live-model evaluations separately measure output-gate recall, quality, cost, and latency. Prompt changes remain human-reviewed and must pass CI gates. Proposals produced by the self-improvement loops in Section 9 enter through this same review-and-CI path; they have no other route into the repository or the running system. The running test deployment, not only unit tests, is used to exercise rejected-draft suppression, output-gate bypass, account isolation, session reset, spoiler filters, forbidden memory requests, and prompt-injection defences.

### 8.1 Agent telemetry and debugging

The canonical [telemetry data contract](telemetry.md) defines the minimal captured fields, prohibited content, evaluation boundary, and verification requirements. Telemetry is diagnostic only: it never authorises output release, chooses account scope, commits memory writes, or becomes product memory.

## 9. Recursive self-improvement

Linger considers a deliberately bounded form of **recursive self-improvement (RSI)**: the system may help improve its regression coverage and operational guidance while humans retain approval authority over every change. This follows current frontier practice, which frames near-term RSI not as a model modifying its own weights or prompts autonomously, but as agents improving the scaffolding around the model through feedback loops that end in reviewed, gated changes. Any adopted loop must preserve that boundary and cannot grant an agent new runtime authority.

Two loops are in scope.

### 9.1 Failure-to-eval promotion

**Pain point.** Observed failures, including blocked prompt-injection attempts, Provenance rejections, and failed deterministic post-checks, can reveal gaps in regression coverage.

**Boundary.** A live-user failure produces only the metadata signature permitted by the [telemetry data contract](telemetry.md): trace ID, component and prompt versions, fixed verdicts, validation outcomes, and failure codes. Runtime telemetry never reconstructs or copies the user's input. Section 7.2 defines the adopted v1 Scene contract and deterministic package validation. The project has not adopted a mechanism for turning a live failure into synthetic content, a review and adoption process for that content, or a promotion workflow.

**Agents involved.** Provenance and the deterministic post-check layer act only as detectors. They cannot create, write, freeze, or promote evaluation data.

**Adoption criteria.** Any future failure-to-eval workflow must use synthetic or sanitised content, require human approval before repository integration, and grant no detector write or release authority.

### 9.2 Sculptor-curated system playbook

**Pain point.** Every agent system accumulates operational lessons — recurring Provenance critique patterns, evaluation-failure clusters, retrieval quirks, prompt gotchas — and they evaporate because nothing owns them. Current harness-engineering practice keeps these lessons in a versioned playbook that developers — and, where useful, prompts — draw on at the moment they are relevant. Maintaining such a playbook is curation work: deduplicate, summarise, link, and prune — which is precisely Sculptor's existing skill set, pointed at a second corpus.

**Mechanism.** A scheduled Sculptor task, run outside user conversations, reads only operational records permitted by the [telemetry data contract](telemetry.md), evaluation results, and developer notes, then proposes playbook edits: merge duplicate lessons, summarise clusters, retire stale entries, and link related ones. The playbook is a versioned repository file, not a record in the user memory store; the Memory & Policy Service is not involved. Sculptor's output is a proposed pull request; humans review and CI gates the merge, identical to any other change under Section 8.

**Relationship to Sculptor's product role.** The curation contract is unchanged — propose, never commit; preserve originals; work within a bounded context. Only the corpus differs: one curation agent, two memory stores — user memories and the system's memory of itself — under the same safeguards. The playbook task never receives raw personal memories, full transcripts, photographs, or sensitive-inference content, consistent with Sections 6.3 and 8.1.

**Relationship to failure-to-eval promotion.** If the project adopts the workflow in Section 9.1, failure-to-eval promotion will produce regression coverage, while Section 9.2 will continue to curate operational guidance. The two concerns remain separate.

**Success measures.** Playbook deduplication precision on seeded duplicate lessons; human acceptance rate of proposed edits; recurrence of repeated Provenance rejection classes tracked across releases. These are reported as evidence that the loop operates as designed; consistent with Section 3.3, the prototype makes no claim that telemetry measurably improved the system.

### 9.3 Boundaries

- Every adopted RSI output is a proposal. Humans review and CI gates every merge; no loop applies changes to prompts, policies, code, or evaluation scenes itself.
- Both loops run on a schedule, not during user conversations, and add no latency or authority to any user-facing flow.
- No agent gains write authority. Playbook changes, and any future evaluation data, must enter through repository review rather than the Memory & Policy Service. Sculptor's product-side curation path remains proposal-only.
- Loops consume only the operational metadata permitted by the [telemetry data contract](telemetry.md).
- Autonomous prompt or skill self-modification remains out of scope (Section 3.3); metric trends are reported without claiming measured product uplift.

### 9.4 Practice-module alignment

These loops are the specification's explicit answer to the practice-module briefing (`docs/submissions/aas-practice-module-briefing.pdf`), which asks which parts of the AI system lifecycle can be automated to reduce development effort and improve system quality attributes, and which grades the project on concrete artifacts:

- **MLSecOps/LLMSecOps pipeline design.** Section 9.1 defines the authority and privacy boundary for a possible future path from security detections to regression coverage. The downstream workflow remains unadopted.
- **AI security risk register.** Detection metadata can identify candidate regression gaps for prompt injection, unsupported claims, and sensitive-inference leakage without copying live-user content.
- **Testing data.** The evaluation-objective catalog defines the intended security coverage. A future downstream design must define the test data, harness, review process, and lifecycle.
- **Agent design documentation.** The system playbook demonstrates Sculptor's curation contract generalising across two memory stores under identical safeguards — an agent-design argument, not an added subsystem.
- **Responsible-AI governance.** Both loops are bounded, human-in-the-loop, and auditable: every change they produce is versioned, reviewed, and traceable, aligning the self-improvement story with the module's governance and accountability requirements.
