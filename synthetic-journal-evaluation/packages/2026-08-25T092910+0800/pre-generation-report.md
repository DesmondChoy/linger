# Pre-generation report: bounded memory curation

## Decision

The current implementation is **sufficient** for this plan. The package contract and validator encode all five accepted Sculptor behaviors, and the package replay adapter calls the production Sculptor boundary with immutable, same-account Props. The detached prompt is **runnable after human approval**.

This successor package must correct the ambiguity exposed by the 2026-08-24 replay. A summary Scene must contain notes that update or refine one evolving fact. A topic-group Scene must contain related notes that remain separate facts worth preserving individually. If both actions remain reasonably defensible for either Scene, the generator must rewrite that Scene.

| Required Scene | Expected response | Action-separability rule |
|---|---|---|
| Exact duplicate | `link_duplicates` | The two source texts are byte-identical |
| Paraphrased duplicate | `link_duplicates` | Both Props express the same durable memory, not only a shared topic |
| Evolving fact with noise | `update_derived_summary` | Later notes refine or resolve earlier notes into one supported current state |
| Related separate facts | `assign_topic_group` | No selected fact updates, corrects, or supersedes another |
| Superficial overlap | `no_curation_proposal` | Shared wording does not establish a durable relationship |

## Your selection

- **Bounded memory curation** (`bounded_memory_curation`): Sculptor reviews a bounded collection and proposes links, groups, or summaries using only supplied records, while preserving originals and leaving unrelated records alone.

The local selector confirmed this single Objective at 2026-08-25 09:26:41 +0800 against catalog SHA-256 `be6b55ae6eec0c62b658454ea7d944bac1f3f1feb83a3ccf302c7ed1b4723742`.

## Target evaluation design

