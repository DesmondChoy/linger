---
name: evidence-assessment
description: Select supplied spoiler-safe evidence and assess whether it supports a book-specific answer.
---

The input JSON contains a reader query and exact, spoiler-safe canonical book
passages that have already passed retrieval. Judge the supplied set without
inferring or widening the reader's spoiler boundary.

Select the smallest evidence set that supports the requested book-specific
answer, then judge that selected set. Do not use retrieval scores as proof of
answerability and do not add outside knowledge.

For a quotation request, select a passage containing the requested wording and
any narrator description the reader asks to include. Do not add neighboring
passages merely because they concern the same scene or theme. Add another
passage only when it supplies distinct support needed for another part of the
requested book answer. A personal reflection alongside the quotation does not
by itself require more book passages. Keep multiple passages when the requested
answer needs them; do not force a single record for a comparison or a quotation
that spans records.

- sufficient: the cited passages directly support a useful answer to the query.
- weak: one or more cited passages are relevant but only partially support the
  requested explanation, relationship, motive, or fact. State the limitation.
- none: none of the passages usefully supports an answer, even if words overlap.

Return only evidence IDs present in the input. Keep weak evidence instead of
discarding it. For none, return no evidence IDs. Give a concise, concrete reason.
This task receives no conversation history.
