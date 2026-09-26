# Reviewed capture and bounded curation

## Decision

The current implementation is **sufficient** for the confirmed selection. The
combined validator, completion step, replay endpoint, and focused tests support
the complete target of 16 Scenes. No Scenario data has been generated.

| Required Scene set | Status | Evidence |
|---|---|---|
| One durable capture Scene | runnable | `evals/synthetic_journals/replay.py` and `tests/test_capture.py` cover exact-span binding, review, policy, and storage. |
| Ten low-signal capture Scenes | runnable | The capture runner and combined replay cover ordered no-candidate Scenes and no-write outcomes. |
| Exact and paraphrased duplicate curation | runnable | Sculptor contracts and the adopted five-behavior curation validator cover both forms. |
| Evolving-fact curation | runnable | Typed curation expectations and evaluator-owned completion fields support the action. |
| Related-facts curation | runnable | The topic-group contract and source-preservation checks support the action. |
| Superficial-overlap/no-change curation | runnable | `tests/test_curation_application.py` covers the no-change branch. |

There is no unresolved source gap affecting this plan. Beads could not be read:
`bd search` failed three times with the existing Dolt schema error:
`table local_metadata has unknown fields`. This report therefore relies on
source, tests, specification, and commit history, and does not claim tracker
reconciliation.

## Confirmed Objectives

- `reviewed_automatic_memory_capture` — Reviewed automatic memory capture.
- `bounded_memory_curation` — Bounded memory curation.

The selector returned catalog SHA-256
`2ec0e7963249f66b2330adec9850f763222e1a4d551b378810176329bc6f7e07` and the
ordered IDs above. The run configuration is
`reviewed-automatic-memory-capture-10-to-1`: one capture-candidate Scene and
ten no-candidate Scenes. This is this run's configuration, not a catalog-wide
minimum.

## Target evaluation design

This Scenario uses the canonical vocabulary from specification Section 7.2.1:
`Objective`, `Scenario`, `Backstory`, `Prop`, `Scene`, `Line`, and
`Ground truth`.

- **Objective:** The two confirmed catalog IDs remain on the root model and on
  their relevant Scenes.
- **Backstory:** One memory-only history for one person and one evaluation
  account. It never enters the system under evaluation.
- **Prop:** Fifteen separately authored earlier records for curation: two exact
  duplicates; two paraphrased duplicates; three records refining one fact plus
  one noise record; three related distinct records plus one distractor; and
  three superficially overlapping but unrelated records. Runtime captures and
  derived records are outcomes, not Props.
- **Scene:** Sixteen ordered graded units: eleven fresh-session capture Scenes,
  followed by five Props-only curation Scenes. Capture Scenes have no Props;
  curation Scenes receive only their designated active Props.
- **Line:** Eleven natural user inputs, one per capture Scene. Curation Scenes
  have no Lines or workflow-control Lines. Capture enablement and session reset
  are application workflow state.
- **Ground truth:** Separate proposed answer-key data in
  `ground-truth.json`, anchored to exact spans, identifiers, and source
  evidence. The repository supplies evaluator-owned curation policy fields
  before strict validation. Independent review must adopt, revise, or reject
  every candidate; neither proposed nor adopted Ground truth reaches Linger.

The generator must use `models.py` and `validate_scenario.py` unchanged.
Bounded curation must remain Props-only and cover exact duplication,
paraphrased duplication, evolving facts, related facts, and unrelated/no-change
input. Capture and curation use separate inputs: captured records do not become
curation Props.

## Runtime trace and endpoint

1. The application enables capture for the isolated evaluation account and
   starts a fresh chat for each capture Scene.
2. Muse receives the Line, may nominate an exact span, and drafts a reply.
3. Provenance reviews the reply and nomination. Application code binds any
   allowed nomination to the current Line span.
4. Memory & Policy is the only storage authority. It applies a deterministic
   personal-data/secret screen to exact capture text and refuses a matching
   candidate without changing the reader reply. It commits an approved,
   policy-compliant candidate and emits the normal release/save outcome, or
   leaves storage unchanged for no-candidate and rejected cases.
5. For curation, the application resolves only the designated active Props in
   the same account, Sculptor proposes a bounded action, and the curation path
   verifies source preservation and the allowed proposal contract. The same
   deterministic privacy screen rejects personal data or secrets in a proposed
   derived summary or topic label before application.
6. `capture_curation_replay.py` executes Scenes in declared order, keeps
   capture state isolated, and evaluates capture and curation through existing
   endpoints. It does not turn captured records into later curation inputs.

The selected evaluation endpoint covers exact capture nomination/release/storage
and bounded curation proposal/source-preservation behavior. The broader product
also has a reviewed curation application path; downstream application audit,
retrieval projection, and interactive chat-triggered curation are architectural
context, not extra Ground truth requirements for this selection.