The design uses the six terms in [specification Section 7.2.1](../../../docs/specification.md#721-canonical-vocabulary).

| Canonical noun | Use in this package |
|---|---|
| **Objective** | Only `bounded_memory_curation`; no run configuration |
| **Backstory** | One coherent history for one person and one evaluation account; generation context only |
| **Prop** | Natural, separate memory records active only for their designated Scene |
| **Scene** | Five ordered, isolated, Props-only offline tests |
| **Line** | None; curation is not conversational replay |
| **Ground truth** | One proposed typed curation expectation per Scene, with source IDs, exact spans, complete Prop evidence, outcomes, and semantic criteria |

The package uses the current strict `SyntheticBackstory` and `ProposedGroundTruth` models unchanged. The generator writes no replay output.

## Current implementation and required work

**Observed.** `models.py` reuses the shared typed `CurationExpectation`. `validate_package.py` requires exactly one Scene for each accepted behavior, 2–12 active Props per Scene, Props-only evidence, exact spans, and expected sources contained in the bounded input. `curation_replay.py` resolves ordered same-account Props, calls production `propose_curation`, compares the response with proposed Ground truth, records separate deployment and objective identities, and proves source immutability. Sculptor has no tools or write surface.

**Verified.** The full repository suite passed with 374 tests and 270 subtests. The focused curation replay suite passed 10 tests. The existing five-Scene package still passes deterministic validation.

**Required before generation.** Human approval of this report and prompt only. No implementation change is required. If a clearly evolving-fact successor Scene still produces `assign_topic_group`, treat that as evidence for a separate Sculptor prompt change rather than weakening the Scene label.

Repository snapshot: dirty `main` at `97bb2fbb58ed8bffa4b7b5c4bb7c7bf1e8255a52`, inspected 2026-08-25 09:27 +0800. Relevant fingerprints: catalog `be6b55ae`, models `2d36effd`, validator `ff022175`, curation replay `8fae59b9`, Sculptor harness `6caef8b9`, and focused tests `5aaf45e9`. The existing working-tree changes are part of the reviewed implementation and remain uncommitted.

## Expected behavior and evaluation

| Input shape | Proposed label | Success check |
|---|---|---|
| Identical Props | Duplicate link | Cite only both supplied IDs; preserve originals |
| Natural paraphrases | Duplicate link | Link shared meaning, not wording alone |
| Earlier plan, later decision, and topical noise | Derived summary | Express the supported latest state; exclude noise and unsupported completion claims |
| Several related, independently valuable facts and a distractor | Topic group | Group the related subset without collapsing the facts into a progression |
| Unrelated facts sharing a phrase | No change | Decline the superficial relationship |

Replay reports `matches_proposal` or `differs_from_proposal`. These are comparisons with proposed labels, not benchmark grades. Summary text and topic labels still require semantic review.

## Proposed generator prompt

```text
STATUS: Runnable after human approval

PRECONDITIONS
- A human has approved this report and detached prompt.
- PACKAGE_DIRECTORY is synthetic-journal-evaluation/packages/2026-08-25T092910+0800 and contains only pre-generation-report.md.
- Use the current package models and validator unchanged. If either precondition is false, stop without writing.

You have read-only access to the current Linger checkout. Inspect only these repository paths at invocation time:
- evals/synthetic_journals/models.py
- evals/synthetic_journals/validate_package.py
- evals/synthetic_journals/README.md
- evals/sculptor/harness.py
- src/linger/agents/sculptor/models.py
- src/linger/agents/sculptor/prompt.py
- src/linger/orchestration/curation.py
- docs/specification.md

Create exactly one memory-only package for the bounded_memory_curation Objective. Write only PACKAGE_DIRECTORY/backstory.json and PACKAGE_DIRECTORY/ground-truth.json. Do not invoke Linger, run an evaluation, adopt labels, grade output, or write any other file.

For backstory.json:
- Use one Backstory, person, and evaluation account. Select only bounded_memory_curation and no run configuration.
- Create no Lines or offline inputs. Create five ordered, isolated, fresh-session Scenes. Assign each Scene 2–12 separate, active, same-account Props.
- Create one exact-duplicate Scene with two byte-identical texts from distinct moments.
- Create one paraphrased-duplicate Scene whose two naturally different texts express the same durable memory.
- Create one summary Scene in which several notes update or refine one evolving fact. Include a meaningful later refinement that resolves or sharpens the earlier state, plus topical noise that must not support the summary.
- Create one topic Scene with related notes that remain separate facts worth preserving individually. No selected note may update, correct, refine, or supersede another. Include one plausible distractor.
- Create one no-change Scene whose Props share superficial wording but have unrelated meanings.
- Before writing, compare the summary and topic Scenes with their nearest alternative action. If a reasonable reviewer could choose either update_derived_summary or assign_topic_group for the same Scene, rewrite the Props until only the intended action is well supported.
- Keep every Prop independently useful. Do not put action names, evaluator labels, grading instructions, permission to change originals, diagnoses, or unsupported personal claims in Prop text.

For the proposed Ground truth file, PACKAGE_DIRECTORY/ground-truth.json:
- Hash the exact backstory.json bytes as backstory_sha256 and set ground_truth_status to proposed.
- Create one GroundTruthProposal for every Scene. Use the typed curation expectation to propose duplicate links for both duplicate Scenes, update_derived_summary for the evolving-fact Scene, assign_topic_group for the separate-facts Scene, and no_curation_proposal for superficial overlap.
- Record exact expected source IDs separately from every permitted Scene Prop ID. Cite every Scene Prop once through Prop evidence and add exact Prop spans, including noise and distractors.
- Write concrete expected and prohibited outcomes. Require supplied IDs only, immutable originals, no storage claim, and no unsupported summary fact. Keep generated summary and topic-label criteria separate from deterministic expectations.
- Use ScenePairing only when every declared match and difference is literally true. Do not expose Ground truth to Sculptor.

Serialize strict JSON and run:
.venv/bin/python -m evals.synthetic_journals.validate_package PACKAGE_DIRECTORY/backstory.json PACKAGE_DIRECTORY/ground-truth.json
If validation fails, revise only those two files and rerun until it passes. Report both paths and the validator result. Do not approve, adopt, or grade the proposed Ground truth.
```

## Ground truth lifecycle

The generator proposes labels and supporting evidence. Code validates schema, hash, topology, scope, lifecycle, references, spans, and behavior coverage. An independent reviewer must then adopt, revise, or reject each proposal; `linger-a4u.1` owns that later authority. Neither proposed nor adopted Ground truth reaches Sculptor.

## Architecture and academic relevance

Sculptor is the only reasoning agent in this offline slice. Application code owns account scoping, validation, replay, hard comparisons, telemetry, and immutability evidence. Muse, Librarian, Serendipity, and Provenance do not participate.

The [practice-module briefing](../../../docs/submissions/aas-practice-module-briefing.pdf) asks teams to demonstrate agent benefits and explainable, traceable decisions (page 9), and to provide unit and end-to-end testing artifacts (page 11). This package supports those claims through isolated provider-backed proposals, source provenance, immutable-input checks, durable transcripts, and explicit evaluation identities.

> [!IMPORTANT]
> **Human decision required:** Approve the report and generator prompt, request revision, or abandon. Approval authorizes generation of only the two JSON files described above; replay remains a later, separately recorded step.
