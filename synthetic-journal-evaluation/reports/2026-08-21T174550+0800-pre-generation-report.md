# Pre-generation decision: account-bound grounded reflection

> **Not ready.** The generator lacks an output contract and concrete account-role binding. Adopt both before generation.

## Your selection

You selected these Objectives:

- **Grounded book reflection** (`grounded_book_reflection`) — Verifies book evidence while avoiding retrieval for personal reflection.
- **Longitudinal memory retrieval with isolation** (`longitudinal_memory_retrieval_with_isolation`) — Uses authorized memories across sessions without exposing another account.

## Selected plan

The plan uses the six terms in [Section 7.2.1, “Canonical vocabulary”](../../docs/specification.md#721-canonical-vocabulary).

| Term | Use in this plan |
|---|---|
| Objective | Combine both Objectives in a later book reflection needing personal history and corpus evidence. |
| Set | Use a corpus-backed Set for Account A and a memory-only Set for Account B. |
| Prop | Insert active-lifecycle memories owned by Accounts A and B. Account B's topical Prop is excluded from Account A's Scenes. Runtime-created records are outcomes, not Props. |
| Scene | Run three Scenes as authenticated Account A: grounded, non-factual, and fresh-session isolation. Their overlap covers both two-Scene minima. |
| Line | Each Scene sends a natural Line to Muse; retrieval starts with fresh conversation state. |
| Ground truth | After generation, assign evidence, relevance, ownership, lifecycle, and retrieval labels; withhold them from the generator. |

## Expected behavior and evaluation

This plan contains conversational Lines:

- **Line 1, Account A:** Cue an earlier memory while asking about a passage and naturally express or omit reading position. Likely behavior: use Account A's memory and book evidence. Success: authorized, resolvable evidence supports the reply.
- **Line 2, Account A:** Reflect without a factual book claim. Likely behavior: skip book retrieval. Success: the reply remains useful.
- **Line 3, Account A:** Use a fresh-session cue matching Account B's Prop. Likely behavior: exclude it. Success: Account B's content reaches neither results nor reply.

## Proposed generator prompt

```text
You have read-only access to the current checkout. At invocation time, inspect data/corpus/ and src/linger/services/memory.py.

Create a paired-account reading history. For the primary account, include an earlier memory-producing event and a later fresh-session book reflection that cues it without repetition. Require repository-backed passage evidence and express reading position naturally or leave ambiguity for clarification. Add a nearby non-factual reflection needing no book evidence. Add a fresh-session isolation interaction authenticated as the primary account; a topical comparison-account memory remains unavailable. Keep memory source text separate from raw journal text. Discover the current work, immutable version, structure, and evidence under data/corpus/. Do not invent book material, reveal excluded content, or name internal routes.

[UNRESOLVED OUTPUT CONTRACT: schema, file layout, and serialization format]
[UNRESOLVED WORKFLOW INPUT: bind the primary and comparison accounts to memory ownership and planned active-lifecycle roles]
```

## Architecture and academic relevance

The architecture fit is:

- **Participating agents:** Muse, Librarian, and Provenance.
- **Non-participating agents:** Sculptor and Serendipity; neither gains curation or connection authority.
- **Deterministic service:** The Memory & Policy Service owns account scope, access, and storage.

The isolation Scene demonstrates account protection, while Line 1 exercises coordinated memory and book evidence with a traceable release decision. Together they provide the integration and security testing requested in the briefing ([pp. 9–11](../../docs/submissions/aas-practice-module-briefing.pdf#page=9)).

## Risks and opportunity

The remaining decisions and risks are:

- **Blocking gaps:** Sets, Props, Scenes, and Lines lack an output contract; the workflow must bind both accounts.
- **Downstream decision:** Assign Ground truth only after generation.
- **Non-blocking risk:** Account-scoped storage exists, but Librarian cannot yet retrieve active memories.
- **Developer inspiration, not adopted scope:** Combine an oblique memory cue with an exact quotation. Add an account-scoped Librarian memory adapter and evidence fusion.

## Provenance

Snapshot: `2026-08-21T17:45:50+08:00`; `main`; HEAD `94d4011506231bc6d6f9e0adc9606d835b2bab34`; dirty. Catalog/selector changes, the account rule, and an earlier report mean HEAD cannot reproduce this memo. Inspected, in fingerprint order: `.agents/skills/generate-synthetic-journals/SKILL.md`; `synthetic-journal-evaluation/evaluation-objectives.yaml`; `docs/specification.md`; `docs/submissions/aas-practice-module-briefing.pdf`; `data/corpus/alice-in-wonderland/pg11-v01b38ea4/catalog.json`; `src/linger/services/memory.py`; `src/linger/orchestration/grounding.py`; `src/linger/agents/muse/tools.py`; `src/linger/agents/librarian/agent.py`; `src/linger/agents/provenance/agent.py`; `tests/test_memory_service.py`; `tests/test_grounding.py`; `tests/test_librarian_end_to_end.py`. Fingerprint: `a97c1302f2c049d5c9fe6e488cb2dc1d46d4af8c39d70be5faba1a3ffcaeed35` (`SHA-256(path + NUL + bytes + NUL)`).

> **Human decision required:** Adopt the minimal output contract and bind the account roles, revise the proposal, or abandon it.
