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

Generate JSON Schema for external tooling with Pydantic's public API:

```python
from evals.synthetic_journals.models import AuthoringManifest, SyntheticContent

content_schema = SyntheticContent.model_json_schema()
manifest_schema = AuthoringManifest.model_json_schema()
```
