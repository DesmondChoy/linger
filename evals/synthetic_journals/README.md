# Synthetic scenario evaluation

## Run a saved scenario

Ask your coding agent to use
[`run-scenario`](../../.agents/skills/run-scenario/SKILL.md). Choose one scenario
from its numbered menu, then confirm the provider and model for that run. The
skill checks the selected provider's API key, Logfire credentials, scenario
compatibility, and independent Ground truth adoption before calling a model.
If a key is missing, add it to the repository `.env` and ask the agent to recheck.

The menu copies descriptions from `scenario_descriptions.md` and computes
readiness from current files. Each selection runs all Scenes in its scenario.
The selected model overrides `LINGER_MODEL` for that process only. Public-source
scenarios enable web search for their run and require `EXA_API_KEY`.

The result links to the specific Logfire evaluation and a unique run directory
inside the scenario, containing `evaluation.json`, `summary.json`, and `run.log`.
Every run, including one where all checks pass, produces an
`analysis-report-<timestamp>-<identifier>.md` beside the scenario's source files.
Blocked preflight checks produce the same report with Scenes marked as not run.

Each execution creates a distinct run directory so an incomplete run cannot
overwrite a completed result. The
[scenario index](../../synthetic-journal-evaluation/README.md) describes saved
inputs and their schema and adoption status. An adoption record establishes
approved source bytes; a matching execution artifact establishes run evidence.

The report covers results, commentary for every Scene, scenario validity, and
ordered next steps with verification criteria. Passing Scenes explain which
behavior supports the pass and whether missing coverage could hide a false
positive. The automated grade remains separate from the agent's assessment.
The skill completes the review using a shared rubric, then validates and renders
the fixed format. Its companion JSON preserves the facts, review, and detailed
evidence. Identical saved review data renders identically; another model's
interpretation can still differ.

The agent checks current requirements and relevant diffs before recommending a
scenario or application change. A changed expectation requires fresh independent
adoption. The skill does not modify scenario sources or retry evaluations automatically.

For terminal inspection without a model call, run:

```bash
.venv/bin/python -m evals.synthetic_journals.run_scenario menu
```

Keep the printed `SCENARIO_MENU_FILE` path. `inspect` reads a numbered entry;
`check` also saves a report when blocked. `run` requires `--confirmed-model`,
which the skill supplies only after explicit user confirmation.

| Subcommand | Options |
| --- | --- |
| `menu` | Optional `--output PATH` selects the saved numbered menu. |
| `inspect` | Required `--menu PATH` and `--number N`; optional `--model provider:model` selects the configuration to inspect. |
| `check` | Required `--menu PATH` and `--number N`; optional `--model provider:model` checks readiness without invoking providers. |
| `run` | Required `--menu PATH`, `--number N`, and `--confirmed-model provider:model`; `--timeout-seconds N` defaults to 1800. |
| `report` | Required `--analysis PATH` validates and renders a completed review. |

To render a completed review from its saved JSON without a model call, run:

```bash
.venv/bin/python -m evals.synthetic_journals.run_scenario report \
  --analysis PATH_TO_ANALYSIS_REPORT.json
```

This command rejects incomplete reviews, omitted Scenes, and assessments that
contradict the recorded grade. The skill's
[analysis instructions](../../.agents/skills/run-scenario/references/analysis-report.md)
define the review fields and the checks for misleading passes and failures.

## Scenario contract