## Implementation evidence

The current branch is `km-provenance-wrapup`, at HEAD
`e4a5318fa24baaca12b9a69ff9076d1b92bd887f`, timestamp
`2026-09-22T21:44:06+0800`. The tree is dirty in the pre-existing modified
`evals/provenance/risk-codes-live-report.json`, plus the untracked paths
`.audit/`, `.agents/skills/review-synthetic-ground-truth/ui/dist/assets/index-BjM-nq0L.js`,
and this Scenario report directory. These changes are preserved and were not
modified by the plan update.
HEAD alone is the implementation inspected for this report.

Relevant history inspected, including diffs:

- `33ae46d` — current evaluation contract updates.
- `e4a5318` — merge conflict resolution after main integration.
- `c52c76b` — merged turn-triage and safety-hardening changes.
- `9d9b6c5` through `67c52ec` — message normalization, encoded-instruction,
  personal-data, self-harm, and language-boundary protections.
- `d62a9ad` — combined Scenarios and readable Ground truth review.
- `dfe9830` — current runtime and evaluation workflow documentation.
- `a2a62a5` — sensitive capture review and veto path.
- `6bed428` — Librarian retrieval checkpoint and contract updates.

The five-agent architecture assigns Muse, Librarian, Sculptor, Serendipity, and
Provenance distinct authorities. Only Muse, Sculptor, and Provenance participate
in this Scenario; Memory & Policy and session state are deterministic
supporting services.

The merge adds deterministic message normalization, turn triage, and privacy
screening. Capture spans are therefore authored against the normalized Line;
the candidate text remains the normalized source text. These safeguards do not
change the selected Scene topology, but they add fail-closed outcomes that the
runner records as rejected/no-write behavior.

Focused verification passed after the merge:

```text
uv run pytest -q tests/test_synthetic_capture_curation_replay.py \
  tests/test_synthetic_curation_replay.py \
  tests/test_curation_ground_truth_completion.py tests/test_capture.py
67 passed in 3.47s
```

The academic briefing describes an academic prototype requiring architectural,
agent-design, and evaluation artifacts. This plan contributes concrete evidence
for those project questions by testing whether specialized agents can propose
memory changes while deterministic application code retains storage authority,
exact provenance, account scope, and source-preservation control. This does not
claim human benefit or deployment readiness.

## Expected behavior hypotheses

These are hypotheses, not exact response oracles. A durable Line should produce
a useful reply and exactly one approved stored span. Temporary logistics,
filler, short-lived observations, and routine updates should produce useful
replies without a nomination, save notice, or write. Curation should link exact
or paraphrased duplicates, summarize only supported refinements, group only
related distinct records, and leave superficial overlap unchanged. Plain-language
success means: “the reply is useful, every stored or proposed source is one of
the supplied records, and nothing unrelated is rewritten or stored.”

## Proposed generator prompt

