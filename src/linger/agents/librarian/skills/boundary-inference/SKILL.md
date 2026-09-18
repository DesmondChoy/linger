---
name: boundary-inference
description: Infer supported chapter progress or exact already-read passages before retrieval.
---

The JSON input contains `current_line`, earlier reader messages in
`prior_reader_statements`, relevant saved records in `relevant_memories`, and
passages in `full_work_candidates` retrieved from across one immutable book
version.
When prior reader statements are supplied, every candidate is one canonical
paragraph. Statement IDs identify reader messages, not assistant summaries or
memories.

Your job is to distinguish chapter-progress support from narrow permission to
revisit an already-read passage. Do not answer the reader, summarize the story,
return passage text, or infer progress from general world knowledge.

Session-supported passages:
- Return `passages` when an earlier supplied reader statement genuinely reports
  reading a scene and `current_line` asks to revisit a specific fragment of
  that same known scene. Use this narrow outcome for scene descriptions; reaching
  a scene does not establish completion of its containing chapter.
- Select supporting_statement_ids from the original earlier reader messages.
  `current_line` alone cannot authorize disclosure. Memories and assistant
  wording cannot substitute for those earlier reader statements.
- Select supporting_evidence_ids for paragraphs locating the scene established
  by those earlier statements. These anchors are not automatically disclosed.
- Separately select passage_evidence_ids for only the exact requested fragment
  the reader already describes knowing. Select the fewest necessary paragraphs,
  at most five. Do not include surrounding paragraphs merely for helpful context.
  Reading anchors and requested paragraphs can differ within that same known
  exchange; neither their chapter number nor proximity proves a later event read.
- For example, an earlier report of reading a captain's farewell, followed by
  a request for the exact words of the farewell already paraphrased by the
  reader, can authorize that reply's paragraph. It does not authorize the
  voyage that follows or every paragraph in the containing chapter.
- Do not authorize from curiosity, an adaptation, overheard or second-hand
  information, a quotation alone, a hypothetical reading plan, or mere names.
  A reading pace such as two chapters a night is not completed-chapter evidence.
- Read the whole earlier statement and `current_line`, including negation and
  corrections. An explicit correction that the reader has not reached the scene
  defeats an older claim. Other-work statements do not establish this work read.
- If the requested event might be later than the established scene, or a single
  candidate paragraph contains inseparable unreached material, return `uncertain`.
  Do not invent smaller IDs or trim text to conceal an unsafe paragraph.
- Confidence measures certainty that these exact paragraphs are already known,
  not their relevance to the question. Ambiguity requires clarification.
- Declare `authorization_basis=session_supported` and cite the supporting
  earlier reader statements only when those statements genuinely report
  reading the scene. Declare `authorization_basis=line_only`, with no
  statement IDs, when only `current_line` locates the fragment.
  A line-only decision reports a location for clarification; it does not grant
  permission to disclose that fragment.

Current event identification before a chapter candidate:
- Distinguish “this passage fits” from “the reader identified this occurrence”.
  A memory repeating the same vague event is not independent identification.
  The reader's inability to recall the animal, speaker, destination, setting,
  cause, or sequence matters when that missing detail distinguishes occurrences.
  Never fill that gap with details learned only from a candidate passage.
- Consider all supplied passages for alternative occurrences, including lower
  ranked passages. A single retrieved match does not prove uniqueness: this is
  a bounded search, not an exhaustive inventory of the book. If the reader has
  explicitly lost the details that identify the event, return uncertain unless
  other original reader wording actually resolves the missing identification.
- A candidate requires event_resolution. Copy event_resolution.reader_event_spans exactly from
  current_line or prior_reader_statements. Include the stopping event and any
  qualifying uncertainty or negation needed to interpret it. Memories may
  support prior knowledge but cannot supply these current identification spans.
- Group passages describing the same occurrence into one event_resolution.occurrences entry.
  Mark exactly one identified occurrence selected. Its distinguishing_reader_spans
  must quote actual reader details identifying that occurrence, not just shared
  theme words such as “return”, “tomorrow”, or “pet disappeared”. Explain how
  those details identify the stopping event, without inventing missing facts.
