# Linger: A Provenance-First Multi-Agent Reflection Companion

Master of Technology in Intelligent Systems, Institute of Systems Science, National University of Singapore. Group 9 Project Report.

- Choy Yong Yi Desmond [A0315402W]
- Leong Kay Mei [A0188702Y]
- Loke Yuen Ying, Jodie [A0310555M]
- Kevin Manuel Lee
- Avan

| Agent | Owner |
|---|---|
| Muse | Avan |
| Librarian | Kevin Manuel Lee |
| Serendipity | Yuen Ying Jodie Loke |
| Provenance | Kay Mei Leong |
| Sculptor | Desmond Choy |

---

## Contents

- [1. Introduction](#1-introduction)
  - [1.1 Problem and objective](#11-problem-and-objective)
  - [1.2 Scope and limitations](#12-scope-and-limitations)
  - [1.3 Constraints and assumptions](#13-constraints-and-assumptions)
  - [1.4 Project key terms](#14-project-key-terms)
- [2. System Overview and Architecture](#2-system-overview-and-architecture)
  - [2.1 Logical architecture](#21-logical-architecture)
  - [2.2 One chat turn](#22-one-chat-turn)
  - [2.3 Deployment](#23-deployment)
  - [2.4 Data and state](#24-data-and-state)
  - [2.5 Technology stack](#25-technology-stack)
  - [2.6 User interface](#26-user-interface)
- [3. Agent Roles and Design](#3-agent-roles-and-design)
  - [3.1 Roles](#31-roles)
  - [3.2 Input boundary: controls before any model](#32-input-boundary-controls-before-any-model)
  - [3.3 Reasoning boundary: typed hand-offs](#33-reasoning-boundary-typed-hand-offs)
  - [3.4 Output boundary: review and release](#34-output-boundary-review-and-release)
  - [3.5 Memory boundary](#35-memory-boundary)
  - [3.6 Prompt patterns](#36-prompt-patterns)
- [4. Explainable and Responsible AI Practices](#4-explainable-and-responsible-ai-practices)
  - [4.1 Responsible AI across the lifecycle](#41-responsible-ai-across-the-lifecycle)
  - [4.2 Explainability and traceability](#42-explainability-and-traceability)
  - [4.3 Fairness and bias mitigation](#43-fairness-and-bias-mitigation)
  - [4.4 Alignment with the Model AI Governance Framework](#44-alignment-with-the-model-ai-governance-framework)
- [5. AI Security Risk Register](#5-ai-security-risk-register)
- [6. LLMSecOps Pipeline](#6-llmsecops-pipeline)
  - [6.1 Change control and continuous integration](#61-change-control-and-continuous-integration)
  - [6.2 Versioning and release](#62-versioning-and-release)
  - [6.3 Monitoring and audit logging](#63-monitoring-and-audit-logging)
  - [6.4 Feeding failures back into development](#64-feeding-failures-back-into-development)
- [7. Testing and Evaluation](#7-testing-and-evaluation)
  - [7.1 How agent quality is evaluated](#71-how-agent-quality-is-evaluated)
  - [7.2 Scenarios and Ground truth](#72-scenarios-and-ground-truth)
  - [7.3 Scenario replay results](#73-scenario-replay-results)
  - [7.4 Component results](#74-component-results)
  - [7.5 Where the system loses quality](#75-where-the-system-loses-quality)
  - [7.6 Testing the application](#76-testing-the-application)
  - [7.7 Cost, speed, and load](#77-cost-speed-and-load)
  - [7.8 Limitations](#78-limitations)
- [8. Reflection](#8-reflection)
  - [8.1 Key findings](#81-key-findings)
  - [8.2 Lessons for building multi-agent systems](#82-lessons-for-building-multi-agent-systems)
  - [8.3 Lessons for evaluating multi-agent systems](#83-lessons-for-evaluating-multi-agent-systems)
  - [8.4 Individual reflections](#84-individual-reflections)
  - [8.5 Future work](#85-future-work)
- [Appendix A. Metric definitions](#appendix-a-metric-definitions)
- [Appendix B. Related work](#appendix-b-related-work)
- [References](#references)

---

## 1. Introduction

### 1.1 Problem and objective

Large language models make it straightforward to build a companion that discusses a person's reading and their life. They make it equally straightforward to build one that misquotes the book, invents what the person said, reveals a chapter the reader has not reached, or quietly stores something that should never have been kept. Linger is an academic prototype of a personal reflection and memory companion.

A reader tells Linger about a book they are reading and about their own life. Linger helps them articulate why a passage or an experience mattered, preserves that reflection, and suggests tentative connections between their reading, their earlier reflections, and public sources. It is grounded in five public-domain works: *Alice's Adventures in Wonderland*, *Animal Farm*, *Narrative of the Life of Frederick Douglass*, *The Adventures of Pinocchio*, and Helen Keller's *The Story of My Life*.

### 1.2 Scope and limitations

Linger is built for a reader who wants to talk through what they are reading alongside their own life. This section lists what the prototype does and what it deliberately does not do.

**In scope**

- **Reflect on reading and life.** The reader describes a passage or an experience, and Linger helps them say why it mattered. An independent reviewer checks every reply before the reader sees it. A reply that fails review is replaced with a fixed, safe decline.
- **Ask about the book.** Exact quotations and questions about what happened are answered from the text, only up to the point the reader has reached. The reader can state their chapter, which is saved for that book, or Linger can infer it from the event they describe.
- **Find connections.** Linger can suggest one tentative link between a reflection and a book passage the reader has reached, their own saved reflections, or a public web page, with the source shown. When nothing supports a link, it says so rather than inventing one.
- **Recall earlier reflections.** Asked what they said before, the reader gets up to three of their own saved records back, in their own words, rather than a paraphrase.
- **Keep a record.** Linger saves a reflection automatically when it judges it worth keeping, using the reader's exact words and showing a visible notice. The reviewer can veto a save, and sensitive content is never saved. Related memories are then curated in the background: duplicates are linked, related memories are grouped, and summaries are added, without changing the originals.

**Out of scope**

- **Text in English only.** Photographs, voice notes, and non-English messages are not supported. A non-English message receives a fixed request to rephrase.
- **Five public-domain books only.** Readers cannot add their own books, and copyrighted texts are excluded.
- **No memory controls.** Readers cannot view, edit, or delete saved memories, or save one by hand.
- **Only inside a conversation.** Linger sends no notifications and does not resurface memories outside an active chat.
- **Not a wellbeing tool.** Linger does not diagnose or assess mental health. A distressing disclosure ends the questioning with a fixed message pointing to support, and a self-harm disclosure adds a crisis-line link.

Behind the in-scope uses, five design decisions distinguish the solution:

- **Five agents, one deterministic memory writer.** Muse, Librarian, Serendipity, Provenance, and Sculptor are arranged around one deterministic Memory and Policy Service, which alone writes personal memories and curation records. Separate application stores persist accounts, transcripts, and reading progress. No model may release its own output or widen its own authority.
- **Independent review before every release.** Every reply is drafted as a typed candidate, reviewed by a Provenance agent that has no tools and no conversation history, and validated by application code against a request-scoped evidence index before any text reaches the reader. Any failure becomes a fixed, application-authored decline.
- **Bounded book retrieval.** The application restricts answer-facing retrieval to the resolved reading position. Private boundary inference may inspect the full work, but its candidates do not become answer evidence without a validated grant. The measured retrieval runs had no spoiler exposures; handling retracted saved progress remains an open defect (Section 7.8).
- **Typed, application-mediated hand-offs.** Agents never call one another. Every hand-off is a typed envelope carrying only what the next step needs, and every model run carries a fingerprint of its exact configuration.
- **Evaluation and release pipeline.** Contract tests, component evaluations, and replay of synthetic conversations use human-adopted expected outcomes. CI runs tests and security scanning. With live evaluation disabled, the release workflow still checks an image and requires human approval before publication. Hosted protections and release evidence have verification limits described in Section 6.2.

### 1.3 Constraints and assumptions

Linger is a prototype running as a single backend process, not ready for production: there is no password reset, email verification, or multi-process deployment. The project makes no claims about scale, availability, or regulatory compliance. In addition, all evaluation uses synthetic readers and public-domain books. No real user data was used, and usefulness to real readers was not measured.

### 1.4 Project key terms

| Term | Meaning |
|---|---|
| Agent | A model-backed component with one job: Muse, Librarian, Serendipity, Provenance, or Sculptor (Table 2) |
| Application layer | Deterministic code that decides what each agent may see and do, and the only layer that releases text or writes to storage |
| Objective | One system-level evaluation goal from a catalogue, with its hard gates and measures |
| Scenario | The complete evaluation design for one synthetic person and account |
| Backstory | That person's situation and reading history |
| Prop | A memory record placed in the store before a Scene runs |
| Line | One reader message |
| Scene | One graded unit: a Line, its Props, and the expected outcome |
| Ground truth | The expected outcome of each Scene, authoritative only after a human reviewer adopts it |

**Table 1.** Key terms.

---

## 2. System Overview and Architecture

This section describes Linger as software: its layers, how one turn flows, where it runs, where state is kept, the technology chosen, and the interface. Section 3 describes the agents and the controls the application places around them.

### 2.1 Logical architecture

Linger has two layers. The **application layer** is deterministic code: it decides what each agent may see and do, and it is the only layer that releases text or writes to storage. The **agent layer** is five model-backed agents, each with one job. Table 2 lists every component.

| Component | Layer | Job |
|---|---|---|
| `run_chat_turn` (`apps/backend/chat_turn.py`) | Application | Runs one turn: controls, tool grants, agent order, release, and capture policy |
| Release checks and evidence index (`src/linger/orchestration/turn_context.py`) | Application | Bind every quotation and citation to evidence retrieved in this request |
| Retrieval (`apps/backend/librarian.py`) | Application | Searches the corpus only up to the reader's position |
| Memory and Policy Service (`src/linger/services/memory.py`) | Application | The only component that writes personal memories and curation records |
| Muse | Agent | Holds the conversation and drafts every reply |
| Librarian | Agent | Works out how far the reader has read and judges whether passages support the request |
| Serendipity | Agent | Suggests one connection to another book, an earlier reflection, or a web page, or recalls the reader's own words |
| Provenance | Agent | Reviews each draft, each memory nomination, and each curation proposal before anything is released or stored |
| Sculptor | Agent | Proposes summaries and topic groups over stored memories without changing the originals |

**Table 2.** Components and layers.

Figure 1 shows which components may interact. No edge connects two agents.

![Layered logical architecture: presentation and transport, application layer, agent layer, and services and stores. The application layer selects a skill for each agent; no edge connects two agents](images/figure-logical-architecture.svg)

**Figure 1.** Logical architecture. No edge connects two agents.

### 2.2 One chat turn

Figure 2 shows one turn, from the reader's message to the released reply. The turn crosses four boundaries, each described in Section 3: input (Section 3.2), reasoning (Section 3.3), output (Section 3.4), and memory (Section 3.5).

![Sequence diagram of one chat turn across the reader, the application, Provenance, Muse, Librarian or Serendipity, and the Memory and Policy Service](images/figure-chat-turn.svg)

**Figure 2.** One chat turn. Grey columns are agents and white columns are application code. Agents never message each other: Muse reaches Librarian and Serendipity only through tools the application grants, and model-written text reaches the reader only at step 9, after the deterministic release checks.

### 2.3 Deployment

In development, the prototype runs as two processes: a Vite server for the React front end and a FastAPI backend on Uvicorn. All five agents, the local retrieval models, and the stores run inside the backend process (Figure 3).

![Physical architecture: the browser and front end call one Uvicorn and FastAPI process that hosts the five agents, the local retrieval models, the state volume, and the corpus; the process calls the model provider, Exa, and Logfire over HTTPS](images/figure-physical-architecture.svg)

**Figure 3.** Physical architecture.

For release, Docker builds one image:

- One Linux AMD64 image on Ubuntu 24.04, running one non-root Uvicorn worker that also serves the built front end.
- The image holds the corpus, the skills and prompts, and the local retrieval models with their file hashes. It excludes provider keys, account databases, private memories, and raw evaluation reports.
- Health and readiness endpoints check configuration, storage, corpus, and models without making a paid model call.
- The release workflow can publish an approved image to the GitHub Container Registry. After candidate promotion, Railway deployment uses that exact published digest (Section 6.2).
- Not provided: multi-user capacity, shared session storage across processes, and zero-downtime deployment.

### 2.4 Data and state

All state lives in the application layer. Table 3 lists where each kind is kept. Only the application writes it, and a turn that fails before release writes nothing. Section 3.5 describes how the agents nominate, review, and curate long-term memories.

| State | Lifetime | Stored in | Written by | Code |
|---|---|---|---|---|
| Evidence index and tool grants | One request | Process memory, discarded after the turn | Application | `src/linger/orchestration/turn_context.py` |
| Agent working context | One agent run | Nowhere; rebuilt from a typed input each run | Application | `src/linger/agents/` |
| Conversation history | One session | Process memory, restored from transcripts after a restart | Application, released turns only | `apps/backend/sessions.py` |
| Book selection and pending clarification | One session; rolled back if a turn fails before release | Process memory | Application | `apps/backend/sessions.py` |
| Declared reading position | Per account and book, across sessions | SQLite | Application, from the reader's own words only | `apps/backend/reading_progress.py`, `apps/backend/progress_store.py` |
| Accounts and transcripts | Per account | SQLite | Application | `apps/backend/accounts.py`, `apps/backend/transcripts.py` |
| Long-term memories, curation layer, and audit log | Per account | Content-hashed Markdown records | Memory and Policy Service only | `src/linger/services/memory.py` |

**Table 3.** State, by lifetime.

### 2.5 Technology stack

Table 4 lists each technology and why it was chosen over the obvious alternative.

| Layer | Choice | Why |
|---|---|---|
| Orchestration | Plain Python in `run_chat_turn` | Sequencing, tool grants, and release stay in one function that is easy to read and unit-test. Agent-graph frameworks such as LangGraph or CrewAI make agent-to-agent calls easy, which this design forbids |
| Agent framework | Pydantic AI | Typed inputs and outputs with validation retries, per-run instructions, provider abstraction, Logfire instrumentation, and a maintained Exa capability |
| Agent structure | One agent per role; skill chosen per run | Each role's tools and validators stay in one place, while each task's instructions and schema are versioned separately |
| Models | Shared `LINGER_MODEL`; team standard OpenAI `gpt-6-luna`; Google and Anthropic supported | All reported live results use OpenAI models; selected skills override reasoning effort (Section 3) |
| Retrieval | Hybrid BM25 and dense retrieval with cross-encoder reranking, in application code | Highest evidence recall with the least evidence volume, at a p95 of 0.46 seconds (Section 7.4). Spoiler safety cannot depend on a model's judgment |
| Web search | Exa, off unless enabled | Public-web connections only when policy and credentials allow |
| Backend | FastAPI on Uvicorn, Python 3.12 | Thin transport and authentication layer over `run_chat_turn` |
| Front end | React 19 with Vite | Account and chat views; Library and Inspect are local developer diagnostics |
| Storage | SQLite for accounts and transcripts; content-hashed Markdown for the corpus and memories | Enough for a single-process prototype. Hashed, immutable records are easy to audit |
| Observability | Logfire under a written data contract | Traces without reader content, enforced by a typed projection and an exported-payload test (Section 6.3) |
| Packaging | Docker; GitHub Container Registry | One tested image moves from CI to release unchanged |

**Table 4.** Technology stack.

### 2.6 User interface

The product interface provides account access and chat. The local development interface also exposes corpus, inspection, and evaluation views. Table 5 distinguishes these uses; Figures 4 to 8 show development and review screens.

| View | Who uses it | What it shows |
|---|---|---|
| Chat with agent map | Reader; map used for development inspection | The conversation, with a local diagnostic map of which components ran for each reply |
| Inspect | Developer, local interface only | For each reply: the route taken, each agent's outcome, the review verdict, and the recorded hand-offs |
| Library / Reader | Developer, local interface only | The registered books and their corpus text for testing and inspection |
| Saved evaluation | Developer | A replayed Scenario: the synthetic reader, the memory placed beforehand, the test message, and the route the build took |
| Ground-truth review | Reviewer | Each proposed expected outcome beside its inputs, with Approve and Needs changes |

**Table 5.** Views in the web interface.

![Chat reply about Alice changing size, beside the live agent map](images/ui-02-grounded-reply.png)

**Figure 4.** Chat with the local diagnostic agent map. The reply is grounded in chapter 2, which the reader confirmed reaching.

![Inspect view showing the route through Muse, Provenance, and release checks](images/ui-05-inspector-card.png)

**Figure 5.** The developer-only Inspect view for one local turn: the route through Muse, Provenance, and the release checks, and each component that ran, in order.

![Library panel listing the five books](images/ui-06-library-reader.png)

**Figure 6.** The local developer Library / Reader view.

![Saved evaluation view with the persona's Backstory, the Prop, the fixed Line, and the route taken](images/ui-07-saved-evaluation.png)

**Figure 7.** A saved evaluation reopened in the interface: the synthetic reader, the memory placed in the account before the run, the fixed test message, the route this build took, and the adopted answer key.

![Ground-truth review application showing a Scene's Line beside the proposed Ground truth, with Needs changes and Approve controls](images/ground-truth-review.png)

**Figure 8.** The Ground-truth review application. (1) The test message sits beside the proposed expected outcome. (2) The reviewer approves it or marks it as needing changes.

---

## 3. Agent Roles and Design

All five agents use the shared configured model, `LINGER_MODEL`; the team standard is OpenAI's `gpt-6-luna`. Shared OpenAI reasoning effort is low (`src/linger/agents/build.py`). Muse reflection and Provenance candidate review override it to medium in `src/linger/agents/muse/skills.py` and `src/linger/agents/provenance/skills.py`. Serendipity runs at medium by role default in `src/linger/agents/build.py`. Earlier evaluations used `gpt-5.6-luna`. Table 6 summarises each role, and Table 7 shows what each role can see and change. Dated evaluation results describe the configuration measured at the time, which may differ from the current implementation.

Agents never call one another, and no agent can release text or write to storage. Sections 3.2 to 3.5 describe the four boundaries where the application constrains the agents. Each lists what the application enforces and what the agents decide.

### 3.1 Roles

| Agent | Purpose and responsibilities | Reasoning pattern | Model | Memory | Tools |
|---|---|---|---|---|---|
| Muse | Owns the conversation. Triages each Line, drafts the only reader-facing prose, nominates at most one exact span for capture, and repairs one round of review findings | Two runs per turn. Triage classifies the Line with no tools. Reflection drafts the reply and decides whether to call each granted tool, up to eight tool calls. One revision run follows if Provenance asks | Configured model; turn triage uses `gpt-6-luna` with OpenAI or `gemini-2.5-flash` with Google | Released session history only: at most eight recent turns and 16,000 characters. Stored memories arrive only as evidence returned by Serendipity | `librarian_route`, `librarian_search`, `serendipity_explore`, granted by the application per turn, after triage |
| Librarian | Resolves the reader's reading boundary, plans book requests as exact spans of the reader's text, and judges whether permitted passages support each part of a request | A chain of single typed judgements that the application runs in order: infer the reading boundary and identify the event when needed, plan the request, then assess the retrieved evidence. No tool loop | Configured model, plus local embedding and reranker models in application-owned retrieval | Stateless per request, apart from a chapter the reader explicitly declared, which is held for the session and saved per account and work | None. Retrieval is application code |
| Serendipity | Looks for one tentative, evidence-supported connection between a reflection and a permitted book passage, memory, or web page, or returns a typed decline; under a separate intent, recalls the reader's earlier words | A search loop. It chooses which granted sources to search, filters and ranks the candidates, then returns one proposal or a typed decline. The intent selects the skill. At most 14 tool calls and 16 model requests | Configured model | None. Holds no account identity | Book search through Librarian's path, account memory search, and Exa web search with page retrieval, each granted per request |
| Provenance | Classifies each Line for the emotional boundary, reviews every complete Muse candidate and memory nomination, and reviews every Sculptor curation proposal against its exact sources | One review per run with no tools. It checks each claim against frozen evidence and returns a typed verdict: pass, revise, or reject | Configured model | None. Every review starts from a fresh typed input | None |
| Sculptor | Proposes bounded curation over supplied memory records while preserving originals; judges memory surfacing offline; runs offline retrieval-improvement experiments | One proposal per run over a bounded record set. Declining is a valid output. Offline research tasks add a web search loop | Configured model | None. Receives only a bounded record set, with account identity excluded | None, except web search and page retrieval in offline research tasks |
| Memory and Policy Service | Deterministic application code, not an agent. The only writer of personal-memory and curation records | Deterministic rules | None | Owns the account-scoped memory store: immutable originals, curation layer, audit log | Not applicable |

**Table 6.** Agent roles.

Muse is the only role that writes reader-facing prose or sees the released conversation, including earlier replies, and it can neither release its own words nor write durable memory. Its tools are thin adapters that the application grants and executes: the model supplies an intent, and the application supplies the reader's exact wording, so Muse cannot substitute a paraphrase of its own as a search query.

Private boundary inference may inspect full-work candidates to identify an event the reader describes (`src/linger/orchestration/boundary.py`). Those candidates do not become answer evidence without a validated reading grant. The application applies the resolved boundary to answer-facing retrieval and assessment before supplying evidence to Muse. Only an explicitly declared chapter persists; inferred boundaries are resolved afresh on each request. Saved-progress reuse must also respect session corrections and retractions, an unresolved edge case described in Section 7.8.

Serendipity filters candidates for eligibility before ranking them. Equal declared top ratings produce a decline; whether the model recognises a semantic tie correctly remains an evaluation question. Its runs are capped at 14 tool calls and 16 model requests, enough for one book search, one web search, and a page retrieval for each web result, twice over (`src/linger/orchestration/connection.py`; component results in Section 7.4).

Provenance is the reason the rest of the design can afford model initiative elsewhere. Its review input is organised by trust level, separating policy and reading scope from frozen evidence and from untrusted tool outcomes. A finding of `spoiler` or `prompt_injection` forces outright rejection with no revision. A Provenance approval is necessary but never sufficient for release or for a write. Figure 9 shows a review that sent a draft back once before passing it.

```json
{
  "provenance_verdicts": ["revise", "pass"],
  "finding_codes": ["unsupported_claim"],
  "revision_count": 1
}
```

**Figure 9.** A recorded Provenance outcome. The first review found an unsupported claim and asked for a revision; the revised candidate passed.

Sculptor's proposals are bound to the content digest of the records it saw, reviewed independently by Provenance, and applied only by the Memory and Policy Service after the sources have been re-read and re-hashed. Declining to curate is a valid outcome, because a curator under pressure to produce a proposal would eventually propose a merge that loses information.

The Memory and Policy Service turns identity, policy, and reviewed candidates into auditable storage decisions. A capture requires trusted account scope, capture policy enabled, a nomination validated as an exact slice of the current message, an independent Provenance allowance, no sensitive content, and an atomic commit without overwrite. A turn that ends in a safe decline or the emotional boundary writes nothing, even if the nomination was approved.

Table 7 shows what each role can see and change during a live turn. Every agent's "can change" entry is no: the application holds all write and release authority. The see entries are qualified because each agent receives a different, bounded slice of the same data.

| Role | Current Line | Earlier session text | Book passages | Account memories | Web pages | Can write storage | Can release text |
|---|---|---|---|---|---|---|---|
| Muse | Yes | Released turns: at most eight turns and 16,000 characters | Only as evidence that `librarian_search` returns, within the reading boundary | Only as evidence that Serendipity returns | Only as evidence that Serendipity returns | No. Nominates one exact span | No. Drafts a candidate |
| Librarian | Yes | The reader's own earlier words, never Muse's replies | Yes. Full-work candidates only for private boundary inference; answer evidence only within the boundary | Only memories that mention the work, for boundary inference | No | No | No |
| Serendipity | Yes, as its search cue | No. The application uses earlier words only for its own privacy checks | Only through Librarian, within the reading boundary | Yes, through `search_memories`, with no account identity | Yes, when granted for the request | No | No |
| Provenance | Yes | Only reader statements the application has verified as exact text from this session | The frozen evidence under review | Cited memories, the nomination, and curation source records | Cited pages under review | No. Its approval is necessary but not sufficient | No |
| Sculptor | No | No | No; an offline chapter-cue task reads chapter text | 2 to 12 records per run, with account identity removed | Only in offline research tasks | No. Proposes curation | No |
| Application, including the Memory and Policy Service | Yes | Yes | Yes | Yes | Yes | Yes. The only writer | Yes. Only after review and deterministic checks |

**Table 7.** Who can see what and who can change what. Sources: each role's typed input in `src/linger/agents/*/models.py`, `src/linger/orchestration/boundary.py`, `src/linger/orchestration/curation.py`, and `src/linger/agents/serendipity/tools.py`.

Section 7.4 reports each agent's component evaluation, and Section 7.3 the scenarios that exercise the agents together.

### 3.2 Input boundary: controls before any model

Table 8 groups transport preprocessing and the subsequent checks in `run_chat_turn`. A check may transform the input, let it continue, or end the turn. Section 7.6 reports their contract tests.

**Application enforces:** request normalization, rate limits, inbound privacy and credential checks, language routing, injection rules, and fixed boundary replies. A detected first-person self-harm phrase skips the English guard. The injection filter runs before the fixed self-harm response, so a message matching both can receive the security decline.

**Agents decide:** only the emotional preflight. If earlier checks allow the turn to continue, tool-less Provenance classifies it as `continue_reflection` or `apply_boundary`. The application chooses the response.

| Check | Example Line | What happens | Code | Tests |
|---|---|---|---|---|
| Transport preprocessing | An 11th message from the same account within one minute, or invisible Unicode characters in a message | HTTP requests are rate-limited; request-schema normalization removes hidden characters before downstream use | `apps/backend/rate_limit.py`, `apps/backend/schemas.py`, `apps/backend/message_normalization.py` | `tests/test_chat_rate_limit.py`, `tests/test_message_normalization.py` |
| 1. Inbound privacy and credentials | An email address, phone number, or detected credential | DataFog redacts detected emails and phone numbers; detected credentials block the turn | `src/linger/contracts/security_validation.py`, `apps/backend/chat_turn.py` | `tests/test_security_validation.py` |
| 2. Language routing | A message detected as non-English | A fixed language reply, unless a detected first-person self-harm phrase exempts it from this guard | `src/linger/orchestration/language_guard.py`, `apps/backend/chat_turn.py` | `tests/test_language_guard.py`, `tests/test_chat_language_boundary.py` |
| 3. Injection rules | A request matching an adopted override or disclosure rule | A fixed security decline before emotional preflight | `src/linger/contracts/security_validation.py`, `apps/backend/chat_turn.py` | `tests/test_security_validation.py` |
| 4. Self-harm boundary | "I want to hurt myself", if no earlier check ended the turn | A fixed boundary reply without a model call | `src/linger/orchestration/emotional.py`, `src/linger/orchestration/self_harm_detection.py` | `tests/test_self_harm_detection.py`, `tests/test_emotional_boundary.py` |
| 5. Emotional preflight (Provenance, no tools) | A distressing disclosure, such as grief that is still raw | If classified `apply_boundary`, a fixed reply; no search or memory capture runs | `src/linger/orchestration/emotional.py` | `tests/test_emotional_boundary.py`; live suite in Section 7.4 |
| None of the above | "I've finished Chapter 2 of Alice. Her changes in size made me feel out of place." | Continues to Muse (Section 3.3) | `apps/backend/chat_turn.py` | |

**Table 8.** Transport preprocessing and turn-level input controls. The inbound detector covers emails and phone numbers; it is not a complete detector of all project-defined PII.

### 3.3 Reasoning boundary: typed hand-offs

Agents reach one another only through the application (Figure 1). Muse calls Librarian and Serendipity through tools the application grants and executes.

**Agents decide:**

1. **Triage.** Muse classifies the Line (`src/linger/orchestration/triage.py`).
2. **Drafting.** Muse writes the reply and chooses which granted tools to call.
3. **Book evidence.** Librarian infers how far the reader has read and judges whether each passage supports the request.
4. **Connections.** Serendipity chooses one supported connection, or declines.

**Application enforces:**

- **Tool grants.** Muse gets only the tools the triage result and reading context allow.
- **Exact wording.** Book searches use the reader's exact words, never a model's paraphrase.
- **Scope.** Answer-facing retrieval uses the resolved reading position. Private full-work boundary-inference candidates cannot enter Muse's evidence without a validated grant.
- **Typed hand-offs.** Every hand-off is a typed Pydantic object carrying only the fields the next step needs (Table 9). Full transcripts are never passed.
- **Permission in the input.** Each agent receives a scope saying what it may search. It returns identifiers that the application looks up again, so no agent can claim a permission it was not given.

| Hand-off | Input to output | Authority note |
|---|---|---|
| Application to Provenance, preflight | `EmotionalBoundaryInput` to `EmotionalBoundaryAssessment` | Current Line and versioned policy only |
| Application to Muse, triage | Current Line to a typed turn classification | Classification only; the application decides the tool grants |
| Application to Muse, draft | `MuseDraftInput` or `MuseRevisionInput` to `MuseCandidate` | A revision keeps the original turn's authority, and at most one is permitted |
| Muse to Librarian, via tools | `librarian_route`, `librarian_search` | Thin adapters. The model writes no book query; the application supplies the reader's exact spans |
| Application to Librarian | Boundary inference, event identification, book request planning, and evidence assessment inputs to typed decisions | Decisions are content-free. Spans must be exact reader text, and identifiers must resolve |
| Muse to Serendipity, via tool | `serendipity_explore` to `ConnectionProposal`, `MemoryRecall`, or `ConnectionDecline` | Fresh dependencies per request. The intent selects the skill |
| Application to Provenance, review | `ProvenanceInput` to `ProvenanceReview` | Fresh input with no history. A revision review carries finding resolutions |
| Application to Sculptor | `AccountScopedMemories` to `CurationProposal` or `NoCurationProposal` | Account identity excluded from the model input |
| Application to Provenance, curation | `CurationReviewInput` to `CurationProvenanceReview` | The verdict echoes the proposal digest unchanged |
| Application to Memory and Policy Service | Reviewed command carrying a digest | Accepted only when the digest matches an approving verdict and the sources are unchanged |

**Table 9.** Typed hand-offs, in the order they occur.

Figure 10 shows one recorded hand-off.

```json
{
  "tool_name": "librarian_search",
  "request": {
    "work_id": "pg11",
    "book_version_id": "pg11-v01b38ea4",
    "max_final_evidence": 5
  },
  "outcome": "success",
  "response": {
    "kind": "result",
    "outcome": "evidence_found",
    "evidence_strength": "sufficient",
    "strength_reason": "The requested reference to Alice's changes in size is directly …",
    "searched_scope": {
      "work_id": "pg11",
      "book_version_id": "pg11-v01b38ea4",
      "max_chapter_inclusive": 2
    }
  }
}
```

**Figure 10.** One Librarian hand-off as recorded for a turn. The request carries no search text: the application supplies the reader's exact words. The response states the scope it searched, here up to chapter 2.

### 3.4 Output boundary: review and release

Muse returns a candidate: the reply, a declaration of each piece of evidence with the reply spans it supports, and either one memory nomination or a reason for none.

**Agents decide:** Provenance reviews the candidate from a fresh input with no conversation history. It checks each declaration against the evidence and scans the whole reply for undeclared quotations, factual claims, and sensitive inferences. It passes the candidate, asks for one revision, or rejects it.

**Application enforces:**

- **Evidence binding.** Every declaration must bind to the request-scoped evidence index, which accepts only records retrieved for this request or cited earlier in the same session.
- **Verbatim quotations.** Each quotation is checked word for word against both the source record and the reply.
- **One release path.** Only text that passes review and these checks reaches the reader.
- **Safe decline.** Any failure ends in a fixed message that reveals nothing from the rejected candidate and writes nothing to storage.

A Provenance pass is necessary but never sufficient: a confident review cannot release a quotation the index cannot bind. Figure 4 in Section 2.6 shows a released reply in the web interface.

### 3.5 Memory boundary

Agents hold no state of their own: every agent run starts from a fresh typed input, and only the application writes storage (Section 2.4).

**Short-term memory.** The application gives Muse only released turns from the current session: at most the last eight turns and 16,000 characters (`apps/backend/sessions.py`). Rejected drafts never enter this history.

**Long-term memory** is kept per account.

**Agents decide:**

1. **Nomination.** Muse nominates at most one exact span of the reader's current message.
2. **Veto.** Provenance can veto the nomination.
3. **Curation.** After a commit, Sculptor may propose one change over a bounded set of stored records, such as a summary or a topic group. Provenance reviews it against the exact sources.
4. **Recall.** When the reader asks what they said before, Serendipity searches the account's memories and returns the reader's own words.

**Application enforces:**

- **Commit rules.** The Memory and Policy Service commits a nomination only if the turn was released, capture is enabled, and Provenance marked the nomination permitted and nonsensitive. Deterministic policy and exact-span checks must also pass. The reader sees a notice for every commit (`src/linger/orchestration/capture.py`). These checks do not eliminate the unresolved identity and offset limits in Section 7.8.
- **Curation rules.** An approved proposal is applied only if the records are unchanged since Sculptor read them. Originals are never edited, and every change is logged (`src/linger/orchestration/curation.py`).

Memory surfacing, where Sculptor judges whether stored history could help a later conversation, runs only in offline evaluation.

### 3.6 Prompt patterns

All five agents share the same prompt patterns. Table 6 gives each role's own reasoning pattern.

- **One agent per role, one skill per task.** Each role is one reusable PydanticAI `Agent`. For each run, the application selects a skill: task instructions, typed input, typed output, permitted tools, validators, and retry limits (`src/linger/agents/skills.py`). For example, Provenance runs `emotional-preflight`, `candidate-review`, or `curation-review` on the same agent.
- **Role rules, then task rules.** The agent's base instructions hold the role's purpose and authority rules from the prompt catalogue (`src/linger/prompts/prompt_catalog.yaml`). The selected skill adds the instructions for that task.
- **Instructions only for offered tools.** Muse's reflection skill adds its routing, grounding, or connection module only when the turn offers the matching tool (`src/linger/agents/muse/skills.py`). Each tool's description states when to call it (`src/linger/agents/muse/tools.py`).
- **Typed output, never free text.** Every run returns a Pydantic model. A validator that rejects the output sends the error back to the model, which retries up to the skill's limit of one to three times.
- **Declining is an output.** Serendipity can return `ConnectionDecline`, Sculptor `NoCurationProposal`, and memory surfacing `Defer` or `DoNotSurface`. A model never has to invent a result to satisfy the schema.
- **Input ordered by trust.** Provenance's review input separates policy and reading scope from frozen evidence and from untrusted tool outcomes (`src/linger/agents/provenance/models.py`).
- **Effort per task.** Muse drafts, Provenance candidate review, and Serendipity run at medium reasoning effort. Other live tasks use the shared low setting.
- **Fingerprinted prompts.** Each skill's digest covers its instructions, schemas, tools, validators, and retry limits. Every traced run records the digest (Section 6.2). Section 7.6 reports the contract tests for skill selection and fingerprints.

---

## 4. Explainable and Responsible AI Practices

### 4.1 Responsible AI across the lifecycle

Responsible AI practice is distributed across the lifecycle rather than concentrated in a final review.

- **Framing.** The specification excludes mental-health profiling, diagnosis, crisis routing, continuous monitoring, and unsolicited resurfacing. The emotional preflight exists to route a distressing disclosure away from the reflective path, not to assess the person.
- **Data.** Only public-domain works are used, each with a recorded source audit and content hash. Evaluation data is synthetic, generated by a model but adopted by a person, and no real user data is used for evaluation.
- **Design.** Authority is separated by component, and every input class is labelled by trust level, so book text, memories, web pages, and model candidates reach a reviewing model marked as data rather than instruction.
- **Development.** Prompts are versioned, packaged resources with automatically computed digests, and prompt changes pass human review.
- **Evaluation.** The three evaluation layers keep contract, component, and conversation claims apart, and any result from a model judge is labelled non-independent because the judge may share the model under test.
- **Operation.** Telemetry is metadata-only under a written contract, and no production configuration can enable content capture in telemetry.
- **Improvement.** Self-improvement loops produce human-reviewed proposals only and grant no runtime authority.

### 4.2 Explainability and traceability

Developers can inspect turns in the local diagnostic interface. Inspect and the agent map show the resolved context, each agent's outcome, the Provenance verdict and finding codes, the deterministic validation results, the release source, and the Logfire trace identifier. These diagnostics are excluded from the product-facing interface. The recorded decision path explains which controls ran; it does not establish that a model's semantic judgment was correct. Figure 5 in Section 2.6 shows the local Inspect view.

Evidence is separated from interpretation within the reply. Book quotations are verbatim and located, claims drawn from a web page carry an exact visible citation, and memory evidence is attributed as the reader's own words rather than as public fact. Every model span records the role, skill, configuration digest, hand-off origin and receiver, verdicts, retries, tokens, latency, and cost. Declines explain themselves through a fixed enumeration of causes rather than generated prose, which keeps the reason for a refusal auditable.

### 4.3 Fairness and bias mitigation

The corpus is small and old and contains dated cultural perspectives. Book claims must be attributed to their sources, and Provenance checks the complete reply for sensitive inferences, including those Muse did not declare. Capture requires its separate approval and deterministic policy checks. These controls reduce risk but do not establish perfect semantic detection. The emotional-content policy is a request-local interaction boundary rather than a label or score attached to the person.

The project has not run a persona-diversity evaluation testing whether equivalent reflections receive comparable treatment across readers of different backgrounds, and it makes no claim about fairness across reader populations.

### 4.4 Alignment with the Model AI Governance Framework

| Model AI Governance Framework heading | Linger practice |
|---|---|
| Internal governance structures | Written system specification and telemetry contract, issue tracking of decisions, and human review of prompt changes. Both branches have required status checks, with the candidate requirements still to align with the promotion policy in Section 6.1 |
| Level of human involvement | Human review for Ground truth adoption, prompt changes, capture-policy changes, and self-improvement proposals. The current release configuration requires approval in the protected `linger-release` environment before publication |
| Operations management | Source audits and content hashing, automatic configuration digests, repeatable scenario replay, a fixed failure taxonomy, and release evidence bound to a commit and image identity |
| Stakeholder interaction and communication | A visible notice for every committed capture, and consistent separation of the reader's words, source text, and the system's interpretation in every reply |

**Table 10.** Alignment with the Model AI Governance Framework.

The framework's generative-AI extension emphasises content provenance, which corresponds directly to the role of the Provenance agent and the evidence index.

---

## 5. AI Security Risk Register

Sixteen risks were identified using the OWASP Top 10 for LLM Applications. They fall into four groups: content that reaches the reader (R1 to R3, R7), content that leaves the system or crosses accounts (R4 to R6, R10, R16), the integrity of the pipeline (R8, R11 to R13, R15), and usability and cost (R9, R14).

| ID | Risk | Likelihood | Impact | OWASP category | Principal control | Evidence status |
|---|---|---|---|---|---|---|
| R1 | Indirect prompt injection through retrieved content or the Line | High | High | LLM01 | Message normalisation, untrusted labelling, application-owned grants, forced rejection on `prompt_injection` | Injection class blocked in both gate runs; triage flagged every override attempt in its completed runs; release-suite attack datasets adopted, live runs deferred |
| R2 | Fabricated or altered quotations and citations | High | High | LLM09 | Muse output validator, verbatim quotation checks, request-scoped evidence index | Citation precision 1.00 in the 17 August Librarian live suite; one uncited web claim passed the 27 September Provenance gate |
| R3 | Spoiler leakage beyond the reading boundary | Medium | High | LLM02 | Boundary resolved per request, scope applied to answer-facing retrieval, forced rejection on `spoiler` | Zero exposures in the retrieval benchmark and a 23-Scene audit; saved-progress retractions remain unresolved |
| R4 | Private wording leaking into web queries | Medium | High | LLM02 | Entry-point email/phone redaction, outbound credential checks, and a wording-overlap gate on queries and URLs | Offline checks exist; outbound protection for stored-memory and model-composed PII remains under review (`linger-lmt7`) |
| R5 | Cross-account memory exposure | Low | High | LLM02 | Account scope from the authenticated token only | Contract and API authorisation tests |
| R6 | Unsafe automatic memory capture | Medium | High | LLM02 | Independent capture veto and deterministic capture policy | Capture-veto recall 1.00 in both historical gate runs; durable event identity and nomination offsets remain unresolved |
| R7 | Over-reach on distressing disclosures | Medium | High | Not applicable | Deterministic self-harm check, tool-less preflight, fixed boundary reply | 8 of 8 preflight cases correct, single run |
| R8 | Output-gate bypass | Low | High | LLM05, LLM06 | Single application-owned release path; rejected drafts excluded from history | Contract tests and turn inspection |
| R9 | Over-refusal degrading usefulness | Medium | Medium | Not applicable | One bounded revision before decline; over-refusal reported as a first-class metric | Measured: 0.12 to 0.18 on responses, 0.11 to 0.33 on captures |
| R10 | Telemetry leaking reader content | Low | High | LLM02 | Telemetry contract, typed projection, exported-payload test | Contract tests |
| R11 | Prompt drift | Medium | Medium | Not applicable | SHA-256 configuration fingerprint on every span; reviewed prompt changes | Contract tests |
| R12 | Supply-chain and code vulnerabilities | Medium | Medium | LLM03 | Locked dependencies; Trivy and CodeQL gates in CI; actions pinned to reviewed commits | Full CI runs on `main` pull requests and candidate pushes. CodeQL also runs on `main` pushes. Both branches require checks, with candidate requirements still to align with Section 6.1 |
| R13 | Secrets exposure | Low | High | LLM02, LLM07 | Environment file excluded from version control and the image; dedicated protected release environments specified | Current release-environment protections remain unverified. No dedicated secret scanning |
| R14 | Cost and latency abuse | Low | Medium | LLM10 | Ten requests per minute per account; per-role request and tool budgets | Contract tests; counters are per process |
| R15 | Developer environment leaking into tests | Medium | Low | Not applicable | CI generates its own offline environment file | Observed once; tests should pin policy explicitly |
| R16 | Account compromise | Low | High | LLM02 | Salted scrypt password hashes; bearer tokens; account derived from the token on every route | API tests; no password reset or verification |

**Table 11.** AI security risk register. Likelihood and impact are the team's qualitative ratings. Evidence comes from Section 7.

The evidence varies by risk and evaluated configuration. R1 to R3, R6, R7, and R9 have historical live-model evidence. R4, R5, R10, R11, R14, and R16 have offline contract evidence, which covers the tested cases rather than every possible model output. R4 also has an unresolved privacy-policy change in current main. R12 is checked by required CI jobs, with remaining branch-policy verification described in Section 6.1. R13 has no dedicated secret scanning. R2 has a live counter-example: a release-gate run passed an uncited web claim that the reviewer should have sent back. R15 was discovered when tests inherited web-search policy from a developer's environment file. Section 7.8 records remaining implementation and evidence limits.

---

## 6. LLMSecOps Pipeline

The implemented workflows define a path from a change to a tested image, reviewed publication, and deployment. Figure 11 shows the current route with human approval. A complete release and deployment of the current implementation has not been verified.

![LLMSecOps loop: change, main pull request, CI, merge, checked promotion, candidate push CI, image checks, human approval, same-image GHCR publication, and Railway digest deployment, with release evidence feeding human review and proposals back to the next change](images/figure-llmsecops-loop.svg)

**Figure 11.** LLMSecOps sequence for the current manual publication route after candidate promotion. Full CI checks the merged candidate before the release workflow builds and checks an image. With live evaluation disabled, human approval in `linger-release` permits publication of that same image. After publication, the automatic promotion run deploys that digest to Railway. Sections 6.1 and 6.2 distinguish implemented checks from hosted settings and release evidence that remain unverified.

### 6.1 Change control and continuous integration

The documented workflow uses reviewed pull requests for code, prompt, and skill changes. It promotes a reviewed batch from `main` to `release-candidate`, whose resulting commit identifies the candidate (`docs/releasing.md`).

A read-only GitHub API check on 17 October 2026 shows both branches protected. `main` requires the seven CI checks in Table 12. `release-candidate` still requires those seven plus **Release promotion**, while the intended policy requires only **Release promotion** before merge. Its external branch settings still need to match that policy. The available token could not verify review requirements, administrator enforcement, bypass permissions, or up-to-date requirements. Hosted setup remains tracked in `linger-t1aw`. Promotion of the current implementation remains tracked in `linger-bjog`.

A maintained system specification records product scope, authority, release contracts, safeguards, and acceptance criteria. The separate telemetry contract defines what may be logged. Implementation proceeded through working slices: reviewed reflection, book grounding, connection discovery, capture and curation, then accounts, persistence, and release tooling.

Continuous integration in `.github/workflows/ci.yml` runs seven checks on pull requests to `main`, pushes to `release-candidate`, and manual dispatch. A push to `main`, including a merged pull request, runs only the two CodeQL checks. Pull requests to `release-candidate` run only **Release promotion**, which accepts only a same-repository promotion from `main`. Full CI then verifies the exact merged candidate commit before release can proceed.

CodeQL scans on `main` pushes refresh GitHub's default-branch security results and cannot trigger release. There is no scheduled scan. Without an eligible pull request, push, or manual dispatch, no new scan runs. Trivy's JSON workflow artifacts refresh on full CI runs, which also check newly disclosed dependency and image vulnerabilities.

These jobs make no paid model calls and use no provider secrets. All seven full CI checks passed for `main` commit `9a5c074` on 14 October 2026 ([CI run 38540172735](https://github.com/DesmondChoy/linger/actions/runs/38540172735)). That run is historical evidence for the named commit.

| Check | Evidence |
|---|---|
| Backend tests | Contract tests, including API authorisation, privacy boundaries, source preservation, evaluation contracts, and release rejection cases |
| Backend tests (embeddings) | Retrieval regressions against the real local embedding and reranker models |
| Frontend tests | Front-end and Ground-truth reviewer tests, lint, and production build |
| CodeQL (Python) and CodeQL (JavaScript/TypeScript) | Static security analysis; findings of severity 7 or above block the build |
| Dependency security | Trivy scan of dependency locks; HIGH or CRITICAL findings block |
| Image (amd64) | Container build, offline startup and persistence smoke test, image vulnerability scan |

**Table 12.** Configured CI checks.

The AI-specific security tests are part of the contract suite: release-gate and curation risk-code grading, emotional-boundary and privacy checks, and injected-content cases. Live-model evaluations run manually or through release checks when live evaluation is enabled. The retained component reports identify their date, model, and prompt digest; they measure those configurations rather than every later commit.

### 6.2 Versioning and release

Code is versioned in Git, and dependencies are locked in `uv.lock` and `pnpm-lock.yaml`. Corpus revisions are content-hashed, so a citation binds to an exact revision of an exact work. Every prompt and skill configuration carries a SHA-256 digest computed over its instructions, input and output schemas, tool permissions, validators, and retry limits, so any change to these alters the digest without anyone remembering to bump a version. Evaluation reports record the dataset digest, run identifier, model, and Git revision, adopted Ground truth records a hash of the approved bytes, and release evidence records the candidate commit and Docker image identity.

The release workflow is implemented in `.github/workflows/release-auto.yml`, `release.yml`, and `release-checks.yml`, and described in `docs/release-checks.md`. Successful push CI on the exact `release-candidate` commit can trigger release. In both evaluation modes, the workflow validates the candidate, builds a fresh image, runs Trivy, and checks offline startup and persistence. With live evaluation disabled, it records an intentional skip without a score and requires human approval in `linger-release` before publishing the same checked image to GHCR. The disabled evaluation switch does not stop image checks or publication.

When live evaluation is enabled, the workflow also runs the 22-Scene behavioural suite and live HTTP checks. Security failures, invalid adoption, missing observations, and missing evidence block publication. Human approval cannot override those blockers. `.github/release-config.json` currently sets both `live_evaluations_enabled` and `auto_publish_enabled` to false, with an uncalibrated automatic-publication threshold of 95. The current configuration therefore requires human approval for every eligible candidate.

After publication in the automatic promotion run, `.github/workflows/railway-deploy.yml` deploys the exact published GHCR digest to the existing Railway service. It does not rebuild from source. Manual candidate publication leaves deployment to the operator. The workflow contracts are covered by `tests/test_release_workflow_modes.py` and `tests/test_railway_release.py`, within the offline evidence described in Section 7.6. Current hosted environment protections and a complete release deployment remain unverified. No current-candidate release or deployment is claimed.

### 6.3 Monitoring and audit logging

Logfire provides three views. The Live view shows the trace hierarchy and per-role exchanges of a run, the Agents view aggregates runs, cost, and duration by role, and the Evals view holds evaluation datasets with expected and actual labels. Every failure carries a fixed stage, code, category, retryability flag, and owner, where the owner is the model, validation, or the application, so failures can be triaged without reading error text. No alert rules are configured; a deployed version would need them. Figure 12 shows one trace in the Live view.

![Logfire Live view of a Sculptor run with its input memories and typed output](images/logfire-trace.png)

**Figure 12.** A Sculptor run in Logfire's Live view during an evaluation run: its input memories (1) and its typed output, a decision not to curate (2). Content is visible only because evaluation runs use synthetic data under a separate evaluation identity.

Runtime spans are metadata-only, and an exported-payload test inspects what actually leaves the process rather than what the code intends to send. A separate evaluation identity may record synthetic content only. Every applied curation produces an immutable audit event, so the memory store carries its own modification history. The release tooling defines an approval record containing the publication route, registry digest, tested image, and CI run; this record format does not establish that a current release has completed.

### 6.4 Feeding failures back into development

One supervised retrieval-research loop has completed. Sculptor analysed recorded retrieval misses, researched a remedy, and proposed a specification. The owner approved its inputs and proposal; a developer implemented the change behind an evaluation-only option and measured it against the fixed pass mark. Section 7.4 reports the result and its cost. The agents gained no authority to change code, prompts, policy, or production settings.

Two operational loops remain specified future work: human-reviewed promotion of failure metadata into regression cases, and scheduled Sculptor proposals to curate a system playbook through pull requests. The scheduled playbook task is a proposal in `docs/specification.md`, not a running service.

---

## 7. Testing and Evaluation

This section answers two questions. The main one is whether the agents make good decisions (Sections 7.1 to 7.5). The supporting one is whether the application code enforces its rules (Section 7.6).

- **Measured boundary checks held in the retained replay batch.** It recorded no spoiler exposure, invented quotation, or unreviewed memory write. These results do not resolve the semantic counter-examples or outstanding boundary defects in Section 7.8.
- **41 of 53 test messages were handled correctly** in the latest full replay. Of the other 12, 5 were wrong decisions by an agent; the rest were provider or software errors that failed safely, plus one grading mistake.
- **The system is slow and does not yet handle several readers at once** (Section 7.7).

### 7.1 How agent quality is evaluated

Agent quality is evaluated at two levels, both with live models.

| | Component evaluation | Scenario replay |
|---|---|---|
| Question | Does one agent decide well when its inputs are fixed? | Does the whole system respond correctly across a conversation? |
| What runs | One agent | All agents, through `run_chat_turn`, as in production |
| Inputs | Fixed evidence for each case | Messages from a synthetic reader, with memories placed beforehand |
| Scale | 4 to 92 cases per agent, 3 to 5 repeats | 16 saved Scenarios |
| What it is for | Finding which agent caused a failure | Showing the system works as it would for a real reader |

**Table 13.** Two levels of agent evaluation.

**Why scenario replay is needed.** Contract tests and component evaluations each check one piece in isolation. Most failures a reader would notice happen between the pieces:

- Librarian retrieves the right passage, but Muse cites a different one.
- A reader describes the Caucus-race in *Alice* and stops where Alice sits alone, hearing footsteps. The system has to work out that she has reached the end of chapter 3 and must not mention later chapters. That needs the stored memory, Librarian's reading-position inference, Muse's draft, and Provenance's review to agree.
- A memory saved in one turn has to be found again in a later one.

Real readers' conversations were not available, and would be private if they were. Scenario replay therefore uses synthetic readers whose correct outcomes are decided in advance, and sends their messages through the same `run_chat_turn` function a real reader's messages go through.

Results are measured as follows. Appendix A defines every metric.

- **Safety:** the share of unsafe drafts blocked (block recall), against the share of safe drafts wrongly blocked (over-refusal).
- **Evidence:** the share of required passages that reach the reply (evidence recall), against the share of citations that are relevant (citation precision).
- **Repeats:** live models vary from run to run, so component cases run 3 to 5 times. A case passes "pass^k" only if every repeat passes.
- **Protocol:** retained results identify their evaluated configuration and adopted Ground truth. Later experiments fixed their pass mark and stop rule before scoring, with human approval of improvement-task prompts. Held-back exposure is reported per experiment: the completed Sculptor retrieval-research experiment reused a set already evaluated in Experiment 3, so it was not an untouched final test.

### 7.2 Scenarios and Ground truth

A Scenario is one synthetic reader with a history, a few test messages, and the outcome each message must produce. Table 14 shows two test messages from a real Scenario.

| | Test 1: reading position is clear | Test 2: reading position is unclear |
|---|---|---|
| Reader | Mara, an arts administrator who reads *Alice* in short stretches on her commute | Same reader |
| Memory placed beforehand | Her note that she stopped reading when Alice and the animals swam ashore from the pool of tears | Her note about Alice drinking from a bottle and ending up the wrong size, with the setting forgotten |
| Test message | "I carried on … the Dodo's race, Alice giving out the sweets and getting her own thimble back … I've just stopped with her alone, hearing footsteps … Could you quote the Dodo's exact announcement about who won and who gets prizes?" | "… she drinks from a bottle and her size gets in the way again … I can't place which bottle episode this is. Why does her attempt to make things easier leave her stuck?" |
| Must happen | Treat chapter 3 as her furthest point. Quote the Dodo's announcement exactly and use chapter 3 evidence only | Ask for a detail that tells the two bottle episodes apart. Give no book explanation until her position is known |
| Must not happen | Move to the next chapter because she hears footsteps, or hint at how the story ends | Pick a bottle episode, guess a position, or name candidate events in the question |

**Table 14.** Two test messages from the *Alice* reading-position Scenario.

The two tests use the same reader and related book questions, but vary both memory clarity and the corresponding message. They check whether the system answers when progress is supported and clarifies when it is ambiguous. They are not a controlled comparison in which only memory changes.

Section 1.4 defines the Scenario terms used below.

**How a Scenario is created.** Each Scenario passes through four stages, shown in Figure 13. A different party does each stage, so the model that writes a test never decides its answer key.

![Four-stage pipeline: a person designs, a model generates, an independent reviewer adopts, and the application replays and grades](images/figure-ground-truth-pipeline.svg)

**Figure 13.** How a Scenario and its Ground truth are created. The agents under evaluation receive only the Props and Lines; the Ground truth goes only to the grader.

1. **Design.** A person selects the Objectives to test and approves a generation design.
2. **Generate.** An authorised model writes the Backstory, Props, Lines, and a proposed Ground truth. Code validates the draft without any provider call.
3. **Adopt.** A reviewer independent of the generator adopts or flags every expected outcome in the review application (Figure 8). Adoption records a hash of the approved text, so any later change to an answer key is visible.
4. **Replay.** The application sends each Line through `run_chat_turn`, grades the result against the adopted Ground truth, and writes an analysis report for every run, including runs where everything passed (Figure 7).

**What the Scenarios cover.** The 16 saved Scenarios test:

- answering questions about each of the five books without spoilers, and asking for the reading position when it is unclear
- connections across books, memories, and the web, and declining when no good connection exists
- saving and tidying memories, and recalling them in later sessions
- sensitive content, which must never be saved
- planted instructions in memories, and direct attacks in the reader's message

**How a run is scored.** The Ground truth is fixed before any run. Each reply is then scored in two ways:

- **Automated checks** compare the reply with the adopted Ground truth: were the right passages cited, did anything go past the reader's position, was a question asked when one was needed. This gives a pass or a fail.
- **A person reads the replies**, because automated checks cannot judge whether an answer is actually good. Where a model judge is used instead, it is labelled as not independent.

### 7.3 Scenario replay results

The latest full replay ran 12 Scenarios on 27 and 28 September with `gpt-6-luna`. Table 15 counts the outcome of every test message.

| What the reader does | Test messages | Passed | Agent made a wrong decision | Error, failed safely | Correct but marked as failed |
|---|---:|---:|---:|---:|---:|
| Asks about a book they are reading (all five books) | 23 | 16 | 1 | 5 | 1 |
| Asks for a connection, or talks about something that needs none | 6 | 4 | 2 | 0 | 0 |
| Comes back in a later session | 3 | 3 | 0 | 0 | 0 |
| Has a memory saved and tidied | 21 | 18 | 2 | 1 | 0 |
| **Total** | **53** | **41** | **5** | **6** | **1** |

**Table 15.** Scenario replay, 27 and 28 September. A fourth later-session message has no automatic check; a person judged its use of memory correct.

The columns mean:

- **Agent made a wrong decision:** an agent judged the situation wrongly.
- **Error, failed safely:** the model provider failed (a rate limit or malformed output) or our own code had a bug. The reader got a safe fallback reply or a clarifying question, never a wrong answer.
- **Correct but marked as failed:** the reply was right, but the automated check rejected it.

The five wrong decisions were:

1. **Book.** The reader named an event ("the Pigeon") rather than a chapter. Librarian could not work out which chapter that was, so the reply did not quote the book.
2. **Connections (two cases).** The reader only wanted to talk about their own life, but Muse still searched books and the web for a connection.
3. **Memory.** Muse marked slightly the wrong part of the reader's message to save, so the saved text did not match the message exactly and was not stored.
4. **Memory.** When a fact changed over time, Sculptor grouped the old and new notes instead of summarising the current fact.

The all-five-agent Scenario stalled during this September batch and produced no completed batch result. Separate targeted runs supplied the stage-level analysis in Section 7.5; they are not additional observations in Table 15. The table also predates later Muse revision and security changes. Serendipity's self-improvement instructions and role-specific medium-reasoning change remain on a separate branch, so their results do not measure the current main configuration.

### 7.4 Component results

Each agent was also evaluated on its own, with fixed inputs. Table 16 summarises retained component measurements by date and configuration. It is not a fresh benchmark of current main.

| Agent | Suite, date, model | Headline result |
|---|---|---|
| Provenance | Release gate, 52 cases, 27 Sep, `gpt-6-luna` | Block recall 0.94 (one uncited web claim passed); over-refusal 0.12; capture-veto recall 1.00 |
| Provenance | Curation gate (12 cases), emotional preflight (8), claim mapping (4), 22 Sep | All targets met |
| Librarian | Retrieval benchmark, 12 queries, no language model | Reranked hybrid: evidence recall 0.92, citation precision 0.83; zero spoiler exposures in all five configurations |
| Librarian | Live run, 12 cases, 17 Aug, `gpt-5.6-luna` | Evidence recall 0.92, citation precision 1.00, zero spoiler exposures |
| Serendipity | Retained component suite, 46 cases × 5, 24 Sep, `gpt-5.6-luna`, skill digest `3cf0760f…` | 210/230 runs pass (0.913); 38 of 46 cases pass all five repeats |
| Muse | Reflection, 51 cases × 3, 30 Sep, `gpt-6-luna` | Hard-gate pass rate 0.94; no leaks |
| Muse | Turn triage, 92 cases × 3, 26 Sep, `gpt-6-luna` | Acceptable classification 0.99 to 1.00 |
| Sculptor | No committed component suite | Evaluated through the Scenarios (Section 7.3) |

**Table 16.** Retained component measurements. The Librarian live run predates two current skills. Serendipity's source is `evals/serendipity/reports/component-reliability-2026-09-24-prompt-3cf0760f.json`; its model differs from current main. The later 9 October score noted in Beads is excluded because its supporting artifact could not be recovered.

The completed Sculptor retrieval-research experiment is a separate offline comparison. Its owner approved the analysis, researched specification, and evaluation-only implementation before scoring (`docs/evaluation/retrieval-research-experiment-4-2026-10-01.md`).

| Condition | Practice needs with selected evidence | Reused held-back needs with selected evidence | Key learning |
|---|---|---|---|
| Stage 2 chapter-tag baseline | 17/20 | 16/20 | The initial candidate cutoff omitted useful passages |
| Approved round 1, 20 candidates per planned part | 20/20 | 20/20 | The fixed pass mark was met with no losses, at higher reading cost |

**Table 17.** Completed offline Sculptor retrieval-research comparison, 1 October 2026. The held-back set was reused.

The comparison used the same Librarian model and prompt, with one selection call per need per condition. Practice evidence volume rose from 1,278 to 4,837 words per need, about 3.8 times, and input tokens rose about 2.5 times. The held-back set had already been evaluated in Experiment 3. The loop stopped after meeting its predefined pass mark; the larger candidate setting is not active for readers.

### 7.5 Where the system loses quality

Table 18 follows each required book passage through the five-agent conversation: retrieved, kept by Librarian's assessment, passed to drafting, and cited in the reply.

| Scene | Retrieved | Assessed | Passed on | Cited | Items |
|---|---|---|---|---|---|
| 06 | 1.00 | 0.94 | 0.94 | 0.78 | 36 |
| 07 | 1.00 | 0.83 | 0.83 | 0.44 | 18 |
| 08 | 0.89 | 0.67 | 0.67 | 0.11 | 18 |
| 06 to 08 | 0.97 | 0.85 | 0.85 | 0.53 | 72 |

**Table 18.** Share of required book evidence surviving each stage, runs 6 to 15 excluding run 9.

Retrieval is not the bottleneck. Almost every required passage is retrieved. About 12 points are lost in Librarian's assessment, and about 32 more between drafting and review. The losses happen where one agent hands evidence to the next. Table 19 groups every observed failure using the categories of Cemri et al. (2025).

| Category | Observed failures in Linger |
|---|---|
| Specification and system design | Answer keys stricter than the requirement they encoded, later loosened and re-adopted; reviewer strictness about inferences such as "used to", which caused more recall failures than curation changed; instruction-only fixes that did not change model behaviour |
| Inter-agent misalignment | Required evidence dropped between retrieval and citation (Table 18); Serendipity choosing an identity comparison over the passages the question needed; a Muse revision dropping sources the first review had accepted; a candidate omitting a mandatory evidence declaration |
| Task verification | A second review objecting to text the first review passed, with no revision left; the reviewer accepting a wrong speaker attribution; an uncited web claim passing review; hard-gate passes with semantic defects |

**Table 19.** Observed failures, by the categories of Cemri et al. (2025).

### 7.6 Testing the application

These tests replace language models with stubs and check application contracts, validators, and known failure paths. Retrieval tests also exercise the real local embedding and reranker models. Passing tests establish the covered behavior; they do not establish live semantic reliability. At `main` commit `9a5c074`, CI on 14 October passed 3,481 core tests and seven embedding tests, 3,488 backend tests in total. Table 20 retains the earlier 6 October breakdown of 3,172 tests at `48f9524`; its area counts have not been recounted for the newer commit.

| Area | Tests | What the group establishes |
|---|---:|---|
| Librarian, retrieval, and corpus | 681 | Boundary decisions grant nothing without support; retrieval never returns records above the ceiling; every corpus revision hashes and parses identically |
| Synthetic evaluation and release tooling | 523 | Ground-truth structures validate deterministically; a component pass cannot become an Objective pass; release blockers cannot be overridden |
| Accounts, API, and chat-turn orchestration | 425 | Only released turns enter history; every release has a recorded verdict; account scope comes from the login token; rate limits and message guards run before any agent |
| Provenance review paths | 400 | Fixed finding codes; forced rejection on spoiler and injection; every prior finding resolved on revision; curation verdicts bound to the digest |
| Cross-cutting contracts, safety detectors, and deployment | 373 | Supported-claim spans are exact; evidence budgets fail closed; self-harm and instruction-leak detectors; usage limits; deployment readiness and security-gate parsing |
| Serendipity and web access | 334 | Historical query/URL privacy cases, permitted search leads, and exact-record recall; current outbound PII coverage remains under review |
| Sculptor and Memory and Policy Service | 332 | Originals are immutable; tombstones are reversible; capture requires nomination, policy, and no veto |
| Runtime skills and fingerprints | 72 | Skill selection is explicit; digests change with instructions, schemas, tools, validators, or retries |
| Telemetry redaction | 32 | Exported payloads contain only contract-permitted fields; failures classify by exception type, not text |

**Table 20.** Historical backend test breakdown at `48f9524`, 6 October 2026. These area counts sum to 3,172; current CI totals are stated above.

Table 21 lists every kind of test and where it runs.

| Type | What it covers | Where it runs | Section |
|---|---|---|---|
| Unit and contract tests | Authority boundaries, validators, retry limits, retrieval scope, capture policy, account authorisation, telemetry redaction, with mocked models | Full CI, on `main` pull requests, candidate pushes, and manual dispatch | 7.6 |
| Retrieval regression tests | Retrieval with the real local embedding and reranker models | Full CI | 7.6 |
| Front-end tests | Front-end behaviour, lint, and production build; the Ground-truth review application | Full CI | 6.1 |
| AI security tests | Release-gate and curation risk codes, injection and policy-override classes, emotional boundary, privacy gate, instruction-leak and self-harm detectors | CI (mocked) and live component suites | 7.4, 7.6 |
| Static and dependency security analysis | CodeQL for Python and TypeScript; Trivy for dependency locks and the container image | Full CI, plus CodeQL-only scans on `main` pushes | 6.1 |
| Container and deployment tests | Image build, offline startup and persistence, readiness checks, live HTTP and streaming turns | CI and release checks | 6.2 |
| Component evaluations | Each agent's decisions with a live model and fixed evidence | Manual, reports committed | 7.4 |
| End-to-end scenario replay | Whole conversations through the production chat-turn boundary against human-adopted Ground truth | Manual and release checks | 7.3 |
| Release behavioural suite | 22 Scenes covering grounding, memory retrieval, connections, sensitive inference, memory injection, and direct attacks | Release checks when live evaluation is enabled, currently disabled | 6.2 |

**Table 21.** Kinds of test and where they run.

### 7.7 Cost, speed, and load

| Measure | Value | Source |
|---|---|---|
| Model calls per grounded turn | At least four: preflight, triage, draft, and review, plus Librarian's judgments inside tool calls | Turn structure |
| Model requests per Line, connection Scene | 11 to 15 | Five-agent Scenario, Scene 07, five repetitions, `gpt-6-luna` |
| Input tokens per Line, connection Scene | 104,000 to 222,000; mean by stage: Muse draft 55,000, Provenance review 54,000, Muse revision 30,000, Librarian assessment 10,000 | As above |
| End-to-end latency, grounded turn | 82 to 90 s in three observed turns | Live turns, 19 Sep, `gpt-5.6-luna` |
| Librarian live case latency | Mean 13.7 s, p95 27.9 s | Librarian live run |
| Retrieval-only latency | p95 0.46 s on local models, zero token cost | Retrieval benchmark |
| Turn triage latency | Median 1.45 s, p90 3.0 s | Triage suite |
| Muse reflection instructions | About 6,900 words; Provenance candidate review about 5,700 words | Skill sizes |

**Table 22.** Cost and latency per turn.

Most tokens go to the two roles that read the most: Muse and Provenance. Their instructions restate rules that code already enforces, which is the target of a planned cost reduction.

A 29 September development record describes a load test with synthetic readers on `gpt-6-luna`. Table 23 reproduces its historical notes. The referenced harness and raw reports could not be recovered for this report, so its timing, cost, and isolation observations have not been independently rechecked. The test is not evidence of current-main capacity.

| Recorded run | Answered | Safely declined | Median / p95 latency | Cost | Cross-reader data exposure reported |
|---|---|---|---|---|---|
| 5 readers, one after another | 13 of 15 | 2 | 22 s / 85 s | US$0.15 | None reported |
| 5 readers at once, book questions (two runs) | 6 and 5 of 15 | 9 and 10 | 45 to 46 s / 58 to 95 s | US$0.05 each | None reported |
| 5 readers at once, light questions | 5 of 15 | 10 | 11 s / 52 s | US$0.03 | None reported |
| 3 readers at once, light questions | 6 of 9 | 3 | 17 s / 28 s | US$0.02 | None reported |

**Table 23.** Historical load observations from 29 September, retained in development notes and `linger-qt84`; raw artifacts are unavailable.

The notes attribute the concurrent declines to provider rate limits and report no cross-reader exposure. These observations indicate a service-reliability problem under concurrency. They do not isolate all application contributions or establish general account-isolation guarantees. Recovering reproducible load evidence and demonstrating a service fix remain open in `linger-qt84`.

### 7.8 Limitations

- **Reader value is not measured.** No real readers used the system.
- **No comparison with a simpler design.** No single-agent version was built, so the results show how this structure behaves, not how much better it is than an unstructured one.
- **No fairness evaluation across reader backgrounds.**
- **Current concurrent-reader capacity is unverified.** Historical notes cover at most five readers, with unavailable raw load artifacts.

Several implementation limits remain open. Saved reading progress can override a session retraction (`linger-ilo4`), and the title parser can mistake reading narration for a title (`linger-qsqm`). Outbound PII coverage requires review after the merged security change (`linger-lmt7`). These defects limit claims about boundary resolution and privacy beyond the tested cases.

Capture still needs server-owned durable event identity and verified nomination offsets (`linger-gmr.8`, `linger-dxep`, `linger-n4h`). Derived-memory lineage and completely omitted memory declarations need stronger recall and release checks (`linger-gn7a`, `linger-s82k`). Capture-triggered curation exists, but independent semantic calibration, approval of capture-produced records as upstream evidence, and a verified capture-to-recall benefit remain incomplete (`linger-a4u.1`, `linger-a4u.4`). Historical passing checks do not close these obligations.

| Threat | Effect on the results |
|---|---|
| One provider, two models | All live results use OpenAI models, and the default changed from `gpt-5.6-luna` to `gpt-6-luna` during the project. Results from different dates are not directly comparable, and the reviewer's trade-off moved with the model |
| Correlated failure | Drafter and reviewer may be the same model with different context. A blind spot shared by both is caught only by the deterministic checks, which cover only what can be checked mechanically |
| Non-independent judges | Model judges may share the model family under test; they are labelled as such, and no hard gate depends on them |
| Small case sets | Suites of 4 to 52 cases are regression guards, not population estimates |
| Synthetic data | Scenarios are authored by a model and adopted by people, not collected from readers, and the corpus is five old public-domain works |
| Moving answer keys | Some Ground truth was loosened and re-adopted during the project. Each adoption is hashed and identified, so results state which answer key they used, but a loosened key can make a later result look like an improvement |
| No comparison condition | No single-agent or ablated architecture was evaluated, so the results show how the structure behaves, not how much better it is than an unstructured alternative |

**Table 24.** Threats to validity.

---

## 8. Reflection

### 8.1 Key findings

Seven findings emerge from the evidence in Section 7. Each is stated with the evidence behind it and what it implies.

**Finding 1: Deterministic boundaries and semantic review need different evidence.** Answer-facing retrieval applies the resolved chapter ceiling before supplying evidence to Muse, and the Memory and Policy Service alone writes personal-memory and curation records. Private boundary inference may inspect the full work without granting those candidates to the reply. The reported replay batch observed no spoiler exposure or unreviewed memory write. Semantic review still passed an uncited web claim and a wrong speaker attribution in separate evaluations. These results support deterministic scope and write controls while showing that citation binding alone cannot establish factual correctness. The current boundary and capture defects in Section 7.8 also require regression coverage before broader guarantees can be made.

**Finding 2: The reviewer's statelessness protects it but also makes it inconsistent.** Provenance reviews every candidate from a fresh context, so a draft cannot argue with it and earlier conversation cannot persuade it. The same property means that the review of a revised draft does not know what the first review accepted. In ten repetitions of one Scene, three of the four declines were a second review objecting to text the first review had passed, with no revision left. Re-reading the four loop declines showed a mixed picture: in two, the second review was right, because Muse had reworded sentences that no finding named; in the other two, the first review had been incomplete. The fix was structural rather than an instruction to the reviewer. Application code now lets Muse rewrite only the sentences a finding names, and revisions were released in five of six cases against five of ten before. An isolation property chosen for security has a consistency cost, and constraining what can change between rounds proved cheaper than giving the reviewer memory.

**Finding 3: Separation of duties is not independence.** Drafter and reviewer can be the same model given different context. In one Pinocchio passage the speaker follows only from the alternating dialogue, and Muse, Provenance, and a focused single-claim reviewer all accepted the wrong speaker. Raising Provenance's reasoning effort from low to medium did not help: it rejected the wrong attribution in two of three reviews either way and took two to five times as long. More reasoning cannot repair a blind spot the drafter and reviewer share. Independence would require a different model or a mechanical check, and the deterministic checks cover only what can be stated mechanically.

**Finding 4: In a fail-closed pipeline, reliability multiplies.** Every stage that can decline adds a chance of declining. A connection Scene in the five-agent Scenario makes about eight to ten model calls, and all four connection Scenes must succeed in the same run. With those Scenes passing in four, three, zero, and one of the last five runs, the chance of all four passing together was effectively zero, and still only about five per cent if the weakest Scene passed half the time. Because each failure is a safe decline, the cost appears as friction for the reader rather than harm, which is the trade the architecture was built to make. But the price rises with every agent added in series, because each one raises the reliability every other agent needs.

**Finding 5: The bottleneck moved from retrieval to the hand-offs.** Early effort went into retrieval, where five strategies were benchmarked and reranked hybrid retrieval was chosen. From the eighth run of the five-agent Scenario onwards, retrieval found every required passage in every run, yet only 53 per cent of required passages were finally cited. About twelve points were lost in Librarian's evidence assessment and about thirty-two across selection, drafting, and review. The component that is easiest to benchmark had stopped being the limit well before end-to-end pass rates could show it, and only stage-by-stage measurement revealed where to work next.

**Finding 6: Structure held where instructions did not.** The changes that lasted changed the shape of a task or added a deterministic check whose error flowed back into the model's own bounded retry. Giving Librarian's assessor per-part candidate pools and short record labels shrank its input from sixty passages to fourteen while every required passage still reached it, and planning each named event as its own request part took the comparison Scenes from no passes to seven in ten attempts. A check that reports a dropped source back to Muse caught every revision that had lost one. By contrast, Serendipity ignored an instruction that a winning connection must cover each named source, a ranking instruction moved one selection in three runs and was not adopted, and a clarification of the reviewer's permissions was reverted after its controls moved the wrong way. In this system, prompts were the least reliable lever.

**Finding 7: A model change moves the trade-off, not just the quality.** When the default model changed from `gpt-5.6-luna` to `gpt-6-luna`, Provenance's over-refusal fell from 0.18 to 0.12 and its block recall fell from 1.00 to 0.94 on the same 52 cases. The new model was not better or worse overall; it sat at a different point between safety and usefulness. A model upgrade is therefore a release in its own right and needs the full evaluation suite. Configuration fingerprints and dated reports are what made the shift visible at all.

### 8.2 Lessons for building multi-agent systems

- **Apply deterministic limits before answer generation.** Restrict answer-facing search by the validated reading grant and keep personal-memory writes in deterministic code; reserve model review for semantic judgments.
- **Constrain what changes between agent rounds.** A stateless reviewer is robust to manipulation but inconsistent with itself; limiting a revision to the flagged sentences restored consistency without giving the reviewer memory.
- **Budget reliability across the chain.** Every agent placed in series multiplies the chance of a decline. Prefer fewer serial judgments, and give each one a narrow, checkable task.
- **Keep rules in code and judgment in prompts.** Once a rule is enforced in code, restating it in a prompt adds cost without benefit. Loading only the instruction modules relevant to the granted tools cut Muse's input from about 25,000 to about 16,000 tokens per run with no change in hard-gate results.
- **Measure survival at every hand-off.** End-to-end pass rates say that something failed; per-stage survival says where.

### 8.3 Lessons for evaluating multi-agent systems

- **A pass is a sample until it is repeated.** Re-running ten Serendipity cases five times each gave a run pass rate of 0.70 with only five cases passing every repeat, and fifteen five-agent runs spanned seven system variants, too few per variant to separate improvement from variance. The repetition protocol in Section 7.1 came late, so several results in Section 7 remain single runs.
- **Hard gates overstate quality.** All three connection passes in two late five-agent runs had semantic defects, because the gates check that sources were cited rather than what the reply says about them. Human semantic review is part of the measurement, not an optional extra.
- **Answer keys are hypotheses too.** Two Scenes' expected outcomes were stricter than the requirement they encoded and were loosened and re-adopted. Hashing each adoption keeps this auditable, but a loosened key can make a later run look like an improvement, so results must name the key they used.
- **Isolate before measuring end to end.** The first curation-and-recall experiment varied in triage, search wording, drafting, and review at once and produced a null result about curation. Re-asking the question by measuring memory search directly was more informative.
- **Write the pass mark down before running.** Pre-registering the threshold, the stop rule, and each Scene's expected direction stopped results being read selectively after the fact.

### 8.4 Individual reflections

*[To be completed by each team member. Each member should address what they would do differently, and what building this system changed in their understanding of multi-agent LLM systems. Useful prompts: which architectural boundary proved hardest to hold in practice, what surprised you about evaluating a non-deterministic system, and what you would prioritise first given another two weeks.]*

### 8.5 Future work

Six items are listed in priority order.

1. **Run the release suite live.** The memory-injection and direct-attack Scenarios have adopted Ground truth but no live run, and they are the strongest available test of the system's resistance to malicious input.
2. **Repeat the single-run results.** Re-run the Provenance gates, the emotional preflight, and the Librarian live suite with repeats on the current model, and report them under pass^k.
3. **Reduce evidence loss between agents.** Target Librarian's under-selection and the drafting stage's citation choices, the two places Table 18 shows evidence is lost, without loosening the reading boundary.
4. **Reduce over-refusal and cost together.** Move rules that code already enforces out of the Muse and Provenance instructions, accepting the change only if the repeated measurements do not regress.
5. **Add a comparison condition.** Evaluate an ablated configuration, such as drafting without independent review, on the same Scenarios, so that the contribution of the structure can be measured rather than inferred.
6. **Deploy and load-test.** Publish an approved image to a multi-account test environment, load-test beyond five readers with a higher provider rate limit, and configure alerting.

---

## Appendix A. Metric definitions

| Metric | Definition |
|---|---|
| Block recall | Unsafe candidates blocked ÷ unsafe candidates |
| Over-refusal rate | Benign candidates blocked or sent back ÷ benign candidates |
| Code precision | Blocked candidates with the correct finding code ÷ blocked candidates |
| Capture-veto recall | Unsafe nominations vetoed ÷ unsafe nominations |
| Capture over-refusal rate | Safe nominations vetoed ÷ safe nominations |
| Decoupling accuracy | Cases where the response and capture decisions were each correct independently ÷ cases |
| Evidence recall | Required passages covered by released evidence ÷ required passages |
| Citation precision | Released citations that are relevant ÷ released citations |
| Evidence-strength accuracy | Cases where the sufficient, weak, or none judgment matches the expected label ÷ cases |
| Spoiler exposure count | Released records or reply facts beyond the permitted boundary |
| Run pass rate | Passing runs ÷ total runs across all cases and repeats |
| pass^k | A case passes only if all k repeated runs pass |
| Stage survival | Required evidence items present at a pipeline stage ÷ required evidence items |
| Recall@5 | Mean, over relevant records, of the chance that a top-five search result stands for that record, averaged over tie orders |

## Appendix B. Related work

Linger draws on four areas of prior work.

**Retrieval-augmented generation.** Grounding model output in passages retrieved at request time (Lewis et al., 2020) is the standard defence against fabricated facts. Linger combines lexical BM25 retrieval (Robertson and Zaragoza, 2009) with dense retrieval and cross-encoder reranking, a combination Anthropic's contextual-retrieval study reports substantially reduces retrieval failures (Ford, 2024). Retrieval alone does not make an answer faithful, and ordinary retrieval does not respect a reader's position in a book; Linger bounds retrieval before search and treats retrieved passages as evidence to verify rather than context to prompt with.

**Verification and provenance.** ScientistOne (Meng et al., 2026) requires every claim in a generated research paper to trace through recorded supporting claims to a grounding source, built into generation rather than audited afterwards. Linger applies the same idea to conversation: every evidence declaration names the reply spans it supports, and the reviewer checks both the mapping and the unmapped remainder. Linger adds a chain of authority to the chain of evidence, because evidence must also be permitted for this reader and request.

**Multi-agent failures and harness design.** Cemri et al. (2025) analysed over 1,600 traces from seven multi-agent frameworks and found that most failures arise from specification and coordination rather than model limits, in three categories: specification issues, inter-agent misalignment, and task verification. Anthropic's guidance on context engineering argues for minimal, curated context per model call (Rajasekaran et al., 2025), and Weng (2026) locates near-term improvement in the harness of typed contracts and gates around a model. These shaped Linger's typed hand-offs, per-agent context projections, and human-reviewed improvement loops.

**Security and evaluation of LLM agents.** Greshake et al. (2023) showed that instructions planted in retrieved content can redirect an LLM application, and the OWASP Top 10 for LLM Applications (OWASP, 2025) supplies the vocabulary of the risk register. Yehudai et al. (2025) survey agent evaluation and identify cost, safety, and robustness as its least developed areas, and Xia et al. (2025) argue for evaluation as a continuous governing function across development and operation, the model Linger's evaluation layers and release gate follow.

## References

Cemri, M., Pan, M. Z., Yang, S., et al. (2025). Why do multi-agent LLM systems fail? *Advances in Neural Information Processing Systems 38, Datasets and Benchmarks Track*. arXiv:2503.13657.

Ford, D. (2024). *Introducing contextual retrieval*. Anthropic.

Greshake, K., Abdelnabi, S., Mishra, S., Endres, C., Holz, T., and Fritz, M. (2023). Not what you've signed up for: Compromising real-world LLM-integrated applications with indirect prompt injection. *Proceedings of the 16th ACM Workshop on Artificial Intelligence and Security*.

Infocomm Media Development Authority and Personal Data Protection Commission. (2020). *Model artificial intelligence governance framework* (2nd ed.). Singapore.

Infocomm Media Development Authority and AI Verify Foundation. (2024). *Model AI governance framework for generative AI*. Singapore.

Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W., Rocktäschel, T., Riedel, S., and Kiela, D. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. *Advances in Neural Information Processing Systems, 33*.

Meng, R., Dalvi Mishra, B., Chen, J., Li, C.-L., Goyal, P., Parmar, M., Song, Y., Song, Y., Sinha, R., Ranganathan, P., Gokturk, B., Yoon, J., and Pfister, T. (2026). *ScientistOne: Towards human-level autonomous research via chain-of-evidence*. arXiv:2605.26340.

OWASP Foundation. (2025). *OWASP Top 10 for large language model applications*.

Rajasekaran, P., Dixon, E., Ryan, C., and Hadfield, J. (2025). *Effective context engineering for AI agents*. Anthropic.

Robertson, S., and Zaragoza, H. (2009). The probabilistic relevance framework: BM25 and beyond. *Foundations and Trends in Information Retrieval, 3*(4), 333 to 389.

Weng, L. (2026). *Harness engineering for self-improvement*. Lil'Log.

Xia, B., Lu, Q., Zhu, L., Xing, Z., Zhao, D., and Zhang, H. (2025). *Evaluation-driven development and operations of LLM agents: A process model and reference architecture* (Version 3). [arXiv:2411.13768v3](https://arxiv.org/abs/2411.13768v3).

Yehudai, A., Eden, L., Li, A., Uziel, G., Zhao, Y., Bar-Haim, R., Cohan, A., and Shmueli-Scheuer, M. (2025). *Survey on evaluation of LLM-based agents*. arXiv:2503.16416.