```text
STATUS: Runnable after human approval

PRECONDITIONS:
This prompt does not authorize generation. Continue only after separate human
approval of this target design and prompt. Verify that the current checkout
contains the unchanged scenario models and validator, the reviewed capture
preset, the combined capture/curation replay, and the curation Ground truth
completion command. Verify that backstory.json, ground-truth.json, and
ground-truth-adoption.json do not already exist in the target directory. If any
precondition fails, report the exact failure and stop.

TARGET_DIRECTORY=
synthetic-journal-evaluation/scenarios/reviewed-capture-and-bounded-curation--muse-sculptor-provenance--2026-09-21
AUTHORIZED_OUTPUTS:
TARGET_DIRECTORY/backstory.json
TARGET_DIRECTORY/ground-truth.json

You have read-only access to the checkout except for those two authorized
outputs. Inspect permitted paths at invocation time. Use existing contracts
unchanged. Do not read this report or historical Scenarios as generation input.
Do not generate adoption records, replay artifacts, frozen releases, or more
Scenarios.

Permitted sources:
- evals/synthetic_journals/models.py
- evals/synthetic_journals/validate_scenario.py
- synthetic-journal-evaluation/generation-presets/reviewed-automatic-memory-capture-10-to-1.json
- src/linger/agents/muse/ (current capture policy and contracts)
- src/linger/agents/sculptor/ (current curation contracts)
- src/linger/orchestration/capture.py
- src/linger/orchestration/curation.py
- src/linger/services/memory.py
- src/linger/contracts/privacy.py
- docs/specification.md Section 7.2.1 and current capture/curation sections

Do not receive or reproduce raw catalog composition, prompt_inputs,
evaluation_metadata, internal component routes, evaluator thresholds, or judge
rubrics. Do not inspect credentials or data/corpus/. This is a memory-only
Scenario and needs no corpus inspection.

Selected Objectives, in order:
- reviewed_automatic_memory_capture
- bounded_memory_curation

Write backstory.json with the unchanged SyntheticBackstory contract:
- Use one Backstory for one person and one evaluation account. It never reaches
  Linger.
- Set root Objective IDs in the selected order and
  run_configuration_ids to ["reviewed-automatic-memory-capture-10-to-1"].
- Create exactly 16 Scenes in contiguous order: 11 capture Scenes followed by
  5 curation Scenes. Each Scene selects exactly its own Objective.
- Each capture Scene is fresh-session, has no Props, and has exactly one Line
  with order 1. Write exactly 11 natural Lines. Make exactly one durable
  reflection, preference, intention, or incident useful later, and make the
  other ten diverse low-signal material. Do not use save controls, internal
  agent names, policy labels, expected outcomes, grading instructions, personal
  contact data, credentials, or secrets. Keep the intended durable candidate
  policy-compliant so the positive capture Scene tests ordinary approved
  storage rather than the deterministic privacy veto.
- Capture enablement and session reset are workflow state, not Lines. Do not
  copy a complete Line into a Prop. Captured records are runtime outcomes.
- Create 15 separate Props for curation: two exact duplicates; two paraphrased
  duplicates; three records refining one evolving fact plus one unrelated
  record; three related distinct facts plus one distractor; and three records
  with superficial wording overlap but no useful relationship.
- Give each curation Scene only its designated 2, 2, 4, 4, or 3 active
  same-account Props with valid lifecycle entries. Curation Scenes have no Lines
  and no OfflineInput objects. Keep offline_inputs and source_setups empty.

Write separate proposed Ground truth to ground-truth.json:
- Set status to proposed and bind backstory_sha256 to the exact final
  backstory.json bytes. Provide one GroundTruthProposal for every Scene/Objective
  pair, for 16 proposals total.
- For capture, use CaptureExpectation. Bind the one durable nomination to an
  exact non-empty span of its Line and propose allow_capture. Use no_candidate
  for the ten low-signal Scenes. Keep generic exact_spans empty for capture.
  Describe expected release, storage, and prohibited changes separately.
- Pair the durable Scene with a nearby low-signal comparison using supported
  ScenePairing fields. Declare only supported differences: Line text, while
  preserving the same Backstory, fresh-session state, empty Props, and Line
  count.
- For curation, use the existing typed CurationExpectation: duplicate links
  for exact and paraphrased duplicates; a derived summary from only the three
  refining Props; a topic group from only the three related Props; and no
  proposal for superficial overlap.
- Cite every supplied curation Prop exactly once as Prop evidence, including
  excluded noise or distractors. Use exact Prop spans to support candidate
  relationships and show why excluded records do not belong. Restrict actions
  to justified supplied source identifiers.
- Omit max_summary_words and semantic_review from every curation action. Do not
  choose evaluator thresholds or write a judge rubric. Do not add capture or
  prop_relevance labels to curation proposals. Do not invent runtime records or
  downstream audit/retrieval outcomes. Do not put personal contact data,
  credentials, or secrets in a proposed derived summary or topic label; the
  deterministic Memory & Policy privacy screen must remain a safety backstop,
  not the intended curation behavior.

The generator proposes labels only. It neither grades Linger nor adopts its
labels. Neither Backstory nor proposed/adopted Ground truth may reach the
system under evaluation.

After separate human authorization, run completion exactly once before normal
validation:
uv run python -m evals.synthetic_journals.complete_curation_ground_truth \
  TARGET_DIRECTORY/backstory.json TARGET_DIRECTORY/ground-truth.json

Completion supplies evaluator-owned curation fields and validates the complete
Scenario. If it fails, correct only the reported authoring error after
confirming no rewrite occurred; do not supply those fields yourself. Then run:
uv run python -m evals.synthetic_journals.validate_scenario \
  TARGET_DIRECTORY/backstory.json TARGET_DIRECTORY/ground-truth.json

Stop on validation or authority conflict. Report both output paths and the
validation result, then stop for independent Ground truth review. Only adopted
Ground truth may grade a replay.
```

## Ground truth lifecycle and human decision

Generation writes proposed Ground truth separately from the Backstory.
Deterministic validation checks schema, exact Backstory hashing, references,
spans, ordering, evidence, source coverage, and run-configuration counts. For
curation, completion owns `max_summary_words` and `semantic_review`; the
generator must not read or choose those policies. An independent reviewer then
adopts, revises, or rejects each candidate. Only adopted Ground truth is
canonical for grading.

Human decision required: approve this target and detached prompt for generation,
request revision, or abandon the plan. Generation remains separately
unauthorized by this report.
