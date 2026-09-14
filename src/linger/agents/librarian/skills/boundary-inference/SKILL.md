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

Memory-supported chapter inference:
- Use `current_line` and memories as separate knowledge signals.
- Use candidate passages only to locate those signals inside the work.
- Return `candidate` only when the signals map coherently to one latest chapter.
- Declare `authorization_basis=memory_supported` only when one or more supplied
  memories genuinely demonstrate knowledge of the selected event, and cite
  their exact input memory IDs. Otherwise declare `authorization_basis=line_only`.
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
  `supporting_evidence_ids`, even if both events are in the same chapter. A
  passage locating only the memory does not establish the current stopping point.
  If the current event cannot be distinguished, return `uncertain`; do not use
  the memory's chapter as a substitute for resolving `current_line`.
- Use `conflicting_context` when credible signals point to incompatible reading
  positions, `insufficient_context` when no event can be located, and
  `low_confidence` when a possible location remains ambiguous.
- Confidence measures certainty about the ceiling, not passage relevance.
