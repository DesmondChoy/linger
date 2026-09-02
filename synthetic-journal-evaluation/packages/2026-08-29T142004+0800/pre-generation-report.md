# Pre-generation report: bounded memory curation

## Decision

The current implementation is **sufficient** for the selected plan. This evaluation measures Sculptor proposal quality and source preservation. After human approval, the detached prompt can generate the package with the existing schema, validator, and `propose_curation` runner.

| Required Scene | Evaluated behavior | Status | Evidence |
|---|---|---|---|
| Exact duplicate | Propose `link_duplicates` with only the two supplied duplicate Props | runnable | The package validator, hard grader, and runner support this behavior |
| Paraphrased duplicate | Recognize one durable memory expressed in different words | runnable | The current five-behavior contract distinguishes this semantic case from exact duplication |
| Evolving fact with noise | Propose `update_derived_summary` using only the records that update one fact | runnable | Prompt version 3 adds summary-over-topic precedence and excludes topical noise; the provider replay passed |
| Related records | Propose `assign_topic_group` for distinct, independently useful facts and omit the distractor | runnable | The current contract and prompt preserve the summary-versus-topic distinction; the provider replay passed |
| Unrelated comparison | Return `NoCurationProposal` for superficial wording overlap | runnable | The runner and hard grader support the no-change result |

## Your selection

- **Bounded memory curation** (`bounded_memory_curation`): Sculptor reviews a bounded collection, proposes links, groups, or summaries from supplied records, preserves every original, and leaves unrelated records alone.

## Target evaluation design

