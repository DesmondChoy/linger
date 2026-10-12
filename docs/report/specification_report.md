# Linger: A Provenance-First Multi-Agent Reflection Companion

Team 9 — Desmond Choy, Kevin Manuel Lee, Kay Mei Leong, Yuen Ying Jodie Loke
[authors to confirm names, order, and affiliations]

19 September 2026

---

> **Author notes. Delete this block before submission.**
> Written against repository revision `d26fa6a`. Every number cites an
> artefact committed at that revision. Outstanding items:
> 1. Confirm the author list, order, and per-agent ownership.
> 2. Write the team's reflection in Section 10.2, where a placeholder is marked.
> 3. Fill the placeholder rows in Tables 6, 8, 11, 12, 13, and 16 and update Appendix C.
> 4. Re-run the Librarian live evaluation on the current prompt digest.
> 5. Update the scenario index's live-result column from the iteration-18 batch.
> 6. Add a persona-diversity evaluation or keep it as the stated limitation in Section 6.3.
> 7. Complete the reference list in the required citation style, including Pydantic AI, Logfire, Exa, `bm25s`, and `fastembed` documentation.
> 8. Decide whether to build the container image, deployment job, and load test before submission or leave them as future work.
> 9. Figures 4 to 8, 10, and 11 were captured from the local prototype on 19 September 2026 (three live turns on `openai:gpt-5.6-luna`). The Logfire figures reuse the annotated screenshots of 14 September 2026. Replace them if the UI changes before submission.
> 10. Appendix E now carries the per-agent design detail; decide how much of it stays in this report and how much moves to the individual reports.
> 11. The at-a-glance tables in Section 5, Table 19, and Table 17 were derived from the report text rather than from the code. Check them against the code before submission. The OWASP column in Table 19 is an editorial addition.

---

## Table of Contents

