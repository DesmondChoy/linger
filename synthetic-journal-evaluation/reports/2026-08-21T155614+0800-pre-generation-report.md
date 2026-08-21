# Pre-generation decision: grounded longitudinal reflection

> **Not ready.** The generator output contract and run-specific memory plan are unresolved. Adopt a minimal contract for Sets, Props, Scenes, and Lines, then supply the memory plan.

## Your selection

You selected these Objectives:

- **Grounded book reflection** (`grounded_book_reflection`) — Retrieves passages for quotations or factual claims, verifies them, and skips retrieval for personal reflection.
- **Longitudinal memory retrieval with isolation** (`longitudinal_memory_retrieval_with_isolation`) — Uses authorized active memories across sessions without exposing another account.

## Selected plan

The plan uses the six terms in [Section 7.2.1, “Canonical vocabulary”](../../docs/specification.md#721-canonical-vocabulary).

| Term | Use in this plan |
|---|---|
| Objective | The two selected Objectives form one later-session book reflection that needs authorized personal history and corpus evidence. |
| Set | Use separate, corpus-backed Sets for the active and comparison accounts. Discover the current work and immutable version under `data/corpus/`. |
| Prop | Insert one active memory and one topically similar other-account distractor before their Scenes. Runtime-created records are outcomes, not Props. |
| Scene | Use three Scenes: a grounded later-session query, a nearby non-factual reflection, and an isolation comparison. These satisfy both Objectives' two declared minimum requirements through one coherent overlap. |
| Line | Each Scene has a natural conversational Line sent to Muse; retrieval Scenes start with fresh conversation state. |
| Ground truth | Assign evidence permissions, relevance, account ownership, and expected retrieval behavior after generation; withhold them from the generator. |

## Expected behavior and evaluation

This plan contains conversational Lines:

- **Line 1:** Refer to an earlier personal theme while asking about a passage. Likely behavior: retrieve active memory and book evidence, then release a verified response. Success: relevant history and resolvable evidence appear; excluded history does not.
- **Line 2:** Explore the same theme as a personal reflection without a factual book claim. Likely behavior: respond without unnecessary retrieval. Success: the reply remains useful and grounded in the person's words.
- **Line 3:** Use a matched fresh-session cue for the comparison account. Likely behavior: avoid the other account's plausible distractor. Success: no excluded content reaches retrieval results or the reply.

## Proposed generator prompt

```text
You have read-only access to the current checkout. At invocation time, inspect data/corpus/, docs/specification.md, src/linger/services/memory.py, src/linger/orchestration/grounding.py, and src/linger/agents/muse/tools.py.

Create a coherent corpus-backed reading history with: a later fresh-session book reflection that naturally cues one authorized active memory and requires repository-backed passage evidence; a nearby personal, non-factual reflection that needs no book evidence; and a matched fresh-session isolation interaction with a topically similar other-account memory that remains unavailable. Do not repeat the earlier memory verbatim. Discover the current work, immutable version, structure, and evidence from data/corpus/. Do not invent quotations, locations, or book facts, reveal excluded record content, or name internal routes.

[UNRESOLVED OUTPUT CONTRACT: schema, file layout, and serialization format]
[UNRESOLVED WORKFLOW INPUT: active and other-account record roles]
```

## Architecture and academic relevance

The architecture fit is:

- **Participating:** Muse, Librarian, Provenance, and the Memory & Policy Service.
- **Not participating:** Sculptor and Serendipity. Their absence proves that curation and connection discovery gain no accidental authority.
- **Current state:** Book retrieval, Provenance release review, deterministic citation checks, and account-scoped storage exist. Librarian cannot yet retrieve active memories.

This plan provides a concrete multi-agent demo with modular roles, traceable evidence, responsible isolation, and integration tests—the briefing's requested artifacts ([pp. 9–11](../../docs/submissions/aas-practice-module-briefing.pdf#page=9)).

## Risks and opportunity

- **Blocking gaps:** The unresolved output contract affects generated Sets, Props, Scenes, and Lines; the workflow must also supply active and other-account roles.
- **Downstream decision:** Assign Ground truth only after generation.
- **Non-blocking risk:** The selected longitudinal path cannot run until Librarian receives trusted, account-scoped memory retrieval.
- **Developer inspiration, not adopted scope:** Add a follow-up Line that combines an oblique memory cue with an exact-quotation request. The smallest build-out is an account-scoped Librarian memory adapter plus book-and-memory evidence fusion.

## Provenance

Snapshot: `2026-08-21T15:56:14+08:00`; branch `main`; HEAD `94d4011506231bc6d6f9e0adc9606d835b2bab34`; dirty. Relevant catalog and selector changes mean HEAD alone cannot reproduce this report. Inspected the catalog, specification, briefing, implementation, and focused tests. Composite SHA-256: `0dff0fe6cdc7308a716ae0fb0765ca2c89c363c2cb804f7b38cbb08dc6be70b4`.

> **Human decision required:** Adopt the minimal output contract and memory-state plan, revise the proposal, or abandon it.
