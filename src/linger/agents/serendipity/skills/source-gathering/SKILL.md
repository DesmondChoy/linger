---
name: source-gathering
description: Gather the records for every source the reader named, without choosing among them, or decline.
---

Gather the sources the reader named so Muse can put them side by side. The JSON
input contains `cue`, `intent`, `presentation`, and `scope`. For this task
`intent` is `gather_sources`: the reader has already chosen which sources to
consider together, such as named books or scenes, a named public text, and
their own earlier writing. Return one bundle or one decline, following the
supplied output schema. A proposal is not a permitted result for this task:
do not build competing connections, rank them, or pick a winner.

Identify every source the cue names before searching, then inspect each one
that is permitted:
- Books, scenes, characters, or passages in the granted library: call
  `search_librarian` once with `work_ids` naming every requested, permitted
  book, and exclude books the reader did not name. Librarian plans the search
  from the reader's own words and judges which passages are relevant.
- The reader's own earlier words, plan, promise, or note ("what I wrote",
  "the thing I said I'd do"): use `search_memories` to find what it refers to.
- A named public text or thinker: when `get_page` is present, open a supplied
  URL directly; when none is supplied and `web_search` is present, search for
  the named text and open only an exact URL it returns. An opened page's
  evidence ID is its exact URL; a `web_search` result is only a lead.
Search only for the sources the reader named. Permission to search a source
does not make an unnamed source part of the request.

Account for each supplied `scope.web_source_urls` entry in
`public_source_checks`. When it is the public source the reader requests, copy
the exact words that refer to it from `cue` into `requested_as`; an indirect
reference such as "that essay" counts. Open that URL with `get_page` before
returning the bundle, including before calling the source unfound. A URL that
the reader did not request has `requested_as=null` and need not be opened.
An allowlist alone does not make every URL a requested source. With no supplied
URLs, return an empty `public_source_checks` list.

Return every record that supports a named source as `evidence_ids`, using only
exact evidence IDs returned by this run's tools. Include every book passage
`search_librarian` returned: Librarian already judged it relevant to what the
reader named. Include every page you opened with `get_page`, cited by its URL:
you open only the public texts the reader named. Include a memory only when it is the reader's own earlier
writing that the cue refers to, and a public page only when it is the named
text. Never add a record to make the bundle look fuller.

List in `unfound_sources` each named source that no returned record supports,
in the reader's own short wording ("Keller at the lake"). A source that was
searched and not found belongs there; do not drop it silently or substitute a
different source for it.

Use `relevance_note` to say briefly which record answers which named source.
Do not interpret the sources, compare them, judge whether they support the
reader's conclusion, or draft the reply. Muse writes the comparison and
Provenance reviews it.

Declining is a successful result. Decline with reason `no_permitted_evidence`
when none of the named sources is permitted, `insufficient_evidence` when no
returned record supports any named source, or `retrieval_unavailable` when the
searches could not run. Never stretch an unrelated record to avoid declining.
