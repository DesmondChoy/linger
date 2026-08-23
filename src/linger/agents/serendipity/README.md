# Serendipity

Serendipity is Linger's optional search-and-connection specialist. It searches
permitted sources, removes ineligible evidence, constructs possible
connections, compares the strongest two or three with an anchored rubric, and
returns exactly one `ConnectionProposal` or one `ConnectionDecline`.

The current slice permits spoiler-bounded book evidence and optional public-web
discovery. Account-scoped stored-memory retrieval remains a later slice.

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
```

Source grants are permissions, not mandatory search steps. Serendipity should
search the permitted sources relevant to the cue and may compare source types
when doing so could improve the result. It does not have to call Librarian or
Exa merely because either is available. It may refine a query and search several
records per source, within a hard run budget of eight model requests and six
total tool calls. A `web_search`
result is only a lead; Serendipity must use `get_page` to read a promising URL
before that URL enters the citable evidence ledger.

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

Exa URLs are their web evidence IDs. Search-result metadata supplies
request-local page leads, while only a successfully opened `get_page` result is
stored as citable web evidence. A guarded wrapper bounds each web query and
requires it to use a general concept rather than personal data or any
multi-character term copied verbatim from the reader's cue. It also rejects any page URL that was not returned by the
current run's search. Web tools are absent entirely when web access or
credentials are not granted.

## Where authority ends

A proposal is untrusted material for Muse, not a user-facing response. The
Serendipity agent still returns only `ConnectionProposal | ConnectionDecline`.
After deterministic validation, application orchestration wraps that decision
with the exact evidence records cited by the selected candidate for the Muse
tool handshake; losing-candidate evidence stays inside the Serendipity run and
is discarded instead of being added to Muse's tool result or Inspect. In the current slice, Muse
keeps proposals internal. Provenance receives the complete Muse candidate,
validated tool result, and release policy, then checks attribution, privacy,
spoilers, sensitive inference, unsupported claims, and prompt injection. There
is no Serendipity-to-reader bypass.

Serendipity cannot save or curate memory. Telemetry and fixed request-local
outcome metadata report a decision but never authorise search, storage, or release.

In the current release slice, a Serendipity proposal cannot widen citation or
public-release authority. Until typed deterministic citation validation covers
these sources, application release logic fails every proposal-bearing turn
closed; its content-bearing diagnostics are not returned by the API. A
validated decline may still be relayed with fixed inspection metadata.

## Related

- `src/linger/agents/serendipity/models.py` — grants, evidence, rubric,
  shortlist, proposal, and decline contracts.
- `src/linger/agents/serendipity/tools.py` — bounded Librarian tool and guarded
  maintained Exa capability.
- `src/linger/agents/serendipity/agent.py` — search, filtering, comparison, and
  selection instructions.
- `src/linger/orchestration/connection.py` — trusted dependency construction,
  run invocation, evidence ledger validation, and fail-closed behavior.
- `src/linger/agents/muse/tools.py` — Muse invocation tool and validated
  decision-plus-evidence handshake.
- `src/linger/agents/provenance/` — mandatory review before display.
- `docs/specification.md` sections 2, 4, 4.2.3, 5.3, 5.6, 6.1, 6.4, 6.5, and
  7.2.
