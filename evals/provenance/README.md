# Provenance evaluations

Provenance assigns three runtime skills to one reusable `provenance_agent`.
Two versioned case packs cover emotional preflight and candidate review. The
candidate review returns independent response and capture decisions. Both packs
are semantic regression suites that write metadata-only reports. Neither
generates or modifies synthetic journal packages.

Each evaluation selects its skill before running the shared Agent. Preflight
uses the production `assess_emotional_boundary` entry point. Risk-code
evaluation supplies `CANDIDATE_REVIEW.run_options()` to the same Agent. Runs
receive no tools or message history. Task fingerprints cover the effective
shared and selected instructions, input and output schemas, validation
identities, and retry limits. Evaluation model overrides can replace the one
Agent's provider without replacing skill selection. A saved report describes
its recorded fingerprint and provider run, not later instruction versions.

The third skill, curation review, is implemented in `review_curation` outside
live chat. Its deterministic tests cover typed findings, exact proposal-digest
binding, source membership, no tools, and rejection behavior. There is no
dedicated curation semantic case pack here. Synthetic curation replay invokes
Sculptor's `propose_curation` and does not exercise Provenance curation review
or the complete apply-and-audit loop.

See [Provenance's assigned skills](../../src/linger/agents/provenance/README.md#assigned-runtime-skills)
for input and output contracts and
[the common architecture](../../docs/agent-skills.md) for Agent reuse.

## Candidate-gate risk codes

`risk-codes-cases.json` holds 24 cases covering both decisions the gate returns.

Twelve **release** cases check the five risk codes reachable in specification
flow 4.2.1: `unresolved_evidence`, `misattribution`, `spoiler`,
`unsupported_claim`, and `prompt_injection`. Twelve **capture** cases check the
four `SENSITIVE_RISK_CODES` that veto automatic capture under flow 4.2.2:
`unsupported_claim`, `sensitive_content`, `emotional_policy_violation`, and
`prompt_injection`. Each code has a positive case and a paired near-miss
negative that differs minimally, plus clean controls on both axes, so detection
is measured separately from a gate that blocks indiscriminately.

Every capture case sets `allow_memory_capture` and carries a real nomination.
The release cases do not, which structurally forces `no_candidate` and is why
they cannot measure the capture axis at all. The case contract enforces this:
an expectation the review envelope could never produce fails the case file
rather than the run.

```bash
uv run python -m evals.provenance.risk_codes
```

`--report PATH` selects the metadata-only JSON report. The default is
`evals/provenance/risk-codes-live-report.json`. The command uses `LINGER_MODEL`
and its matching provider API key, and exits with a nonzero status when the
suite's recall, over-refusal, or code-precision targets fail.

Grading has four axes: each decision **and** its finding codes. A correct
decision carrying the wrong code fails as `code_mismatch` or
`capture_code_mismatch`. This matters because no production code branches on a
code's value, so a mislabelling gate is otherwise invisible.

The two decisions are graded **separately and never pooled**, because the
product contract is that they are decoupled. A `reject_capture` alongside a
released response is correct, not an over-refusal. Two cases test that property
directly: a clean response carrying a vetoed nomination, and a revised response
carrying an allowed one. `decoupling_accuracy` reports them, and it is the only
metric that catches a gate which has learnt to veto whenever it revises.

`contains_sensitive_content` is graded too. It is derived from the capture
findings rather than returned by the model, so a veto labelled with a
non-sensitive code silently produces the wrong deterministic policy outcome.

The summary reports `block_recall` and `capture_veto_recall` (safety),
`over_refusal_rate` and `capture_over_refusal_rate` (usability),
`code_precision` and `capture_code_precision` (labelling),
`sensitive_content_accuracy`, `decoupling_accuracy`, and a per-code breakdown
for each axis.

Each case embeds a complete `ProvenanceInput`, so the production contract
validates the case file and schema drift breaks the pack immediately. Evidence
records are built from real chapters under
`data/corpus/alice-in-wonderland/`; `test_committed_cases_match_the_current_corpus`
fails if the committed JSON stops matching the corpus. Nominated spans are
derived from their Line rather than written by hand, so each one is the exact
codepoint slice that `candidate_from_review` re-slices at binding time.
Regenerate after a corpus rebuild:

```bash
uv run python -m evals.provenance._fixtures
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
