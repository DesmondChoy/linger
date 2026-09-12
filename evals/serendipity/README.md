# Serendipity component evaluations

This directory evaluates only behavior owned by Serendipity at its typed agent
boundary. It does not evaluate whether Linger delivered a successful
reader-facing experience.

The component boundary is:

```text
controlled ConnectionDiscoveryInput
+ fixture-backed Librarian / Exa results
                ↓
        production Serendipity agent
                ↓
 ConnectionProposal | ConnectionDecline
+ observed search and evidence ledger
```

Muse invocation, live retrieval quality, Muse presentation, Provenance review,
deterministic release, and the final reader response are outside the component
claim. The runner may exercise production Serendipity code and tool adapters,
but its dependencies return case-owned fixture evidence so a failure can be
localized to Serendipity's routing, filtering, comparison, or selection.

## Current component behaviors

The required baseline uses local contract language rather than product-objective
names:

| Behavior | Component question |
| --- | --- |
| `route_book_relationship_to_librarian` | When the cue asks about a relationship inside the book, does Serendipity start with Librarian? |
| `route_external_recommendation_to_web` | When the cue asks for an outside work or source, does Serendipity start with web search and open a page before citing it? |
| `expand_source_only_when_justified` | Does Serendipity add a second permitted source only when the first source cannot answer the cue alone? |
| `stop_when_primary_source_is_sufficient` | When the primary source already supplies enough evidence, does Serendipity stop instead of searching another available source? |
| `select_evidence_with_a_real_semantic_bridge` | Does the selected evidence support a specific shared structure and a meaningful difference, rather than a generic topic match? |
| `rank_the_strongest_supported_connection` | Does Serendipity select the uniquely strongest supported candidate, and decline when the top candidates remain tied? |
| `decline_when_no_supported_bridge_exists` | Does Serendipity decline when the retrieved evidence cannot support two eligible candidates or only supplies a generic theme? |
| `exclude_ineligible_evidence_before_selection` | Does Serendipity remove evidence that violates scope, provenance, or untrusted-content rules before comparing candidates? |

These behaviors follow the component's sequence: route, retrieve, optionally
expand, filter eligibility, assess the bridge, rank, then propose or decline.
Retrieval quality itself still belongs to Librarian or the web provider;
Serendipity is graded on which permitted tool it calls and what it does with the
returned evidence.

The loader requires at least one case for every required behavior and permits
multiple cases per behavior. Contrast pairs should differ in one material
condition, such as a specific supported bridge beside a generic-theme
decline, or a clear winner beside a tied-winner decline. A behavior name does
not dictate the output shape: ranking includes both a clear-winner proposal and
a tied-top decline, while eligibility filtering may either leave a valid winner
or leave nothing safe to propose.

The runtime supports authorised-memory discovery through `search_memories`,
using the authenticated account's curated retrieval view. Selected memory
evidence can support a personal-context claim only after Muse declares it,
Provenance reviews it, and application code resolves the exact active record.
The current component cases cover book and web sources. The memory scenario in
`cases/future/` remains outside that baseline until executable memory cases and
their grading are added.

## Case contract

Each current JSON case contains:

- one canonical `ConnectionDiscoveryInput` containing the cue, intent,
  presentation mode, and application-owned source grants;
- fixture evidence returned only through the permitted tool adapters;
- expected search observations, so routing and search-before-proposal are
  checked from the run rather than asserted as `true` in fixture prose;
- one expected proposal or decline;
- deterministic hard-gate expectations; and
- separate semantic criteria for generated connection prose.

Case files never contain a reader-visible expected reply. The expected output is
always `ConnectionProposal | ConnectionDecline` because that is the boundary
Serendipity owns.

## Hard grading and semantic review

Hard grading checks observed behavior:

- response contract and expected proposal/decline;
- decline reason;
- exact run-evidence identity;
- required selected evidence and unknown-evidence rejection;
- presentation preservation;
- web-policy flag consistency;
- at least one permitted search before every proposal;
- expected source routing and tool order;
- tool and model-request budgets;
- spoiler-scope compliance;
- web-search lead versus opened-page provenance; and
- absence of storage and release authority from the available tool surface.

Semantic review remains separate. It judges cue fit, reflective value,
meaningful difference, tentativeness, and forbidden overclaims. A semantic
score can never override a failed hard gate. The default local run exposes the
rubric for human review; an explicitly configured secondary evaluator may add a
structured semantic judgment.

## Relation to product objectives

Component evidence supports diagnosis; it is not an objective result.

| Product objective | Supporting Serendipity behaviors | What still requires objective-level production replay |
| --- | --- | --- |
| `cross_source_tentative_connection` | `route_external_recommendation_to_web`, `expand_source_only_when_justified`, `select_evidence_with_a_real_semantic_bridge`, `rank_the_strongest_supported_connection` | Muse invocation, real retrieval, Muse presentation, Provenance review, deterministic release, and the reader-visible response |
| `weak_evidence_safe_decline` | `decline_when_no_supported_bridge_exists`, `rank_the_strongest_supported_connection` | Honest relay of restraint and absence of unsupported released claims |
| `untrusted_content_injection_resistance` | `exclude_ineligible_evidence_before_selection` | End-to-end confirmation that untrusted content changes no tool authority, memory behavior, review decision, or released response |
| `grounded_book_reflection` | `route_book_relationship_to_librarian`, `stop_when_primary_source_is_sufficient`, `select_evidence_with_a_real_semantic_bridge` | Librarian retrieval quality, Muse evidence use, citation resolution, spoiler safety, and release |

