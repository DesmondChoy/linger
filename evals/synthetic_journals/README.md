# Synthetic journal package validation

The v1 package has two JSON files: generated content and a separate authoring
manifest containing only proposed Ground truth. The manifest hashes the exact
content-file bytes. One package contains one Backstory, person, and evaluation
account; build a full dataset from multiple independently validated packages.

The Pydantic models in `models.py` are the schema authority. Validate a package
from the repository root:

```bash
.venv/bin/python -m evals.synthetic_journals.validate_package \
  path/to/content.json path/to/authoring-manifest.json
```

The validator fails closed on schema drift, coercion, bad hashes, missing or
extra Ground truth proposals, invalid references or ordering, span mismatches,
unresolvable evidence, false Scene-pair claims, and unmet run configurations.
It does not decide whether generated prose is realistic or whether a proposed
behavioral label is correct. An independent reviewer must adopt, revise, or
reject every proposal before it can grade Linger.

The adopted run configurations keep imbalanced tests explicit and scoped to
their Objective. Reviewed automatic capture uses one capture-candidate Scene
and ten no-candidate Scenes. Longitudinal retrieval uses two fresh-session
Scenes sharing the same eleven active Props: the target Scene has one relevant
Prop and ten distractors, while the comparison Scene has no relevant Props.
The authoring manifest records a typed proposed relevance judgment for every
available Prop. Validation checks coverage and counts; independent review
decides whether the proposed relevance and distractors are semantically sound.

Generate JSON Schema for external tooling with Pydantic's public API:

```python
from evals.synthetic_journals.models import AuthoringManifest, SyntheticContent

content_schema = SyntheticContent.model_json_schema()
manifest_schema = AuthoringManifest.model_json_schema()
```
