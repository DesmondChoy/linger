# Sources for the Final Project Report

This document collects academic papers, frontier-lab engineering articles, and
expert technical syntheses that may support the final Linger report. Sources are
organised by Linger's five named agents and by overall architecture. A source
with broad relevance has one full record at its primary location and scoped
cross-references under every other affected agent.

| Source | Architecture | Muse | Librarian | Sculptor | Serendipity | Provenance |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| ScientistOne / Chain-of-Evidence | Yes | Yes | — | — | — | Yes |
| Anthropic: Contextual Retrieval | — | — | Yes | — | Yes | — |
| Anthropic: Effective Context Engineering | Yes | Yes | Yes | Yes | Yes | Yes |
| Weng: Harness Engineering | Yes | — | — | Yes | — | Yes |

## Overall Architecture

### ScientistOne: Towards Human-Level Autonomous Research via Chain-of-Evidence

- **Source type:** Academic preprint with a reported multi-system evaluation.

- **Reference:** Meng, R., Dalvi Mishra, B., Chen, J., Li, C.-L., Goyal, P.,
Parmar, M., Song, Y., Song, Y., Sinha, R., Ranganathan, P., Gokturk, B., Yoon,
J., & Pfister, T. (2026). *ScientistOne: Towards Human-Level Autonomous Research
via Chain-of-Evidence*. arXiv:2605.26340.
[https://doi.org/10.48550/arXiv.2605.26340](https://doi.org/10.48550/arXiv.2605.26340)

- **Core contribution.** The paper defines Chain-of-Evidence (CoE), a
verifiability standard requiring every research claim to trace through recorded
supporting claims to a grounding source. ScientistOne constructs these links
while reviewing literature, running experiments, and writing a paper. A
separate CoE Integrity Audit checks reproduced scores, task-rule violations,
reference existence, and agreement between described methods and submitted
code.

- **Evidence reported.** Across 75 generated papers from five autonomous research
systems, the authors report systematic evidence failures in every baseline.
ScientistOne produced no hallucinated references among 337 bibliography
entries, reproduced all 12 scores eligible for verification, and aligned its
method descriptions with code in 14 of 15 papers.

- **Architectural relevance.** CoE supports Linger's separation of generation,
evidence retrieval, semantic review, deterministic validation, and release
authority. Both systems build provenance into the workflow rather than trying
to reconstruct it after publication or display. Linger extends that approach
with reader-specific evidence authority, privacy, spoiler, sensitive-inference,
prompt-injection, and memory-capture controls.

- **Limitations.** CoE models explicit claim chains, whereas Linger's current
book-corpus slice implements a complete response plus declared evidence uses,
exact quotations, and source locations. CoE's native provenance measurement
also concentrates on numerical claims; citation support is judged largely from
abstracts, and qualitative overclaims and false negatives remain possible.

- **Possible report use.** Frame Linger as combining a chain of evidence with a
chain of authority: evidence must support the response and be permissible for
this reader and request.

### Effective Context Engineering for AI Agents

- **Source type:** Frontier-lab engineering guidance based on Anthropic's applied
experience; not a controlled academic evaluation.

- **Reference:** Rajasekaran, P., Dixon, E., Ryan, C., & Hadfield, J. (2025,
September 29). *Effective context engineering for AI agents*. Anthropic.
[https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

- **Core contribution.** The article treats model context as a finite attention
budget and recommends supplying the smallest high-signal set of instructions,
tools, examples, history, and retrieved data that supports the task. It covers
just-in-time retrieval, progressive disclosure, compaction, external notes, and
specialised agents with isolated contexts.

- **Architectural relevance.** This supports Linger's bounded specialist
contexts, narrow tool surfaces, compact session state, stable evidence
identifiers, and just-in-time evidence loading. Each role receives only what it
needs; working context is kept distinct from durable product memory.

- **Limitation.** The article provides practitioner design rationale, not evidence
that Linger's implementation is effective. Its discussion of agent-written
notes does not authorise autonomous personal-memory capture in Linger.

- **Possible report use.** Cite it when explaining why Linger minimises and
isolates context instead of sharing the full conversation, corpus, and memory
archive with every agent.

### Harness Engineering for Self-Improvement

- **Source type:** Expert technical synthesis by Lilian Weng, surveying academic
and frontier-lab work; useful as a source map, but secondary evidence for the
underlying empirical claims.

- **Reference:** Weng, L. (2026, July 4). *Harness Engineering for
Self-Improvement*. Lil'Log.
[https://lilianweng.github.io/posts/2026-07-04-harness/](https://lilianweng.github.io/posts/2026-07-04-harness/)

- **Core contribution.** Weng defines a harness as the software surrounding a
model that manages workflow, tools, context, persistent state, permissions, and
evaluation. The article surveys file-backed memory, isolated sub-agents,
context playbooks, workflow optimisation, and self-improving harnesses. It also
argues that evaluators and permission controls should remain outside an
optimisation loop, with held-out tests, trace audits, and human review at
important decisions.

- **Architectural relevance.** The framing closely matches Linger's
application-owned orchestration: deterministic code controls hand-offs,
release, account scope, and writes, while models return bounded proposals. It
also supports Section 9's human-gated failure-to-eval and playbook-curation
loops.

- **Limitations.** Linger does not implement open-ended recursive
self-modification. Agents may propose evaluation cases or playbook edits, but
cannot modify prompts, policies, code, or their own authority. Specific
empirical claims from Weng's survey should cite the underlying primary papers.

- **Possible report use.** Use Weng to define the harness layer and motivate
Linger's external permission, evaluation, and human-approval gates.

## Muse

### ScientistOne / Chain-of-Evidence

- **Source record.** See the [full source record](#scientistone-towards-human-level-autonomous-research-via-chain-of-evidence).

- **Relevance.** ScientistOne's evidence-aware writing pipeline parallels Muse's obligation to
produce a complete candidate with declared evidence uses rather than prose that
is sourced afterward. The comparison is limited: Muse supports reflective
dialogue, not scientific paper production, and its declarations remain
untrusted hints rather than release authority.

- **Possible report use.** Explain why Muse produces a candidate for review and
cannot send its own output directly to the reader.

### Effective Context Engineering

- **Source record.** See the [full source record](#effective-context-engineering-for-ai-agents).

- **Relevance.** The article supports giving Muse a minimal prompt, compact conversation state,
and narrow specialist hand-offs instead of the entire corpus and memory
archive. Its recommendation to use clear, non-overlapping tools also aligns
with Muse having no general-purpose tool surface.

- **Boundary.** Context minimisation does not remove the evidence needed for a
grounded answer, and compaction must not silently convert a summary into durable
product memory.

## Librarian

### Introducing Contextual Retrieval

- **Source type:** Frontier-lab engineering article reporting internal retrieval
experiments; not a peer-reviewed paper.

- **Reference:** Ford, D. (2024, September 19). *Introducing Contextual
Retrieval*. Anthropic.
[https://www.anthropic.com/engineering/contextual-retrieval](https://www.anthropic.com/engineering/contextual-retrieval)

- **Core contribution.** Anthropic describes prepending a short, document-aware
description to each chunk before constructing both embedding and BM25 indexes.
Their tested pipeline combines contextual embeddings, contextual BM25, rank
fusion, and reranking.

- **Evidence reported.** In Anthropic's tested domains and top-20 setup,
contextual embeddings plus contextual BM25 reduced retrieval failure from 5.7%
to 2.9%; adding reranking reduced it to 1.9%. These are relative reductions of
49% and 67%.

- **Librarian relevance.** Literary passages often contain pronouns, dialogue, or
scene-dependent phrases that make weak standalone chunks. A derived contextual
prefix is therefore a candidate for Linger's planned comparison of keyword,
semantic, hybrid, fusion, and reranked retrieval.

- **Boundaries.** The prefix must remain derived index metadata, never source text
or citation authority, and it must not expose information beyond the request's
spoiler boundary. Anthropic's top-20 results do not predict Linger's Recall@5 or
nDCG@5; the method must earn its place against Linger's frozen retrieval cases,
latency, and cost. Simpler bounded reads or ordinary hybrid retrieval may still
win for the small initial corpus.

- **Possible report use.** Cite the article as practitioner evidence for testing
document-aware chunk enrichment and reranking, not as evidence that Linger
achieved Anthropic's improvements.

### Effective Context Engineering

- **Source record.** See the [full source record](#effective-context-engineering-for-ai-agents).

- **Relevance.** The article's just-in-time retrieval and progressive-disclosure guidance maps
directly to Librarian: retain stable evidence references, retrieve only the
minimum authorised excerpts needed for the request, and avoid injecting the
whole corpus or memory archive.

## Sculptor

### Harness Engineering

- **Source record.** See the [full source record](#harness-engineering-for-self-improvement).

- **Relevance.** Weng's treatment of context as a structured, file-backed playbook maps closely
to Sculptor's second corpus: bounded operational records become proposed,
deduplicated playbook edits. The Generator/Reflector/Curator pattern surveyed in
the article is useful prior-art routing for Linger's failure detection and
Sculptor curation loop.

- **Boundary.** Sculptor proposes changes but cannot merge them, modify prompts,
or expand its own authority. Human review and CI remain outside the loop.

### Effective Context Engineering

- **Source record.** See the [full source record](#effective-context-engineering-for-ai-agents).

- **Relevance.** Structured external notes and periodic curation support Sculptor's purpose:
preserve original records while deduplicating and improving derived summaries
and links. However, Anthropic's agentic-memory example is not a precedent for
unreviewed personal-memory capture; Linger's deterministic Memory & Policy
Service remains the only write authority.

## Serendipity

### Contextual Retrieval

- **Source record.** See the [full source record](#introducing-contextual-retrieval).

- **Relevance.** Contextual retrieval may improve the internal-evidence leg of Serendipity's
search because Serendipity uses the same bounded Librarian adapters. It does not
justify contextualising private memories into public web queries, and it says
nothing about verifying web evidence.

### Effective Context Engineering

- **Source record.** See the [full source record](#effective-context-engineering-for-ai-agents).

- **Relevance.** The article's hybrid, just-in-time exploration model fits Serendipity's role:
start from lightweight cues, retrieve only relevant internal or web evidence,
and progressively disclose more context when the task warrants it.

- **Boundary.** Serendipity may propose a tentative connection but cannot release
it, write a memory, or treat retrieved instructions as authority. Runtime
exploration must remain within its bounded internal-search and Exa surfaces.

## Provenance

### ScientistOne / Chain-of-Evidence

- **Source record.** See the [full source record](#scientistone-towards-human-level-autonomous-research-via-chain-of-evidence).

- **Relevance.** ScientistOne's Claim Verifier is the clearest analogue to Provenance: both sit
between generated prose and release, compare a complete draft with supplied
evidence, and cause unsupported material to be revised or removed.

- **Difference.** Linger's gate is broader. Provenance independently inspects the entire response
instead of trusting Muse's declarations and also checks attribution, privacy,
spoilers, account boundaries, sensitive inference, prompt injection, and
automatic memory capture. It provides separation of duties, not guaranteed
model independence.

- **Possible report use.** Cite CoE as evidence that generation and verification
should be separate stages, then explain Linger's extension from claim
verifiability to safe, authorised per-turn release.

### Effective Context Engineering

- **Source record.** See the [full source record](#effective-context-engineering-for-ai-agents).

- **Relevance.** Role isolation and minimal high-signal context directly support Provenance's
design: it receives the complete candidate, authorised evidence, and applicable
policy constraints, but no tools or conversation history that could bias or
expand the review task.

### Harness Engineering

- **Source record.** See the [full source record](#harness-engineering-for-self-improvement).

- **Relevance.** Weng's recommendation that permission controls and evaluators sit outside the
loop being improved supports Provenance's lack of release or write authority.
The application, held-out evaluations, CI, and humans remain the actual gates;
Provenance supplies a verdict rather than controlling deployment or policy.
