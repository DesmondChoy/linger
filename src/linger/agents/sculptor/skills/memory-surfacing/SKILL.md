---
name: memory-surfacing
description: Propose a grounded suggestion now, defer it, or remain silent in offline evaluation.
---

Decide whether the supplied memories justify one useful suggestion now, a
deferred suggestion, or silence. This is an offline decision, without a fresh
user request. This task does not propose curation actions.

The JSON input contains `memories` with `memory_id` and `text`, plus `context`:
`context.now` supplies the current time, `context.current_context` describes
the situation, and `context.history` records prior suggestions and feedback.
Use only this input; do not infer omitted personal context or use the actual
wall clock.

Use `surface_now` only for a specific, useful, timely suggestion grounded in the
supplied memories and situation. Put the suggestion in `suggestion`, explain
its present usefulness in `rationale`, and cite its `source_memory_ids`.
A shared word, broad topic, or vague association is not enough. Do not invent
events, preferences, commitments, or personal facts.

Use `defer` when a grounded opportunity could become useful at a later time or
when a concrete condition changes. Give a future timezone-aware time or a
specific observable condition for reconsideration. Deferring does not schedule
anything. Do not defer a cancelled, completed, superseded, or unsupported
opportunity merely to avoid silence.

Use `do_not_surface` when the evidence is irrelevant, insufficient, superseded,
repetitive, or would require a sensitive inference. Silence is a successful
outcome when there is no useful grounded opportunity. Empty memories warrant
`insufficient_evidence`, not an invented suggestion. A cancellation or correction
can defeat an otherwise plausible suggestion; respect what is true now and
preserve uncertainty when the available records do not resolve it.

Account for prior suggestions and feedback. Do not repeat a surfaced suggestion
without a material change that makes it useful again. Respect dismissals and
active suppression periods; expiry alone does not establish renewed usefulness.
Do not infer a diagnosis, mental-health state, or other sensitive attribute from
memories. Use `sensitive_inference` when an opportunity depends on such inference.

For `do_not_surface`, provide a supported `reason` and `rationale`; cite the
memories informing that decision in `source_memory_ids` when available. The
source list may be empty.

Never claim that a suggestion was delivered, a reminder was scheduled, or any
record was changed.
