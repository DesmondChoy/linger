---
name: chapter-cues
description: Revise every chapter's reading aids so book search finds the chapter a reader means.
---

Revise the reading aids for every chapter of one book. Search reads each
chapter's `routing_description`, `characters`, and `retrieval_cues` beside
every passage of that chapter, so good aids help it choose the right chapter
when a reader describes a scene in their own words. This task does not curate
memories, and it never changes book text, quotations, or citations.

The JSON input contains `chapters`, each with its `chapter_number`, `title`,
full `text`, and current `cues`, plus `word_budget` and `rounds`. Each round
records practice questions, the chapter that answers each one
(`target_chapter`), whether search reached the answering passage (`reached`),
and the chapters search returned instead (`chapters_returned`, best first).
The last round used the current cues. A later round may include the
`failure_patterns` you named when you wrote its cues.

First, name the patterns behind the remaining failures in `failure_patterns`.
A pattern is general, such as readers naming a character differently from the
book, a memorable event missing from its chapter's aids, or one chapter's aids
describing another chapter's event. When an earlier round's patterns persist,
say which and why. A miss where the target chapter was returned but the
passage was not cannot be fixed by chapter aids; say so instead of distorting
the aids.

Then return aids for every chapter, including chapters no practice question
asks about. Start from each chapter's current aids: keep every accurate
character and cue, and remove or replace only what is wrong, misleading, or
belongs to another chapter. Then add what is missing. Shorter aids give search
less to match, so aim for about three quarters of `word_budget` for every
chapter and never exceed it. Apply every fix
your failure patterns call for in the aids themselves; naming a pattern
changes nothing. For each chapter:

- Describe its memorable scenes, actions, objects, and outcomes the way a
  reader might recall them, in plain words rather than only the book's
  phrasing.
- List the characters who appear in it. A widely used alternate name for one
  of those characters is allowed.
- Make the aids distinctive: prefer what sets this chapter apart from its
  neighbors over themes that recur across the book.
- State only what this chapter's text supports. Never describe an event from
  another chapter, and never mention what happens later in the book.
- Keep what already works. A question that was reached must stay reachable.
- Stay within `word_budget` words, counted across the description, every
  character, and every cue.

The practice questions are a small sample of what readers ask. Fix the
pattern, not the sample: do not copy question wording into the aids, and do
not overload a chapter only because a practice question targets it.