- Include every plausible competing occurrence as ruled_out only when exact
  reader wording positively excludes it; cite that wording in its
  distinguishing_reader_spans and explain the distinction. If two occurrences
  remain compatible, return uncertain rather than selecting the earliest,
  highest ranked, most famous, or latest one. Do not put a plausible alternative
  in event_resolution.other_evidence_ids to avoid comparing it.
- Put remaining unrelated records and earlier memory anchors in
  event_resolution.other_evidence_ids. This required array is nested inside
  event_resolution alongside reader_event_spans and occurrences, never at the
  top level. Supply [] only when every candidate is assigned to an occurrence.
  Account for every supplied candidate exactly once across
  event_resolution.occurrences[*].evidence_ids and
  event_resolution.other_evidence_ids. A memory anchor already cited in
  memory_assessments or supporting_evidence still needs its own inventory
  entry. Those support citations are separate from occurrence accounting.
  Do not duplicate a ruled-out occurrence in other_evidence_ids. Being in this private inventory grants
  nothing. Select only the needed current-event and memory anchors as boundary
  support. Include a quoted anchor for every selected-occurrence evidence ID in supporting_evidence;
  if a record is unnecessary to identify that occurrence, reassess its inventory
  placement instead of leaving selection and support inconsistent.
  The selected current occurrence must establish the candidate chapter.
- A specific sequence of completed reading can identify its final stop even
  when earlier events and memory anchors are in different chapters. Do not
  confuse a sequence the reader explicitly reports completing with alternative
  possibilities the reader cannot distinguish.

Private source binding before a chapter candidate:
- supporting_evidence contains objects with evidence_id and source_excerpt, not bare IDs.
  For every permission anchor, copy a brief contiguous event-identifying clause
  from that exact supplied record, preferably 5–12 words. Choose the action or
  distinguishing detail supporting the remembered event, current stop or
  connection, rather than copying its narrative setup or an entire paragraph.
  Read the full record to assess support; the short excerpt binds that record
  and does not replace the complete event-identification judgment. Use a longer
  span only when necessary to preserve the event's meaning or distinguishing detail.
  Only whitespace, including line wrapping, may differ. Preserve every word,
  original pronoun, capitalization, punctuation and markup; do not correct or
  paraphrase the text. Prefer a concise span supporting the event. Do not infer a chapter from
  a section ordinal in an ID; read the canonical chapter metadata and source text.
- Every grounded-memory and selected-occurrence evidence ID needs one such anchor.
  Additional connecting evidence may be included with its own source excerpt.
  Whitespace-normalized text membership only binds the record: a real but irrelevant excerpt
  does not support the event. Recheck semantic relevance before returning candidate.
- These excerpts stay private. Do not answer the reader or disclose them in a
  route handoff. Uncertainty grants nothing and does not require excerpt anchors.

Candidate field placement example:
The following excerpt shows inventory placement for three hypothetical input
IDs. Use the actual supplied IDs and exact reader wording, and fill the other
required candidate fields. Here the earlier-memory ID is both boundary support
and other event-resolution evidence; the alternative occurs only once in the
inventory.

```json
{
  "supporting_evidence": [
    {"evidence_id": "earlier-memory-id", "source_excerpt": "The captain declined the invitation."},
    {"evidence_id": "current-stop-id", "source_excerpt": "She returned after the storm."}
  ],
  "event_resolution": {
    "reader_event_spans": ["I stopped at the return after the storm."],
    "occurrences": [
      {
        "evidence_ids": ["current-stop-id"],
        "disposition": "selected",
        "distinguishing_reader_spans": ["after the storm"],
        "explanation": "The stated cause identifies this return."
      },
      {
        "evidence_ids": ["alternative-return-id"],
        "disposition": "ruled_out",
        "distinguishing_reader_spans": ["after the storm"],
        "explanation": "This alternative follows a different event, not the stated storm."
      }
    ],
    "other_evidence_ids": ["earlier-memory-id"]
  }
}
```

Before returning a candidate, compare its complete inventory with
full_work_candidates. Repair missing, unknown, and repeated IDs together.
Moving a misplaced field or removing a duplicate does not excuse omitting
earlier memory anchors. If valid semantic identification is unavailable,
return uncertainty instead of inventing a complete-looking proof.

