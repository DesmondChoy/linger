# Provenance evaluations

Two versioned case packs cover Provenance's two call sites: the emotional-boundary
preflight and the candidate release gate. Both are agent-level semantic
regression suites that write metadata-only reports. Neither generates or modifies
synthetic journal packages.

## Candidate-gate risk codes

`risk-codes-cases.json` checks the five risk codes reachable in specification
flow 4.2.1: `unresolved_evidence`, `misattribution`, `spoiler`,
`unsupported_claim`, and `prompt_injection`. Each code has a positive case and a
paired near-miss negative that differs minimally, plus two clean passes, so
detection is measured separately from a gate that blocks indiscriminately.

```bash
uv run python -m evals.provenance.risk_codes
```

Grading has two axes: the response decision **and** the finding codes. A correct
decision carrying the wrong code fails as `code_mismatch`. This matters because
no production code branches on a code's value, so a mislabelling gate is
otherwise invisible. The summary reports `block_recall` (safety),
`over_refusal_rate` (usability), `code_precision` (labelling), and a per-code
breakdown.

Each case embeds a complete `ProvenanceInput`, so the production contract
validates the case file and schema drift breaks the pack immediately. Evidence
records are built from real chapters under
`data/corpus/alice-in-wonderland/`; `test_committed_cases_match_the_current_corpus`
fails if the committed JSON stops matching the corpus. Regenerate after a corpus
rebuild:

```bash
python -m evals.provenance._fixtures
```

Cases are hand-authored and reviewed. A gate evaluated on cases written by the
model family it gates would not be independent evidence.

## Emotional-boundary preflight

This versioned case set checks the production emotional-boundary classifier for
both safety misses and unnecessary refusal. It covers current first-person
distress, inability to cope, ordinary frustration, literary and quoted
language, concern about another person, and embedded instructions.

Run the live evaluation from the repository root:

```bash
uv run python -m evals.provenance.emotional_boundary
```

Use `--report <path>` to choose the JSON report location; the default is
`evals/provenance/live-report.json`.

The command uses the configured `LINGER_MODEL` and its API key. It writes
`live-report.json` only when you run it. The report contains case IDs, expected
and actual decisions, prompt and policy versions, latency, and aggregate
accuracy, boundary-miss, and over-refusal metrics. It excludes evaluated Lines,
prompts, rationales, and credentials.

The command exits with a nonzero status unless all eight cases pass. Unit tests
validate case loading, exact-label grading, aggregate metrics, and report
redaction without contacting a model provider.
