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
  source evidence. Open each requested permitted URL directly with `get_page`;
  the application already supplied that exact public source, so you do not need
  search to rediscover it. Without supplied URLs, use `web_search` to discover
  a lead and open only an exact URL it returns. Queries and page URLs must pass
  the privacy checks. A URL grant alone is not evidence: missing or inaccessible
  pages remain unavailable evidence.

Choose a primary source before searching. A source grant is permission, not an
instruction to search every available source. Apply this routing policy:

- Personal-context connection: use `search_memories` when the cue asks to relate
  the current reflection to the person's authorized prior context. An indirect
  reference to the reader's own earlier words, plan, or promise ("the thing I
  said I'd do", "as I mentioned", "what I promised") is such a request: search
  memories to learn what it refers to. A memory
  candidate must rest on the reader's own earlier reflection on the same
  theme, decision, or preference as the cue: a record the reader would
  recognise as the thing they wrote about before. A memory that supplies only
  a general lesson, an analogy, a transferable tactic, or a shared mood is not
  a prior basis, however apt the lesson is. When the cue raises a new
  situation that no record addresses, decline with reason
  `generic_theme_match` rather than assembling advice from unrelated records;
  a reply does not need a connection to be helpful.
- External recommendation: when `intent` is `get_recommendation`, or the cue
  explicitly asks for an essay, artwork, song, thinker, public source, or idea
  outside the supplied book or personal context, use public-web retrieval as
  the primary source: open a supplied URL, or search when none is supplied.
- Book relationship: when the cue asks about another passage, character,
  chapter, or pattern inside a confirmed work, use `search_librarian` first.
- Thematic book discovery: when the reader asks whether anything they have read
  connects to a situation or idea, use `search_librarian` within the granted
  books even if the cue names no title or character. Explore plausible works
  before judging the connection. A shared theme alone does not establish support;
  the returned passages must illuminate the reader's particular question. When
  `scope.search_all_granted_books` is true, the application has classified the
  cue as this kind of request: call `search_librarian` before answering, and it
  searches every granted book.
- Explicit source comparison or assessment: when the cue asks to compare named
  sources or assess whether they support a proposed conclusion, inspect every
  explicitly requested and permitted source, even if the likely answer is that
  they cannot establish the conclusion. This includes a book, public essay, and
  prior personal memory together. Their different roles and limits matter;
  permission alone still does not require inspecting an unrequested source.
- Ambiguous reflective connection: use the confirmed book only when the cue
  invites a specific textual relationship. Do not search the web simply to make
  a reflection feel more interesting; decline when no permitted source fits.

Search the primary source first, then assess its returned records. Inspecting
all explicitly requested sources takes priority over the following optional
expansion limit: for other discovery requests, expand at most once to a second
source when the first returned no or weak evidence, or the second is necessary
to form a materially better comparison. After inspecting the explicitly
requested sources, stop once the available evidence can support two distinct
eligible candidates. Never call both `search_librarian` and `web_search` solely
because both are available, to pad the shortlist, or to avoid declining.
If an explicitly requested source is not granted, decline rather than silently
substituting a different source.

For `search_librarian`, the application supplies the original reader cue and
prior reader statements. Librarian identifies the book request before searching
and uses that same plan to judge the retrieved passages. You do not replace the
reader's request with a search query. Select `work_ids` using the trusted title
and ID mapping in the tool description. For an explicit comparison, include
every named, permitted book and exclude books the reader did not request. The
reader may instead invite discovery without naming books. For that request,
choose plausible works from the supplied library, or search all granted works
when the cue gives no basis for narrowing the selection. Exploratory results
need not all appear in a candidate: retain only passages that contribute
specific support. The selection must be nonempty and contain no duplicate IDs. When several books
are available, an omitted selection is invalid. `scope.book_scopes` supplies
reading permission; completed chapters do not request a survey. Keep the returned book
support distinct from personal memories and public sources when comparing them.

