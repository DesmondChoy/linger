---
name: memory-surfacing
description: Propose a grounded suggestion now, defer it, or remain silent in offline evaluation.
---

Decide whether the supplied memories justify one useful suggestion now, a
deferred suggestion, or silence. This is an offline decision, without a fresh
user request. This task does not propose curation actions.

The application supplies an explicit current time, current situation, prior
surfacing history, and a bounded set of memories. Use only this input. Do not
use the actual wall clock or assume access to any omitted personal context.

Use surface_now only for a specific, useful, timely suggestion grounded in the
supplied memories and situation. Explain what makes it useful now and cite the
memory IDs that support it. A shared word, broad topic, or vague association is
not enough. Do not invent events, preferences, commitments, or personal facts.

Use defer when a grounded opportunity could become useful at a later time or
when a concrete condition changes. Give a future timezone-aware time or a
specific observable condition for reconsideration. Deferring does not schedule
anything. Do not defer a cancelled, completed, superseded, or unsupported
opportunity merely to avoid silence.

Use do_not_surface when the evidence is irrelevant, insufficient, superseded,
repetitive, or would require a sensitive inference. Silence is a successful
outcome when there is no useful grounded opportunity. Empty memories warrant
insufficient_evidence, not an invented suggestion. A cancellation or correction
can defeat an otherwise plausible suggestion; respect what is true now and
preserve uncertainty when the available records do not resolve it.

Account for prior suggestions and feedback. Do not repeat a surfaced suggestion
without a material change that makes it useful again. Respect dismissals and
active suppression periods; expiry alone does not establish renewed usefulness.
Do not infer a diagnosis, mental-health state, or other sensitive attribute from
memories. Use sensitive_inference when an opportunity depends on such inference.

For silence, cite the memories informing the decision when available; the source
list may be empty. A typed proposal is not proof of semantic usefulness.

Never claim that a suggestion was delivered, a reminder was scheduled, or any
record was changed.
