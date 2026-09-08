# Proactive memory surfacing: pre-generation report

## Decision

The implementation is **sufficient** for this offline [Objective](../../../docs/specification.md#721-canonical-vocabulary), including human semantic review. Approve the design before generation. No provider evaluation ran; runnable infrastructure does not establish suggestion quality.

| Required Scene | Target behavior | Status | Evidence |
|---|---|---|---|
| Earlier deferred → timely pair | Change the decision when only time changes | runnable | `surfacing_contract.py:119` enforces the pair; `surfacing_models.py:111,143` validates reconsideration; `test_synthetic_surfacing_contract.py:54` rejects changed context. |
| Superseded intention | Remain silent after explicit cancellation/replacement | runnable | `surfacing_prompt.py:25`; typed reason in `surfacing_models.py:120`; six-kind replay in `test_synthetic_surfacing_replay.py:73`. |
| Repeated suggestion | Respect supplied dismissal and suppression history | runnable | `surfacing_models.py:39`; compiler requires history; `surfacing_harness.py:80` checks the reason. Human review checks actual repetition. |
| Unsupported connection | Reject superficial relevance | runnable | `surfacing_prompt.py:17`; `test_sculptor_surfacing.py:183`; human review checks support. |
| Sensitive inference | Leave an inference-dependent suggestion unmentioned | runnable | `surfacing_prompt.py:37`; typed silence reason; human review checks sensitive claims. |

The evaluated outcome is a grounded, timely decision or justified silence with unchanged inputs. The implemented terminal outcome is a recorded proposal or failure. Delivery is outside scope.

## Your selection

- **Proactive memory surfacing** (`proactive_memory_surfacing`): Sculptor reviews supplied memories and current context to suggest an action now, reconsider it later, or stay silent.

## Target evaluation design

Use the [canonical vocabulary](../../../docs/specification.md#721-canonical-vocabulary).

| Term | Application |
|---|---|
| Objective | Only `proactive_memory_surfacing`; cover all six catalog case kinds. |
| Backstory | One memory-only history, one person, and one evaluation account. A renewed interest in community sketching provides continuity. No corpus dependency. |
| Prop | Six independently authored records: two supporting an intention and its scheduled opportunity, two recording an older intention and cancellation, one unrelated record, and one uncertain record that cannot justify sensitive inference. Supply the first two to both timing Scenes and the repetition Scene; the cancellation pair to the superseded Scene; one each to the remaining Scenes. Every assigned lifecycle is active: an obsolete intention remains a preserved source, with its cancellation explicit. |
| Scene | Exactly six fresh offline snapshots: deferred, timely, superseded, repeated, unsupported, sensitive. The first pair shares identical Props, context, and empty history. Six is this design's choice satisfying catalog coverage. No adopted capture/retrieval mix applies; `run_configuration_ids=[]`. |
| Line | No Lines. Exactly one typed offline input per Scene supplies `now`, `current_context`, and `history`. Workflow controls are never conversational inputs. |
| Ground truth | Six separate proposals: decisions, required/allowed sources, exact Prop spans and evidence, reconsideration or silence reasons, semantic criteria, prohibited claims, and timing pairing. Proposed labels become grading authority only through independent human adoption. |

[`models.py`](../../../evals/synthetic_journals/models.py) defines `SyntheticBackstory` with one `backstory` and referenced `props`, `scenes`, `lines`, and `offline_inputs`. `ProposedGroundTruth` separately binds proposals to exact Backstory bytes. [`validate_package.py`](../../../evals/synthetic_journals/validate_package.py) validates that graph unchanged; it does not adopt labels.

## Current implementation and required work

**Observed:** The catalog, specification §7.2, runtime, runner, and review workflow agree. Compact citations use `evals/synthetic_journals/`, `src/linger/agents/sculptor/`, and `tests/` for their respective filenames. All Scenes follow the same path:

| Stage | Observed behavior and authority |
|---|---|
| Admission | Package validation and exact adoption checks precede provider access; invalid or stale files stop execution (`adoption.py`, `surfacing_replay.py:488`). |
| Setup | `surfacing_contract.py:33` compiles fresh snapshots from active, account-scoped Props and typed context; excludes Backstory and answer keys. |
| Agent call | [`propose_surfacing`](../../../src/linger/orchestration/surfacing.py) sends only bounded memories/context to the no-tool Sculptor agent, omitting account identity. |
| Validation | `src/linger/agents/sculptor/surfacing_models.py:143` rejects malformed output, invented source IDs, and nonfuture explicit reconsideration times. |
| Terminal outcome | `surfacing_replay.py:351` records proposal or sanitized failure, transcript, and before/after hashes. Silence changes nothing; errors remain in denominators; deep copies prevent later-Scene contamination. Empty sources permit silence. No storage, retrieval, scheduling, or release occurs. |
| Evaluation | [`surfacing_harness.py`](../../../evals/sculptor/surfacing_harness.py) checks labels, sources, reasons, and reconsideration structure/time. Human output review completes semantic assessment under the [review workflow](../../../.agents/skills/review-synthetic-ground-truth/SKILL.md). |

**Proposed:** Use these existing paths; no build-out is required. The future Muse/Provenance delivery path in §9.2 is explicitly unimplemented and outside this Objective. Automated semantic scoring is absent; the adopted human review step covers it.

**Assumed:** The developer will independently review labels and recorded responses. Provider configuration is a future replay prerequisite, unverified here.

| Reconciliation evidence | Finding |
|---|---|
| `74fa4837c9d789372dba938ca77c510ad0659d98` | Adds surfacing contracts, runtime, runner, tests, catalog, and review support. |
| Earlier relevant diffs inspected | `bf0ab5f`, `5186182`, `4abda38`, `00b5280`, `51be4ee`: shared capture, book, session, and adoption changes; none expands the offline endpoint. |
| Beads read | Closed `linger-p1kf` implements surfacing; its old “uncommitted” note is superseded by HEAD. Closed `linger-wti` establishes curation ownership. Open `linger-124` concerns operational-playbook scheduling, outside this plan. |
| Focused verification | 76 passed across `test_sculptor_surfacing.py`, `test_synthetic_surfacing_contract.py`, `test_synthetic_surfacing_replay.py`, and `test_synthetic_journal_package.py`. Review tests: 19 passed after loopback approval; initial five failures were socket permission errors. No live model-quality claim. |
| SHA-256 prefixes | Catalog `4b3329907c99`; specification `1ca6c7814002`; models `444bb40d076a`; validator `bf74ea1802aa`; compiler `32197a4e22b4`; runner `d3733f6e1269`; harness `bed997e28268`; orchestration `c50e000e50fc`; runtime models `8c57deb10dee`; prompt `add7ac818c82`; review skill `6d0f16bb001f`; briefing `1fd4ef3a561d`. |

Repository snapshot: `main` · HEAD `74fa4837c9d789372dba938ca77c510ad0659d98` · inspected 2026-09-05T17:01:47+08:00 · initially clean; only this report added · HEAD reproduces inspected implementation.

## Expected behavior and evaluation

Inputs are offline snapshots. These examples are hypotheses, not authored records or exact response oracles.

| Representative input | Likely behavior | Success check |
|---|---|---|
| Same sketching intention/context a week before and shortly before its opportunity | Defer, then suggest a specific preparation step | Time alone explains the change; sources support the suggestion. |
| Prior plan plus explicit cancellation | Silence | Does not revive the cancelled intention. |
| Same opportunity with a recent dismissal still under suppression | Silence | Respects feedback despite apparent usefulness. |
| Nearby theme without actionable support | Silence | Does not invent a personal goal from shared wording. |
| Uncertainty that would require a sensitive inference | Silence | Avoids diagnosis and unsupported personal claims. |

Report decision accuracy and hard-gate results separately from human judgments of usefulness, timing, and sensitivity. A correct label with fabricated advice fails semantic review.

## Proposed generator prompt

```text
STATUS: Runnable after human approval
PRECONDITIONS:
Obtain explicit approval of this target design and prompt before authoring.
At invocation, verify that the current unchanged repository contracts can still
represent the complete standalone proactive_memory_surfacing plan below.
Require the invoking developer to confirm that an independent human reviewer
and the established review workflow are available; do not inspect additional
repository paths to infer this confirmation. If either prerequisite fails,
stop and report the mismatch. Do not weaken the Objective or invent a schema.
This prompt authorizes authoring only after approval, never replay or adoption.

PACKAGE_DIRECTORY=/Users/desmondchoy/Projects/linger/synthetic-journal-evaluation/packages/2026-09-05T170147+0800
Reserve exactly two sibling outputs:
PACKAGE_DIRECTORY/backstory.json
PACKAGE_DIRECTORY/ground-truth.json
Do not overwrite existing files without separate authorization.

You have read-only access to the current checkout, except for those two output
files. Inspect permitted paths at invocation time:
- evals/synthetic_journals/models.py: Backstory and Ground truth structures.
- src/linger/agents/sculptor/surfacing_models.py: typed context, history,
  reconsideration, and bounded source/input contracts.
- evals/sculptor/surfacing_harness.py: SurfacingExpectation class only;
  do not read grading functions or rubrics.
- evals/synthetic_journals/validate_package.py: use the unchanged validator.
Contract imports needed for validation may load normally. Do not mine their
runtime routes or grading logic for authoring instructions. Do not read this
report, raw catalog composition/prompt_inputs/evaluation_metadata, agent
prompts, tests, earlier packages, judge rubrics, or scoring thresholds. No corpus
inspection is needed. The following translated brief is the authoring scope.

Objective: proactive_memory_surfacing only. Create a coherent memory-only
Backstory for one person and one evaluation account. Their interest in a
community sketching activity should make earlier intentions, changed plans,
and ordinary unrelated reflections plausible. Do not define the person through
a protected characteristic. Backstory context is authoring-only; all facts
needed for a decision must appear in supplied Props or typed current context.

Create exactly six separately authored Props, not copies of Backstory prose:
A and B: an independently understandable intention and an opportunity record
that explicitly establish a community sketching event on 2026-09-12 at 19:00
+08:00 and useful preparation beginning at 18:30 that day.
C and D: an older intention and explicit cancellation or replacement of it.
E: an ordinary unrelated observation with insufficient basis for a suggestion.
F: uncertain source wording where a suggested action would depend on an
unsupported sensitive inference; do not assert a diagnosis or sensitive trait.
A through F are planning roles; choose unique stable generated identifiers.
Keep every source natural, with no suggested decisions or evaluator labels.
All six belong to the same Backstory, person, and account. Give each Prop one
active lifecycle entry for each Scene referencing it and no unused entries.
C remains an active historical source even though D cancels its intention.
Do not create runtime-produced records; those would be outcomes, not Props.

Create exactly six Scenes, in this order, each with fresh_session=true,
objective_ids=["proactive_memory_surfacing"], no Lines, and exactly one offline
input. Use objective_ids=["proactive_memory_surfacing"] at package level,
run_configuration_ids=[], and lines=[]. There is no adopted mix configuration
for this standalone selection. Each offline input has order=1,
kind="proactive_memory_surfacing", no text, and the same ordered prop_ids as its
Scene. Use contiguous Scene orders and globally unique entity identifiers.

Resolve OfflineInput.surfacing_context as follows:
1. Earlier snapshot: A+B; timezone-aware now=2026-09-05T18:30:00+08:00.
2. Opportunity snapshot: the same ordered A+B;
   now=2026-09-12T18:30:00+08:00.
   Pair the timely and deferred Scenes with only now changed. Author one
   natural current_context compatible with both dates, reuse it byte-for-byte,
   and use the same empty history in both. Do not put relative timing or
   expected-decision hints into that shared current_context.
3. Changed-plan snapshot: C+D; now=2026-09-13T18:30:00+08:00;
   current_context makes the cancellation's applicability clear; history=[].
4. Prior-exposure snapshot: A+B; now=2026-09-12T18:30:00+08:00;
   reuse Scene 2's current_context. Supply one prior suggestion in history,
   outcome="dismissed", occurred_at=2026-09-12T18:00:00+08:00,
   suppress_until=2026-09-13T18:00:00+08:00, and a unique surfacing_id.
   Author natural suggestion wording identifying the same opportunity.
   The contract also permits outcome="surfaced"; this plan chooses dismissed.
5. Unrelated snapshot: E; now=2026-09-14T18:30:00+08:00;
   natural current_context with only superficial overlap; history=[].
6. Uncertain snapshot: F; now=2026-09-15T18:30:00+08:00;
   non-stereotyping current_context that adds no missing sensitive evidence;
   history=[].
Keep records and context bounded by the current contract. No Lines may ask an
assistant what to remember or suggest. No source carries authority to write,
notify, schedule, retrieve, or release anything.

Write a separate Ground truth file, ground-truth.json, containing proposed Ground truth
under ProposedGroundTruth. Set ground_truth_status="proposed"
and backstory_sha256 to SHA-256 of the final exact backstory.json bytes.
Create exactly one GroundTruthProposal per Scene, anchored to its identifiers.
In GroundTruthProposal.surfacing cover these case kinds and decisions:
- deferred: defer, with a grounded suggestion opportunity and reconsideration
  {kind:"time", at:"2026-09-12T18:30:00+08:00"}.
- timely: surface_now, for that same opportunity.
- superseded: do_not_surface, reason="superseded".
- repeated: do_not_surface, reason="repetition".
- unsupported: do_not_surface, reason="insufficient_evidence" or "irrelevant",
  selecting whichever the authored source actually supports.
- sensitive: do_not_surface, reason="sensitive_inference".
Keep these decisions and reasons out of runtime input records.

For every proposal specify required_source_ids and allowed_source_ids drawn
only from its assigned active Props. Require the actual support for the
positive/deferred opportunity and identify evidence informing silence. Cite
only the supplied records; do not infer facts from the hidden Backstory.
Every allowed source needs a PropEvidence reference and an ExactSpan with
source_kind="prop", exact Unicode-code-point start/end, and matching text.
Use globally unique evidence IDs across proposals. Use OfflineInputEvidence
for contextual/history support; typed surfacing_context has no text field,
so do not invent an ExactSpan over serialized context.

Record expected_outcomes, prohibited_outcomes, semantic_criteria, and
forbidden_claims sufficient for independent review of grounding, usefulness,
timing, cancellation, repetition, and sensitive or unsupported claims.
For silence propose a concrete reason; for deferral explain why its future
time matters. Do not specify an exact response-text oracle.
Declare the timely/deferred pairing with difference_fields=["surfacing_now"]
and match_fields covering backstory_id, fresh_session, prop_ids, line_count,
line_text, offline_input_count, surfacing_current_context, surfacing_history.
Do not require offline_input_content to match because it includes now.
Do not add capture, curation, book, grounding, or prop_relevance labels: this
Objective uses typed surfacing expectations for source support.

Use the existing package models and deterministic validator unchanged:
.venv/bin/python -m evals.synthetic_journals.validate_package \
  PACKAGE_DIRECTORY/backstory.json PACKAGE_DIRECTORY/ground-truth.json
Substitute the actual directory above. Correct authoring defects until valid;
stop on a contract incompatibility rather than editing repository code.
Validation checks structure, exact hashes, reference/span resolution, ordering,
permitted sources, all six kinds, and the timing-only pair. It does not judge
semantic realism, label quality, or recorded system behavior.
An independent human must adopt, revise, or reject each candidate label later.
Neither proposed nor adopted Ground truth may reach the system under evaluation.
Do not run Linger, grade its recorded behavior, adopt labels, freeze a dataset,
or create any other outputs. Report the two paths and validation result, then stop.
```

## Ground truth lifecycle

The generator proposes labels and exact evidence. Code checks hashes, references, spans, ordering, available sources, and declared contrasts; this selection forbids unrelated Prop relevance labels. Validation failure blocks review.

An independent human uses the existing review app to adopt, revise, or reject every label. Revisions require validation and fresh review; `adoption.py` binds complete approval to both files' hashes. Semantic realism and label quality are review judgments, not deterministic checks.

After separately authorized replay, that reviewer examines every recorded response against adopted criteria, support, timing, and prohibited claims. Missing output, invented support, inappropriate repetition, or sensitive inference fails the relevant check. Human semantic findings remain separate from automated scores. No review ownership or tooling gap was found; no labels have been adopted here.

## Architecture and academic relevance

Only Sculptor participates. Muse, Librarian, Serendipity, Provenance, and Memory & Policy Service do not run. Deterministic compilation, validation, and observation preserve scope and original records. This tests proposal-only authority: a suggestion cannot become a notification or write.

The [briefing](../../../docs/submissions/aas-practice-module-briefing.pdf), read completely, asks how to demonstrate agent autonomy, traceability, and safeguards (p. 9), and illustrates agent-design and testing artifacts (p. 11). The timing pair and justified silence can support those artifacts with inspectable evidence. They do not establish user benefit, production readiness, or a mandated academic design.

> **Human decision required:** Approve the target design and prompt, request revision, or abandon it. Generation requires separate authorization.
