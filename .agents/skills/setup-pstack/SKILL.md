---
name: setup-pstack
description: Configure optional project-local Codex model overrides for pstack roles. Use for setup-pstack, configure pstack models, or changing pstack's model choices in this repository.
metadata:
  short-description: configure project-local pstack model choices
---

# Set up pstack for Codex

Configure optional role-to-model overrides in `.agents/pstack-models.md`. Keep setup project-local. Do not edit `~/.codex`, a global `AGENTS.md`, or global skills unless the user explicitly asks for global configuration.

## Default behavior

Pstack works without this file. Every collaboration role inherits the parent Codex model when no override exists. Inheritance is the recommended default because model availability varies by host and task.

## Steps

1. Inspect the models and reasoning efforts exposed by the current collaboration tool. Do not infer availability from an old config file.
2. Read `.agents/pstack-models.md` if it exists. Treat only its listed roles as overrides.
3. Ask the user only when they invoked this skill to make a model choice and the requested mapping is not already clear. Offer only currently available values plus `inherit-parent`.
4. Write the complete project-local file with `apply_patch`. Use `inherit-parent` for unspecified roles. Keep panel sizes within Codex's current limit of three child agents.
5. Re-read the file and verify that every non-inherited model and reasoning effort is supported by the current collaboration tool.

Use this shape:

```markdown
# pstack model configuration

Project-local optional overrides. Delete a line or use `inherit-parent` to omit the model override.

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
