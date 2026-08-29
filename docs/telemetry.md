# Linger Telemetry Data Contract

Status: **Canonical telemetry contract**

This document is the sole authority for what Linger records in Pydantic
Logfire. The product and architecture specification links here instead of
duplicating this contract.

## 1. Purpose

Telemetry exists to explain where and how a request or evaluation became slow,
failed, declined, or produced a poor result:

```text
request -> agent -> tool -> model -> review -> deterministic checks -> release
```

This supports the prototype's traceability, monitoring, and logging
requirements. Logfire is not product memory, conversation history, behavioural
analytics, an evidence store, or a release authority.

**Rule:** human runtime content is private by default. The `linger-backend`
service records **where and how** the system behaved. The explicit
`linger-evals` service may also record **what** synthetic input and output
produced an evaluation result.

## 2. What the backend service records

Only the following metadata may be exported by `linger-backend`. A field
outside this table is forbidden until this document, the typed projection, and
the exported-payload test are updated together.

| Area | Captured metadata |
|---|---|
| Correlation | Server-generated trace and span IDs |
| Request | Route template, status, outcome, and duration |
| Agent and model | Agent role and stage; provider and model; prompt-template ID, version, and static artifact digest; application-mediated hand-off input origin, receiver, and contract; output origin, receiver, and contract; success, decline, or failure; retry count; latency; tokens; cost |
| Tool and retrieval | Registered tool name; status; retries; duration; validated public `work_id`, `book_version_id`, and chapter ceiling; evidence count; resolvable public evidence IDs; retrieval outcome |
| Review and release | Provenance response, emotional-boundary, and capture decisions; fixed finding codes and count; revision count; deterministic validation outcome; release source and fixed boundary origin |
| Failure | Fixed failure stage and code; retryability; owner type (`model`, `validation`, or `application`) |
| Evaluation | Objective ID, case ID, dataset version, run ID, system variant, Ground truth status, expected and actual fixed labels, proposal comparison or adopted-label pass/fail, aggregate counts and metrics, latency, tokens, and cost |

Values must be fixed enums, booleans, numbers, repository versions,
server-generated correlation IDs, or identifiers validated against an
application-owned public registry. Route values must be templates such as
`/api/sessions/{session_id}`, never resolved paths.

The prompt digest covers only canonical static instructions and input/output
contract identities. It never covers a composed prompt, user input, retrieved
evidence, or other runtime content.

Hand-off metadata describes observable logical routing through the
application-owned orchestrator. It does not imply that agents communicate
autonomously or transfer authority. Origins, receivers, and contract names are
fixed application enums or repository-owned identifiers; payloads remain
absent.

## 3. What the backend service does not record

Every runtime string originating from a user, model, tool, evidence source,
provider, or exception is content-bearing by default. `linger-backend` must not
record:

- user or assistant messages, conversation summaries, memories, or sensitive
  traits and inferences;
- system instructions, composed prompts, completions, reasoning, critiques,
  rejected drafts, or released replies;
- tool arguments or results, reader cues, search queries, retrieval notes,
  excerpts, or content-bearing URLs;
- photographs, audio, other binary content, or media descriptions;
- credentials, tokens, cookies, authorization headers, or other secrets;
- account, session, turn, memory, source-event, idempotency, client-supplied, or
  other behaviour-linking identifiers; or
- raw exception messages, provider payloads, validation inputs, stack locals,
  or arbitrary unvalidated identifiers.

Human or production traffic never enters the content-bearing evaluation path.
A live failure creates only a metadata signature; a human must author a
synthetic or sanitised regression case. Runtime telemetry cannot reconstruct
the user's content.

## 4. Synthetic evaluation transcripts

The capture and bounded-curation replay runners use the same Logfire project
under the separate `linger-evals` service, `synthetic-evaluation` environment,
and `content.classification=synthetic` resource attribute. No production
configuration or environment flag enables this service or its recorder.

Configure that project before beginning the human-gated synthetic evaluation
workflow. Objective selection and `pre-generation-report.md` approval emit no
evaluation telemetry. Package generation and independent Ground truth review
also emit no replay result. After the human confirms every review row, the
review skill writes `ground-truth-adoption.json` and routes a supported single
Objective to one provider-backed runner; that runner publishes the Pydantic
Evals experiment and `linger-evals` traces. Without local `logfire projects use`
credentials or `LOGFIRE_TOKEN`, the runner retains its durable JSON output but
exports nothing to Logfire.

Each runner uses Pydantic Evals for one native case per Scene and
content-bearing Pydantic AI instrumentation for the fixed named agents: Muse,
Provenance, Librarian, Serendipity, and Sculptor. A workflow instruments only
the agents it invokes. Evaluation spans may record validated synthetic Lines or
Props, proposed expected outputs, actual outputs, labels, model-visible
instructions and messages, provider-returned thinking parts, tool calls and
results, tokens, cost, and fixed evaluation metadata. Binary content and full
model-request parameter objects remain disabled.

