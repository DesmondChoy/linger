# Synthetic journal evaluation

## Package contract

The package has two JSON files: `backstory.json` contains the generated
Backstory, Props, Scenes, Lines, and offline inputs; `ground-truth.json` contains
only proposed Ground truth and hashes the exact `backstory.json` bytes. One
package contains one Backstory, person, and evaluation account; build a full
dataset from multiple independently validated packages.

Checked-in authoring packages live under
`synthetic-journal-evaluation/packages/<scenario-set>--<agents>--<YYYY-MM-DD>/`. The human-only
`pre-generation-report.md` sits beside `backstory.json` and
`ground-truth.json` but is not validator input. Shared resolved constraints
remain under `synthetic-journal-evaluation/generation-presets/` because packages
reference them by ID and the validator applies them across packages.

Book packages store shared Scene facts in `ProposedGroundTruth.book_scene_facts`.
Each book proposal stores one discriminated `book_expectation` that matches its
Objective ID. Generic `grounding` belongs only to
`weak_evidence_safe_decline`.

## Model configuration

Provider-backed runners use `LINGER_MODEL` and the matching API key from the
repository-root `.env`. The example configuration selects
`openai:gpt-5.6-luna`. The application requires an explicit model setting.
Supported prefixes are `google:`, `openai:`, and `anthropic:`, paired with
`GOOGLE_API_KEY`, `OPENAI_API_KEY`, and `ANTHROPIC_API_KEY`. These runners have
no model-selection CLI option.

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

1. Invoke the `generate-synthetic-journals` skill. A human selects one or more
   Objectives in the loopback selector and confirms the complete selection.
2. The skill creates a descriptively named package directory containing only
   `pre-generation-report.md`. Selection confirmation is not generation
   approval.
3. A human reads the report and approves its design and detached generator
   prompt, requests changes, or abandons the attempt. Generation proceeds only
   after separate approval and only when the prompt is runnable or all named
   preconditions have been met.
4. A separately authorized generator writes `backstory.json` and
   `ground-truth.json` beside the report. Validate both files with the command
   below.
5. Invoke the `review-synthetic-ground-truth` skill. A human independent of the
   generator approves or flags every proposed Ground truth row.
6. **Make Changes** returns the decision without writing an adoption or starting
   runtime. Confirmation writes `ground-truth-adoption.json`. For an exact
   supported selection, the agent validates that adoption and starts one
   provider-backed replay. Supported selections include capture, curation,
   continuity, either book Objective alone, both book Objectives in
   either order, either connection or weak-evidence Objective alone, and their
   combined selection. Other selections stop after adoption.
7. Inspect the experiment in Pydantic Evals and the Logfire Agents, LLMs and
   providers, and Live views. Keep the runner's JSON output as the durable,
   complete evaluation record.

The local selectors and reviewer return decisions to the agent. Neither browser
server invokes a generator, model, or replay runner.

