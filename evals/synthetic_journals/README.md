# Synthetic journal package validation

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

Review a validated package with the desktop-only local app:

```bash
uv run python \
  .agents/skills/review-synthetic-ground-truth/scripts/ground_truth_reviewer.py \
  path/to/backstory.json path/to/ground-truth.json \
  --reviewer-id REVIEWER_ID
```

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
runtime authority or provider credentials. Capture and bounded curation are the
only implemented confirmed replay paths; other or mixed Objectives stop after
adoption.

Replay the validated capture-only package through the production Muse path:

```bash
uv run python -m evals.synthetic_journals.replay \
  synthetic-journal-evaluation/packages/2026-08-23T182725+0800/backstory.json \
  synthetic-journal-evaluation/packages/2026-08-23T182725+0800/ground-truth.json \
  --adoption synthetic-journal-evaluation/packages/2026-08-23T182725+0800/ground-truth-adoption.json \
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

Replay a validated bounded-curation package through production Sculptor:

```bash
uv run python -m evals.synthetic_journals.curation_replay \
  path/to/backstory.json path/to/ground-truth.json \
  --adoption path/to/ground-truth-adoption.json \
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

Curated-run identity has two purposes. `full_deployment` hashes the configured
model and every deployed prompt fingerprint for lineage. `objective_execution`
hashes the configured model, Sculptor prompt, and active curation contracts for
behavioral comparison. Changing an inactive prompt changes the former but not
the latter.

The adopted run configurations keep imbalanced tests explicit and scoped to
their Objective. Reviewed automatic capture uses one capture-candidate Scene
and ten no-candidate Scenes. Longitudinal retrieval uses two fresh-session
Scenes sharing the same eleven active Props: the target Scene has one relevant
Prop and ten distractors, while the comparison Scene has no relevant Props.
The Ground truth file records a typed proposed relevance judgment for every
available Prop. Validation checks coverage and counts; independent review
decides whether the proposed relevance and distractors are semantically sound.

Generate JSON Schema for external tooling with Pydantic's public API:

```python
from evals.synthetic_journals.models import ProposedGroundTruth, SyntheticBackstory

backstory_schema = SyntheticBackstory.model_json_schema()
ground_truth_schema = ProposedGroundTruth.model_json_schema()
```
