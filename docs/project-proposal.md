**PROJECT PROPOSAL**

# Linger

*A personal reflection and memory companion*

**Graduate Certificate in Architecting AI Systems - Practice Module**<br>
**Team:** Team 9<br>
**Members:** 5<br>
**Effort:** 75 person-days<br>
**Sponsor:** Not applicable (self-sourced idea)<br>
**Date:** 2026-07-26

---

## 1. Project title

**Linger** - an academic prototype of a personal reflection and memory companion, grounded initially in a small literary corpus. It helps a user articulate why an idea or experience mattered, preserve it as a structured memory, and later explore grounded, tentative connections across conversations, books, photographs, and evidence found through general web search.

## 2. Project members

| Member | Name | Agent / component owned |
|---|---|---|
| 1 | *Avan Quak* | **Muse** - reflection-companion agent |
| 2 | *Kevin Manuel* | **Librarian** - retrieval-and-reranking agent |
| 3 | *Choy Yong Yi Desmond* | **Sculptor** - memory-organisation agent |
| 4 | *Loke Yuen Ying, Jodie* | **Serendipity** - connection agent |
| 5 | *Leong Kay Mei* | **Provenance** - verifier agent |

Package ownership and the planned per-member effort allocation are shown in Section 6.

## 3. Overview

People retain fragments from books and everyday life: a passage, question, photograph, or personal interpretation. The pain points are concrete: highlights and notes accumulate in capture tools (Kindle, Readwise, Notion, photo rolls) but are rarely revisited; the *reason* a fragment mattered is lost because nothing prompts the user to articulate it at the moment of capture; and rediscovery depends on the user remembering to search for something they have, by definition, forgotten.

General-purpose AI agents (ChatGPT, Claude, OpenClaw, Hermes) already offer memory, image understanding, web search, and delegated tasks. Linger is not trying to be another general personal agent. It is a purpose-built reflection and memory application: a **provenance-first reflection companion** that keeps the user's words, source evidence, and generated interpretation distinct. Before any Muse-generated response reaches the user, a separate Provenance invocation semantically reviews the complete draft for quotations, factual claims, sensitive inferences, attribution, privacy, spoiler, and prompt-injection risks. Application code then performs deterministic checks where applicable. A non-factual reflection may pass without retrieval, but never without review.

The primary users are people who want to preserve the meaning behind an experience or idea, not merely the raw artefact.

The stakeholders are the end users; the project team, acting as system builder and prototype operator; and the hosted model and web-search providers on which the prototype depends. There is no external business sponsor.

### 3.1 User journey

Linger supports a continuous journey from reflection to rediscovery:

| Stage | User experience | How Linger helps |
|---|---|---|
| **1. Reflect** | The user talks with Muse or adds a photograph. | **Muse**, the reflection companion, drafts useful follow-ups and reflections. **Provenance** reviews every complete draft before it is displayed, including drafts that contain no factual claims. |
| **2. Ground** | When grounding is useful, the user receives relevant, cited passages or memories, clearly separated from Muse's interpretation. | **Librarian** retrieves and reranks evidence across books and structured memories; Muse drafts a response that separates source evidence, the user's words, and generated interpretation; Provenance checks the draft and its claimed support. |
| **3. Preserve** | After onboarding opt-in, a useful memory is retained without interrupting the conversation for per-memory approval. | **Sculptor** automatically creates, structures, and organises the memory; the user may immediately undo or later review, edit, or delete it. |
| **4. Reconnect** | A conversation or photograph suggests a potentially meaningful connection. | Muse may hand the cue to **Serendipity**, which searches internal evidence and, when useful, performs a general web search. Muse drafts the user-facing connection, and Provenance reviews the whole reply and its evidence before release. |

Automatic memory capture is available only after explicit onboarding opt-in and then runs without per-memory approval. Each captured memory is visibly disclosed in the conversation with an immediate undo control; users can pause capture or later review, edit, and delete memories. Content about sensitive traits is excluded from automatic capture and may be saved only through an explicit user action. Deletion cascades to derived summaries, links, embeddings, indexes, and application traces. Raw photographs remain transient unless the user chooses to save them, and derived memories are captured only while the opt-in remains active.

### 3.2 Agent roles

The prototype uses five agents with distinct reasoning responsibilities. Sculptor is the only agent permitted to request memory creation or updates; the Memory & Policy Service validates and commits those requests under deterministic application controls. User review, correction, and deletion actions go directly from the web interface to the service rather than through a model.

