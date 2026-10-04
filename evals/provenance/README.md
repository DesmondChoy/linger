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
	uv sync --locked --dev
	export LINGER_MODEL=openai:gpt-6-luna
	export OPENAI_API_KEY='your-key'
```

Set the model and API-key pair that matches your provider. The commands below
use the configured `LINGER_MODEL` and its provider credentials.

## Run the live evaluations

Run the candidate-review pack. It covers 52 cases across specification flows
4.2.1, 4.2.2, and 4.2.3: 34 response cases and 18 capture cases. The pack grades
the response decision and risk codes separately from the capture decision and
codes. It also grades the derived sensitive-content flag and required finding
resolutions. A correct decision with an incorrect required code fails.

```bash
	uv run python -m evals.provenance.risk_codes \
	  --report tmp/provenance/risk-codes.json
```

Use `--cases` for the focused nine-case capture pack:

```bash
	uv run python -m evals.provenance.risk_codes \
	  --cases evals/provenance/risk-codes-cases-unsupported-claims.json \
	  --report tmp/provenance/unsupported-claims.json
```

This pack covers unsupported book-fact nominations, reading-habit controls,
sensitive content, policy overrides, harmful content, and no-candidate
behavior. Its report has `complete_case_set=false` even when every selected
case passes. It does not replace the complete baseline. Risk-code case files
use schema version 3. The current risk-code report format uses schema version 2.

Run the eight-case emotional-boundary pack. It checks distress against ordinary
frustration, literary content, quoted content, third-person concern, and embedded
instructions. The deterministic self-harm backstop has separate unit tests.

```bash
	uv run python -m evals.provenance.emotional_boundary \
	  --report tmp/provenance/emotional-boundary.json
```

Run the curation-review pack. It contains twelve cases and does not apply any
curation writes.

```bash
	uv run python -m evals.provenance.curation_risk_codes \
	  --report tmp/provenance/curation-risk-codes.json
```

Each curation risk code has an unsafe or unsupported case and a supported
comparison. The injection case accepts either `revise` or `reject`, so it
measures blocking and code detection, not the runtime skill's required rejection
of actions that follow instructions inside memory text.

Run the claim-mapping diagnostic. It contains four cases and does not retrieve
passages. It tests support from named records and complementary contributions
to a joint claim.

```bash
	uv run python -m evals.provenance.claim_mapping \
	  --report tmp/provenance/claim-mapping.json
```

Each command exits with a nonzero status when its evaluation target fails.
Inspect the report named by `--report` for case-level failures and aggregate
metrics. Every runner accepts `--report`. Only `risk_codes` accepts `--cases`.
Choose a distinct report path for each run to preserve earlier evidence.

Synthetic connection replays also report [late Provenance findings](../synthetic_journals/provenance_diagnostics.py).
The diagnostic identifies objections first raised during revision review on
unchanged draft content, which can exhaust Muse's single revision opportunity.
It is diagnostic evidence about review consistency, not a separate release
approval or a live evaluation pack.

## Run deterministic checks

Run the Provenance and curation unit tests without contacting a model provider:

```bash
	uv run pytest -q \
	  tests/test_provenance_risk_code_evals.py \
	  tests/test_provenance_emotional_evals.py \
	  tests/test_provenance_review.py \
	  tests/test_provenance_skills.py \
	  tests/test_curation_risk_code_evals.py \
	  tests/test_provenance_claim_mapping.py \
	  tests/test_provenance_late_findings.py \
	  tests/test_self_harm_detection.py
```

Regenerate `risk-codes-cases.json` only after changing the corpus or its case
fixtures:

```bash
	uv run python -m evals.provenance._fixtures
```

Do not treat deterministic checks as a substitute for the provider-backed
semantic evaluations.

## Saved reports

These committed reports describe their recorded prompts, case sets, and models.
They do not establish a passing result for the current runtime. Dates are the
reports' UTC generation dates.

| Report | Date | Recorded result |
| --- | --- | --- |
| [Complete candidate review](risk-codes-live-report.json) | 2026-09-27 | 44/52 cases pass on `openai:gpt-6-luna`. `targets_pass=false`. |
| [Focused capture review](risk-codes-unsupported-claims-live-report.json) | 2026-09-27 | 9/9 selected cases pass on `openai:gpt-6-luna`. `complete_case_set=false`. |
| [Emotional boundary](emotional-boundary-live-report.json) | 2026-09-22 | 8/8 cases pass on `openai:gpt-5.6-luna`. |
| [Curation review](curation-risk-codes-live-report.json) | 2026-09-22 | All 12 cases meet the targets. The report identifies its model only as `configured`. |
| [Claim mapping](claim-mapping-live-report.json) | 2026-09-22 | 4/4 cases pass on `openai:gpt-5.6-luna`. |

The [focused capture report history](live_reports/README.md) preserves the case
and prompt changes behind earlier runs. Compare reports only with their stated
case sets, prompt fingerprints, and provider settings.
