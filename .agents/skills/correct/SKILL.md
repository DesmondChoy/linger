---
name: correct
description: "Find recurring agent mistakes in this repo and prevent them through architecture, types, lint, or behavioral tests. Use for /correct or an explicit request to prevent a repeated mistake."
---

# Correct

**Runtime and authority.** Follow [`runtime-adaptation.md`](../poteto-mode/references/runtime-adaptation.md) for Codex and Claude Code tools, available models, shared-checkout delegation, and project-local paths. Preserve the user's scope and explicit checkpoints. This skill does not authorize commits, pushes, pull requests, remote changes, or unrelated work.

Change the repository so the next contributor cannot repeat an evidenced mistake. Assume an agent may see only the files it opened, copy the nearest example, and take the shortest path that compiles. Make a locally reasonable edit correct for the whole repository.

## Find the mistake classes

Use the correction and scope the user named. Within that scope, inspect relevant commits, reverts, review comments, instruction files, and documented workarounds. Group repeated mistakes into classes and cite at least two occurrences before calling one recurring. A new correction does not automatically invoke this skill or authorize a repository sweep. If only one occurrence is evidenced, address the concrete defect within scope and distinguish a proposed general rule from a demonstrated pattern.

## Prevent each class at the highest useful level

1. **Architecture.** Give each piece of state one owner and each task one supported path. Hide internals where the language or build can enforce the boundary. Replace hand-synced lists with one source of truth. Migrate callers and remove obsolete paths within the authorized change.
2. **Types and lint.** Make invalid states unrepresentable when practical. If the bad code still compiles, consider a focused lint or CI check whose error names the intended file, type, or function. An existing widespread pattern may need a check that prevents new instances while its migration is planned.
3. **Behavioral tests.** Assert what the caller or user can observe. Verify that the test catches the wrong behavior and survives an internal refactor. Preserve valid coverage when replacing weak tests.
4. **Instructions.** Reserve prose for decisions requiring judgment. Prefer an enforceable rule when one can establish the requirement with less ongoing effort.

## Fix and prove

Fix the relevant recurring class in coherent units. Prove each new check detects a real past mistake using an isolated reproduction or temporary mutation, then run the existing focused checks. Reuse the same validation command locally and in CI when CI changes are in scope. Preserve existing work and restore temporary mutations. A commit per class is an option only when commits are authorized.

Where an instruction file already documents a rule, record its enforcing mechanism when that helps future contributors. Remove redundant prose only after the replacement preserves its meaning. Do not add a universal rule table or exception-approval process unless the project needs one. Report a missing decision or authority before changing policy.

**Reply:** Give each class, its evidence, the mechanism chosen, the proof, and why a stronger mechanism was unnecessary or unavailable. Report out-of-scope follow-ups separately.