| Agent | Role in the journey | Key autonomous decisions | Tools Given |
|---|---|---|---|
| **Muse** | Maintains an ongoing reflection conversation across text and photographs while respecting spoiler boundaries when books are discussed. It produces candidate responses but cannot send them directly to the user. | Whether to ask a follow-up, request evidence, create a memory cue, invoke Serendipity, or report uncertainty; how to revise once against a Provenance critique. | Conversation state, image analysis, ask user, call Librarian, call Sculptor, call Serendipity |
| **Librarian** | Plans and executes retrieval across the book corpus and Sculptor-maintained memory store, returning reranked evidence with stable citations. | Which sources and retrieval strategy to use, how to formulate or expand the query, how to fuse and rerank candidates, and when evidence is sufficient. | Corpus search, scoped memory-query API, rerank |
| **Sculptor** | Automatically creates and maintains structured memories, preserving originals while improving their organisation for retrieval. | What to summarise, which memories are duplicates or related, how to group them, and when derived summaries should be refreshed. | Scoped memory search/create/update APIs, cluster |
| **Serendipity** | Responds to cues from Muse or photographs and proposes useful connections across memories, books, and general web search results. | Whether to search internally or on the web, what evidence to request, whether a connection is supportable, and how to revise against critique. | General web search, image analysis, call Librarian |
| **Provenance** | Semantically reviews every complete Muse candidate response in a separate restricted-context invocation, independently detecting quotations, factual claims, and sensitive inferences rather than trusting Muse's labels. | Whether to pass a non-factual draft, pass a supported draft, request one revision, or reject based on evidence, attribution, privacy scope, spoiler boundaries, sensitive inference, and prompt injection. | Read cited evidence, quotation and citation check, policy check, injection scan |

Five agents separate conversation, retrieval, memory curation, connection generation, and independent verification. Scoped hand-offs keep each invocation within a bounded task context; deterministic application code enforces access and writes. Provenance is the mandatory output gate for Muse, not only a verifier for Serendipity's connection proposals.

## 4. General flow

Working context contains only session essentials: capture consent, spoiler boundary, active topic, and a compact conversation summary. Long-term structured memories are retrieved only when needed rather than placed in every prompt.

An *active memory* is a memory record owned by the requesting account and not deleted. It may have been captured automatically while memory capture was enabled or saved explicitly by the user. Each memory is a structured record with fields for the user's own words, source citations, a generated summary, provenance links to the originating conversation or photograph, version metadata, and created/updated timestamps. Every write carries an idempotency key derived from its account, source event, and capture type so retries cannot create duplicates. Original user records remain immutable; a correction creates a linked active version, while derived summaries are versioned and replaceable.

The deterministic Memory & Policy Service obtains account identity from authenticated request context rather than agent or model output. It exposes scoped read, create, update, review, and delete operations and enforces account isolation and deletion on every request. Agents cannot choose or widen their access. Retrieved evidence carries its source type, owner or account scope, trust level, and verification state.

Every Muse invocation returns a typed candidate containing the complete response text plus its declared claims, quotations, evidence identifiers, and sensitive-inference flags. Those fields assist review but do not authorise release: Provenance examines the entire draft and may identify items Muse omitted or misclassified. Regular expressions and structural checks may provide defence in depth, but they are not the semantic security boundary. Provenance returns pass, revise, or reject; application code then validates exact quotations, citation locations, account scope, and spoiler constraints where applicable. Only approved output is displayed. A rejected first draft receives at most one bounded revision and re-review; a final rejection produces an application-authored safe decline.

The end-to-end design comprises three related flows. A normal turn uses the reflection flow; memory capture and connection discovery run only when their respective conditions are met.

### 4.1 Reflection and grounding

Muse keeps the conversation coherent and asks Librarian for evidence only when grounding is needed. It always produces a candidate response rather than replying directly. Provenance semantically reviews the complete draft, including any undeclared factual claims, quotations, or sensitive inferences; a passing draft then undergoes applicable deterministic checks before release. A non-factual response may need no evidence retrieval, but it still receives a Provenance verdict.

![Reflection and grounding flow](images/reflection-and-grounding.png)

*There is no Muse-to-user bypass. A revision returns to the same review path before release.*

### 4.2 Opt-in memory capture and control

Sculptor may propose a memory change, but deterministic application code owns access control and every write. The same path is used by the bounded final capture check before compaction or close. The save notice reports the committed operation through fixed application UI; it is not an unreviewed Muse response or a new model-generated paraphrase.

![Opt-in memory capture and control flow](images/opt-in-memory-capture-and-control.png)

