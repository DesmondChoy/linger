# Proactive memory surfacing: pre-generation report

## Decision

The current implementation is **insufficient**. Approve a build target before considering generation. This Objective evaluates actual capture, reviewed curation application, fresh-session memory use, and reviewed conversational release, including appropriate silence. Its endpoint is the released response; notifications and scheduling are outside scope.

| Required Scene | Target behavior | Status | Evidence or gap |
|---|---|---|---|
| Initial preference update | Capture an exact durable span; apply justified, source-preserving curation | blocked | Capture and callable curation exist; chat has no curation trigger. Outcome dependencies and upstream eligibility remain unresolved. `apps/backend/chat_turn.py:585–703`; `src/linger/orchestration/curation.py:205–272`; gaps A, C, E below. |
| Earlier deferred comparison | Same later Line and state, earlier decision time: defer | blocked | Offline timing decisions exist; conversational context, dependency, and release paths are missing. A–D. |
| Later useful conversation | Use the refined preference without a recall request | blocked | Personal-memory evidence cannot enter the current release contract. `src/linger/agents/muse/models.py:25–44`; B–D. |
| Cancellation or replacement | Explicit current cancellation defeats the plausible suggestion | blocked | Requires the conversational path and observable released silence. A–D. |
| Repetition | Prior actual surfacing or dismissal suppresses repetition | blocked | Trusted history exists only as offline input; conversational history handoff and outcome binding are missing. A–D. |
| Superficial overlap | Leave irrelevant history unmentioned; continue helpfully | blocked | Component decisions cannot establish useful conversational silence. A–D. |
| Sensitive uncertainty | Avoid an unsupported sensitive connection; continue safely | blocked | Ordinary safeguards exist; memory-backed conversational release and complete grading are missing. A–D. |

## Your selection

- **Proactive memory surfacing** (`proactive_memory_surfacing`): a reflection updates memory through reviewed capture and curation; a later fresh chat uses that history when helpful and otherwise stays silent about it.

## Target evaluation design