Uncertainty output:
- Use BoundaryUncertainDecision when progress remains unresolved. Return only
  memory_assessments, outcome="uncertain", confidence and reason_code. Do not
  add work_id, book_version_id, chapter_number, authorization_basis,
  supporting_memory_ids, supporting_evidence, event_resolution or reason.
  Individual memory assessments can retain their canonical evidence and reason;
  those private assessments are not a scope grant.
- A high-confidence compatible passage is still uncertain when the occurrence
  is unidentified. Confidence is not permission and cannot fill missing detail.

Memory-supported chapter inference:
- Fill `memory_assessments` before choosing the outcome and authorization basis.
  Include one entry for every supplied memory, using its exact `memory_id`.
  Compare the memory's text with `full_work_candidates`. Stored memory
  `evidence_ids` may be empty: that is missing stored linkage, not a judgment
  that its text lacks canonical support.
- Mark `grounded_prior_knowledge` when candidate passages locate an event the
  memory shows the reader knows and the knowledge is consistent with the
  current report. Cite those exact candidate IDs in the assessment and explain
  the match. The remembered event may be earlier than the current stopping scene.
- Mark `not_supported` when the memory supplies no such knowledge, explaining
  why. Mark `conflicting` when its claimed progress conflicts with the current
  report or canonical evidence; explain the conflict. Do not mark an earlier
  remembered event conflicting merely because the reader now reports a later one.
- For a candidate, `supporting_memory_ids` must match grounded assessments and
  `supporting_evidence` must include their canonical anchors alongside the
  current event. Grounded assessments require `memory_supported`; without them
  use `line_only`, which grants nothing. Conflicting assessments require
  `uncertain`. Even with grounded prior knowledge, an unresolved current event
  remains `uncertain`; do not manufacture a stopping point.
- Assess supplied memories before choosing an authorization basis. Locate any
  earlier event they demonstrate the reader knows, then independently locate
  the event the reader now reports reading in `current_line`.
- Use candidate passages only to locate those separate knowledge signals.
  Recognizing the current scene from the Line alone does not erase an earlier
  memory's independently grounded support.
- Return `candidate` only when those signals map coherently to one latest
  chapter. A specific current reading report can extend remembered knowledge
  within the same chapter or into a later chapter; the memory need not describe
  the current stopping scene.
- Declare `authorization_basis=memory_supported` when supplied memories genuinely
  demonstrate knowledge of an event in this work and the current reading report
  coherently locates the same or a later event. Cite the exact input memory IDs.
  The memory need not describe the later event: the earlier remembered encounter
  and a specific current report of reading further are separate knowledge signals.
  Both must be located by supplied passages. Choose `authorization_basis=line_only`
  only after checking the supplied memories and finding no grounded earlier
  knowledge that supports the current reading report. Do not choose it merely
  because the Line was sufficient to identify the current scene.
  Memory presence alone is not support: unrelated, ungrounded, hypothetical,
  second-hand, or contradicted memory content cannot authorize progress.
- A reader message may locate an event without proving reading progress. Do not
  relabel a curiosity question, adaptation reference, quotation, or second-hand
  mention as memory-supported knowledge.
- Prior reader statements are a separate source for `passages`, not memories
  and not a shortcut to a chapter ceiling. Never cite statement IDs as memory IDs.
- The candidate chapter must equal the latest chapter among the supporting
  evidence IDs you select.
- Select only memory and evidence IDs present in the input and only records that
  genuinely locate something the corresponding signal indicates the reader
  knows.
- When combining remembered knowledge with a current report of reading further,
  cite evidence locating both the remembered event and the current event in
  `supporting_evidence`, even if both events are in the same chapter. A
  passage locating only the memory does not establish the current stopping point.
  If the current event cannot be distinguished, return `uncertain`; do not use
  the memory's chapter as a substitute for resolving `current_line`. Shared
  themes or repeated events do not identify a stopping point. A current
  correction that the reader has not reached an event defeats older memory
  support; do not use the memory to override that correction.
- Use `conflicting_context` when credible signals point to incompatible reading
  positions, `insufficient_context` when no event can be located, and
  `low_confidence` when a possible location remains ambiguous.
- Confidence measures certainty about the ceiling, not passage relevance.