### 4.3 Connection discovery and verification

Connection discovery is optional. Serendipity's proposal and evidence identifiers go to Muse, which drafts the complete user-facing reply. That reply then uses the same mandatory Provenance output gate as an ordinary reflection. Provenance may pass it, request one revision and resubmission, or reject it; rejection produces an application-authored safe decline rather than fresh Muse text.

![Connection discovery and verification flow](images/connection-discovery-and-verification.png)

Six safeguards govern the flow:

- **Spoiler control:** the user states their position in the book at the start of each session; when unstated, Muse defaults to the most conservative boundary (no content beyond the opening), and pre-emptively asks which chapter the user has reached whenever it is unsure. Muse confirms this boundary before Librarian retrieves unfinished text.
- **Citation validation:** whenever an exact quotation is displayed or stored, application code verifies its text, source, and location against the corpus. Muse separates evidence from interpretation, while Provenance reviews every complete draft for undeclared or mislabelled quotations and factual claims and checks the semantic support claimed for them.
- **Memory control:** Sculptor captures and organises memories automatically, but preserves the original record and provenance. It may link, group, or summarise memories but cannot delete them; the user retains review, correction, and deletion controls. Before a long opted-in conversation is compacted or closed, one bounded Sculptor pass checks for an important uncaptured reflection under the same notice, undo, and sensitive-content rules.
- **Verification:** Provenance runs on every Muse candidate response as a separate model invocation. It receives the complete draft, cited evidence, and applicable policy constraints, but neither unrestricted agent working context nor write tools. It independently detects quotations, factual claims, and sensitive inferences, returning a semantic pass, a structured critique for one bounded revision, or rejection. It may use the same underlying model, so this is separation of duties rather than model independence. No rejected or unrevised Muse draft reaches the user.
- **Media handling:** raw photographs remain transient unless the user chooses to save them; derived memories may be captured automatically only while the user's memory opt-in remains active.
- **Emotional content:** Muse is a reflection companion, not a wellbeing tool. It never diagnoses or labels the user's mental state and stops reflective probing after a distressing disclosure. It uses a fixed boundary response encouraging appropriate human support; crisis assessment and resource routing are out of scope.

Orchestration follows an explicit state-machine workflow implementing a **plan → act → check → refine** loop. Agents coordinate through typed contracts carrying the candidate response, claims, evidence identifiers, confidence, and policy flags needed by the next step; full transcripts and unrestricted working context are not passed between agents. Muse's declarations are hints rather than trusted classifications because Provenance examines the full text independently. Each agent can respond to incomplete evidence or decline, and the policy service is application code, not an agent, so access, write, and release guarantees never depend on model instructions alone.

## 5. Scope of work

The prototype accepts conversation and photographs as memory cues. Source-grounded book retrieval remains limited to 3–5 public-domain books from Project Gutenberg; Serendipity may also use general web search when looking for evidence supporting a connection.

- **In scope:** ongoing Muse conversations; semantic Provenance review of every Muse candidate response; deeper evidence verification when a draft contains quotations, factual claims, connections, or sensitive inferences; photograph understanding; cited retrieval across the book corpus and structured memories using keyword, semantic, and hybrid strategies plus reranking; opt-in automatic memory capture; structured summaries, duplicate linking, topic grouping, and progressive disclosure through Sculptor; Serendipity connections triggered by conversations or new photographs, with general web search; request-specific spoiler filtering; deterministic quotation and citation validation; user-controlled review and deletion; adversarial tests; simple web UI; CI/CD and test deployment.
- **Stretch:** voice-note transcription as a third memory cue (including audio-borne injection tests); cross-book, memory-to-memory, and song-to-memory connections; comparing a revisited pairing with the earlier reflection; a synthetic exercise of an opt-in feedback pipeline.
- **Out of scope:** persistent reading-progress tracking; live music, photo-library, messaging, or social integrations; the full Gutenberg catalogue; copyrighted books or lyrics; music or copyrighted-audio analysis; production-scale or compliance claims; mental-health profiling or crisis-resource routing; any claim that telemetry measurably improved the system.

### 5.1 How the implementation demonstrates key considerations

