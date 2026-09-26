# Proactive memory surfacing

## Decision

The confirmed Objective is **proactive memory surfacing**. The current
implementation is **insufficient for this complete selection**. The repository
has the conversational Scenario contract and component surfacing evidence, but
the production trigger, typed memory hand-off into Muse, deterministic release
path, complete replay, and end-to-end grading are not yet established.

The detached prompt below is therefore **Target state — do not run**. It
describes the complete target and names the prerequisites that must be resolved
before generation. No Scenario data has been generated.

## Your selection

- Objective: `proactive_memory_surfacing` — Proactive memory surfacing.
- Catalog: `synthetic-journal-evaluation-objectives`.
- Confirmed catalog SHA-256:
  `2ec0e7963249f66b2330adec9850f763222e1a4d551b378810176329bc6f7e07`.
- Confirmation: `2026-09-24T22:58:55+08:00`.
- Branch: `km-provenance-wrapup`.
- HEAD: `73efb06d79091388753c36a191d43d99b412e791` — merge commit.
- Repository snapshot: dirty. Materially relevant tracked/untracked changes
  include `docs/implementation/provenance-todos.md`,
  `docs/implementation/provenance-4.2.5.md`, the review UI bundle, audit
  material, and the existing reviewed capture/curation Scenario directory.
  HEAD alone does not reproduce those uncommitted documentation or artifact
  changes; the inspected implementation paths are present at HEAD.
- Local timestamp: `2026-09-24T23:00:01+0800`.
- Material-path fingerprint (SHA-256 of ordered file hashes):
  `6d05fba05d0f95e06309b45dfe4b89b61b309895d0b3f240cce6f78c83d5d0c8`.

Relevant recent history inspected included the current merge and the recent
runtime safety commits on 2026-09-21/22. The implementation-specific provenance
note records the earlier capture/curation replay and explicitly states that it
did not exercise later fresh-chat surfacing or final release. Beads inspection
was attempted, but `bd` could not open the local database because its schema
contains an unknown field in `local_metadata`; no Beads status is claimed here.

## Target evaluation design

