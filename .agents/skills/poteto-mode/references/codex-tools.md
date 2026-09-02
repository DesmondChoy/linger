# Codex adaptation for pstack

This project vendors pstack's skill instructions. When an upstream instruction names a Claude Code tool, model, path, or workflow, apply the mappings and limits in this file. Repository `AGENTS.md`, developer instructions, and the user's current request always take precedence.

## Authority and scope

- A skill selects a method. It does not grant permission to broaden the task or mutate external state.
- Do not commit, push, open or merge a pull request, rewrite history, update an issue, deploy, send a message, or change a remote service unless the user or repository policy authorizes that action for the current task.
- Respect read-only requests literally. A review, explanation, diagnosis, or status request does not authorize repairs.
- Use Beads for durable project tracking when `AGENTS.md` requires it. Otherwise use Codex's plan tool only when a plan helps.
- Treat instructions to open a PR at the end of an upstream playbook as conditional on explicit authorization. Without it, stop after verification and report the proposed git commands.

## Tool mapping

| Upstream action | Codex action |
|-----------------|--------------|
| Read files | Use the filesystem tools or `exec_command`. Prefer `rg` and `rg --files` for discovery. |
| Create or edit files | Use `apply_patch`. Formatting and other bulk mechanical rewrites may use the relevant command. |
| Run a command | Use `exec_command`. Use non-interactive flags. |
| Search the web | Use the web tool when current or external evidence is required. |
| Invoke `/name` or the `Skill` tool | Load and follow the project skill named `name`. |
| Spawn an `Agent` or `Task` | Use `spawn_agent` when delegation is allowed. |
| Wait for agents | Use `wait_agent`. Use `interrupt_agent` only to stop active work. There is no `close_agent`. |
| Use a todolist | Use Beads when required by the repository. Otherwise use `update_plan` for nontrivial work. |
| Ask a fixed-choice question | Use `request_user_input` when available. Otherwise ask one concise plain-text question. |

## Collaboration policy

Codex collaboration agents share the current checkout and filesystem. This repository forbids git worktrees unless the user explicitly requests one.

- The current runtime has four collaboration slots, including the main agent. At most three child agents can run at once.
- Use subagents only when the user, repository instructions, or the active skill explicitly calls for delegation.
- Give concurrent writers disjoint paths. Keep one main-thread writer when edits overlap. Serialize work that shares a file or mutable state.
- Give each agent a bounded task and the file paths it needs. The main agent continues useful local work, inspects artifacts and diffs, and owns the final judgment.
- Replace `subagent_type` and `readonly` fields with a plain-language brief. State whether the task is read-only and name its write scope.
- To emulate `poteto-agent`, tell the child to read the project-local `poteto-mode` skill before acting. To emulate `comment-sicko`, tell it to read `no-comments/references/comment-sicko.md`.
- A request for dozens or hundreds of workers is outside this runtime's capacity. Partition the work into waves of at most three children.

## Models

Omit the `model` override by default so a child inherits the parent model. Independent lenses and prompts provide useful diversity even when only one model is available.

If the user configures role overrides with `setup-pstack`, read `.agents/pstack-models.md`. Use only model names and reasoning efforts that the current collaboration tool exposes. A missing or invalid override falls back to inheritance and is reported; it never triggers an unrelated PR.

Claude model names in upstream `Models` sections are provenance, not valid Codex defaults.

## Skills and product features

| Upstream name | Codex equivalent |
|---------------|------------------|
| `run` | Run the CLI or TUI and inspect its real output. |
| `verify` | Use the relevant browser, computer-use, test, or runtime tool and inspect the real artifact. |
| `plugin-dev:skill-development` | Use the project-available `$skill-creator` skill. |
| `loop` | Use a Codex heartbeat automation for recurring follow-up, or the applicable task or collaboration wait tool. Do not block with long sleeps. |

Project skills live under `.agents/skills/`. Global skill or configuration writes are out of scope unless the user explicitly requests global installation.

For task history, prefer Codex task tools such as `list_threads` and `read_thread`, plus the current task context. Do not assume Claude transcript paths exist. For shared project state, inspect the current repository, GitHub, Beads, and only the connectors available in the current session.

## Advanced upstream playbooks

The Graphite, stack-shipping, orchestrate, autopilot, worktree, and simulator-cleanup playbooks are retained as upstream reference material. In this repository they are unavailable by default because they assume tools, topology, or destructive authority that Linger does not grant.

Use one only when the user explicitly requests that workflow and authorizes its prerequisites. Apply the no-worktree rule, current collaboration limit, and authority rules above. If the workflow cannot be adapted without changing its meaning, explain the mismatch and use the narrowest safe playbook instead.

`poteto-mode/scripts/worktree-audit.sh` reads Claude-specific transcript paths and must not run in Linger. The `watch-pr` and `orch` scripts may run only when their owning workflow is authorized and their dependencies are present.

## Instructions file

The project instructions file is `AGENTS.md`. Global Codex instructions, when explicitly in scope, live under `~/.codex/`. Never substitute `CLAUDE.md` or write global configuration as part of a project-local setup.
