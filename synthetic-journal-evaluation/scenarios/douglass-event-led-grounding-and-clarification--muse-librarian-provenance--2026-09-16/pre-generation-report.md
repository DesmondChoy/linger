# Narrative of the Life of Frederick Douglass, an American Slave: event-led grounding and clarification

## Decision

Generation was approved on 2026-09-16 for one Scenario per registered book. On 2026-09-17, human review requested that grounded reflection use no memory. The revised design separates grounding from memory-supported spoiler inference. The book-specific outputs beside this report remain proposed Ground truth; this approval does not adopt labels or authorize replay.

The implementation is **sufficient** to execute and assess this complete plan after independent Ground truth adoption and replay authorization. Generation is approved. This is execution readiness, not a prediction that the model will pass. The evaluated outcome includes grounded release, correct event-derived reading permission, and spoiler-free clarification. Deterministic grades and human judgments of meaning must remain separate.

| Planned Scene | Target behavior | Status | Evidence |
|---|---|---|---|
| Grounded reflection without memory | Use the current Line’s explicit completed chapter to retrieve and quote permitted evidence and release a reviewed reflection. Exercises grounded book reflection. | runnable | `evals/synthetic_journals/book_contract.py`, `book_replay.py`; `tests/test_synthetic_book_contract.py`. |
| Event-led spoiler inference | Use an earlier memory and current reading events to infer a ceiling; constrain subsequent evidence and released claims. Exercises spoiler-boundary clarification. | runnable | `src/linger/orchestration/boundary.py:228–470`, `grounding.py:201–287`; `tests/test_boundary_inference.py`. |
| Personal comparison | Give a useful personal reflection without book routing, retrieval, or evidence claims. Exercises grounded book reflection. | runnable | `tests/test_librarian_route_e2e.py:525`; `evals/synthetic_journals/book_replay.py:939–946`. |
| Ambiguous event comparison | Ask a reviewed, spoiler-free clarification without granting a ceiling or retrieving response evidence. Exercises spoiler-boundary clarification. | runnable | `boundary.py:283–459`; `tests/test_boundary_observability.py:180`; `tests/test_synthetic_book_replay.py:769`. |

## Your selection

- **Grounded book reflection** (`grounded_book_reflection`): Librarian supplies evidence for quotations and factual claims; Muse stays grounded, Provenance verifies support, and personal reflection avoids unnecessary retrieval.
- **Spoiler-boundary clarification** (`spoiler_boundary_clarification`): Librarian matches remembered events against the book to infer progress; retrieval respects that boundary, and uncertainty leads to clarification.

## Target evaluation design