The durable capture artifact records the synthetic Line, exact agent input,
model-visible messages, typed output, tool calls and results, usage, released
reply, capture outcome, and matching Logfire trace and span IDs. The durable
curation artifact records the supplied Props, source hashes before and after
the call, typed Sculptor response, deterministic failures, separate semantic
criteria, full-deployment and objective-execution identities, and correlated
trace IDs. Both artifacts omit thinking parts. Logfire may display only
thinking content that the provider actually returned; absence does not
establish that a model performed no internal reasoning.

Proposed authoring labels remain explicitly `proposed`. Comparison is reported
as `matches_proposal` or `differs_from_proposal`, never as an adopted Ground
truth pass.

### 4.1 Native Logfire views

The evaluation integration populates four native views in the existing
Logfire project:

- **Evals** shows the code-defined dataset, replay experiments, one result per
  Scene, synthetic input, proposed expected output, compact actual output,
  evaluator labels, operational metrics, and run comparison.
- **Agents** groups invocations by fixed agent name. It shows only agents
  exercised by the selected workflow and time range: capture normally shows
  Muse and Provenance, while bounded curation shows Sculptor.
- **LLMs and providers** aggregates model calls, latency, tokens, cost, and
  provider reliability data.
- **Live** shows the complete nested experiment, case, application, agent, and
  model-call trace.

Pydantic AI's native span names are `invoke_agent <name>`, but Logfire renders
them as **Muse run**, **Provenance run**, and equivalent `<agent> run` labels.
Selecting an agent-run span opens its ordered messages and typed result;
selecting **Details** or **Raw Data** exposes its raw span name and fixed
attributes. These rows describe completed invocations; they do not invoke an
agent interactively.

### 4.2 Event and hand-off sequence

Expanding a Scene's blue descendant count in **Full Trace** reveals the
chronological application-owned sequence. A normal reviewed-capture Scene is:

```text
case
  -> chat.request
  -> provenance.emotional_boundary -> Provenance run -> model call
  -> muse.draft -> Muse run -> model call
  -> provenance.review -> Provenance run -> model call
  -> proposal_comparison or adopted_hard_gate_grade evaluator
```

An isolated bounded-curation Scene is:

```text
case
  -> sculptor.curation -> Sculptor run -> model call
  -> proposal_comparison or adopted_hard_gate_grade evaluator
```

If emotional preflight returns `apply_boundary`, the trace stops before Muse
and the application releases the fixed boundary response. Otherwise Muse
receives a discriminated draft envelope whose `muse_turn.user_message` contains
the synthetic Line, and Provenance later receives a separate candidate-review
envelope. A revision adds another Muse and Provenance cycle within the same
case.

Proposal mode emits `proposal_comparison` with `matches_proposal` or
`differs_from_proposal`. When the exact package has a validated independent
adoption, the same case position emits `adopted_hard_gate_grade` with
`passes_hard_gates` or `fails_hard_gates` and uses the adopted Ground truth
identity as the dataset version.

Bounded-curation experiment metadata also records
`full_deployment_identity` for complete deployed-prompt lineage and
`objective_execution_identity` for behavioral comparison of the configured
model, Sculptor prompt, and active curation contracts. An inactive prompt may
change the former without changing the latter.

The application-owned parent spans carry
`handoff.input.origin`, `handoff.input.receiver`,
`handoff.input.contract`, `handoff.output.origin`,
`handoff.output.receiver`, and `handoff.output.contract`. These attributes
describe deterministic routing. The receiving agent's native message panel and
the durable JSON transcript contain the corresponding synthetic payload.

## 5. Configuration and verification

The contract is enforced by construction:

1. Automatic Pydantic AI and FastAPI instrumentation remains disabled for
   `linger-backend`. The replay command explicitly instruments only the fixed
   named Pydantic AI agents with content enabled under `linger-evals`.
2. Request spans use fixed route templates and never inspect bodies, headers,
   raw URLs, query strings, or resolved path values.
3. Application-authored attributes come only from typed allowlist projections.
4. Failures map to fixed stages, codes, owner types, and retryability instead of
   recording exception objects or messages. Exceptions from an agent invocation
   are model failures. Deterministic envelope, output, and finding-location
   checks are non-retryable validation failures; instrumentation projection
   defects are non-retryable application failures and do not interrupt the
   agent result they were describing.
5. Exported-payload tests inject distinctive secret markers into every
   prohibited source and assert that no span, log, event, or resource attribute
   contains them.
6. Local development uses the project credentials created by
   `logfire projects use`; deployed and CI environments use `LOGFIRE_TOKEN`.
   Without either credential source Linger exports nothing to Logfire, and
   console export remains disabled.
7. Evaluation tests inject distinctive synthetic prompt, instruction, tool,
   and output markers; assert that native Pydantic Evals and Pydantic AI spans
   retain them; and separately assert that `linger-backend` exports none of
   those fields.

Logfire's built-in scrubbing may remain enabled as defence in depth, but it
does not replace allowlisting. Adding a telemetry field requires the contract,
projection, and regression test to change in the same review.
