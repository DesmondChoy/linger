# Runtime adaptation for pstack

This project vendors pstack's skill instructions and runs them on two runtimes: Codex and Claude Code. Both load the same files from `.agents/skills/` (Claude Code through the `.claude/skills` symlink). When a skill names a tool, model, path, or workflow, apply the shared rules below and then the section for the runtime you are running in. Repository `AGENTS.md`, developer instructions, and the user's current request always take precedence.

## Authority and scope

- A skill selects a method. Explicit user instructions take precedence over skill guidance, within system and developer constraints. A skill does not grant permission to broaden the task or mutate external state.
- Carry forward authorization already given for the same action and scope. Before requesting missing approval, finish authorized preparation and verification so the user can review a concrete result. Preserve explicit checkpoints and continue independent authorized work while awaiting an answer.
- Do not commit, push, open or merge a pull request, rewrite history, update an issue, deploy, send a message, or change a remote service unless the user or repository policy authorizes that action for the current task.
- Respect read-only requests literally. A review, explanation, diagnosis, or status request does not authorize repairs.
- Use Beads for durable project tracking when `AGENTS.md` requires it. Otherwise use the runtime's plan tool only when a plan helps.
- Treat instructions to open a PR at the end of an upstream playbook as conditional on explicit authorization. Without it, stop after verification and report the proposed git commands.

## Workflow and verification

Apply the proportional workflow in `AGENTS.md` to every upstream playbook. Fixed candidate counts, new harnesses, per-edit checks, and additional reviewers are methods to select when useful, not automatic gates. An explicitly requested experiment or comparison keeps its requested design and evidence requirements.

Run required checks and verify the changed contract with relevant evidence. Reuse existing checks, add coverage for meaningful gaps, and stop widening or repeating verification once it passes unless new changes, failures, or unresolved concerns justify more. Report baseline failures and unavailable checks accurately. Human Ground truth adoption and explicit user checkpoints remain required where they establish the requested evidence or authority.

## Collaboration policy

Collaboration agents on both runtimes share the current checkout and filesystem. This repository forbids git worktrees unless the user explicitly requests one.

- Respect the runtime's concurrency limit (see the runtime sections). Larger fan-outs run in waves.
- `AGENTS.md` encourages bounded, independent delegation when it improves speed or quality. Work directly when coordination adds more cost than value. Architecture tournaments are optional unless the user requests one or unresolved design uncertainty justifies it.
- Give concurrent writers disjoint paths. Keep one main-thread writer when edits overlap. Serialize work that shares a file or mutable state.
- Give each agent a bounded task and the file paths it needs. The main agent continues useful local work, inspects artifacts and diffs, and owns the final judgment.
- State in the brief whether the task is read-only and name its write scope.
- To emulate `poteto-agent`, tell the child to read the project-local `poteto-mode` skill before acting. To emulate `comment-sicko`, tell it to read `no-comments/references/comment-sicko.md`.

## Models

Omit the model override by default so a child inherits the parent model. Independent lenses and prompts provide useful diversity even when only one model is available.

If the user configures role overrides with `setup-pstack`, read the current runtime's section of `.agents/pstack-models.md`. Use only model names and reasoning efforts that the current runtime's subagent tool exposes. A missing or invalid override, falls back to inheritance and is reported; it never triggers an unrelated PR.

## Task history

Read only the current task and, when a skill needs history, tasks from this project. Never scan another project's history or guess paths. For shared project state, inspect the current repository, GitHub, Beads, and only the connectors available in the current session.

## Project files

Project skills live under `.agents/skills/`. The project instructions file is `AGENTS.md`; durable guidance goes there on both runtimes. Global skill or configuration writes are out of scope unless the user explicitly requests global installation.

## Advanced upstream playbooks

The Graphite, stack-shipping, orchestrate, autopilot, worktree, and simulator-cleanup playbooks are retained as upstream reference material. In this repository they are unavailable by default because they assume tools, topology, or destructive authority that Linger does not grant.

Use one only when the user explicitly requests that workflow and authorizes its prerequisites. Apply the no-worktree rule, the runtime's concurrency limit, and the authority rules above. If the workflow cannot be adapted without changing its meaning, explain the mismatch and use the narrowest safe playbook instead.

`poteto-mode/scripts/worktree-audit.sh` audits git worktrees against Claude Code transcripts and must not run in Linger, which has no worktrees. The `watch-pr` and `orch` scripts may run only when their owning workflow is authorized and their dependencies are present.

## Codex

