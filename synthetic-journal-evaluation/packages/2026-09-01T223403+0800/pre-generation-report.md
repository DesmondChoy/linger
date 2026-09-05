# Cross-source tentative connection pre-generation report

> Historical snapshot from 1 September 2026 at `77164fb`. The readiness findings
> and proposed prompt below describe that checkout, not the current implementation.

## Decision

The current implementation is **insufficient** for the complete selected plan. Do not generate this package yet: both required Scenes depend on account-scoped memory evidence, releasable public evidence, and an Objective-specific replay and grading path that do not exist together.

| Required Scene | Target behavior | Status | Exact evidence or gap |
|---|---|---|---|
| Supported connection | A fresh-session Line joins one active personal-memory Prop, current corpus evidence, and retrievable public evidence; the released reply cites support and stays tentative. | blocked | `ConnectionScope` permits only `book_corpus` and `web` ([models.py](../../../src/linger/agents/serendipity/models.py), line 15); the focused contract test rejects `authorised_memory` ([test_serendipity.py](../../../tests/test_serendipity.py), lines 171–173). A selected web record then fails deterministic release ([reflection.py](../../../src/linger/orchestration/reflection.py), lines 512–516; [test_reflection.py](../../../tests/test_reflection.py), lines 516–537). |
| Nearby overreach comparison | The same bounded exploration qualifies or declines when the three source roles do not support the stronger connection, without leaking private Prop wording into a web query. | blocked | The query guard checks the current cue and shaped personal data, not active-memory text ([tools.py](../../../src/linger/agents/serendipity/tools.py), lines 39–51 and 157–170). No cross-source runner or adopted grader exists, and no run-specific public-evidence bundle was supplied. |

The Objective evaluates the released connection or acceptable decline, its evidence and citations, and private-memory non-disclosure at the search boundary. Later capture or curation is terminal product context, not part of this evaluation.

## Your selection

- **Cross-source tentative connection** (`cross_source_tentative_connection`) — Serendipity explores authorized memories, book passages, and public evidence while Muse cites support, private wording stays out of web search, and Provenance blocks unsupported certainty.

## Target evaluation design

