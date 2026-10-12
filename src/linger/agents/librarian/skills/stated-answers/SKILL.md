---
name: stated-answers
description: List every distinct answer the selected records state, each with a verbatim quote.
---

# Stated answers

The application has already selected the book records that answer the reader's
book question, and a writer will draft the reply from them. List every separate
answer those records state, so that the writer drops none of them. A passage
often gives more than one reason, step, or named thing, and the later ones are
the ones that get lost.

Read each supplied record from its first line to its last. Return one item for
each distinct answer the records state to `book_question`:

- `answer`: the answer in one short plain clause.
- `evidence_id`: the supplied record that states it.
- `source_quote`: a short contiguous quote copied from that record's text,
  containing the words that state this answer. Only whitespace may differ.

An item must be something the text states. Do not infer a motive, cause, or
conclusion that the words do not give, and use nothing you know about the book
beyond the supplied records. The quote must state the answer itself, not merely
mention the same subject.

An answer given in dialogue counts, including one given as a retort or drawn
out during an exchange between speakers.

Keep separate answers separate: two different reasons are two items, even when
one speaker or one sentence gives both. List each answer once, even when
several records state it. Do not pad: leave out background, restatements of the
question, and anything that does not answer it. If the records state one
answer, return one item; if they state none, return an empty list.
