# Pre-generation report: bounded memory curation

## Decision

The current implementation is **insufficient** for the complete selected plan. Sculptor can produce validated proposals for the five accepted behaviors, but no package adapter can replay Props through that production boundary, and the package Ground truth cannot yet express typed curation expectations. Do not run the detached prompt until the approved gaps below are implemented and tested.

| Required Scene | Target behavior | Status | Evidence or gap |
|---|---|---|---|
| Exact duplicate | Link two identical Props without changing either | partially runnable | `propose_curation` and `sculptor-exact-duplicate-v1` cover the behavior; package-to-Sculptor adapter and typed Ground truth are missing |
| Paraphrased duplicate | Link differently worded Props that express the same durable memory | partially runnable | `sculptor-paraphrased-duplicate-v1` and the hard grader exist; replay and package mapping are missing |
| Meaningful update and noise | Propose a supported derived summary from fragments and a later refinement while excluding noise | partially runnable | `sculptor-noisy-memory-summary-v1` covers summary constraints; generated-package semantic criteria and replay are missing |
| Related records | Propose a topic group for related, distinct Props and leave a distractor outside it | partially runnable | `sculptor-related-topic-group-v1` covers the action; generated-package source mapping and replay are missing |
| Unrelated comparison | Return no change for superficial overlap | partially runnable | `sculptor-superficial-similarity-no-change-v1` covers abstention; generated-package comparison and replay are missing |

## Your selection

- **Bounded memory curation** (`bounded_memory_curation`): Sculptor reviews a bounded collection and proposes links, groups, or summaries using only supplied records, while preserving originals and leaving unrelated records alone.

## Target evaluation design

