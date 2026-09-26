# Serendipity

Serendipity is Linger's optional search-and-connection specialist. It searches
permitted sources, removes ineligible evidence, constructs possible
connections, compares the strongest two or three with an anchored rubric, and
returns exactly one `ConnectionProposal` or one `ConnectionDecline`. A separate
recall skill returns the reader's own earlier records as one `MemoryRecall`, or
declines. A separate gathering skill returns the records for every source the
reader named as one `SourceBundle`, without ranking them, or declines.

Serendipity can search active account-scoped curated memories, spoiler-bounded
book evidence, and optional public-web sources. Selected evidence may enter
the Muse, Provenance, and deterministic release path under its source-specific
citation rules. Image evidence is unsupported.

Serendipity has no write or release authority. Muse owns the conversation,
Librarian owns internal retrieval, Exa supplies public-web search, application
code owns access grants, and Provenance reviews every complete Muse draft.

## Assigned runtime skills

One reusable PydanticAI Agent, `serendipity_agent`, owns three runtime skills,
[`connection-discovery`](skills/connection-discovery/SKILL.md),
[`memory-recall`](skills/memory-recall/SKILL.md), and
[`source-gathering`](skills/source-gathering/SKILL.md). Application code
selects one from the brief's intent before a model run; the model then chooses permitted searches and
domain decisions within that skill. An Agent object is reusable configuration.
A model run is an invocation that can include several searches and retries.

| Assigned skill | Typed input | Typed output | Current consumers |
| --- | --- | --- | --- |
| `connection-discovery` | `ConnectionDiscoveryInput` | `ConnectionProposal` or `ConnectionDecline` | `orchestration.connection._agent_explorer` in production chat; `evals.serendipity.runner.run_case` with controlled tool evidence |
| `memory-recall` | `ConnectionDiscoveryInput` with `intent="recall_memory"` and a memory-only scope | `MemoryRecall` or `ConnectionDecline` | `orchestration.connection._agent_explorer` in production chat |
| `source-gathering` | `ConnectionDiscoveryInput` with `intent="gather_sources"` | `SourceBundle` or `ConnectionDecline` | `orchestration.connection._agent_explorer` in production chat |

`memory-recall` searches only `search_memories` and returns the one to three
records that are the reader's own earlier words on what the cue asks about;
one record is a complete recall. A record that only shares vocabulary or
offers a transferable lesson is not a match, and no match is a decline with
reason `no_matching_memory`. Recall never interprets, ranks interpretations, or
drafts the reply.

`source-gathering` serves a reader who has already chosen the sources to
consider together, such as named scenes, a named public text, and their own
earlier note. It inspects each named, permitted source with the same tools as
discovery and returns one `SourceBundle`: every record that supports a named
source, plus `unfound_sources` naming what it could not find. It does not build
or rank competing connections, because a shortlist that must pick one winner
drops some of the sources the reader asked for; Muse writes the comparison.
Every book passage `search_librarian` returned must stay in the bundle, since
Librarian already judged it relevant to the reader's named needs, and so must
every page opened with `get_page`, cited by its exact URL.

[`skills.py`](skills.py) binds the instructions, contracts, tools, optional Exa
capability, validator, and retry limits. `agents.serendipity` in the
[`prompt catalogue`](../../prompts/prompt_catalog.yaml) contains only the shared role
and authority rules. The Agent's base instructions use this entry; each run adds
the selected skill. Both resources load from the package without a
working-directory dependency. See the
[runtime skills architecture](../../../../docs/agent-skills.md).

The Agent keeps one fixed output schema (proposal, decline, recall, or bundle)
and its registered `validate_serendipity_output` validator. No skill overrides
`output_type`; the validator retries any result that does not match the task's
intent, a recall citing a record this run's `search_memories` did not return,
and a bundle that cites an unreturned record or omits a returned book passage
or an opened page. It preserves two output retries, the existing default tool retry
budget of two, and the bounded internal tools' individual limit of one retry.
`build_serendipity_agent(model)` preserves model injection for tests and
evaluation. No account, search ledger, or capability instance is stored on the
shared Agent.

## Inputs and authority

Application orchestration creates one `ConnectionDiscoveryInput` containing:

- the active reader cue;
- the connection intent and presentation policy; and
- a trusted `ConnectionScope` granting selected sources and any book scopes.

The initial input contains authority, not prefetched search results. A typical
grant is:

```json
{
  "allowed_sources": ["book_corpus", "web"],
  "book_scopes": [
    {
      "work_id": "pg11",
      "book_version_id": "pg11-v01b38ea4",
      "chapter_max": 5
    }
  ]
}
```

