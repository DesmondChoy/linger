# Synthetic journal package validation

## Package contract

The package has two JSON files: `backstory.json` contains the generated
Backstory, Props, Scenes, Lines, and offline inputs; `ground-truth.json` contains
only proposed Ground truth and hashes the exact `backstory.json` bytes. One
package contains one Backstory, person, and evaluation account; build a full
dataset from multiple independently validated packages.

Checked-in authoring packages live under
`synthetic-journal-evaluation/packages/<timestamp>/`. The human-only
`pre-generation-report.md` sits beside `backstory.json` and
`ground-truth.json` but is not validator input. Shared resolved constraints
remain under `synthetic-journal-evaluation/run-configurations/` because packages
reference them by ID and the validator applies them across packages.

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
2. The skill creates a timestamped package directory containing only
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
   runtime. Confirmation writes `ground-truth-adoption.json`. For exactly one
   supported Objective, the agent validates that adoption and starts one
   provider-backed replay. The skill automatically routes reviewed automatic
   capture and bounded memory curation; other selections stop after adoption.
7. Inspect the experiment in Pydantic Evals and the Logfire Agents, LLMs and
   providers, and Live views. Keep the runner's JSON output as the durable,
   complete evaluation record.

The local selectors and reviewer return decisions to the agent; neither browser
server invokes a generator, model, or replay runner. The grounded-reflection and
spoiler-boundary runner described below is implemented for explicit invocation
after adoption, but it is not an automatic route owned by the current review
skill.

The Pydantic models in `models.py` are the schema authority. Validate a package
from the repository root:

```bash
uv run python -m evals.synthetic_journals.validate_package \
  path/to/backstory.json path/to/ground-truth.json
```

The validator resolves shared run configurations from
`synthetic-journal-evaluation/run-configurations/`. Use
`--run-configuration-directory <path>` to validate against another directory.

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

The app joins each Scene's Lines, Props, and offline inputs with the complete
proposed Ground truth in one side-by-side review row. **Confirm and run
evaluation** remains disabled until the reviewer approves every row. **Make
Changes** returns the reviewed, flagged, and unchecked proposal IDs without
writing an adoption or starting runtime. Confirmation writes a separate
`ground-truth-adoption.json` beside the two immutable generated JSON files. The
adoption binds the human identity and decisions to the exact package hashes; it
does not rewrite `ground-truth.json`.

The loopback server only returns the decision. The agent validates the result
and chooses a known objective-specific runner. The browser never receives
runtime authority or provider credentials. Automatic post-confirmation routes
cover capture, bounded curation, and session continuity. The grounded-reflection
plus spoiler-boundary runner is available for explicit invocation after adoption;
other or mixed Objectives stop after adoption.

The Objective catalog and review skill register session continuity as a
supported replay path. Confirming its Ground truth authorizes the agent to run
`evals.synthetic_journals.continuity_replay` once with the validated adoption.
The loopback server itself never invokes runtime.

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
`ScenePairing` asserts — the comparison Scene's session began clean — while
continuity Scenes report `not_applicable`. Session-contract deviations surface
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

## Grounded reflection and spoiler-boundary replay

Replay the validated three-Scene book package through the production
application chat-turn boundary:

```bash
uv run python -m evals.synthetic_journals.book_replay \
  path/to/backstory.json path/to/ground-truth.json \
  --adoption path/to/ground-truth-adoption.json \
  --output /tmp/book-reflection-spoiler-run.json
```

The package must select `grounded_book_reflection` followed by
`spoiler_boundary_clarification`, with no run configuration. It contains one
combined inference-and-grounding Scene, one ambiguous clarification comparison,
and one personal no-retrieval comparison. All three use one Line in a fresh
session. The two book-boundary Scenes share one active Prop; the personal Scene
has no Prop.

The runner seeds each Scene's designated Prop into fresh, account-scoped
storage, disables automatic capture, and calls `run_chat_turn` directly. This
is the same application workflow used by `POST /api/chat`, but replay does not
construct an HTTP request or depend on FastAPI exception semantics.
It records the content-free boundary handoff separately from bounded Librarian
retrieval, released evidence, Provenance verdicts, and the response. Typed
Ground truth grades the inference or clarification decision, exact ceiling,
permitted and forbidden production evidence IDs, exact quotations, absence of
retrieval, and unchanged Prop storage. Proposed labels never enter chat.

Repository-text evidence uses a globally unique `evidence_id` for each review
reference. The grader matches its hash-bound exact text against evidence
observed from production, so packages do not depend on a particular retrieval
index's window IDs. The command shares the other runners' proposal, adoption,
and output behavior; it does not adopt or run independent review itself.

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
