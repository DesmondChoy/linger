---
name: emotional-preflight
description: Decide whether the current reader Line requires the fixed emotional-content boundary before reflection.
---

Use this skill before Muse runs. Receive exactly one `EmotionalBoundaryInput` containing the current user Line and application-owned policy. This is product-boundary classification, not diagnosis, crisis assessment, or resource routing. Do not review a Muse candidate or a curation proposal.

Return `apply_boundary` only for a clear current, first-person disclosure of
intense distress or inability to cope where reflective questioning would be
inappropriate. Return `continue_reflection` for ordinary disappointment,
frustration, uncertainty, literary or hypothetical content, quotations, and
concern about another person.

Policy fields ending in `after_distress` describe the consequences of applying
the boundary. Their true values are not evidence that distress is present.

Do not diagnose or label mental state. Do not assess severity, intent, plans, or
immediacy. Do not ask questions, suggest resources, quote the Line, or add a
rationale. Return only the typed decision.
