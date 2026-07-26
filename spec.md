# Linger: A Personal Reading Memory Companion

Status: **Early idea for team discussion**

This is not an approved specification or a commitment to build the project. The team may simplify, reshape, or reject it after testing the core assumptions.

## The idea

Readers rarely leave a book with only a rating or a desire for the next recommendation. They retain fragments: a quotation, character, plot moment, question, or personal interpretation.

Linger—named after the Cranberries song—would help a reader discuss and preserve those fragments. Later, it could suggest a tentative connection between a saved reading memory and another book, a user-selected song, or a photograph. The reader remains in control of what is stored and whether a proposed connection is meaningful.

[Project Gutenberg](https://www.gutenberg.org/) is a long-running online library of more than 75,000 free eBooks, focused on older works whose U.S. copyright has expired; it provides the prototype's initial book corpus.

## Core hypothesis

A reading companion will be more useful when it can:

1. help the reader articulate why part of a book mattered;
2. preserve that reflection with supporting textual evidence; and
3. reconnect it to a later book, song, or experience without inventing meaning or becoming intrusive.

The prototype will test that product hypothesis through the four AAS modules:

| AAS module | Hypothesis and implementation in Linger |
|---|---|
| Explainable and Responsible AI | Readers will trust connections more when quotations, user statements, and generated interpretations are clearly separated; supporting passages and uncertainty are visible; and storage, correction, and deletion remain under user control. The prototype implements citations, provenance, explicit confirmation, data minimisation, and documented corpus limitations. |
| AI and Cybersecurity | Agent separation is useful only if it reduces disclosure and tool misuse. A deterministic policy service will enforce user isolation, scoped memory access, confirmation, and deletion. Tests will cover prompt injection in retrieved content, fabricated quotations, forbidden memory requests, log leakage, and deleted-data retrieval. |
| Architecting Agentic AI Solutions | Specialised agents may produce safer and more useful results than one general agent. The Reading Companion chooses retrieval and follow-up actions; the Connection Agent searches authorised evidence and may decline to create a link; and the Verifier independently accepts, revises, or rejects proposals. The same cases will be run through a credible single-agent baseline. |
| Integrating and Deploying AI Solutions | Versioned prompts, corpus builds, tool contracts, policies, and evaluation cases should make changes reproducible and regressions detectable. The prototype will use automated contract, retrieval, security, and end-to-end tests; basic workflow tracing; cost and latency measurements; CI/CD; and a reproducible test deployment. |

These are hypotheses, not foregone conclusions. If the single-agent baseline performs equally well, an agent boundary should be removed. Multiple characters in a workflow are not automatically a multi-agent architecture.

## Proposed prototype

The minimum end-to-end experience is:

1. The reader selects one of a small set of Gutenberg books.
2. A Reading Companion discusses the book and retrieves supporting passages.
3. It asks a small number of useful follow-up questions and drafts a structured memory.
4. The reader edits, confirms, or rejects the memory before anything is stored.
5. The reader selects a song or uploads a photograph, optionally explaining what it means to them.
6. A Connection Agent chooses relevant authorised memories and passages, then proposes a grounded, explicitly tentative link.
7. A Verifier checks the evidence, privacy boundary, and interpretive overreach before the result is shown.
8. The reader may save, dismiss, or delete the result and the original memory.

Book recommendations are a possible extension, but they are not the distinctive part of the prototype.

### Song-based experience

The song feature should be more than playlist recommendation:

- **Song as a memory cue:** Given a song, the agent retrieves a small number of potentially relevant reading memories and explains the evidence for each connection.
- **Reading soundtrack:** Given a confirmed memory or book theme, the agent proposes a song and explains whether it echoes, contrasts with, or reframes the memory.
- **Changing interpretation:** If the user revisits a pairing later, the agent can compare the new reflection with the earlier confirmed one without rewriting history.

For the first prototype, only the song-as-memory-cue flow is required. The agent may ask for clarification, revise after verification, or return "no responsible connection found." Nearest-neighbour matching by itself is not agentic.

## Candidate system shape

The initial design should contain only components with distinct responsibilities:

| Component | Responsibility |
|---|---|
| Reading Companion agent | Chooses when to retrieve passages, conducts the reflection, handles uncertainty, and proposes a memory. |
| Connection Agent | Searches authorised memory summaries, book passages, and permitted media information to propose a cross-book, song-to-book, or photo-to-book connection. It may return no connection. |
| Verifier agent | Independently checks quotations, connection evidence, privacy scope, prompt injection, copyrighted-content handling, and unsupported sensitive inferences. |
| Memory and policy service | Deterministically enforces confirmation, user isolation, access permissions, storage, and deletion. This is a service, not an agent. |

The exact number of agents remains open. An agent should be retained only if it demonstrates meaningful reasoning, tool use, state, or coordination that cannot be replaced by a normal service or prompt section.

Two-way conversation alone is not evidence of agentic behaviour. The demo should show agents selecting tools, responding to incomplete evidence, coordinating through defined inputs and outputs, and failing safely.

## Minimum scope

The prototype must:

- ingest 3-5 selected Gutenberg books with source metadata;
- retrieve passages using stable citations;
- distinguish quotations, user statements, and generated interpretations;
- require explicit confirmation before storing a memory;
- use only authorised memory content when generating a connection;
- present connections as hypotheses rather than facts;
- support one song-to-memory connection using a user-supplied song title, artist, and optional personal note;
- reject or revise fabricated quotations, injected instructions, and intrusive inferences;
- let the user delete a memory from application-controlled storage and retrieval;
- record enough provenance to explain the important steps;
- provide a simple web interface for the end-to-end demonstration; and
- compare the same representative cases using a single-agent baseline.

## Data used for the prototype

- **Books:** 3-5 deliberately selected Project Gutenberg texts. Their applicable rights and source metadata must be recorded.
- **Reading memories:** Synthetic examples and reflections created by the team. No real private archive is required.
- **Songs:** User-selected titles, artists, optional personal notes, and only metadata or descriptors the prototype is permitted to use. Full lyrics and audio are not required.
- **Images:** Manually uploaded, user-selected, or synthetic images. There will be no live Google Photos integration.
- **Evaluation cases:** A small, fixed set covering ordinary use, unsupported claims, privacy violations, prompt injection, and deletion.

## Responsible AI and security essentials

- The user must approve persistent memories and any analysis of personal media.
- Application code, not model instructions, must enforce permissions and deletion.
- Retrieved book text and media descriptions must be treated as untrusted data.
- Agents receive only the minimum information needed for the current task.
- Generated interpretations must show uncertainty and must not be attributed to the user without confirmation.
- The system must not claim an authoritative song meaning, fabricate lyrics, or reproduce or store copyrighted lyrics without permission.
- The system must avoid inferring sensitive traits such as health, religion, sexuality, ethnicity, or political affiliation.
- Logs and general telemetry must not contain raw personal memories.
- Prototype claims apply only to the tested system and evaluation set; the team should not claim universal security or production readiness.

## Minimum evidence of success

The team should be able to demonstrate that:

1. a normal reading-memory and connection workflow completes with inspectable citations;
2. no memory is persisted without confirmation;
3. a fabricated quotation is rejected or marked unsupported;
4. an instruction hidden in a book passage or image cannot obtain protected memories;
5. deleted content is no longer returned by the application's retrieval system;
6. human reviewers find at least some proposed book, song, or image connections useful and non-intrusive; and
7. the comparison shows where multiple agents help and where they do not.

Initial percentage targets should be set only after running a proof of concept. Evaluation should remain small enough to build and review properly while covering grounding, privacy, security, usefulness, latency, and cost.

## Explicitly out of scope

- Live Google Photos, messaging, or social-network integrations
- Music-streaming integration or a stored catalogue of full songs or lyrics
- The full Project Gutenberg catalogue
- Copyrighted books without permission
- A production recommendation platform
- Continuous monitoring or unsolicited resurfacing of personal content
- Mental-health assessment or psychological profiling
- Training a foundation model
- Production-grade scale, availability, or regulatory-compliance claims
- Extra agents created solely to give every participant an agent

## Questions the team must answer before committing

1. Is this a problem the team finds valuable enough to spend the module on?
2. Can a small proof of concept produce book-to-song connections that feel useful rather than forced?
3. Which agent boundaries provide measurable value over a single-agent baseline?
4. Is the Verifier needed for every response or only higher-risk actions?
5. What personal data, if any, may be sent to an external model provider?
6. Can a platform or evaluation workstream satisfy the individual-report expectations, or must each member own an agent?
7. Can the complete vertical slice, evaluation, deployment, and reports fit within 60-75 person-days?

## Suggested next step

Brief the team using this document, gather objections and alternatives, and then time-box a small proof of concept. It should test cited Gutenberg retrieval, one reading-memory conversation, one song-to-book connection, one adversarial case, and the single-agent baseline. A photo connection can follow if the core flow works. Only after that evidence exists should the team write a detailed proposal or system specification.