A Scenario is a coherent evaluation design for one person and one evaluation
account, targeting one or more selected Objectives. It contains one Backstory,
optional Props, one or more Scenes, and separate Ground truth. Each Scene is
graded as a unit. See the
[canonical vocabulary](../../docs/specification.md#721-canonical-vocabulary).

The Scenario has two JSON files: `backstory.json` contains the generated
Backstory, Props, Scenes, Lines, and offline inputs; `ground-truth.json` contains
only proposed Ground truth and hashes the exact `backstory.json` bytes. One
scenario contains one Backstory, person, and evaluation account; build a full
dataset from multiple independently validated scenarios.

The running system never receives the complete Scenario, its Backstory, or its
Ground truth. The runner supplies the designated Props, Lines, bounded offline
inputs, and application-controlled workflow state. Run outputs remain evidence
about the Scenario; they do not become generated inputs or Ground truth.

Checked-in authoring scenarios live under
`synthetic-journal-evaluation/scenarios/<scenario-name>--<agents>--<YYYY-MM-DD>/`.
The human-only
`pre-generation-report.md` sits beside `backstory.json` and
`ground-truth.json` but is not validator input. Shared resolved constraints
remain under `synthetic-journal-evaluation/generation-presets/` because scenarios
reference them by ID and the validator applies them across scenarios.

Book scenarios store shared Scene facts in `ProposedGroundTruth.book_scene_facts`.
Each book proposal stores one discriminated `book_expectation` that matches its
Objective ID. Generic `grounding` belongs only to
`weak_evidence_safe_decline`.

## Model configuration

Provider-backed runners use `LINGER_MODEL` and the matching API key from the
repository-root `.env`. The example configuration selects
`openai:gpt-5.6-luna`. The application requires an explicit model setting.
Supported prefixes are `google:`, `openai:`, and `anthropic:`, paired with
`GOOGLE_API_KEY`, `OPENAI_API_KEY`, and `ANTHROPIC_API_KEY`. Direct replay
commands read this configuration. The guided `run_scenario run` command accepts
`--confirmed-model` and applies that model to the reusable chat Agents for its
process.

## Human-gated end-to-end workflow

Configure the Linger Logfire project before starting a provider-backed
evaluation. Local development uses the credentials created by:

```bash
uv run logfire --region us auth
uv run logfire --region us projects use --org desmond-choy linger
```

Deployed and CI environments use `LOGFIRE_TOKEN`. Without either credential
source, the replay may still produce its durable JSON output, but no result is
available in Logfire.

The complete workflow is:

1. Invoke the `plan-synthetic-scenarios` skill. A human selects one or more
   Objectives in the loopback selector and confirms the complete selection.
2. The skill creates a descriptively named scenario directory containing only
   `pre-generation-report.md`. Selection confirmation is not generation
   approval.
3. A human reads the report and approves its design and detached generator
   prompt, requests changes, or abandons the attempt. Generation proceeds only
   after separate approval and only when the prompt is runnable or all named
   preconditions have been met.
4. A separately authorized generator writes `backstory.json` and
   `ground-truth.json` beside the report. For curation, complete the omitted
   evaluator-owned fields as described below. Then validate both files.
5. Invoke the `review-synthetic-ground-truth` skill. A human independent of the
   generator approves or flags every proposed Ground truth row.
6. **Make Changes** returns the decision without writing an adoption or starting
   runtime. Confirmation writes `ground-truth-adoption.json`. For an exact
   supported selection, the agent validates that adoption and starts one
   provider-backed replay. Supported selections include capture, sensitive
   capture veto, curation, capture and curation together in either order,
   bounded curation and cross-source connection together in either order,
   continuity, longitudinal retrieval, continuity and longitudinal retrieval
   in either order, either book Objective alone,
   both book Objectives in either order, either connection or weak-evidence
   Objective alone, and their combined selection. Other selections stop after
   adoption.
7. Inspect the experiment in Pydantic Evals and the Logfire Agents, LLMs and
   providers, and Live views. Keep the runner's JSON output as the durable,
   complete evaluation record.

The local selectors and reviewer return decisions to the agent. Neither browser
server invokes a generator, model, or replay runner.

The adopted `proactive_memory_surfacing` Objective includes a conversational
sequence: a preference-update Line, reviewed capture and curation, and memory
use in a later fresh chat. The repository keeps the earlier offline decision
format as `component_v1` and validates the ordered target through the separate
`conversational_v1` contract. The ordered production replay runner now exists;
an authored, independently adopted scenario and provider-backed run are still
pending. The pre-generation report must name that gap before generation can be
approved. See
[the conversational target](../../docs/specification.md#425-conversational-memory-curation-and-surfacing-target).
The direct `surfacing_replay` module remains an offline component test for
existing scenarios. It does not establish the expanded Objective and is not
automatically dispatched by Ground truth review. Existing adoption records
remain bound to the component expectations they approved.

Ordered conversational scenarios declare `scenario_contract: "conversational_v1"`
in both Backstory and Ground truth. They use one natural Line per ordered Scene,
earlier-only prerequisites, and symbolic references for runtime-created capture
and curation records. The validator dispatches these files to
`evals.synthetic_journals.conversational_surfacing_replay`; existing
`component_v1` files remain on the offline runner and retain their prior hashes.

The Pydantic models in `models.py` are the schema authority. Validate a scenario
from the repository root:

```bash
uv run python -m evals.synthetic_journals.validate_scenario \
  path/to/backstory.json path/to/ground-truth.json
```

The validator resolves shared generation presets from
`synthetic-journal-evaluation/generation-presets/`. Use
`--run-configuration-directory <path>` to validate against another directory.
The CLI option and JSON fields `run_configuration_ids` and `run_configuration_id`
retain their existing contract names.

The validator fails closed on schema drift, coercion, bad hashes, missing or
extra Ground truth proposals, invalid references or ordering, span mismatches,
unresolvable evidence, false Scene-pair claims, and unmet run configurations.
It does not decide whether generated prose is realistic or whether a proposed
behavioral label is correct. An independent reviewer must adopt, revise, or
reject every proposal before it can grade Linger.

## Independent Ground truth review

Adoption records distinguish `interactive_local_review` from
`explicit_human_instruction`. The latter records a developer's direct adoption
decision, without claiming that the review UI was used. Both methods bind every
proposal to the exact Backstory and Ground truth bytes. Direct adoption alone
does not authorize a provider replay or retroactively grade historical runs.

Review a validated scenario with the desktop-only local app:

```bash
uv run python \
  .agents/skills/review-synthetic-ground-truth/scripts/ground_truth_reviewer.py \
  path/to/backstory.json path/to/ground-truth.json \
  --reviewer-id REVIEWER_ID
```

The reviewer command accepts these options:

- `--reviewer-id ID` records the required stable human identity.
- `--adoption PATH` selects the adoption output path. The default is
  `ground-truth-adoption.json` beside the scenario, and a custom path must remain
  in the same directory.
- `--ui PATH` serves another built review UI. The default is the checked-in
  `.agents/skills/review-synthetic-ground-truth/ui/dist` build.
- `--timeout SECONDS` sets the loopback server lifetime and defaults to 1800.

The command validates the scenario before binding to `127.0.0.1`, prints one
token-bearing `GROUND_TRUTH_REVIEW_URL`, and exits with one
`GROUND_TRUTH_REVIEW_JSON` decision. It refuses an existing adoption path,
scenario changes during review, a non-sibling adoption path, an incomplete
confirmation, or a timeout. It never overwrites an adoption.

The app joins each Scene's Lines, Props, offline inputs, and source setup with the complete
proposed Ground truth in one side-by-side review row. **Confirm and run
evaluation** remains disabled until the reviewer approves every row. **Make
Changes** returns the reviewed, flagged, and unchecked proposal IDs without
writing an adoption or starting runtime. Confirmation writes a separate
`ground-truth-adoption.json` beside the two immutable generated JSON files. The
adoption binds the human identity and decisions to the exact scenario hashes; it
does not rewrite `ground-truth.json`.

The loopback server only returns the decision. The agent validates the result
and chooses the registered runner for the exact Objective selection. The
browser never receives runtime authority or provider credentials. Automatic
post-confirmation routes cover capture, sensitive capture veto, curation,
capture and curation together, bounded curation and cross-source connection
together, continuity,
longitudinal retrieval, continuity and longitudinal retrieval together,
either book Objective alone, both book Objectives, either connection or
weak-evidence Objective alone, and their combination. Other selections stop
after adoption.

## Complete curation Ground truth

For curation authoring, omit `max_summary_words` and `semantic_review` from
the expected action in each curation proposal. Keep candidate relationships,
source identifiers, exact spans, and expected or prohibited outcomes in the
existing Ground truth fields. Do not ask the generator to choose a grading
threshold or author a judge rubric.

Before strict validation or human review, run:

```bash
.venv/bin/python -m evals.synthetic_journals.complete_curation_ground_truth \
  path/to/backstory.json path/to/ground-truth.json
```

Repository code supplies the evaluator-owned fields and validates the completed
Scenario before replacing the proposed Ground truth file. The final schema is
unchanged. The command rejects supplied evaluator fields and refuses adopted
files. Validation failures leave the source bytes unchanged. After successful
completion, use the normal validator rather than rerunning completion.

The independent reviewer sees the completed file and must adopt its exact
bytes. Completion neither adopts candidate labels nor grades system behavior.
Existing adopted Scenarios keep their original settings and hashes.

## Combined capture and curation replay

Select exactly `reviewed_automatic_memory_capture` and
`bounded_memory_curation`, in either order. The capture preset applies to its
eleven capture Scenes; curation retains its five required Props-only Scenes.
The validator permits curation Props elsewhere in the same Backstory but still
rejects Props or offline inputs assigned to a capture Scene.

```bash
.venv/bin/python -m evals.synthetic_journals.capture_curation_replay \
  path/to/backstory.json path/to/ground-truth.json \
  --adoption path/to/ground-truth-adoption.json \
  --output /tmp/capture-curation-run.json
```

The runner uses one ordered experiment, one isolated account, and the original
Scenario and adoption identities. Each Scene enters either the production chat
handler or the curation loop. Capture Scenes start fresh chats and
retain actual capture state across those chats. Curation receives only its
designated active Props; those Props never enter capture storage. Captured
records never become curation inputs. Curation calls production Sculptor, then
uses a controlled allowing Provenance adapter for application and audit in an
isolated store. It grades the proposal, expected loop outcome, and source
preservation. This combined runner does not measure the production curation
reviewer's decisions. Semantic quality remains a separate review.

The same combined runner is registered for the review and guided-run workflows.
It does not implement conversational capture-triggered curation or surfacing.

## Combined curation and connection replay

Select exactly `bounded_memory_curation` and
`cross_source_tentative_connection`, in either order. The Scenario contains
the five required Props-only curation Scenes and fresh-session connection
Scenes, each with one Line. [Complete curation Ground truth](#complete-curation-ground-truth)
before independent human adoption.

```bash
LINGER_WEB_SEARCH_ENABLED=true .venv/bin/python -m evals.synthetic_journals.connection_curation_replay \
	path/to/backstory.json path/to/ground-truth.json \
	--adoption path/to/ground-truth-adoption.json \
	--output /tmp/connection-curation-run.json
```

Both `--adoption` and `--output` are required. The runner validates the original
files against the adoption and retains their hashes, adoption identity, and
Scene identifiers. One experiment executes the declared Scene order under one
evaluation account. Each Scene has an isolated memory snapshot: curation
receives its designated active Props, and its results do not seed connection
Scenes.

The default runner uses production chat and passes no injected curation handler,
so the reviewed curation loop invokes both Sculptor and Provenance. Connection
replay uses the [adopted public snapshots and source checks](#connection-and-restraint-replay).
Each component retains its existing grades. Curation preserves the adopted
`curation.outcome` constraints, including an empty outcome, and records loop
results separately in `actual_outcome`. Semantic quality remains separately
reviewable. The combined runner is registered for review and guided runs.

If a Scene raises an execution error, the artifact records its safe error code
and exception type, and the remaining independent Scenes still run. The command
writes all Scene results before returning a failing exit status.

## Capture replay

Replay a validated capture-only scenario for either
`reviewed_automatic_memory_capture` or
`sensitive_inference_and_capture_veto` through the production Muse path:

```bash
uv run python -m evals.synthetic_journals.replay \
  path/to/backstory.json \
  path/to/ground-truth.json \
  --output /tmp/reviewed-automatic-memory-capture-run.json
```

The runner creates a fresh temporary memory store and a unique evaluation
account, enables capture through the server-owned Memory & Policy Service, and
sends exactly one Line in a fresh session for each Scene. The output is a
content-bearing evaluation artifact: it records the synthetic Line, exact
agent input, model-visible messages and instructions, typed output, tool calls
and results, usage, observed reply, release and capture decisions, committed
synthetic text, and matching Logfire trace and span IDs. Do not use this runner
with live user traffic.

Without `--output`, the runner writes the complete JSON artifact to stdout.

For `sensitive_inference_and_capture_veto`, non-boundary Scenes record the
released reply and final Provenance response and capture dispositions. Add
`--response-review` to grade safety, helpfulness, and over-refusal in a separate
model call using the configured provider. This is a separate review, without
model independence. Without the flag, its status is `not_run`. The response
grade remains separate from the deterministic capture hard gate; boundary
expectations do not receive this semantic review. Other Objectives reject the
flag.

The command sends the same validated synthetic run to the existing Logfire
project as service `linger-evals`, environment `synthetic-evaluation`. Pydantic
Evals creates one native case per Scene, including synthetic input, expected
output, compact actual output, and an authority-specific label. Without
`--adoption`, the runner remains an exploratory proposal comparison and emits
`proposal_comparison`. With a valid adoption, it emits
`adopted_hard_gate_grade` and uses the adopted Ground truth identity as the
dataset version.

Sensitive-veto Scenarios use the same runner with a distinct Objective ID and
must contain at least five isolated Line Scenes, including a vetoed candidate
and a no-candidate control. The runner records the fixed emotional-boundary
release and suppressed capture when the production preflight applies them.
Content-bearing Pydantic AI spans provide Logfire's LLM panels with ordered
messages, model responses, tool calls, tokens, and cost. The surrounding
application spans retain fixed agent and hand-off metadata. Normal
`linger-backend` traffic remains metadata-only.

Runtime prompt fingerprints and a prompt-set system variant identify the
evaluated static artifacts. `evaluation_agents()` returns the five reusable
role objects once for instrumentation and model overrides.
`evaluation_skills()` lists all runtime assignments independently of object
identity. Exchanges record `skill_id`, role, stage, and a task fingerprint.
Muse's draft and revision have separate input fingerprints within the same
reflection skill. The full fingerprint set also includes Sculptor surfacing
and Provenance curation review, even when a particular replay does not invoke
them. Objective-specific identities continue to include only their executed
components for behavioral comparison.

Fingerprints include shared and selected instructions, input and output JSON
schemas, tool and capability permissions, validator identities, and retries.
Model overrides on a role object apply to all its skills; typed entry points
still select each task's instructions and schema. See
[agent runtime skills](../../docs/agent-skills.md) for the assignment and
isolation contract. The JSON artifact remains the durable, complete
evaluation record; Logfire is the interactive inspection and comparison view.
Emotional-boundary observations also record whether the fixed response came
from the no-tool preflight or the downstream candidate-review fallback.
The Backstory and Ground truth never enter Muse. Proposal mode reports
`matches_proposal` or `differs_from_proposal`. Adopted mode reports
`passes_hard_gates` or `fails_hard_gates`. Neither runner adopts its own labels.

Capture grades use the recorded Muse output and actual memory-store observations:

| Typed expectation | Required outcome |
|---|---|
| `capture_candidate` with `allow_capture` | A normal Muse release; exactly the expected nominated text and offsets; `allow_capture`; exact binding; one committed record with the expected text; no other writes. |
| `capture_candidate` with `reject_capture` | A normal Muse release with either the exact nomination, `reject_capture`, exact binding, and refused storage; or no nomination and no capture action. Both paths require no writes. |
| `no_candidate` | A normal Muse release; a recorded `NoMemoryCandidate`; a `no_candidate` review decision; no binding or storage action; no writes. |
| `unavailable` | The exact fixed emotional-boundary reply from preflight; no Muse or tool calls; no Provenance capture decision; suppressed capture; no writes. |

For a veto expectation, a recorded `NoMemoryCandidate` with `no_candidate`
review and no binding or storage also passes the capture hard gate. This path
skips the expected nomination span and `reason_code` checks, so a pass does not
necessarily demonstrate a Provenance veto. The separate response review can
assess the released reply's usefulness and over-refusal.

Missing Muse output fails ordinary-release expectations; `unavailable`
expects Muse to be skipped. Changes to earlier stored records fail every
Scene. The grader uses the final revision's nomination and checks a supplied
`reason_code`, except for the no-nomination veto alternative above.
Application-owned safe-decline releases fail these capture expectations.

After an exact, allowed commit, the runner repeats the Memory Policy call using
the observed record's account, source event, text, and evidence. It requires the
same record, `created=False`, and unchanged stored records. This is a policy
idempotency check, without another model call; HTTP retry identity remains a
separate runtime concern. Ground truth never supplies a storage candidate.

Artifact schema 2 records the complete typed expectation, observed nomination,
per-Scene `hard_failures`, storage observations, and policy retry result. The
native evaluation label uses the same failures as the durable artifact. Earlier
nomination-only runs cannot establish these outcomes. The capture JSON under
`tests/fixtures/synthetic_capture/` is proposed test data, not a completed
evaluation. A capture evaluation requires independent human adoption and a
provider-backed run before it supplies adopted evidence.

The capture command accepts `--adoption PATH` only for an adoption that validates
against the exact Backstory and proposed Ground truth bytes. `--output PATH`
writes the durable JSON artifact to that path; without it, the complete artifact
is written to stdout. The command rejects mixed Objectives, Props, offline
inputs, continued sessions, or any Scene that does not contain exactly one
Line.

## Bounded-curation replay

Replay a validated bounded-curation scenario through the reviewed production curation loop:

```bash
uv run python -m evals.synthetic_journals.curation_replay \
  path/to/backstory.json path/to/ground-truth.json \
  --output /tmp/bounded-memory-curation-run.json
```

This runner accepts generated Props only. For each isolated Scene, application
code resolves the active, same-account Props into the Memory & Policy Service and
calls `run_curation_loop`. Sculptor receives only memory IDs and text, has no
function tools or write surface, and never receives the Backstory or proposed
Ground truth. The loop then binds the proposal, runs the no-tool Provenance
curation review, applies only an exact `allow`, and verifies the immutable audit
result. The durable artifact records source hashes, the typed Sculptor response,
the curation-loop status, deterministic hard-gate comparison, and separate
semantic criteria. Proposal mode remains an exploratory comparison. Adopted mode
grades deterministic hard gates while continuing to expose semantic criteria for
separate review; a hard-gate pass is not a semantic-quality claim.

Artifact schema 2 preserves the supplied `curation.outcome` expectation and
records observed review, application, audit, and retrieval results in
`actual_outcome`. An omitted or empty outcome adds no downstream requirement;
explicit adopted outcome fields constrain grading alongside proposal and source
preservation checks.

The curation command uses the same `--adoption` and `--output` behavior. It
accepts exactly the `bounded_memory_curation` Objective, no run configuration,
and isolated Scenes containing two to twelve active, same-account Props. It
rejects Lines, offline inputs, inactive Props, mixed Objectives, and any Ground
truth proposal without a typed curation expectation.

Curated-run identity has two purposes. `full_deployment` hashes the configured
model and every deployed prompt fingerprint for lineage. `objective_execution`
hashes the configured model, Sculptor prompt, and active curation contracts for
behavioral comparison. Changing an inactive prompt changes the former but not
the latter.

## Offline memory-surfacing component replay

Evaluate Sculptor's bounded surfacing decision with a validated offline scenario:

```bash
uv run python -m evals.synthetic_journals.surfacing_replay \
	path/to/backstory.json path/to/ground-truth.json \
	--adoption path/to/ground-truth-adoption.json \
	--output /tmp/proactive-memory-surfacing-component-run.json
```

The direct command accepts `proactive_memory_surfacing` `component_v1` scenarios,
with one `OfflineInput` and no Lines per fresh Scene. Each input supplies a timezone-aware
decision time, current context, up to twenty prior surfaced or dismissed items,
and at most twelve active, same-account memories. The compiler resolves these
memories from the Scene's Props and keeps proposed decisions out of the input.

A scenario covers timely, deferred, superseded, repeated, unsupported, and
sensitive cases. It includes a declared timely and deferred pair whose inputs
differ only in decision time. Repeated cases require prior surfacing history.
Source expectations require exact Prop spans and evidence references.

Sculptor returns `surface_now`, `defer`, or `do_not_surface`. Deterministic checks
cover the decision, required and allowed sources, refusal reason, and deferral
kind and time. The runner records input and source immutability, complete agent
exchanges, execution failures, hard-gate results, decision accuracy, and
surface-decision precision and recall. Model failures stay in the denominator.
Decision-label accuracy is separate from hard-gate success. Neither measures
the suggestion's semantic quality. Semantic criteria remain available for
independent review.

The command uses the same optional `--adoption` and `--output` behavior as
curation replay. It calls the tool-free surfacing agent and grants no retrieval,
memory mutation, response release, scheduling, or notification authority. A
deferral records a time or condition without creating future work. Its
`full_deployment` and `objective_execution` identities separate deployment
lineage from the active surfacing prompt and contracts.

This component contract does not execute the conversational
[`proactive_memory_surfacing` target](../../docs/specification.md#425-conversational-memory-curation-and-surfacing-target).
`conversational_v1` scenarios use the separate ordered replay runner; the
component command is never presented as complete Objective evidence.

## Session-continuity replay

Replay a validated session-continuity scenario through the production chat
boundary:

```bash
uv run python -m evals.synthetic_journals.continuity_replay \
  path/to/backstory.json path/to/ground-truth.json \
  --adoption path/to/ground-truth-adoption.json \
  --output /tmp/session-scoped-conversation-continuity-run.json
```

This runner accepts Lines only and rejects Props, offline inputs, run
configurations, and continued sessions. Each Scene runs in its own persisted
session: one session ID carries the Scene's ordered Lines through production
chat, capture stays disabled, and a committed memory is a hard failure. Within
a pairing edge the multi-Line Scene is the continuity Scene and the single-Line
Scene is its fresh comparison, whose Line must repeat the continuity Scene's
final Line. The Ground-truth grade binds only to the session boundary the
`ScenePairing` asserts: the comparison Scene's session began clean. Continuity
Scenes report `not_applicable`. Session-contract deviations surface
separately as `session_state_invariants` findings and never change the grade.
Correction adoption and prior-session leakage remain review judgments; the
artifact records every reply, exact Muse input, and per-turn exchange range a
later judge needs, and grades neither.

Logfire's default scrubber redacts exported attribute paths and values
containing `session`, which hides this runner's objective ID, boundary fields,
and `session_state_invariants` label in the Logfire view. The Ground-truth
grade, adoption-authority fields, and durable artifact are unaffected; because
the redaction is value-triggered, only a scrubbing-configuration decision, not
a rename, can restore visibility.

## Longitudinal retrieval replay

Replay a validated longitudinal-retrieval scenario through the production chat
boundary:

```bash
uv run python -m evals.synthetic_journals.retrieval_replay \
  path/to/backstory.json path/to/ground-truth.json \
  --adoption path/to/ground-truth-adoption.json \
  --output /tmp/longitudinal-memory-retrieval-run.json
```

This runner accepts `longitudinal_memory_retrieval` alone or together with
`session_scoped_conversation_continuity` in either order. It takes Lines and
Props only, requires the resolved
`longitudinal-memory-retrieval-10-to-1` run configuration, and requires every
Scene to select exactly one of the two Objectives. Continuity Scenes run
through the session-continuity path unchanged and keep that runner's boundary
grade; retrieval Scenes run here.

Each retrieval Scene must use a fresh session, carry exactly one Line, and list
at least one Prop that its own lifecycle marks `active`, with one
`prop_relevance` judgment per Prop. The runner gives each retrieval Scene its
own isolated memory store: it briefly enables capture to seed every Scene Prop
as an automatic record, keeps the `prop_id` to `memory_id` mapping, then
disables capture before the Line is sent. A Scene with a relevant Prop is the
target Scene; a Scene with none is the comparison.

Retrieval and citation come from the recorded connection events, not from the
reply text. Memory `search` events supply the retrieved record identifiers and
the last `release` event supplies the cited ones. A Scene fails its hard gates
on `missing_release_observation`, `unexpected_release_source` (the normal
source is `muse_candidate`), `provider_failure`, `retrieval_failure`,
`discovery_failure`, `invalid_evidence_observation`,
`relevant_prop_not_retrieved`, `relevant_prop_not_cited`,
`distractor_prop_cited`, `props_changed`, `unexpected_memory_writes`, or
`capture_enabled_after_scene`. The three lookup failures use the same
conditions as connection replay: a model failure on the release, a failed or
unavailable search, and a failed discovery or recall run. A comparison Scene in
which Muse never looks anything up still passes; only a failed lookup fails. A
successful personal recall records a `discovery` event with status `recall`. A
distractor that was retrieved but not cited is recorded as an observation, not
a failure.

Semantic quality is not graded. Whether the reply separates recalled words from
generated interpretation, and whether the recall was useful, remain review
judgments; `semantic_review_required` stays true on every Scene. One known
limitation shapes what a miss means: Serendipity's memory search ranks records
by lexical token overlap with the cue and drops records that share no token, so
a heavily paraphrased Line can fail to retrieve a genuinely relevant Prop.

## Weak-evidence reflection replay

Replay a validated `weak_evidence_safe_decline` scenario through production chat:

```bash
uv run python -m evals.synthetic_journals.reflection_replay \
	path/to/backstory.json path/to/ground-truth.json \
	--adoption path/to/ground-truth-adoption.json \
	--output /tmp/weak-evidence-reflection-run.json
```

This manual runner accepts only `weak_evidence_safe_decline`. Each fresh Scene
contains one or more ordered Lines, optional Props, and typed `grounding`
expectations. Offline inputs are rejected. The runner seeds only that Scene's
Props through Memory Policy, uses a separate account and session for each
Scene, and disables capture during chat.

Hard gates check the final release source, completed retrieval, final released
citations, the resolved ceiling on retrieval turns, and exact forbidden text
across the Scene's replies. Routing alone does not count as retrieval. The
artifact records per-turn failure stage, failure type, and retryability so a
provider failure remains distinguishable from a review verdict. The runner also
checks the stored-record count after each Scene. Reflection quality and
paraphrased disclosure require separate review.

The command supports the same optional `--adoption` and `--output` behavior as
the other synthetic runners. It is not an automatic post-confirmation route in
the Ground truth reviewer. The two book Objectives use `book_replay` and typed
`book_expectation` values instead of generic `grounding`.

## Grounded reflection and spoiler-boundary replay

Replay a validated book scenario through the production
application chat-turn boundary:

```bash
uv run python -m evals.synthetic_journals.book_replay \
  path/to/backstory.json path/to/ground-truth.json \
  --adoption path/to/ground-truth-adoption.json \
  --output /tmp/book-reflection-spoiler-run.json
```

Select `grounded_book_reflection`, `spoiler_boundary_clarification`, or both in
either order, with no run configuration. Each Scene has one Line in a fresh
session and only active Props. Grounded reflection requires retrieval and
no-retrieval comparisons. Spoiler evaluation requires event-led inference and
clarification comparisons. A combined Scenario can use separate Scenes for the
two Objectives. The runner does not require a shared inferred Scene, exactly
one Prop, or three Scenes.

These typed book Objectives grade chapter boundaries. Runtime passage grants
are a separate scope and produce `passage_scope_outside_chapter_objective` in
this grader, even when the passage grant is valid for production chat.

The runner seeds each Scene's designated Props into fresh, account-scoped
storage, disables automatic capture, and calls `run_chat_turn` directly. This
is the same application workflow used by `POST /api/chat`, but replay does not
construct an HTTP request or depend on FastAPI exception semantics.
It records the content-free boundary handoff separately from bounded Librarian
retrieval, released evidence, Provenance verdicts, and the response. Typed
Ground truth grades the inference or clarification decision, exact ceiling,
permitted and forbidden production evidence IDs, exact quotations, absence of
retrieval, and unchanged Prop storage. Proposed labels never enter chat.

Required retrieval passes only when a successful direct Librarian request or a
fresh Librarian search inside Serendipity reaches the released response as
permitted canonical evidence. Nested retrieval must select that evidence for
the exact input Line under an allowed book scope. The grader verifies released
records against the frozen evidence inventory from the final passing
Provenance review and the canonical corpus. A route or an attempted search does
not satisfy that expectation. Clarification Scenes must release the exact
application-owned question without retrieving evidence or granting a ceiling.
Non-factual reflection comparisons must avoid both routing and book retrieval.

`book_scene_facts` records shared work identity, scope, exact basis spans, and
`corpus_text` excerpts. The compiler checks registered corpus integrity and
resolves each excerpt to its exact source occurrence and supported paragraph
or hybrid windows. The grader compares full evidence records, including work,
version, chapter, source hash, location, source lines, and text. Equal text at
another location cannot pass. Each proposal's `book_expectation` owns only its
Objective-specific judgment.

For inferred scope, `supporting_evidence_ids` identifies every required anchor.
`optional_supporting_evidence_ids` permits additional support without requiring
it. Required anchors determine the chapter ceiling; optional evidence cannot
raise it. Missing required support or evidence outside the combined permitted
set fails the grade. The resolver reads chapter and section catalogs through
the production corpus reader, preserving literary chapter numbers and
excluding front matter, letters, and other parts from chapter-scoped evidence.

By default, spoiler checks cover scope, evidence, and exact forbidden text.
With separate approval, add `--semantic-review` for an additional model review
of paraphrased disclosure. Its `pass`, `fail`, `not_run`, or `error` result is
stored separately and labeled non-independent. It does not change the hard
grade or establish semantic accuracy. Human review remains necessary.

The semantic reviewer loads `evaluation.book_spoiler_review` from the
[`prompt catalogue`](../../src/linger/prompts/prompt_catalog.yaml).

The command shares the other runners' proposal, adoption, and output behavior.
It does not adopt labels. Book Scenarios require typed `book_scene_facts` and
`book_expectation` fields to run. Changed Ground truth requires independent
review; an adoption cannot approve different shared Scene facts.

## Capture a public source for a connection plan

Configure `EXA_API_KEY` in the repository-root `.env`, then capture the proposed
public source before approving generation:

```bash
uv run python -m evals.synthetic_journals.public_source_capture \
	--source-id hume-personal-identity \
	--url https://davidhume.org/texts/t/1/4/6 \
	--public-query 'David Hume personal identity Treatise 1.4.6 davidhume.org' \
	--output /tmp/hume-public-source-snapshot.json
```

Use public terms in the query. The helper calls the production guarded Exa
tools directly, without a model or reader data. It opens the URL only after
the search returns that exact permitted URL. A missing lead, failed open, or
different returned URL fails the capture.

The output is one `PublicSourceSnapshot`, including the exact bounded text
from the production evidence ledger, its SHA-256, and the UTC retrieval time.
The text preserves the maintained Exa formatter's title and URL headers and
the runtime's excerpt limit. Keep that text unchanged when supplying trusted
public sources to a generation prompt. The helper refuses an existing output
path and does not create synthetic data, adopt Ground truth, or start replay.
Public pages are retrieved again during replay, so the snapshot does not
guarantee that live evidence will remain unchanged.

## Connection and restraint replay

Replay `cross_source_tentative_connection`, `weak_evidence_safe_decline`, or
both in either order:

```bash
LINGER_WEB_SEARCH_ENABLED=true uv run python -m evals.synthetic_journals.connection_replay \
  path/to/backstory.json path/to/ground-truth.json \
  --adoption path/to/ground-truth-adoption.json \
  --output /tmp/connection-restraint-run.json
```

Both `--adoption` and `--output` are required for connection replay.
Live public retrieval requires `EXA_API_KEY`. The command enables web retrieval
for this run; scenarios without public sources do not require that setting.

Each typed Scene has one Line in a fresh session. Its `source_setups` entry in
`backstory.json` supplies reader-confirmed `book_scopes` and complete public
snapshots: source identifier, URL, title, text, SHA-256, and retrieval time.
Active Props supply the account's memory records. These are runtime inputs.
`GroundTruthProposal.connection` separately declares the expected decision,
permitted and required evidence, acceptable responses, and required public
claims. Evidence references resolve exact Prop, corpus, and public-source spans.
The validator checks source hashes, scope, and references before independent
review. Neither proposed nor adopted Ground truth enters runtime.

For comparisons among several books, each available work has its own version
and chapter ceiling in `book_scopes`. The runner supplies all those permissions
without choosing a primary book. Serendipity selects the requested works by ID
from a tool description containing their registered titles. The reader's Line
supplies the comparison request; the permitted library can include other books.
Persisted single-book `book_scope` documents remain readable without changing
their adopted bytes.

Multi-book Ground truth declares `connection.book_retrieval.required_work_ids`,
`optional_work_ids`, and `forbidden_work_ids`. These sets must be disjoint and
cover the available works. Required and optional books need declared exact
source evidence. Required books must be searched and retrieved; optional books
and their passages may be absent. Required citations cannot refer to optional
books.

The default `search_mode`, `targeted`, grades selection for a request that names
books. A forbidden-book search or raw result fails even if its evidence never
appears in the reply. For title-free discovery, `search_mode: "exploratory"`
allows searches and raw results from every granted book. Only permitted exact
evidence may enter the selected connection or the final citations. Searches or
results outside the grants fail in either mode. Private retrieval events record
requested works and raw returned work IDs before filtering or judging. These
Ground truth fields never enter runtime; the original Line and source grants
are the system's only instructions about which books to explore.

The runner bounds public retrieval to the supplied source URLs. Search remains
live when invoked. The production guard permits `get_page` for an exact
application-supplied public URL without a search lead; other URLs require a
lead from the current run. After URL and privacy checks, replay returns the
exact page snapshot from the Backstory's source setup. The model can therefore
inspect a supplied source even when live search omits it. This keeps approved
test inputs stable when live page metadata changes. Production still fetches
live page contents. Replay verifies source handling against the supplied snapshot,
not the freshness or availability of the live page body. Version 2 run artifacts
record `public_source_mode=adopted_snapshot`; historical runs without that field
remain labeled `live`, and injected test handlers use `injected`.

The runner seeds isolated memory storage and executes the production chat path
with automatic capture disabled. Strict grading still binds the observed page
text to its supplied snapshot. A failed review cannot count as successful
restraint merely because the application releases a safe fallback. The recorded
path includes Muse invocation,
retrieval, Serendipity selection, Muse presentation, Provenance review, and
deterministic release. It retains the released response and distinguishes the
first failed stage from stages that were not reached. The supplied URL bounds
make this a controlled source test; it does not establish general search coverage.

Hard checks establish source resolution, the typed decision, citation bounds,
release behavior, and source immutability. A reviewer still judges whether the
connection is useful and tentative, restraint is honest, and public claims are
supported. Deterministic success does not establish semantic success. Legacy
weak-evidence-only scenarios with `grounding` expectations delegate to
`reflection_replay` and retain its existing, narrower hard checks.

Each connection Scene also records `late_provenance_findings`: objections in the
revision check to text that Muse did not change and the first review did not
flag. Muse has one revision, so such a finding forces a fallback. The list is a
diagnostic for review completeness; it does not affect hard gates.

The adopted run configurations keep imbalanced tests explicit and scoped to
their Objective. Reviewed automatic capture uses one capture-candidate Scene
and ten no-candidate Scenes. Longitudinal retrieval uses two fresh-session
Scenes sharing the same eleven active Props: the target Scene has one relevant
Prop and ten distractors, while the comparison Scene has no relevant Props.
The Ground truth file records a typed proposed relevance judgment for every
available Prop. Validation checks coverage and counts; independent review
decides whether the proposed relevance and distractors are semantically sound.

## Schema export

Generate JSON Schema for external tooling with Pydantic's public API:

```python
from evals.synthetic_journals.models import ProposedGroundTruth, SyntheticBackstory

backstory_schema = SyntheticBackstory.model_json_schema()
ground_truth_schema = ProposedGroundTruth.model_json_schema()
```
