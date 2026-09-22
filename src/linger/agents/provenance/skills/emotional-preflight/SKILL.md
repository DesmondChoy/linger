---
name: emotional-preflight
description: Classify whether a reader message requires the emotional-content boundary before drafting a reply.
---

Classify `current_line` using the supplied `policy` before a reply is drafted.
Decide whether the application should use one of its fixed responses instead
of continuing reflective conversation. This is product-policy classification,
not diagnosis, crisis assessment, or resource routing.

Return `apply_self_harm_boundary` only for a clear, current, first-person
disclosure that the reader wants to kill themselves, end their life, harm
themselves, or has suicidal thoughts or intent. Return `apply_boundary` for
any other clear, current, first-person disclosure of intense distress or
inability to cope where reflective questioning would be inappropriate. Return
`continue_reflection` for ordinary disappointment, frustration, uncertainty,
literary or hypothetical content, quotations, and concern about another
person — including literary or hypothetical discussion of a character's
self-harm or suicide, which is not a reader disclosure.

Policy fields ending in `after_distress` describe the consequences of applying
a boundary. Their true values are not evidence that distress is present.

Do not diagnose or label mental state. Do not assess severity, intent, plans, or
immediacy. Do not ask questions, suggest resources, quote `current_line`, or add a
rationale. Return only the typed decision.
