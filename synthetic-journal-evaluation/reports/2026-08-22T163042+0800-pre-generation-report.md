# Pre-generation report: grounded book reflection and longitudinal memory retrieval

## Decision

The current implementation is **insufficient** for the selected plan. Book grounding runs end to end, but nothing retrieves stored memories into a reflection turn, so two of the four required Scenes cannot run. Approve the build target and the target-state prompt; do not generate data yet.

| Required Scene | Target behavior | Status | Evidence or gap |
|---|---|---|---|
| S1 grounded book reflection | A Line that makes a book claim or quotation triggers Librarian retrieval inside the confirmed reading ceiling; Provenance passes; every quotation resolves to corpus text | partially runnable | Path exists: `src/linger/orchestration/grounding.py`, `apps/backend/hybrid_librarian.py`, release checks in `src/linger/orchestration/reflection.py` (`_trusted_book_evidence`, `_validate_release`), covered by `tests/test_grounding.py`, `tests/test_librarian_end_to_end.py`, `tests/test_reflection.py`. Gaps: reading position is confirmed by the interim parser in `apps/backend/main.py` (`resolve_reading_context`), which linger-lfh replaces; no package-driven Scene runner feeds Lines to `POST /api/chat` |
| S2 personal reflection, no retrieval | A nearby non-factual Line is answered without calling Librarian | partially runnable | Muse holds no general tools and calls `librarian_search` only on demand (`src/linger/agents/muse/tools.py`); no runner records whether retrieval occurred per Scene |
| S3 later session, one relevant memory | A fresh session answers better because one active Prop is retrieved and cited as recalled user words | blocked | `MemoryPolicyService.list_active` is consumed only by the private-wording check in `src/linger/orchestration/connection.py`. Librarian exposes no memory tool; no memory reaches a Muse reflection. linger-xn2.5 was closed as superseded and depends on open linger-4sp |
| S4 later session, comparison | A nearby fresh-session Line where no stored Prop is relevant, and none is presented as support | blocked | Same missing retrieval capability; with no retrieval there is no selective-retrieval behavior to observe |

## Your selection

- **Grounded book reflection** (`grounded_book_reflection`): Librarian retrieves book passages when a reflection includes a quotation or factual claim. Tests whether Muse stays grounded, Provenance verifies the evidence, and personal reflection avoids unnecessary retrieval.
- **Longitudinal memory retrieval** (`longitudinal_memory_retrieval`): across sessions, Librarian retrieves active memories authorized by the Memory & Policy Service. Tests whether Muse benefits from relevant history without relying on prior chat context or forcing unrelated memories in.

## Target evaluation design

