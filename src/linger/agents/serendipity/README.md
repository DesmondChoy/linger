# Serendipity

Serendipity is Linger's optional search-and-connection specialist. It searches
multiple permitted sources, removes ineligible evidence, constructs possible
connections, compares the strongest two or three with an anchored rubric, and
returns exactly one `ConnectionProposal` or one `ConnectionDecline`.

Books are one internal source, not Serendipity's domain or entry condition.
Linger is a personal reflection and memory companion. A current cue may connect
to an authorised memory without any book context, or to public-web evidence
without pretending that Librarian searches the web.

Serendipity has no write or release authority. Muse owns the conversation,
Librarian owns internal retrieval, Exa supplies public-web search, application
code owns access grants, and Provenance reviews every complete Muse draft.

## Inputs and authority

Application orchestration creates one `ConnectionDiscoveryInput` containing:

- a request ID and the active reader cue;
- an optional description of the current user-supplied photograph;
- the connection intent and presentation policy; and
- a trusted `ConnectionScope` granting selected sources and any book ceilings.

The initial input contains authority, not prefetched search results. A typical
grant is:

```json
{
  "allowed_sources": ["authorised_memory", "book_corpus", "web"],
  "book_scopes": [
    {
      "work_id": "pg11",
      "book_version_id": "pg11-v01b38ea4",
      "chapter_max": 5
    }
  ]
}
```

Serendipity cannot add a source, choose an account, enable web access, change a
book revision, raise a chapter ceiling, or change presentation policy. Account
identity and service handles live in `SerendipityDependencies`, which tool code
can access but the model cannot see or supply.


## Search ownership

The ownership boundary is:

| Component | Search responsibility |
| --- | --- |
| Librarian | Authorised reader memories and spoiler-bounded book corpora |
| Serendipity | Chooses useful permitted searches and compares their results |
| Exa | Public-web search and page retrieval for Serendipity |
| Muse | Supplies the current conversational or photograph-derived cue |

`search_librarian` is a thin Pydantic AI tool over Linger's Librarian service.
The account comes from trusted dependencies, and every book query is clamped to
the granted revision and chapter ceiling. The maintained
`pydantic_ai_harness.exa.ExaSearch` capability supplies `web_search` and
`get_page`; Linger wraps that capability only to enforce source permission,
prevent private-memory wording from entering web queries, and record returned
URLs in the search trace plus opened pages in the evidence ledger.

## Search, shortlist, and selection flow

```text
Application grants source permissions
                ↓
Static instructions + ConnectionDiscoveryInput
                ↓
        Serendipity chooses permitted tools to conduct searches
          ├─ Librarian: Internal evidence - spoiler-bounded book excerpts/authorised memories 
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
```

Source grants are permissions, not mandatory search steps. Serendipity should
search the permitted sources relevant to the cue and may compare source types
when doing so could improve the result. It does not have to call Librarian or
Exa merely because either is available. It may refine a query and search several
records per source. A `web_search`
result is only a lead; Serendipity must use `get_page` to read a promising URL
before that URL enters the citable evidence ledger.

### Source-routing policy

Serendipity chooses one primary source from the reader's requested relationship,
not from the order of `allowed_sources`:

| Cue or intent | Primary search | Expansion rule |
| --- | --- | --- |
| External recommendation: essay, artwork, song, thinker, public source, or outside idea | Exa | Add an internal source only when the reader explicitly asks for a personal/book comparison or the web result is insufficient and the internal comparison is materially useful. |
| Recurrence in the reader's own life or prior reflections | Librarian: `authorised_memory` | Add Exa only when the reader also asks for an outside lens; add a book only when a confirmed work is part of the requested comparison. |
| Relationship within a confirmed work | Librarian: `book_corpus` | Add memory or web only when the cue explicitly asks to cross that domain or the bounded book evidence is insufficient. |
| Explicit comparison across domains | Every named, permitted domain | Do not add unnamed domains merely because they are granted. |
| Ambiguous reflective connection | Librarian: `authorised_memory` | Do not search the web just to manufacture novelty. Decline when internal evidence is weak. |