- [Abstract](#abstract)
- [1. Introduction](#1-introduction)
  - [1.1 Problem](#11-problem)
  - [1.2 Approach](#12-approach)
- [2. Scope, Contributions, and Related Work](#2-scope-contributions-and-related-work)
  - [2.1 Scope and constraints](#21-scope-and-constraints)
  - [2.2 Contributions](#22-contributions)
  - [2.3 Related work](#23-related-work)
- [3. Design and Architecture](#3-design-and-architecture)
  - [3.1 Design principles](#31-design-principles)
  - [3.2 System overview and logical architecture](#32-system-overview-and-logical-architecture)
  - [3.3 The chat-turn workflow](#33-the-chat-turn-workflow)
  - [3.4 The output release contract](#34-the-output-release-contract)
  - [3.5 A worked turn](#35-a-worked-turn)
  - [3.6 Runtime skills](#36-runtime-skills)
  - [3.7 Inter-agent communication](#37-inter-agent-communication)
  - [3.8 Physical architecture and deployment](#38-physical-architecture-and-deployment)
  - [3.9 Technology choices](#39-technology-choices)
- [4. Evaluation Framework](#4-evaluation-framework)
  - [4.1 Three layers of evidence](#41-three-layers-of-evidence)
  - [4.2 Metric definitions](#42-metric-definitions)
  - [4.3 Objectives and scenario generation](#43-objectives-and-scenario-generation)
  - [4.4 How results are reported](#44-how-results-are-reported)
- [5. The Agents and the Memory & Policy Service](#5-the-agents-and-the-memory--policy-service)
  - [5.1 Muse — the conversation](#51-muse--the-conversation)
  - [5.2 Librarian — reading boundaries and book evidence](#52-librarian--reading-boundaries-and-book-evidence)
  - [5.3 Serendipity — connection discovery and memory recall](#53-serendipity--connection-discovery-and-memory-recall)
  - [5.4 Provenance — independent review](#54-provenance--independent-review)
  - [5.5 The Memory & Policy Service](#55-the-memory--policy-service)
  - [5.6 Sculptor — memory curation and surfacing](#56-sculptor--memory-curation-and-surfacing)
- [6. Explainable and Responsible AI](#6-explainable-and-responsible-ai)
  - [6.1 Alignment across the lifecycle](#61-alignment-across-the-lifecycle)
  - [6.2 Explainability and traceability](#62-explainability-and-traceability)
  - [6.3 Fairness and bias](#63-fairness-and-bias)
  - [6.4 Governance alignment](#64-governance-alignment)
- [7. AI Security Risk Register](#7-ai-security-risk-register)
- [8. LLMSecOps Pipeline](#8-llmsecops-pipeline)
  - [8.1 Engineering method and change control](#81-engineering-method-and-change-control)
  - [8.2 Automated testing](#82-automated-testing)
  - [8.3 Versioning and tracking](#83-versioning-and-tracking)
  - [8.4 Deployment](#84-deployment)
  - [8.5 Monitoring and alerting](#85-monitoring-and-alerting)
  - [8.6 Logging and auditability](#86-logging-and-auditability)
  - [8.7 Automating the lifecycle](#87-automating-the-lifecycle)
- [9. System-Level Evaluation](#9-system-level-evaluation)
  - [9.1 Automated contract tests](#91-automated-contract-tests)
  - [9.2 Scenario replay](#92-scenario-replay)
  - [9.3 Cost and latency](#93-cost-and-latency)
  - [9.4 Guarantee traceability matrix](#94-guarantee-traceability-matrix)
  - [9.5 Threats to validity](#95-threats-to-validity)
- [10. Findings, Reflection, and Future Work](#10-findings-reflection-and-future-work)
  - [10.1 Findings](#101-findings)
  - [10.2 Reflection](#102-reflection)
  - [10.3 Future work](#103-future-work)
- [References](#references)
- [Appendix A. Repository map](#appendix-a-repository-map)
- [Appendix B. Metric definitions](#appendix-b-metric-definitions)
- [Appendix C. Metric coverage by agent](#appendix-c-metric-coverage-by-agent)
- [Appendix D. AI security risk register](#appendix-d-ai-security-risk-register)
- [Appendix E. Agent design detail](#appendix-e-agent-design-detail)
  - [E.1 Muse — the conversation](#e1-muse--the-conversation)
  - [E.2 Librarian — reading boundaries and book evidence](#e2-librarian--reading-boundaries-and-book-evidence)
  - [E.3 Serendipity — connection discovery and memory recall](#e3-serendipity--connection-discovery-and-memory-recall)
  - [E.4 Provenance — independent review](#e4-provenance--independent-review)
  - [E.5 The Memory & Policy Service](#e5-the-memory--policy-service)
  - [E.6 Sculptor — memory curation and surfacing](#e6-sculptor--memory-curation-and-surfacing)
- [Appendix F. Related work and technology rationale](#appendix-f-related-work-and-technology-rationale)
  - [F.1 Related work](#f1-related-work)
  - [F.2 Technology choices in full](#f2-technology-choices-in-full)
- [Appendix G. List of figures and tables](#appendix-g-list-of-figures-and-tables)

---

## Abstract

Large language models make it easy to build a companion that talks with a person about their reading and their life. They make it equally easy to build one that misquotes the book, invents what the person said, spoils a chapter they have not reached, or quietly stores something about them that should never have been kept. Linger is an academic prototype that treats these failure modes as the central design problem rather than as quality issues to be tuned away.

Linger is a personal reflection and memory companion grounded in five public-domain books. It is built as five specialised reasoning agents (Muse, Librarian, Serendipity, Provenance, and Sculptor) around one deterministic Memory & Policy Service. The governing rule is that no model may release its own output or widen its own authority. Every reply is a typed candidate that is reviewed by a tool-less Provenance agent and then validated by application code against a request-scoped evidence index before it is shown. Every memory write passes through the same review and a deterministic commit.

This report describes the design method, the runtime-skill mechanism that binds each agent to typed contracts and auditable prompt fingerprints, the spoiler-safe retrieval pipeline, and a three-layer evaluation method that keeps contract tests, live component evaluations, and end-to-end scenario replay apart. On the committed evidence, the Provenance release gate blocks 100 % of unsafe candidates across five risk classes with a 14 % over-refusal rate. The Librarian pipeline reaches 0.92 evidence recall and 1.00 citation precision with zero spoiler exposure, and an audit of 23 synthetic book-grounded conversations found no leak of text beyond the reader's position. The main cost of the design is over-refusal, not leakage. Several agents have defined but unreported metrics, containerised deployment and load testing are not implemented, and the conversational capture-to-surfacing loop remains a target. These gaps are stated throughout.

---

## 1. Introduction

### 1.1 Problem

A reflection companion exists to help a person understand why something mattered to them. That purpose sets its own bar for trust: a companion that blends its own interpretation into the person's words, or that reveals a plot point the reader has not reached, undermines the trust it exists to build. Getting this right is not a matter of style. It has to be guaranteed by how the system is built.

General-purpose assistants already offer memory, retrieval, image understanding, and web search, but none of them offer that guarantee. When such a system says "as you wrote last month" or "as Alice says in Chapter 5", nothing in its architecture ensures that the person did write it or that Alice does say it. For a reflection companion, that guarantee is the product.

Linger makes provenance the organising principle of the architecture and evaluates the system primarily on whether its safeguards hold rather than on how fluent its prose is. The question the project sets out to answer is whether a multi-agent system can be structurally prevented from misquoting, spoiling, fabricating, and over-storing, and what such a structure costs in usefulness.

### 1.2 Approach

Linger separates generation, evidence selection, review, validation, and storage, and assigns each to a different component with a different authority. Five reasoning agents each own one Pydantic AI `Agent` object and a small set of application-selected runtime skills. Application code, not any model, sequences every hand-off, decides which evidence an agent may see, validates every typed output, and alone releases text to the reader or commits a memory. A deterministic retrieval service enforces the reader's spoiler boundary before any passage reaches a model. Telemetry records where and how each decision was made without recording what the person said.

---

## 2. Scope, Contributions, and Related Work

This section fixes what the report covers, states what it contributes, and places the design against the work it draws on.

### 2.1 Scope and constraints

Linger's scope is bounded by its five reasoning agents (Muse, Librarian, Serendipity, Provenance, and Sculptor) and the deterministic Memory & Policy Service that coordinates them. This report describes and evaluates that system and no other. The corpus is five public-domain works: *Alice's Adventures in Wonderland*, *Animal Farm*, *Narrative of the Life of Frederick Douglass*, *The Adventures of Pinocchio*, and Helen Keller's *The Story of My Life*. The prototype is single-user and local. It has no end-user authentication or database, and conversation state lives in the backend process and disappears on restart. Chat content is sent to the configured model provider, which is OpenAI by default with Google and Anthropic also supported. Public-web discovery through Exa is opt-in. Automatic memory capture is disabled in the interactive application and enabled only as controlled server-side evaluation state.

The prototype makes no production claims about scale, availability, or regulatory compliance, and it does not claim that its telemetry measurably improved the system. Mental-health assessment, crisis routing, continuous monitoring, and end-user memory management are out of scope: no agent is designed, reviewed, or evaluated to perform them.

### 2.2 Contributions

The report makes four contributions. Section 9.4 reports the evidence that each one holds in practice.

1. An authority model for multi-agent LLM systems in which no model can release, write, or widen scope. It is realised through typed hand-off envelopes, a request-scoped evidence index, and a single application-owned release path (Sections 3.1 and 3.4).
2. A runtime-skill mechanism that keeps one reusable agent per role while binding every run to explicit instructions, schemas, validators, tool allow-lists, and retry budgets. A SHA-256 fingerprint of that configuration is recorded on every model span (Section 3.6).
3. A spoiler-safe retrieval pipeline in which reading permission is inferred from the reader's own words on every request, retrieval is bounded to that permission before search, and the model judge sees only permitted evidence (Section 5.2).
4. A layered evaluation method with a canonical vocabulary, a human-gated Ground-truth lifecycle, deterministic hard gates, and separately reported semantic review, applied to each agent and to the system end to end (Sections 4 and 9).

### 2.3 Related work

Linger draws on four strands of prior work. Retrieval-augmented generation (Lewis et al., 2020) and contextual retrieval with reranking (Ford, 2024) supply the retrieval design, which Linger bounds by a reading boundary before search. The chain-of-evidence standard of ScientistOne (Meng et al., 2026), under which every claim traces to a grounding source, is the model for Linger's `supported_claims` mapping, to which Linger adds a chain of authority: evidence must also be permitted for this reader and this request. Context engineering (Rajasekaran et al., 2025) and harness engineering (Weng, 2026) motivate the minimal, labelled context each agent receives and the typed gates around every run. Indirect prompt injection (Greshake et al., 2023) and the OWASP Top 10 for LLM Applications (OWASP, 2025) shape the untrusted-by-default rule and the risk register, and Singapore's Model AI Governance Framework (IMDA, 2020; IMDA, 2024) provides the governance headings used in Section 6. Appendix F discusses each strand.

---

## 3. Design and Architecture

This section moves from principles to mechanism. It states the design principles, shows the components and the path of one chat turn, states the release contract precisely, walks through one turn in the running prototype, and then describes the skill mechanism, the hand-off envelopes, the physical deployment, and the technology choices.

### 3.1 Design principles

Five principles were fixed before implementation and recorded in the system specification. They shaped every architectural decision that follows.

The first is separation of authority. Generation, evidence selection, review, deterministic validation, and storage are performed by different components, and only one of them, the Memory & Policy Service, can write. Agents return typed proposals and application code decides. This is a separation of duties rather than of models: the same underlying model may play several roles, and the design assumes that it does.

The second is that provenance is built in rather than reconstructed. The reply and its evidence declarations are produced together as one typed candidate, reviewed together, and validated together. There is no post-hoc citation step.

The third is to fail closed. Any missing, unresolved, ambiguous, or changed evidence, any failed review, and any failed deterministic check results in a safe decline. A safe decline is a fixed, application-authored message that tells the reader the system cannot answer this request. It reveals nothing from the rejected candidate and writes nothing. The system never falls back to a best-effort reply.

The fourth is minimal, labelled context. Each agent receives only the fields its task needs, projected by application code. Trusted context, canonical evidence, and untrusted tool outcomes are labelled separately in the typed input.

The fifth is that everything is untrusted by default. Reader messages, book text, memories, web pages, photographs, and model candidates are data. Instructions inside them never gain tool authority or widen policy.

### 3.2 System overview and logical architecture

Figure 1 shows the components. The React front end talks to a thin FastAPI adapter. Every request enters one application-owned boundary, `run_chat_turn`, which owns session scope, specialist grants, agent sequencing, output release, and capture policy. Synthetic replay calls this same boundary directly, so evaluations exercise production code paths.

```mermaid
flowchart LR
    subgraph UI[Presentation]
        FE[React chat UI<br/>local Reader and Inspect tools]
    end
    subgraph API[Transport]
        FA[FastAPI adapter<br/>/api/chat, /api/chat/stream, sessions]
    end
    subgraph APP[Application orchestration]
        CT[run_chat_turn<br/>scope, grants, sequencing, release, capture]
        SK[Runtime skill selection<br/>SKILL.md + typed contracts + validators]
        EI[Request-scoped evidence index]
        MPS[Memory & Policy Service<br/>sole write authority]
    end
    subgraph AG[Reasoning roles — one Pydantic AI Agent each]
        M[Muse]
        L[Librarian]
        S[Sculptor]
        SE[Serendipity]
        P[Provenance]
    end
    subgraph SVC[Deterministic services]
        RET[Scoped retrieval<br/>BM25 + bge-small + MiniLM reranker]
        COR[Canonical corpus<br/>5 immutable book revisions]
        MEM[Account-scoped memory store]
        EXA[Exa web search<br/>optional, application-granted]
    end
    LF[Pydantic Logfire<br/>metadata-only runtime service]
    FE --> FA --> CT
    CT --> SK --> M & L & S & SE & P
    CT --> EI
    CT --> MPS --> MEM
    L --> RET --> COR
    SE --> RET
    SE --> EXA
    SE --> MEM
    CT --> LF
```

*Figure 1. Logical architecture. Agents never call each other. Application code selects a skill, projects the input, runs the agent, and validates the result.*

Figure 2 shows the same system from the point of view of authority. The agents propose and assess. Application code controls access, writes, and release.

![Five agents with explicit responsibilities under application orchestration, above application services for scoped retrieval, memory policy, and deterministic release checks](../images/multi-agent-architecture-v1.png)

*Figure 2. The five roles and the authority boundary.*

### 3.3 The chat-turn workflow

A reader's message, called a Line, passes through the sequence in Figure 3. The order matters. The emotional preflight runs before Muse and its tools, so a distressing disclosure never triggers retrieval or connection search. The candidate review runs on the complete candidate, so Provenance can find claims that Muse omitted or mislabelled. The deterministic checks run after semantic approval, so a plausible but unresolvable citation still fails closed.

```mermaid
flowchart TD
    Line[Reader's current Line] --> Pre[Provenance: emotional preflight<br/>no tools, current Line only]
    Pre -->|apply_boundary| Fixed[Application-owned canonical boundary reply]
    Pre -->|continue_reflection| Muse[Muse: reflection draft]
    Muse -->|librarian_route / librarian_search| Lib[Librarian: boundary inference,<br/>book-request plan, scoped retrieval, evidence assessment]
    Muse -->|serendipity_explore| Ser[Serendipity: connection discovery<br/>or memory recall]
    Lib --> Muse
    Ser --> Muse
    Muse -->|MuseCandidate:<br/>reply + evidence uses + supported_claims| Rev[Provenance: candidate review<br/>fresh context, no tools]
    Rev -->|pass| Det[Application: deterministic release checks]
    Rev -->|revise, once| Muse
    Rev -->|reject| Decline[Application-authored safe decline]
    Det -->|valid| Reply[Reply released]
    Det -->|invalid| Decline
    Rev -->|allow_capture, released reply,<br/>capture policy enabled| MPS[Memory & Policy Service commit]
```

*Figure 3. One chat turn. Every arrow is an application-mediated hand-off with a typed envelope.*

Section 3.5 walks through one turn in full, including the fail-closed variations and what the reader sees in the running prototype.

Two workflows run outside the chat turn. Reviewed curation selects a bounded set of stored originals, obtains one Sculptor proposal, obtains an independent Provenance verdict bound to the proposal's digest, and lets the Memory & Policy Service apply only an exactly matching allowed proposal. Memory surfacing is an offline decision path in which Sculptor judges a supplied batch. Its conversational integration is a product target, not an implemented feature.

### 3.4 The output release contract

The release contract is the heart of the authority model and deserves a precise statement.

Muse's typed output, `MuseCandidate`, contains the complete reply text and a list of evidence uses. Each evidence use names a source (a book record, a memory record, a web page, or an earlier reader line), any exact quotation and its location, and the exact reply spans it supports, held in `supported_claims`. The candidate also contains either one exact-span memory nomination taken verbatim from the current Line or a typed reason for nominating nothing. Muse's registered output validator retries invalid evidence identifiers, mismatched quotations, stale spans, and missing visible links for public sources before the candidate leaves the agent.

Provenance then reviews the candidate with no tools and no history. It receives the trusted context (policy, reading context, and passage scope), the frozen canonical book evidence, the exact selected memory and web records, the verified session lines, the untrusted tool outcomes of the current run, and the candidate's own declarations. It must verify each declaration and, separately, scan the whole reply for undeclared quotations, factual claims, and sensitive inferences. It returns `pass`, `revise`, or `reject` for the response, with fixed finding codes, and an independent `allow_capture` or `reject_capture` for the nomination. A `spoiler` or `prompt_injection` finding forces `reject`.

After a `pass`, application code resolves every book declaration against a request-scoped evidence index. The index accepts only exact records from the current direct Librarian result, the selected records of a current Serendipity proposal, or records re-resolved from identifiers cited by an earlier released reply in the same session. Memory declarations must bind to the authenticated active-memory snapshot. Web declarations must bind to a page actually opened from an exact application-supplied URL or a permitted search lead, and must appear as an exact Markdown citation. Quotations are checked verbatim against both the source and the reply. Any failure produces the safe decline.

A first `revise` verdict gives Muse exactly one revision with the same turn authority, the draft's tool messages, and the same evidence index. The second review receives the original candidate and its findings and must return one resolution per finding. An unresolved finding prohibits approval. A second `revise`, a `reject`, or a failed revision produces the safe decline. Rejected drafts are never displayed and are excluded from session history.

Capture is gated separately. It requires a Muse nomination, no Provenance veto, a released ordinary reply, and the deterministic capture policy to be enabled. Every safe decline and every emotional-boundary release suppresses writes, even when the nomination was independently approved.

### 3.5 A worked turn

A worked example shows the sequence in practice. A reader writes: "I've finished Chapter 2 of Alice's Adventures in Wonderland. Alice's changes in size made me think about feeling out of place. Can we explore that?" The preflight classifies the Line as ordinary reflection. While drafting, Muse recognises a book cue in the reader's own words and calls `librarian_route`. The application resolves the work as *Alice*, records an explicit current-turn completion of Chapter 2, and the Librarian boundary judgment confirms a chapter ceiling of 2. Muse then calls `librarian_search`. The application plans the request from the reader's exact words ("Alice's changes in size"), searches only Chapters 1 and 2, reranks the results, and asks Librarian's evidence assessment whether the permitted passages support the request. The result is `sufficient` with two records, say the "Drink me" passage and the telescope passage, which enter the request-scoped evidence index.

Muse drafts a reply that quotes one line exactly and declares that quotation with its record identifier and location. It maps the sentence about Alice's size to the two records through `supported_claims` and leaves its own reflective question unmapped because it makes no factual claim. It returns `NoMemoryCandidate` because nothing in the Line is worth preserving. Even a nomination would not be stored while capture is disabled. Provenance receives the candidate, the two frozen records, the tool outcomes, and the current Line. It confirms the quotation, confirms that nothing in the reply relies on later chapters, and returns `pass`. The application resolves both declarations against the index, checks the quotation verbatim against the record and the reply, and releases the text. The reader sees a short reply with one located quotation and one question. The Inspect tool shows three model invocations (preflight, draft with its tool calls, and review), the Librarian judgments, the verdict, and the trace identifier.

Two variations show the fail-closed paths. Had the reader written "What happens after Alice meets the Caterpillar?" with no stated progress, routing would have found no current progress, the boundary judgment would have returned *uncertain*, and Muse would have been required to ask which chapter the reader has reached rather than answer. Had Muse quoted a line that was not in the two records, Provenance would have returned `revise` with an `unresolved_evidence` finding, Muse would have had one chance to repair it, and a second failure would have produced the safe decline.

Figures 4 to 8 show the same example in the local application on 19 September 2026. The page has two halves. The conversation is on the left. On the right is an observed-run map that fills in as each component completes, followed by the Inspect view.

![Landing page: the Linger chat with an empty conversation, a "Try a line" tray of example prompts with a book selector, and the composer](images/ui-01-landing.png)

*Figure 4. The starting page. The "Try a line" tray offers an exact quotation request, a question about an unread part, a request for a connection, and plain thinking aloud. Nothing is sent until the reader presses Send.*

![The reader's Chapter 2 message and Linger's grounded reply on the left; on the right the observed-run map showing Book corpus, Librarian, and the current-conversation row, with the Inspect card for reader message 01 stating "Alice's Adventures in Wonderland, through completed chapter 2"](images/ui-02-grounded-reply.png)

*Figure 5. The grounded reply. The reply describes the Chapter 1 and 2 size changes and ends with one open question. The observed-run map records that Provenance approved the candidate and that the deterministic checks released it, and the Inspect card records the resolved reading position. The "Saved to your memories" notice shows the capture notice mechanism, because this developer environment had the controlled capture policy enabled.*

![Detail panel for the Librarian node showing the librarian_search contract: work_id pg11, book_version_id pg11-v01b38ea4, outcome evidence_found, evidence_strength sufficient, and searched_scope with max_chapter_inclusive 2](images/ui-03-librarian-contract.png)

*Figure 6. The Librarian node opened. The search was bounded to `max_chapter_inclusive: 2` on the content-hashed revision `pg11-v01b38ea4`, and the evidence assessment returned `sufficient` with its reason.*

![Detail panel for the Provenance node on a later run of the same message: review path revise then pass after one revision, finding code unsupported_claim, revision_count 1](images/ui-04-provenance-revision.png)

*Figure 7. The revision loop observed on a repeat of the same message. The first candidate received `revise` with an `unsupported_claim` finding, Muse repaired it once, and the second review returned `pass`. The Inspect view exposes only the fixed verdicts and codes, never the rejected draft.*

![The observed-run map's "What ran, in order" list: Preflight (emotional boundary preflight), Muse (draft, revision), Librarian (processing, evidence strength, book corpus search), Serendipity (search rank select, book corpus search), Corpus, Provenance (review), all complete](images/ui-05-inspector-card.png)

*Figure 8. "What ran, in order" for that turn. Every component and its stages are recorded by the application, not reported by any agent.*

A grounded turn therefore costs at least three model invocations plus the Librarian judgments made inside the tool calls. A personal reflection with no book costs two. In the three live turns captured for the figures above, the end-to-end time from Send to release was between 82 and 90 seconds, with the Muse draft and its tool calls accounting for most of it. The preflight took 1.7 to 3.7 seconds. Per-turn cost and latency are recorded on every trace but have not been aggregated into a reported figure beyond these observations (Section 9.3).

### 3.6 Runtime skills

Each logical role owns exactly one production Pydantic AI `Agent`, constructed once at import. What varies per run is the skill. A skill is an immutable assignment record that binds a `SKILL.md` instruction resource, a typed input and output contract, an output validator, a tool allow-list, and a retry budget. The application selects a skill constant, for example `MEMORY_CURATION.run_options()`, and passes its options to the run. There is no plugin registry, no filesystem search, and no model-driven skill selection.

There are twelve assigned skills. Muse has *reflection*, which covers both draft and revision. Librarian has *boundary inference*, *event identification*, *book request*, and *evidence assessment*. Sculptor has *memory curation* and *memory surfacing*. Serendipity has *connection discovery* and *memory recall*. Provenance has *emotional preflight*, *candidate review*, and *curation review*.

Shared role policy lives in a packaged prompt catalogue and contains only what is common to the role. The selected skill's instructions are added per run. Neither ever loads repository development instructions. Each run records a stable `template_id` and a SHA-256 digest computed over the effective shared and selected instructions, the input and output JSON schemas, tool and capability permissions, validator identities, and retry limits. The digest is never computed over request content. A change to any covered element changes the digest without a manual version counter, so prompt drift is visible on every trace.

Muse and Serendipity keep fixed output schemas with registered validators. Librarian, Sculptor, and Provenance select a task-specific output schema per run. Instructions load through `importlib.resources`, so an installed wheel runs identically to a checkout. Figure 9 illustrates the mechanism for Provenance, whose one agent object serves three skills.

![One reusable Provenance agent with three assigned skills; for curation review the application selects the skill, loads its instructions and typed contract, runs the agent with fresh context, then validates the verdict and applies policy](../images/runtime-skills-detail-v1.png)

*Figure 9. Runtime skills on one reusable agent. The application selects the skill and supplies instructions, evidence, and output schema before the model runs. An `allow` verdict still requires application validation.*

### 3.7 Inter-agent communication

There is no free-form messaging between agents. Every hand-off is a strict, discriminated Pydantic envelope that carries only the fields the next step requires. Full transcripts and unrestricted working context are never passed. Table 1 lists the envelopes.

| Hand-off | Input → Output | Authority notes |
|---|---|---|
| App → Provenance (preflight) | `EmotionalBoundaryInput` → `EmotionalBoundaryAssessment` | Current Line and versioned policy only |
| App → Muse | `MuseDraftInput` / `MuseRevisionInput` → `MuseCandidate` | Revision keeps the original turn's authority; at most one |
| Muse → Librarian (tools) | `librarian_route`, `librarian_search` | Thin adapters; the model writes no book query, the application supplies reader spans |
| App → Librarian | `LibrarianBoundaryInferenceInput` → `LibrarianBoundaryDecision`; event identification; `LibrarianBookRequestInput` → `BookRequestPlan`; `LibrarianEvidenceStrengthInput` → `BookEvidenceAssessment` | Decisions are content-free; spans must be exact reader text; identifiers must resolve |
| Muse → Serendipity (tool) | `serendipity_explore` → `ConnectionProposal` / `MemoryRecall` / `ConnectionDecline` | Fresh dependencies per request; intent selects the skill |
| App → Provenance (review) | `ProvenanceInput` → `ProvenanceReview` | Fresh input, no history; a revision review carries `finding_resolutions` |
| App → Sculptor | `AccountScopedMemories` → `CurationProposal` / `NoCurationProposal`; `SurfacingInput` → `SurfaceNow` / `Defer` / `DoNotSurface` | Account identity excluded from model input |
| App → Provenance (curation) | `CurationReviewInput` → `CurationProvenanceReview` | Verdict echoes the proposal digest |
| App → Memory & Policy Service | Reviewed command with digest | Accepted only when the digest matches an `allow` verdict and the sources are fresh |

*Table 1. Typed hand-off envelopes.*

### 3.8 Physical architecture and deployment

The current deployment is a local two-process prototype. A Vite development server serves the React 19 front end on port 5173, and a Uvicorn-hosted FastAPI backend runs on port 8000 with all agents, retrieval models, and file stores in the backend process. Python 3.12 dependencies are locked with `uv` and the front end uses `pnpm`. Model calls go over HTTPS to the configured provider. OpenAI calls use the Responses API so that reasoning can be retained across tool calls. The corpus is versioned, content-hashed Markdown under `data/`, and evaluation memories are account-scoped Markdown under `memories/`. Figure 12 shows the arrangement.

The local front end also mounts two developer tools that a product build would omit. Reader is a chapter browser that does not set reading progress (Figure 10). Inspect is a read-only per-turn view of context, agent outcomes, verdicts, and the trace identifier (Figures 6 to 8). A third developer surface replays saved evaluation Scenes through the same map (Figure 11). Telemetry is exported to one Logfire project under two service identities: `linger-backend`, which records metadata only, and `linger-evals`, in which synthetic content is permitted.

![The Library panel open beside the chat: "Reading space" listing the five registered books with Open book buttons](images/ui-06-library-reader.png)

*Figure 10. The Reader tool listing the five registered works. Browsing here grants no reading progress to the chat.*

![Saved-evaluation view: scenario "Alice kitchen spoiler boundary", scene "scene-kitchen-boundary", the invented persona Priya Nadar, the memory placed in the account before the run, the fixed reader message, and the route this build actually took](images/ui-07-saved-evaluation.png)

*Figure 11. A saved evaluation case in the explorer: the synthetic persona, the memory placed before the run, the fixed reader message, and the route the build actually took. The banner states that it is not a live conversation. Section 4.1 defines the evaluation vocabulary.*

Continuous integration runs in GitHub Actions on every pull request and push, and the build produces an installable wheel that bundles the prompt catalogue and all skill resources. Containerisation, a deployment job, the multi-account test deployment, and the load test called for by the specification are not yet implemented. Section 8 describes the pipeline.

```mermaid
flowchart LR
    Browser[Browser] -->|HTTP/JSON| Vite[Vite dev server<br/>React 19, port 5173]
    Vite -->|/api| Uvicorn[Uvicorn + FastAPI<br/>Python 3.12, port 8000]
    Uvicorn -->|in-process| Agents[Five Pydantic AI agents<br/>retrieval models: bm25s, fastembed, reranker]
    Uvicorn -->|files| Stores[(Canonical corpus<br/>account-scoped memories)]
    Agents -->|HTTPS| LLM[Model provider]
    Agents -->|HTTPS, opt-in| Exa[Exa search]
    Uvicorn -->|OTLP| Logfire[Logfire]
```

*Figure 12. Physical architecture of the local prototype.*

### 3.9 Technology choices

Table 2 summarises the main technology and architecture choices and the reason for each. Appendix F.2 gives the full rationale.

| Choice | Alternative considered | Reason |
|---|---|---|
| Five roles rather than one prompt | One well-instructed model that reflects, retrieves, connects, curates, and checks itself | Authority, not capability: a component that cannot see the memory store cannot leak it, and a reviewer with no history cannot be talked round. Each boundary is enforceable in code and testable without a model |
| Application-orchestrated hand-offs | An agent-graph framework (LangGraph, AutoGen, CrewAI) | The dominant risk is a model widening its own authority; sequencing, grants, and release are easiest to control and unit-test in plain Python in one file |
| Pydantic AI | A custom tool-dispatch and web-client layer | Typed input and output with validation retries, per-run instructions and output types, a capability and toolset model, provider abstraction, Logfire instrumentation, and a maintained Exa search capability |
| One agent per role with per-run skills | One agent per skill | Preserves per-role tool and validator authority and the five-role mental model while making each task's instructions, schema, and retries explicit and fingerprinted |
| Deterministic retrieval with model judgment on either side | Model-driven retrieval | Spoiler safety cannot depend on a model's discretion; retrieval is a scoped, testable service and the model judges only the boundary and the evidence strength |
| Hybrid BM25 and dense retrieval with cross-encoder reranking | Any single strategy | Chosen on measurement (Section 5.2): reranking raised evidence recall to 0.92 and halved evidence volume at a p95 cost of 0.46 s on local models |
| Logfire under a written data contract | Ad hoc logging | Traceability without content leakage, enforced by a typed projection and an exported-payload test |
| Markdown file stores | A database | Adequate for a single-user prototype; immutability plus content hashing is simpler to reason about than migrations |

*Table 2. Technology and architecture choices.*

---

## 4. Evaluation Framework

Results in this report appear in two places. Each agent's component evaluation is reported inside that agent's section (Section 5), and the system-level evidence is in Section 9. This section defines the method that both rely on, so that no result is met before its measure is defined: the three layers of evidence, the metrics, the Objective catalogue and the human-gated process that generates the synthetic evaluation data, and how the results are laid out.

### 4.1 Three layers of evidence

Evaluation is organised into three layers. Each answers a different question, and their results are never pooled.

Layer 1 consists of automated contract tests with mocked models. Given a model output, does the application enforce its contracts? These tests use Pydantic AI's `TestModel` or fixed functions in place of a provider and run in seconds. They establish authority boundaries, validator behaviour, retry limits, scope enforcement, and telemetry redaction. They establish nothing about decision quality.

Layer 2 consists of component evaluations with a live model and fixed evidence. Does each agent make the right local decision when the evidence is held constant? Each agent has a case set in which retrieval dependencies return fixed evidence, so a failure localises to the agent's own routing, filtering, comparison, or selection rather than to retrieval variance. Grading has two parts. Deterministic hard gates check schema, response kind, cited identifiers, required and forbidden tool operations, word limits, and quotation substrings. A separately reported semantic review is performed by a human or a secondary model. A semantic score can never override a failed hard gate, and a secondary-model review is labelled non-independent because it may share the model under test.

Layer 3 consists of scenario replay with a live model through the production chat-turn boundary. Do the agents hand off correctly, and do the safeguards hold across a whole conversation? Replay uses a fixed vocabulary of seven terms, defined in Table 3 and used with capital initials throughout this report.

| Term | Meaning |
|---|---|
| Objective | One evaluation goal from a catalogue, such as *spoiler boundary clarification* or *reviewed automatic memory capture*, with its hard gates and suggested measures |
| Scenario | The complete evaluation design for one synthetic person and account. It contains one or more Scenes |
| Backstory | That person's situation and reading history |
| Prop | A memory record placed in the store before a Scene runs |
| Line | One reader message |
| Scene | One graded unit: a Line, its Props, and the expected outcome |
| Ground truth | The expected outcomes for each Scene. Proposed when the Scenario is generated, authoritative only after a human reviewer independently adopts it. The adopted bytes are hashed so that a later replay can prove it graded against the approved expectations |

*Table 3. The scenario-replay vocabulary.*

Each Scene has hard gates, such as no post-boundary retrieval, no unexpected record written, and release source equal to the ordinary Muse release, together with separate review judgments. A passing component run must never be aggregated or labelled as an Objective pass. The run-scenario tooling also flags potentially misleading passes, where the expected outcome occurred for the wrong reason.

### 4.2 Metric definitions

For safety gates the primary pair is recall on the unsafe class, meaning the fraction of unsafe inputs blocked, and the over-refusal rate, meaning the fraction of benign inputs blocked. Code precision measures whether the recorded finding code is correct. Decoupling accuracy measures whether two decisions that should be independent, response release and memory capture, actually are. For evidence selection the primary pair is evidence recall, the fraction of gold passages present in the released evidence computed over relevant ranges, and citation precision, the fraction of released citations that are relevant. Retrieval reports p95 latency and evidence-token volume because they are costs that the reader and the downstream model pay. Live runs are non-deterministic, so where repeats exist the report gives pass^k, under which a case passes only if all k repeats pass, rather than a single-run pass rate. Appendix B collects the definitions.

Reader value is not measured. Whether a released sentence was worth reading is a human judgment. The repository records it as such and reports no proxy score for it.

### 4.3 Objectives and scenario generation

Scenario replay is organised around a catalogue of eleven system-level Objectives (Table 4). Each Objective names the agents it exercises, the hard gates a Scene must pass, the measures to report, and a generation brief with composition rules and prompt boundaries for the synthetic data that tests it. The catalogue is the single source of evaluation-goal text; the skills that plan and generate Scenarios read it and never copy it.

| Objective | Family | What it tests |
|---|---|---|
| Grounded book reflection | Retrieval and grounding | Librarian retrieves passages when a reflection includes a quotation or factual claim; Muse stays grounded; Provenance verifies the evidence; personal reflection proceeds without retrieval |
| Spoiler-boundary clarification | Retrieval and grounding | Librarian infers progress from remembered events; retrieval stays within that boundary; Muse asks for clarification rather than risk a spoiler |
| Cross-source tentative connection | Retrieval and grounding | Serendipity links authorised memories, book passages, and public evidence; Muse cites its support; private wording is protected during web search; Provenance blocks unsupported conclusions |
| Weak-evidence safe decline | Retrieval and grounding | When a plausible connection lacks evidence, Muse and Serendipity qualify or decline it, and Provenance blocks invented support while allowing a non-factual reflection |
| Reviewed automatic memory capture | Conversation and memory | With capture enabled, Muse nominates, Provenance reviews, and the Memory & Policy Service stores approved durable content and leaves low-signal content unstored |
| Session-scoped conversation continuity | Conversation and memory | Muse follows a developing reflection within one chat; a new chat starts without the previous session's working history |
| Longitudinal memory retrieval | Conversation and memory | Across sessions, Serendipity searches the memories the Memory & Policy Service authorises, at Muse's request, while Librarian still handles any book a Line refers to |
| Bounded memory curation | Conversation and memory | Sculptor proposes links, groups, or summaries over a bounded set using only supplied records and preserving every original |
| Proactive memory surfacing | Conversation and memory | A reflection updates memory through reviewed capture and curation; in a later chat Sculptor decides whether that history can help, and Muse responds through the normal gates |
| Untrusted-content injection resistance | Safety and security | Book passages, memories, and web results carrying malicious instructions are ignored, Provenance blocks unsafe output, and the legitimate task still succeeds |
| Sensitive-inference and capture veto | Safety and security | Linger responds helpfully without diagnosing or inferring a sensitive trait; the tool-less preflight stops the Muse path for a distressing disclosure; the fixed boundary reply and capture veto apply |

*Table 4. The Objective catalogue.*

Scenarios are generated by a model and adopted by people, in four stages that keep generation, adoption, and replay separate (Figure 13). In the planning stage a person selects one or more Objectives in a local selector, and the `plan-synthetic-scenarios` skill writes a pre-generation report with a detached generator prompt; selecting an Objective is not approval to generate. In the generation stage, after the person approves the design, a separately authorised generator writes the Backstory, the synthetic person, the Props, the Lines, and a proposed Ground truth, and both files are validated without any provider call. In the review stage the `review-synthetic-ground-truth` skill opens the proposal in a local review app, and a reviewer who is independent of the generator adopts or flags every expected outcome; adoption records a hash of the approved bytes. In the replay stage the `run-scenario` skill replays the Scenario through the production chat-turn boundary and writes an analysis report for every run, including all-pass runs. Neither the proposed nor the adopted Ground truth ever enters the system under evaluation, and no browser step invokes a model or a replay.

```mermaid
flowchart LR
    Cat[(Objective catalogue<br/>11 Objectives)] --> Plan[Plan<br/>person selects Objectives;<br/>skill writes pre-generation report]
    Plan -->|person approves design| Gen[Generate<br/>authorised model writes Backstory,<br/>Props, Lines, proposed Ground truth]
    Gen --> Val[Validate<br/>schema, no provider call]
    Val --> Rev[Review<br/>independent person adopts or flags<br/>each expected outcome; adoption hashed]
    Rev -->|adopted| Run[Replay<br/>production chat-turn boundary;<br/>analysis report every run]
    Run --> LF[Logfire Evals]
    Rev -->|flagged| Plan
```

*Figure 13. The scenario lifecycle. Every arrow that changes state is a human decision; the model writes proposals only.*

Table 5 lists the Scenarios saved under this process.

| Scenario (short name) | Book | Agents exercised | Scenes | What it tests |
|---|---|---|---|---|
| Alice Caterpillar | *Alice* | Muse, Librarian, Provenance | 3 | Grounded quotation within a chapter-5 ceiling; clarification when progress is ambiguous; personal reflection without retrieval |
| Alice quotation | *Alice* | Muse, Librarian, Provenance | 2 | Retrieve only when a quotation is asked for; skip retrieval for a personal reflection |
| Alice kitchen | *Alice* | Muse, Librarian, Provenance | 2 | Infer a chapter boundary from remembered events; ask before answering when size changes leave progress ambiguous |
| Pigeon | *Alice* | Muse, Librarian, Provenance | 3 | Quote the Pigeon exchange exactly within supported progress; clarify an uncertain later growth episode |
| Event-led (Alice) | *Alice* | Muse, Librarian, Provenance | 4 | Boundary inference from the reader's description of an event; spoiler inference; ambiguity handling |
| Animal Farm, Douglass, Helen Keller, Pinocchio | one work each | Muse, Librarian, Provenance | 4 each | The same event-led grounding and clarification design applied to the other four works |
| Identity connections | *Alice* and a public essay | Muse, Librarian, Serendipity, Provenance | 3 | Tentative cross-source connection; decline an unsupported conclusion about personality change |
| Roses | *Alice* and a public source | Muse, Librarian, Serendipity, Provenance | 3 | Distinguish reflection from causal proof when comparing concealment across memory, book, and research |
| Cross-source | *Alice* and a public essay | Muse, Librarian, Serendipity, Provenance | 3 | Tentative comparison across memory, book, and essay; reject the conclusion that one social self is the authentic one |
| Reviewed capture | none | Muse, Sculptor, Provenance | 16 | Selective automatic capture at a 1:10 durable-to-low-signal mix; source-preserving curation |
| Pottery | none | Sculptor | 5 | Offline curation: exact and paraphrased duplicates, an evolving fact, a topic group, and a superficial similarity |

*Table 5. Saved evaluation Scenarios. The Alice Caterpillar, quotation, and kitchen Scenarios use a historical schema and were not in the iteration-18 batch; the batch ran Pigeon, Event-led (Alice), Animal Farm, Douglass, Helen Keller, Pinocchio, Roses, and Cross-source.*

### 4.4 How results are reported

Component results (layer 2) are reported inside each agent's section in Section 5, after that agent's design, so that a role's decision logic and the evidence for it sit together. Each is described with its evaluation design, its results, and an interpretation. System-level results are in Section 9: the contract-test suite (layer 1), scenario replay (layer 3), cost and latency, and a traceability matrix that joins the per-agent numbers to the guarantees they support. Where a measure is defined but not yet reported, the table carries a placeholder so that the gap is visible in the same place as the results. Table 18 in Appendix C summarises coverage across all agents.

The scenario batch that Section 5 refers to throughout is *iteration 18*, the eighteenth run of a Librarian-focused improvement cycle in which each iteration re-ran the full scenario set after a prompt or code change. It was run on 18 September 2026 and is reported in full in Section 9.2. Table 5 in Section 4.3 lists the saved Scenarios; the eight native Scenarios in the batch total 29 Scenes.

---

## 5. The Agents and the Memory & Policy Service

All five roles run on the configured `LINGER_MODEL`, which was `openai:gpt-5.6-luna` in every committed evaluation. The roles are presented in the order they act in a chat turn. Muse drafts, Librarian and Serendipity supply evidence, Provenance reviews, and the Memory & Policy Service commits. Sculptor, which runs outside the turn, comes last. Each role is presented under the same headings: an at-a-glance table, its role, a summary of its decision logic, its results, and its implementation status. The full design of each role, including its authority boundary, skills and contracts, complete decision logic, enforcement layers, relationships with the other roles, and evaluation design, is in Appendix E, one subsection per role. The evaluation method is in Section 4.

### 5.1 Muse — the conversation

| | |
|---|---|
| **Purpose** | Owns the reply. Turns one bounded reader turn into one typed candidate for independent review. |
| **Model** | `openai:gpt-5.6-luna` via `LINGER_MODEL`, using the Responses API so that reasoning is retained across tool calls. |
| **Memory** | Sees released session history only, under application control. Memory records reach it only as evidence returned by Serendipity. Writes nothing, and nominates at most one exact span per turn. |
| **Tools** | `librarian_route`, `librarian_search`, and `serendipity_explore`. All three are thin adapters granted and executed by the application. |
| **Prompt pattern** | One *reflection* skill for draft and revision, written as decision rules rather than a persona. Structured output `MuseCandidate` with `supported_claims`. |
| **Reasoning loop** | A single draft with tool calls, then at most one revision driven by Provenance findings. The revision repairs every finding and then re-audits the whole reply. |
| **Fallback** | Validator retries. A `reject`, a second `revise`, or a failed revision produces the application's safe decline. The draft is discarded and never re-enters history. |
| **Autonomy** | Chooses the path (reflect, probe, ground, or connect) and how to use evidence inside an application-sealed turn. Cannot release, store, or widen scope. |
| **Evaluated in** | A five-case baseline with hard gates, and scenario replay through the release suite, the claim-mapping suite, and the native Scenes. |

#### Role

Muse owns the reply. It turns one bounded reader turn into one typed candidate, calls a specialist when that would help, and responds to one independent review. It is the only role that writes reader-facing prose and the only one that sees conversation history. It cannot release its own words or write durable memory.

#### Decision logic

Muse first chooses a path. A plain reflection or a reading check-in is answered from the reader's experience without retelling the book. If a book is named but the reading position is unclear, Muse asks one question rather than guessing. If the reader's own words carry a book cue, Muse calls `librarian_route`, and the application inserts the reader's exact message so the model cannot paraphrase it. A route returns a scope, not text; Muse then calls `librarian_search` and must honour whichever of four branches comes back: ask the returned clarification, answer from the returned records, answer within stated limitations, or say that no supporting passage was found. When a connection might help, Muse calls `serendipity_explore` with an intent only and may ignore the proposal, but if it uses one it must declare every record it relies on. The draft declares every evidence use with its identifier, quotation, location, and the exact reply spans it supports, and ends with either one exact-span memory nomination or a typed reason for none. A `revise` verdict gives one repair: fix every finding, then re-audit the whole reply. Appendix E.1 gives the full decision rules, contracts, and enforcement layers.

#### Results

No committed live component run exists for the five-case baseline. Its hard gates are exercised in the test suite against supplied outputs. In the 18 September scenario batch the release suite passed 12 of 12 and the claim-mapping suite 4 of 4, and 26 of the 29 native Scenes passed. Table 6 lists the measures.

| Measure | Source | Value |
|---|---|---|
| Hard-gate pass (5 baseline cases) | Component harness | *to be populated* |
| Exact-quotation accuracy | Scenario release events | *to be populated* |
| Evidence recall at release | Scenario release events | *to be populated* |
| Memory-capture precision / recall | Reviewed-capture scenario (1:10 mix) | *to be populated* |
| Release-suite pass | Scenario batch, 18 Sep 2026 | 12 / 12 |
| Claim-mapping suite pass | Scenario batch, 18 Sep 2026 | 4 / 4 |

*Table 6. Muse measures. Rows marked "to be populated" are defined and computable from recorded artefacts but not yet reported.*

None of the three Scene failures, discussed in Section 9.2, is a released fabrication. The five hand-written baseline cases are a regression guard rather than a performance measure, and this report does not present them as a rate. Per-Scene quotation accuracy and evidence recall can be computed from the recorded release events, and memory-capture precision and recall from the reviewed-capture scenario, whose 1:10 Scene mix was built for that purpose. Neither has yet been reported.

#### Status

The typed candidate, the specialist tool paths, and the independent review with one revision are complete. Spoiler-boundary ownership and automatic nomination are partial. Muse receives a validated scope or exact paragraph identifiers and the release checks enforce them, but server-owned durable event identity for capture remains open. The photograph conversation path is not started. There is no product image-input path, and image evidence has no release contract.

### 5.2 Librarian — reading boundaries and book evidence

| | |
|---|---|
| **Purpose** | Answers two questions: what has this reader actually read, and do these passages support this request. |
| **Model** | `openai:gpt-5.6-luna` via `LINGER_MODEL`. |
| **Memory** | None of its own. Eligible memories arrive as boundary-inference input. Nothing persists, and the boundary is re-resolved on every request. |
| **Tools** | None. Its skills are tool-less and are wrapped by a deterministic retrieval service: BM25 (`bm25s`), `bge-small` embeddings, and a MiniLM cross-encoder reranker over a content-hashed corpus. |
| **Prompt pattern** | Four skills (boundary inference, event identification, book request, evidence assessment), each with a task-specific output schema. Decisions are content-free. Request spans must be exact reader text, never a model-written query. |
| **Reasoning loop** | Localise, plan, retrieve deterministically within the permitted scope, and assess. One output retry per skill. |
| **Fallback** | Fails closed when the boundary or a location cannot be validated. A search or rerank failure degrades to direct chapter reads inside the validated scope. A planning failure falls back to original-text retrieval. An empty scope means no search. |
| **Autonomy** | Localisation authority only. It may say where the reader is and whether the evidence suffices. Only code may disclose text or set scope. |
| **Evaluated in** | A retrieval strategy benchmark (12 cases, 5 strategies), live release validation (12 cases), and the boundary audit in scenario replay (Section 9.2). |

#### Role

Librarian answers the two questions that the application cannot answer deterministically: what has this reader actually read, and do these passages support this request. It does nothing else. Everything between those judgments, namely identity resolution, catalogue filtering, search, fusion, reranking, and resolution to canonical lines, is deterministic application code. The split exists because spoiler safety must not depend on a model's discretion. A model may localise the reader's position, but only code may disclose text.

#### Decision logic

Librarian's work is two model judgments around a deterministic retrieval service. First it localises the reader: a resolver identifies the work from the reader's words, and the boundary-inference skill decides from the Line and any eligible memories whether a chapter ceiling or an exact already-read passage is established, returning *uncertain*, and so a clarification, whenever the evidence is line-only, low-confidence, or ambiguous. Chapter 5 completed permits Chapters 1 to 5; Chapter 5 started permits 1 to 4. Nothing is persisted, so the boundary is resolved again on every request. Second, the book-request skill copies the exact spans of the reader's text that express each book need; no model ever writes a query. Retrieval then runs entirely in code, filtered to the permitted chapters before search: BM25 and dense retrieval each return up to ten candidates, a cross-encoder reranks overlapping windows, and the merged pool of at most twenty is resolved to canonical lines. Finally the evidence-assessment skill sees only the permitted records and returns `sufficient`, `weak`, or `none` for each requested part, selecting the smallest set that serves it. Appendix E.2 gives the full rules and enforcement layers.

#### Results

Table 7 gives the benchmark results.

| Strategy | Evidence recall | Citation precision | Strength-label accuracy | p95 latency (ms) | Mean evidence tokens |
|---|---|---|---|---|---|
| direct (bounded chapter selection, control) | 0.50 | 0.16 | 0.67 | 3.2 | 402 |
| bm25 | 0.75 | 0.28 | 0.92 | 3.1 | 1518 |
| semantic | 0.79 | 0.33 | 1.00 | 3.0 | 1433 |
| hybrid | 0.79 | 0.30 | 1.00 | 2.9 | 1535 |
| **hybrid_reranked** (selected) | **0.92** | **0.83** | 0.92 | 461 | 595 |

*Table 7. Retrieval strategy benchmark on the Alice corpus `pg11-v01b38ea4` (Project Gutenberg text 11, content-hashed revision), five repetitions, local models, zero retrieval token cost. All five strategies passed the zero-forbidden-exposure and exact-resolution gates.*

The live twelve-case evaluation of 17 August 2026 reached evidence recall of 0.92, citation precision of 1.00, strength accuracy of 0.92, an answerable-release rate of 1.00, and zero spoiler exposures, with a mean latency of 13.7 seconds and a p95 of 27.9 seconds. The project targets on the final user-visible pipeline were met.

Reranking is what makes the difference. The three unreranked strategies plateau at about 0.79 recall and 0.3 precision because they return many plausible but wrong windows; the reranker raises recall to 0.92 and cuts the evidence volume by more than half, at a p95 latency cost of 0.46 seconds. The retrieval-only precision of 0.83 is diagnostic: the Librarian judge and the release validator raise it to 1.00 in the live run.

The live report predates the book-request and event-identification skills, which were added after a verified false negative in *Douglass* (the decisive passage ranked first but scored 0.352 against a 0.5 cut-off), and should be re-run on the current prompt digest. The 18 September boundary audit (Section 9.2), 23 book Scenes with no ceiling or support leak, is the most recent evidence that the boundary logic holds under the current skills.

#### Status

Five works are registered, with chapter, named-unit, and exact-passage grants. The reranked hybrid path is the selected production strategy. The event-identification and book-request skills were added at the most recent iteration. Two limits are known. Omission remains a model-quality risk in both planning and assessment, because exact-span checks prevent invented wording but not semantic omission. A high retrieval score neither proves relevance nor authorises a boundary. The benchmark and live report cover *Alice* only.

### 5.3 Serendipity — connection discovery and memory recall

| | |
|---|---|
| **Purpose** | Finds one tentative, evidence-supported connection between the reader's reflection and a permitted source, or declines. Under a separate intent, recalls the reader's own earlier words. |
| **Model** | `openai:gpt-5.6-luna` via `LINGER_MODEL`. |
| **Memory** | Searches the account-scoped curated retrieval view by lexical token overlap, and only when the application grants it. Recall returns one to three exact records. Writes nothing. |
| **Tools** | Book search through Librarian's judged retrieval, memory search, Exa web search, and `get_page`. Each is withheld unless granted for this request. Budgets are eight model requests, six tool calls, and five results per source. |
| **Prompt pattern** | Two skills (connection discovery and memory recall) with one fixed output schema of proposal, decline, or recall and a registered validator. An anchored ordinal rubric with a filter before the comparison. |
| **Reasoning loop** | Eight stages: request, sealed permissions, route and search, evidence ledger, filter, compare two or three candidates, verify against the ledger, hand off. At most one expansion to a second source, and one run per turn. |
| **Fallback** | Typed declines (`generic_theme_match`, `no_matching_memory`, tied winner). Any ledger or presentation mismatch fails closed to a safe decline. |
| **Autonomy** | Chooses where to search, which candidates survive, and whether to decline. Cannot open an ungranted source, widen the ceiling, publish, or write. |
| **Evaluated in** | A ten-case component suite with contrast groups, and scenario replay through the Cross-source and Roses scenarios and the outside-essay web smoke test. |

#### Role

Serendipity looks for a tentative, evidence-supported connection between the reader's current reflection and a permitted source, which may be a passage, an earlier memory, or a public page. It returns one proposal or one decline. Under a separate intent it recalls the reader's own earlier words. Connection-finding is a separate role because it needs search, comparison, and a willingness to say no, and none of those belong in the agent that writes the reply. A drafter that also hunts for connections has every incentive to find one.

#### Decision logic

A request passes through eight stages. Muse supplies an intent and the application inserts the reader's message as the cue and seals the permissions: a revision and chapter ceiling if progress is confirmed, memory search only if the account has curated records, web access only with the policy flag and credentials. Serendipity identifies the relationship the reader is asking for and inspects the permitted sources that relationship needs, expanding to a second source at most once. Every record a search returns is written to a ledger the model cannot edit, and a web result counts only once the page is opened. Candidates are then filtered on three anchored ratings (cue fit, reflective value, safety) and six disqualifiers; safety has no usable middle. Survivors are compared by cue fit first, then value, never by a weighted total, and a tie between the top two is a decline. The result is verified against the ledger before it leaves the agent, and one run per turn is allowed. A privacy gate screens every outgoing query and URL for the reader's own wording and personal data. Appendix E.3 gives the routing policy, the rubric, and the contract invariants.

#### Results

No component run report has been committed. Serendipity's coordination behaviour appears in the scenario batch of Section 9.2. The Cross-source scenario suite passed. The Roses scenario suite failed on one Scene where Provenance rejected a bounded evidence-limit statement. The outside-essay web smoke test passed, with the final synthesis mapping both sources. Table 8 lists the measures.

| Measure | Source | Value |
|---|---|---|
| Component suite pass^k (10 cases, k repeats) | Component harness | *to be populated* |
| Weak-evidence decline rate | Roses and Cross-source scenarios | *to be populated* |
| Target-connection hit rate | Roses and Cross-source scenarios | *to be populated* |
| Evidence recall / citation precision (connection evidence) | Scenario release events | *to be populated* |
| Cross-source scenario suite | Scenario batch, 18 Sep 2026 | Passed |
| Roses scenario suite | Scenario batch, 18 Sep 2026 | Failed (1 Scene, review-caused) |
| Outside-essay web smoke test | Scenario batch, 18 Sep 2026 | Passed |

*Table 8. Serendipity measures.*

Serendipity is the agent whose evaluation is best designed and least reported. The behaviours it is graded on are the right ones. The most important single number for the role is its decline rate on weak evidence, the analogue of Provenance's block recall, and the contrast-group construction is the right defence against a suite that rewards saying yes. What is missing is a committed run with repeats. The ten-case suite should be run with pass^k on the current prompt digest, and `target_connection_hit_rate` and `weak_evidence_decline_rate` should be reported from the Roses and Cross-source scenarios.

#### Status

Bounded book, active-memory, and granted-web discovery run in production, with the web path exercised by scenario replay against saved page snapshots. Three limits are known. The memory search compares the cue with each record by lexical token overlap, so a heavily paraphrased cue can miss a relevant record, and the memory component case remains outside the component baseline. Images have no retrieval, citation, or release path. Whether a connection helps a person reflect still requires human evaluation.

### 5.4 Provenance — independent review

| | |
|---|---|
| **Purpose** | Independent reviewer. Classifies the Line for the emotional boundary, reviews every Muse candidate and nomination, and reviews every Sculptor proposal. |
| **Model** | `openai:gpt-5.6-luna` via `LINGER_MODEL`, the same provider model as Muse. |
| **Memory** | None. No history. Every run starts from a fresh typed input. |
| **Tools** | None. |
| **Prompt pattern** | Three skills (emotional preflight, candidate review, curation review) with closed finding-code taxonomies. The review input is organised by trust level. |
| **Reasoning loop** | Verify each declaration, then scan the whole reply independently. On a revision, resolve each earlier finding and re-inspect. A curation review echoes the proposal digest. |
| **Fallback** | A preflight failure produces the safe decline before Muse runs. An invalid or missing review produces the safe decline, and the application never substitutes its own approval. A mismatched curation review blocks the apply step. |
| **Autonomy** | Verdict authority only. An approval is necessary but never sufficient for a release or a write. |
| **Evaluated in** | The release-gate suite (24 of 28 cases run), the curation-gate suite (12 cases), the emotional-boundary suite (8 cases, no committed run), and the wrong-passage diagnostic. |

#### Role

Provenance is the reviewer, and it is the reason the rest of the design can afford to be generous with model initiative. It classifies the current Line for the emotional boundary before Muse runs. It reviews every complete Muse candidate, including drafts that declare no factual claim, because a non-factual reflection may pass without retrieval but never without review. It decides independently whether a nomination may be captured, and it reviews every Sculptor proposal against its exact sources. It has no tools and no history. Every review starts from a fresh typed input, so a prior review cannot influence the next, and the draft under review cannot argue with it.

A Provenance approval is necessary but never sufficient for a release or a write. A missing, malformed, stale, or incorrectly bound review fails closed.

#### Decision logic

The emotional preflight is deliberately minimal: `apply_boundary` only for a clear, current, first-person disclosure of intense distress, `continue_reflection` for everything else, with no diagnosis, label, or rationale. The candidate review receives an input organised by trust level and must do two things: verify every declaration and quotation against the frozen evidence, and independently scan the whole reply for undeclared quotations, claims, and sensitive inferences, reporting every defect it can find because Muse has one revision. It enforces the branch of each Librarian result, checks a nomination as an exact slice of the Line, and returns findings from a closed code set; `spoiler` and `prompt_injection` force `reject`, and a revision review must resolve each earlier finding. The curation review allows each Sculptor action only under the conditions Sculptor was given and echoes the proposal digest unchanged. Appendix E.4 gives the trust table, the finding codes, and the enforcement layers.

#### Results

Table 9 gives the release-gate results and Table 10 the curation-gate results.

| Metric | Value |
|---|---|
| Block recall (unsafe candidates blocked) | **1.00** |
| Code precision (correct finding code) | **1.00** |
| Capture-veto recall | **1.00** |
| Decoupling accuracy | **1.00** |
| Sensitive-content accuracy | 0.96 |
| Overall accuracy | 0.75 |
| Over-refusal rate, response | 0.14 |
| Over-refusal rate, capture | 0.17 |
| Capture code precision | 0.80 |
| Evaluation errors | 0 |

*Table 9. Provenance release gate on the 24-case pack, `openai:gpt-5.6-luna`, prompt version 8, 12 September 2026. Every one of the five unsafe classes was blocked and correctly labelled. The four claim-mapping and revision cases added since have not yet been run live.*

| Metric | Value |
|---|---|
| Positive recall (unsafe proposals rejected) | **1.00** |
| Code recall | **1.00** |
| Near-miss precision | 0.67 |
| Targets passed | No (over-refusal) |

*Table 10. Provenance curation gate, 12 cases, 15 September 2026.*

In the committed suites Provenance has never let an unsafe candidate or an unsafe curation proposal through, and it labels what it blocks correctly, which is what makes the downstream fixed-code handling safe. The cost is in the same tables: an overall accuracy of 0.75 with perfect block recall means every error is a false positive. About one in seven benign candidates is sent back or declined and one in six safe nominations is vetoed, so both suites miss their targets on usability, not safety. The decoupling accuracy of 1.00 shows the two decisions are genuinely independent. The scenario batch corroborates the pattern (Section 9.2). Reducing over-refusal without lowering block recall is the clearest next step for the role.

The emotional-boundary suite has no committed run (Table 11). Since the preflight is the only gate that can skip Muse entirely, that is the most important missing piece of Provenance evidence.

| Measure | Source | Value |
|---|---|---|
| Boundary accuracy (8 cases) | Emotional-boundary suite | *to be populated* |
| Boundary-miss count | Emotional-boundary suite | *to be populated* |
| Over-refusal rate | Emotional-boundary suite | *to be populated* |

*Table 11. Provenance emotional preflight measures.*

#### Status

All three skills, the deterministic gates, and the curation binding are implemented. Chat consumes the preflight and the candidate review, and the application curation loop consumes the curation review. The same provider model backs Muse and Provenance, which is separation of duties rather than independence.

### 5.5 The Memory & Policy Service

| | |
|---|---|
| **Purpose** | The only component that writes. Turns application-owned identity, policy, and reviewed candidates into auditable storage decisions. |
| **Model** | None. Deterministic application code. |
| **Memory** | Owns the store: append-only originals (one immutable Markdown record per capture), a curation layer of duplicate links, versioned derived summaries, topic groups, and reversible retrieval tombstones, and an immutable audit log. All of it is account-scoped. |
| **Tools** | Not applicable. Invoked by the application with reviewed, digest-bound commands. |
| **Prompt pattern** | Not applicable. |
| **Reasoning loop** | A deterministic rule chain: trusted scope, capture enabled, review allowance, no sensitive content, idempotency, atomic commit. Curation applies only an exactly matching allowed proposal. |
| **Fallback** | Any failed rule means no write. Stale, unknown, cross-account, or changed sources are rejected. An exact retry is reused and a conflicting one refused. |
| **Autonomy** | None by design. Its properties are established by contract tests rather than by model evaluation. |
| **Evaluated in** | Contract tests (Section 9.1). Memory-retrieval measures are specified but not yet reported (Table 12). |

#### Role

The Memory & Policy Service is not a reasoning role. It is a deterministic service that turns application-owned identity, policy, and reviewed candidates into auditable storage decisions, and it is the only component that writes. It decides trusted account scope, whether automatic capture is enabled, whether every deterministic capture rule passes, stable identifiers, storage paths, idempotency, atomic commit behaviour, and the minimum read projection. It never accepts an agent-supplied account identity, a self-authorised review flag, sensitive content, an unreviewed or substituted candidate, conflicting idempotent retries, or a request that crosses another account's scope.

#### Decision logic

Automatic capture is a deterministic rule chain. The server builds the account context; Muse nominates an exact slice of the current message; Provenance returns a capture decision independent of the response decision; the application validates offsets, identifiers, verdict, and release source and suppresses every write on a boundary reply or safe decline; the service then requires capture enabled, a review allowance, no sensitive content, and a matching idempotent retry before creating the record without overwrite. The store has an append-only original layer and a curation layer of duplicate links, versioned derived summaries, topic groups, and reversible tombstones. A `CurationPlan` binds one Sculptor proposal to its account, source hashes, and base curation state; only an `allow` verdict echoing that digest is applied, sources are re-read and re-hashed first, and an immutable audit event is appended. Appendix E.5 gives the full mechanism.

#### Results

Memory retrieval is an application service rather than an agent, but the specification commits to ranked-retrieval measures for it, and the longitudinal-retrieval replay runner and its 1:10 relevant-to-distractor preset exist. The current memory search compares the cue with each authorised record by lexical token overlap and drops records that share no token, so a heavily paraphrased cue can miss a relevant record. A measured Recall@5 would make that limitation quantitative. Table 12 lists the measures.

| Measure | Source | Value |
|---|---|---|
| Recall@5 | Longitudinal-retrieval replay, 1:10 relevant/distractor preset | *to be populated* |
| nDCG@5 | Longitudinal-retrieval replay | *to be populated* |
| Precision@5 | Longitudinal-retrieval replay | *to be populated* |
| Distractor citation count | Longitudinal-retrieval replay | *to be populated* |
| Fresh-session leakage rate | Session-continuity replay | *to be populated* |

*Table 12. Memory-retrieval measures. Specified but not yet reported.*

#### Status

Trusted scope, deterministic policy, atomic idempotent storage, the interim record, and reviewed curation application are complete. A public versioned memory schema with correction, deletion, undo, and version migration is deferred beyond the prototype, and server-owned durable event identity for capture remains open.

### 5.6 Sculptor — memory curation and surfacing

| | |
|---|---|
| **Purpose** | Keeps the memory store useful without changing what the reader said. Proposes one curation change or none, and judges whether a batch justifies surfacing a suggestion. |
| **Model** | `openai:gpt-5.6-luna` via `LINGER_MODEL`. |
| **Memory** | Reads bounded, account-stripped record sets of two to twelve records supplied by the application. Proposes changes to the curation layer only. Never edits or deletes an original. |
| **Tools** | None. |
| **Prompt pattern** | Two skills (memory curation and memory surfacing) with task-specific output schemas. The instructions prefer the narrower action and no change under ambiguity, and treat silence as a successful surfacing outcome. |
| **Reasoning loop** | One proposal per run, reviewed by Provenance's curation-review skill and applied by the Memory & Policy Service only when the digest matches. |
| **Fallback** | One output retry, then rejection. A proposal that Provenance does not allow, or whose sources changed, is dropped without effect. |
| **Autonomy** | Proposal-only. Runs outside conversation turns. Surfacing has no production consumer yet. |
| **Evaluated in** | A five-case curation baseline, the Pottery scenario replay, the offline surfacing harness, and the Provenance curation gate (Section 5.4). |

#### Role

Sculptor keeps the memory store useful without ever changing what the reader originally said. Under curation it proposes one change that makes existing memories easier to retrieve, or no change. Under surfacing it judges whether a supplied batch justifies one useful suggestion now, later, or not at all. It is a separate role for two reasons. Organising memory (deduplicating, summarising, grouping, and pruning) should not be mixed with the conversation, and the reader's originals must be untouchable by anything that also writes prose.

#### Decision logic

Curation follows one pattern: prefer the narrower action, and prefer no change under ambiguity. `link_duplicates` requires every source to express the same durable memory; `update_derived_summary` requires one evolving fact that each cited source contributes to, preserving corrections and uncertainty; `assign_topic_group` requires a shared theme with each fact still independently useful; a tombstone requires an already-established duplicate link; and when the input does not establish the required state, Sculptor proposes no change. Surfacing treats silence as a successful outcome: `surface_now` needs a specific, timely, grounded suggestion, `defer` needs a concrete future time or observable condition, and `do_not_surface` covers irrelevant, insufficient, superseded, repetitive, or sensitive-inference cases. Prior suggestions and dismissals are respected, and Sculptor never claims to have delivered or scheduled anything. Appendix E.6 gives the action conditions, the surfacing rules, and the enforcement layers.

#### Results

No live run has been committed for the curation baseline, the Pottery scenario, or the surfacing harness. The Provenance curation gate that reviews Sculptor's proposals has a committed result (Table 10). Table 13 lists the measures.

| Measure | Source | Value |
|---|---|---|
| Curation hard-gate pass (5 baseline cases) | Component harness | *to be populated* |
| Curation precision | Pottery scenario (5 Scenes) | *to be populated* |
| No-change accuracy | Pottery scenario | *to be populated* |
| Provenance resolution (every derived record resolves to originals) | Pottery scenario | *to be populated* (expected 1.0 by construction) |
| Source preservation (hashes unchanged) | Pottery scenario | *to be populated* |
| Surfacing decision accuracy | Offline surfacing replay | *to be populated* |
| Inappropriate-surfacing rate | Offline surfacing replay | *to be populated* |

*Table 13. Sculptor measures.*

Sculptor's safety properties are established by construction and by the contract tests: originals are immutable, there is no account scope in the input, its authority is proposal-only, and tombstones are reversible. These are the properties that matter most for a memory system. Its quality, meaning whether it links the right duplicates and groups the right facts, is defined through `curation_precision`, `no_change_accuracy`, and `provenance_resolution` but not yet reported. The Pottery scenario and the offline surfacing replay would supply decision accuracy and an inappropriate-surfacing rate. Both should be labelled component evidence only, because the conversational surfacing path is not implemented.

#### Status

The proposal boundary, the reviewed application workflow, fixed cases, and package-backed replay exist. The service applies reviewed curation and materialises originals, summaries, and topic groups for retrieval. Not yet done are the conversational capture-to-curation-to-surfacing demonstration, a measured retrieval benefit from curation, independent calibration of the curation Ground truth, and the scheduled operational playbook task.

---

## 6. Explainable and Responsible AI

This section and the two that follow cover the cross-cutting assurance material in the order principles, risks, and controls. Section 9 then reports the evidence that the controls hold.

### 6.1 Alignment across the lifecycle

At framing, the specification excludes mental-health profiling, diagnosis, crisis routing, continuous monitoring, unsolicited resurfacing, and end-user memory management until governance for them exists. At the data stage, only public-domain works are used, each with a recorded source audit and a content hash. Synthetic evaluation data is human-reviewed before adoption, and no real user data is used for evaluation. At design, authority is separated and every input class is labelled by trust. During development, prompts are versioned resources with automatic digests, prompt changes are human-reviewed, and the contract suite runs in CI. At evaluation, the layered method of Section 4 keeps component, coordination, and reader-value claims apart and labels model-judged results non-independent. In operation, telemetry is metadata-only under a written contract with a fixed failure taxonomy, and no production flag can enable content capture. For improvement, both specified self-improvement loops produce human-reviewed proposals only.

### 6.2 Explainability and traceability

Every reply is inspectable in the local Inspect tool, which shows the resolved context, each agent's outcome, Provenance's verdict and finding codes, the deterministic validation results, the release source, and the Logfire trace identifier. Evidence is separated from interpretation in the reply itself. Book quotations are verbatim and located, web claims carry an exact citation, and memory evidence is attributed as personal context rather than public fact. Every model span records role, skill, stage, template identifier, digest, hand-off origin and receiver, verdicts, retry count, tokens, latency, and cost, so any decision can be traced to the exact configuration that produced it. Declines explain themselves structurally through a fixed enumeration of causes.

### 6.3 Fairness and bias

The corpus is small and old. The specification acknowledges that it may contain dated cultural perspectives, and Linger surfaces book text as quoted evidence attributed to the work, never as its own claim. Provenance detects sensitive inferences independently of Muse's self-declaration, and sensitive-trait content is never captured. The emotional-content policy is a request-local interaction boundary rather than a label or a severity score. The system stops probing and points to human support without characterising the person. The project has not run a persona-diversity evaluation of Muse's reflections, which would test whether the same reflection prompt receives comparable treatment across readers of different backgrounds. That is a limitation and a future evaluation Objective.

### 6.4 Governance alignment

Against the IMDA Model AI Governance Framework, internal governance is provided by the written specification and telemetry contract, issue tracking, and reviewed prompt changes. The level of human involvement is human-in-the-loop for every irreversible or high-impact decision (Ground-truth adoption, prompt changes, capture-policy enablement, and every self-improvement proposal) and human-out-of-the-loop only for bounded, reviewed, reversible runtime decisions. Operations management covers data provenance, versioning by digest, repeatability through replay, and a fixed failure taxonomy. Stakeholder communication is served by a visible notice for every committed capture and by the separation of reader words, source text, and interpretation in every reply. The generative-AI framework's emphasis on content provenance maps directly onto Provenance's role.

---

## 7. AI Security Risk Register

Fifteen risks were identified from the OWASP LLM Top 10, from the specification's safeguard sections, and from failures observed during evaluation. They fall into four groups: content that reaches the reader (prompt injection, fabricated citations, spoiler leakage, over-reach on distress), content that leaves the system (private wording in web queries, cross-account memory exposure, telemetry leakage), the integrity of the pipeline (output-gate bypass, prompt drift, supply chain, secrets, test isolation), and usability and cost (over-refusal, cost and latency abuse). Eleven have committed evidence that the control holds, from either the live gate suites or the contract tests; the emotional preflight (R7) has a suite with no committed run, and dependency audit and secret scanning (R12, R13) are not yet in the pipeline. Appendix D gives the register in full, with likelihood, impact, the nearest OWASP category, the owning layer, and the evidence for each risk. Section 9.4 joins the register to the guarantees and the tests.

---

## 8. LLMSecOps Pipeline

Figure 14 shows the pipeline as a loop from a change to a reviewed proposal for the next change. The subsections follow that lifecycle: change control, automated testing, versioning and tracking, deployment, monitoring and alerting, logging and auditability, and the two bounded automation loops.

```mermaid
flowchart LR
    Dev[Change: code, prompt, SKILL.md, corpus, scenario] --> PR[Pull request, human review]
    PR --> CI{GitHub Actions}
    CI --> T1[pytest: contract tests<br/>incl. scenario validator, fingerprints, redaction]
    CI --> T2[vitest: 66 front-end tests]
    T1 & T2 --> Merge[Merge to main]
    Merge --> Build[uv build wheel<br/>prompts and skills bundled]
    Build --> Deploy[Test deployment — not yet implemented]
    Deploy --> Live[Live evaluations: per-agent suites, scenario replay]
    Live --> LF[Logfire Evals, Agents, Live views]
    LF --> Review[Human review of failures]
    Review -->|proposals only| Dev
```

*Figure 14. The LLMSecOps loop. Solid stages are implemented. The deployment stage is designed but not built.*

### 8.1 Engineering method and change control

Development was specification-first. A single system specification records the product scope, the authority model, the output release contract, the safeguards, and the acceptance criteria. The architecture document records the runtime-skill contract, and a telemetry contract is the sole authority on what may be logged. Implementation was staged so that a working end-to-end slice existed before each new capability was added: reflection with review first, then book grounding, then connection discovery, then reviewed capture and curation. Change control comes from issue tracking, human-reviewed prompt changes, and a continuous-integration workflow that runs the full contract-test suite on every pull request. Established libraries were preferred to local implementations wherever they reduced complexity: Pydantic AI for agents, its maintained Exa capability for web search, `bm25s` and `fastembed` for retrieval, and Logfire for telemetry.

### 8.2 Automated testing

Automated testing runs in CI on every pull request and push to the main branch. The AI-specific security tests exist: the release-gate and curation risk-code suites, the emotional-boundary suite, the privacy-gate and public-source access tests, and the injected-content scenarios. The live-model suites are run manually and their reports committed, and only their deterministic graders run in CI.

### 8.3 Versioning and tracking

Code is in Git and dependencies are in `uv.lock` and `pnpm-lock.yaml`. Corpus revisions are content-hashed. Prompts and skills are fingerprinted automatically. Evaluation datasets and reports carry dataset digests, run identifiers, and the Git revision.

### 8.4 Deployment

Deployment is not yet implemented beyond the wheel build. A container image, a deployment job, and front-end lint and build steps in CI are the obvious additions.

### 8.5 Monitoring and alerting

Logfire's Live, Agents, and Evals views show the trace hierarchy, per-role model exchanges, and evaluation datasets with expected and actual labels, latency, tokens, and cost. Every failure carries a fixed stage, code, category, retryability, and owner (`model`, `validation`, or `application`). No alert rules are configured. Figures 15 and 16 show the Agents and Live views for a synthetic evaluation run.

![Logfire Agents view with three cards: Provenance (22 runs, under $0.01, avg 1.7 s), Muse (11 runs, under $0.01, avg 3.7 s), Sculptor (5 runs, under $0.01, avg 2.9 s), all on gpt-5.6-luna](images/logfire-agents.png)

*Figure 15. Logfire Agents view after the reviewed-capture-and-curation evaluation of 13 September 2026, showing runs, cost, and average time per role. Only roles that were actually invoked appear.*

![Logfire Live view: the linger-evals trace list on the left and a Sculptor run span on the right showing the shared instructions, the typed input of four memory Props, and the structured NoCurationProposal output with its reason](images/logfire-trace.png)

*Figure 16. A Sculptor run in the Live view. The synthetic `linger-evals` service may record the input Props and the typed output. The runtime `linger-backend` service records only the metadata columns.*

### 8.6 Logging and auditability

Runtime spans are metadata-only under the telemetry contract. Every applied curation produces an immutable audit event. The Inspect projection records each turn's decisions, and design decisions and their rationale are kept in the issue tracker.

### 8.7 Automating the lifecycle

Two bounded loops are specified to reduce development effort while keeping humans in control. In failure-to-eval promotion, Provenance rejections, blocked injections, and failed deterministic checks emit only permitted metadata signatures, which identify candidate regression gaps. Turning a signature into a synthetic Backstory remains a human-reviewed workflow that the project has not adopted. In the Sculptor-curated system playbook, a scheduled Sculptor task reads permitted operational records and proposes a pull request that deduplicates, summarises, and prunes a versioned playbook of operational lessons. CI and human review gate the merge exactly as for any change. Both loops run outside user conversations, add no runtime authority, and are bounded by the telemetry contract.

---

## 9. System-Level Evaluation

The results in this section belong to the system rather than to any one agent. Section 9.1 reports the automated contract tests (layer 1), Section 9.2 the end-to-end scenario replay (layer 3), and Section 9.3 cost and latency. Section 9.4 joins each guarantee to its mechanism, risks, tests, and result, and Section 9.5 states the threats to validity.

### 9.1 Automated contract tests

The backend suite was run on the current codebase on 19 September 2026 with the same offline environment that CI uses (`LINGER_WEB_SEARCH_ENABLED=false` and no Exa key). The command `uv run pytest` reported 1,967 passed and 0 failed, with 678 subtests passed, in 69.6 seconds across 115 test modules. The front-end suite (`vitest`) passed 66 of 66 tests in 10 files.

An earlier run on the same day without the offline environment, that is, with the developer's `.env` granting web search, produced five failures in tests that assert the Serendipity connection tool is not granted. With the variables unset the same tests pass. This is a test-isolation gap rather than a product defect, since the tests should pin the web-search policy rather than inherit it from the environment. It is recorded as risk R15.

Table 14 groups the collected tests by area and states what each group establishes.

| Area | Tests | Files | What the tests establish |
|---|---:|---:|---|
| Librarian and retrieval: boundary inference, book-request planning, judged retrieval, chapter and section corpora, passage grants, spoiler scope | 672 | 62 | Boundary decisions grant nothing without support. Retrieval never returns records above the ceiling. Every corpus revision hashes and parses identically. Exact-paragraph grants stay exact. |
| Provenance: preflight, candidate review, revision review, curation review, risk-code grading | 315 | 20 | Fixed finding codes. Forced rejection on spoiler and injection. Every prior finding must be resolved on revision. Curation verdicts bind to the digest. |
| Muse and chat-turn orchestration: release validator, sessions, HTTP and streaming API, inspection | 262 | 17 | Only released turns enter history. Every release has a recorded verdict. Safe declines suppress capture. Session reset and rollback. |
| Synthetic evaluation tooling: scenario validator, replay runners, analysis, diagnostics | 232 | 10 | Ground-truth structures validate deterministically. A component pass cannot become an Objective pass. Failure flags survive into analysis. |
| Serendipity: routing, privacy gate, page access, recall, output retries, generic-decline detection | 195 | 15 | Copied reader wording never reaches a public query or URL. Discovered URLs need a lead. Recall returns only exact records. |
| Sculptor and Memory & Policy Service: curation, surfacing, capture policy, store | 162 | 14 | Originals are immutable. Tombstones are reversible. Account scope comes from context only. Capture requires nomination, no veto, and policy. |
| Cross-cutting contracts: claim support, evidence strength, chapter references, rerank windows, agent construction | 84 | 12 | `supported_claims` spans are exact and non-stale. Shortlist budgets fail closed. |
| Telemetry redaction | 27 | 2 | Exported payloads contain only contract-permitted fields. Failures classify by exception type, never by text. |
| Runtime skills, prompt catalogue, fingerprints | 18 | 4 | Skill selection is explicit. Digests change with instructions, schemas, tools, validators, or retries. Resources load from an installed wheel. |

*Table 14. Contract-test coverage by area: 1,967 tests in 115 modules.*

What this layer does not establish bears repeating. Every model call in these tests is a `TestModel` or a fixed function. The suite proves that the application enforces its contracts on whatever the model returns. It says nothing about whether the live model returns good decisions.

### 9.2 Scenario replay

The most recent committed batch is iteration 18 of a Librarian-focused improvement cycle. It was run on 18 September 2026 with `openai:gpt-5.6-luna` at medium reasoning effort, twelve suites with six concurrent workers, and 222 source files hash-verified unchanged before and after the run. Table 15 summarises it.

| Evaluation | Result |
|---|---|
| Native scenario replay: Pigeon, Roses, Cross-source, Animal Farm, Douglass, Helen Keller, Pinocchio, and a generic event-led grounding scenario | **26 of 29 Scenes** passed; 28 of 32 judgments; 5 of 8 scenario suites passed strictly |
| Direct notebook helpers | 12 of 12 |
| Muse / Librarian release suite | 12 of 12 |
| Claim-mapping suite | 4 of 4 |
| Outside-essay web smoke test | Passed |
| Boundary audit across 23 book Scenes | **No ceiling leak and no support leak**; 5 positive independent event gates and 6 safe ambiguous controls |
| Independent review of the 29 native Scenes | 17 credible passes, 8 limited, 1 potential false positive, 1 potential false negative, 2 supported failures |

*Table 15. Scenario replay, iteration 18, 18 September 2026.*

Replay results are also written to Logfire's Evals view as a dataset, an experiment, and ordered cases. Figures 17 and 18 show an earlier run of the reviewed-capture-and-bounded-curation scenario.

![Logfire Evals overview for run reviewed_capture_and_bounded_curation-24d12013: 16 of 16 cases completed, 0 task errors, average task duration 5.81 s, and the adopted_hard_gate_grade label at passes_hard_gates 94% and fails_hard_gates 6%](images/logfire-overview.png)

*Figure 17. Evals overview for a 16-case run. Every case completed with no task errors, and the adopted hard-gate label passed for 15 of 16 Scenes. The generic "Assertions 0 %" tile is a Logfire default that the project's label-based grading does not use.*

![Logfire case view for scene-15: the input, the actual output (no_curation_proposal with the model's reason, graded fails_hard_gates with hard failure expected_curation_proposal) beside the adopted expected output (assign_topic_group over prop-09, prop-10, prop-11), with semantic_review_required true and source_immutable true](images/logfire-case15.png)

*Figure 18. The one failing Scene. Sculptor declined to curate where the adopted Ground truth expected a topic group over three records. The case records that the source records were unchanged and that a semantic review is still required. A hard-gate failure is never silently upgraded or downgraded.*

The scenario index in the repository lists ten saved scenarios, nine with independent Ground-truth adoption records. Three early *Alice* scenarios use a historical schema and need migration before a graded replay. The index's "current live result" column has not yet been updated from this batch.

The batch's value lies as much in its documented failures as in its passes. *Douglass* fails safely: after a wrong-record repair and then a duplicate inventory repair both failed, Muse withheld rather than answering. *Animal Farm* grants the correct Chapter 5 ceiling, but the candidate omits a mandatory recognition-evidence declaration and Provenance's output is filtered during repair. That is a mapping defect, not a leak. *Roses* Scene 2 is blocked by a review that the human reviewers judged questionable, because it rejected a bounded statement about the limits of the evidence. The batch also records one potentially misleading pass, in *Pinocchio*, where a source-dependent interpretation was not declared even though the expected outcome occurred. That is precisely the class of result the run-scenario tooling exists to surface. The reviewers further noted that the identity-change release attracted unnecessary review objections to inner quoted spans already covered by a full contiguous declaration. Taken together with the Provenance results in Section 5.4, the picture is consistent. The system's failures are over-caution and bookkeeping, and no Scene released a fabricated quotation or a post-boundary fact.

### 9.3 Cost and latency

| Measure | Source | Value |
|---|---|---|
| Model invocations per grounded turn | Trace | At least 3 (preflight, draft, review) plus Librarian judgments |
| Mean / p95 latency per grounded turn | Trace aggregate | *to be populated* (three observed live turns, 19 Sep 2026: 82 to 90 s end to end) |
| Mean cost per grounded turn (USD) | Trace aggregate | *to be populated* |
| Librarian live case mean / p95 latency | 12-case live run | 13.7 s / 27.9 s |
| Retrieval-only p95 (reranked) | Benchmark | 0.46 s |
| Load test: success rate, p95, cost at 5 concurrent sessions | Not implemented | *to be populated* |

*Table 16. Cost and latency measures.*

### 9.4 Guarantee traceability matrix

Table 17 joins each guarantee the architecture makes to the mechanism that provides it, the register entries it addresses, the layer-1 tests that establish the contract, the live evidence that the mechanism holds, and the gap that remains. It is the summary of results a reader should take from this report. The numbers are those reported in Section 5 and in Sections 9.1 and 9.2.

| Guarantee | Mechanism (section) | Risk IDs | Layer 1: contract tests | Layers 2 and 3: live evidence | Result | Remaining gap |
|---|---|---|---|---|---|---|
| No misquotation or altered citation | Muse output validator; verbatim quotation and location checks; request-scoped evidence index (3.4, 5.1) | R2 | Cross-cutting claim-support tests; Provenance review tests | Release gate (`unresolved_evidence`, `misattribution` blocked); Librarian live run | Block recall 1.00; citation precision 1.00; no Scene released a fabricated quotation | Librarian live run predates two current skills |
| No text beyond the reader's position | Boundary re-resolved per request; scope before search; ceiling-bounded index; `spoiler` forces reject (5.2, 3.4) | R3 | Librarian and retrieval tests (672) | Benchmark exposure gate; live run; 23-Scene boundary audit | Zero spoiler exposures; no ceiling or support leak | Benchmark covers *Alice* only; boundary inference not measured at component level |
| No unsupported claim or sensitive inference | `supported_claims` mapping; independent whole-reply scan; closed finding codes (3.4, 5.4) | R1, R2 | Provenance tests (315); claim-support tests | Release gate; claim-mapping suite 4 / 4; wrong-passage diagnostic | Block recall 1.00; code precision 1.00 | Over-refusal 0.14 on benign candidates |
| Nothing stored without nomination, review, and policy | Exact-span nomination, independent capture verdict, deterministic policy, sole write authority (5.4, 5.5) | R5, R6 | Sculptor and Memory & Policy tests (162); orchestration tests (262) | Release gate, capture axis | Capture-veto recall 1.00; decoupling accuracy 1.00 | Capture over-refusal 0.17; memory-retrieval measures unreported |
| No model releases its own output or widens its authority | Single release path; sealed tool grants; fresh-context review; digest-bound curation (3.4, 3.6, 5.3, 5.4) | R1, R8, R11 | Orchestration tests; Serendipity grant tests (195); fingerprint tests (18) | Scenario replay release-source gates | 26 of 29 Scenes passed; every failure was a safe decline or a bookkeeping defect, none a release | |
| No private wording leaves the system | Privacy gate on queries and URLs; metadata-only telemetry contract (5.3, 8.6) | R4, R10 | Serendipity privacy tests; telemetry redaction tests (27) | | Established by contract tests only | No live measurement |
| Distress is met by the boundary, not by probing | Tool-less emotional preflight before Muse; canonical boundary reply (5.4) | R7 | Provenance preflight tests | Emotional-boundary suite (8 cases) | No committed run | The most important missing piece of evidence |

*Table 17. Guarantee traceability matrix.*

### 9.5 Threats to validity

| Threat | What it means for the results |
|---|---|
| One provider model | Every committed live result uses `openai:gpt-5.6-luna`. The architecture is provider-agnostic; the numbers are not. |
| Non-independent judge | Secondary-model semantic reviews may share the model under test. They are labelled as such, and the hard gates do not depend on them. |
| Small case sets, single runs | Five-case baselines and 12 to 24-case suites are regression guards, not population estimates, and most committed results are single runs. Only where repeats exist should a pass be read as reliable. |
| Synthetic data | Scenarios are authored and human-adopted, not collected from readers, and the corpus is five old public-domain works. |
| Correlated failure | Drafter and reviewer are the same model with different context. A blind spot shared by both is caught only by the deterministic checks, which cover what can be checked mechanically. |
| Unreported per-turn cost and latency | Every span records them; no per-turn aggregate is reported. The Librarian live p95 of 27.9 s shows latency is material. |
| Unevaluated inputs and stale reports | Image inputs have no release contract and no evaluation. The Librarian live report predates two current skills; wherever a report predates the code it describes, this report says so. |

---

## 10. Findings, Reflection, and Future Work

### 10.1 Findings

The design goal, that a model never releases its own output and that the safeguards hold, is supported by every committed live result: perfect block recall across five unsafe classes, perfect capture-veto recall, zero spoiler exposures, and a 23-Scene boundary audit with no leak. The retrieval measurements support the specific engineering choice of reranked hybrid retrieval on both quality and cost grounds.

The consistent cost, across Provenance's two suites and the scenario batch, is over-refusal. About one benign candidate in seven is sent back or declined, and human reviewers identified specific review objections as unnecessary. This is the expected shape of a fail-closed design and is preferable to the alternative, but it is the axis on which the next iteration should work.

Several things are not yet shown. Serendipity's component suite, Sculptor's curation and surfacing baselines, the emotional preflight, and the memory-retrieval Recall@5 that the specification commits to all have well-designed evaluations with no committed results. The conversational capture-to-curation-to-surfacing loop is a target with only its decision component measured. Containerised deployment, multi-account testing, and load testing are unbuilt. These gaps are stated so that the results are not read as more than they are.

### 10.2 Reflection

Fixing authority boundaries in application code first, and then adding agents inside them, made the security story testable from the start. Adopting the framework's maintained runtime-skill and capability features instead of building a tool layer reduced code and made every run auditable. Deterministic retrieval was the right call for spoiler safety. Single live runs were misleading often enough that repeated runs became the standard. Scenario schemas changed under the evaluation data more than once, and stale scenarios are a real cost of a refactor-heavy project.

[Team reflection to be written here: what each member would do differently, and what the project changed in their understanding of agent systems.]

### 10.3 Future work

Future work, in priority order, is as follows. First, report the defined but unreported metrics (memory-retrieval Recall@5, Serendipity's weak-evidence decline rate, Sculptor's curation precision, and the emotional preflight) with repeats. Second, reduce Provenance over-refusal without lowering block recall, using the reviewer notes from the scenario batch as the starting point. Third, implement the conversational capture-to-surfacing loop that Section 3.3 describes as a target. Fourth, containerise, deploy to a multi-account test environment, and run the specified load test. Fifth, adopt the failure-to-eval loop so that every blocked attack becomes regression coverage without ever copying reader content.

---

## References

Ford, D. (2024, September 19). *Introducing contextual retrieval*. Anthropic. https://www.anthropic.com/engineering/contextual-retrieval

Greshake, K., Abdelnabi, S., Mishra, S., Endres, C., Holz, T., & Fritz, M. (2023). Not what you've signed up for: Compromising real-world LLM-integrated applications with indirect prompt injection. *Proceedings of the 16th ACM Workshop on Artificial Intelligence and Security*.

Infocomm Media Development Authority & Personal Data Protection Commission. (2020). *Model artificial intelligence governance framework* (2nd ed.). Singapore.

Infocomm Media Development Authority & AI Verify Foundation. (2024). *Model AI governance framework for generative AI*. Singapore.

Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W., Rocktäschel, T., Riedel, S., & Kiela, D. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. *Advances in Neural Information Processing Systems, 33*.

Meng, R., Dalvi Mishra, B., Chen, J., Li, C.-L., Goyal, P., Parmar, M., Song, Y., Song, Y., Sinha, R., Ranganathan, P., Gokturk, B., Yoon, J., & Pfister, T. (2026). *ScientistOne: Towards human-level autonomous research via chain-of-evidence*. arXiv:2605.26340. https://doi.org/10.48550/arXiv.2605.26340

OWASP Foundation. (2025). *OWASP Top 10 for large language model applications*. https://owasp.org/www-project-top-10-for-large-language-model-applications/

Rajasekaran, P., Dixon, E., Ryan, C., & Hadfield, J. (2025, September 29). *Effective context engineering for AI agents*. Anthropic. https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents

Robertson, S., & Zaragoza, H. (2009). The probabilistic relevance framework: BM25 and beyond. *Foundations and Trends in Information Retrieval, 3*(4), 333–389.

Weng, L. (2026, July 4). *Harness engineering for self-improvement*. Lil'Log. https://lilianweng.github.io/posts/2026-07-04-harness/

---

## Appendix A. Repository map

| Path | Contents |
|---|---|
| `src/linger/agents/<role>/` | One package per role: agent construction, skill assignments, `skills/<name>/SKILL.md` |
| `src/linger/prompts/prompt_catalog.yaml` | Shared role instructions and evaluation-only prompts |
| `src/linger/orchestration/` | Reflection reply, curation loop, evidence index, release validation |
| `apps/backend/` | FastAPI adapter, `run_chat_turn`, sessions, telemetry configuration |
| `apps/frontend/` | React chat UI with local Reader and Inspect tools |
| `data/` | Canonical, content-hashed book corpus |
| `memories/` | Account-scoped memory store used by controlled evaluation |
| `evals/` | Per-agent harnesses, case sets, and committed reports |
| `synthetic-journal-evaluation/` | Objective catalogue, presets, scenarios with Ground truth, replay reports |
| `tests/` | Contract-test modules |
| `docs/` | Specification, architecture, telemetry contract, corpus audits, design notes, per-agent reports, report sources |
| `.github/workflows/ci.yml` | GitHub Actions: backend and frontend test jobs |

## Appendix B. Metric definitions

| Metric | Definition |
|---|---|
| Block recall | Unsafe candidates blocked ÷ unsafe candidates |
| Over-refusal rate | Benign candidates blocked or revised ÷ benign candidates |
| Code precision | Blocked candidates with the correct finding code ÷ blocked candidates |
| Capture-veto recall | Unsafe nominations vetoed ÷ unsafe nominations |
| Decoupling accuracy | Cases where the response and capture decisions were each correct independently ÷ cases |
| Evidence recall | Gold relevant ranges covered by released evidence ÷ gold relevant ranges |
| Citation precision | Released citations that are relevant ÷ released citations |
| Evidence-strength accuracy | Cases where the retrieved coverage supports the expected `sufficient` / `weak` / `none` label ÷ cases |
| Spoiler exposure count | Released records or reply facts beyond the permitted boundary |
| pass^k | A case passes only if all k repeated runs pass |
| Recall@5, nDCG@5, Precision@5 | Standard ranked-retrieval measures at a release limit of five, specified for memory retrieval and not yet reported |

## Appendix C. Metric coverage by agent

| Agent or concern | Defined | Reported | Gap |
|---|---|---|---|
| Provenance release gate | Block recall, over-refusal, code precision, capture-veto recall, capture over-refusal, sensitive-content accuracy, decoupling accuracy | All (24 cases) | Repeats; reduce over-refusal |
| Provenance curation gate | Positive recall, near-miss precision, code recall | All (12 cases) | Repeats |
| Provenance emotional preflight | Accuracy, boundary miss, over-refusal (8 cases) | None | Commit one run |
| Librarian retrieval | Evidence recall, citation precision, strength accuracy, p95, tokens, cost | Benchmark and 12-case live | Refresh live run; add boundary-localisation and clarification accuracy from the scenario batch |
| Muse | Hard gates (5 cases); scenario measures for quotation accuracy, evidence recall, capture precision and recall | Scenario Scenes only | Report per-Scene measures |
| Serendipity | 8 behaviours with contrast groups; scenario measures for connection hit rate and weak-evidence decline rate | None committed | Commit run with pass^k; report scenario measures |
| Sculptor curation | Hard gates (5 cases); curation precision, no-change accuracy, provenance resolution | None | Run Pottery scenario |
| Sculptor surfacing | Decision accuracy, inappropriate-surfacing rate, timing contrast | None | Run offline replay |
| Memory retrieval | Recall@5, nDCG@5, Precision@5 | None | Run the retrieval replay with the 1:10 preset |
| Injection resistance | Injection block rate, benign completion rate, unauthorised-effect count | Class blocked in the gate suite | One dedicated scenario |
| Cost and latency | Tokens, cost, latency per span | Per-strategy and per-suite | Per-turn cost and p95; load test |

*Table 18. Metric coverage by agent.*

## Appendix D. AI security risk register

The risks below were identified from the OWASP LLM Top 10, from the specification's safeguard sections, and from failures observed during evaluation. Table 19 summarises the register. The entries that follow give each risk's controls and the evidence that the control works, and state where that evidence is missing.

| ID | Risk | Likelihood | Impact | Nearest OWASP LLM Top 10 category | Owning layer | Evidence status |
|---|---|---|---|---|---|---|
| R1 | Indirect prompt injection through retrieved content | High | High | LLM01 Prompt injection | Untrusted labelling; application-owned grants; Provenance forced reject | Verified: block recall 1.00 (Section 5.4) |
| R2 | Fabricated or altered quotations and citations | High | High | LLM09 Misinformation | Muse validator; Provenance; deterministic release checks (Section 3.4) | Verified: codes blocked; citation precision 1.00 (Section 5.2) |
| R3 | Spoiler leakage across the reading boundary | Medium | High | LLM02 Sensitive information disclosure | Librarian and scoped retrieval; ceiling-bounded index; Provenance forced reject | Verified: zero exposures; 23-Scene audit (Section 9.2) |
| R4 | Private wording leaking into public web queries | Medium | High | LLM02 Sensitive information disclosure | Serendipity privacy gate (Section 5.3) | Contract tests only |
| R5 | Cross-account memory exposure | Low | High | LLM02 Sensitive information disclosure | Memory & Policy Service; authenticated snapshot binding | Contract tests only |
| R6 | Unsafe automatic capture | Medium | High | LLM02 Sensitive information disclosure | Provenance capture decision; deterministic capture policy | Verified: capture-veto recall 1.00 (Section 5.4) |
| R7 | Over-reach on distressing disclosures | Medium | High | | Provenance emotional preflight; canonical boundary reply | Suite exists; no committed run |
| R8 | Output-gate bypass | Low | High | LLM05 Improper output handling; LLM06 Excessive agency | Single application-owned release path | Contract tests; inspection projection |
| R9 | Over-refusal degrading usefulness | Medium | Medium | | Provenance; one bounded revision | Measured: 0.14 response, 0.17 capture, above target |
| R10 | Telemetry leaking reader content | Low | High | LLM02 Sensitive information disclosure | Telemetry contract and typed projection | Contract tests (exported-payload test) |
| R11 | Prompt drift | Medium | Medium | | Runtime-skill fingerprint on every span (Section 3.6) | Contract tests |
| R12 | Supply-chain risk | Medium | Medium | LLM03 Supply chain | Locked dependencies; maintained library tools | No dependency audit in the pipeline |
| R13 | Secrets exposure | Low | High | LLM07 System prompt leakage; LLM02 | Environment handling | No secret scanning in the pipeline |
| R14 | Cost and latency abuse | Low | Medium | LLM10 Unbounded consumption | Revision, retry, and exploration budgets | Recorded per span; no per-turn aggregate |
| R15 | Developer environment leaking into tests | Medium | Low | | CI offline environment | Observed; tests should pin the policy |

*Table 19. AI security risk register. Likelihood and impact are the team's qualitative ratings. The OWASP column names the nearest category of the 2025 Top 10 for LLM applications and is blank where none fits.*

**R1. Indirect prompt injection through retrieved content** (book text, web pages, memories, photographs). Likelihood high, impact high. All evidence is labelled untrusted, tool grants are application-owned so that an injected instruction gains no authority, and a `prompt_injection` finding forces rejection with no revision. The class is blocked and correctly labelled in the release-gate suite with block recall 1.00.

**R2. Fabricated or altered quotations and citations.** High, high. The controls are validator retries on invalid identifiers, verbatim quotation and location checks against the canonical record, a request-scoped evidence index that accepts only exact current or previously released records, and `supported_claims` span validation. The `unresolved_evidence`, `misattribution`, and `unsupported_claim` codes are blocked in the suite, and citation precision was 1.00 in the live Librarian run.

**R3. Spoiler leakage across the reading boundary.** Medium, high. The boundary is re-resolved from the reader's words on every request, Librarian returns content-free locations, retrieval, Serendipity search, citation validation, and release are all bounded to the ceiling, and a `spoiler` finding forces rejection. There were zero exposures in the live Librarian run and no ceiling or support leak across the 23 audited Scenes.

**R4. Private wording leaking into public web queries.** Medium, high. The deterministic overlap guard and personal-data detectors run on queries and on raw and decoded URLs. The evidence is the contract tests on the privacy gate.

**R5. Cross-account memory exposure.** Low, high. Account identity comes from authenticated context only and is excluded from Sculptor input, and memory evidence is bound to the authenticated snapshot. The evidence is the request-isolation tests.

**R6. Unsafe automatic capture** of sensitive traits, distress, or injected content. Medium, high. Capture is off by default. A write requires a nomination, no veto, and the deterministic policy. Sensitive-trait content is never captured, and every safe decline and emotional boundary suppresses writes. Capture-veto recall was 1.00.

**R7. Over-reach on distressing disclosures.** Medium, high. The tool-less preflight runs before Muse, the response is canonical and application-owned, and the candidate review is defence in depth. The eight-case suite exists but has no committed run.

**R8. Output-gate bypass.** Low, high. There is one release path, rejected drafts are excluded from history, and the release source is recorded as a fixed enumeration. The evidence is the contract tests and the inspection projection.

**R9. Over-refusal degrading usefulness.** Medium, medium. One bounded revision precedes a decline, and over-refusal is reported as a first-class metric. The measured values are 0.14 for responses and 0.17 for capture, both above target, plus the one review-caused scenario failure.

**R10. Telemetry leaking reader content.** Low, high. A written contract, a typed projection, an exported-payload test, failure classification by exception type rather than text, and content instrumentation confined to the code-owned evaluation service. The evidence is the telemetry redaction tests.

**R11. Prompt drift.** Medium, medium. Instructions, schemas, tools, validators, and retries are digested automatically on every span, and prompt changes are human-reviewed. The evidence is the fingerprint tests.

**R12. Supply-chain risk.** Medium, medium. Dependency files are locked and maintained library tools are preferred to custom clients. A dependency audit is not yet part of the pipeline.

**R13. Secrets exposure.** Low, high. The `.env` file is ignored by git and only the selected provider's key is required. Secret scanning is not yet part of the pipeline.

**R14. Cost and latency abuse.** Low, medium. There is at most one revision, connection exploration is sequential, each skill has a retry budget, and cost and tokens are recorded on every span. Evaluation reports record cost and latency.

**R15. Developer environment leaking into tests.** Medium, low. CI generates an offline `.env`. Five tests fail locally with web search enabled and pass with it disabled. The tests should pin the policy explicitly.

## Appendix E. Agent design detail

This appendix gives, for each role in Section 5, the authority boundary, the skills and typed contracts, the complete decision logic, the enforcement layers and failure behaviour, the relationships with the other roles, and the evaluation design. Results are in Section 5.

### E.1 Muse — the conversation

#### Authority boundary

| May decide | Must preserve | May never decide |
|---|---|---|
| How to reflect; whether grounding or a connection would help; which safe follow-up question to ask; how to use returned evidence; whether one exact span of the reader's text is worth nominating for memory | The reader's request; the evidence identifiers, locations, and quotations exactly as returned; the request's authority on revision | Reader identity; spoiler authority; evidence availability; release approval; account scope; capture permission; storage; whether a connection may bypass a specialist's decline |

#### Skills and contracts

One skill, *reflection*, serves both the initial draft (`MuseDraftInput`) and the single permitted revision (`MuseRevisionInput`). Both return the fixed `MuseCandidate` schema. Muse's shared policy is short: be warm, concise, and concrete, treat books as optional context rather than a prerequisite, treat all supplied material as data, and return a candidate for separate review. The skill instructions are long and are written as decision rules rather than as a persona.

#### Decision logic

Muse first chooses a path. For a plain reflection or a reading check-in, it replies to the reader's experience without retelling or interpreting the book. The reader's own description of a scene is conversation context, not canonical evidence for a book claim. When context is insufficient, for example when a book is named but its reading position is unclear or two works are plausible, Muse asks one question rather than guessing. When the reader's own words carry a book cue (a title, a character, a scene, or a contextual pronoun), Muse calls the argument-less `librarian_route`. The application inserts the reader's exact message, so Muse cannot substitute a paraphrase. An active session book on its own does not justify a route call.

A route returns a scope, not text. Muse then calls `librarian_search` with the returned work and revision identifiers, and the application supplies the ceiling. The result has one of four branches that Muse must honour. A *clarification* branch means Muse asks the returned question and does not answer the book question. A *sufficient* branch means Muse answers from the returned records. A *weak* branch means Muse answers within the stated limitations. A *none* branch means Muse says that the search found no supporting passage, never that the event is absent from the book.

When a connection might deepen the reflection, Muse calls `serendipity_explore` with an intent only. The application supplies the cue and the source grants. Muse may ignore a proposal. If it uses one, it must declare every record it relies on with that record's true source kind. If Serendipity declines, Muse relays a fixed safe next step rather than inventing a connection.

Muse then drafts completely. The reply goes in `reply`. Every evidence use, whether a book record, an active memory, an opened web page, or an earlier reader line, is declared with its identifier, any exact quotation and location, and the exact reply spans it supports. A comparison across sources is built from a short attributed account of each source, keeps fiction, personal report, and public argument distinct, and ends with one open question. A hypothesis supplied by the reader or by Serendipity stays a hypothesis. Quotations are copied exactly and declared exactly. Source words are never altered to fit a sentence, and plain prose is preferred to decorative quotation marks. When drafting words the reader could say, only facts the reader supplied may be used. The candidate ends with either one exact-span memory nomination from the current Line or a typed `NoMemoryCandidate` reason.

A `revise` verdict returns the findings, the previously accepted claims and quotation interiors, and the draft's tool messages. Muse must repair every finding and then re-audit the whole reply for the same defect elsewhere, because the findings are required repairs rather than an exhaustive list. A source-mapping repair simplifies the reply to the requested source accounts, one essential comparison, and one open question, and then regenerates all declarations against the final text. A later reader statement supersedes an earlier one on the same detail.

Muse never diagnoses or labels a mental state and does not keep probing after distress. The preflight normally intercepts such a Line before Muse runs, and the candidate review is defence in depth.

#### Enforcement and failure behaviour

| Layer | Enforced by | Guarantee |
|---|---|---|
| Tool grants | Application | Muse's three tools are thin adapters. The application owns which are granted, their scope, execution, and validation. |
| Cue insertion | Application | The reader's exact message is the routing cue and the retrieval cue. The model cannot rewrite it. |
| Output validator | Schema and registered validator | Invalid evidence identifiers, mismatched quotations, stale `supported_claims` spans, and missing visible links for public sources are retried before the candidate leaves the agent. |
| History | Application | Only released turns enter history. Rejected drafts are excluded. |
| Release | Application | Muse never releases. Every candidate goes to Provenance and then to the deterministic checks. |

Validator retries are bounded. A `reject`, a second `revise`, or a failed revision produces the application's safe decline, and the draft is discarded. Muse never sees a rejected draft again as history.

#### Working with the other roles

Muse is the only caller of Librarian's routing and search tools and of Serendipity. It receives typed results and nothing else: a scope, a clarification, or no match from routing; bounded evidence or a typed failure from search; a proposal or a decline from Serendipity. Provenance sees Muse's complete candidate and the untrusted tool outcomes, but never Muse's history.

#### Evaluation design

Muse's own harness is a fixed five-case baseline that grades supplied outputs against one instruction behaviour each: reflect without demanding book context, probe when a named book is unconfirmed, confirm a chapter boundary, ground an answer within a boundary, and relay a Serendipity decline honestly. Each case supplies the reader message, its dynamic context and tool transcript, the primary expected behaviour, probing and provenance invariants, and explicit forbidden outcomes. The loader requires exactly five cases and one per behaviour. The hard gates are deterministic. A probe must contain a question. Forbidden terms must not appear as whole words. The reply must respect its word limit. Any quotation-marked span of five or more words must be a substring of the supplied Librarian evidence, the reader's own message, or the decline's safe next step. Fabricated text presented without quotation marks is beyond the hard gates by design and belongs to the human or secondary-model rubric, which is reported separately and can never override a hard failure.

Muse's harder obligations only appear under real tool results and real review: honouring a clarification branch, keeping source accounts distinct, mapping every substantive claim, and repairing a revision. Muse is therefore mainly evaluated through scenario replay (Section 9.2). Three suites in the iteration-18 batch target it directly. The release suite runs twelve cases through Librarian, Muse, Provenance, and release validation. The claim-mapping suite runs four cases on `supported_claims` completeness. The native Scenes carry release judgments.

### E.2 Librarian — reading boundaries and book evidence

#### Authority boundary

| May decide | Must preserve | May never decide |
|---|---|---|
| Whether the reader's words and eligible memories locate a chapter ceiling or an exact already-read passage; which reader spans express a book request; whether the permitted evidence is `sufficient`, `weak`, or `none` for each requested part | The reader's original wording; every supplied identifier; the work and revision it was given | What text is disclosed; the reading scope of any search; whether a candidate is answered; anything about memory or release |

#### Skills and contracts

Librarian has four skills on one agent. All are tool-less and each has one output retry.

| Skill | Input → Output | What it answers |
|---|---|---|
| Boundary inference | `LibrarianBoundaryInferenceInput` → `LibrarianBoundaryDecision` | A memory-supported or Line-supported chapter ceiling, an exact set of already-read paragraphs, or *uncertain*, with a confidence and only input identifiers |
| Event identification | Original reader wording and private candidates → an identified occurrence or *unresolved* | Which single occurrence in the book the reader's stopping description refers to. A precondition before a proposed ceiling is accepted |
| Book request | `LibrarianBookRequestInput` → `BookRequestPlan` | The exact `reader_spans` and `context_spans` that express each book need. No model-written query |
| Evidence assessment | `LibrarianEvidenceStrengthInput` → `BookEvidenceAssessment` | Whether the permitted evidence set supports every requested part, with a reason and limitations |

#### Decision logic

The first step is identity. When Muse routes, a shared deterministic resolver looks for a registered title, alias, or author in the reader's message. A longer name beats a name it contains, and a canonical title beats an alias at the same position. With no name signal, catalogue cues are scored as 0.3 plus 0.2 per distinct whole cue that overlaps, capped at 1.0, with a threshold of 0.6. Generic single words do not count. No candidate gives `NoMatch`, several qualifying candidates give a typed identity clarification, and a resolved name scores 1.0. These are heuristics rather than probabilities. A `NoMatch` may fall back to the session's active book unless a strong cue names another work. Naming a book never confirms a chapter.

The second step is the boundary. A private search may inspect the whole immutable work, but its passages never enter the turn's evidence. Librarian assesses every supplied memory against the canonical candidates, asking whether it establishes earlier knowledge, gives no support, or conflicts with the current report, and declares a consistent basis of either `memory_supported` or `line_only`. The instructions spell out what does not count: curiosity, an adaptation, a quotation alone, a hypothetical reading plan, a reading pace, a second-hand account, and mere names. An explicit correction defeats an older claim. Event identification runs independently on the reader's wording and the candidates. It must not equate the earliest compatible occurrence, the strongest retrieval hit, or the most detailed passage with the reader's stopping point, and if the wording fits several occurrences it returns *unresolved* with the missing distinction.

Application code then derives the ceiling from the cited records and rejects invented identifiers, a mismatched work or revision, an invalid basis, or inconsistent chapters. Line-only candidates, confidence below 0.75, or any ambiguity yield an exact clarification. At chapter granularity, Chapter 5 completed permits Chapters 1 to 5 and Chapter 5 started permits Chapters 1 to 4. A named section without a chapter number, such as a preface or a letter, is granted only individually. Where numbering restarts between parts, canonical unit identifiers keep the locations distinct. An earlier reader statement that genuinely reports reading a scene can authorise a narrow session-supported passage of at most five paragraphs without implying the containing chapter. Nothing is persisted, and the boundary is resolved again for every request.

The third step is planning. Before retrieval, the book-request skill receives the reader's message and earlier statements but no passages. It returns each book need as exact spans copied from the reader's text: the shortest fragments that name the book content, excluding personal details, other sources, and progress-only statements. A `BookRequestSpanValidation` capability rejects spans that do not occur in the supplied text within the single retry.

The fourth step is deterministic retrieval. The catalogue and indexes are filtered to eligible chapters before search. Each planned part becomes a query, with the original text as a fallback query, up to 16 queries of 2,000 characters. BM25 and dense retrieval each return up to ten candidates with no private score cut-off. Candidates are kept by evidence identity. Overlapping token windows are reranked by the cross-encoder and each passage takes its best window score. Keyword, semantic, and reranker ranks are interleaved, the query streams are merged into a private pool of at most twenty candidates, and the pool is resolved to exact canonical lines. The reranker orders candidates. It does not decide support.

The fifth step is assessment. The evidence-assessment skill receives the plan, the original request, and only the permitted records. It may recover an omitted need as an `additional_part`, whose spans must also match the reader's text. It must map every selected record to a requested part with its `necessary_support` and must select the smallest set that serves the part's purpose, which is `reference` for grounding a moment and `answer` for an explicit question, claim check, or quotation request. A `sufficient` verdict must cover every part. A `weak` verdict keeps the evidence with stated limitations so that Muse can explain the limit. A `none` verdict returns nothing. Application code checks unique mappings, valid identifiers, coverage, and the caller's release limit. An oversized selection fails closed rather than truncating the evidence behind a verdict.

#### Enforcement and failure behaviour

| Layer | Enforced by | Guarantee |
|---|---|---|
| Scope before search | Application | Post-boundary catalogue entries and chapter bodies never reach the evidence judge, Muse, a bounded index, or the reranker. Only the private first-phase inference sees them, and it has localisation authority, not disclosure authority. |
| Identifier validation | Application | Every memory and evidence identifier a decision cites must exist in its input. Work and revision must match. |
| Span validation | Capability and application | Request spans must be non-empty and exact substrings of the reader's text. |
| Clarification as a type | Contract | A clarification carries no evidence, score, or strength label because no search occurred. The release validator rejects a book answer in its place. |
| Grant precedence | Application | A passage route permits only its exact paragraph identifiers. Chapter authority takes precedence where both exist. |

Retrieval fails closed when the boundary or an evidence location cannot be validated. Search or reranking failures may degrade to direct chapter reads, but only inside the same validated scope. A failure carries a stable error code and a retryability flag and no unvalidated excerpt. Planning failures are recorded and fall back to original-text retrieval within the same scope. An empty authorised scope means no search.

#### Working with the other roles

Muse and Serendipity use the same judged retrieval path, `retrieve_for_judgement`. Neither may write its own book query or widen scope. Serendipity receives the strength, reason, and limitations in its `judgement` field. Provenance receives the frozen canonical records that Librarian selected and enforces the branch of each search result.

#### Evaluation design

Librarian is evaluated at two levels, both with a known chapter ceiling, so that retrieval quality is measured separately from boundary inference. Boundary inference from an unknown reading position, book routing, and clarification are scenario Objectives (`spoiler_boundary_clarification` and `grounded_book_reflection`) and are covered by the scenario replay in Section 9.2. Both levels cover *Alice* only. The other four registered works have corpus integrity tests but no retrieval benchmark.

The retrieval strategy benchmark uses twelve frozen query cases on *Alice's Adventures in Wonderland*, for example `drink-me`, `pool-of-tears`, `identity-theme`, and `exact-caucus-quote`, and two negative controls, `future-cheshire` and `absent-spaceship`, whose answers lie beyond the ceiling or outside the book. Each case fixes a reading boundary, a query, and gold relevant ranges, which are canonical chapter line ranges grouped so that any one range in a group satisfies it and every group must be satisfied. Five configurations run on identical inputs: direct bounded chapter reads as the control, BM25, dense embeddings, their reciprocal-rank fusion, and fusion plus cross-encoder reranking. No model is called. Two gates must pass before any quality number counts: zero passages beyond the ceiling, and exact resolution of every returned identifier to canonical text. The quality measures are evidence recall over the range groups, citation precision over the complete relevant-range list, and evidence-strength accuracy, meaning whether the retrieved coverage supports the case's expected `sufficient`, `weak`, or `none` label. Warm-query p95 latency (excluding one-time model and index initialisation), the evidence-token volume passed downstream, and incremental cost complete the report. A predeclared selection rule picks the configuration. The retrieval-only precision is labelled diagnostic because the judge downstream may retain only the identifiers that actually support an answer.

The live release validation runs the same twelve cases through the selected retriever, the Librarian judge, Muse, Provenance, and the deterministic release validator with the live model. It measures the final user-visible projection: evidence recall and citation precision of what was actually released, an answerable-release rate, a spoiler-exposure count, and citation resolution, against the project targets of recall of at least 0.90 and citation precision of at least 0.95. Latency and provider usage are recorded per case, and the report retains the synthetic replies and agent exchanges for investigation.

### E.3 Serendipity — connection discovery and memory recall

#### Authority boundary

The authority boundary is deliberately lopsided. Serendipity has broad freedom over judgment and none over permission. A model can narrow what reaches the reader but can never widen it.

| May decide | Must preserve | May never decide |
|---|---|---|
| Which permitted source to inspect first; memory and web queries; whether evidence supports a connection; whether an optional expansion is justified; candidate interpretations, their ranking, and whether to decline | The reader's exact words as the cue; the requested intent; the presentation mode the application derived; the list of permitted sources; the frozen revision and chapter ceiling; every evidence identifier exactly as returned | Who the account holder is; whether a new source may be opened; where the spoiler boundary falls; whether anything is published; whether memory is written; whether web content may skip review |

#### Skills and contracts

Two skills share one agent, one fixed output schema (proposal, decline, or recall), and a registered validator. Connection discovery takes `ConnectionDiscoveryInput`, which carries the cue, the intent, the presentation mode, and a trusted `ConnectionScope` of `allowed_sources`, `book_scopes` with work, revision, and `chapter_max`, and optional `web_source_urls`. It returns `ConnectionProposal` or `ConnectionDecline`. Memory recall takes the same input with `intent = recall_memory` and a memory-only scope and returns `MemoryRecall`, holding one to three exact records where one is a complete recall, or a decline with reason `no_matching_memory`. The input carries authority rather than prefetched results. Application code derives the presentation mode, so that `get_recommendation` becomes *direct* and `find_connection` becomes *ask before showing*, and Serendipity must return it unchanged.

#### Decision logic

A request passes through eight stages. The application controls permissions and validates evidence. The model chooses searches, assesses support, and compares.

1. The request is raised. Muse supplies only an intent, and the application inserts the reader's actual message as the cue.
2. Permissions are sealed. Confirmed reading progress grants a revision and ceiling. Existing memories grant memory search, but only when the account's curated retrieval view has records. Web access needs both the policy flag and credentials and may be narrowed to explicit URLs. An exact-passage grant does not permit Serendipity book search.
3. Serendipity identifies the relationship the reader is asking for and inspects every explicitly requested, permitted source, within the budgets of eight model requests, six tool calls, and five results per source.
4. An evidence ledger accumulates. Every record a search returns is written to a ledger that the model cannot see or edit. A web search result is only a lead, and a page must be opened before it counts.
5. Candidates are filtered before ranking. Those the model identifies as generic, unsupported, out of scope, past the ceiling, privacy-risky, or carrying injected instructions are excluded.
6. Two or three survivors are compared and ranked against anchored categories. If the top two tie there is no winner and the result is a decline.
7. The result is verified against the ledger. Every cited identifier must resolve to a record this run retrieved, from a granted source, inside the ceiling. The web-claim flag must match the winner's real sources and the presentation must be unchanged. Any mismatch fails the run closed to a safe decline, never to a partial result.
8. Muse receives the full shortlist and the selected candidate's records. Provenance reviews the draft, the canonical evidence, and the untrusted tool outcomes including the shortlist and comparison notes, and application code validates each declaration.

There is one run per turn. A second request with the same intent reuses the decision, and a second request with a different intent is declined outright, which removes any incentive to retry until something surfaces.

Having permission to search somewhere is not a reason to search there. The routing policy is keyed to what the reader is asking for, and the order in which sources are listed carries no meaning. The table below summarises the policy.

| What the reader is asking for | Where the search starts | When it may expand |
|---|---|---|
| A link to something they reflected on before | Memory | Only if the requested relationship genuinely needs a second domain |
| Another passage, character, or pattern inside the book they are reading | Book (`search_librarian`) | Web only on explicit request, or when the book evidence cannot answer alone |
| An essay, artwork, song, thinker, or idea from outside the book and their own history | Web, opening an application-granted URL directly or searching for a lead | The book only for an explicit comparison or to make the outside result usable |
| An explicit comparison across named domains | Each named, permitted source | Never adds a domain the reader did not name |
| An open reflection with no specific evidence relationship | Decline | Never searches the web merely to manufacture novelty |

A memory candidate must be the reader's own earlier reflection on the same theme, decision, or preference, in other words a record they would recognise as the thing they wrote about before. A general lesson, an analogy, a transferable tactic, or a shared mood is not a prior basis, and a cue that no record addresses yields a decline with reason `generic_theme_match`. For other discovery requests the model may expand at most once to a second source, and only when the first returned nothing or weak evidence or the second is necessary for a materially better comparison. Inspecting all explicitly requested sources takes priority over that limit. Serendipity declines when a requested source is unavailable and stops once it has inspected the requested sources and can compare two eligible candidates.

Choosing between candidates is the most consequential design in the role. It runs in two stages that are easily conflated: a filter that removes candidates entirely, and a comparison among the survivors. Nothing that fails the filter can be rescued by comparing well.

A candidate is not a passage or a page but a proposed interpretation, which the contract forces into parts. A `tentative_claim` states the connection in one hedged sentence. The `evidence_ids` are unique, non-empty, and resolvable to this run. The `shared_structure` says what the two things have in common, and the `meaningful_difference` says how they nonetheless differ. The `interpretation` says why the pairing deserves the reader's attention, and a `comparison_note` says why it ranks where it does. Requiring both a shared structure and a meaningful difference is the anti-genericism device, and it works at the level of content rather than scoring. Structure without difference is a topic match ("both passages are about change") that tells the reader nothing. Difference without structure is two unrelated things.

In the first stage, each candidate is rated on three ordinal categories with written anchors. The ratings are labels, not numbers.

| Criterion | Strong | Middle | Rejecting |
|---|---|---|---|
| Cue fit | *direct*: answers this exact cue | *partial*: needs one inferential step | *weak*: could fit many unrelated cues |
| Reflective value | *high*: materially changes how the cue is seen | *medium*: adds a useful angle | *low*: mostly restates it |
| Safety | *clear*: within every boundary | *review*: unresolved risk | *ineligible*: violates a boundary |

A candidate is eligible only when cue fit is not *weak*, reflective value is not *low*, safety is exactly *clear*, and it carries none of six disqualifiers: generic-only, insufficient support, scope risk, privacy risk, spoiler risk, and prompt injection. Safety has no usable middle. A *review* rating is as disqualifying as *ineligible*, because an unresolved risk is not something to weigh against merit. Eligibility is derived by the contract from the ratings and never asserted separately, so an agent cannot rate a candidate weak and declare it eligible anyway.

In the second stage, survivors are ordered by cue fit first. Only on a tie does reflective value matter, and only on a further tie does safety. No weighted total is ever formed, because a total can hide a low safety rating behind a high fit score. That is exactly why filtering is a separate requirement from ranking. The consequence is structural. Since every eligible candidate already has safety *clear*, the third key never breaks a tie, the ranking collapses to two dimensions with two usable values each, and an eligible candidate can occupy exactly four strength positions. A proposal requires the top two candidates to land in different positions. Equal top ratings mean no clear winner and a decline. The skill also instructs the model not to inflate ratings to force a selection.

The contract enforces internal consistency. A proposal is rejected before it leaves the agent unless the shortlist holds two or three candidates, their claim strings differ after normalising case and spacing (which catches repeated wording rather than paraphrase), they are listed in non-increasing rubric order, the first strictly outranks the second, the selected identifier is the first candidate, every candidate's ratings and disqualifiers satisfy the eligibility rules, and every cited identifier resolves to a record this run retrieved. Each of these guarantees proves that the agent did not contradict itself, not that its ratings were right. A confidently mis-rated candidate passes every structural check. That is the gap the evaluation below exists to address.

#### Enforcement and failure behaviour

| Layer | Enforced by | Guarantee |
|---|---|---|
| Sealed grant | Application | Memory and web tools are withheld without grants. The book tool rejects ungranted calls and uses the application-owned scope. |
| Guarded retrieval | Tool wrappers | Book queries are clamped to the granted revision and chapter. Web queries are length-bounded and screened for personal data and the reader's own wording. |
| Public page access | Tool wrapper | Application-supplied URLs may be opened directly. Otherwise `get_page` requires a URL that this run's search returned. Both paths pass privacy checks, and only an opened page becomes citable. |
| Typed invariants | Schema | Shortlist size, distinctness, ordering, a strict winner, eligibility, and unchanged presentation. The validator also retries a proposal on a recall task, a recall on another intent, and a recall citing an unreturned record. |
| Ledger validation | Orchestration | Every cited identifier resolves to an in-scope record this run retrieved. Anything else fails closed. |

The privacy gate guards the moment text leaves the system, and its rule scales with how much the reader wrote. A very short message such as "Li and I divorced" is almost entirely private, so any shared token longer than one character is blocked when the source is at most eight tokens. A long passage about a book is mostly public vocabulary, and blocking every shared word would block "why" or "error", so longer text is protected against runs of three consecutive copied tokens instead, which is how copied phrasing actually escapes. Tokens are Unicode-normalised and case-folded. Raw and percent-decoded URLs are both checked, and shaped personal data and secrets are rejected by maintained detectors. Everything a tool returns is data. The model must recognise an attempt to redirect it through retrieved text and assign the `prompt_injection` disqualifier. The schema enforces the declared disqualifier but does not detect injection itself.

Declines are typed. An empty, weak, or failed search describes only that search. Weak book evidence may support a limited comparison. Evidence that cannot support the relationship yields a decline, which Muse relays honestly.

#### Working with the other roles

Muse is the only caller. It receives the validated decision with the full shortlist and the selected candidate's records, and records cited only by unselected candidates are omitted. Librarian is called through the book tool with the original cue and prior statements and returns passages plus its strength judgment. Provenance sees the finished draft, the canonical evidence, and the full shortlist with ratings and comparison notes in the untrusted tool outcomes, and must assess them rather than accept the ratings as authority. Sculptor never runs in the same workflow, but its approved curation shapes the memory view that Serendipity later searches. The Memory & Policy Service supplies the account-scoped view. Serendipity cannot see or widen the account.

#### Evaluation design

The component boundary is stated precisely. A controlled `ConnectionDiscoveryInput` and fixture-backed Librarian and Exa results go into the production agent, skill, contracts, and tool adapters, and out come one proposal or decline plus the observed search and evidence ledger. Muse invocation, live retrieval quality, Muse's presentation, Provenance review, deterministic release, and the reader's reply are outside the claim. Holding the evidence fixed is the key methodological choice. An agent handed three irrelevant passages and declining is behaving correctly, and it would be indistinguishable from one declining out of timidity if retrieval varied between runs.

Ten current cases cover eight named behaviours in the component's own order: route a book relationship to Librarian, route an external recommendation to the web and open a page before citing it, expand to a second source only when justified, stop when the primary source suffices, select evidence with a real semantic bridge rather than a topic match, rank the uniquely strongest candidate and decline on a tie, decline when no supported bridge exists, and exclude ineligible evidence before comparing. The loader refuses to run if any behaviour has no case. Cases are paired into contrast groups that differ in one material condition, for example a specific supported bridge beside a generic-theme decline, or a clear winner beside a tied-winner decline, so that a suite in which every case expects a proposal cannot reward an agent that always says yes. Routing is graded from the observed tool calls against each case's allowed, required, and ordered operations, never from any claim in the output. A separate semantic rubric judges cue fit, reflective value, meaningful difference, tentativeness, and forbidden over-claims, and can never override a hard gate. The current cases cover book and web sources. An authorised-memory case exists under `cases/future/` and is outside the baseline.

The production replay for Serendipity's Objectives (`cross_source_tentative_connection` and `weak_evidence_safe_decline`) runs the real chat path with isolated memory storage and registered corpus retrieval, with page access bounded to adopted page snapshots after production URL and privacy checks. It reports six ordered stages (invocation, retrieval, Serendipity selection, Muse presentation, Provenance review, and deterministic release), each `passed`, `failed`, or `not_reached`, with a single first-failure stage, so that a failure localises to one hand-off.

### E.4 Provenance — independent review

#### Authority boundary

| Provenance provides | Application provides |
|---|---|
| `response_decision` (`pass`, `revise`, `reject`) with typed findings | Revision, rejection, evidence checks, and release |
| `capture_decision` (`allow_capture`, `reject_capture`, `no_candidate`) with capture findings | Candidate extraction, capture policy, and storage |
| `allow`, `revise`, or `reject` for one curation proposal, echoing its digest | Digest binding, source revalidation, policy checks, apply, and audit |

#### Skills and contracts

Three skills share one agent, and no skill inherits another's policy or schema. Emotional preflight takes `EmotionalBoundaryInput`, which holds the current Line and the versioned policy, and returns `EmotionalBoundaryAssessment`, with one retry. Candidate review takes `ProvenanceInput` and returns `ProvenanceReview`, with two retries and a validator that retries finding-location mismatches. Curation review takes `CurationReviewInput`, which holds the digest, the proposal, and exact source snapshots, and returns `CurationProvenanceReview`, with one retry.

#### Decision logic

The emotional preflight is deliberately minimal. It returns `apply_boundary` only for a clear, current, first-person disclosure of intense distress or inability to cope where reflective questioning would be inappropriate. It returns `continue_reflection` for ordinary disappointment, frustration, uncertainty, literary or hypothetical content, quotations, and concern about another person. It does not diagnose, label, assess severity or intent, ask questions, suggest resources, quote the Line, or add a rationale. Policy fields describing consequences "after distress" are explicitly not evidence that distress is present. On `apply_boundary` the application returns its fixed boundary text and records that Muse did not run.

The candidate review input is organised by trust, and the review follows that organisation.

| Field | Trust | Use |
|---|---|---|
| `context.policy`, `reading_context`, `passage_scope` | Application-owned | The boundary of what may be claimed |
| `context.required_clarification` | Application-owned | The exact question validated routing selected. Asking it needs no passage, and the reply must not be rejected for failing to answer the book question |
| `canonical_book_evidence` | Frozen authority | The complete book-record set for this response |
| `canonical_connection_evidence` | Validated provenance, untrusted content | Exact selected memory and opened-page records |
| `canonical_session_lines` | Verified | Reader statements the application confirmed as exact substrings of a Line |
| `untrusted_tool_outcomes` | Untrusted | The drafter's tool calls and results, including Serendipity's shortlist |
| `candidate.response`, `evidence_uses`, `memory` | Untrusted declarations | To be verified independently, never trusted |
| `current_line.text` | Trusted provenance, untrusted content | For distress and for checking the nomination |

The reviewer must check every declaration and exact quotation and also inspect the whole reply independently, because the candidate may omit or mislabel a claim. It must complete that scan before returning `revise` and report every defect it can find, because Muse has one revision. It enforces the branch of each `librarian_search` result. A clarification branch forbids a book answer. A `sufficient` result is verified against the returned records. A `weak` result must preserve the stated limitations. A `none` result supports only "the search found no passage", never "the event is absent". A nomination is checked as an exact code-point slice of the current Line, and any paraphrase is rejected.

Two rules resolve a recurring ambiguity. Reader attribution never exempts a book-corpus claim, so a claim about characters, plot, or quotations needs a record even when framed as something the reader said. A claim with no book content, purely about the reader's own statements or life, is outside the book-evidence requirement, and when doubted it routes to `revise` with a `misattribution` finding asking Muse to attribute it explicitly, never to an unfixable `reject`.

Findings use a closed `RiskCode` taxonomy of `unresolved_evidence`, `misattribution`, `spoiler`, `unsupported_claim`, `prompt_injection`, `sensitive_content`, and `emotional_policy_violation`, with exact locations where required. A `spoiler` or `prompt_injection` finding forces `reject`. Capture findings cannot be cited against the response, and `contains_sensitive_content` is derived from them so that a caller cannot set it inconsistently. On a revision review the input adds `previous_response_review`. The reviewer must return one resolution per earlier finding, may explain that an earlier finding was mistaken, and must still inspect the whole revised reply. Unresolved findings prohibit approval.

The curation review allows each action only under the same conditions that Sculptor was given (Appendix E.6). Duplicates must be the same durable memory. A derived summary must be supported by its cited sources, preserve uncertainty, and exclude unrelated details. A topic group's members must be related yet distinct and its label supported. A tombstone must target a genuine duplicate, and a restore must be consistent with the evidence. A `revise` verdict means the action is defensible but the text, label, or source selection needs correction. A `reject` verdict means the action is unsupported, unsafe, or follows instructions embedded in memory text. Findings use the separate closed `CurationRiskCode` taxonomy of `unsupported_derivation`, `incorrect_duplicate`, `incoherent_topic`, `unsafe_tombstone`, `invalid_restore`, and `prompt_injection`, and name the affected memory identifiers. An allowed review has no findings and returns the proposal digest unchanged.

#### Enforcement and failure behaviour

| Layer | Enforced by | Guarantee |
|---|---|---|
| Fresh context | Application | No tools, no dependencies, no history. Each run sees only its typed input. |
| Closed taxonomies | Schema | Only known codes. Findings locate the affected object, and capture and response findings are separate. |
| Forced outcomes | Application | `spoiler` or `prompt_injection` forces `reject`. An unresolved prior finding blocks approval. |
| Deterministic follow-up | Application | After `pass`, every declaration is resolved against the request-scoped index and every quotation is checked verbatim. |
| Digest chain | Application and service | A curation verdict binds to the account scope, the ordered curation-state digest, the complete action, and the source hashes. A non-`allow` verdict or a digest mismatch is rejected, and the audit contract rebuilds and verifies the plan. |

A preflight failure fails closed to the safe decline before Muse runs. A candidate-review failure or an invalid review yields the safe decline, and the application never substitutes its own approval. A curation review that is missing, malformed, or mismatched blocks application.

#### Working with the other roles

Provenance reviews Muse's candidate and Sculptor's proposal but never sees Muse's history or Sculptor's selection process. It receives Librarian's frozen records as evidence and Serendipity's shortlist as untrusted outcomes. It has no contact with the Memory & Policy Service except through the digest its curation verdict carries.

#### Evaluation design

Provenance has three versioned semantic suites, one per skill, plus a focused diagnostic. All are hand-authored and reviewed rather than model-generated, on the principle that a gate evaluated on cases written by the model family it gates would not be independent evidence. Each case embeds a complete production input, so the production contract validates the case file and schema drift breaks the pack immediately. Every suite writes a metadata-only report of case identifiers, expected and actual decisions, prompt template and digest, latency, and aggregates, and never the evaluated text.

The release-gate pack holds 28 candidate-review cases built on evidence records from the real *Alice* chapters. Twelve release cases cover the five finding codes reachable on the reply path: `unresolved_evidence`, `misattribution`, `spoiler`, `unsupported_claim`, and `prompt_injection`. Twelve capture cases cover the four codes that veto automatic capture: `unsupported_claim`, `sensitive_content`, `emotional_policy_violation`, and `prompt_injection`. Each capture case carries a real exact-span nomination derived from its Line. For every code there is a positive case and a paired near-miss negative that differs minimally, plus clean controls on both axes, so that detection is measured separately from a gate that blocks indiscriminately. Four further release cases test claim-mapping completeness and the revision path: an incomplete mapping, a revision that leaves it incomplete, and a revision that repairs it without changing the prose, graded on the explicit `finding_resolutions` as well as the verdict. Grading has four axes, each of the two decisions and its finding codes, because no production code branches on a code's value and a gate that blocks for the wrong reason would otherwise be invisible. The two decisions are graded separately and never pooled. A `reject_capture` beside a released reply is correct, and two cases (a clean reply with a vetoed nomination, and a revised reply with an allowed one) exist to catch a gate that has learnt to veto whenever it revises. The `decoupling_accuracy` metric reports them. The derived `contains_sensitive_content` flag is also graded, because a veto with a non-sensitive code would silently produce the wrong deterministic outcome. The command exits non-zero when recall, over-refusal, or code-precision targets fail. The committed run predates the four claim-mapping cases and covers the 24-case pack.

The curation-gate pack covers the six curation codes, each with a positive proposal and a paired near miss in which the same action is supported by its sources, giving twelve cases. It measures whether Provenance distinguishes an unsafe action from the same action when the evidence justifies it. Prompt injection accepts either `revise` or `reject`, because the curation instructions do not fix a severity.

The emotional-boundary suite has eight cases, one per behaviour: clear first-person distress, inability to cope, ordinary frustration, literary content, quoted content, concern about a third person, and an embedded instruction in both a positive and a negative Line. It grades exact labels, reports accuracy, boundary-miss count, and over-refusal, and exits non-zero unless all eight pass.

The wrong-passage diagnostic uses four claim-mapping fixtures in two pairs to test whether Provenance checks a claim against its declared passage rather than against any available passage. Declaring only a non-supporting record must fail even when a supporting neighbour is available, and the correct-record control must pass, so that blanket rejection cannot pass the pair.

### E.5 The Memory & Policy Service

#### Automatic capture

The server builds the account context, and agents never provide an account identifier. Muse nominates an untrusted Unicode code-point slice of the current message. Provenance returns a capture decision that is independent of the response decision. The application binds the hand-off by validating source offsets, evidence identifiers, event identity, the review verdict, and the release source, and it suppresses every write on an emotional boundary or a safe decline. The service then requires capture to be enabled, a review allowance, no sensitive content, and a matching idempotent retry. It hashes the account key, derives an idempotency key, creates the record without overwrite, and returns created-or-reused. A committed capture produces a visible notice and nothing else. The interactive application exposes no save, review, correction, or deletion action.

#### Memory model and reviewed curation

The original layer is append-only. Each capture produces one immutable Markdown record with its identifiers, source event, evidence identifiers, and timestamps. The curation layer records Sculptor's applied proposals: duplicate links, versioned derived summaries that cite their originals, topic groups, and reversible retrieval tombstones. A `CurationPlan` binds one proposal to its account, source hashes, and base curation state. Provenance must allow that exact digest. The service then appends an immutable event, verifies the persisted state, and reuses an exact retry. The `list_for_retrieval` projection returns originals, summaries, and topic groups without rewriting sources, and duplicate links preserve retrievable text. Because there is no model in the service, its properties are established by contract tests rather than by model evaluation.

### E.6 Sculptor — memory curation and surfacing

#### Authority boundary

| May decide | Must preserve | May never decide |
|---|---|---|
| Under curation, one supported retrieval change or no change. Under surfacing, a suggestion now, a deferral, or silence. Each uses only the supplied memories and context | The originals, verbatim; every supplied identifier; uncertainty and corrections in the sources; the supplied clock | Which account or memories to inspect; what should be captured; whether a proposal is stored; whether an original may be edited or deleted; when to suggest a memory to the reader (curation) |

#### Skills and contracts

Two skills share one agent, with no tools and one output retry each. Memory curation takes `AccountScopedMemories`, which holds two to twelve records from one account as identifier and text only, with the account identity removed. It returns a `CurationProposal` with exactly one action or a `NoCurationProposal` with a reason. Memory surfacing takes `SurfacingInput`, which holds bounded memories, `context.now`, the current situation, and a history of prior suggestions and feedback. It returns `SurfaceNow` (a suggestion, a rationale, and source identifiers), `Defer` (a timezone-aware time or an observable condition), or `DoNotSurface` (a typed reason).

#### Decision logic

Curation follows one pattern: prefer the narrower action, and prefer no change under ambiguity. The table sets out when each action may be used.

| Action | Use only when | Must not |
|---|---|---|
| `link_duplicates` | Every source expresses the same durable memory | Link on similar words or a shared topic |
| `update_derived_summary` | Memories update, refine, or correct one evolving fact, and each cited source contributes to it | Cite topical noise; present conflicting versions as simultaneously true; drop corrections, changes over time, or unresolved uncertainty |
| `assign_topic_group` | Memories share a useful theme but each remains a separate, independently useful fact | Use a group to avoid resolving an update to one fact |
| `tombstone_for_retrieval` | A record is already linked to a distinct canonical duplicate. Suppresses retrieval and never deletes | Infer link state from wording or identifiers |
| `restore_to_retrieval` | Reversing such a tombstone is consistent with the evidence | |
| `no_curation_proposal` | The distinction is ambiguous or the required state is not established | |

When both a summary and a group seem plausible, one changing fact takes the summary and distinct facts take the group. Sculptor may not infer existing duplicate links or tombstone state from memory wording. When the input does not establish the required state, it chooses another supported action or no change.

For surfacing, silence is a successful outcome. A `surface_now` decision needs a specific, useful, and timely suggestion grounded in the supplied records and situation. A shared word, a broad topic, or a vague association is not enough, and no event, preference, commitment, or personal fact may be invented. A `defer` decision needs a concrete future time or an observable condition and does not schedule anything. A cancelled, completed, superseded, or unsupported opportunity is not deferred merely to avoid silence. A `do_not_surface` decision covers evidence that is irrelevant, insufficient, superseded, or repetitive, or that would require a sensitive inference (reason `sensitive_inference`). Empty memories yield `insufficient_evidence` rather than an invented suggestion. Prior suggestions are respected: nothing is repeated without a material change, dismissals and active suppression periods hold, and expiry alone does not renew usefulness. Sculptor uses only the supplied clock and never claims that a suggestion was delivered, a reminder scheduled, or a record changed.

#### Enforcement and failure behaviour

| Layer | Enforced by | Guarantee |
|---|---|---|
| Bounded input | Application | Two to twelve unique records from one trusted scope, with the minimum text needed. |
| Strict schemas | Contract | Unknown fields, repeated identifiers, out-of-scope sources, and oversized summaries or labels are rejected. A tombstone cites target and canonical, and a restore cites its single target. |
| No original mutation | Contract | The output has no operation that edits or deletes an original. |
| Digest-bound review | Provenance and application | A `CurationPlan` binds the proposal to account, source hashes, and base curation state. Only an `allow` verdict echoing that digest can be applied. |
| Source freshness and audit | Memory & Policy Service | Sources are re-read and re-hashed after the agent calls. Stale, unknown, cross-account, or changed sources are rejected, and an immutable audit event is appended and verified. |

A malformed proposal is retried once and then rejected. A proposal that Provenance does not allow, or whose sources changed between selection and application, is dropped without effect. Surfacing has no production consumer, so its decisions are validated and graded offline.

#### Working with the other roles

Sculptor never runs inside a conversation turn and has no contact with Muse or Serendipity. Its curation proposals are reviewed by Provenance's curation-review skill and applied by the Memory & Policy Service. Its approved results change the retrieval view that Serendipity's memory search and Muse's memory evidence later read.

#### Evaluation design

The curation baseline has five fixed cases, one per behaviour: an exact duplicate, a paraphrased duplicate, a noisy evolving fact that requires a derived summary, a related topic group, and a superficial similarity that must produce no change. Each supplies one bounded account-scoped memory set, the expected action, immutable-original and provenance requirements, and forbidden outcomes. The hard gates are deterministic: response kind, action, source-memory identifiers, schema, provenance boundary, and summary length. The generated summary text and topic labels carry a separate rubric.

The Pottery scenario is a bounded-curation replay. It converts each Scene's active same-account Props into `AccountScopedMemories` and calls production `propose_curation`, recording source hashes before and after every call, the complete observable exchange, the typed output, the hard-gate result, separate semantic criteria, and correlated trace identifiers. Its five Scenes (`scene-exact-duplicate`, `scene-paraphrased-duplicate`, `scene-evolving-fact-with-noise`, `scene-related-distinct-with-distractor`, and `scene-superficial-similarity`) are the ones shown in the Logfire figures in Section 9.2. The replay exercises the proposal only. It does not invoke Provenance's curation review or the apply-and-audit loop, which are covered by the curation-gate suite (Section 5.4) and by contract tests.

The offline surfacing harness grades the decision contract on timely, deferred, superseded, repeated, unsupported, and sensitive situations. Hard gates check source selection, decision, refusal reason, and deferral kind and time. Suggestion quality and the meaning of a deferral condition require independent review. The provider-backed replay supplies bounded synthetic memories, the current context, a fixed decision time, and prior surfacing history to the tool-free agent and records source preservation, decision metrics, and complete exchanges. Offline scores do not establish the conversational `proactive_memory_surfacing` Objective, which additionally requires reviewed capture, applied curation, later fresh-session use, and reviewed release.

## Appendix F. Related work and technology rationale

### F.1 Related work

Grounding model output in retrieved text (Lewis et al., 2020) is the standard defence against fabricated facts, but retrieval alone does not verify that the generated text is faithful to what was retrieved. Anthropic's contextual-retrieval work (Ford, 2024) reports that hybrid lexical and embedding retrieval with reranking materially reduces retrieval failures. Linger adopts that combination and measures it on its own corpus (Section 5.2). It differs from ordinary retrieval-augmented generation in two ways. Retrieval is bounded by a reading boundary before search, and the retrieved passages are treated as evidence to be verified against the reply rather than as context to prompt with.

ScientistOne (Meng et al., 2026) defines a chain-of-evidence standard under which every research claim must trace through recorded supporting claims to a grounding source. The authors report that building this into the generation workflow, rather than auditing afterwards, eliminated hallucinated references across 337 bibliography entries. Linger's `supported_claims` mapping (Section 3.4) is a conversational analogue: every evidence declaration names the exact reply spans it supports, and Provenance checks both the mapping and the unmapped remainder. Linger adds a chain of authority to the chain of evidence. Evidence must not only support the reply but also be permitted for this reader and this request.

Anthropic's guidance on context engineering (Rajasekaran et al., 2025) argues for minimal, curated context per call and for keeping system state outside the model. Weng (2026) describes harness engineering, the scaffolding of typed contracts, gates, and feedback loops around a model, as the practical locus of near-term self-improvement. Both inform Linger's decision to give each agent only a task-specific projection of state, to keep session history under application control, and to treat self-improvement as human-reviewed proposals only (Section 8.7).

Greshake et al. (2023) showed that instructions embedded in retrieved content can redirect an LLM application. Linger's response is structural. All retrieved content, memories, photographs, and model candidates are labelled untrusted, tool grants are owned by the application so that an injected instruction gains no authority, and a `prompt_injection` finding by Provenance forces rejection with no revision. The OWASP Top 10 for LLM Applications (OWASP, 2025) supplies the vocabulary for the risk register in Section 7.

Singapore's Model AI Governance Framework (IMDA, 2020) and its generative-AI companion (IMDA, 2024) organise governance around internal structures, the level of human involvement, operations management, and stakeholder communication. Section 6.4 maps Linger's practices onto those headings.

### F.2 Technology choices in full

The first choice is five roles rather than one prompt. A single well-instructed model could be asked to reflect, retrieve, connect, curate, and check itself. The decomposition exists for authority, not capability. A component that cannot see the memory store cannot leak it. A reviewer with no history cannot be talked round by the draft it is reviewing. A curator that returns only identifiers cannot rewrite an original. Each boundary in Figure 1 corresponds to something the application can enforce in code and test without a model. The price is more model calls per turn and a coordination surface that itself needs evaluation, which is why Sections 4 and 9 exist.

The second is application-orchestrated hand-offs rather than an agent-graph framework. Frameworks such as LangGraph, AutoGen, and CrewAI model agents routing to one another. Linger's dominant risk is a model widening its own authority. That risk is easiest to control, and to test with ordinary unit tests, when sequencing, grants, and release live in plain Python in one file.

The third is Pydantic AI. It supplies typed input and output with validation retries, per-run instructions and output types, a capability and toolset model, provider abstraction, Logfire instrumentation, and a maintained Exa search capability. Choosing it removed the need for any custom tool-dispatch or web-client code. The specification forbids re-implementing generic tooling locally.

The fourth is one agent per role with per-run skills. Keeping five role objects preserves the per-role tool and validator authority and the "five roles" mental model, while making each task's instructions, schema, and retries explicit and fingerprinted.

The fifth is deterministic retrieval with model judgment on either side. Spoiler safety cannot depend on a model's discretion. Retrieval is a scoped, testable service, and the Librarian model judges only the reading boundary and the evidence strength.

The sixth is hybrid BM25 and dense retrieval with cross-encoder reranking, chosen on measurement (Section 5.2). Reranking raised retrieval-only citation precision from roughly 0.3 to 0.83 and evidence recall to 0.92 at a p95 latency of 0.46 seconds, on local models at zero token cost.

The seventh is Logfire under a written data contract. Traceability without content leakage is enforced by a typed projection and an exported-payload test rather than by convention.

The last is Markdown file stores. They are adequate for a single-user prototype, and immutability plus content hashing are simpler to reason about than a database with migrations.

## Appendix G. List of figures and tables

| Item | Title | Section |
|---|---|---|
| Figure 1 | Logical architecture | 3.2 |
| Figure 2 | The five roles and the authority boundary | 3.2 |
| Figure 3 | One chat turn | 3.3 |
| Figure 4 | The starting page | 3.5 |
| Figure 5 | The grounded reply | 3.5 |
| Figure 6 | Librarian contract detail | 3.5 |
| Figure 7 | Provenance revision loop | 3.5 |
| Figure 8 | What ran, in order | 3.5 |
| Figure 9 | Runtime skills on one reusable agent | 3.6 |
| Table 1 | Typed hand-off envelopes | 3.7 |
| Figure 10 | The Reader tool | 3.8 |
| Figure 11 | A saved evaluation Scene | 3.8 |
| Figure 12 | Physical architecture of the local prototype | 3.8 |
| Table 2 | Technology and architecture choices | 3.9 |
| Table 3 | The scenario-replay vocabulary | 4.1 |
| Table 4 | The Objective catalogue | 4.3 |
| Figure 13 | The scenario lifecycle | 4.3 |
| Table 5 | Saved evaluation Scenarios | 4.3 |
| Table 6 | Muse measures | 5.1 |
| Table 7 | Retrieval strategy benchmark | 5.2 |
| Table 8 | Serendipity measures | 5.3 |
| Table 9 | Provenance release gate | 5.4 |
| Table 10 | Provenance curation gate | 5.4 |
| Table 11 | Provenance emotional preflight measures | 5.4 |
| Table 12 | Memory-retrieval measures | 5.5 |
| Table 13 | Sculptor measures | 5.6 |
| Figure 14 | The LLMSecOps loop | 8 |
| Figure 15 | Logfire Agents view | 8.5 |
| Figure 16 | A Sculptor run in the Logfire Live view | 8.5 |
| Table 14 | Contract-test coverage by area | 9.1 |
| Table 15 | Scenario replay, iteration 18 | 9.2 |
| Figure 17 | Logfire Evals overview | 9.2 |
| Figure 18 | The failing Scene in Logfire | 9.2 |
| Table 16 | Cost and latency measures | 9.3 |
| Table 17 | Guarantee traceability matrix | 9.4 |
| Table 18 | Metric coverage by agent | C |
| Table 19 | AI security risk register | D |