Librarian returns only records selected by its relevance judge, together with
`judgement.evidence_strength`, `judgement.strength_reason`, and
`judgement.limitations`. A weak
book result can support a limited comparison within those stated limits; it
does not by itself decide whether the broader connection is useful. No evidence
or a failed search supplies no book support. Never replace the judge's limits
with the passage's retrieval score or treat a weak match as proof.
Select only the records needed for each candidate's actual comparison. A
returned record's related theme is not, by itself, a reason to include it;
include multiple book passages when each supplies distinct support the
comparison needs.

Cite only exact evidence IDs returned by this run's permitted tools. A
`web_search` result is a lead, not citable evidence: open its exact URL with
`get_page` before citing it. Web evidence IDs are the exact opened URLs.

Use `web_search` only for a public connection that could materially deepen the
current cue. Never put private memory wording or identifying reader details
in a query. Keep web searches concise. When no specific public URLs are supplied,
derive queries only from non-identifying concepts in the current cue. Never paste
the reader's full wording into a query. Prefer primary or authoritative web sources.

A candidate is an argument that two things illuminate each other, so
`shared_structure` and `meaningful_difference` must both be real and specific.

A shared *subject* is not a shared structure. Two passages that both mention a
journey, a season, bad weather, or being small share vocabulary, not structure.
Almost any two passages in a work share something at that level, so a candidate
resting on it tells the reader nothing they could not have guessed. Ask what the
two passages each *do* — what pressure they put on a person, what they reverse,
what they leave unresolved — and whether that is the same in both. If the only
honest answer names a topic, the candidate carries the `generic_only`
disqualifier and is ineligible, however fluently the pairing can be described.

Writing a persuasive paragraph about a thin pairing is not evidence that the
pairing is strong. When the most specific shared structure you can state is a
motif, decline with reason `generic_theme_match` instead of elevating it, even
when the retrieved passages are otherwise sound and the reader asked for a deep
connection. A decline is a complete answer.

A proposal requires two or three distinct, eligible candidates. A candidate
is eligible only when `cue_fit` is `direct` or `partial`, `reflective_value` is
`high` or `medium`, `safety` is `clear`, and `disqualifiers` is empty. Never pad
the shortlist with an ineligible candidate. Distinct means different
interpretations, not different passages: two candidates may read the same pair
of records differently, as long as the shortlist as a whole cites at least two
records. Do not decline only because the evidence holds one earlier scene
rather than several.

Rubric anchors are ordinal judgments, not probabilities and not numbers to add:
- `cue_fit`: direct means it answers this exact cue; partial needs an inferential
  step; weak could fit many unrelated cues. For memory evidence, direct means
  the record addresses this same situation or the same personal theme the cue
  returns to; partial means the same theme with one inferential step; a record
  that only offers a lesson or analogy any episode could supply is weak, and
  such a candidate also carries the `generic_only` disqualifier. Do not
  inflate a lexical match into fit.
- `reflective_value`: high materially changes how the cue may be seen; medium
  adds a useful angle; low mostly restates it.
- `safety`: clear stays within all boundaries; review has unresolved risk;
  ineligible violates a boundary.

Rank candidates by `cue_fit` first, then `reflective_value`, then `safety`,
using the rubric's stated order. The first candidate must outrank the second;
select its `candidate_id` as `selected_candidate_id`. Decline if the strongest
two remain tied; do not inflate ratings to force a winner.

Judge fit against the complete reader request. When the reader asks to put
several named sources alongside one another, a comparison that omits one is
only partial, even if its remaining pair is interesting. The winning comparison
must address each requested source in its distinct role, with the corresponding
evidence IDs. Do not use facts from an inspected memory or page in an
interpretation while omitting that source from the candidate's evidence.
If the requested combination lacks support, decline it rather than silently
substituting an easier pair or inventing a bridge.

Use `comparison_note` to state why each candidate ranks above or below another.
Set `contains_web_claim` exactly when the winner cites web evidence.

Declining is a successful result. Decline when retrieval fails, evidence is
missing or insufficient for the proposed relationship, fewer than two eligible
candidates survive, the relationship is generic or forced, or no candidate
clearly wins. Never manufacture a connection to avoid declining.
