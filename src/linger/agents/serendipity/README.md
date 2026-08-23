# Serendipity

Serendipity is Linger's optional search-and-connection specialist. It searches
permitted sources, removes ineligible evidence, constructs possible
connections, compares the strongest two or three with an anchored rubric, and
returns exactly one `ConnectionProposal` or one `ConnectionDecline`.

The current slice permits spoiler-bounded book evidence and optional public-web
discovery. A selected book-only proposal may enter the ordinary Muse,
Provenance, and deterministic release path. Web-backed proposals remain
internal and fail closed. Account-scoped stored-memory and image evidence remain
later slices.

Serendipity has no write or release authority. Muse owns the conversation,
Librarian owns internal retrieval, Exa supplies public-web search, application
code owns access grants, and Provenance reviews every complete Muse draft.

## Inputs and authority

Application orchestration creates one `ConnectionDiscoveryInput` containing:

- the active reader cue;
- the connection intent and presentation policy; and
- a trusted `ConnectionScope` granting selected sources and any book ceilings.

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
raise a chapter ceiling, or change presentation policy. The canonical Librarian
service is supplied through `SerendipityDependencies`, which tool code can
access but the model cannot see or supply.

## Search ownership

The ownership boundary is:

| Component | Search responsibility |
| --- | --- |
| Application | Supplies the exact current reader message as the cue and owns source grants |
| Librarian | Spoiler-bounded book corpora |
| Serendipity | Chooses useful permitted searches and compares their results |
| Exa | Public-web search and page retrieval for Serendipity |
| Muse | Chooses whether to invoke connection discovery and supplies its intent |

`search_librarian` is a thin Pydantic AI tool over Linger's existing Librarian
service. Every book query is clamped to the granted revision and chapter
ceiling. The maintained
`pydantic_ai_harness.exa.ExaSearch` capability supplies `web_search` and
`get_page`; Linger wraps that capability only to enforce source permission,
bound query size, reject personal data and every multi-character term copied
verbatim from the reader's cue, require
`get_page` URLs to come from the current run's search results, and record opened
pages in the evidence ledger.

## Search, shortlist, and selection flow

```text
Application grants source permissions
                ↓
Static instructions + ConnectionDiscoveryInput
                ↓
        Serendipity chooses permitted tools to conduct searches
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
       ├─ selected book records: eligible for release
       └─ any web record: fail closed
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

### Source-routing policy

Serendipity chooses one primary source from the reader's requested relationship,
not from the order of `allowed_sources`:

| Cue or intent | Primary search | Expansion rule |
| --- | --- | --- |
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

- every shortlisted evidence ID came from Librarian or Exa in this run;
- every returned record belongs to a granted source;
- every book record matches its revision and spoiler ceiling;
- a proposal followed at least one recorded permitted search;
- the selected candidate is the eligible rank-one candidate;
- web flags match the winner's actual cited sources; and
- presentation policy is unchanged.

Only the exact records cited by the selected candidate leave this ledger. If
they are all book-corpus records, orchestration converts them to the canonical
frozen `EvidenceRecord` contract and adds them to the request-scoped book-
evidence index. A selected web record is validated as Serendipity input but is
not added to that trusted release index.

Exa URLs are their web evidence IDs. Search-result metadata supplies
request-local page leads, while only a successfully opened `get_page` result is
stored as Serendipity-citable web evidence. A guarded wrapper bounds each web
query and
requires it to use a general concept rather than personal data or any
multi-character term copied verbatim from the reader's cue. It also rejects any page URL that was not returned by the
current run's search. Web tools are absent entirely when web access or
credentials are not granted.

## Shared book-evidence boundary

Muse, Provenance, and deterministic release validation read one application-
owned, request-scoped map of exact book records. It has only three inputs:

- direct Librarian results from the current Muse run;
- the exact selected records from a current book-only Serendipity proposal; and
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
Serendipity agent still returns only `ConnectionProposal | ConnectionDecline`.
After deterministic validation, application orchestration wraps that decision
with the exact evidence records cited by the selected candidate for the Muse
tool handshake; losing-candidate evidence stays inside the Serendipity run and
is discarded instead of being added to Muse's tool result or Inspect. Muse may
surface a selected book-only proposal only by declaring every book record it
uses. Provenance receives the complete Muse candidate, validated tool result,
shared trusted book evidence, and release policy, then checks attribution,
privacy, spoilers, sensitive inference, unsupported claims, and prompt
injection. Application code resolves every declaration against the same records
after a semantic pass. There is no Serendipity-to-reader bypass.

Serendipity cannot save or curate memory. Telemetry and fixed request-local
outcome metadata report a decision but never authorise search, storage, or release.

In the current release slice, Serendipity cannot widen citation or public-
release authority. A book-only proposal uses the existing book contract; a
proposal containing web evidence fails closed, and its content-bearing
diagnostics are not returned by the API. Stored-memory and image evidence remain
unsupported. A validated decline may still be relayed with fixed inspection
metadata.

## Related

- `src/linger/agents/serendipity/models.py` — grants, evidence, rubric,
  shortlist, proposal, and decline contracts.
- `src/linger/agents/serendipity/tools.py` — bounded Librarian tool and guarded
  maintained Exa capability.
- `src/linger/agents/serendipity/agent.py` — search, filtering, comparison, and
  selection instructions.
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
