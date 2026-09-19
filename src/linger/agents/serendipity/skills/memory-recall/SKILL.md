---
name: memory-recall
description: Find the reader's own earlier records on what the cue asks about, or decline.
---

Recall what the reader has already written about the supplied cue. The JSON
input contains `cue`, `intent`, `presentation`, and `scope`. For this task
`intent` is `recall_memory` and `scope.allowed_sources` grants memory only.
Return one recall or one decline, following the supplied output schema. A
proposal is not a permitted result for this task.

Search before answering. Use `search_memories`, which reads only the active
records authorized to the current account. Search for what the cue asks about
or returns to; a second search with different wording is reasonable when the
first finds nothing. No book or public-web source is available for this task.

A record matches only when it is the reader's own earlier words on the same
fact, preference, decision, or personal theme that the cue asks about or
returns to: a record the reader would recognise as the thing they wrote
before. One matching record is a complete recall. Return the one to three
matching records, most directly relevant first, as `evidence_ids`, using only
exact evidence IDs returned by this run's `search_memories` calls.

A record that only shares vocabulary with the cue, or that offers a general
lesson, analogy, transferable tactic, or shared mood, is not a match. Never
include a record to make the recall look fuller.

Use `relevance_note` to say briefly why the records address the cue. Do not
quote the records at length, interpret them, compare or rank interpretations,
propose a connection, or draft the reader's reply. Muse writes the reply and
Provenance reviews it.

Declining is a successful result. When no returned record matches, decline
with reason `no_matching_memory`. When the search itself could not run,
decline with reason `retrieval_unavailable`. Never stretch an unrelated record
into an answer to avoid declining.
