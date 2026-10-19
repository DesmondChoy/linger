---
name: sharpen
description: "Sharpen a task before starting: the expert approach, what the user is really after, and the right level of specification. Use for /sharpen."
---

# Sharpen

**Runtime and authority.** Follow [`runtime-adaptation.md`](../poteto-mode/references/runtime-adaptation.md) for Codex and Claude Code tools, available models, shared-checkout delegation, and project-local paths. Preserve the user's scope and explicit checkpoints. This skill does not authorize commits, pushes, pull requests, remote changes, or unrelated work.

Before starting, ask how a top expert would approach this task (their raw sources, their real methods, an outside check that the result is right), what the user is really after, and whether the task is over- or underspecified. Question assumptions and constraints you introduced yourself. Preserve explicit user constraints; surface a conflicting constraint as a material choice rather than silently relaxing it. Leave choices that belong to the user open until their answer is needed. Fold in only what makes the work better, not bigger, and choose an independent check appropriate to the task, without narrating the framing, then do the work. Don't hand back a rewritten prompt.
