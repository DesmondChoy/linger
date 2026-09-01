---
name: recall
description: "Reconstruct recent project context from Codex task history, live repository state, Beads, and available shared records. Use for recall my work on X, catch me up, what have I been working on, or where did I leave off."
metadata:
  short-description: catch up from Codex tasks and current project state
---

# Recall

Rebuild the user's recent working context and return a tight current-state brief. History is evidence about what happened. The current repository, pull requests, and Beads are the authority for what is true now.

1. Lock the scope. Default to this project and the last seven days. Preserve an explicit window such as "all" or "since June". Never read another project's tasks unless asked.
2. Use Codex app tools such as `list_threads` and `read_thread` to find relevant tasks. Skip the current task and unrelated summaries. For a small result set, read directly. When the active skill and runtime allow delegation, split a larger result set across at most three read-only collaboration agents.
3. If task-history tools are unavailable, use the current conversation and repository evidence. State the missing history source rather than scanning guessed transcript paths.
4. For a named feature, file, subsystem, or bug, inspect the shared record through the **why** skill. Use only available connectors. A missing connector is a reported gap, not an invitation to invent one.
5. Verify surfaced branches, commits, pull requests, and issues against live `git`, `gh`, and Beads state. Do not treat an old task summary as current truth.
6. Keep private task details scoped to this response. Sanitize them before any public output.

## Output

- **Capsule.** At most five bullets covering the work and current state.
- **Threads.** One line each with a concrete status such as merged, open PR, in flight, verified but uncommitted, reverted, or planned.
- **Problems.** At most five recurring blockers or failed approaches.
- **Next move.** The single most useful concrete action.

Cite Codex tasks by their task title and ID when available. Cite shared records by commit, PR, Bead, issue, document, or permalink.

**Reply:** the brief only.