| Consideration | Implementation |
|---|---|
| **Explainability & trust** | Every displayed Muse response has a recorded Provenance verdict. Exact book quotations and source locations carry inspectable citations; quotations, user statements, and generated interpretations are visually and structurally separated; connections are presented as hypotheses with visible uncertainty; workflow tracing records why each step happened. |
| **Responsible AI & governance** | Automatic memory capture requires explicit onboarding opt-in and remains visibly controllable through save notices, undo, pause, review, correction, and cascading deletion. Content about sensitive traits is excluded from automatic capture. Sculptor preserves originals and provenance when creating derived records, and raw photographs remain transient unless saved. In this personal-use setting, the small, older public-domain corpus and its dated cultural perspectives are disclosed rather than presented as neutral. Muse uses a fixed boundary response for distressing disclosures rather than attempting diagnosis or crisis assessment. Data minimisation and alignment with the IMDA Model AI Governance Framework remain in scope. |
| **Security** | Retrieved book text, general web-search results, photographs, and candidate model responses are treated as untrusted input. Provenance semantically reviews every Muse draft, including for undeclared claims and sensitive inferences; each evidence item carries source, ownership, trust, and verification metadata, and private memory text is never copied verbatim into a web-search query. Authenticated account identity is supplied by application code, never by an agent. Deterministic controls enforce output release, access, cascading deletion, spoiler filters, and isolation **between user accounts**. The test deployment uses multiple accounts so cross-account retrieval is tested rather than merely asserted. Automated adversarial cases cover prompt injection, fabricated claims, spoiler leakage, forbidden memory requests, output-gate bypass, log leakage, and deleted-data retrieval. |
| **Agent autonomy & orchestration** | Framework-native orchestration (Pi in TypeScript, PydanticAI in Python) implementing plan → act → check → refine: agents select tools, respond to incomplete evidence, decline unsafe actions, and coordinate through typed contracts carrying bounded, role-specific context. Muse drafts and may revise, but application-controlled orchestration prevents direct release without a Provenance verdict. |
| **Controlled improvement** | Provenance returns structured critiques for bounded revision. Prompt changes remain human-reviewed, versioned, and gated by the CI evaluation suite; no improvement claim relies on prototype user telemetry. |
| **MLOps / LLMSecOps** | Versioned prompts, corpus builds, tool contracts, policies, and JSON/YAML evaluation cases; fast mocked contract tests in CI; separate live-model evaluation of output-gate recall, quality, cost, and latency; and logs scrubbed of raw personal memories. The system is deployed to a reproducible test environment so Provenance verdict coverage, rejected-draft suppression, user isolation, prompt-injection defences, forbidden memory requests, and deletion are exercised against a running system, not just unit tests. |

**Proposed stack (subject to team confirmation):** **Pi for TypeScript agents; PydanticAI for Python agents** - whichever language a given agent is written in - with typed tool contracts as the common interface between them. Orchestration is expressed in the agent framework's own typed control flow, keeping the plan → act → check → refine cycle in ordinary reviewable code. A hosted LLM API, FastAPI backend, lightweight web UI, Docker, and GitHub Actions CI/CD.

### 5.2 Trade-offs and validation

| Question | Proposal |
|---|---|
| **Benefits and trade-offs** | Specialised agents improve separation of duties, traceability, context isolation, and independent verification. Mandatory Provenance review provides a simple, auditable release rule and avoids brittle regex routing, but adds one model invocation to every Muse turn, increasing latency, cost, orchestration complexity, and correlated-model failure risk. The prototype measures that overhead directly rather than claiming it is production-optimal. |
| **Scale** | The prototype targets up to five concurrent user sessions, not production scale. A basic load test will report success rate, p95 latency, and per-session model cost. |
| **Retrieval evaluation** | A fixed set of citation-labelled book and memory queries compares keyword, semantic, hybrid, and reranked retrieval using Recall@5 and nDCG@5. The same set tests whether Librarian's strategy selection improves relevance or latency over the strongest fixed approach. |
| **Memory-quality evaluation** | Seeded duplicate and noisy memories test Sculptor's linking and grouping precision and the resulting change in Recall@5 and nDCG@5. Every derived summary must remain traceable to its original memories, and Sculptor must never delete an original. |
| **Demo success criteria - safety** | A fixed 40-case set is defined before implementation as versioned JSON or YAML. Each case has one primary behaviour and records its inputs, expected outputs or evidence identifiers, and forbidden outputs as applicable: 15 safety/adversarial cases, 5 reflection cases, 5 memory-capture cases, 10 expected-connection cases, and 5 weak-evidence cases. Shared deterministic checks validate citations, evidence identifiers, disclosure boundaries, and Provenance verdict coverage across the set. Every user-visible Muse response must have an approving verdict; rejected and superseded drafts must never be displayed. No cross-account, deleted, or post-boundary content may be revealed; every seeded text-, web-, or image-borne injection must be blocked or safely ignored; sensitive-trait content must never be captured automatically; and ambiguous spoiler boundaries must trigger clarification. |
| **Demo success criteria - quality** | Reflection cases define the expected action and acceptable follow-up intent; memory-capture cases define whether a memory should be saved and its required fields; expected-connection cases define acceptable target memory/source pairs; and weak-evidence cases require decline. The harness reports reflection-action accuracy, semantic detection recall for quotations, factual claims, and sensitive inferences, unsupported-claim block rate, non-factual pass rate, memory-capture precision and recall, target-connection hit rate, evidence recall, citation precision, exact-quotation accuracy, and weak-evidence decline rate. Any LLM-as-judge score is secondary and explicitly labelled non-independent. |

