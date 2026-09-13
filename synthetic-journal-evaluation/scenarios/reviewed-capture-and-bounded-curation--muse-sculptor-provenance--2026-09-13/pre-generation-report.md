# Reviewed capture and bounded curation

## Decision

The current implementation is **sufficient** for this complete selection. Combined validation and replay support all 16 planned Scenes. Repository completion supplies evaluator-owned curation fields before independent review. The prompt is ready for separate human approval; no Scenario data has been generated. Capture evaluates nomination through storage. Curation evaluates proposal quality and source preservation; its later application is architectural context.

Statuses below describe execution support for this combined Scenario, not predicted model performance.

| Required Scene set | Target behavior | Status | Evidence |
|---|---|---|---|
| One durable capture Scene | Exact nomination, independent approval, one unchanged-source write | runnable | `capture_curation_replay.py:130` uses the production capture path; `tests/test_synthetic_capture_curation_replay.py:116` proves exact capture and original adoption identity. |
| Ten low-signal capture Scenes | Useful ordinary replies without nomination or storage | runnable | The same sixteen-Scene test observes eleven fresh capture sessions, one durable record, and per-Scene grades. `tests/test_chat_capture.py:228` covers no nomination. |
| Exact-duplicate curation Scene | Link two identical originals without rewriting either | runnable | The combined test calls production `propose_curation` with only designated Props and verifies source hashes; `curation_replay.py:392` records the proposal. |
| Paraphrased-duplicate curation Scene | Link two differently worded versions of the same fact | runnable | `evals/sculptor/harness.py:40` requires this behavior; combined replay tests exercise all five curation outcomes. |
| Evolving-fact curation Scene | Summarize three refining records; exclude one unrelated record | runnable | Existing derived-summary contract and source checks; `complete_curation_ground_truth.py` supplies repository-owned policy before strict validation. |
| Related-facts curation Scene | Group three related but distinct records; exclude one distractor | runnable | Existing topic-group contract and source checks; completion supplies semantic-review policy while candidate relationships remain independently reviewed. |
| Superficial-overlap curation Scene | Leave three unrelated records ungrouped | runnable | Combined replay covers no proposal and unchanged sources; `tests/test_curation_application.py:215` proves the downstream no-review/no-write branch. |

## Your selection

- **Reviewed automatic memory capture** (`reviewed_automatic_memory_capture`): Muse may nominate a reflection; Provenance and Memory & Policy store approved durable content and leave low-signal content unstored.
- **Bounded memory curation** (`bounded_memory_curation`): Sculptor proposes links, groups, or summaries from supplied memories while preserving originals and leaving unrelated records alone.

## Target evaluation design