The design uses the [six canonical nouns](../../../docs/specification.md#721-canonical-vocabulary) and a memory-only Backstory. Book material does not help this Objective, so the generator must not inspect `data/corpus/`.

| Noun | Application |
|---|---|
| **Objective** | Only `bounded_memory_curation`. The package contains one Scene for each of the five Sculptor behaviors required by the current validator. No run configuration applies. |
| **Backstory** | One coherent history for one person and one evaluation account. It guides generation and never enters Sculptor. |
| **Prop** | Natural memory records positioned before their Scenes. They supply exact duplicates, paraphrases, evolving facts, related facts, noise, distractors, and superficial overlap. |
| **Scene** | Five isolated units. Each supplies 2–12 active, same-account Props to production `propose_curation`. |
| **Line** | None. Curation remains separate from conversational replay. |
| **Ground truth** | `ground-truth.json` proposes the expected Sculptor response kind, action, and source Prop identifiers, with supporting evidence and semantic criteria. Independent review adopts, revises, or rejects each proposal before adopted grading. |

`evals/synthetic_journals/models.py` defines one `SyntheticBackstory` containing the Backstory, Props, Scenes, and empty Line and offline-input collections. `ProposedGroundTruth` hashes the exact `backstory.json` bytes and anchors each proposed answer to a Scene and Objective. `evals/synthetic_journals/validate_package.py` validates the graph, lifecycle, evidence, exact spans, and five required Sculptor behaviors.

## Current implementation and required work

**Observed.** The catalog defines this Objective as Sculptor-only proposal quality. `evals/synthetic_journals/curation_replay.py` converts each Scene's active Props to `AccountScopedMemories`, calls production `propose_curation`, records the typed response, and verifies source hashes before and after the call. The package model, validator, grader, and runner cover the complete selected plan.

**Observed.** Commit `2916dba` established reviewed Ground truth and adopted replay. Commit `f4db8d0` added a separate product application path through Provenance, deterministic policy, `MemoryPolicyService`, audit verification, and curated retrieval. Closed Beads `linger-a4u.2` and `linger-a4u.5` preserve that separation. Those downstream stages exist in the product but are outside this Objective and its Ground truth.

**Observed.** Bead `linger-a4u.1.2` tracks a demonstrated summary-versus-topic provider error. The current working-tree prompt version 3 adds an explicit precedence rule and excludes topical noise. A fresh five-Scene provider replay passed all hard comparisons and preserved every source hash. This quality correction does not change the package schema or runner.

**Proposed.** No contract, adapter, grading, or source build-out is required before package generation. Keep `backstory.json` as synthetic Props and Scenes, keep `ground-truth.json` limited to the expected Sculptor action and source identifiers, and keep replay at `propose_curation`.

**Assumed.** A human still reviews the generated package for realism and semantic label quality before adopting Ground truth.

Repository snapshot: dirty `main` at `57c81348dd357bf6bd447e3e521cbc83564aa819`, inspected 2026-08-29 15:28 +0800. Material changes are the Sculptor prompt version 3 and report-scope skill clarification; `HEAD` alone does not reproduce them. Fingerprints: catalog `1b18bef9`, models `400b7ca5`, validator `ff022175`, runner `3780f428`, grader `6caef8b9`, Sculptor prompt `5c1acfb1`.

## Expected behavior and evaluation

The plan contains no Lines or offline inputs. Each Scene sends Props directly to Sculptor.

| Representative input | Likely Sculptor response | Success check |
|---|---|---|
| Identical records | `link_duplicates` | The proposal cites exactly the supplied duplicate IDs and leaves source hashes unchanged |
| Natural paraphrases | `link_duplicates` | The proposal identifies the same durable memory without inventing a source |
| One evolving fact plus topical noise | `update_derived_summary` | The proposal cites only the updating records, and the summary reflects the current fact without unsupported claims |
| Related, distinct records plus a distractor | `assign_topic_group` | The proposal cites only the related records and keeps them conceptually distinct |
| Superficially similar, unrelated records | `NoCurationProposal` | Sculptor declines instead of grouping records by shared wording |

Hard gates compare response kind, action, source identifiers, schema, and source preservation. Summary text and topic labels remain separate semantic review judgments.

## Proposed generator prompt

```text
STATUS: Runnable after human approval

PRECONDITIONS
- A human has approved this target design and detached prompt.
- PACKAGE_DIRECTORY is synthetic-journal-evaluation/packages/2026-08-29T142004+0800, contains pre-generation-report.md, and contains neither output file.
- If either precondition is false, stop without writing.

You have read-only access to the current Linger checkout. Inspect only these permitted paths at invocation time:
- evals/synthetic_journals/models.py
- evals/synthetic_journals/validate_package.py
- evals/sculptor/harness.py
- src/linger/agents/sculptor/models.py
- src/linger/agents/sculptor/prompt.py

Create one memory-only synthetic-journal package for only the bounded_memory_curation Objective. Use the current contracts unchanged. Write exactly two sibling outputs: PACKAGE_DIRECTORY/backstory.json and the separate proposed Ground truth file PACKAGE_DIRECTORY/ground-truth.json. Do not read this report as generator input, inspect the corpus, invoke Linger, run an evaluation, create replay data, grade recorded behavior, adopt labels, or write another file.

For PACKAGE_DIRECTORY/backstory.json:
- Create exactly one Backstory for one person and one evaluation account. Use only bounded_memory_curation in objective_ids and leave run_configuration_ids empty.
- Create exactly five ordered, isolated Scenes: exact duplicate, paraphrased duplicate, evolving fact with noise, related distinct facts with a distractor, and superficial similarity with no useful curation.
- Create no Lines and no offline inputs. Each Scene must contain 2–12 active, same-account Props.
- Position every Prop before its Scene and give it a clear lifecycle role. Keep each Prop understandable on its own.
- Use natural text. Do not place expected actions, labels, grading instructions, unsupported claims, or permission to alter originals in Prop text.

For PACKAGE_DIRECTORY/ground-truth.json:
- Hash the exact backstory.json bytes as backstory_sha256, set ground_truth_status to proposed, and create one GroundTruthProposal per Scene. Do not claim adoption.
- Propose only the expected Sculptor response kind, action, and exact source Prop identifiers using the current typed curation expectation.
- Cite every Scene Prop exactly once as Prop evidence. Add exact Prop spans that support the expected relationship and expose noise, distractors, or misleading overlap.
- Require link_duplicates for exact and paraphrased duplicates, update_derived_summary for the evolving fact using only its updating Props, assign_topic_group for related distinct facts using only that subset, and NoCurationProposal for superficial overlap.
- Include semantic criteria for summary support and topic-label quality. Treat these as later review judgments, not deterministic facts.
- Require supplied identifiers only, immutable originals, preserved provenance, no storage authority, and no unsupported derived claim.
- Do not add Provenance review, policy application, audit, tombstone or restoration, or curated retrieval expectations. Never expose proposed Ground truth to Sculptor.

Serialize strict JSON accepted by evals/synthetic_journals/models.py. Run:
.venv/bin/python -m evals.synthetic_journals.validate_package PACKAGE_DIRECTORY/backstory.json PACKAGE_DIRECTORY/ground-truth.json
If validation fails, revise only the two output files and rerun until it passes. Report both paths and the validator result. The validator checks package facts; it does not approve semantic quality, adopt Ground truth, or grade recorded Sculptor behavior.
```

## Ground truth lifecycle

The generator proposes the Sculptor response kind, action, source identifiers, evidence, exact spans, and semantic criteria. Repository code rejects invalid schema or hashes, unresolved references, incorrect lifecycle state, incomplete evidence, and missing behavior coverage. It does not assess recorded behavior or semantic quality.

An independent human reviewer adopts, revises, or rejects every proposed label. Only adopted Ground truth may grade a run. Semantic realism, relationship correctness, summary support, and topic-label quality remain review judgments. Neither proposed nor adopted Ground truth reaches Sculptor.

## Architecture and academic relevance

Sculptor is the only participating reasoning agent. The runner and deterministic grader enforce bounded input, allowed source identifiers, proposal shape, and source preservation. Muse, Provenance, Librarian, Serendipity, policy application, audit, and curated retrieval do not participate in this evaluation.

This plan tests whether a specialized agent can improve bounded memory organization while preserving source authority. It supports the briefing's questions about modular-agent benefits and its expected agent-design and evaluation artifacts (PDF pages 9 and 11).

> [!IMPORTANT]
> **Human decision required:** Approve the target design and generator prompt, request a revision, or abandon the package.
