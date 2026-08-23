# Pre-generation report: longitudinal memory retrieval

## Decision

The current implementation is **insufficient** for the confirmed plan. Both required Scenes are blocked: you can approve the target design and the target-state prompt, but you cannot run generation or the evaluation yet. Linger stores account-scoped memories and isolates sessions, yet nothing retrieves a stored memory into a reflection turn.

| Required Scene | Target behavior | Status | Evidence or gap |
|---|---|---|---|
| `scene-target` | In a fresh session, one relevant Prop among 11 active Props reaches Muse and shapes the reply. | blocked | Capability gap. Muse is built with `librarian_search` and `serendipity_explore` only (`src/linger/agents/muse/agent.py:124`), and `Librarian.retrieve` scores book paragraphs under a `BookScope` (`apps/backend/librarian.py:120`). No component reads memories for a turn. |
| `scene-comparison` | The same 11 active Props are available, none is relevant, and the reply presents no stored record as support. | blocked | Same capability gap, plus an adapter gap: the only write path is `MemoryPolicyService.save_automatic`, which requires a reviewed capture candidate (`src/linger/services/memory.py:124`). Nothing pre-positions Props for a Scene. |

## Your selection

- **Longitudinal memory retrieval** (`longitudinal_memory_retrieval`) — Across sessions, Librarian retrieves active memories authorized by the Memory & Policy Service, testing whether Muse benefits from one person's relevant history without relying on prior chat context or forcing unrelated memories into the response.

## Target evaluation design

