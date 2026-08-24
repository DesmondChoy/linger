# Provenance emotional-boundary evaluation

This versioned case set checks the production emotional-boundary classifier for
both safety misses and unnecessary refusal. It covers current first-person
distress, inability to cope, ordinary frustration, literary and quoted
language, concern about another person, and embedded instructions.

Run the live evaluation from the repository root:

```bash
uv run python -m evals.provenance.emotional_boundary
```

The command uses the configured `LINGER_MODEL` and its API key. It writes
`live-report.json` only when you run it. The report contains case IDs, expected
and actual decisions, prompt and policy versions, latency, and aggregate
accuracy, boundary-miss, and over-refusal metrics. It excludes evaluated Lines,
prompts, rationales, and credentials.

The command exits with a nonzero status unless all eight cases pass. Unit tests
validate case loading, exact-label grading, aggregate metrics, and report
redaction without contacting a model provider.

This is an agent-level semantic regression suite. It does not generate or
modify synthetic journal packages.
