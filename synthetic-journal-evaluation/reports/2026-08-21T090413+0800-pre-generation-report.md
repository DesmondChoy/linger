# Pre-generation plan: memory lifecycle and bounded curation

> **Verdict: Not ready.** The selected objectives form a coherent plan, but
> Linger has not adopted an output format, file layout, or record schema. Adopt
> the smallest contract that represents a Backstory, its source reflections, ordered
> control intentions, and curation inputs. Then rerun this plan. Until then, a
> generator would have to invent project structure.

## Selected plan

This memory-only plan uses one **Backstory**—the fictional person's history that
keeps the generated material coherent. It combines:

- **User-controlled memory lifecycle** (`user_controlled_memory_lifecycle`):
  source text for an explicit save, a later correction, and a deletion intention.
- **Bounded memory curation** (`bounded_memory_curation`): three offline batches
  covering exact duplicates, related or refined reflections, and records that
  should remain unchanged.

The same history can produce both kinds of input. Neither objective needs book
evidence, so inspecting `data/corpus/` would add no value.

## Expected behavior and evaluation

Use these examples as hypotheses, not exact expected wording:

- **Lifecycle control:** “Writing this down so I stop losing it: …” is saved.
  “That is not quite what I meant—closer to …” creates a corrected immutable
  version. “Delete that memory” removes both versions. Success means one active
  version after correction and no remaining family after deletion.
- **Duplicate batch:** Two reflections express the same durable memory. Sculptor
  should propose a duplicate link that cites only those records and preserves
  both originals. Success means it catches the duplicate without rewriting it.
- **Related batch:** Several independently useful reflections support a topic
  group or summary. Success means every claim traces to the supplied records.
- **No-change batch:** Records share words but describe unrelated experiences.
  Success means Sculptor explicitly leaves them alone.

## Proposed generator prompt

```text
You have read-only access to the current Linger checkout. Inspect these paths
at invocation time:
  src/linger/services/memory.py
  apps/backend/main.py
  src/linger/agents/sculptor/models.py

Write natural first-person journal material for one fictional person.

A. Provide source text for one explicit save; later replacement text that
corrects its meaning; then an intention to delete that record and its earlier
versions. Express intent in the person's own words. Invent no account, event,
or memory identifiers.

B. Provide a bounded group of reflections accumulated over time: an exact
duplicate pair, related but distinct records, a later refinement, unrelated
noise, and one group that warrants no reorganization. Keep each reflection
useful on its own. Use natural repetition, never evaluator labels.

Do not use conversational phrases as substitutes for executed controls or tell
the curator how to organize the material.

<<UNRESOLVED: output format, file layout, and record schema. Do not invent them.>>
```

## Architecture and academic relevance

- The **Memory & Policy Service** alone saves, versions, and deletes memories.
  No agent participates in lifecycle controls.
- **Sculptor** receives 2–12 supplied records and returns one proposal or an
  explicit no-change result. It has no tools or write authority.
- **Muse, Librarian, Serendipity, and Provenance** do not participate. Their
  absence proves that deterministic controls and offline curation do not gain
  conversational or release authority.

These cases create testing evidence for traceable memory changes and bounded
agent authority, supporting the module's architecture and testing artifacts
(briefing pp. 9, 11, and 13).

## Risks and opportunity

- **Blocking:** No adopted generation output contract exists.
- **Non-blocking implementation gaps:** No backend caller schedules curation,
  and the service cannot yet apply Sculptor's derived proposals.
- **Developer inspiration, not adopted scope:** Correct and then delete a memory
  after curation groups it. The smallest build-out persists derived changes with
  source references and removes them when their source family is deleted.

## Provenance

- Generated 2026-08-21 at 09:04:13 +08:00 from `main` at `0385d89`.
- The tree was dirty only because `SKILL.md` contained the revised report
  contract. `HEAD` alone cannot reproduce this report.
- Inspected the catalog, skill, briefing, specification, memory and curation
  code, backend routes, and focused tests. Combined SHA-256: `572f69a…2c971`.

> **Human decision required:** adopt the minimal output contract (recommended),
> revise the selected plan, or abandon it. Do not approve it unchanged.
