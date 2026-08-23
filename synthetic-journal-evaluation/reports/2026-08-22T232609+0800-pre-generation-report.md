# Pre-generation report: grounded book reflection and longitudinal memory retrieval

## Decision

The current implementation is **insufficient** for the complete selected plan. Book grounding runs end to end and fails closed, but no code path puts a stored memory in front of a reflection turn, so the two memory Scenes cannot run. Approve the build target and the target-state prompt; hold generation until the preconditions exist.

| Required Scene | Target behavior | Status | Evidence or gap |
|---|---|---|---|
| S1 — grounded book reflection | A Line that quotes or claims a book fact triggers Librarian retrieval inside the reader's confirmed ceiling, Provenance reviews the draft, and every released quotation resolves to corpus text | partially runnable | Path exists end to end: `src/linger/agents/muse/tools.py` (`librarian_search`), `src/linger/orchestration/grounding.py` (`build_request` mints the request ID and access scope), release checks in `src/linger/orchestration/reflection.py` (`_trusted_book_evidence`, `_validate_release`), served by `POST /api/chat` in `apps/backend/main.py`. Covered by `tests/test_grounding.py`, `tests/test_librarian_end_to_end.py`, `tests/test_reflection.py`. Gap: the reading position still comes from the interim parser `resolve_reading_context` (`apps/backend/main.py:133`), which linger-lfh replaces, and no runner feeds package Lines to the endpoint |
| S2 — personal reflection, no retrieval | A nearby non-factual Line is answered without any Librarian call | partially runnable | Muse holds only `librarian_search` and `serendipity_explore` and calls neither by default (`src/linger/agents/muse/tools.py`). Gap: nothing records per-Scene whether retrieval happened, so "no unnecessary retrieval" is unobservable today |
| S3 — later session, one relevant memory | A fresh session answers better because one active Prop is retrieved, and the reply separates recalled words from interpretation | blocked | `MemoryPolicyService.list_active` (`src/linger/services/memory.py:144`) has exactly one consumer: the private-wording guard in `src/linger/orchestration/connection.py:65`. Librarian exposes no memory tool, so no stored record reaches a reflection. linger-xn2.5 is closed as superseded and its schema dependency linger-4sp is open |
| S4 — later session, comparison | A nearby fresh-session Line that the stored Props do not help, with no Prop presented as support | blocked | Same missing capability. Without retrieval there is no selective-retrieval behavior to grade |

## Your selection

- **Grounded book reflection** (`grounded_book_reflection`): Linger uses Librarian to retrieve book passages when a reflection includes a quotation or factual claim. Tests whether Muse stays grounded, Provenance verifies the evidence, and personal reflection proceeds without unnecessary retrieval.
- **Longitudinal memory retrieval** (`longitudinal_memory_retrieval`): across sessions, Librarian retrieves active memories authorized by the Memory & Policy Service. Tests whether Muse benefits from relevant history without relying on prior chat context or forcing unrelated memories in.

## Target evaluation design