This [Scenario uses the canonical vocabulary](../../../docs/specification.md#721-canonical-vocabulary): one memory-only Backstory, one person, and one evaluation account. Corpus inspection adds no value here.

| Term | Application to this plan |
|---|---|
| Objective | Preserve both selected IDs. Capture has two catalog minimums; curation has four. The adopted curation validator additionally requires paraphrased duplication, producing five curation Scenes. |
| Backstory | One coherent personal history in `SyntheticBackstory.backstory`; identity and context remain outside runtime. Root collections contain separate Props, Scenes, Lines, and empty `offline_inputs`/`source_setups`. Set `run_configuration_ids` to `["reviewed-automatic-memory-capture-10-to-1"]`. |
| Prop | Fifteen separately authored earlier records: 2 exact duplicates, 2 paraphrases, 4 evolving-fact/noise records, 4 related-fact/distractor records, and 3 superficial-overlap records. Each has matching Backstory/person/account IDs and an active lifecycle entry for its designated curation Scene. No capture Scene receives Props. Runtime captures and derived records are outcomes, never Props. These counts are this proposed design, not universal minimums. |
| Scene | Sixteen ordered graded units: eleven fresh-session capture Scenes, followed by five isolated Props-only curation Scenes. Curation uses already supplied earlier records; it does not depend on successful capture. Each Scene has only its relevant Objective ID. Each curation input contains 2–12 active records. |
| Line | Eleven natural inputs, exactly one per capture Scene, with order 1. The preset requires one durable candidate and ten varied low-signal inputs. Capture enablement and session reset are trusted workflow state. Curation has no Lines and no `OfflineInput` objects; its Props are its offline input. |
| Ground truth | Separate `ProposedGroundTruth` binds exact `backstory.json` bytes by SHA-256 and contains sixteen Scene/Objective proposals. Capture uses typed nomination spans and review decisions; curation uses typed actions, source identifiers, Prop evidence, and exact spans. Proposed labels are candidates; only independent human adoption makes them grading authority. Curation forbids retrieval `prop_relevance` labels; its source sets and evidence express intended use/non-use. |

Use the unchanged scenario contracts in [models.py](../../../evals/synthetic_journals/models.py). The updated [validate_scenario.py](../../../evals/synthetic_journals/validate_scenario.py) accepts this combination and enforces capture isolation at Scene scope. Repository code completes evaluator-owned curation fields before strict validation and independent review.

## Current implementation and required work

**Observed.** The following appendix distinguishes runtime paths, selected evaluation endpoints, and completed implementation work.

| Area | Reconciled evidence and consequence |
|---|---|
| Capture path and terminal outcome | `run_chat_turn` → no-tool Provenance preflight → Muse nomination → independent response/capture review → exact-span binding → deterministic release and `MemoryPolicyService.save_automatic` → reply plus save notice only for a committed record. One revision is allowed. No nomination creates no write; capture veto permits a safe reply. Invalid binding, policy refusal, conflicts, or unavailable storage do not commit. Emotional preflight skips Muse and suppresses capture; safe decline/clarification suppress eligible capture. See `apps/backend/chat_turn.py:489–585,792–928,1193–1204`, `src/linger/orchestration/capture.py:24`, specification §§4.1–4.2.2. |
| Capture evaluation endpoint | `evals/synthetic_journals/replay.py:420–516,578–658` observes nomination, review, binding, release, stored text/count, earlier-record hashes, and a policy-level idempotency retry. Normal releases with approval, veto, or no nomination are supported. Intended safe-decline cases remain outside this runner, while `tests/test_chat_capture.py:393` covers suppression. The planned inputs expect ordinary release; an actual decline fails the intended Scene, even if storage suppression is safe. Policy retry evidence does not establish server-owned HTTP retry identity. |
| Curation path and terminal outcome | `src/linger/orchestration/curation.py:207–272` resolves immutable account-scoped originals, calls Sculptor, and verifies preservation. No proposal ends without review/write. Otherwise the application hashes account, state, proposal, and source snapshots; separate Provenance review must allow that exact digest. Revise/reject/unbound verdicts stop. Memory & Policy rechecks freshness, scope, state, and idempotency, appends and verifies an audit event, and materializes the retrieval view (`src/linger/services/memory.py:198–308`). Originals remain unchanged. Chat does not initiate this callable loop. |
| Curation evaluation endpoint | `curation_replay.py:276–281,392–432` calls production `propose_curation`, records its response, and checks source hashes and proposal hard gates. Generated summaries/topic labels still need semantic review. This intentionally ends before curation Provenance review, application, audit, and retrieval; closed `linger-jra` explicitly preserves that boundary. Those later stages are not selected evaluation gaps. |
| Combined validation | `validate_scenario.py:729–751` applies capture restrictions to capture Scenes, allowing the separate curation Props. Capture count, fresh-session, one-Line, no-Prop, and no-offline-input checks remain enforced. The existing curation validator requires all five behaviors and their active source records. `tests/test_synthetic_journal_scenario.py:168` covers forbidden capture inputs. |
| Combined replay and review handoff | `capture_curation_replay.py` dispatches the original ordered Scenes to the existing capture and curation handlers. It preserves the Scenario hash, adoption identity, IDs, account scope, and per-Objective grading. Capture uses a temporary account store; curation sees only its designated Props. `replay_support.py` and the review skill register this exact combination. No single-Objective replacement files or capture-to-curation dependency are introduced. `tests/test_synthetic_capture_curation_replay.py:116,276` verifies sixteen ordered observations, both Objective orders, interleaving, retained capture state, immutable designated Props, and one native evaluation. |
| Curation authoring authority | The catalog's Ground truth lifecycle assigns evaluator-owned fields to `complete_curation_ground_truth.py`. The generator omits `max_summary_words` and `semantic_review` from action objects. The command supplies repository policy in the unchanged contract, fully validates it, then atomically replaces proposed Ground truth. It refuses supplied fields, repeat completion, invalid input, and an existing `ground-truth-adoption.json` sidecar. `tests/test_curation_ground_truth_completion.py:37–161` covers label preservation and refusal without changes. |
| Tracker reconciliation | Closed `linger-gmr.9` matches current blank-span rejection tests. Open `linger-gmr.8` still matches client `turn_id` becoming capture source identity; `linger-6tt` and nomination-variance issue `linger-n4h` remain open. These are controlled-run limitations, not evidence that normal capture is missing. Open `linger-a4u.4` gates captured-record reuse, which this Prop-only curation design does not attempt. Closed `linger-a4u.2`, `linger-a4u.5`, and `linger-3ry` establish proposal replay, reviewed application, and earlier independent adoption respectively. In-progress `linger-a4u.1` retains semantic calibration work; historical adoption does not approve this Scenario. |
| Relevant commit diffs inspected | HEAD `6d0623a` fixes veto grading so rejected captures require no writes or retry; `d2bce1d` renames scenario APIs; `1fb2f98` adds evaluation-link emission; `d2f8f63` removes manual prompt revision labels; `d0ce6b7` consolidates reusable role Agents and application-selected skills; `f4db8d0` establishes reviewed curation application. The current uncommitted `linger-r9oc` implementation adds combined validation and dispatch plus repository-owned completion. The selected Objective text remains unchanged; catalog edits describe workflow support and field ownership. |
| Fresh verification | Full repository suite: `.venv/bin/python -m pytest -q` — **1,216 passed, 578 subtests passed**. Regression coverage includes all sixteen Scenes, source and adoption identity, completion before human review, and guided-run reporting of failures in either Objective. Combined tests inject model responses while executing production chat and curation boundaries; they do not establish live-model quality. Quality review and `git diff --check` passed. Both updated workflow skills passed `quick_validate.py`. Ruff and MyPy are unavailable in this environment. |

**Proposed.** Approve this target design and detached prompt before generation. No further build-out or product-triggered capture-to-curation integration is required for this selection.

**Assumed.** Controlled execution supplies one authenticated evaluation account, capture enablement, isolated chats, and designated earlier Props. Capture output is not authorized upstream curation evidence.

Snapshot: `main`, HEAD `6d0623ac7b89abbf0d5d353399d2b416afea7d97`; implementation is uncommitted under `linger-r9oc`, alongside the pre-existing dirty `.beads/interactions.jsonl`. HEAD alone does not reproduce the inspected validation, completion, or combined replay. Local timestamp: `2026-09-13T21:32:20.714015+08:00`. Material-file fingerprint: `69e7f090f4a5642259832497053c282d6bec1092bfd4d98167c68d661a8f56d8` (SHA-256 of ordered SHA-256/path lines for catalog, preset, specification, chat turn, scenario models/validator/replays/completion/registry/adoption, capture/curation orchestration, memory service, Sculptor harness, new combined/completion tests, review/guided-run/validator regression tests, the two updated workflow skills, and the synthetic-journals README).

## Expected behavior and evaluation

The plan contains conversational Lines and Props-only offline curation. These input descriptions and response behaviors are hypotheses, not generated data or exact response oracles.

| Representative input type | Likely behavior and plain-language success check |
|---|---|
| Durable preference/reflection | A useful reply accompanies storage of exactly the approved words, once. |
| Temporary logistics, filler, short-lived observation, routine update | A useful reply produces no nomination, save notice, or memory write across all ten comparisons. |
| Exact and paraphrased repetition | Sculptor proposes duplicate links using only the two supplied originals; both remain unchanged. |
| Evolving fact with unrelated noise | A supported summary preserves the refinement and excludes the noise; no unsupported personal claim appears. |
| Related distinct facts with a distractor | A topic group includes only related sources and preserves their distinct meanings. |
| Superficial overlap | No proposal; no original changes. Shared wording alone does not establish a relationship. |

## Proposed generator prompt

```text
STATUS: Runnable after human approval

PRECONDITIONS:
This prompt does not authorize generation. Continue only after the human separately approves this target design and prompt for generation.
Verify that the current checkout contains the adopted combined capture/curation validator, replay registration, and curation Ground truth completion command. Confirm that both output paths below are absent and no ground-truth-adoption.json exists beside them. If these conditions fail, report the exact failure and stop.
Use the selected Objectives and run configuration unchanged. Do not split this into separate Backstories, invent fields, fabricate observed records, or bypass validation.

SCENARIO_DIRECTORY=synthetic-journal-evaluation/scenarios/reviewed-capture-and-bounded-curation--muse-sculptor-provenance--2026-09-13
Reserve exactly two sibling output paths:
SCENARIO_DIRECTORY/backstory.json
SCENARIO_DIRECTORY/ground-truth.json

You have read-only access to the current checkout, except those two authorized outputs. Inspect the permitted sources at invocation time. Use current contracts unchanged; stop if they cannot represent the complete design. Do not read this report or historical scenarios as generation inputs.

Permitted repository sources:
- evals/synthetic_journals/models.py
- evals/synthetic_journals/validate_scenario.py
- synthetic-journal-evaluation/generation-presets/reviewed-automatic-memory-capture-10-to-1.json
- src/linger/agents/muse/models.py and its current capture policy/instructions under src/linger/agents/muse/
- src/linger/agents/sculptor/models.py and its source-preservation instructions under src/linger/agents/sculptor/skills/memory-curation/
- src/linger/orchestration/capture.py and src/linger/services/memory.py for exact-span and account/lifecycle rules
- docs/specification.md Sections 5.5, 6.3, and 7.2.1 for capture policy, source authority, and canonical vocabulary
Follow only schema imports needed to understand data shape. Do not extract evaluator thresholds, example answer keys, or judge rubrics from imported modules. Do not read complete_curation_ground_truth.py or its evaluator policy; execute its command as directed below without exposing its contents. Do not inspect credentials, unrelated personal material, or data/corpus/. This design is memory-only.

Selected Objective IDs, in order:
reviewed_automatic_memory_capture
bounded_memory_curation

Purpose:
Create natural durable and low-signal conversation material, plus an accumulated personal history containing repeated facts, meaningful refinements, related distinct facts, and misleading thematic overlap. Keep every source independently understandable. The design tests selective storage and source-preserving curation proposals.

Write backstory.json using SyntheticBackstory:
- One Backstory for one person and one evaluation account. Write plausible authoring context; it never reaches the running system. Do not stereotype or make sensitive traits define the person.
- Set root objective_ids to the ordered selection above and run_configuration_ids to ["reviewed-automatic-memory-capture-10-to-1"]. The 1:10 mix is this run's capture Scene configuration, not a general Objective minimum.
- Create exactly sixteen Scenes with unique identifiers and contiguous order: eleven capture Scenes, then five isolated curation Scenes. Each Scene selects only its own Objective. All belong to the same Backstory.
- Each capture Scene starts a fresh session, has exactly one natural Line at order 1, and receives no Props. Exactly one Scene contains a durable reflection, preference, intention, or incident useful beyond the immediate chat. Ten contain diverse temporary logistics, conversational filler, short-lived observations, and routine updates. Write eleven Lines total. Do not reveal the intended candidate or its span in runtime input. Do not use save commands, internal agent names, policy labels, expected outcomes, or grading instructions.
- Capture enablement is server-controlled evaluation state, and resets are workflow controls; neither is a Line. Captured records are observed outcomes, not generated Props. Do not copy a complete Line into a Prop.
- Create fifteen separate earlier Props, positioned before their designated curation Scenes: two exact duplicates; two independently worded duplicates; three records refining one evolving fact plus one unrelated noise record; three related but distinct facts plus one distractor; and three records sharing superficial wording but lacking a useful relationship.
- These five curation Scenes each receive only their designated 2, 2, 4, 4, or 3 active same-account Props. Supply matching Prop lifecycle entries. Keep every original independently understandable. They have no Lines or OfflineInput objects. Keep offline_inputs and source_setups empty throughout.
- The extra paraphrased-duplicate Scene satisfies the existing five-behavior curation contract. Curation starts only after its earlier Props exist. It does not consume captured records or pretend that a proposed summary was stored.

Write proposed Ground truth in the separate ground truth file, ground-truth.json, using the existing ProposedGroundTruth structure. Omit only the evaluator-owned curation action fields specified below; repository completion supplies them before full validation:
- Set ground_truth_status to proposed and backstory_sha256 to SHA-256 of the final exact backstory.json bytes. Provide one uniquely identified GroundTruthProposal per Scene/Objective pair: sixteen proposals total.
- For capture, use CaptureExpectation. Propose one capture_candidate bound to an exact nonblank Unicode-code-point slice of that Scene's Line, with allow_capture. Propose ten no_candidate nominations with no_candidate decisions. Keep generic exact_spans empty for capture; the nominated span belongs only in capture.nomination.span. Describe expected normal release, exact reviewed storage or no write, and prohibited changes separately in expected_outcomes/prohibited_outcomes.
- Pair the durable Scene with a nearby low-signal comparison using supported ScenePairing fields: same Backstory, fresh-session status, empty Prop set, and Line count; different Line text. Do not claim all other content is identical or require identical wording across all ten comparisons.
- For curation, use the existing typed CurationExpectation: exact_duplicate and paraphrased_duplicate propose duplicate links; noisy_memory_summary proposes a supported derived summary from only the three refining sources; related_topic_group proposes a group from only the three related distinct sources; superficial_similarity_no_change proposes no curation.
- Cite every curation Scene Prop exactly once as Prop evidence, including excluded noise. Provide exact Prop spans supporting relationships and showing why excluded records do not belong. Restrict proposed action source identifiers to the justified supplied subset. Use expected_outcomes/prohibited_outcomes to explain source-grounded candidate meaning and unsupported claims. Omit max_summary_words and semantic_review from every curation action object, including null values. Do not choose a threshold or author a judge rubric. The repository completion command supplies its policy without changing your candidate labels.
- Do not add capture or prop_relevance labels to curation proposals. Curation's permitted sources, evidence, and expected/prohibited outcomes cover use and non-use. There is no longitudinal retrieval Objective or retrieval mix in this selection.
- Keep curation expectations at bounded proposal quality, supplied-source use, no unsupported claims, and preservation of every original. Do not add downstream curation review, application, audit, tombstone, restoration, or retrieval expectations. Do not create runtime records or invent outcome identifiers.

The generator neither grades recorded behavior nor adopts its labels. Do not receive raw composition, prompt_inputs, evaluation_metadata, component routes, evaluator thresholds, or judge rubrics. Neither the Backstory context nor proposed/adopted Ground truth may enter the system under evaluation.

After separate human authorization, write both JSON files with those evaluator-owned fields omitted. Run completion once before the normal validator:
.venv/bin/python -m evals.synthetic_journals.complete_curation_ground_truth SCENARIO_DIRECTORY/backstory.json SCENARIO_DIRECTORY/ground-truth.json

Completion validates the full completed contract and Scenario before atomically rewriting ground-truth.json. If completion fails, correct only the reported authoring error and retry after confirming it made no rewrite. Do not supply the omitted fields yourself. Once completion succeeds, do not rerun it or read the completed evaluator settings. Run:
.venv/bin/python -m evals.synthetic_journals.validate_scenario SCENARIO_DIRECTORY/backstory.json SCENARIO_DIRECTORY/ground-truth.json

Stop on any validation or authority conflict after completion. Do not remove fields to force a repeated completion or modify a file beside an adoption record. Validation checks schema, exact hashing, references, span resolution, ordering, permitted evidence, declared Scene differences, source coverage, lifecycle state, and run-configuration counts. It does not establish semantic realism, label quality, adoption, or recorded-system performance. Report the two paths and validation result, then stop for independent human review. Do not generate adoption records, replay data, frozen releases, or additional Scenarios.
```

## Ground truth lifecycle

The generator proposes labels and exact source spans while omitting evaluator-owned curation fields. Repository completion supplies its policy and validates the unchanged full contract before an atomic write. The standard validator then checks objective facts. Wrong hashes, unresolved references, invalid ordering/spans, missing evidence, false pairings, or wrong configuration counts fail validation. Curation evidence covers every supplied Prop; retrieval relevance judgments are inapplicable here.

The independent human developer uses the existing review skill to adopt, revise, or reject every label. Revisions need fresh validation and review. `adoption.py` binds complete approval to both files' exact hashes. Semantic realism, durability, relationship correctness, and label quality are review judgments, not deterministic checks. Repository code owns grading fields. After human adoption, the registered combined runner can replay this exact selection through its separate component endpoints. Neither proposed nor adopted Ground truth reaches runtime.

## Architecture and academic relevance

Muse, Sculptor, and Provenance participate across the selected evaluation paths; Librarian and Serendipity do not. Memory & Policy, session state, exact-span binding, and the evaluators provide deterministic controls. Curation's separate application-review path is context only.

This plan tests whether agents can propose useful memory changes while application code retains storage authority. It can supply traceable demonstration and testing evidence for the briefing's modular-agent questions and expected architecture, agent-design, and evaluation artifacts ([briefing](../../../docs/submissions/aas-practice-module-briefing.pdf), PDF pages 9 and 11). It does not establish human benefit or deployment readiness.

> [!IMPORTANT]
> **Human decision required:** Approve the target design and prompt for generation, request revision, or abandon this plan. Generation remains separately authorized; replay follows independent Ground truth adoption through the review skill.
