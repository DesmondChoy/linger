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
.venv/bin/python -m evals.synthetic_journals.validate_package \
  path/to/backstory.json path/to/ground-truth.json
```

The validator fails closed on schema drift, coercion, bad hashes, missing or
extra Ground truth proposals, invalid references or ordering, span mismatches,
unresolvable evidence, false Scene-pair claims, and unmet run configurations.
It does not decide whether generated prose is realistic or whether a proposed
behavioral label is correct. An independent reviewer must adopt, revise, or
reject every proposal before it can grade Linger.

Replay the validated capture-only package through the production Muse path:

```bash
.venv/bin/python -m evals.synthetic_journals.replay \
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

The command sends the same validated synthetic run to the existing Logfire
project as service `linger-evals`, environment `synthetic-evaluation`. Pydantic
Evals creates one native case per Scene, including synthetic input, proposed
expected output, compact actual output, and a `proposal_comparison` label.
Content-bearing Pydantic AI spans provide Logfire's LLM panels with ordered
messages, model responses, tool calls, tokens, and cost. The surrounding
application spans retain fixed agent and hand-off metadata. Normal
`linger-backend` traffic remains metadata-only.

Runtime prompt fingerprints and a prompt-set system variant identify the
evaluated static artifacts. The JSON artifact remains the durable, complete
evaluation record; Logfire is the interactive inspection and comparison view.
Emotional-boundary observations also record whether the fixed response came
from the no-tool preflight or the downstream candidate-review fallback.
The Backstory and proposed Ground truth never enter Muse. The runner compares
observed capture labels with the proposals, but reports only
`matches_proposal` or `differs_from_proposal`; it does not grade or adopt them.

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