This plan uses the [seven canonical nouns from Section 7.2.1](../../../docs/specification.md#721-canonical-vocabulary): `Objective`,
`Scenario`, `Backstory`, `Prop`, `Scene`, `Line`, and `Ground truth`.

| Noun | Target use |
|---|---|
| Objective | One confirmed `proactive_memory_surfacing` Objective. Its capture and curation prerequisites are included in the same Scenario; separate prerequisite Objectives are not selected. |
| Backstory | One memory-only Backstory for one person and one evaluation account. It describes an evolving preference and its surrounding ordinary conversation. |
| Prop | Earlier same-account source records only, positioned before their designated Scenes. Captured memories, curation proposals, derived records, and runtime identifiers are outcomes, never Props. |
| Scene | Seven ordered graded units: one initial capture Scene; one useful timely surfacing Scene; one matched deferred Scene; one cancelled/replaced Scene; one repeated/dismissed-history Scene; one superficial-overlap Scene; and one unsupported or sensitive-inference Scene. All conversational Scenes start fresh sessions. |
| Line | Exactly one natural conversational input per Scene. Workflow state such as capture enablement, session reset, decision time, prior surfacing history, and cancellation is not a Line. The later Lines do not ask for recall or reveal the expected decision. |
| Ground truth | Separate proposed Ground truth in `ground-truth.json`, with exact spans/evidence, typed conversational expectations, source lineage, state-transition expectations, pairings, expected and prohibited released behavior. It is not supplied to Linger and is not authoritative until independent review. |

The initial Line must naturally refine an earlier preference and enter the
normal preflight, Muse nomination, Provenance review, and deterministic capture
policy. Only a successful new capture may trigger application-owned bounded
curation. Later fresh-session Lines must consume only the actual durable state
and actual curation result. The timely/deferred pair must have identical Line,
memory state, current context, and prior history, differing only in supplied
decision time. Other Scenes must make cancellation/replacement, prior exposure
or dismissal, superficial overlap, and sensitive/speculative inference
observable in supplied context or Lines.

No corpus is needed: this is a memory-only Scenario. The future generator must
not inspect `data/corpus/` or invent book evidence.

## Current implementation and required work

| Required Scene/path | Status | Evidence and gap |
|---|---|---|
| Natural capture and reviewed storage | Partially runnable | Existing chat capture, exact-span binding, Provenance review, and Memory & Policy storage exist. The selected Objective requires this as a prerequisite and requires observed outcomes to flow into later Scenes. |
| Capture-triggered curation | Partially runnable | `src/linger/orchestration/conversational_memory.py` has `curate_after_capture`, and tests cover triggering only after a new capture. The complete product replay must prove the real outcome and carry its runtime references forward. |
| Fresh-session retrieval and bounded Sculptor input | Blocked | `src/linger/orchestration/surfacing.py` and `SurfacingInput` provide an offline decision adapter, but the current specification says chat does not initiate surfacing. The product hand-off from authorised retrieval to Sculptor in a later chat is missing. |
| Sculptor decision into Muse | Blocked | `src/linger/contracts/surfacing.py` is a typed hand-off asset, but a production path that supplies the selected memory and lineage to Muse, preserves attribution, and handles silence/deferral is not established. |
| Muse → Provenance → deterministic release | Blocked | The Objective requires reviewed response release with personal-memory evidence resolution. Existing offline surfacing replay does not execute this conversational release boundary. |
| All seven Scenes and outcome dependencies | Blocked | `conversational_surfacing_contract.py` can compile `conversational_v1` and enforce capture-before-surfacing, fresh sessions, one Line, and symbolic runtime source references. No complete Objective-specific runner grades observed capture, curation, later memory use, release, and no-change branches together. |

The offline `surfacing_replay.py` is narrower component evidence: it accepts
one `OfflineInput`, no Lines, and evaluates only Sculptor's decision against
Props. It cannot establish this Objective. The conversational contract and
focused tests are useful schema/compiler evidence, not proof of production
readiness. The provenance implementation note and Section 4.2.5 agree on this
source gap; no contradictory adopted runtime contract was found.

The complete product trace must include the normal emotional preflight and Muse
path; successful capture; separate curation Provenance review and application;
immutable originals and audit verification; fresh-session reset; authorised
retrieval; bounded Sculptor input; Sculptor decision; Muse wording; Provenance
review; deterministic personal-memory release; and helpful ordinary
conversation when surfacing is deferred or suppressed. Capture veto, no
nomination, curation rejection/failure, invalid lineage, retrieval failure,
and release rejection must remain observable no-change branches.

## Lifecycle and contract notes

Use `evals/synthetic_journals/models.py` and
`evals/synthetic_journals/validate_scenario.py` unchanged. The Backstory file
must use `scenario_contract: "conversational_v1"`,
`conversational_scenes`, Lines, and symbolic prerequisite Scene IDs. The Ground
truth file must use `ground_truth_status: "proposed"`, match the exact
Backstory SHA-256, and contain one conversational proposal per Scene. Runtime
capture, curation, and derived identifiers must be symbolic outcome references,
not fabricated Props or records.

The lifecycle is: generator writes proposed Ground truth; deterministic
validation checks schema, hashes, references, spans, ordering, evidence, and
the conversational graph; an independent reviewer adopts, revises, or rejects
each candidate label. Only adopted Ground truth may grade a run. Neither
proposed nor adopted Ground truth may reach the system under evaluation.

## Academic relevance note

The NUS-ISS briefing asks teams to demonstrate multi-agent coordination,
assurance, trust, accountability, explainability, governance, and security in a
project artifact, and asks how benefits can be demonstrated through scenarios
where agents show autonomy and handle queries responsibly. This Scenario gives
one concrete demonstration: an initial natural Line flows through Muse,
Provenance, Memory & Policy, and Sculptor, then a later fresh conversation
tests useful surfacing and appropriate silence with inspectable source lineage.
That is an academic-relevance claim, not an additional professor requirement.

## Expected behavior and evaluation

These are hypotheses, not exact response oracles. A useful preference update
should produce one approved durable record and a reviewed curation outcome.
The timely Scene should produce a grounded, attributed suggestion. The deferred,
cancelled, repeated, unsupported, and sensitive Scenes should not insert the
suggestion, while still allowing an ordinary helpful reply when policy permits.
The matched timing pair should change the decision only because the supplied
decision time changes. Success means the recorded capture, curation, source
lineage, fresh-session boundary, Sculptor decision, release review, and
no-change branches match independently adopted Ground truth.

## Proposed generator prompt

```text
STATUS: Target state — do not run

PRECONDITIONS: do not run until every prerequisite below is implemented and
verified.

Do not generate this Scenario until all of the following are implemented and
verified in the current checkout:

1. A production conversational path triggers reviewed capture and then
   application-owned bounded curation only after a successful new capture.
2. Later fresh sessions retrieve actual account-scoped durable state and pass
   only bounded authorised candidate memories, current context, decision time,
   and prior surfacing/dismissal history to Sculptor.
3. A typed Sculptor-to-Muse hand-off preserves personal-memory attribution and
   source lineage, and supports surface_now, defer, and do_not_surface.
4. Muse, Provenance, and deterministic memory-evidence release execute after
   the surfacing decision, including safe ordinary responses for silence.
5. A complete replay/grading path executes conversational_v1 and records
   capture, curation, fresh-session memory use, surfacing, release, and
   no-change outcomes. The offline surfacing runner alone is insufficient.
6. The current models.py and validate_scenario.py contracts represent all
   runtime dependencies and outcome references without fabricated records.

If any prerequisite is absent, stop and report it. Do not weaken the Objective,
replace Lines with OfflineInput, invent runtime Props, or treat an offline
decision score as proof of conversational release.

Write exactly these two files beside this prompt:
  SCENARIO_DIRECTORY/backstory.json
  SCENARIO_DIRECTORY/ground-truth.json

You have read-only access to the checkout except for those two authorized
outputs. Inspect these paths at invocation time:
  synthetic-journal-evaluation/evaluation-objectives.yaml
  docs/specification.md (Sections 4.2.5 and 7.2.1)
  evals/synthetic_journals/models.py
  evals/synthetic_journals/validate_scenario.py
  evals/synthetic_journals/conversational_surfacing_contract.py
  src/linger/orchestration/conversational_memory.py
  src/linger/orchestration/surfacing.py
  src/linger/contracts/surfacing.py
  src/linger/agents/muse/
  src/linger/agents/sculptor/
  src/linger/services/memory.py

Create one memory-only Scenario for one person and one evaluation account with
one Backstory, earlier source Props, seven ordered conversational Scenes, and
one natural Line per Scene. Seed only earlier source Props. Keep captured
memories, curation results, derived records, and runtime identifiers out of
Props. All later Scenes must start fresh sessions and refer to earlier work only
through symbolic prerequisite outcomes.

The seven Scenes must cover: a preference-update capture; useful timely
surfacing; a matched deferred time contrast; cancellation or replacement;
prior surfacing/dismissal repetition; superficial thematic overlap; and a
sensitive or speculative inference that must remain unsurfaced. Keep capture
enablement, session reset, decision time, and prior feedback as workflow state,
not conversational controls. Do not put expected decisions in Lines or Props.

Write separate proposed Ground truth containing exact Line/Prop spans, capture
and curation expectations, symbolic source lineage, expected and prohibited
released behavior, and the timely/deferred pairing. Use only the fields and
contracts defined by models.py. Do not choose evaluator thresholds, judge
rubrics, adoption status, or downstream grades.

The separate ground truth file is a proposed answer key, not a runtime input.

Before finishing, run the unchanged deterministic validator against both files.
The validator only establishes objective facts and contract conformance; it
does not decide whether the proposed labels are semantically correct. Report
validation output separately and leave Ground truth status as proposed.
```

## Ground truth lifecycle

The generator writes proposed Ground truth separately from the Backstory. The
unchanged deterministic validator checks objective facts and graph integrity;
an independent reviewer later adopts, revises, or rejects each candidate.
Only adopted Ground truth may grade a run, and no Ground truth enters Linger.

## Architecture and academic relevance

The target exercises the five-agent authority boundaries: Muse owns wording,
Librarian and application services own bounded retrieval, Sculptor owns the
surfacing proposal, Provenance owns review, and Memory & Policy owns writes and
release enforcement. It demonstrates the briefing's requested multi-agent
coordination and responsible scenario-based assurance through observable
source lineage and appropriate silence.
