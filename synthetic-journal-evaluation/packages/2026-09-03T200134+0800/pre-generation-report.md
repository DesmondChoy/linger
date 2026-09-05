# Pre-generation decision memo

## Decision

The current implementation is **sufficient** for the selected design and a separately approved generation step. The package validator, human review, and replay now use the same book answer key. This establishes runnable evaluation infrastructure, not proven model accuracy.

| Required Scene | Target behavior | Status | Evidence |
|---|---|---|---|
| Event-led inference and grounded reflection | Infer progress from a remembered event, retrieve within that boundary, and release a supported reflection. | runnable | Canonical compiler, exact corpus evidence matching, production chat integration, and boundary-observability tests pass. |
| Ambiguous spoiler comparison | Clarify without retrieving or revealing later events. | runnable | Shared route precedence and correlated inference observations pass. Literal disclosure checks are deterministic; optional semantic review is separate. |
| Personal reflection comparison | Respond without unnecessary retrieval. | runnable | Replay verifies no route, search, or released evidence and unchanged Prop storage. |

The evaluation ends at boundary decisions, retrieval, evidence, quotations, and released spoilers. Memory capture and curation are outside these Objectives.

## Your selection

- **Grounded book reflection** (`grounded_book_reflection`): Retrieve and verify passages for book claims or quotations; avoid unnecessary retrieval for personal reflection.
- **Spoiler-boundary clarification** (`spoiler_boundary_clarification`): Infer progress from remembered events, retrieve within that boundary, and clarify uncertainty.

## Target evaluation design