A passing component run means only that Serendipity made the expected local
decision under controlled evidence. It must never be aggregated or labeled as
an objective pass.

## Cross-source production replay

[`evals.synthetic_journals.connection_replay`](../synthetic_journals/README.md#connection-and-restraint-replay)
supports independently adopted packages for `cross_source_tentative_connection`,
`weak_evidence_safe_decline`, or both. The typed path runs production chat with
isolated memory storage, registered corpus retrieval, and live public retrieval
bounded to the supplied URLs. Adopted public snapshots define the exact evidence
expected from live pages. Changed or unavailable evidence cannot count as
successful restraint. This controlled test does not establish general search
coverage.

The release gate checks selected memory and public evidence against the exact
current-run records reviewed by Provenance. Unknown or changed evidence fails
closed. Structural stage results remain separate from human judgments about
usefulness, tentativeness, honest restraint, and support for public claims.
Legacy weak-evidence-only packages delegate to the reflection runner and retain
its narrower hard checks. A component result never substitutes for a released
production response.

The direct `cross_source_tentative_connection` replay drives ordered synthetic
messages through production chat in an isolated account, memory store, and
session:

```bash
uv run python -m evals.serendipity.objective_replay \
	evals/serendipity/objective_cases/cross-source-outside-essay-v1.json \
	--output /tmp/cross-source-production-run.json
```

The positional `case` contains a `CrossSourceReplayCase`, including ordered
messages, an expected decision, and an expected release source. `--output` is
required. This command has no synthetic-package or `--adoption` argument.
Provider-backed chat uses `LINGER_MODEL` and its matching API key. Actual web
tools require both `LINGER_WEB_SEARCH_ENABLED=true` and `EXA_API_KEY`.

The direct replay grades the final turn's recorded connection events and release
inspection in this order:

| Stage | Recorded check |
| --- | --- |
| `invocation` | A discovery event exists. |
| `retrieval` | Search events exist, with no search failure or unavailable-retrieval status. |
| `serendipity_selection` | The final discovery event has no failure and matches the expected proposal or decline decision. |
| `muse_presentation` | Release inspection exists without a Muse draft or revision failure. |
| `provenance_review` | The final Provenance verdict is `pass`. |
| `deterministic_release` | The actual release source matches the expected source without a deterministic validation failure. |

Stages report `passed`, `failed`, or `not_reached`, with one
`first_failure_stage`. Later stages are `not_reached` after the first failed
check. The JSON retains the final reply, release source, and trace ID.

These structural checks support production diagnosis. They do not independently
grade semantic presentation, exact source selection, the correctness of a
Provenance verdict, or every earlier turn. `hard_gate_pass` means that all listed
checks passed; `semantic_review_required` remains true. It is not an
independently adopted synthetic-package grade. Fixture-backed component grades
remain separate.

## Running and reports

Validate the current cases and deterministic graders:

```bash
uv run pytest tests/test_serendipity_evals.py
```

Run the production Serendipity agent with fixture-backed tools:

```bash
uv run python -m evals.serendipity.runner \
	--output evals/serendipity/reports/latest.json
```

The component command accepts these options:

- `--output PATH` is required and writes the durable report.
- `--semantic-review` requests an additional model judgment against the case's
  semantic criteria. The CLI uses the configured model for this review, so the
  result is not independent of that model. It cannot override a hard failure.
- `--no-logfire` skips the runner's Logfire configuration. The component model
  still runs and writes its JSON report.

The component tools return fixture evidence, so they require no Exa credential
or live retrieval. The Serendipity agent uses the configured `LINGER_MODEL` and
matching provider API key.

The optional semantic reviewer loads `evaluation.serendipity_review` from the
[`prompt catalogue`](../../src/linger/prompts/prompt_catalog.yaml).

The durable JSON report records dataset and prompt identities, configured model,
case inputs, observed searches, typed outputs, hard grades, semantic rubrics,
usage, latency, and per-case failures. Content-bearing evaluation data must use
synthetic or public fixtures only.

The runner selects the production `connection-discovery` skill for every case.
It reuses one Serendipity Agent across the suite while creating each case's
dependencies and permitted Exa capability separately. The report's `skill_id`
and Pydantic Evals case metadata identify `serendipity.connection-discovery`.
The prompt fingerprint covers shared and selected instructions, input and output
contracts, permitted tools and capabilities, validation, and retry limits.
Model injection preserves this selected configuration and its fixed output
schema. See the [runtime skills architecture](../../docs/agent-skills.md).

When Logfire is configured, the runner also submits the same cases through
Pydantic Evals. Logfire is the interactive comparison surface; the checked or
explicitly retained JSON report remains the complete reproducible artifact.
Local validation and reporting must succeed without Logfire credentials.

## Versioning

Current cases use schema version 3 and `-v3` case IDs. Incompatible case-format
changes require a schema bump. Accepted cases are extended with reviewed
successors rather than silently weakened. Reports bind the dataset digest,
prompt fingerprint, model, and code revision when available.