### Success thresholds

| Threshold | Measures |
|---:|---|
| **80%** | Reflection-action accuracy; memory-capture precision and recall; target-connection hits; weak-evidence declines |
| **90%** | Evidence recall |
| **95%** | Citation precision; semantic detection recall for seeded quotations, factual claims, and sensitive inferences |
| **100%** | Exact-quotation accuracy; Provenance verdict coverage for Muse responses; rejected-draft suppression |

## 6. Effort estimates

The WBS below lists the top-level work packages, an accountable owner for each, and rough estimates in person-days. Each package will be broken into assignable tasks at kick-off, with actual effort tracked in the fortnightly progress reports. Owners (M1–M5) correspond to the members in Section 2; the owner is accountable for the package, not its sole contributor.

Guideline: 5 members × 15 person-days ≈ **75 person-days**. The core plan uses 70 person-days and reserves 5 for integration and evaluation risks; stretch items are excluded.

| # | WBS work package | Owner | Est. (person-days) |
|---|---|---|---|
| 1 | Corpus ingestion, indexes, and citation scheme (3–5 Gutenberg books) | M2 | 4 |
| 2 | Memory & policy service (opt-in automatic storage, isolation, review, deletion) + data model | M3 | 5 |
| 3 | Muse - reflection-companion agent (multi-turn dialogue, multimodal input routing, follow-ups, agent hand-offs) | M1 | 5 |
| 4 | Librarian - retrieval agent (book and memory retrieval, query planning, keyword/semantic/hybrid search, fusion, reranking) | M2 | 6 |
| 5 | Sculptor - memory-organisation agent (structured summaries, duplicate linking, grouping, progressive disclosure) | M3 | 5 |
| 6 | Serendipity - connection agent (conversation/photo cues, internal and web search, decline behaviour, revision loop) | M4 | 6 |
| 7 | Provenance - universal Muse output-review agent (semantic claim, quotation, sensitive-inference, evidence, privacy, injection, and overreach checks; critiques) | M5 | 5 |
| 8 | **Orchestration & integration** (Pi/PydanticAI agent assembly, typed tool contracts, mandatory output gate, end-to-end flow, failure handling) | M1 | 6 |
| 9 | Security test suite & AI risk register (text-, web-, and image-borne injection, fabrication, output-gate bypass, cross-account access, deletion) | M5 | 5 |
| 10 | Evaluation harness: retrieval, reflection, memory, connection quality, semantic output detection, and release-gate benchmarks | M4 | 5 |
| 11 | Web UI for conversation, photograph, and memory-management flows | M3 | 4 |
| 12 | CI/CD, tracing, cost/latency measurement, test deployment | M2 | 4 |
| 13 | Group report, architecture and agent documentation, presentation | M5 (coordinator) | 4 |
| 14 | Individual reports (1.2 days per member × 5 members) | All members | 6 total |
| 15 | Contingency for integration and evaluation risks | M1 (coordinator) | 5 |
| | **Total** | | **75** |

The owner named above is accountable for a package, while implementation and review effort may be shared. The planned allocation reconciles the 75-person-day guideline:

| Member | Shared project work, integration, and contingency | Individual report | Planned total |
|---|---:|---:|---:|
| M1 | 13.8 | 1.2 | 15.0 |
| M2 | 13.8 | 1.2 | 15.0 |
| M3 | 13.8 | 1.2 | 15.0 |
| M4 | 13.8 | 1.2 | 15.0 |
| M5 | 13.8 | 1.2 | 15.0 |
| **Total** | **69.0** | **6.0** | **75.0** |

Effort will be tracked and reported in fortnightly progress reports per the module schedule (proposal due 31 Jul 26; project conduct 10 Aug – 9 Oct 26; presentations from 12 Oct 26; final reports 30 Oct 26).
