---
name: connection-discovery
description: Search permitted sources, compare supported connections, and propose one winner or decline.
---

Apply this skill to one ConnectionDiscoveryInput. Use its reader cue, intent,
presentation policy, and source grants to discover a tentative connection.
Return ConnectionProposal or ConnectionDecline; the Pydantic contracts define
the exact schemas and ranking constraints. This skill performs source selection
and comparison. It does not infer reading progress, draft the reader's reply,
review a candidate, or save a memory.

Search before proposing. You may use:
- `search_memories` for active records authorized to the current account;
- `search_librarian` for the permitted, spoiler-bounded book corpus;
- Exa `web_search` and `get_page` only when those tools are present, which means
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
  outside Linger, use Exa as the primary source.
- Book relationship: when the cue asks about another passage, character,
  chapter, or pattern inside a confirmed work, use `search_librarian` first.
- Explicit cross-domain request: when the cue itself asks to compare two source
  domains, search each named and permitted domain. For example, “connect this
  chapter with an outside essay” warrants book and web searches.
- Ambiguous reflective connection: use the confirmed book only when the cue
  invites a specific textual relationship. Do not search the web simply to make
  a reflection feel more interesting; decline when no permitted source fits.

Search the primary source first, then assess its returned records. Expand to a
second source only when the reader explicitly requested that source, the first
source returned no or weak evidence, or the second source is necessary to form
a materially better comparison. Stop searching once the available evidence can
support two distinct eligible candidates. Never call both Librarian and Exa
solely because both are available, to pad the shortlist, or to avoid declining.
If an explicitly requested source is not granted, decline rather than silently
substituting a different source.

Librarian may return several internal records and Exa may return several
public-web records. Cite only exact evidence IDs returned during this run. For web evidence, the evidence ID is the exact returned URL.

Use web_search only for a public connection that could materially deepen the
current cue. Read promising pages with get_page. Never put private memory
wording or identifying reader details in a query. Keep web searches concise and
derive them only from non-identifying concepts in the current cue. Never paste
the reader's full wording into a query. Prefer primary or authoritative web sources.

Use this sequence:
1. Classify the cue using the routing policy and choose its primary source.
2. Search that primary source, or every explicitly requested cross-domain
  source.
3. Assess whether the returned evidence is sufficient; expand once only when
   the routing policy permits it.
4. Construct distinct possible connections between the cue and eligible
   evidence.
5. Shortlist the strongest two or three. Never pad the shortlist with an
   ineligible candidate; decline if two eligible candidates cannot be formed.
6. Compare the shortlist using the rubric below.
7. Return exactly one ConnectionProposal naming the rank-one candidate, or one
   ConnectionDecline.

Rubric anchors are ordinal judgments, not probabilities and not numbers to add:
- `cue_fit`: direct means it answers this exact cue; partial needs an inferential
  step; weak could fit many unrelated cues.
- `reflective_value`: high materially changes how the cue may be seen; medium
  adds a useful angle; low mostly restates it.
- `safety`: clear stays within all boundaries; review has unresolved risk;
  ineligible violates a boundary.

Use `comparison_note` to state why each candidate ranks above or below another.
Set `contains_web_claim` exactly when the winner cites web evidence.

Declining is a successful result. Decline when retrieval fails, evidence is
missing or weak, fewer than two eligible candidates survive, the relationship
is generic or forced, or no candidate clearly wins. Never manufacture a
connection to avoid declining.
