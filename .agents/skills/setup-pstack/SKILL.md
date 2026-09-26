---
name: setup-pstack
description: Configure optional project-local model overrides for pstack roles on Codex and Claude Code. Use for setup-pstack, configure pstack models, or changing pstack's model choices in this repository.
metadata:
  short-description: configure project-local pstack model choices
---

# Set up pstack

Configure optional role-to-model overrides in `.agents/pstack-models.md`. The file has one section per runtime, because Codex and Claude Code expose different model names. Each runtime reads only its own section. Keep setup project-local. Do not edit `~/.codex`, `~/.claude`, a global `AGENTS.md`, or global skills unless the user explicitly asks for global configuration.

## Default behavior

Pstack works without this file. Every subagent role inherits the parent model when no override exists for the current runtime. Inheritance is the recommended default because model availability varies by host and task.

## Steps

1. Inspect the models and reasoning efforts exposed by the current runtime's subagent tool (`spawn_agent` on Codex; the `Agent` tool's `model` aliases on Claude Code). Do not infer availability from an old config file.
2. Read `.agents/pstack-models.md` if it exists. Treat only the listed roles in the current runtime's section as overrides. Preserve the other runtime's section unchanged.
3. Ask the user only when they invoked this skill to make a model choice and the requested mapping is not already clear. Offer only currently available values plus `inherit-parent`.
4. Write the complete project-local file with the runtime's edit tool. Use `inherit-parent` for unspecified roles. On Codex, keep panel sizes within the limit of three child agents.
5. Re-read the file and verify that every non-inherited model and reasoning effort is supported by the current runtime's subagent tool. You cannot validate the other runtime's section from here; leave it as found.

Use this shape:

```markdown
# pstack model configuration

Project-local optional overrides. Delete a line or use `inherit-parent` to omit the model override. Each runtime reads only its own section.

## Codex

feature, refactoring: inherit-parent
bug-fix: inherit-parent
perf-issue: inherit-parent
hillclimb: inherit-parent
judgment and prose: inherit-parent
strongest judgment: inherit-parent
how explorer: inherit-parent
how explainer: inherit-parent
how critics: inherit-parent, inherit-parent, inherit-parent
why investigators: inherit-parent
why synthesizer: inherit-parent
reflect tooling: inherit-parent
reflect judgment, divergent, synthesizer: inherit-parent
arena runners: inherit-parent, inherit-parent, inherit-parent
arena cross-judge pool: inherit-parent
swarm workers: inherit-parent
architect runners: inherit-parent, inherit-parent, inherit-parent
interrogate reviewers: inherit-parent, inherit-parent, inherit-parent

## Claude Code

feature, refactoring: inherit-parent
bug-fix: inherit-parent
perf-issue: inherit-parent
hillclimb: inherit-parent
judgment and prose: inherit-parent
strongest judgment: inherit-parent
how explorer: inherit-parent
how explainer: inherit-parent
how critics: inherit-parent, inherit-parent, inherit-parent
why investigators: inherit-parent
why synthesizer: inherit-parent
reflect tooling: inherit-parent
reflect judgment, divergent, synthesizer: inherit-parent
arena runners: inherit-parent, inherit-parent, inherit-parent
arena cross-judge pool: inherit-parent
swarm workers: inherit-parent
architect runners: inherit-parent, inherit-parent, inherit-parent
interrogate reviewers: inherit-parent, inherit-parent, inherit-parent
```

The same model may appear more than once when independent prompts or lenses still provide value. Do not claim model diversity when every entry inherits the same parent.

**Reply:** the project-local path, changed role mappings, and validation result.