Use the six [canonical nouns](../../../docs/specification.md#721-canonical-vocabulary) as follows.

| Noun | Application in this package |
|---|---|
| Objective | Both confirmed catalog entries. Each requires a positive Scene and a comparison; the combined Scene satisfies both positive requirements. |
| Backstory | One corpus-backed history for one person and evaluation account. It guides authoring and stays outside runtime inputs. |
| Prop | One separately written event memory, active in both spoiler Scenes and absent from the personal comparison. No run configuration applies. |
| Scene | Three ordered, fresh-session Scenes: combined inference/grounding, ambiguous clarification, and personal reflection. This count is the chosen design, not a universal runner restriction. |
| Line | One natural conversational input per Scene. No offline inputs, chapter coordinates, or workflow instructions. |
| Ground truth | Four proposed judgments in a separate file: two for the combined Scene and one per comparison. Shared book facts belong once to each relevant Scene. An independent human must adopt the judgments before grading. |

[`models.py`](../../../evals/synthetic_journals/models.py) defines the Backstory graph and separate proposed Ground truth. It defines `book_scene_facts` and `book_expectation`, replacing the older book fields. [The validator](../../../evals/synthetic_journals/validate_package.py) checks hashes, references, spans, ordering, and pairings and calls the book compiler. The future generator must use these repository models unchanged.

## Current implementation and required work

**Observed.** The authorized repair is implemented in the working tree. Shared `book_scene_facts` owns book scope and evidence. Each proposal's `book_expectation` owns its Objective-specific judgment. Generic `grounding` belongs only to weak-evidence evaluation. The [design record](../../../docs/design/synthetic-book-replay-contract.md) explains the boundary.

| Former gap | Implemented check and example |
|---|---|
| Contract and selection | The compiler and replay accept grounded-only, spoiler-only, and both orders. Missing or extra labels fail validation instead of crashing. |
| Source integrity | Registered corpus, immutable source, exact spans, inferred ceiling, and pairings validate. The same sentence in a different paragraph does not match. |
| Route adapter | Tool names distinguish route from search. Production and replay choose clarification before a routed result. Request IDs select the matching private inference exchange. |
| Evidence grading | Full work, version, chapter, hash, source lines, location, and window text must match. Unknown support IDs and another Prop's memory support fail. |
| Spoiler meaning | Hard gates check exact forbidden text. Optional `--semantic-review` reports paraphrased disclosure separately as non-independent. A hard pass does not prove semantic safety. |
| Human review | The interface displays shared facts, derived ceiling, basis spans, excerpts, and typed expectations. A changed file invalidates the entire adoption. |
| Support agreement | Catalog, specification, review dispatch, and README agree on exact supported selections. Old book packages remain historical, obsolete inputs. |

**Observed.** The product path is account-scoped Prop setup → preflight → Muse routing → private full-work inference → validated boundary → bounded retrieval → Muse response → Provenance and deterministic checks → release and session record. Uncertainty requires clarification. Failed safety or release checks stop normal release. Personal reflection can skip book tools; capture is disabled.

**Observed.** Reusable assets include `book_contract.py`, `book_evidence.py`, `book_replay.py`, `book_semantics.py`, `adoption.py`, and the boundary-observability tests. History records narrow replay (`d77efea`), generic grounding (`b1903e3`, `94a32e2`), inference (`cb48cec`), merged contracts (`9045a4a`), and partial repair (`78fb245`). This repair completes `linger-yq1`, `linger-6fz0`, `linger-96z`, and `linger-3sif`. Closed `linger-ck1` and `linger-lfh` record earlier implementations; `linger-o0f` duplicates the shipped inference work.

**Observed.** Verification: `.venv/bin/python -m pytest -q --tb=short` passed **632 tests and 301 subtests**. The focused book suite passed 38 tests; the review UI build and both Node tests passed. Regression tests cover source tampering, repeated text, hybrid windows, malformed contracts, wrong runtime identity, route precedence, correlated support, stale adoption, and every supported selection. Semantic tests use a local test model and prove result handling, not live judge accuracy.

**Proposed.** No further implementation build-out is required for this selected plan. Keep independent human review of boundary defensibility, ambiguity, and semantic disclosure.

**Assumed.** Future generation can inspect the current checkout and write the two reserved files after separate approval.

Snapshot: `main`, HEAD `ac0f281a247b8d6508f83201c299ab7eed42961c`, 2026-09-05 09:18 +08:00; fixes and report are uncommitted, and staged `.gitignore` is unrelated. **HEAD alone does not reproduce this assessment.** Relevant-file fingerprint: `6e250b2c941f7f0cadbc6e665f20e86da376ea75e667ab174f1ae63f63e64646`, SHA-256 of ordered `shasum -a 256` output for models, validator, book compiler, evidence resolver, book runner, semantic reviewer, replay-support registry, Librarian contracts, reflection orchestration, routing orchestration, catalog, reviewer script, and specification.

## Expected behavior and evaluation

The plan contains Lines. These examples illustrate intent; they are not generated data or exact response oracles.

| Example input | Expected behavior | Success check |
|---|---|---|
| Prop recalls an earlier identity conversation; Line asks why that known event matters and requests a quotation. | Infer the supported boundary and ground the response. | Work, version, ceiling, quotation, and location agree with adopted Ground truth. |
| Same Prop; Line vaguely asks about a later encounter. | Ask where the reader has reached. | No evidence retrieval or released spoiler, including in the question. Review must establish genuine ambiguity. |
| No Prop; Line says changing plans makes identity feel uncertain. | Offer personal reflection. | No unnecessary retrieval. Usefulness is reviewed separately. |

## Proposed generator prompt

```text
STATUS: Runnable after human approval

PRECONDITIONS:
The developer must explicitly approve generation using this design and prompt. At invocation time, confirm that the current canonical book models, compiler, validator, review interface, and supported replay selections still agree and their focused tests pass. Confirm that the registered corpus is intact and both reserved output paths are absent. Stop without writing files if any condition is unmet or cannot be established. Implementation approval alone is not generation approval.

PACKAGE_DIRECTORY=synthetic-journal-evaluation/packages/2026-09-03T200134+0800

You have read-only access to the current checkout except for two reserved outputs:
- PACKAGE_DIRECTORY/backstory.json
- PACKAGE_DIRECTORY/ground-truth.json

Do not overwrite existing outputs or write other files. Do not invoke Linger, grade recorded responses, or adopt labels.

Inspect these permitted paths at invocation time:
- data/corpus/
- evals/synthetic_journals/models.py
- evals/synthetic_journals/validate_package.py
- evals/synthetic_journals/book_contract.py
- evals/synthetic_journals/book_evidence.py
- docs/specification.md, Section 7.2.1

Discover the available work, immutable version, ordered structure, and exact passages from the current corpus. Do not assume a title, version, chapter count, or passage from an earlier report. Use the finalized models and deterministic package validator unchanged. If they cannot represent the design, stop; do not invent fields or another schema.

Selected Objectives:
- grounded_book_reflection
- spoiler_boundary_clarification

Write one Backstory for one person and one evaluation account. Give the person plausible reading habits and a personal concern connected to the discovered work. Keep the Backstory separate from runtime inputs.

Write exactly one Prop as a separate record recalling previously discussed events. It is active before the first and second Scenes and absent from the third. Do not copy a complete Line into it. Do not put chapter coordinates or later events into Props or Lines.

Write three ordered Scenes, each with a fresh session and one natural Line:
1. Both Objectives: the Prop and Line refer to known events supporting a uniquely defensible reading boundary. Connect a personal question to a passage and request an exact quotation or factual explanation requiring evidence.
2. Spoiler comparison: keep the same active Prop. Write a genuinely ambiguous event reference for which clarification is appropriate. Ambiguity must be supported by the content.
3. Grounded-reflection comparison: use no Prop. Write a nearby personal reflection useful without a factual book claim, quotation, or retrieval.

Every Prop, Scene, and Line belongs to the same Backstory. Workflow controls are not Lines. Use no offline inputs and no run configuration IDs.

Write PACKAGE_DIRECTORY/backstory.json and compute the SHA-256 of its exact bytes.

Write the separate ground truth file at PACKAGE_DIRECTORY/ground-truth.json with ground_truth_status set to proposed. Produce four proposed Ground truth judgments, one per Scene-Objective pair, using only the finalized repository contract.

Record shared book identity, boundary expectations, authorized Props, exact input basis spans, and corpus excerpts once in the appropriate Scene record. Follow the finalized evidence representation and uniqueness rules. Exact Unicode code-point spans must resolve to the stated source occurrence and text. Do not repeat shared facts in competing proposal fields.

For the combined Scene, propose the event-supported safe boundary and supporting locations. Follow the contract if it derives the ceiling from support; do not invent a second ceiling field. Its grounded proposal identifies required retrieval, permitted evidence, and exact quotation locations. Its spoiler proposal identifies at least one disjoint forbidden later fact.

For the ambiguous Scene, propose clarification with no granted ceiling or supporting inference evidence, and identify at least one forbidden later fact. For the personal Scene, propose no required retrieval and no permitted book evidence.

Include expected and prohibited outcomes and accurate Scene pairings. Preserve declared matching inputs and identify actual differences. Place spans and evidence where the finalized models require them.

Run evals/synthetic_journals/validate_package.py against the two sibling files. Correct only those files and rerun until schema, Backstory hash, references, ordering, spans, pairings, corpus evidence, and Objective facts validate. Stop if a failure requires repository code changes.

Validation does not establish semantic realism or adopt proposed Ground truth. An independent reviewer assesses relevance, the defensibility of the boundary, ambiguity, and forbidden facts. Do not grade prose quality, later memory capture, curation, or recorded Linger behavior. Neither proposed nor adopted Ground truth, nor the authoring Backstory, may reach Linger. Only designated Props and Lines are supplied through their established workflow.
```

## Ground truth lifecycle

Generation proposes; repository code validates objective facts; an independent human adopts, revises, or rejects every judgment. Semantic realism and label quality are review judgments. Missing spans, wrong corpus identity, false pairings, incomplete decisions, or self-adoption prevent acceptance.

The review app exposes the shared facts and typed expectations before confirmation. Its complete-file hash detects later changes. Preserve historical approvals as records; changed Ground truth requires fresh review. Only adopted Ground truth may grade a run, and neither proposed nor adopted Ground truth reaches Linger.

## Architecture and academic relevance

Muse, Librarian, and Provenance participate; Sculptor and Serendipity are outside this design. Memory & Policy supplies Props; application services own account scope, session isolation, boundary validation, and release. Full-work inference must return a content-free boundary before bounded retrieval supplies evidence to Muse.

The briefing asks how coordination and traceability can be demonstrated ([p. 9](../../../docs/submissions/aas-practice-module-briefing.pdf#page=9)) and lists end-to-end testing artifacts ([p. 11](../../../docs/submissions/aas-practice-module-briefing.pdf#page=11)). These paired Scenes can demonstrate a traceable evidence boundary and safe clarification.

> **Human decision required:** Approve the target design and generator prompt, request revisions, or abandon the package. No generation, adoption, or provider-backed replay has been performed.