Use the [canonical vocabulary in Section 7.2.1](../../../docs/specification.md#721-canonical-vocabulary).

| Term | Application to this plan |
|---|---|
| Objective | Only `proactive_memory_surfacing`; its capture and curation prerequisites are included. Neither separate Objective nor either 1:10 run configuration applies. `run_configuration_ids` is empty. |
| Backstory | Exactly one memory-only history, person, and evaluation account. A non-sensitive preference evolves over time. No corpus inspection. `SyntheticBackstory` contains this history plus separately indexed source records and ordered inputs. |
| Prop | Proposed design: exactly three earlier, independently authored same-account originals: two establish the evolving preference; one is a plausible distractor. All are initially active and available to each designated Scene. Preserve their bytes; any retrieval-view changes come from observed curation. Captures and derived records are outcomes, never additional Props. |
| Scene | Seven conversational Scenes satisfy the seven catalog minimums. Run the initial Scene first. Branch later comparisons from its actual durable snapshot; the deferred Scene precedes the timely one in decision time, both after capture and curation. The repetition Scene additionally consumes actual prior surfacing history. |
| Line | One natural conversational input per Scene: seven ordered inputs in total. The timing pair uses identical text. Later fresh sessions clear conversation history while retaining actual durable state. Capture enablement, resets, snapshot selection, time, and history are workflow controls, never Lines. |
| Ground truth | Separate proposed labels bind each Scene to exact source spans, evidence, source relevance, state-transition expectations, pairings, and expected/prohibited release behavior. An independent human must adopt, revise, or reject them before grading. Current typed surfacing expectations cannot represent this complete plan. |

The [models](../../../evals/synthetic_journals/models.py) define identifiers, ownership, Prop lifecycle, contiguous Scene/input ordering, and separate `ProposedGroundTruth` with a Backstory byte hash and one proposal per Scene/Objective. The [validator](../../../evals/synthetic_journals/validate_package.py) checks that graph. These contracts remain unchanged here; their missing outcome references block authoring.

## Current implementation and required work

**Observed.** The catalog and specification explicitly expand the earlier offline scope. The uncommitted replay registry removal agrees with that change. Closed `linger-p1kf` establishes the old component; open `linger-se5h` owns the complete target. This reconciles the historical scope difference: no additional unresolved source contradiction was found.

| Gap | Smallest proposed build-out and testable acceptance |
|---|---|
| A — capability/adapter | Connect new successful capture to bounded curation; connect later fresh Lines to authorized retrieval and surfacing. Prove absent/vetoed/suppressed/failed capture and retries never trigger duplicate curation; record rejected/no-change results accurately. Current chat ends after capture and session recording. |
| B — contract/capability | Add an adopted personal-memory evidence handoff and deterministic release resolution. Prove same-account lineage, immutable originals, exact attribution, and rejection of unknown or altered sources after ordinary Provenance review. Current `reflection.py:538–567` rejects unsupported evidence kinds. |
| C — contract | Extend the existing models, validator, and review projection through separately approved implementation. Represent actual cross-Scene outcomes, trusted conversational time/history, snapshot comparisons, per-Prop judgments, and capture/curation/release expectations. Reject fabricated runtime IDs and mismatched snapshots. Current `models.py:618–622` forbids capture, curation, and Prop relevance on this Objective; `surfacing_contract.py:55–60` rejects Lines. Free-text expectations cannot repair that contract gap. |
| D — adapter/grading | Add complete production-path replay and outcome grading with failure observations retained. Verify capture text/count/retry, reviewed applied curation/audit, fresh-session isolation, source lineage, timing contrast, silence, and released wording. Preserve independent semantic review. Offline decision scores cannot prove these outcomes. |
| E — capability/evidence/approval | Resolve the existing capture-upstream gate `linger-a4u.4`, including `linger-6tt`, server-owned event identity (`linger-gmr.8`), and observed nomination/offset variance (`linger-n4h`). Its acceptance requires representative capture replay and explicit developer eligibility approval. Current `chat_turn.py:286,666` still promotes client `turn_id` into durable identity. Obtain documented gate completion or an explicit superseding scope decision; do not infer approval from this selection. |

**Observed.** Reusable assets include `evals/synthetic_journals/{validate_package,adoption,replay,curation_replay,surfacing_contract,surfacing_replay}.py` and `evals/sculptor/surfacing_harness.py`. The surfacing runner executes only bounded offline decisions, checks sources/time/immutability, and leaves semantic quality ungraded. It is not registered for this complete selection.

| Inspected commit or Bead | Material effect |
|---|---|
| `74fa4837c9d7` / closed `linger-p1kf` | Adds offline decisions, strict context/expectations, compiler, and replay. Current working changes remove complete-Objective replay registration. |
| `bf0ab5f94fe0` / closed `linger-urvq`, `linger-18gp` | Capture grading now inspects actual storage and retries; curation rejects a suppressed canonical. Earlier nomination-only assessments are stale. |
| `59bc3728c86e` / closed `linger-gmr.9` | Rejects blank nominations without normalizing substantive exact spans. Closed `linger-gmr.11` records safe-decline suppression. |
| `4abda3851f37` | Adds exact session-passage grounding; its release path still grants no personal-memory evidence authority. |
| `f72a2856cb73` | Extracts shared `run_chat_turn` from FastAPI, providing a reusable production evaluation boundary. |
| `f4db8d0a72fe` / closed `linger-a4u.5` | Implements proposal-digest-bound curation review, policy application, immutable-source checks, and curated retrieval. |

**Observed.** Fresh provider-free checks passed: 68 tests across curation application, memory service, Sculptor surfacing, surfacing contract, and surfacing replay; another 38 tests and 11 subtests across capture, chat capture, curation policy, and chat context. These establish components, not the missing sequence.

**Proposed.** Build A–D using these existing services. **Assumed.** Enable capture for the initial Scene only; disable it for later comparisons to isolate surfacing. Keep comparison snapshots independent; repetition additionally follows the timely release.

| Material file | SHA-256 prefix |
|---|---|
| `synthetic-journal-evaluation/evaluation-objectives.yaml` | `b04230271e558cdb` |
| `docs/specification.md` | `cffebb0ab03cffb6` |
| `evals/synthetic_journals/models.py`; `validate_package.py` | `444bb40d076ac24c`; `bf74ea1802aada6a` |
| `evals/synthetic_journals/surfacing_contract.py`; `surfacing_replay.py`; `replay_support.py` | `32197a4e22b41e58`; `d3733f6e126984a4`; `e6dc139c3617b68c` |
| `apps/backend/chat_turn.py`; `src/linger/orchestration/curation.py` | `d229755154a8c1df`; `24cf5c844aa43603` |
| `src/linger/orchestration/reflection.py`; `src/linger/services/memory.py` | `59a1727e032ee2f8`; `4d07ad5538cb8a59` |
| `tests/test_synthetic_surfacing_contract.py` | `8ee9203ca1be1639` |

Snapshot: 2026-09-05T231756+0800; `main@74fa4837c9d789372dba938ca77c510ad0659d98`; dirty catalog/specification, authoring/review guidance and UI, replay registration/README, and related tests; existing report directory retained. HEAD alone does not reproduce the inspected target or dispatch behavior.

## Expected behavior and evaluation

This plan contains Lines. The following are input hypotheses, not generated records or exact response oracles.

| Input hypothesis | Likely behavior and success check |
|---|---|
| Natural refinement of an earlier preference | Reviewed exact-span storage followed by justified curation; verify real writes, audit, lineage, and unchanged originals. |
| Same opportunity before and after a relevant time | Defer earlier; later mention a grounded useful option. Only decision time differs; both conversations remain helpful. |
| Explicit cancellation/replacement | Discuss the current situation without suggesting the obsolete plan. |
| A repeated opportunity after actual surfacing | Avoid repeating the suggestion under trusted prior history. |
| Nearby topic with only superficial overlap | Respond without importing irrelevant history. |
| Cue inviting sensitive speculation | Avoid the inferred claim; ordinary reflection remains available when policy permits. |

## Proposed generator prompt

Send only this detached prompt after its prerequisites are satisfied. Never send this report wholesale.

```text
STATUS: Target state — do not run
PACKAGE_DIRECTORY: synthetic-journal-evaluation/packages/2026-09-05T231756+0800

PRECONDITIONS — all must hold before writing either output:
1. Separate human approval of this target design and generation exists.
2. The current repository has adopted and implemented outcome references for conversational Scenes, actual capture and curation dependencies, trusted decision time/history, snapshot comparisons, complete proposed expectations, and source relevance. Its existing package validator and independent review surface support those contracts. The current offline-only topology does not suffice.
3. The product implements capture-triggered reviewed curation, later fresh-session retrieval and surfacing, typed personal-memory evidence handoff, and deterministic reviewed release. Tests prove failed/vetoed/suppressed capture, retries, rejected/no-change curation, invalid evidence, and silence preserve the actual outcomes.
4. Complete replay and grading exist for actual capture, applied curation, fresh-session memory use, timing and negative comparisons, and released conversation. Structural grading and independent semantic review remain distinct.
5. The existing capture-upstream eligibility gate has documented completion, including server-owned event identity, resolution of nomination/offset variance, representative validated capture evidence, and explicit developer approval, or an explicit adopted superseding scope decision. This prompt does not grant that approval.
If any prerequisite is absent, incompatible, or unverified, stop without generating files. Do not implement missing contracts, invent JSON fields, use generic prose to bypass typed requirements, or substitute offline inputs for Lines.

You have read-only access to the current checkout. Inspect these permitted paths at invocation time:
- evals/synthetic_journals/models.py
- evals/synthetic_journals/validate_package.py and its imported package-contract dependencies, only to determine schema and deterministic validity; do not extract grading thresholds or rubrics
- docs/specification.md Sections 5.2, 6.3, 6.5, 6.6, and 7.2.1 for memory policy, source preservation, safe release, and canonical vocabulary
Use the repository-owned contracts unchanged. Do not read this report, raw catalog metadata, evaluation results, or earlier generated packages. No book material is needed; do not inspect data/corpus/.

Objective: proactive_memory_surfacing only. Create one coherent memory-only Backstory for one fictional person and one evaluation account whose non-sensitive preference changes meaningfully over time. Keep the Backstory generator-only. Set objective_ids to this selection and run_configuration_ids to an empty list; no other Objective or 1:10 configuration applies.

Create exactly three separate earlier Props for this Backstory/account: two independently understandable originals establishing the preference and one plausible unrelated historical record. Make all three initially active and available to every designated Scene. Assign each its complete per-Scene lifecycle. These are source records, not copied Backstory paragraphs or future Lines. Do not create captures, summaries, curation results, or runtime identifiers as Props.

Create exactly seven conversational Scenes with one natural Line each:
- Initial preference update: earlier Props precede a durable refinement expressed without a save request. Propose a justified source-preserving refinement outcome, without authoring its resulting record.
- Earlier deferred comparison: a later opportunity is premature.
- Timely comparison: the identical opportunity is now useful.
- Cancellation/replacement: explicit current information defeats an otherwise plausible suggestion.
- Repetition: actual prior surfacing or dismissal makes another mention inappropriate.
- Superficial overlap: nearby subject matter does not make stored history useful.
- Sensitive uncertainty: a proposed connection would require unsupported sensitive inference and should remain unmentioned.

Use natural person-authored Lines, without internal role names, controls, expected decisions, or evaluator language. Later Lines must not copy the updated preference or explicitly request recall. Do not fabricate diagnoses or stereotyped personal histories.

Plan the initial Scene first, then later fresh chats with conversation history cleared and actual durable account state preserved. Use capture-enabled workflow state only for the initial Scene and disable capture for later comparisons. Initial Props remain distinguishable from every observed capture and curation result. Through the adopted outcome-reference contract, later Scenes refer to actual outputs; never manufacture successful records or substitute reseeded expected summaries if an operation fails.

Keep the deferred and timely Scenes paired. Both decision times must be timezone-aware and after the actual prerequisite capture/curation. Their Line text, candidate state, current situation, and prior history must be identical; only supplied decision time changes. Use independent copies of the same actual post-prerequisite snapshot so the earlier comparison cannot alter the later one. The repetition Scene additionally references actual prior surfacing or dismissal, with trusted occurrence and suppression information. Cancellation must be explicit in its Line or authorized supplied context. Keep workflow context separate from Lines and proposed decisions. Do not invent a parallel context schema or prior runtime event.

Write PACKAGE_DIRECTORY/backstory.json using SyntheticBackstory and its adopted component models. Write the separate Ground truth file PACKAGE_DIRECTORY/ground-truth.json using ProposedGroundTruth, ground_truth_status proposed, and the exact SHA-256 of the final Backstory file bytes. These are the only two output paths. Do not edit repository files or this report.

Propose one complete Ground truth entry for every Scene/Objective. Include:
- Exact non-empty initial durable Line span with Unicode code-point offsets and exact supporting earlier Prop spans; expected review/storage and prohibited writes.
- Justified curation action, required source relationships, immutable-original expectations, and actual application expectations, using adopted outcome references for execution-created sources.
- Expected surface_now, defer, or do_not_surface decisions for later Scenes; allowed and required source lineage, useful suggestion criteria, meaningful reconsideration, and reasons for silence.
- The timing pair, identical inputs/state/history, and exact fresh-session boundaries; one relevance judgment for every available initial Prop in every Scene, using the adopted contract.
- Expected and prohibited released behavior, distinguishing recalled user words from interpretation; no obsolete, repeated, irrelevant, unsupported, or sensitive claim.
Keep proposed Ground truth outside runtime inputs. Current GroundTruthProposal.surfacing represents offline decisions only and currently forbids the required combined capture/curation and Prop-relevance information: if that remains true, STOP. Do not add another Objective or hide unsupported structures in free text.

Run the repository Python environment's evals/synthetic_journals/validate_package.py with the two sibling paths. Require schema, exact Backstory hash, ownership, references, source spans/evidence, ordering, pairings, complete Prop judgments, adopted outcome dependencies, and any resolved counts to validate. Missing deterministic support is a precondition failure, not a reason to weaken this plan.

Validation does not establish semantic realism, label correctness, or system performance. Do not run or grade Linger, observe its recorded behavior to choose labels, claim adoption, or write adoption/replay files. A human independent of the generator must adopt, revise, or reject every candidate label. Neither proposed nor adopted Ground truth may reach the evaluated system. Stop after the two validated proposed files.
```

## Ground truth lifecycle

The generator proposes exact spans, relationships, and outcomes. Deterministic validation rejects bad hashes, ownership, references, ordering, evidence, and pairings; the adopted extension must additionally validate outcome dependencies and complete Prop judgments. Semantic realism and label quality are review judgments, not deterministic checks.

An independent human reviews every label using `review-synthetic-ground-truth`; changes or rejection produce no adoption. Accepted proposals receive a separate hash-bound adoption via `adoption.py`. Ownership is established; displaying and validating the expanded dependencies remains gap C. Only adopted Ground truth may grade a run; neither proposed nor adopted labels enter Linger. Missing evidence or an unapproved row prevents adoption.

## Architecture and academic relevance

Muse, Librarian, Sculptor, and Provenance participate; Serendipity does not. Memory & Policy owns storage, scope, curation verification, and retrieval state; session services own fresh-chat isolation. Sculptor proposes; it cannot write or release responses.

| Product path and terminal outcome | Branches and verification |
|---|---|
| Initial Line → Provenance preflight → Muse → candidate review → deterministic capture → new-capture trigger → Sculptor curation → digest-bound Provenance review → policy application/audit → preserved originals and updated retrieval view | Preflight boundary skips Muse and downstream work; preflight error fails closed. No nomination, veto, invalid span, suppression, or failure creates no new record. Idempotent retry triggers no new curation. No-change skips review/write; revise/reject or stale/invalid plans do not apply. Verify actual hashes/audit, never report failed verification as success. |
| Each later fresh Line → preflight → authorized retrieval of actual durable state → bounded Sculptor decision → Muse → Provenance → deterministic personal-memory release → user reply and permitted session record | Useful suggestions retain source lineage. Defer/cancel/repeat/weak/sensitive branches insert no suggestion but allow helpful conversation. Retrieval or evidence failures fail closed. One revision returns through the same gates; rejection fails closed. Deferral schedules nothing. Session services record released turns under application policy; fresh reset clears conversational history. |

The complete product sequence is unimplemented; its evaluated endpoint includes these state changes and released wording. The existing offline runner ends at a validated decision.

A trace from changed preference to verified later use would demonstrate agent coordination and traceability asked about on briefing p. 9, and supply end-to-end testing evidence for the example artifacts on p. 11 ([briefing](../../../docs/submissions/aas-practice-module-briefing.pdf)). This is a proposed demonstration, not evidence of user benefit or a mandatory prescribed design.

> **Human decision required:** Approve this build target and target-state prompt, request revisions, or abandon the attempt. Generation remains unavailable until the named preconditions are met.
