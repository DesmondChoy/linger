---
name: automate-me
description: "Use for automate me, create or update my mode skill, capture my working style as a skill, or wanting Codex to follow the user's recurring conventions. Drafts or revises a project-local mode skill with skill-creator and optional evidence from recent Codex tasks."
metadata:
  short-description: draft your own personal -mode skill from recent transcripts
---

# Automate me

A guided flow for turning the user's working conventions into a skill agents will follow. The output is one `-mode` skill tailored to them (e.g. `jay-mode`, `priya-mode`).

This skill orchestrates three parts: a bounded evidence pass, the **skill-creator** skill, and the **unslop** skill. It sequences them; it does not replace them.

**Platform note.** On Codex or another non-Claude runtime, the Claude tool names, `claude-*` slugs, and Claude built-in skills named below (including `plugin-dev:skill-development`) are Claude defaults. Resolve them via [`codex-tools.md`](../poteto-mode/references/codex-tools.md).

## Flow

### 0. Check for an existing skill

Look under `.agents/skills/` for `*-mode/SKILL.md` matching the user's handle. Keep the result project-local unless the user explicitly asks for a global skill. If one exists, confirm intent with `request_user_input` when available unless the user already asked to update it:

- Update the existing skill (default for repeat runs)
- Start fresh (rare; ask why before doing it)

Update mode changes the rest of the flow:
- Step 1 mines only history since the skill was last edited (`git log -1 --format=%cI <path>`).
- Step 2 asks what's changed or missing, not what to capture from zero.
- Step 4 edits the existing file in place. Preserve sections the user hasn't contradicted; revise ones with new evidence; add new sections only for genuinely new rules.

### 1. Mine their history

Use Codex task tools to list and read only recent tasks in this project. Do not scan another project's task history. If task tools are unavailable, use the current conversation and repository evidence, and state that the history sample is limited.

Survey recent Codex tasks within that scope for recurring patterns. When delegation is allowed, run at most three read-only agents across slices of the selected task set. Each agent uses the task IDs supplied by the parent and returns a short structured list with evidence pointers. Default signals worth hunting:

- Response preferences (length, tone, format, "dumb it down" corrections)
- Delegation habits (subagents, models, specialized workflows, parallelism)
- Verification posture (what "done" means; unit tests vs live repro; reviewers)
- Code and prose discipline (style, principles cited, lint/format tools)
- Process conventions from repository instructions, commits, PRs, review, and merge tooling
- Meta preferences (fixing skills mid-task, proposing new ones)

Cross-check across slices before elevating a signal. Patterns seen in 2+ slices are high-confidence; lone signals are weak and usually get dropped.

### 2. Ask the user directly

History misses intent that has not come up yet. Use `request_user_input` when available. Ask one or two short questions, then one optional free-form question only if needed.

Shape: one or two questions with 4-6 options each, `allow_multiple: true` for category questions. Start broad ("Which areas matter most?"), then follow up on selected areas with specific options. After the structured rounds, one free-form chat question catches anything the options missed.

Don't dump 20 questions. Two structured rounds plus one open question is usually enough.

### 3. Cluster findings

Group the combined signals into sections. Common ones (use only what applies):

- **Response style**: length, tone, format.
- **Autonomy**: how much to do without asking; MCP tool use.
- **Understand first**: which skills to reach for when scoping or investigating a change.
- **Subagents**: default, parallelism, model-to-task, specialized workflows.
- **Prose / code discipline**: principles, lint tools, style guides.
- **Review and verify**: repro posture, verification skills, live-testing tools.
- **Process**: repository rules, commits, PRs, review, and merge tooling.
- **Skills**: skill-authoring habits, fix-the-skill-first, proposing new skills.

The **poteto-mode** skill shows the shape. Read it for granularity. Don't copy its content; the user's rules are not the same as poteto-mode's.

### 4. Draft the skill

Use the **skill-creator** skill to author the skill. Placement:

- Path: preserve an existing project-local location. For a new mode, use `.agents/skills/<handle>-mode/SKILL.md`.
- Handle: the user's first name or chosen identifier.
- Frontmatter `description`: trigger on their name + `/<handle>-mode` + "work in their style", not on generic keywords like "write code" or "review PR".
- Frontmatter formatting: follow **skill-creator**. Keep `description` as one YAML scalar and use only Codex-supported frontmatter keys.
- Add `agents/openai.yaml` with `policy.allow_implicit_invocation: false` by default. Mode skills are heavy and opinionated. Enable implicit invocation only when the user explicitly wants it.

### 5. Iterate on prose

Apply the **unslop** and **skill-creator** guidance to the draft.

Show the draft to the user and take feedback. Expect multiple iterations. Cut ruthlessly; a mode skill is not a manual.

### 6. Verify and hand back

Run the Codex skill validator and any structural forward test required by **skill-creator**. Work in the current checkout. Do not create a worktree. Commit, push, or open a pull request only when the user explicitly asks.

## Guardrails

- **Don't overfit to one conversation.** A preference stated once and contradicted another time is noise. Require multiple instances before codifying it.
- **Don't be clever.** Restating other skills' contents, inventing metaphors, or writing "poetic" prose for an agent reader is cost without benefit. Keep it operational.
- **Reference, don't inline.** Other skills the user relies on should appear as path references, not pasted excerpts. Same for any principle docs they maintain elsewhere.
- **Keep sections minimal.** Only add a section if the user has a specific, non-default rule there. "Communicate clearly" is not a section. "Short paragraphs. Tables when comparing options. Bullets only when items are genuinely parallel." is.
- **Name conventions generic.** Use "the user" or "the human" in imperatives, not the author's first name. Others may read or adopt the skill.
- **Don't force symmetry.** If a user has no process rules worth writing down, skip the Process section entirely. Sparse is fine; bloated is not.

## Evaluation

A `-mode` skill is subjective output. Ask whether it reads like the user and whether it missed anything. Run structural validation even when a benchmark would add little signal.

Run a description-optimization loop only if the skill's trigger accuracy turns out to be a problem in practice.

## When not to use

- User wants a task-specific skill rather than working conventions: use **skill-creator** alone.
- User wants to capture one narrow workflow (e.g. "how I write commit messages"): that's a regular skill, not a mode skill.

## Reference files

- The **poteto-mode** skill: example of the output shape.
- The **unslop** skill: prose discipline for every line.
- the **skill-creator** skill: skill authoring process and validation guidance.
