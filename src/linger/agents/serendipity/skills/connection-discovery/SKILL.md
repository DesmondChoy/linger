---
name: connection-discovery
description: Search permitted sources, compare supported connections, and propose one winner or decline.
---

Find a tentative, evidence-supported connection for the supplied reader cue.
The JSON input contains `cue`, `intent`, `presentation`, and `scope`. Return
one proposal with a ranked shortlist and selected candidate, or one decline.
Follow the supplied output schema and preserve the input's `presentation`
value in a proposal. This task selects and compares sources; it does not infer
reading progress, draft the reader's reply, review a candidate, or save a memory.

Search before proposing. You may use:
- `search_memories` for active records authorized to the current account;
- `search_librarian` for the permitted, spoiler-bounded book corpus;
- `web_search` and `get_page` only when those tools are present, which means
  public-web access was explicitly granted for this run. When
  `scope.web_source_urls` is supplied, only those exact public URLs may become
  source evidence. Search for those pages, then open their exact search leads;
  missing or inaccessible permitted pages are unavailable evidence.

Choose a primary source before searching. A source grant is permission, not an
instruction to search every available source. Apply this routing policy:

- Personal-context connection: use `search_memories` when the cue asks to relate
  the current reflection to the person's authorized prior context.
- External recommendation: when `intent` is `get_recommendation`, or the cue
  explicitly asks for an essay, artwork, song, thinker, public source, or idea
  outside the supplied book or personal context, use `web_search` as the
  primary source.
- Book relationship: when the cue asks about another passage, character,
  chapter, or pattern inside a confirmed work, use `search_librarian` first.
- Explicit cross-domain request: when the cue itself asks to compare two source
  domains, search each named and permitted domain. For example, “connect this
  chapter with an outside essay” warrants book and web searches.
- Ambiguous reflective connection: use the confirmed book only when the cue
  invites a specific textual relationship. Do not search the web simply to make
  a reflection feel more interesting; decline when no permitted source fits.

Search the primary source first, then assess its returned records. Expand at
most once to a second source only when the reader explicitly requested it,
the first source returned no or weak evidence, or the second source is necessary to form
a materially better comparison. Stop searching once the available evidence can
support two distinct eligible candidates. Never call both `search_librarian`
and `web_search` solely because both are available, to pad the shortlist, or
to avoid declining.
If an explicitly requested source is not granted, decline rather than silently
substituting a different source.

Cite only exact evidence IDs returned by this run's permitted tools. A
`web_search` result is a lead, not citable evidence: open its exact URL with
`get_page` before citing it. Web evidence IDs are the exact opened URLs.

Use `web_search` only for a public connection that could materially deepen the
current cue. Never put private memory wording or identifying reader details
in a query. Keep web searches concise and
derive them only from non-identifying concepts in the current cue. Never paste
the reader's full wording into a query. Prefer primary or authoritative web sources.

A proposal requires two or three distinct, eligible candidates. A candidate
is eligible only when `cue_fit` is `direct` or `partial`, `reflective_value` is
`high` or `medium`, `safety` is `clear`, and `disqualifiers` is empty. Never pad
the shortlist with an ineligible candidate.

Rubric anchors are ordinal judgments, not probabilities and not numbers to add:
- `cue_fit`: direct means it answers this exact cue; partial needs an inferential
  step; weak could fit many unrelated cues.
- `reflective_value`: high materially changes how the cue may be seen; medium
  adds a useful angle; low mostly restates it.
- `safety`: clear stays within all boundaries; review has unresolved risk;
  ineligible violates a boundary.

Rank candidates by `cue_fit` first, then `reflective_value`, then `safety`,
using the rubric's stated order. The first candidate must outrank the second;
select its `candidate_id` as `selected_candidate_id`. Decline if the strongest
two remain tied; do not inflate ratings to force a winner.

Use `comparison_note` to state why each candidate ranks above or below another.
Set `contains_web_claim` exactly when the winner cites web evidence.

Declining is a successful result. Decline when retrieval fails, evidence is
missing or weak, fewer than two eligible candidates survive, the relationship
is generic or forced, or no candidate clearly wins. Never manufacture a
connection to avoid declining.
