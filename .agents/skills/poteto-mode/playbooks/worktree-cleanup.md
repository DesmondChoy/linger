### Worktree and simulator cleanup

This playbook is disabled for ordinary Linger work. The repository forbids worktrees unless the user explicitly requests them, and cleanup deletes local state.

Use this playbook only when the user explicitly asks to inspect or remove exact worktrees, simulators, or caches. First inventory targets with read-only commands. Show any uncommitted or untracked files and identify active Codex tasks that may use each target. Ask before any deletion that could discard work or remove a user-owned environment.

Do not run `scripts/worktree-audit.sh` in Linger. It assumes Claude transcript storage and is not a valid Codex authority check. Resolve Codex task state with the app's task-list and task-read tools when available.

After explicit approval, use exact validated paths and non-interactive commands. Never target a home directory, repository root, workspace root, unresolved variable, or broad glob. Report what was removed and whether it can be recovered.

**Reply:** the inspected targets, held-back items and reasons, exact removals, and measured space reclaimed when applicable.
