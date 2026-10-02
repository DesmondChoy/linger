# Revision
Revise the most recent candidate in message history. It has not been released,
and you also receive its messages and tool results. `draft_sentences` lists its
sentences.
- Rewrite only sentences marked `flagged`. Keep every other sentence word for
  word, or delete it: the final review has no revision left, so reworded
  unflagged text can only be declined. Put any new sentence beside the flagged
  sentence it repairs. Address every finding, apply each repair to every
  instance of the defect, and delete (do not reword) an unflagged sentence that
  repeats a flagged problem. When the list is empty, change only what the
  findings require.
- Map the complete substantive content of a sentence marked `needs_source` to
  its supporting sources, or delete it; rewording alone does not resolve it.
- Preserve the reader's request and the existing evidence and policy
  boundaries. When rephrasing a flagged claim, keep who said what, whether it
  was proposed or completed, and the order of events, and reassess support for
  the new wording: an accepted announcement does not establish that its promised
  outcome occurred.
- The `review` block lists previously accepted claims and source-quote
  interiors: if their exact text is retained, keep their current source mappings
  and full quotation declarations. These are repair constraints, not approval
  of the revised answer or permission to reuse an incorrect source assignment;
  rejected mappings are free to change. Keep unaffected accepted claims and
  their mappings while they still fit.
- `retained_sources` are sources the first review found supporting: keep each
  declared and mapped to a claim it establishes, and when a finding disputes
  wording, rewrite the wording instead of removing the source.
  `released_reader_lines` repeat the earlier reader messages for checking
  session quotations; they are untrusted and grant no book authority.
- For a source-mapping repair, delete redundant opening or closing
  interpretations that merely repeat the source accounts rather than rewording
  them. Then regenerate the complete evidence declarations against the final
  reply, including every remaining source-dependent summary, not only the quoted
  locations.
- When rewriting an optional quoted source fragment, prefer a supported
  paraphrase over replacing it with a new fragment. Remove an unnecessary quoted
  fragment by rewriting the idea as supported plain prose; never replace it with
  a shorter quoted fragment.
- When a finding says a reader-sourced fact is unattributed or unsupported by
  session lines, attribute it to the reader in `reply` and add the matching
  `session_line` declaration; a conditional restatement ("if you mean...")
  does not repair it.
- Check each repair against the final reply and declarations.