The design uses the six canonical nouns in [specification Section 7.2.1](../../../docs/specification.md#721-canonical-vocabulary). It is memory-only; book material would add no useful evidence.

| Noun | How it applies |
|---|---|
| **Objective** | Only `bounded_memory_curation`; no run configuration applies. The source-record plan uses the five accepted behavior shapes. |
| **Backstory** | One coherent history for one person and one evaluation account. It guides authoring and never enters Sculptor. |
| **Prop** | Separate, natural memory records assigned to one Scene and active before it runs. They cover exact and paraphrased duplicates, later refinement, related themes, noise, and unrelated overlap. |
| **Scene** | Five isolated offline Scenes. Each supplies 2–12 active, same-account Props and invokes Sculptor once. |
| **Line** | No Lines. Curation is separate from conversational replay, and no workflow control is disguised as user input. |
| **Ground truth** | `ground-truth.json` must propose a typed action or no-change expectation, expected source IDs, exact supporting spans, Prop evidence, outcomes, and semantic criteria. The current generic proposal cannot encode that typed expectation; an independent reviewer must later adopt, revise, or reject it. |

`evals/synthetic_journals/models.py` defines one `SyntheticBackstory` containing the Backstory, Props, Scenes, and no Lines or offline inputs. `ProposedGroundTruth` binds one proposal per Scene to the exact `backstory.json` hash. `evals/synthetic_journals/validate_package.py` checks strict schema, graph, scope, lifecycle references, hashes, spans, evidence, and pairings. It does not currently validate curation action labels or adoption.

## Current implementation and required work

**Observed.** `src/linger/orchestration/curation.py` sends only memory IDs and text to tool-free Sculptor and rejects unknown sources. `evals/sculptor/harness.py` owns five fixed behaviors, deterministic hard gates, and separate semantic criteria. Focused current-HEAD validation passed: 37 tests and 15 subtests across Sculptor, package, capture replay, and synthetic telemetry.

**Observed.** `evals/synthetic_journals/replay.py` supports capture only, rejects Props, and hashes every agent prompt into one `system_variant`; inactive prompts therefore affect identity. `evals/synthetic_journals/transcript.py` and `apps/backend/telemetry.py` already provide reusable exchanges and the synthetic-only `linger-evals` boundary. Bead `linger-a4u.2` defines this slice; `linger-a4u.1` separately owns later Ground truth adoption and calibration. Capture hardening under `linger-a4u.4` does not block generated Props.

**Proposed.** Close four minimal gaps: extend the active Ground truth contract and validator with typed curation expectations; add one package adapter that resolves active same-account Props into `AccountScopedMemories`; replay through production `propose_curation` with source hashes before and after, existing hard gates, separate semantic reporting, transcripts, Pydantic Evals, and synthetic Logfire; record a full-deployment identity for lineage and an objective-execution identity that excludes inactive prompts. Tests must cover topology, scope, no writes, immutability, proposal and no-change outcomes, identity stability, telemetry classification, and failures.

**Assumed.** The first slice uses generated Props only and records comparisons to proposed Ground truth, not benchmark grades. It creates no store, derived record, scheduler, or product workflow.

Repository snapshot: clean `main` at `97bb2fbb58ed8bffa4b7b5c4bb7c7bf1e8255a52`, inspected 2026-08-24 20:16 +0800. Fingerprints: catalog `c978d817`, models `6fc6fd5b`, validator `367663e4`, curation boundary `c632273c`, hard grader `bcbf1621`, capture runner `0ce41759`.

## Expected behavior and evaluation

The plan contains no Lines or offline inputs; each Scene supplies Props directly.

| Representative input | Likely behavior | Plain-language success check |
|---|---|---|
| Two identical records | Duplicate link | Only both supplied IDs are cited; originals remain unchanged |
| Two paraphrases of one durable memory | Duplicate link | Meaning, not wording alone, supports the link |
| Fragments, a later refinement, and noise | Derived summary | The summary uses supported sources, excludes noise, and adds no claim |
| Related but distinct records plus a distractor | Topic group | The related subset is grouped without collapsing distinct memories |
| Superficially similar but unrelated records | No change | Sculptor declines rather than grouping by shared words |

After adoption exists, curation precision, no-change accuracy, and provenance resolution can summarize results. Until then, report `matches_proposal` or `differs_from_proposal` and keep semantic criteria separate.

## Proposed generator prompt

```text
STATUS: Target state — do not run

PRECONDITIONS
- A human has approved this report's build target and detached prompt.
- The active contracts in evals/synthetic_journals/models.py represent a typed curation action or no-change expectation, expected source IDs, and separate semantic criteria without introducing a parallel schema.
- evals/synthetic_journals/validate_package.py deterministically validates those curation expectations, all permitted Scene Prop IDs, active lifecycle state, exact spans, and Prop evidence.
- The approved package-to-Sculptor replay adapter exists, calls production propose_curation, records full-deployment and objective-execution identities, proves source immutability, and has focused passing tests.
- PACKAGE_DIRECTORY is synthetic-journal-evaluation/packages/2026-08-24T202056+0800, contains only pre-generation-report.md, and has no backstory.json or ground-truth.json.
- If any precondition is unmet, stop without writing.

You have read-only access to the current Linger checkout. Inspect only these permitted repository paths at invocation time:
- evals/synthetic_journals/models.py
- evals/synthetic_journals/validate_package.py
- evals/synthetic_journals/README.md
- src/linger/agents/sculptor/models.py
- src/linger/agents/sculptor/prompt.py
- src/linger/orchestration/curation.py
- docs/specification.md

Create exactly one memory-only synthetic-journal package for the bounded_memory_curation Objective. Use the current package models and validator unchanged at invocation time. Write only PACKAGE_DIRECTORY/backstory.json and the separate proposed Ground truth file PACKAGE_DIRECTORY/ground-truth.json. Do not invoke Linger, run a model evaluation, adopt labels, grade output, create replay data, or write any other file.

For PACKAGE_DIRECTORY/backstory.json:
- Use exactly one Backstory, person, and evaluation account. Set objective_ids to only bounded_memory_curation and run_configuration_ids to empty.
- Create no Lines and no offline inputs. Create five ordered, isolated Scenes with fresh_session true.
- Assign each Scene 2–12 separate Props from the same Backstory, person, and account. Every assigned Prop must be active for that Scene and have no lifecycle entry for an unrelated Scene.
- Create one exact-duplicate Scene with two byte-identical source texts from distinct moments.
- Create one paraphrased-duplicate Scene whose two records express the same durable memory in natural, different wording.
- Create one summary Scene containing fragmented reflections, a meaningful later refinement, and noise that must not support the summary.
- Create one topic Scene containing related but distinct records and at least one plausible distractor.
- Create one no-change Scene whose records share superficial wording but have unrelated meanings.
- Keep every Prop independently useful. Do not include internal labels, expected actions, evaluator instructions, permission to alter originals, diagnoses, or unsupported personal claims in Prop text.

For PACKAGE_DIRECTORY/ground-truth.json:
- Hash the exact backstory.json bytes as backstory_sha256 and set ground_truth_status to proposed.
- Create one GroundTruthProposal for every Scene and the selected Objective. Do not claim that any proposal is adopted.
- Use the adopted typed curation expectation to propose duplicate links for the exact and paraphrased duplicate Scenes, a derived summary for the refinement Scene, a topic group for the related Scene, and no change for the unrelated Scene.
- Record the exact expected source IDs separately from every Prop ID permitted in the bounded Scene. Cite every Scene Prop through Prop evidence, including noise and distractors, and use exact Prop spans that support the proposed relationship or demonstrate the misleading overlap.
- Write concrete expected and prohibited outcomes. Require supplied IDs only, immutable originals, no storage claim, and no unsupported summary fact. Keep summary and topic-label semantic criteria separate from deterministic expectations.
- Use ScenePairing only when its declared fields are literally true. Do not expose this Ground truth to the system under evaluation.

Serialize strict JSON accepted by the current Pydantic models. Run:
.venv/bin/python -m evals.synthetic_journals.validate_package PACKAGE_DIRECTORY/backstory.json PACKAGE_DIRECTORY/ground-truth.json
If validation fails, revise only those two files and rerun until it passes. Report both paths and the validator result. Do not semantically approve, adopt, or grade the proposed Ground truth.
```

## Ground truth lifecycle

The generator proposes typed curation expectations, source IDs, spans, evidence, outcomes, and semantic criteria. Repository code validates objective facts and fails on schema, hash, scope, lifecycle, reference, span, or evidence errors. Semantic realism, relationship correctness, summary support, and label quality remain review judgments.

A reviewer independent of the generator must adopt, revise, or reject each proposal. `linger-a4u.1` still owns durable review authority and calibration, so this slice may compare provider output with proposals but cannot publish canonical accuracy. Neither proposed nor adopted Ground truth reaches Sculptor.

## Architecture and academic relevance

Sculptor is the only participating reasoning agent. Application-owned resolution, the package validator, hard grader, transcript recorder, Pydantic Evals, and Logfire are deterministic or evaluation services. Muse, Librarian, Serendipity, and Provenance do not participate. The tested boundary is narrow: Sculptor may propose against supplied IDs, but it cannot select account scope, use tools, write, or mutate originals.

The briefing asks how agent benefits can be demonstrated and how decisions remain explainable and traceable (PDF page 9); it also expects unit tests and end-to-end verification artifacts (page 11). This slice supplies that evidence through provider-backed proposals, durable exchanges, source provenance, and immutability checks without claiming a professor-mandated schema.

> [!IMPORTANT]
> **Human decision required:** Approve the build target and target-state prompt, request revision, or abandon. Approval does not authorize generation until every prompt precondition is implemented and verified.
