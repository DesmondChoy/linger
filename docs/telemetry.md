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

**Rule:** runtime content is private by default. Logfire records **where and
how** the system behaved; versioned eval artifacts record **what** synthetic
input and output produced an evaluation result.

## 2. What Logfire records

Only the following metadata may be exported. A field outside this table is
forbidden until this document, the typed projection, and the exported-payload
test are updated together.

| Area | Captured metadata |
|---|---|
| Correlation | Server-generated trace and span IDs |
| Request | Route template, status, outcome, and duration |
| Agent and model | Agent role and stage; provider and model; prompt-template ID and version; success, decline, or failure; retry count; latency; tokens; cost |
| Tool and retrieval | Registered tool name; status; retries; duration; validated public `work_id`, `book_version_id`, and chapter ceiling; evidence count; resolvable public evidence IDs; retrieval outcome |
| Review and release | Provenance response and capture decisions; fixed finding codes and count; revision count; deterministic validation outcome; release source |
| Failure | Fixed failure stage and code; retryability; coarse application-owned type |
| Evaluation | Case ID, dataset version, run ID, system variant, expected and actual fixed labels, pass/fail and aggregate metrics, latency, tokens, and cost |

Values must be fixed enums, booleans, numbers, repository versions,
server-generated correlation IDs, or identifiers validated against an
application-owned public registry. Route values must be templates such as
`/api/sessions/{session_id}`, never resolved paths.

## 3. What Logfire does not record

Every runtime string originating from a user, model, tool, evidence source,
provider, or exception is content-bearing by default. Logfire must not record:

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

Full synthetic prompts, tool transcripts, and outputs belong in reviewed,
repository-versioned eval cases or reports, not Logfire. A live failure creates
only a metadata signature; a human must author a synthetic or sanitised
regression case. Runtime telemetry cannot reconstruct the user's content.

## 4. Configuration and verification

The contract is enforced by construction:

1. Automatic Pydantic AI and FastAPI instrumentation remains disabled because
   it emits fields outside this allowlist. Application-owned spans record the
   required model, tool, and request metadata instead.
2. Request spans use fixed route templates and never inspect bodies, headers,
   raw URLs, query strings, or resolved path values.
3. Application-authored attributes come only from typed allowlist projections.
4. Failures map to fixed stages and codes instead of recording exception
   objects or messages.
5. Exported-payload tests inject distinctive secret markers into every
   prohibited source and assert that no span, log, event, or resource attribute
   contains them.
6. Local development uses the project credentials created by
   `logfire projects use`; deployed and CI environments use `LOGFIRE_TOKEN`.
   Without either credential source Linger exports nothing to Logfire, and
   console export remains disabled.

Logfire's built-in scrubbing may remain enabled as defence in depth, but it
does not replace allowlisting. Adding a telemetry field requires the contract,
projection, and regression test to change in the same review.