Serendipity cannot add a source, enable web access, change a book revision,
widen a reading scope, or change presentation policy. The canonical Librarian
service is supplied through `SerendipityDependencies`, which tool code can
access but the model cannot see or supply.

The application grants `memory` only when its active account-scoped curated
retrieval view contains records. It grants `book_corpus` only with confirmed
chapter or named-unit context; an exact-passage grant does not permit Serendipity
book search.
Web tools require both `LINGER_WEB_SEARCH_ENABLED=true` and `EXA_API_KEY`.
`get_recommendation` and `gather_sources` use `presentation=direct`, while
`find_connection` uses `ask_before_showing`. When triage pinned
`find_connection` (the reader asked about their reading without naming books)
and books are granted, the scope sets `search_all_granted_books`:
`search_librarian` then searches every granted book whatever `work_ids` the
model selects, and the validator retries any answer given before a book
search. `recall_memory` grants memory only, never the book corpus
or the web, and its result carries no presentation policy. Presentation policy does not bypass release checks.

## Search ownership

The ownership boundary is:

| Component | Search responsibility |
| --- | --- |
| Application | Supplies the exact current reader message as the cue and owns source grants |
| Memory & Policy Service | Supplies the active account-scoped curated retrieval view |
| Librarian | Spoiler-bounded book corpora |
| Serendipity | Chooses useful permitted searches and compares their results |
| Exa | Public-web search and page retrieval for Serendipity |
| Muse | Chooses whether to invoke connection discovery and supplies its intent |

`search_librarian` invokes the same Librarian path as Muse and accepts no
model-written book query. Application code supplies the original reader cue and
earlier reader statements. Librarian plans the request before private retrieval;
the exact planned spans form the search query, and assessment reuses that plan.
Book retrieval stays within the granted revision and reading scope. Selected
records and their judgment remain subject to the existing evidence and release
checks.

The maintained `pydantic_ai_harness.exa.ExaSearch` capability supplies `web_search` and
`get_page`; Linger wraps that capability only to enforce source permission,
bound query size, reject private data and copied reader or memory wording, and
record opened pages in the evidence ledger. An exact public URL supplied by
the application may be opened directly; other URLs require a lead from the
current run's search results. Page URLs pass privacy checks in raw and decoded
form. The returned page identity must match the request before it is citable.

## Search, shortlist, and selection flow

```text
Application grants source permissions
                ↓
Shared policy + selected connection-discovery skill + ConnectionDiscoveryInput
                ↓
        Serendipity chooses permitted tools to conduct searches
          ├─ Memory: Active account-scoped curated records
          ├─ Librarian: Internal evidence - spoiler-bounded book excerpts
          └─ Exa: External evidence - public web (web_search, get_page)
                ↓
      Several evidence records returned
                ↓
       Construct possible connections
                ↓
     Shortlist strongest 2–3 candidates
                ↓
       Compare with anchored rubric
                ↓
 ConnectionProposal | ConnectionDecline
                ↓
       Deterministic validation
                ↓
 Validated decision + exact evidence bundle
                ↓
      Muse drafts the reader response
                ↓
         Provenance reviews it
                ↓
    Deterministic release validation
       ├─ book: canonical record, scope, location, and quotation checks
       ├─ memory: exact active account record and attribution review
       └─ web: exact opened page and visible URL citation
```

Source grants are permissions, not mandatory search steps. Serendipity should
search the permitted sources relevant to the cue and may compare source types
when doing so could improve the result. It does not have to call Librarian or
Exa merely because either is available. It may refine a query and search several
records per source, within a hard run budget of eight model requests and six
total tool calls. A `web_search`
result is only a lead; Serendipity must use `get_page` to read a promising URL
before that URL enters the Serendipity evidence ledger. Entry in that ledger
does not grant public-release authority.

`search_memories(query, max_results_per_source=5)` searches only the supplied
curated records. It ranks positive normalized-token overlaps, breaks ties by
memory ID, and clamps the requested limit to one through five. The tool is
absent when memory access is not granted. `search_librarian` uses the same
per-source result limit. Repeated `serendipity_explore` calls with the same
intent reuse the result for the turn; a different intent receives a decline.

### Source-routing policy

Serendipity chooses one primary source from the reader's requested relationship,
not from the order of `allowed_sources`:

| Cue or intent | Primary search | Expansion rule |
| --- | --- | --- |
| Connection to the reader's authorized prior context | `search_memories` | Keep private memory wording out of public-web queries. |
| External recommendation: essay, artwork, song, thinker, public source, or outside idea | Exa | Add the confirmed book only when the reader explicitly asks for that comparison or the web result is insufficient and the book comparison is materially useful. |
| Relationship within a confirmed work | Librarian: `book_corpus` | Add web only when the cue explicitly asks to cross that domain or the bounded book evidence is insufficient. |
| Explicit comparison across domains | Every named, permitted domain | Do not add unnamed domains merely because they are granted. |
| Ambiguous reflective connection | Confirmed book, when specifically relevant | Do not search the web just to manufacture novelty. Decline when no permitted evidence fits. |

The execution sequence is primary search → sufficiency check → optional expansion
→ shortlist and compare. Expansion is justified only when the reader requested
the second domain, the primary search returned no or weak evidence, or the second
source is necessary for a materially better comparison. Serendipity stops once
the collected evidence supports two distinct eligible candidates. It never
searches both Librarian and Exa solely because both tools are available, to pad
the shortlist, or to avoid a valid decline.

If the requested primary source is unavailable or outside the application grant,
Serendipity declines rather than silently substituting another domain.

Concrete routing examples:

| Reader cue | Expected calls |
| --- | --- |
| “Does the Caterpillar echo anything earlier in this book?” | Librarian book search only. |
| “Recommend an essay or artwork that resonates with this feeling.” | Exa search and page retrieval only. |
| “Connect this chapter to an outside essay.” | Librarian book search plus Exa. |

## Eligibility before ranking

Hard gates run before comparison. Evidence and candidates are ineligible when
they are out of scope, past a spoiler ceiling, unresolved, unsafe,
injection-bearing, unsupported, or merely a generic theme match. Ineligible
material cannot win by scoring well elsewhere.

The application enforces structural boundaries. Serendipity performs the
semantic filtering, and Provenance later checks the complete user-facing draft.
These layers are complementary; model judgment never widens application-owned
authority.

## Candidate rubric

Each `ConnectionCandidate` includes the evidence IDs, proposed bridge, and one
`CandidateRubric`. The rubric uses anchored categories rather than subjective
decimals or a synthetic confidence sum:

| Criterion | Strong anchor | Middle anchor | Rejecting anchor |
| --- | --- | --- | --- |
| Cue fit | `direct` — answers this cue | `partial` — one inferential step | `weak` — could fit many cues |
| Reflective value | `high` — materially changes the view | `medium` | `low` — mostly restates |
| Safety | `clear` | `review` | `ineligible` |

Eligibility is derived by the contract. A candidate is eligible only when it
has neither a rejecting anchor nor a disqualifier. Eligible candidates are then
ranked lexically: cue fit, reflective value, safety. The ordinal indices used for that
comparison are never exposed or summed into a confidence number.

`comparison_note` explains why each candidate ranks above or below another.
The shortlist must contain two or three distinct, eligible candidates for a
proposal. If fewer than two survive or no candidate clearly wins, Serendipity
declines instead of padding the matrix.

## Proposal and decline

A `ConnectionProposal` contains:

- the ranked shortlist of two or three eligible candidates;
- the ID of the rank-one candidate;
- qualitative uncertainty about the selected interpretation;
- the unchanged presentation mode;
- a follow-up for Muse; and
- a closed web-claim policy flag.

The selected candidate contains the tentative claim, cited evidence IDs, shared
structure, meaningful difference, interpretation, rubric, and comparison note.
Consumers resolve `selected_candidate_id` against the shortlist; the model does
not duplicate the winner's content at the top level.

A `ConnectionDecline` contains a machine-readable reason and safe next step.
Declining is a successful outcome; rejected candidates do not leave the agent
boundary.

## Deterministic validation

Tool calls populate an application-owned evidence ledger. After the model
returns, orchestration verifies that:

- every shortlisted evidence ID came from a permitted search tool in this run;
- every returned record belongs to a granted source;
- every book record matches its revision and spoiler ceiling;
- a proposal followed at least one recorded permitted search;
- the selected candidate is the eligible rank-one candidate;
- web flags match the winner's actual cited sources; and
- presentation policy is unchanged.

Only the exact records cited by the selected candidate, memory recall, or
source bundle leave this ledger. If they include book-corpus records, orchestration converts those records to the
canonical `EvidenceRecord` contract and adds them to the request-scoped book
evidence index. Selected memory and web records use the separate request-scoped
connection evidence registry. Their declarations must resolve to those exact
records before deterministic release.