One corpus-backed Backstory carries both Objectives, using the canonical nouns in [specification Section 7.2.1](../../docs/specification.md#721-canonical-vocabulary). The reader whose earlier reflections were stored is the reader who later asks the grounded question.

| Noun | How it applies here |
|---|---|
| **Objective** | The two confirmed catalog entries. Each Scene declares the Objective it serves, and every selected Objective needs at least one Scene. No run configuration applies: the only resolved configuration in `synthetic-journal-evaluation/run-configurations/` targets `reviewed_automatic_memory_capture`, which you did not select, so `run_configuration_ids` stays empty. |
| **Backstory** | One person, one evaluation account, one reading history. Corpus-backed: the generator discovers the available work, its immutable version, chapter structure, and exact quotable text under `data/corpus/` at invocation time. It never enters the running system and is never copied into a Prop or Line. |
| **Prop** | Separate memory records written as their own source text, positioned before S3 and S4 only. Plan one Prop the later reflection genuinely benefits from and at least two plausible but unhelpful ones. Every Prop declares a lifecycle state for exactly the Scenes that reference it; the book Scenes carry no Props. |
| **Scene** | Four ordered units, S1 through S4, each in a fresh session. S1 pairs with S2 on retrieval need; S3 pairs with S4 on memory relevance. |
| **Line** | The conversational inputs. S1 needs two ordered Lines: one that states the book and reading position naturally, then one that makes the claim or quotation. S2, S3, and S4 take one Line each. Session reset and account state are workflow state, not Lines. |
| **Ground truth** | The generator writes **proposed** labels only, in a separate authoring manifest: which Scene requires retrieval, permitted corpus evidence with exact locations, quotation spans, per-Prop relevance and lifecycle, and prohibited outcomes. Deterministic validation then checks facts, and an independent reviewer adopts, revises, or rejects each label. Only **adopted** Ground truth grades a run. |

`evals/synthetic_journals/models.py` defines both contracts, and `evals/synthetic_journals/validate_package.py` checks them. `SyntheticContent` holds one `Backstory`, `Prop` records with per-Scene `lifecycle`, ordered `Scene` records, and `Line` records. `AuthoringManifest` holds `content_sha256`, `ground_truth_status: proposed`, and one `GroundTruthProposal` per Scene and Objective pair with outcomes, `exact_spans`, typed `evidence`, and a `ScenePairing`.

## Current implementation and required work

**Observed.** Book grounding enforces the authority boundary. The application mints the request ID and access scope, an unconfirmed reading returns a typed clarification instead of dispatching, and `_validate_release` re-resolves every declared quotation. `tests/test_grounding.py`, `tests/test_librarian_end_to_end.py`, `tests/test_reflection.py`, and `tests/test_synthetic_journal_package.py` cover those contracts. Reusable assets: the package validator, `evals/muse/harness.py`, `evals/librarian/`, and `DELETE /api/sessions/{session_id}` for session reset.

**Observed.** `MemoryPolicyService` commits and lists account-scoped records, but `MemoryRecord` has no lifecycle field and `save_automatic` writes only through the capture-policy path.

**Proposed** build-out:

1. **Capability gap — memory retrieval.** Expose account-scoped active-memory retrieval to Muse through a thin Librarian adapter. Acceptance: a fresh-session turn retrieves only the trusted account's active records, and the reply distinguishes recalled words from interpretation. Tracked by superseded linger-xn2.5, which depends on open linger-4sp.
2. **Capability gap — Prop lifecycle.** Represent states beyond implicitly active so `PropLifecycle` values mean something. Acceptance: an inactive, superseded, or deleted record never returns as evidence. Covered by linger-4sp.
3. **Adapter gap — Prop seeding.** Position Props before a Scene runs without routing them through automatic capture. Acceptance: seeded records are account-scoped, distinguishable from runtime captures, and never model-authored.
4. **Adapter gap — Scene runner.** Feed package Lines to `POST /api/chat`, reset the session between Scenes, and record retrieval calls, evidence identifiers, and released text. Acceptance: one machine-readable outcome per Scene.
5. **Adapter gap — reading boundary.** Finish linger-lfh so a natural reading-position Line confirms work and ceiling through a typed Muse boundary; linger-kow tracks the synthetic boundary schema. Acceptance: S1 confirms without a hand-tuned phrase, and ambiguous phrasing still clarifies.
6. **Grading gap.** No harness measures evidence recall, citation precision, or retrieval relevance; review ownership and adoption tooling stay unadopted.

Repository snapshot: branch `main`, `HEAD` `df5a359`, tree clean except untracked `synthetic-journal-evaluation/reports/`, inspected 2026-08-22T23:26:09+08:00; `HEAD` alone reproduces it.

## Expected behavior and evaluation

The plan contains Lines only, no offline inputs.

| Representative input | Likely behavior (hypothesis) | Plain-language success check |
|---|---|---|
| S1a: a natural statement of which book the person is reading and how far | Muse records the boundary, or asks one clarifying question when the phrasing is ambiguous | The turn confirms a ceiling or asks about it, and reveals nothing past it |
| S1b: a reflection that quotes a remembered passage and asks what it means | Librarian returns passages at or before the ceiling; the reply quotes only corpus text and cites it | Every quoted phrase appears at the cited corpus location (evidence recall, citation precision, exact quotation accuracy) |
| S2: a personal reflection with no factual claim | Muse answers directly and calls no tool | The reply is useful and no retrieval happened |
| S3: a later fresh-session question revisiting an earlier theme | Retrieval surfaces the one relevant Prop; the reply marks what was recalled | The answer is better because of the stored record, and the record is identified (recall@5, nDCG@5) |
| S4: a nearby later question the stored records do not help with | Retrieval returns nothing usable; the reply stands on its own | No unrelated Prop is offered as support (precision@5) |

Treat the behavior column as hypothesis, not oracle.

## Proposed generator prompt

```text
STATUS: Target state — do not run.

PRECONDITIONS. Do not execute this prompt until all of the following exist in
the repository you are given:
1. Account-scoped active-memory retrieval reachable by Muse through Librarian.
2. Memory lifecycle states beyond implicitly active records.
3. An evaluation-only path that positions memory records before a Scene runs.
4. A Scene runner that feeds Lines to the chat API with a fresh session per
   Scene and records what was retrieved and released.
5. A typed reading-boundary confirmation that accepts natural phrasing.
If any precondition is unmet, stop and report which one. Content produced
under an unmet precondition is invalid.

ROLE. You are an authoring generator. You have read-only access to the current
checkout and must inspect it at invocation time rather than trust any earlier
description of it. You never observe Linger's recorded output, never grade it,
and never adopt your own labels.

PERMITTED PATHS. Read `data/corpus/`, `evals/synthetic_journals/models.py`,
`evals/synthetic_journals/README.md`, and `docs/specification.md` Section
7.2.1. Discover the available work, its immutable version identifier, chapter
structure, and exact quotable text under `data/corpus/` yourself. Do not
hardcode a book fact taken from another document.

WHAT TO CREATE. One package covering two Objectives: `grounded_book_reflection`
and `longitudinal_memory_retrieval`.

Backstory: exactly one, for one person and one evaluation account, corpus-
backed. Give the person a plausible reading history for the work you discover
and a multi-session history that explains why earlier reflections were stored.
The Backstory never enters the running system and is never copied into a Prop
or a Line.

Props: create at least three memory records as separate source text in the
person's own words. At least one must be the record a later reflection
genuinely benefits from; at least two must be plausible but unhelpful for that
later question. Assign Props only to the later-session Scenes, and give each
Prop a lifecycle state for exactly the Scenes that reference it. Create no
Props for the book Scenes.

Scenes: create exactly four, ordered, each in a fresh session.
- Scene 1 (grounded_book_reflection): a reflection that cannot be answered well
  without a specific passage from the work you discovered.
- Scene 2 (grounded_book_reflection): a nearby personal, non-factual reflection
  that needs no book evidence and stays useful on its own.
- Scene 3 (longitudinal_memory_retrieval): a later question that revisits an
  earlier theme without repeating any Prop verbatim and that is more useful
  when the relevant Prop is available.
- Scene 4 (longitudinal_memory_retrieval): a nearby later question, close in
  topic, that the available Props do not help answer.

Lines: write natural journal or conversation input in the person's own words.
Scene 1 takes two ordered Lines: the first names the book and how far the
person has read, phrased the way a reader would say it; the second makes the
claim or quotation that needs evidence. Scenes 2, 3, and 4 take one Line each.
Write no offline inputs. Never name internal agents, expected routes, grading
labels, or session controls inside a Line, and never state chapter coordinates
in a Prop.

OUTPUT CONTRACT. Write two JSON files.
1. Content: conform exactly to `SyntheticContent` in
   `evals/synthetic_journals/models.py`. Extra fields are rejected. Do not
   invent another schema, and leave `run_configuration_ids`
   empty: no resolved run configuration applies to these Objectives.
2. Authoring manifest: conform exactly to `AuthoringManifest` in the same file.
   Set `ground_truth_status` to "proposed" and `content_sha256` to the SHA-256
   of the exact content-file bytes you wrote.

PROPOSED GROUND TRUTH. The manifest holds proposed Ground truth only. Write one
`GroundTruthProposal` for every Scene and Objective pair. In each proposal:
- State expected outcomes and prohibited outcomes as plain sentences about what
  the run should and must not do.
- For the grounded Scene, record permitted book evidence as repository_text
  evidence with the exact path, source SHA-256, code-point span, and text you
  read from `data/corpus/`, and record the exact quotation span in the Line.
- For the later-session Scenes, record prop evidence for the Prop that should
  help, and say which Props must not be presented as support.
- Declare the Scene pairing: Scene 1 with Scene 2, Scene 3 with Scene 4, naming
  only fields that genuinely match and genuinely differ.
Never write a claim about Linger's recorded behavior, and never mark a label
adopted. Your labels stay candidates until an independent reviewer accepts
them.

BEFORE YOU FINISH. Run the deterministic package validator at
`evals/synthetic_journals/validate_package.py` from the repository root:
`.venv/bin/python -m evals.synthetic_journals.validate_package <content.json>
<authoring-manifest.json>`. Fix every reported failure and rerun until it
passes. Report both file paths, the content SHA-256, and the validator result.
Hand neither the manifest nor any proposed label to the system under
evaluation.
```

## Ground truth lifecycle

The generator proposes, code checks facts, and a person decides.

**Generator.** It writes content and the manifest together, anchoring every proposed label to generated identifiers, exact code-point spans, corpus evidence, per-Prop relevance and lifecycle, and Scene pairings.

**Deterministic validation.** `evals/synthetic_journals/validate_package.py` verifies the manifest hash against the exact content bytes, one proposal per Scene and Objective pair, spans resolving inside the referenced Line or Prop, repository evidence resolving at the declared path, hash, and offsets, contiguous ordering, unique evidence identifiers, and true pairing claims. It fails closed, and judges neither prose realism nor label correctness.

**Independent adoption.** A reviewer who did not generate the package adopts, revises, or rejects each label. Required evidence: the corpus passage at its declared location for every quotation claim, and the Prop text behind every relevance judgment. Acceptance checks: the grounded Scene needs a passage, the comparison Scene does not, one Prop is the helpful one, and no prohibited outcome is unreachable. Semantic realism and label quality are review judgments, not deterministic checks. Only adopted labels grade a run.

**Gap.** Review ownership and adoption tooling are unadopted. Smallest decision: name one reviewer other than the generator's operator, and record each verdict beside the package.

## Architecture and academic relevance

Participating: **Muse** drafts every response, **Librarian** retrieves book evidence and, after the build-out, authorized memories, and **Provenance** reviews every candidate. The **Memory & Policy Service** is the deterministic authority for account scope, storage, and eligibility. **Sculptor** and **Serendipity** do not participate.

The plan tests one authority boundary: Muse cannot widen its own evidence scope. Application code mints the request identifier and access scope and clamps the ceiling in `src/linger/orchestration/grounding.py`, so a model-supplied value cannot reach further. The same rule must hold for memory eligibility, which comes from trusted application state rather than model output.

This answers the briefing's explainability and traceability question (page 9) and yields the testing artifacts it expects, including agent-behavior tests and end-to-end flow verification (page 11): each Scene links a released response to the evidence that authorized it.

> **Human decision required.** Choose one: approve the build target and the target-state prompt; revise either; or abandon this plan. Generation stays unauthorized until the five named preconditions exist.
