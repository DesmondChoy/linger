---
name: no-comments
description: "Spawn the comment-sicko subagent, fix accepted findings, and offer encodings for claimed constraints."
metadata:
  short-description: strip comments before review, fix the accepted findings, encode claimed constraints
---

# No comments

Spawn a read-only collaboration agent and tell it to read [`references/comment-sicko.md`](references/comment-sicko.md) before reviewing the scoped diff. Act on accepted findings only when the user's request authorizes edits.

Use the reviewer's fresh perspective to find overlooked issues; accept only findings grounded in current code and the authorized scope.

**Platform note.** On Codex or another non-Claude runtime, the `comment-sicko` subagent and the Claude tool names below are Claude defaults. Resolve them via [`codex-tools.md`](../poteto-mode/references/codex-tools.md).

## Scope

Use the caller's files or diff. Otherwise use the current task's changes, following **quality** scope rules. Preserve unrelated work and explicit user constraints.

## Steps

1. Spawn one collaboration agent with the scope and the instruction to read `references/comment-sicko.md` in full. Give it no write scope. Do not restate its rules.
2. Inspect the report against current code and evidence. Reject scope escapes, unsupported findings, and deletions that would violate explicit user instructions or valid constraints. Preserve ambiguous constraint comments until their meaning or replacement is established in step 5. Use **how** or **why** when source inspection leaves a concrete evidence gap; do not accept a deletion solely because the reviewer prefers it.
3. Fix clear accepted findings directly within scope. If an accepted fix has an unresolved structural choice, use **architect**; otherwise implement the clear fix without a separate design phase.
4. Implement the smallest root-cause fix in scope. Remove every named workaround. If the root cause is out of scope, land the smallest in-scope fix and report the rest open. The **principle-fix-root-causes** and **principle-redesign-from-first-principles** skills guide intent only: fix real causes, redesign as if requirements always existed, never bolt on symptom guards. Neither authorizes widening the fence nor fixing instances outside it.
5. Constraint comments say `do not remove`, `do not change wording`, or `talk to X before changing`. Preserve valid constraints, including those outside our control. When existing authorization covers enforcing an understood constraint, implement and verify the cheapest adequate in-scope enforcement before removing a redundant comment. If enforcement needs a material decision or missing authority, prepare the concrete proposal and ask only about that gap. Preserve the comment while its meaning or replacement remains unresolved; report remaining work.
6. Report the deletion count, restored comments, reruns, architect sketch, fixes, encoding offers, encodings, unenforced constraints, and other open work.