This [Scenario uses the canonical vocabulary](../../../docs/specification.md#721-canonical-vocabulary). Four separate Scenes keep grounded reflection independent of memory while preserving event-led spoiler inference and both comparisons.

| Term | Application |
|---|---|
| Objective | Exactly the two confirmed IDs, in the order above. Each requires a positive and comparison Scene. They use separate inputs and pairings. |
| Backstory | One corpus-backed history, one person, one evaluation account. Discover a currently enabled work whose narrative is covered by numbered main-text chapters. Inspect its complete current work and immutable version at generation time. |
| Prop | Two separately authored earlier source records. One supports spoiler inference; the other supports the genuinely ambiguous comparison. Each is active only in its designated Scene. Grounded and personal reflections receive none. No copied Backstory, stored chapter field, fabricated capture, or derived record. |
| Scene | Exactly four fresh-session Scenes, ordered grounded, personal, spoiler inference, ambiguous. Each remains a graded unit and has exactly one Objective. No preset applies: `run_configuration_ids` is empty. |
| Line | Exactly one natural conversational input per Scene. The grounded Line explicitly states completed chapter progress. Spoiler Lines use reading events without chapter coordinates. Reset and disabled capture are workflow state. No offline inputs. |
| Ground truth | Four separate proposals in `ground-truth.json`, one per Scene–Objective pair. Shared `book_scene_facts` owns scope, exact Prop/Line basis spans, and corpus excerpts for the three book Scenes. Proposals own typed `book_expectation`, pairings, expected and prohibited outcomes. They remain proposed until an independent human adopts them. |

`evals/synthetic_journals/models.py` defines `SyntheticBackstory` with nested Backstory and separate Props, Scenes, and Lines. `ProposedGroundTruth` hashes the exact Backstory file. Its book proposals prohibit generic `grounding`, duplicated evidence, and `prop_relevance`; authorized Prop IDs and basis spans express their source roles. `validate_scenario.py` remains unchanged; `book_contract.py` now resolves both registered corpus layouts against the same authoring structures.

## Current implementation and required work

**Observed.** The complete selected product path exists. `book_replay.py` executes production chat with isolated Scene stores, one evaluation account, fresh sessions, designated Props, and capture disabled. It observes private attempts and final release. Its endpoint matches these chapter-scoped Objectives; exact-passage permissions, later clarification answers, capture, and curation are outside this plan.

| Implementation appendix | Reconciled path or evidence |
|---|---|
| Grounded Scene | The current Line supplies book identity and explicit completed chapter progress. No Prop is seeded. Production routing validates that declaration, retrieves within its ceiling, and releases a grounded reflection through Provenance. |
| Spoiler-inference Scene | Memory & Policy seeds the designated Prop. `apps/backend/chat_turn.py:853–987` runs Provenance preflight and Muse. `routing.py:60–238` resolves identity; `boundary.py:228–470` privately searches the complete eligible chapter scope against separate Line and memory anchors. Application validation binds content-free support and a request-only ceiling. `grounding.py:201–287` retrieves within it and assesses support. `reflection.py:566–780,995–1104` reviews the full draft and checks evidence identity, claim spans, quotations, and scope before release. Released Line/response enter session history; inferred progress is not persisted. |
| Personal Scene | Preflight → Muse → Provenance → deterministic release validation → useful reflection and released history. No Prop, route, evidence lookup, reading permission, or durable write. |
| Ambiguous Scene | Same initial path; uncertainty, unsupported authorization, conflicting evidence, or invalid inference produces a typed clarification. No release-evidence retrieval occurs. After Provenance passes, application releases the validated question, records pending clarification and released history, and suppresses capture. |
| Shared short circuits | Emotional preflight skips Muse/Librarian; preflight failure fails closed. Empty or rejected evidence provides no claim authority. Provenance permits one revision with the same gated evidence context; rejection, failed repair, or deterministic failure ends in application safe decline. Failed turns do not become working conversation history; non-release restores prior reading state. These branches remain observable, not additional Objectives. |
| Reusable evaluation assets | `models.py`, `validate_scenario.py`, `book_contract.py`, `book_evidence.py`, `book_replay.py`, `book_semantics.py`, `adoption.py`, and the independent review skill. Compiler resolves exact corpus occurrences and derives the inferred ceiling from supporting chapters. |
| Fresh verification | `pytest -q` over `test_synthetic_book_contract.py`, `test_boundary_inference.py`, `test_boundary_observability.py`, `test_librarian_route_e2e.py`, and `test_synthetic_book_replay.py`: **80 passed, 6 subtests passed**. Controlled outputs establish orchestration and contracts; no live model or generated dataset was used. |
| Section-catalog support | On 2026-09-16, the user authorized the evaluator update. `book_evidence.py` now uses shared `load_units`/`read_unit` and production evidence construction. `book_contract.py` uses the actual main-narrative chapter maximum. Douglass chapters and Keller Part I are supported; prefaces, letters, and other parts remain excluded. Models and validator are unchanged. Eleven new regressions failed before the fix; all 73 focused checks passed after. The full backend suite passed 1,517 tests and 630 subtests across the initial run and five loopback-permission retries. |
| Separate Objective Scenes | On 2026-09-17, human review requested grounded reflection without memory. The compiler now accepts independent grounding and spoiler Scenes by removing its extra shared-Scene restriction. Per-Objective coverage and pairing checks remain. The new regression failed before the fix; all 79 focused contract, book-replay, and connection checks passed after it. Models, validator, catalog, and production runtime are unchanged. |
| Semantic limits | `book_replay.py:999–1017` checks forbidden evidence and literal disclosure. `book_semantics.py` can separately flag paraphrases; its optional model verdict is non-independent and never changes deterministic grades, as tested at `test_synthetic_book_replay.py:1027`. Human inspection remains necessary for semantic grounding and non-disclosure. |

**Proposed.** No capability, contract, adapter, or grading build-out is required for this design. Human evaluation must inspect all released text against adopted source facts, including paraphrases and unsupported personal wording.

**Assumed.** Generation can find suitable events in an intact enabled corpus with numbered main-text chapters. A failed corpus or contract check invalidates the prompt. Provider configuration is required only for separately authorized replay.

| History and work tracking | Readiness implication |
|---|---|
| HEAD `a7cbb8b` | Explorer UI reads saved evaluations without granting retrieval, release, or storage authority. |
| `4f088257da68` | Preserves reading context and validates evidence-selection boundaries. Linked `linger-g5gr` is unavailable locally; the inspected diff and tests establish the behavior independently. |
| `c31019ffe965` | Adds exact reader request planning, complete evidence support, per-memory inference assessments, and validated review repairs. |
| `61862d3caf79`; `d0ffab020f92` | Preserve reader-selected identity and pending clarification; bind chapter parsing to its declaration sentence. |
| `33fe2ffcfd07` | Separates current-Line and memory searches; records private tool attempts and actual released citations. |
| Closed `linger-lfh`, `linger-o0f`, `linger-yq1`, `linger-3sif`, `linger-ck1` | Event-led inference, canonical book contracts, independent adoption, and combined replay shipped. Earlier missing-path reports are obsolete. |
| Closed `linger-r1pa`, `linger-h4gl`, `linger-54nl`, `linger-y0kr`, `linger-rd16` | Historical failures and later successful replays establish feasibility, not current model reliability. |
| Open `linger-55r9`; in progress `linger-zba5`, `linger-ecxr` | Unsupported claim clauses, invented personal wording, and incomplete final-version live regression coverage remain known quality limits. They do not remove the execution or observation paths. No new provider calls are authorized here. |
| Open `linger-3yyi`, `linger-t1k` | Stale routing and replay-blocker statements are resolved by current `routing.py:70–73`, `test_librarian_routing.py:357,386`, and closed `linger-yq1`. Broader adversarial coverage remains outside this selection. |
| Dirty documentation/diagnostic | Librarian design/progress/README edits describe implemented planning and session fallback. Untracked Provenance claim-mapping diagnostic and test, plus its README, are component evidence only; no live semantic fix. `.beads/interactions.jsonl` is also dirty. HEAD reproduces production and scenario schemas, but the uncommitted resolver/compiler changes are required for section-based evidence and separate Objective Scenes. |

No unresolved material source contradiction remains for this plan. Known model errors remain failures to measure. Dataset assembly and freezing are separate unadopted stages, not execution gaps.

Snapshot: `main` at `a7cbb8baa3389a0fdf1a84c780eed6a899892065`, dirty, `2026-09-17T19:17:50+08:00`; SHA-256 prefixes: catalog `2bcd10711b606c5d`, specification `3ba7bf0b7a4eb6b5`, models `f71cc45e4343f968`, validator `5fbb380480c22831`, book compiler `eac10dc295429477`, book resolver `b8895fecba776757`, book replay `23adc6ad7dfe3ba5`, boundary `a2bbaadada0e9859`, registry `9a9f88e9a793104e`.

## Expected behavior and evaluation

The plan contains Lines only. These input descriptions are hypotheses, not generated content or exact response oracles.

| Representative input shape | Likely behavior | Success check |
|---|---|---|
| Explicit completed chapter, passage question, and personal context in one Line with no Prop | Retrieve the permitted passage, quote accurately, offer grounded reflection | Reading permission comes from the Line; quotation and citation resolve; no earlier memory is needed. |
| Natural account of reaching an event, tied to an earlier separately stored reading memory | Infer progress and bound evidence use | Correct ceiling and supporting Prop/corpus occurrence; no private later-story content reaches Muse or the released response. |
| Nearby personal uncertainty that makes sense without a book claim | Reflect helpfully without searching | No book route, evidence search, citation, or invented autobiographical fact. |
| Vague event reference with earlier memory that cannot uniquely authorize the requested progress | Ask for clarification without revealing candidate later events | No ceiling grant or response-evidence retrieval; released question matches validated clarification; literal and paraphrased forbidden facts remain absent. |

## Proposed generator prompt

The report is human-only. After explicit approval, supply only this detached prompt to the future generator.

```text
STATUS: Runnable after human approval

PRECONDITIONS
Do not run without explicit human approval to generate this design. Recheck the current checkout before writing. The adopted Backstory/Ground truth schemas and deterministic validator remain unchanged. The current resolver and compiler must support the complete design below, including separate Scenes for the two Objectives. The workflow must still support event-led progress inference from a prior memory and current reading events, followed by separately bounded evidence use and reviewed release. The grounded reflection uses a reader-confirmed chapter without memory. The separate spoiler-inference Scene must retain event-led inference from a prior memory; a reader-confirmed substitute does not satisfy that Scene.

An intact enabled work must provide a complete chapter-based narrative, uniquely localizable known events, genuinely ambiguous comparison material, exact quotable support, and a forbidden later fact. If any prerequisite fails, stop and identify it. Do not alter the design or schema to bypass a failure. Approval here does not authorize replay, Ground truth adoption, or additional model calls.

SCENARIO_DIRECTORY=synthetic-journal-evaluation/scenarios/douglass-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16

You have read-only access to the current checkout. Inspect the permitted paths at invocation time. You may write exactly two sibling outputs, SCENARIO_DIRECTORY/backstory.json and SCENARIO_DIRECTORY/ground-truth.json. Do not change the report, source code, corpus, policies, or validators. Do not read this report as generation input.

Permitted repository paths:
- data/corpus/ and the immutable source paths identified by the selected corpus registration, read solely to verify corpus identity, structure, events, and exact text.
- src/linger/corpus/units.py, src/linger/corpus/registry.py and its corpus definition modules, read solely to establish enabled identity, immutable revision, source integrity, and chapter structure.
- evals/synthetic_journals/models.py
- evals/synthetic_journals/validate_scenario.py
- evals/synthetic_journals/book_contract.py
- evals/synthetic_journals/book_evidence.py
Read the adopted authoring contracts and validation requirements. Do not inspect runtime agent prompts, replay results, judge instructions, other Scenario files, or raw catalog developer metadata. Do not select evaluator thresholds or rubrics.

Purpose:
Create a coherent personal reading history with four separate Scenes. Grounded reflection uses only a current Line that explicitly states completed chapter progress and requests a passage-based reflection and exact quotation. A personal comparison needs no book evidence. Separately, a prior memory and current events support spoiler-boundary inference, contrasted with genuinely ambiguous progress requiring clarification. Keep the personal reflection useful even if a book claim cannot safely be made.

Use these Objective IDs in this order:
["grounded_book_reflection", "spoiler_boundary_clarification"]
Set run_configuration_ids to an empty array. No capture, curation, or longitudinal-retrieval preset applies.

Discover the available work, title, author, immutable version, ordered structure, and evidence from the current corpus. Choose a work whose complete narrative lies within eligible numbered main-text chapters. Do not copy book facts from an earlier report or invent quotations, locations, or events. Inspect the complete work so that the proposed safe boundary and forbidden later fact are defensible. Keep later facts out of conversational inputs and Props.

Write backstory.json as SyntheticBackstory from models.py:
1. One Backstory, one person, one evaluation account, with plausible reading habits and personal context. The Backstory informs authoring only and never enters the evaluated application.
2. Exactly two separate Props in the person's own natural wording. Both describe earlier reading experiences. The first supplies relevant prior event knowledge for the spoiler-inference Scene; the second belongs to the ambiguous comparison and cannot uniquely justify the requested progress. Each source must make sense independently. Give each Prop an active lifecycle entry for only its designated Scene. Do not copy Backstory prose into Props. Do not create memory-capture outcomes, derived summaries, chapter-progress fields, or expected labels.
3. Exactly four ordered fresh-session Scenes, each with one Line:
   - First: grounded reflection, assigned only grounded_book_reflection, with no Props. The current Line explicitly names the book and the completed chapter, connects a passage to a personal question, and requests an exact quotation or examination of wording. It must make sense without any earlier memory.
   - Second: personal comparison, assigned only grounded_book_reflection, with no Props. Keep it close in personal theme while requiring no quotation, book fact, or factual lookup.
   - Third: event-led spoiler inference, assigned only spoiler_boundary_clarification and only the first Prop. Prior event knowledge and the current Line must support one safe boundary without chapter numbers or location coordinates in either input. Subsequent evidence and released claims must respect that inferred ceiling.
   - Fourth: ambiguous event comparison, assigned only spoiler_boundary_clarification and only the second Prop. Make uncertainty apparent from the supplied sources rather than hidden Backstory facts. Ask naturally about a book event while leaving insufficient authorized progress evidence for a unique ceiling.
4. Exactly four Lines, one per Scene with order 1. Every Line is conversational input belonging to this Backstory. Do not embed internal agent names, routes, policy instructions, expected answers, save controls, or grading labels. Chapter coordinates belong only in the grounded Line’s explicit reading declaration, never in Props or spoiler Lines. Use a natural book identity cue in each book-related Line and Prop. A question showing curiosity alone is not evidence that the reader reached the event.
5. Use distinct entity identifiers and contiguous Scene orders. Leave offline_inputs and source_setups empty. Fresh sessions, account scope, and disabled automatic capture are trusted workflow setup, not Line text. Runtime-created records are outcomes, never generated Props.

Write proposed Ground truth in the separate ground truth file, ground-truth.json, as ProposedGroundTruth. Set ground_truth_status to "proposed" and backstory_sha256 to the hash of the exact completed backstory.json bytes.

Create exactly three BookSceneFacts entries, for the first, third, and fourth Scenes:
- For the first, use ReaderConfirmedBookScope with current work/version and the chapter explicitly completed in the Line. Supply no inference basis spans or authorized Props. Its corpus evidence supports the requested quotation and contextual claims without relying on earlier memory.
- For the third, use LibrarianInferredBookScope with current work/version, its authorized Prop ID, and supporting corpus evidence IDs. Supply exact non-empty Unicode-code-point basis spans in both the Prop and Line. Resolve exact CorpusTextEvidence excerpts against the current chapter Markdown, including exact occurrence offsets. The compiler derives the safe ceiling from the supporting evidence chapters; do not invent a parallel ceiling field.
- Include permitted evidence at or before each known boundary. The spoiler-inference Scene must include at least one resolvable forbidden later fact. The grounded Scene must include the exact quotation its Line naturally requests.
- For the fourth, use ClarificationBookScope with current work/version and its authorized Prop. Include exact Prop and Line basis spans and resolvable forbidden later evidence. Do not invent a safe ceiling for unresolved progress.
- Do not attach book facts to the personal no-retrieval Scene.

Create exactly four GroundTruthProposal records, one per assigned Scene–Objective pair:
- First Scene, grounded_book_reflection: typed GroundedBookExpectation with retrieval "required", permitted_evidence_ids, and exact_quotation_evidence_ids resolving to that Scene's book facts.
- Third Scene, spoiler_boundary_clarification: typed SpoilerBoundaryBookExpectation identifying forbidden_later_evidence_ids from that Scene's book facts.
- Second Scene, grounded_book_reflection: retrieval "not_required", with no permitted or quotation evidence.
- Fourth Scene, spoiler_boundary_clarification: forbidden_later_evidence_ids and expectations for clarification without a granted ceiling, response-evidence retrieval, or spoiler disclosure.

In every proposal, supply source-grounded expected_outcomes and prohibited_outcomes. Keep evidence and inference basis spans owned by BookSceneFacts; leave proposal evidence, exact_spans, and prop_relevance empty. Do not supply generic grounding, capture, curation, surfacing, or connection expectations. Authorized Prop IDs and exact basis spans state the intended source use under this book contract.

Pair the first and second Scenes reciprocally for grounded_book_reflection. Match backstory_id, fresh_session, line_count, and empty prop_ids; differ on line_text. Pair the third and fourth reciprocally for spoiler_boundary_clarification. Match backstory_id, fresh_session, and line_count; differ on line_text and prop_ids. The paired Objectives must contrast required versus unnecessary retrieval and inference versus clarification respectively.

Expected outcomes must preserve accurate attribution, the correct inferred boundary, only authorized support, exact quotations, a useful personal comparison, and clarification without literal or paraphrased later facts. Identify the exact supporting and forbidden source occurrences. Keep these candidate labels separate from all runtime inputs. Do not grade recorded system behavior, impose exact response wording, claim independent review, or label your proposals adopted.

Validate the two files with the unchanged deterministic validator:
.venv/bin/python -m evals.synthetic_journals.validate_scenario SCENARIO_DIRECTORY/backstory.json SCENARIO_DIRECTORY/ground-truth.json

Correct authoring errors only within those two files. Stop on a missing capability, source, or incompatible contract; never change repository code or weaken the selected Objectives. Validation proves structural facts, references, exact spans, corpus integrity, pairings, and required counts, not semantic realism or label correctness. An independent human must adopt, revise, or reject every proposal before grading. Neither proposed nor adopted Ground truth may reach the evaluated application. Stop after producing and validating the two files.
```

## Ground truth lifecycle

The generator proposes four labels with exact Prop/Line spans and corpus occurrences. Code verifies hashes, identifiers, ordering, active lifecycle, complete proposal coverage, pairings, scope/evidence compatibility, and resolvable quotations. Book-specific source roles replace the relevance array forbidden by this contract.

An independent human uses `review-synthetic-ground-truth` to inspect every label, revise or reject weak candidates, and confirm only acceptable proposals. `adoption.py` binds all decisions to both exact file hashes; changes require renewed validation and adoption. Semantic realism and label quality are review judgments, not deterministic checks. After separately authorized replay, inspect every released claim and paraphrase; an automated pass alone is insufficient evidence of semantic success.

## Architecture and academic relevance

Muse, Librarian, and Provenance participate; Sculptor and Serendipity do not. Deterministic memory policy, corpus retrieval, request scope, session state, and release validation enforce the boundary: private access to the complete book does not authorize disclosure.

The briefing asks how agent coordination and traceability can be demonstrated, and identifies architecture and testing artifacts as useful evidence (pp. 9, 11, 13 of [the complete briefing](../../../docs/submissions/aas-practice-module-briefing.pdf)). This paired demonstration connects a private inference decision to bounded retrieval and reviewed release, providing concrete material for those artifacts without asserting an additional academic requirement.

> **Human decision required:** Independently review the generated proposals before adopting any labels. Generation approval does not authorize adoption or replay.
