# Provenance evaluations

This directory contains the versioned evaluation packs for the reusable
`provenance_agent`. The packs cover emotional-boundary preflight, candidate
response and capture review, curation review, and claim-to-source mapping.

Live commands call the configured model provider and write metadata-only JSON
reports. The reports contain case IDs, decisions, finding codes, metrics, model
metadata, and prompt fingerprints. They do not contain prompts, source text,
or model rationales.

## Set up the environment

Run these commands from the repository root:

```bash
uv sync
export LINGER_MODEL=openai:gpt-6-luna
export OPENAI_API_KEY=<your-key>
```

Set the model and API-key pair that matches your provider. The commands below
use the configured `LINGER_MODEL` and its provider credentials.

## Run the live evaluations

Run the candidate-gate pack. It covers 52 cases across specification flows
4.2.1, 4.2.2, and 4.2.3.

```bash
uv run python -m evals.provenance.risk_codes \
  --report evals/provenance/risk-codes-live-report.json
```

Run the emotional-boundary pack.

```bash
uv run python -m evals.provenance.emotional_boundary \
  --report evals/provenance/emotional-boundary-live-report.json
```

Run the curation-review pack. It contains twelve cases and does not apply any
curation writes.

```bash
uv run python -m evals.provenance.curation_risk_codes \
  --report evals/provenance/curation-risk-codes-live-report.json
```

Run the claim-mapping diagnostic. It contains four cases and does not retrieve
new passages.

```bash
uv run python -m evals.provenance.claim_mapping \
  --report evals/provenance/claim-mapping-live-report.json
```

Each command exits with a nonzero status when its evaluation target fails.
Inspect the report named by `--report` for case-level failures and aggregate
metrics.

## Run deterministic checks

Run the Provenance and curation unit tests without contacting a model provider:

```bash
uv run pytest -q \
  tests/test_provenance_risk_code_evals.py \
  tests/test_provenance_review.py \
  tests/test_provenance_skills.py \
  tests/test_curation_risk_code_evals.py \
  tests/test_provenance_claim_mapping.py
```

Regenerate the candidate risk-code JSON only after changing the corpus or its
case fixtures:

```bash
uv run python -m evals.provenance._fixtures
```

Do not treat deterministic checks as a substitute for the provider-backed
semantic evaluations.

## Results

TODO: add the accepted live-report results after the Provenance implementation
is complete.