The adopted `proactive_memory_surfacing` Objective includes a conversational
sequence: a preference-update Line, reviewed capture and curation, and memory
use in a later fresh chat. The current package contract and runner do not
represent that sequence. Its pre-generation report must describe the target
and name those gaps before generation can be approved. See
[the conversational target](../../docs/specification.md#425-conversational-memory-curation-and-surfacing-target).
The direct `surfacing_replay` module remains an offline component test for
existing packages. It does not establish the expanded Objective and is not
automatically dispatched by Ground truth review. Existing adoption records
remain bound to the component expectations they approved.

The Pydantic models in `models.py` are the schema authority. Validate a package
from the repository root:

```bash
uv run python -m evals.synthetic_journals.validate_package \
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

Review a validated package with the desktop-only local app:

```bash
uv run python \
  .agents/skills/review-synthetic-ground-truth/scripts/ground_truth_reviewer.py \
  path/to/backstory.json path/to/ground-truth.json \
  --reviewer-id REVIEWER_ID
```

The reviewer command accepts these options:

- `--reviewer-id ID` records the required stable human identity.
- `--adoption PATH` selects the adoption output path. The default is
  `ground-truth-adoption.json` beside the package, and a custom path must remain
  in the same directory.
- `--ui PATH` serves another built review UI. The default is the checked-in
  `.agents/skills/review-synthetic-ground-truth/ui/dist` build.
- `--timeout SECONDS` sets the loopback server lifetime and defaults to 1800.

The command validates the package before binding to `127.0.0.1`, prints one
token-bearing `GROUND_TRUTH_REVIEW_URL`, and exits with one
`GROUND_TRUTH_REVIEW_JSON` decision. It refuses an existing adoption path,
package changes during review, a non-sibling adoption path, an incomplete
confirmation, or a timeout. It never overwrites an adoption.

The app joins each Scene's Lines, Props, offline inputs, and source setup with the complete
proposed Ground truth in one side-by-side review row. **Confirm and run
evaluation** remains disabled until the reviewer approves every row. **Make
Changes** returns the reviewed, flagged, and unchecked proposal IDs without
writing an adoption or starting runtime. Confirmation writes a separate
`ground-truth-adoption.json` beside the two immutable generated JSON files. The
adoption binds the human identity and decisions to the exact package hashes; it
does not rewrite `ground-truth.json`.

The loopback server only returns the decision. The agent validates the result
and chooses the registered runner for the exact Objective selection. The
browser never receives runtime authority or provider credentials. Automatic
post-confirmation routes cover capture, curation, continuity, either
book Objective alone, both book Objectives, either connection or weak-evidence
Objective alone, and their combination. Other selections stop after adoption.

## Capture replay

Replay the validated capture-only package through the production Muse path:

```bash
uv run python -m evals.synthetic_journals.replay \
  synthetic-journal-evaluation/packages/2026-08-23T182725+0800/backstory.json \
  synthetic-journal-evaluation/packages/2026-08-23T182725+0800/ground-truth.json \
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

The command sends the same validated synthetic run to the existing Logfire
project as service `linger-evals`, environment `synthetic-evaluation`. Pydantic
Evals creates one native case per Scene, including synthetic input, expected
output, compact actual output, and an authority-specific label. Without
`--adoption`, the runner remains an exploratory proposal comparison and emits
`proposal_comparison`. With a valid adoption, it emits
`adopted_hard_gate_grade` and uses the adopted Ground truth identity as the
dataset version.
Content-bearing Pydantic AI spans provide Logfire's LLM panels with ordered
messages, model responses, tool calls, tokens, and cost. The surrounding
application spans retain fixed agent and hand-off metadata. Normal
`linger-backend` traffic remains metadata-only.

Runtime prompt fingerprints and a prompt-set system variant identify the
evaluated static artifacts. The JSON artifact remains the durable, complete
evaluation record; Logfire is the interactive inspection and comparison view.
Emotional-boundary observations also record whether the fixed response came
from the no-tool preflight or the downstream candidate-review fallback.
The Backstory and Ground truth never enter Muse. Proposal mode reports
`matches_proposal` or `differs_from_proposal`. Adopted mode reports
`passes_hard_gates` or `fails_hard_gates`. Neither runner adopts its own labels.

Capture grades use the recorded Muse output and actual memory-store observations:

| Typed expectation | Required outcome |
|---|---|
| `capture_candidate` | A normal Muse release; exactly the expected nominated text and offsets; `allow_capture`; exact binding; one committed record with the expected text; no other writes. |
| `no_candidate` | A normal Muse release; a recorded `NoMemoryCandidate`; a `no_candidate` review decision; no binding or storage action; no writes. |

Missing Muse output and changes to earlier stored records fail the Scene. The
grader uses the final revision's nomination when Muse revises its draft. Veto
and safe-decline expectations require a separate typed replay contract and are
outside these supported cases.

After an exact, allowed commit, the runner repeats the Memory Policy call using
the observed record's account, source event, text, and evidence. It requires the
same record, `created=False`, and unchanged stored records. This is a policy
idempotency check, without another model call; HTTP retry identity remains a
separate runtime concern. Ground truth never supplies a storage candidate.

Artifact schema 2 records the complete typed expectation, observed nomination,
per-Scene `hard_failures`, storage observations, and policy retry result. The
native evaluation label uses the same failures as the durable artifact. Earlier
nomination-only runs cannot establish these outcomes. The checked-in capture
package remains proposed and needs independent human adoption and a fresh
provider-backed run before it supplies adopted evaluation evidence.

The capture command accepts `--adoption PATH` only for an adoption that validates
against the exact Backstory and proposed Ground truth bytes. `--output PATH`
writes the durable JSON artifact to that path; without it, the complete artifact
is written to stdout. The command rejects mixed Objectives, Props, offline
inputs, continued sessions, or any Scene that does not contain exactly one
Line.

## Bounded-curation replay

Replay a validated bounded-curation package through production Sculptor:

```bash
uv run python -m evals.synthetic_journals.curation_replay \
  path/to/backstory.json path/to/ground-truth.json \
  --output /tmp/bounded-memory-curation-run.json
```

This runner accepts generated Props only. For each isolated Scene, application
code resolves the active, same-account Props into one
`AccountScopedMemories` value and calls `propose_curation`. Sculptor receives
only memory IDs and text, has no function tools or write surface, and never
receives the Backstory or proposed Ground truth. The durable artifact records
every source hash before and after the call, the complete observable Sculptor
exchange, the typed response, deterministic hard-gate comparison, and separate
semantic criteria. Proposal mode remains an exploratory comparison. Adopted
mode grades deterministic hard gates while continuing to expose semantic
criteria for separate review; a hard-gate pass is not a semantic-quality claim.

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

Evaluate Sculptor's bounded surfacing decision with a validated offline package:

```bash
uv run python -m evals.synthetic_journals.surfacing_replay \
	path/to/backstory.json path/to/ground-truth.json \
	--adoption path/to/ground-truth-adoption.json \
	--output /tmp/proactive-memory-surfacing-component-run.json
```

The direct command accepts only `proactive_memory_surfacing`, with one
`OfflineInput` and no Lines per fresh Scene. Each input supplies a timezone-aware
decision time, current context, up to twenty prior surfaced or dismissed items,
and at most twelve active, same-account memories. The compiler resolves these
memories from the Scene's Props and keeps proposed decisions out of the input.

A package covers timely, deferred, superseded, repeated, unsupported, and
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
Ground truth review therefore stops after adoption for this Objective instead
of dispatching the component command as a complete evaluation.

## Session-continuity replay

Replay a validated session-continuity package through the production chat
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

## Weak-evidence reflection replay

Replay a validated `weak_evidence_safe_decline` package through production chat:

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

Replay a validated book package through the production
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
clarification comparisons. A combined package includes a shared inferred Scene.
The runner does not require exactly one Prop or three Scenes.

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

Required retrieval passes only when Librarian returns evidence and the released
response cites permitted evidence. A route or an attempted search does not
satisfy that expectation. Clarification Scenes must release the exact
application-owned question without retrieving evidence or granting a ceiling.
Non-factual reflection comparisons must avoid both routing and book retrieval.

`book_scene_facts` records shared work identity, scope, exact basis spans, and
`corpus_text` excerpts. The compiler checks registered corpus integrity and
resolves each excerpt to its exact source occurrence and supported paragraph
or hybrid windows. The grader compares full evidence records, including work,
version, chapter, source hash, location, source lines, and text. Equal text at
another location cannot pass. Each proposal's `book_expectation` owns only its
Objective-specific judgment.

By default, spoiler checks cover scope, evidence, and exact forbidden text.
With separate approval, add `--semantic-review` for an additional model review
of paraphrased disclosure. Its `pass`, `fail`, `not_run`, or `error` result is
stored separately and labeled non-independent. It does not change the hard
grade or establish semantic accuracy. Human review remains necessary.

The command shares the other runners' proposal, adoption, and output behavior.
It does not adopt labels. Historical book packages using the removed fields
remain unchanged but are obsolete replay inputs. New Ground truth requires new
independent review; an old adoption cannot approve changed shared Scene facts.

## Connection and restraint replay

Replay `cross_source_tentative_connection`, `weak_evidence_safe_decline`, or
both in either order:

```bash
LINGER_WEB_SEARCH_ENABLED=true uv run python -m evals.synthetic_journals.connection_replay \
  path/to/backstory.json path/to/ground-truth.json \
  --adoption path/to/ground-truth-adoption.json \
  --output /tmp/connection-restraint-run.json
```

Live public retrieval requires `EXA_API_KEY`. The command enables web retrieval
for this run; packages without public sources do not require that setting.

Each typed Scene has one Line in a fresh session. Its `source_setups` entry in
`backstory.json` supplies any reader-confirmed book scope and complete public
snapshots: source identifier, URL, title, text, SHA-256, and retrieval time.
Active Props supply the account's memory records. These are runtime inputs.
`GroundTruthProposal.connection` separately declares the expected decision,
permitted and required evidence, acceptable responses, and required public
claims. Evidence references resolve exact Prop, corpus, and public-source spans.
The validator checks source hashes, scope, and references before independent
review. Neither proposed nor adopted Ground truth enters runtime.

The runner bounds public retrieval to the supplied source URLs, seeds isolated
memory storage, and executes the production chat path with automatic capture
disabled. Exa searches and opens public pages live. Snapshots establish the
adopted source identity and exact support for grading; missing or changed live
evidence cannot pass as intended restraint. The recorded path includes Muse invocation,
retrieval, Serendipity selection, Muse presentation, Provenance review, and
deterministic release. It retains the released response and distinguishes the
first failed stage from stages that were not reached. The supplied URL bounds
make this a controlled source test; it does not establish general search coverage.

Hard checks establish source resolution, the typed decision, citation bounds,
release behavior, and source immutability. A reviewer still judges whether the
connection is useful and tentative, restraint is honest, and public claims are
supported. Deterministic success does not establish semantic success. Legacy
weak-evidence-only packages with `grounding` expectations delegate to
`reflection_replay` and retain its existing, narrower hard checks.

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