The design uses the six canonical nouns in [`docs/specification.md` Section 7.2.1](../../docs/specification.md#721-canonical-vocabulary).

| Noun | How it applies |
|---|---|
| **Objective** | One Objective: `longitudinal_memory_retrieval`. Its catalog minimum is two Scenes: a later-session query with one relevant active memory, and a nearby later-session comparison for which the available memories are not relevant. |
| **Backstory** | Exactly one Backstory, one person, one evaluation account, memory-only. It carries a multi-session history with an earlier memory-producing event and later revisits of the same theme. No corpus inspection is required, so the generator does not read `data/corpus/`. |
| **Prop** | 11 Props, all separate source records written in the person's own words and positioned before both Scenes. Both Scenes share the same bank, and every Prop is `active` in both. The mix comes from `synthetic-journal-evaluation/run-configurations/longitudinal-memory-retrieval-10-to-1.json`: 1 relevant and 10 distractors. That 1:10 ratio is a Prop constraint for this run, not a Scene ratio or a catalog-wide rule. |
| **Scene** | Two Scenes, both `fresh_session: true`, ordered 1 and 2, each holding all 11 `prop_ids` and one Line. `scene-target` is the relevant-memory Scene; `scene-comparison` is its pair. |
| **Line** | Two Lines, one per Scene. Lines are conversational input only. Session reset and memory state are workflow setup, not Lines. The plan uses no offline inputs. |
| **Ground truth** | The generator writes **proposed** Ground truth in a separate authoring manifest: one `GroundTruthProposal` per Scene, each with a `prop_relevance` judgment for all 11 Props, `PropEvidence` matching exactly its relevant Props, expected and prohibited outcomes, and a `ScenePairing`. A reviewer independent of the generator turns proposals into **adopted** Ground truth. |

Both contracts are **Adopted v1**, modeled in `evals/synthetic_journals/models.py` and checked by `evals/synthetic_journals/validate_package.py`. Content is one JSON document holding `schema_version`, `objective_ids`, `run_configuration_ids`, one `backstory`, `props` with per-Scene `lifecycle`, `scenes`, and `lines`. The manifest is a second JSON document holding `schema_version`, `content_sha256`, `ground_truth_status: "proposed"`, and `proposals`. They represent this Objective unchanged, so no contract gap blocks it.

## Current implementation and required work

**Observed.** `MemoryPolicyService` owns account-scoped policy, writes, and reads, including `list_active` (`src/linger/services/memory.py:144`), covered by `tests/test_memory_service.py`. Session isolation exists through `history` and `clear` in `apps/backend/sessions.py`. The sole caller of `list_active`, `src/linger/orchestration/connection.py:65`, blocks cues repeating private memory wording — a leak check, not retrieval. `tests/test_synthetic_journal_retrieval_package.py` proves the validator enforces the shared 11-Prop bank, relevance mix, active lifecycle, and Prop-evidence agreement.

**Proposed.** Close three gaps before any Scene runs.

- **Capability gap: memory retrieval.** Add an account-scoped memory retrieval path that Librarian serves and Muse can call in a fresh session. Acceptance: a focused test shows a fresh-session turn with 11 active Props surfaces the relevant record, passes the Provenance gate, and reads lifecycle eligibility from stored state, not model output.
- **Adapter gap: Prop seeding.** Add a deterministic evaluation-only seeder that writes Props for one account and asserts their lifecycle state before a Scene. Acceptance: seeding 11 Props makes `list_active` return exactly those 11 records, and the seeder refuses a non-evaluation account.
- **Grading gap: retrieval measurement.** Extend the harness pattern in `evals/librarian/benchmark.py` to grade memory retrieval against adopted Prop relevance. Acceptance: the harness reports per-Scene retrieved Prop identifiers, so recall and precision follow from adopted labels.

Relevant Beads: `linger-4sp` (migrate to the adopted memory schema), because `MemoryRecord` has no lifecycle field today; `linger-0yd` touches the same store.

**Assumed.** The evaluation account is the configured `linger_account_id` and needs no new isolation model.

Repository snapshot: branch `main`, `HEAD` `df5a359`, dirty, inspected 2026-08-23 08:38 +0800; uncommitted edits to `evals/synthetic_journals/models.py`, `evals/synthetic_journals/validate_package.py`, `docs/specification.md`, and the catalog, plus the untracked run configuration and retrieval test, mean `HEAD` alone does not reproduce this implementation.

## Expected behavior and evaluation

The plan contains Lines only, no offline inputs.

| Representative input | Likely behavior | Success check |
|---|---|---|
| `scene-target` Line: the person revisits a theme they reflected on months ago, without repeating the earlier wording. | Muse retrieves the one relevant active memory and answers more usefully than it could without history, marking recalled words as the person's own. | The reply draws on the relevant record only, and its support resolves to that Prop. Later: `recall_at_5`, `precision_at_5`. |
| `scene-comparison` Line: a topically adjacent reflection that stored history does not help. | Muse answers on its own terms and cites no stored record as support. | No Prop is presented as evidence, and the reply is still useful. Later: `precision_at_5`. |

Treat both response descriptions as hypotheses, not oracles.

## Proposed generator prompt

```text
STATUS: Target state — do not run.

PRECONDITIONS. Do not run this prompt until all three exist in the checkout:
1. An account-scoped memory retrieval path that Librarian serves and Muse can
   call in a fresh session.
2. A deterministic evaluation-only Prop seeder that pre-positions memory records
   for one evaluation account and asserts their lifecycle state before a Scene.
3. A retrieval grading harness that records which Props were retrieved per Scene.
If any precondition is unmet, stop and report it. Produce nothing.

You have read-only access to the current checkout. Inspect these paths at
invocation time; do not rely on any summary of them:
- evals/synthetic_journals/models.py
- evals/synthetic_journals/validate_package.py
- synthetic-journal-evaluation/run-configurations/longitudinal-memory-retrieval-10-to-1.json

TASK. Write two JSON files for the Objective longitudinal_memory_retrieval:
a content file and a separate authoring manifest. Use the v1 models in
evals/synthetic_journals/models.py exactly as written. Do not invent another
schema, and do not add fields.

CONTENT FILE.
- Set schema_version to 1, objective_ids to ["longitudinal_memory_retrieval"],
  and run_configuration_ids to ["longitudinal-memory-retrieval-10-to-1"].
- Write exactly one Backstory for one person and one evaluation account. Give it
  a multi-session history containing an earlier memory-producing event and later
  returns to the same theme. This Backstory is memory-only: do not read or cite
  the book corpus. The Backstory never enters the running system.
- Write exactly 11 Props. Every Prop belongs to that Backstory, person, and
  evaluation account. Write each Prop as separate source text in the person's own
  words; never copy a Line into a Prop or a Prop into a Line. Give every Prop a
  lifecycle entry of "active" for both Scenes.
- Write exactly 2 Scenes, both with fresh_session true, ordered 1 then 2. Give
  each Scene all 11 prop_ids, so the two Scenes share the same 11 active Props.
  Name the first Scene the target Scene and the second the comparison Scene.
- Write exactly 2 Lines, one per Scene, as natural first-person input to Muse.
  The target Line revisits the earlier theme without repeating the relevant Prop
  verbatim, and reads as a better question when prior context is available. The
  comparison Line stays close in topic yet gains nothing from stored history.
  Lines are conversation only: never write a save, delete, reset, or memory
  control request, and never name an internal component or an expected route.
  Write no offline inputs.
- In the target Scene, exactly one Prop is relevant; the remaining ten Props are
  plausible but unhelpful distractors. Keep the distractors close in topic and
  wording so selective retrieval is not trivial. In the comparison Scene, none of
  the 11 Props is relevant.

AUTHORING MANIFEST. Write it as a second file that records proposed Ground truth
only. Never place manifest content in the content file.
- Set schema_version to 1, ground_truth_status to "proposed", and content_sha256
  to the SHA-256 of the exact content file bytes you wrote.
- Write one GroundTruthProposal per Scene, both with objective_id
  longitudinal_memory_retrieval.
- In each proposal, record one prop_relevance judgment for every one of the 11
  available Props in that Scene. In the target Scene mark exactly one "relevant"
  and ten "distractor". In the comparison Scene mark all 11 "distractor".
- Make each proposal's PropEvidence list match its relevant Prop judgments
  exactly. The comparison proposal therefore carries no Prop evidence.
- Give each proposal at least one expected outcome and one prohibited outcome in
  plain language, describing what a correct reply does and must not do.
- Pair the two Scenes with a ScenePairing that declares which fields match and
  which differ, and keep the declaration true of the content you wrote.

VALIDATE. Run evals/synthetic_journals/validate_package.py against your two
files. Fix every reported failure and rerun until it passes. Report both file
paths and the validator output.

BOUNDARIES. You are authoring, not grading. Do not run Linger, do not observe or
judge any recorded system behavior, and do not claim your labels are adopted:
they are proposed Ground truth until an independent reviewer accepts them. Do not
write thresholds, judge rubrics, metric names, or evaluation commentary into
either file, and never expose the manifest or its judgments to Linger.
```

## Ground truth lifecycle

The generator proposes. It writes the content file and the separate authoring manifest together, anchoring every judgment to generated identifiers. Required evidence is `PropEvidence` for each relevant Prop, plus a `prop_relevance` judgment covering all 11 Props in each Scene. Exact spans are optional, because relevance attaches to whole Props; any span written must slice its source exactly by code point.

Repository code validates. `evals/synthetic_journals/validate_package.py` checks the manifest hash against the exact content bytes, resolves every reference, enforces the shared 11-Prop bank, requires each Prop to be `active` in each Scene, requires one relevance judgment per available Prop, requires Prop evidence to match the relevant judgments, and requires observed mixes of 1 relevant and 10 distractors in one Scene and 0 and 11 in the other. It fails on a hash mismatch, an unknown identifier, a missing judgment, a wrong mix, an inactive Prop, or a false pairing claim. It adopts nothing.

A reviewer independent of the generator adopts, revises, or rejects each label. Only adopted Ground truth grades a run, and neither the manifest nor adopted Ground truth reaches Linger. Semantic realism, distractor quality, and whether the relevant Prop is genuinely the useful one are review judgments, not deterministic checks.

**Gap: review ownership and adoption tooling are not adopted.** The smallest decision needed: name who reviews these labels and where an adopted set is stored, apart from the manifest.

## Architecture and academic relevance

Participating: Muse, Librarian, Provenance as the mandatory release gate, and the Memory & Policy Service as the deterministic service owning record eligibility. Sculptor and Serendipity do not participate; this plan curates nothing and explores no cross-source connection.

The plan tests one authority boundary: record lifecycle eligibility must come from trusted application state, not model output. Muse may consume only what the Memory & Policy Service authorizes and Librarian returns; it can neither widen account scope nor promote a convenient record. The comparison Scene tests the same boundary from the other side, since no record is authorized as support.

Academic relevance: the briefing asks what common services, such as shared memory, support the agents (page 9) and expects testing artifacts including end-to-end flow verification (page 11). Paired retrieval Scenes over one shared memory store, graded against adopted labels, answer both.

> **Human decision required**
>
> Because the implementation is insufficient, choose one:
>
> - **Approve the build target and the target-state prompt** as written, held closed by its preconditions.
> - **Revise** the target design, the gap list, or the prompt before approval.
> - **Abandon** this Objective for now.
>
> Execution is not on offer until the retrieval path, Prop seeder, and grading harness exist.
