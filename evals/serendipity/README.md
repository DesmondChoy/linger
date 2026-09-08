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
using the authenticated account's curated retrieval view. Memory evidence may
inform Serendipity's internal comparison but cannot authorise a released claim.
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

The direct `cross_source_tentative_connection` replay drives ordered synthetic
messages through production chat in an isolated account, memory store, and
session:

```bash
uv run python -m evals.serendipity.objective_replay \
	synthetic-journal-evaluation/packages/PACKAGE/backstory.json \
	synthetic-journal-evaluation/packages/PACKAGE/ground-truth.json \
	--adoption /tmp/cross-source-adoption.json \
	--output /tmp/cross-source-production-run.json
```

The two positional paths are a validated package: `backstory.json` supplies the
Backstory, Props, Scenes, and Lines, and `ground-truth.json` supplies the
proposals whose typed connection expectations drive grading. Both are validated
before any provider call. `--adoption` binds an independent reviewer's decision
to the exact proposed bytes; without it the run reports against unadopted
proposals and can never return `passes_hard_gates`. `--output` is optional and
prints to stdout when omitted. Provider-backed chat uses `LINGER_MODEL` and its
matching API key. Actual web tools require both `LINGER_WEB_SEARCH_ENABLED=true`
and `EXA_API_KEY`.

It records the first failed stage using this closed taxonomy:

1. `invocation` — Muse did not request Serendipity when the adopted scenario
   required it, or invoked it outside policy.
2. `retrieval` — a required permitted source was unavailable, returned no
   usable evidence, violated scope, or failed exact resolution. Wording the
   adopted package declared private that reaches an issued public-web query
   also fails here, with reason code `private_wording_in_public_query`.
3. `serendipity_selection` — Serendipity produced the wrong decision, cited
   unknown evidence, changed presentation, or selected no clear eligible winner.
4. `muse_presentation` — Muse omitted, distorted, overstated, or misattributed
   the validated connection.
5. `provenance_review` — independent review failed to detect or correctly
   classify support, privacy, spoiler, injection, or sensitive-inference risk.
6. `deterministic_release` — application release validation accepted an invalid
   declaration or rejected a fully valid reviewed candidate.

The report grades the final response's inspection metadata in this order:

| Stage | Recorded check |
| --- | --- |
| `invocation` | A Serendipity trace exists and is not skipped. |
| `retrieval` | Librarian reports completion, Serendipity does not report failure, and no issued web query carries wording the package declared private. |
| `serendipity_selection` | Serendipity reports completion. A decline expectation also requires a recorded connection decline. |
| `muse_presentation` | Release inspection exists without a Muse draft or revision failure. |
| `provenance_review` | Release inspection contains a verdict without a Provenance review failure. |
| `deterministic_release` | The actual release source matches the expected source without a deterministic validation failure. |

Stages report `passed`, `failed`, or `not_reached`, with one
`first_failure_stage`. Later stages are `not_reached` after the first failed
check. The JSON retains the final reply, release source, and trace ID.

These status checks support production diagnosis. They do not independently
grade semantic presentation, exact source selection, the correctness of a
Provenance verdict, or every earlier turn. `objective_pass` means that all
listed checks passed. It is not an independently adopted synthetic-package
grade. Fixture-backed component grades remain separate.

### Observing outbound web queries

Grading the privacy gate needs the exact queries Serendipity issued, but
`TurnInspection` deliberately carries no query text. The replay therefore starts
the evaluation-only observer in
[`query_observation.py`](../../src/linger/orchestration/query_observation.py)
around each Scene. Production starts no observer and retains nothing, and the
runtime never learns which wording a package forbade: the comparison happens in
the grader, so adopted Ground truth stays outside the system under evaluation.

Each observation records the query and one verdict. A `blocked` query is the
runtime privacy gate refusing to search and asking the model to generalise, so
it is evidence the gate works, not a leak; only an `issued` query can fail the
`retrieval` stage. Reports keep both.

### What the replay does not score

`require_tentative` and `public_claims` reach the report as
`semantic_review` and are never scored. Whether a connection is framed honestly
and whether a public claim is realistic are review judgments, consistent with
the separation above, and a semantic judgment never overrides a failed hard
gate.

A selected web page is releasable: Muse must declare and visibly cite the exact
URL opened in that turn, and application code validates the URL and any exact
quotation against the page excerpt before release. The component suite may prove
that Serendipity correctly selects and flags a book-to-web candidate, but only
the objective replay reports the actual deterministic-release outcome.

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

The durable JSON report records dataset and prompt identities, configured model,
case inputs, observed searches, typed outputs, hard grades, semantic rubrics,
usage, latency, and per-case failures. Content-bearing evaluation data must use
synthetic or public fixtures only.

When Logfire is configured, the runner also submits the same cases through
Pydantic Evals. Logfire is the interactive comparison surface; the checked or
explicitly retained JSON report remains the complete reproducible artifact.
Local validation and reporting must succeed without Logfire credentials.

## Versioning

Current cases use schema version 3 and `-v3` case IDs. Incompatible case-format
changes require a schema bump. Accepted cases are extended with reviewed
successors rather than silently weakened. Reports bind the dataset digest,
prompt fingerprint, model, and code revision when available.