Exa URLs are their web evidence IDs. Search-result metadata supplies
request-local page leads, while only a successfully opened `get_page` result is
stored as Serendipity-citable web evidence. A guarded wrapper bounds each web
query and rejects private data and copied reader or memory wording. For source
text of at most eight tokens, any shared multi-character token blocks the query.
For longer source text, the guard rejects three consecutive copied tokens, or
the whole query if shorter. Page URLs undergo the same checks in raw and decoded
form. The exact public URL being opened is excluded from reader-wording
comparisons, while memory text and private-data checks remain in scope. An
application-supplied URL allowlist permits direct opens of those exact URLs;
otherwise the URL must come from the current run's search leads. Web tools are
absent when web access or credentials are not granted.

## Shared book-evidence boundary

Muse, Provenance, and deterministic release validation read one application-
owned, request-scoped map of exact book records. It has only three inputs:

- direct Librarian results from the current Muse run;
- the exact selected book records from a current Serendipity proposal; and
- records Librarian re-resolved from identifiers cited by an earlier
  successfully released reply in the same session.

The single reviewed revision receives the draft tool messages and reads this
same map, so it does not reconstruct passages from the draft's prose. For
cross-turn continuity, the session stores only the turn identifier, release
source, cited evidence identifiers, and review finding codes. It
stores neither passage text nor reading progress. A re-resolved identifier
grants only that exact earlier passage, not neighbouring text or a current
spoiler boundary. Web, stored-memory, and image evidence never enter this map.

## Where authority ends

A proposal is untrusted material for Muse, not a user-facing response. The
selected skill returns a connection proposal or decline, a memory recall, or a
source bundle.
After deterministic validation, application orchestration wraps the decision
with the exact evidence cited by the selected candidate or recall for the Muse
tool handshake. Losing-candidate evidence stays inside the Serendipity run and
is excluded from Muse's tool result and Inspect. Muse may
surface a selected proposal only by declaring every record it uses with its
actual source kind. Provenance receives the complete Muse candidate, validated
tool result, exact book and connection evidence, and release policy, then checks attribution,
privacy, spoilers, sensitive inference, unsupported claims, and prompt
injection. Application code resolves every declaration against the same records
after a semantic pass. There is no Serendipity-to-reader bypass.

Serendipity cannot save or curate memory. Telemetry and fixed request-local
outcome metadata report a decision but never authorise search, storage, or release.

Serendipity cannot widen citation or public-release authority. Selected book
records use the canonical book contract. A selected web page can support a
release only when Muse visibly cites its exact opened URL and application code
resolves that declaration against the current run. Provenance still treats the
page as untrusted evidence. A selected memory must still resolve to its exact
active account record; it supports the reader's personal context, not public
facts or causal claims. Image evidence has no runtime contract. Content-bearing
connection diagnostics are not returned by the API. A validated decline may
still be relayed with fixed inspection metadata.

## Evaluation scope

The [component pack](../../../../evals/serendipity/README.md) exercises this same
skill with controlled book and web tool evidence. Its reports retain
`serendipity.connection-discovery`, effective instruction and contract
fingerprints, and observed searches. The memory scenario in `cases/future/`
remains outside that component baseline. Synthetic connection replay and the
direct production replay also exercise Muse, Provenance, and release validation;
a component pass does not establish a product objective result.

## Related

- `src/linger/agents/serendipity/models.py` — grants, evidence, rubric,
  shortlist, proposal, and decline contracts.
- `src/linger/agents/serendipity/tools.py` — bounded Librarian tool and guarded
  maintained Exa capability.
- `src/linger/agents/serendipity/agent.py` — reusable Agent and output validator.
- `src/linger/agents/serendipity/skills.py` — assigned connection-discovery,
  memory-recall, and source-gathering tasks.
- `src/linger/agents/serendipity/prompt.py` — effective instruction and contract
  fingerprint exports.
- `src/linger/orchestration/connection.py` — trusted dependency construction,
  run invocation, evidence ledger validation, and fail-closed behavior.
- `src/linger/orchestration/turn_context.py` — shared request-scoped book-
  evidence index.
- `apps/backend/sessions.py` — released evidence handles without passage text.
- `src/linger/agents/muse/tools.py` — Muse invocation tool and validated
  decision-plus-evidence handshake.
- `src/linger/agents/provenance/` — mandatory review before display.
- `docs/specification.md` sections 2, 4, 4.2.3, 5.3, 5.6, 6.1, 6.4, 6.5, and
  7.2.
