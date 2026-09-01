---
name: reflect
description: Review the active Codex task for durable lessons, separate one-offs from patterns, and propose concrete skill or structural improvements. Use only when the user says reflect or explicitly asks to capture this task's lessons.
metadata:
  short-description: turn a Codex task's lessons into proposed improvements
---

# Reflect

Mine the current Codex task for durable lessons. Reflection does not grant permission to edit memory, trackers, global configuration, or unrelated skills.

## Process

1. Use the active task context. If more history is needed and Codex task tools are available, read only this task. Do not search unrelated task histories.
2. When collaboration is available, spawn up to three read-only reviewers with distinct lenses: judgment, tooling, and divergent alternatives. Omit model overrides by default. Give each the same task evidence and forbid writes.
3. Synthesize findings into **Accepted**, **Rejected**, and **Backlog**. A durable lesson must recur or explain a concrete failure. Move any rule that belongs in code, a lint, metadata, or a script to Backlog rather than adding more prose.
4. Present the full proposal and wait for explicit approval before changing a skill. Reflection itself is analysis.
5. For approved skill edits, use **skill-creator**. Keep project skill changes under `.agents/skills/` unless the user explicitly requests global scope. Run the Codex validator and a forward test when required.
6. Update Codex memory only when the user explicitly asks for a memory update. File tracker work only when the user or repository workflow authorizes it.

## Output

- Accepted lessons with evidence and proposed destinations.
- Rejected findings with a short reason.
- Backlog mechanisms that would enforce the lesson more reliably than prose.
- After approval, changed paths and validation results.

Optional role overrides live in `.agents/pstack-models.md`. Every reviewer inherits the parent model by default.
