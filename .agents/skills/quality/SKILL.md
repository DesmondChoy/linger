---
name: quality
description: Review scoped code changes with fresh eyes and fix verified issues when edits are authorized. Use before commits or for requested quality reviews.
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git show:*), Read, Edit, Glob, Grep
---

Review the changes covered by the current request with fresh eyes. Find correctness and integration issues while preserving unrelated work and any request for a report-only review.

## Process

### 1. Establish the scope

Use the user's named files, hunks, commit, or branch diff when supplied. Otherwise, review the current task's changes. Before a commit, review the changes intended for that commit.

Inspect the checkout to locate those changes:

```bash
git status --short
```

Choose the relevant working-tree, staged, or committed diff for that scope, and inspect any in-scope untracked files separately. Git status is an inventory, not authorization to review or fix every dirty file. When a file contains both task changes and unrelated edits, keep the review and fixes focused on the intended hunks and their effects.

Resolve scope from the request and available evidence. Ask only if the intended changes cannot be distinguished and that ambiguity materially affects the review.

### 2. Read the relevant context

Read the scoped diff, surrounding definitions, relevant callers, contracts, tests, and configuration. Read complete files when needed to understand behavior or ownership. Expand inspection when a finding or unresolved uncertainty requires more context; do not read every changed file in full by default.

Reading a related file for context does not add it to the authorized edit scope.

### 3. Review correctness and integration

Check the concerns relevant to the change:

- Does the logic match the intended behavior, including reachable edge cases and error paths?
- Are types, function signatures, and API contracts consistent across callers and consumers?
- Do state updates and side effects preserve the required invariants?
- Did the change introduce dead code, unintended debug output, or misleading comments?
- Do the available tests or other checks cover the behavior that changed?

### 4. Act within the requested mode

When fixes are authorized, correct verified issues within scope and preserve unrelated edits. Make routine implementation decisions from the evidence without another approval step.

For a report-only or read-only request, report findings without editing or staging files. Report issues outside the authorized scope separately. Ask only when a material decision remains unresolved or the next action needs new authority.

### 5. Verify any fixes

Run the checks appropriate to the changes made and inspect the resulting diff for unintended edits. Expand validation only when failures, integration risk, or new changes justify it. State which checks passed, failed, or could not run.

### 6. Report the result

Summarize the reviewed scope, verified findings, fixes made, validation evidence, and any unresolved issues or limits. Distinguish findings from assumptions and distinguish completed fixes from proposed work.

## When to run

- Before a commit, on the changes intended for that commit.
- When requested with `/quality`, in the requested review or repair mode.
- After significant implementation work, on that task's changes.