| Upstream action | Codex action |
|-----------------|--------------|
| Read files | Use the filesystem tools or `exec_command`. Prefer `rg` and `rg --files` for discovery. |
| Create or edit files | Use `apply_patch`. Formatting and other bulk mechanical rewrites may use the relevant command. |
| Run a command | Use `exec_command`. Use non-interactive flags. |
| Search the web | Use the web tool when current or external evidence is required. |
| Invoke `/name` or the `Skill` tool | Load and follow the project skill named `name`. |
| Spawn an `Agent` or `Task` | Use `spawn_agent` when delegation is allowed. Replace `subagent_type` and `readonly` fields with a plain-language brief. |
| Wait for agents | Use `wait_agent`. Use `interrupt_agent` only to stop active work. There is no `close_agent`. |
| Use a todolist | Use Beads when required by the repository. Otherwise use `update_plan` for nontrivial work. |
| Ask a fixed-choice question | Use `request_user_input` when available. Otherwise ask one concise plain-text question. |
| `loop`, recurring follow-up | Use a heartbeat automation, or the applicable task or collaboration wait tool. Do not block with long sleeps. |
| `run` | Run the CLI or TUI and inspect its real output. |
| `verify` | Use the relevant browser, computer-use, test, or runtime tool and inspect the real artifact. |
| `plugin-dev:skill-development` | Use the project-available `$skill-creator` skill and its validator. |
| Task history | Use `list_threads` and `read_thread`. Cite tasks by title and ID. |

Concurrency: four collaboration slots including the main agent, so at most three children run at once. A request for dozens or hundreds of workers runs in waves of at most three.

Models: `claude-*` names in upstream sections are provenance, not valid Codex values. Use only models the collaboration tool exposes.

Global Codex configuration, when explicitly in scope, lives under `~/.codex/`. Never substitute `CLAUDE.md`.

These defaults follow the [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra) on instruction precedence, approval preparation, verification, and useful delegation. They do not change runtime permissions or available capabilities.

## Claude Code

Upstream pstack names Claude Code tools directly, so most instructions apply as written. These rows cover the Linger-specific differences.

| Upstream action | Claude Code action |
|-----------------|--------------------|
| Read files | Use `Read`, `Grep`, and `Glob`, or `Bash` for pipelines. |
| Create or edit files | Use `Edit` or `Write`. Bulk mechanical rewrites may use the relevant command. |
| Run a command | Use `Bash`. Use non-interactive flags. |
| Search the web | Use `WebSearch` or `WebFetch` when current or external evidence is required. |
| Invoke `/name` or the `Skill` tool | Use the `Skill` tool with the project skill named `name`. |
| Spawn an `Agent` or `Task` | Use the `Agent` tool. Use `subagent_type: "Explore"` for read-only discovery and `general-purpose` otherwise. `poteto-agent` and `comment-sicko` are not defined agent types; emulate them as described above. Never pass `isolation: "worktree"` in Linger. |
| Wait for agents | Agents run in the background and notify on completion. Continue local work until notified. Use `SendMessage` to continue an agent and `TaskStop` only to stop active work. |
| Use a todolist | Use Beads. `AGENTS.md` forbids `TodoWrite` and `TaskCreate` in Linger. |
| Ask a fixed-choice question | Use `AskUserQuestion`. |
| `loop`, recurring follow-up | Use the `loop` skill or `ScheduleWakeup` for self-paced follow-up, and `Monitor` for an event the harness can watch. Do not block with long sleeps. |
| `run` | Use the `run` skill, or run the CLI or TUI and inspect its real output. |
| `verify` | Use the browser, computer-use, test, or runtime tool that exercises the real artifact. |
| `plugin-dev:skill-development` | Use the available skill-creator skill (for example `anthropic-skills:skill-creator`). Keep frontmatter within the keys Codex's validator accepts: `name`, `description`, `license`, `allowed-tools`, and `metadata`. |
| Task history | In the desktop app, use the session-management tools (`list_sessions`, `search_session_transcripts`). Otherwise read transcripts under `~/.claude/projects/<project-slug>/*.jsonl`, where the slug is this repository's absolute path with `/` replaced by `-`. Cite sessions by title or ID. |

Concurrency: no fixed slot limit. Launch independent agents in one message so they run in parallel, and keep each wave small enough that you can read every result (about five). Larger fan-outs run in waves.

Models: the `Agent` tool's `model` field accepts the aliases it lists (`fable`, `opus`, `sonnet`, `haiku`). Map an upstream `claude-*` name to its family alias. Omit the field to inherit the parent.

Invocation: Claude Code ignores `agents/openai.yaml`, so skills that Codex keeps explicit-only (`poteto-mode` and the `principle-*` skills) are model-invocable on Claude Code by design. Do not add `disable-model-invocation`; Codex's validator rejects it.

`CLAUDE.md` imports `AGENTS.md` and `CONSTITUTION.md`; edit `AGENTS.md`, not `CLAUDE.md`. Global Claude Code configuration, when explicitly in scope, lives under `~/.claude/`. Do not write agent-private memories in place of shared instructions; use `bd remember` when `AGENTS.md` asks for persistent knowledge.
