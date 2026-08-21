# Pre-generation plan: memory lifecycle and bounded curation

> **Verdict: Not ready.** Linger has not adopted an output format, file layout,
> or record schema. Adopt the smallest contract that represents the fictional
> context, generated source records, and six tests with ordered controls. Then
> rerun; otherwise, the generator must invent project structure.

## Your selection

You selected two Objectives:

- **User-controlled memory lifecycle** (`user_controlled_memory_lifecycle`):
  Direct save, correction, and deletion without agent write authority.
- **Bounded memory curation** (`bounded_memory_curation`): Supported links,
  groups, or summaries that preserve every supplied memory.

## Selected plan

The [canonical vocabulary](../../docs/specification.md#721-canonical-vocabulary)
defines this plan:

| Noun | Role in this plan |
|---|---|
| **Objective** | **User-controlled memory lifecycle** (`user_controlled_memory_lifecycle`) and **Bounded memory curation** (`bounded_memory_curation`). One person's history supports both. |
| **Backstory** | One memory-only fictional person's history. Neither Objective needs book evidence. |
| **Prop** | Separately generated source memories supplied to curation Scenes. Memories created by lifecycle controls are outcomes, not Props. |
| **Scene** | Six minimum Scenes: save, correction, deletion, duplicate curation, related-memory curation, and no-change curation. |
| **Line** | None. Lifecycle intentions use deterministic controls; curation Props go to offline Sculptor, not Muse. |
| **Ground truth** | Assigned after generation and withheld from the generator. The success checks below are hypotheses only; assignment remains undefined. |

## Expected behavior and evaluation

There are no Lines. Inputs are deterministic control intentions or curation
Props:

- **Lifecycle Scenes:** “Writing this down so I stop losing it: …” is saved.
  “That is not quite what I meant—closer to …” creates a corrected immutable
  version. “Delete that memory” removes both versions. Success means one active
  version after correction and none after deletion.
- **Duplicate Scene:** Two Props express the same durable memory. Sculptor
  should cite only those records, link them, and preserve both originals.
- **Related-memory Scene:** Several useful Props support a topic group or
  summary. Every proposed claim should trace to supplied records.
- **No-change Scene:** Similar but unrelated Props should produce an explicit
  no-change result.

## Proposed generator prompt

```text
You have read-only access to the Linger checkout. Inspect:
  src/linger/services/memory.py
  apps/backend/main.py
  src/linger/agents/sculptor/models.py

Write natural first-person journal material for one fictional person.

A. Provide source text for an explicit save, later replacement text that
corrects its meaning, and then an intention to delete that record and its earlier
versions. Use the person's own words. Invent no account, event, or memory IDs.

B. Provide accumulated reflections containing an exact duplicate pair, related
but distinct records, a later refinement, unrelated noise, and one group that
warrants no reorganization. Keep each reflection useful on its own. Use natural
repetition, never evaluator labels.

Do not substitute conversational phrases for executed controls or tell the
curator how to organize the material.

<<UNRESOLVED: output format, file layout, and record schema. Do not invent them.>>
```

## Architecture and academic relevance

- The **Memory & Policy Service** alone saves, versions, and deletes memories.
- **Sculptor** receives 2–12 records and returns one proposal or no change. It
  has no tools or write authority.
- **Muse, Librarian, Serendipity, and Provenance** do not participate. Their
  absence tests that deterministic controls and offline curation gain no
  conversational or release authority.

These Scenes test traceable memory changes and bounded agent authority (briefing
pp. 9, 11, and 13).

## Risks and opportunity

- **Blocking:** No output contract represents the Backstory, curation Props, or six
  Scenes. This plan has no Lines.
- **Separate downstream decision:** Ground truth assignment remains undefined
  and must stay outside the generator prompt.
- **Non-blocking gaps:** No backend caller schedules curation, and the service
  cannot yet apply Sculptor's derived proposals.
- **Developer inspiration, not adopted scope:** Correct and delete a memory after
  curation groups it. Persist derived changes with source references, then remove
  them when their source family is deleted.

## Provenance

- Generated 2026-08-21 at 11:37:11 +08:00 from `main` at `0385d89`.
- The revised skill and two prior comparison reports are not in `HEAD`; `HEAD`
  alone cannot reproduce this report.
- Inspected the catalog, specification, briefing, relevant runtime code, and
  focused tests. Combined SHA-256: `6e97251…b3ea69`.

> **Human decision required:** adopt the minimal output contract (recommended),
> revise the selected plan, or abandon it. Do not approve it unchanged.