The design uses the six canonical nouns in [specification Section 7.2.1](../../docs/specification.md#721-canonical-vocabulary). One corpus-backed Backstory covers both Objectives: the reader whose earlier reflections were stored also asks the later grounded question.

| Noun | How it applies here |
|---|---|
| **Objective** | The two confirmed catalog entries. Each Scene declares the Objective it serves, and every selected Objective needs at least one Scene. No run configuration applies: the only resolved configuration in `synthetic-journal-evaluation/run-configurations/` targets `reviewed_automatic_memory_capture`, which is not selected. |
| **Backstory** | One person, one evaluation account, one reading history. It is corpus-backed: the generator discovers the available work, immutable version, chapter structure, and quotable text under `data/corpus/` at invocation time. It never enters the running system. |
| **Prop** | Separate memory records positioned before S3 and S4, written as their own source text rather than copied from the Backstory or any Line. Plan at least one Prop that a later reflection should benefit from and two or more that it should not. Every Prop declares a lifecycle state for each Scene that references it. |
| **Scene** | Four bounded units in the order S1, S2, S3, S4. Each runs in a fresh session. S1 pairs with S2 on retrieval need; S3 pairs with S4 on memory relevance. |
| **Line** | The conversational inputs. S1 needs an ordered pair: one Line that establishes the reading position naturally, then one that makes the book claim. S2, S3, and S4 each carry one Line. Session reset and account state are workflow state, not Lines. |
| **Ground truth** | The generator writes **proposed** labels only, in a separate authoring manifest: which Scene requires retrieval, permitted corpus evidence with exact locations, quotation spans, per-Prop relevance and lifecycle, and prohibited outcomes. Deterministic validation then checks facts; an independent reviewer adopts, revises, or rejects each label. Only **adopted** Ground truth grades a run. |

Both contracts are **Adopted v1**, defined in `evals/synthetic_journals/models.py` and checked by `evals/synthetic_journals/validate_package.py`. `SyntheticContent` holds one `Backstory`, `Prop` records with per-Scene `lifecycle`, ordered `Scene` records, and `Line` records. `AuthoringManifest` holds `content_sha256`, `ground_truth_status: proposed`, and one `GroundTruthProposal` per Scene and Objective pair with outcomes, `exact_spans`, typed `evidence`, and `ScenePairing`.

## Current implementation and required work

**Observed.** Book grounding fails closed: the request scope is application-minted, an unconfirmed reading returns a typed clarification without dispatch, evidence above the ceiling is filtered, and the release path re-resolves every declared quotation. `tests/test_grounding.py`, `tests/test_librarian_end_to_end.py`, and `tests/test_reflection.py` cover those contracts; `tests/test_synthetic_journal_package.py` covers the validator with 17 tests. Reusable assets: that validator, `evals/muse/harness.py`, and `evals/librarian/`.

**Observed.** `MemoryPolicyService` (`src/linger/services/memory.py`) commits and lists account-scoped records, but `MemoryRecord` has no lifecycle field and `save_automatic` writes only through the capture policy path.

**Proposed** build-out:

1. **Capability gap — memory retrieval.** Expose account-scoped active-memory retrieval to Muse through a thin Librarian adapter. Acceptance: a fresh-session turn retrieves only the trusted account's active records, and the reply separates recalled user words from interpretation. Tracked by linger-xn2.5, which depends on open linger-4sp.
2. **Capability gap — Prop lifecycle.** Represent non-active states so `PropLifecycle` values other than `active` mean something. Acceptance: an inactive, superseded, or deleted record never returns as evidence. Covered by linger-4sp.
3. **Adapter gap — Prop seeding.** Position Props before a Scene runs without routing them through automatic capture. Acceptance: seeded records are account-scoped, distinguishable from runtime captures, and never model-authored.
4. **Adapter gap — Scene runner.** Feed package Lines to `POST /api/chat`, reset the session between Scenes, and record retrieval calls, evidence identifiers, and released text. Acceptance: replay produces one machine-readable outcome record per Scene.
5. **Adapter gap — reading boundary.** Finish linger-lfh so a natural reading-position Line confirms work and ceiling through a typed Muse boundary. Acceptance: S1 confirms without a hand-tuned phrase, and ambiguous phrasing still clarifies.
6. **Grading gap.** Review ownership and adoption tooling are unadopted, and no harness measures evidence recall, citation precision, or retrieval relevance.

Repository snapshot: branch `main`, `HEAD` `df5a359`, clean tree, inspected 2026-08-22T16:30:42+08:00; `HEAD` reproduces this inspection.

## Expected behavior and evaluation

The plan contains Lines only.

| Representative input | Likely behavior (hypothesis) | Plain-language success check |
|---|---|---|
| S1a: a natural statement of which book and how far the person has read | Muse records the boundary, or asks one clarifying question if the phrasing is ambiguous | The turn either confirms a ceiling or asks about it, and reveals nothing beyond it |
| S1b: a reflection quoting a remembered passage and asking what it means | Librarian returns passages at or before the ceiling; the reply quotes only corpus text and cites it | Every quoted phrase appears in the cited corpus location (evidence recall, citation precision, exact quotation accuracy) |
| S2: a personal reflection with no factual claim | Muse answers directly without calling Librarian | The reply is useful and no retrieval happened |
| S3: a later question revisiting an earlier theme in a fresh session | Retrieval surfaces the one relevant Prop; the reply distinguishes recalled words from interpretation | The response is better because of the stored record, and the record is identified (recall@5, nDCG@5) |
| S4: a nearby later question the stored records do not help with | Retrieval returns nothing usable; the reply answers without leaning on unrelated records | No unrelated Prop is presented as support (precision@5) |

Treat the response column as a hypothesis, not an oracle.

## Proposed generator prompt

```text
STATUS: Target state — do not run.

PRECONDITIONS. Do not execute this prompt until all of the following exist in
the repository you are given:
1. Account-scoped active-memory retrieval reachable by Muse through Librarian.
2. Memory lifecycle states beyond implicitly active records.
3. An evaluation-only path that positions memory records before a Scene runs.
4. A Scene runner that feeds Lines to the chat API with a fresh session per
   Scene and records outcomes.
5. A typed reading-boundary confirmation that accepts natural phrasing.
If any precondition is unmet, stop and report which one. Producing content
under an unmet precondition invalidates this prompt.

ROLE. You are an authoring generator. You have read-only access to the current
checkout and must inspect it at invocation time instead of trusting any earlier
description of it. You never observe Linger's recorded output, never grade it,
and never adopt your own labels.

PERMITTED PATHS. Read `data/corpus/`, `evals/synthetic_journals/models.py`,
`evals/synthetic_journals/README.md`, and `docs/specification.md` Section 7.2.1.
Discover the available work, its immutable version identifier, chapter
structure, and exact quotable text under `data/corpus/` yourself. Do not
hardcode any book fact from another document.

WHAT TO CREATE. One package for two Objectives: `grounded_book_reflection` and
`longitudinal_memory_retrieval`.

Backstory: exactly one, for one person and one evaluation account, corpus-
backed. Give the person a plausible reading history for the work you discover
and a multi-session history that explains why earlier reflections were stored.
The Backstory never enters the running system and is never copied into a Prop
or a Line.

Props: create at least three memory records as separate source text in the
person's own words. At least one must be the record a later reflection
genuinely benefits from; at least two must be plausible but unhelpful for that
later question. Assign each Prop only to the later-session Scenes and give each
a lifecycle state for exactly the Scenes that reference it. Do not create Props
for the book-reflection Scenes.

Scenes: create exactly four, ordered, each in a fresh session.
- Scene 1 (grounded_book_reflection): a reflection that cannot be answered well
  without a specific passage from the discovered work.
- Scene 2 (grounded_book_reflection): a nearby personal, non-factual reflection
  that needs no book evidence and stays useful on its own.
- Scene 3 (longitudinal_memory_retrieval): a later question that revisits an
  earlier theme without repeating any Prop verbatim, and that is more useful
  when the relevant Prop is available.
- Scene 4 (longitudinal_memory_retrieval): a nearby later question, close in
  topic, that the available Props do not help answer.

Lines: write natural journal or conversation input in the person's own words.
Scene 1 takes two ordered Lines: the first states which book and how far the
person has read, phrased the way a reader would say it; the second makes the
claim or quotation that requires evidence. Scenes 2, 3, and 4 take one Line
each. Do not write offline inputs. Never name internal agents, expected routes,
grading labels, or session controls inside a Line. Never state chapter
coordinates in a Prop.

OUTPUT CONTRACT. Write two JSON files.
1. Content: conform exactly to `SyntheticContent` in
   `evals/synthetic_journals/models.py` (schema_version 1). Extra fields are
   rejected. Do not invent another schema, and do not add a run configuration
   identifier: no resolved run configuration applies to these Objectives.
2. Authoring manifest: conform exactly to `AuthoringManifest` in the same file.
   Set `ground_truth_status` to "proposed" and `content_sha256` to the SHA-256
   of the exact content file bytes you wrote.

PROPOSED GROUND TRUTH. The manifest holds proposed Ground truth only. Write one
`GroundTruthProposal` for every Scene and Objective pair. In each proposal:
- State expected outcomes and prohibited outcomes as plain sentences about what
  the run should and must not do.
- For the grounded Scene, record permitted book evidence as repository_text
  evidence with the exact path, source SHA-256, code-point span, and text you
  read from `data/corpus/`, and record the exact quotation span in the Line.
- For the later-session Scenes, record prop evidence for the Prop that should
  help, and state which Props must not be presented as support.
- Declare the Scene pairing: Scene 1 with Scene 2, Scene 3 with Scene 4, naming
  only fields that genuinely match and genuinely differ.
Never write a claim about Linger's recorded behavior, and never mark any label
adopted. Your labels are candidates until an independent reviewer accepts them.

BEFORE YOU FINISH. Run the deterministic package validator at
`evals/synthetic_journals/validate_package.py` from the repository root:
`.venv/bin/python -m evals.synthetic_journals.validate_package <content.json>
<authoring-manifest.json>`. Fix every reported failure and rerun until it
passes. Report both file paths, the content SHA-256, and the validator result.
Do not hand the manifest or any proposed label to the system under evaluation.
```

## Ground truth lifecycle

The generator proposes, code checks facts, and a person decides.

**Generator.** It writes content and the manifest together, anchoring every proposed label to generated identifiers, exact code-point spans, corpus evidence, per-Prop relevance and lifecycle, and Scene pairings.

**Deterministic validation.** `evals/synthetic_journals/validate_package.py` verifies the manifest hash against the exact content bytes, one proposal per Scene and Objective pair, spans resolving inside the referenced Line or Prop, repository evidence resolving at the declared path, hash, and offsets, contiguous ordering, unique evidence identifiers, and true pairing differences. It fails closed, and judges neither prose realism nor label correctness.

**Independent adoption.** A reviewer who did not generate the package adopts, revises, or rejects each label. Required evidence: the corpus passage at its declared location for every quotation claim, and the Prop text behind every relevance judgment. Acceptance checks: the grounded Scene needs a passage, the comparison Scene does not, the relevant Prop is the only helpful one, and no prohibited outcome is unreachable. Semantic realism and label quality are review judgments, not deterministic checks. Only adopted labels grade a run, and neither state reaches Linger.

**Gap.** Review ownership and adoption tooling are unadopted. Smallest decision: name one reviewer other than the generator's operator, and record each verdict beside the package.

## Architecture and academic relevance

Participating: **Muse** drafts every response, **Librarian** retrieves book evidence and, after the build-out, authorized memories, and **Provenance** reviews every candidate. The **Memory & Policy Service** is the deterministic authority for account scope, storage, and record eligibility. **Sculptor** and **Serendipity** do not participate.

The plan tests one authority boundary: Muse cannot widen its own evidence scope. Application code mints the request identifier, access scope, and reading ceiling, and clamps any value Muse supplies (`build_request` and the ceiling clamp in `src/linger/orchestration/grounding.py`). The same rule must hold for memory: record eligibility comes from trusted application state, not model output.

This meets the briefing's expectation of testing artifacts covering agent behavior and end-to-end flow verification (page 11) and answers its explainability and traceability question (page 9): each Scene links a released response to the evidence identifiers and spans that authorized it.

> **Human decision required.** Choose one: approve the build target and the target-state prompt; revise either; or abandon this plan. Generation stays unauthorized until the five named preconditions exist.