The execution sequence is primary search → sufficiency check → optional expansion
→ shortlist and compare. Expansion is justified only when the reader requested
the second domain, the primary search returned no or weak evidence, or the second
source is necessary for a materially better comparison. Serendipity stops once
the collected evidence supports two distinct eligible candidates. It never
searches both Librarian and Exa solely because both tools are available, to pad
the shortlist, or to avoid a valid decline.

If the requested primary source is unavailable or outside the application grant,
Serendipity declines rather than silently substituting another domain. For
example, an outside-essay request with no web grant does not become a memory
search merely because authorised memories are available.

Concrete routing examples:

| Reader cue | Expected calls |
| --- | --- |
| “Does the Caterpillar echo anything earlier in this book?” | Librarian book search only. |
| “Does this resemble something I have said before?” | Librarian memory search only. |
| “Recommend an essay or artwork that resonates with this feeling.” | Exa search and page retrieval only. |
| “Connect this chapter to something I saved and then suggest an outside essay.” | Librarian book and memory searches plus Exa. |

## Eligibility before ranking

Hard gates run before comparison. Evidence and candidates are ineligible when
they are out of scope, deleted or cross-account, past a spoiler ceiling,
unresolved, unsafe, injection-bearing, unsupported, or merely a generic theme
match. Ineligible material cannot win by scoring well elsewhere.

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
- closed memory, web, and consent policy flags.

The selected candidate contains the tentative claim, cited evidence IDs, shared
structure, meaningful difference, interpretation, rubric, and comparison note.
Consumers resolve `selected_candidate_id` against the shortlist; the model does
not duplicate the winner's content at the top level.

A `ConnectionDecline` contains a machine-readable reason, safe next step, and
up to three rejected candidates when retaining that comparison helps debugging.
Declining is a successful outcome.

## Deterministic validation

Tool calls populate an application-owned evidence ledger. After the model
returns, orchestration verifies that:

- every shortlisted evidence ID came from Librarian or Exa in this run;
- every returned record belongs to a granted source;
- every book record matches its revision and spoiler ceiling;
- a proposal followed at least one recorded permitted search;
- the selected candidate is the eligible rank-one candidate;
- memory and web flags match the winner's actual cited sources; and
- presentation policy is unchanged.

Exa URLs are their web evidence IDs. Search-result metadata records candidate
URLs in the search trace, while only a successfully opened `get_page` result is
stored as citable web evidence. A guarded wrapper rejects a web query that
copies private memory wording. Web tools are absent entirely when web access or
credentials are not granted.

## Where authority ends

A proposal is untrusted material for Muse, not a user-facing response. The
Serendipity agent still returns only `ConnectionProposal | ConnectionDecline`.
After deterministic validation, application orchestration wraps that decision
with the exact evidence records cited by the selected candidate for the Muse
tool handshake; losing-candidate evidence remains visible to inspection but is
not added to Muse's prompt. Muse may use only the selected bridge and its cited records to draft natural
language. Provenance receives the complete candidate, validated decision,
evidence bundle, and release policy, then checks attribution, privacy, spoilers,
sensitive inference, unsupported claims, and prompt injection. There is no
Serendipity-to-reader bypass.

Serendipity cannot save or curate memory. Telemetry and the shortlist explain a
decision but never authorise search, storage, or release.

For local evaluation, selecting a synthetic reader in the UI adds only that
reader's immutable fixture memories to Librarian's `authorised_memory` results.
The fixture does not bypass source routing, candidate comparison, Muse, or
Provenance, so the same handshakes remain visible in Inspect.

## Related

- `src/linger/agents/serendipity/models.py` — grants, evidence, rubric,
  shortlist, proposal, and decline contracts.
- `src/linger/agents/serendipity/tools.py` — bounded Librarian tool and guarded
  maintained Exa capability.
- `src/linger/agents/serendipity/agent.py` — search, filtering, comparison, and
  selection instructions.
- `src/linger/orchestration/connection.py` — trusted dependency construction,
  run invocation, evidence ledger validation, and fail-closed behavior.
- `src/linger/agents/muse/tools.py` — Muse invocation adapter and validated
  decision-plus-evidence handshake.
- `src/linger/agents/provenance/` — mandatory review before display.
- `docs/evaluation/synthetic-readers.md` — three isolated demo histories and
  the sequential UI test flow.
- `docs/specification.md` sections 2, 4, 4.2.3, 5.3, 5.6, 6.1, 6.4, 6.5, and
  7.2.