Use the six [canonical evaluation nouns](../../../docs/specification.md#721-canonical-vocabulary) as follows.

| Noun | Application in this package |
|---|---|
| **Objective** | One selected Objective with its catalog minimum of two contrasting Scenes. No run configuration applies, so `run_configuration_ids` is empty. |
| **Backstory** | One corpus-backed history for one person and one evaluation account, including a prior reflection and two plausible later cues. The running system never receives it. |
| **Prop** | One separately written, account-scoped memory record, active before both Scenes. It is not copied from a Line and has a lifecycle role in each Scene. |
| **Scene** | Two fresh-session units: one supportable connection and one nearby overreach comparison. They share the Backstory and Prop but differ in Line and public-evidence offline input. |
| **Line** | One natural conversational input sent to Muse in each Scene. Workflow controls are not Lines. Each Scene also has one offline input containing only its resolved public-evidence bundle. |
| **Ground truth** | Separate proposed labels bind target connections or acceptable decline, supporting Prop, repository, and offline-input evidence, exact spans, public claims needing citations, the Scene pairing, expected outcomes, and prohibited leakage or certainty. Independent review alone can make them adopted Ground truth. |

[`SyntheticBackstory` and `ProposedGroundTruth`](../../../evals/synthetic_journals/models.py) require one strict graph of Backstory, Props, Scenes, Lines, offline inputs, evidence, pairings, and proposals. The [package validator](../../../evals/synthetic_journals/validate_package.py) checks the exact Backstory hash, topology, ordering, spans, repository text, references, and declared pairing differences. It does not decide whether the connection is insightful or the labels are correct.

## Current implementation and required work

**Implementation appendix.** **Observed.** For each target Scene, the runner would pre-position the active Prop through the Memory & Policy Service and open a fresh session before sending the Line. A preflight boundary stops before Muse. Otherwise, Muse may call Serendipity, which uses bounded Librarian and Exa search and returns a typed proposal or decline; Muse drafts, Provenance passes, revises, or rejects, and deterministic checks release the reply or substitute the application safe decline. Missing evidence, an unsafe query, or weak support short-circuits to decline; failed review or citation resolution short-circuits to safe decline. Only released session history changes; Prop storage remains unchanged. Book-only proposals and declines reach terminal outcomes, but web-backed proposals fail closed and Serendipity has no stored-memory grant. The Objective endpoint is the released response plus request-local evidence and search observations. Current synthetic runners intentionally cover other Objectives, not this one.

The recent diffs establish that boundary: `6d32e6a` removed the obsolete memory/eval path; `52e0b30` added bounded discovery; `8758a6c` authorized selected book-only evidence; `6180304` hardened Provenance and preflight; and `ef32d8e` made unsupported Objectives stop after adoption. Closed Beads `linger-3g1`, `linger-ks8`, and `linger-0yd` respectively record web discovery, rubric/Inspect alignment, and deletion of the old memory path. No relevant open Bead owns this build-out. Focused tests passed: **98 passed, 30 subtests passed**.

**Proposed.** Close five gaps with the smallest existing-architecture extension: a **capability gap** adds a typed, account-scoped Serendipity memory adapter over the active memories already loaded by the Memory & Policy Service; a second **capability gap** admits successfully opened web records to a deterministic citation authority; a third **capability gap** checks outgoing queries against authorized Prop text; an **adapter gap** adds a two-Scene replay that seeds Props, supplies resolved public evidence, and records queries and releases; and a **grading gap** applies deterministic citation and non-leak checks while leaving semantic connection quality to independent review. Acceptance requires same-account active-only retrieval, no private phrase reaching Exa, resolvable support for every released factual claim, fail-closed unsupported evidence, no storage change, and adopted-label grading only.

**Assumed.** The generic package contracts can represent this plan unchanged. A **source gap** remains until the workflow supplies an independently reviewed, retrievable public-evidence bundle for both Scenes. No material authority contradiction remains.

Snapshot: `main@77164fb5a3a9266b4060346303d47789c90ff9da`, clean, `2026-09-01T22:26:00+0800`; fingerprints: catalog `35efc39c`, specification `80c2d7c3`, models `a7afb1a3`, validator `58a84b8d`, connection `0f4289ec`, Serendipity contract `f77072fb`. `HEAD` alone reproduces the inspected implementation.

## Expected behavior and evaluation

The plan contains Lines and public-evidence offline inputs. In the supported Scene, a Line asks whether a personal theme resonates with a book passage and public context; the likely response offers a qualified connection with resolvable citations. Success means all three source roles support the bridge, the interpretation remains tentative, and the web query contains no verbatim private Prop wording. In the comparison Scene, a nearby Line invites a stronger conclusion than the evidence permits; the likely response qualifies or declines. Success means no invented support, causation, or citation, while the response remains useful. Response wording is a hypothesis, not an exact oracle.

## Proposed generator prompt

```text
STATUS: Target state — do not run

PACKAGE_DIRECTORY=synthetic-journal-evaluation/packages/2026-09-01T223403+0800

PRECONDITIONS:
- The application has a typed, account-scoped active-memory grant for connection discovery.
- Successfully opened public-web evidence has deterministic citation and release authority, and the Provenance gate can review it.
- The outgoing web-query privacy guard checks the authorized memory text as well as the current Line.
- A cross_source_tentative_connection replay and adopted-label grading path can execute both Scenes through the production chat boundary.
- The workflow has supplied an independently reviewed, retrievable public-evidence bundle for both Scenes. PUBLIC_EVIDENCE_BUNDLE=NOT_SUPPLIED.

If any precondition is false or any resolved workflow input is missing, stop without writing files. Do not reinterpret this status as generation approval.

You have read-only access to the current checkout. Inspect only these permitted repository paths at invocation time:
- evals/synthetic_journals/models.py
- evals/synthetic_journals/validate_package.py
- data/corpus/

Do not read this report. Discover the available corpus work, immutable version, structure, and exact evidence from data/corpus/ at invocation time. Do not hardcode corpus facts from an earlier run. Use the supplied public-evidence bundle exactly; do not invent or replace public sources.

Use evals/synthetic_journals/models.py unchanged as the Backstory and Ground truth contract. Create exactly one corpus-backed Backstory for one person and one evaluation account. Set objective_ids to ["cross_source_tentative_connection"] and run_configuration_ids to [].

Create exactly one Prop containing a prior personal reflection as separate source text. Bind it to the Backstory person and evaluation account, and make it active before both Scenes. Do not copy a complete Line into the Prop.

Create exactly two fresh-session Scenes. The supported Scene must make one tentative connection supportable across the Prop, resolvable repository book evidence, and the supplied public evidence. The nearby comparison Scene must make the stronger exploration overreach unless it is qualified or declined. Both Scenes share the same Backstory and Prop. Give each Scene exactly one natural Line sent to Muse and exactly one offline input containing only that Scene's resolved public-evidence record. Lines must not mention agents, routes, labels, expected answers, or workflow controls.

Write a separate proposed Ground truth file. Include one GroundTruthProposal for each Scene and this Objective. Anchor the intended target connection or acceptable decline, expected and prohibited outcomes, supporting evidence identifiers, exact relevant spans, every public factual claim that requires a retrievable citation, and the matched-Scene relationship. Use PropEvidence for the personal record, RepositoryTextEvidence with current hashes and exact spans for book support, and OfflineInputEvidence for public support. Pair the Scenes so Backstory, fresh-session state, Prop IDs, and Line count match while Line text and public-evidence content differ. Record that private Prop wording must not appear verbatim in any public-search query and that unsupported causation or certainty is prohibited.

Write only these two sibling outputs:
- PACKAGE_DIRECTORY/backstory.json
- PACKAGE_DIRECTORY/ground-truth.json

Set ground_truth_status to "proposed" and bind ground-truth.json to the exact backstory.json SHA-256. Proposed Ground truth must not enter the system under evaluation. Do not observe or grade Linger's behavior, claim adoption, create an adoption file, or create replay output.

Run evals/synthetic_journals/validate_package.py against the two files. Treat any schema, hash, reference, span, ordering, evidence, pairing, or configuration failure as a generation failure. Deterministic validation does not establish semantic realism or label quality; an independent human reviewer must later adopt, revise, or reject every proposal.
```

## Ground truth lifecycle

The generator proposes exact Scene-bound labels and evidence in `ground-truth.json`. The validator rejects schema drift, hash mismatch, unresolved references, bad spans, missing proposal pairs, invalid repository evidence, or false declared differences; it neither checks recorded behavior nor adopts labels. An independent human developer then uses `review-synthetic-ground-truth` to adopt, revise, or reject every proposal. Review must inspect complete Lines, Prop text, public offline inputs, repository evidence, target connections, public claims, citations, and prohibited leakage. Semantic realism, connection value, evidence support, and label quality are review judgments, not deterministic checks. Adoption tooling exists; Objective-specific replay grading remains the named grading gap.

## Architecture and academic relevance

Muse, Serendipity, Librarian, and Provenance participate; Sculptor does not. The deterministic Memory & Policy Service owns account-scoped memory reads, application code owns source grants and release checks, and Exa supplies untrusted public evidence. The plan tests whether a proposal-only agent can combine minimized evidence without gaining account, write, or release authority. The briefing asks teams to demonstrate agent coordination, explainability and traceability, end-to-end tests, and the value of modular agents over a monolithic chatbot ([pp. 9, 11, and 13](../../../docs/submissions/aas-practice-module-briefing.pdf#page=9)); these paired Scenes would provide one concrete, auditable artifact for those questions.

> **Human decision required:** Approve the build target and target-state prompt, request a revision, or abandon this attempt. Do not approve execution until every prompt precondition and the public-evidence source gap are resolved.
