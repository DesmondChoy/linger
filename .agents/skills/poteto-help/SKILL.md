---
name: poteto-help
description: Answer questions about this repo's pstack setup, poteto-mode, and which skill, playbook, or principle fits a task. Use for /poteto-help or questions about using pstack.
metadata:
  short-description: find the right shared pstack workflow
---

# Poteto help

Read [runtime-adaptation.md](../poteto-mode/references/runtime-adaptation.md) before answering. This repo shares `.agents/skills/` between Codex and Claude Code through the `.claude/skills` symlink. Apply the current runtime's tools and the repository's authority rules.

Answer the question, give at most one useful example prompt, and link the local file the answer came from. A help question stays read-only. A request to do work, such as "use pstack to fix this bug", routes to [poteto-mode](../poteto-mode/SKILL.md) within the user's authorized scope.

This file maps questions to the files that own the details. Read the relevant file before recommending its workflow. Local files describe this adaptation. The [upstream guide](https://github.com/cursor/plugins/tree/99743e9c151c8537cbbf1f98bb38f34ef3368453/pstack/docs/guide) describes Cursor and may differ.

## Find what they need

Infer the need from the question and conversation. Go straight to the relevant section when it is clear. Ask one concise multiple-choice question only if setup, starting work, choosing a skill, fixing a run, or customization would lead to materially different answers.

Check only state that changes the answer:

- `.agents/pstack-models.md` holds optional model overrides, with a section for each runtime. Without a section for this runtime, roles inherit the parent model. Setup is optional.
- Look for an existing verification skill, focused tests, or app harness before recommending a new harness. A missing `verify-*` directory alone does not establish a verification gap.
- Check that a recommended skill is installed and that its required tools exist. Advanced playbooks have additional restrictions in the runtime adaptation.

## Get set up

The shared suite is already installed in this repo. Codex reads `.agents/skills/`; Claude Code reads the same files through `.claude/skills`. Global plugin installation is unnecessary for this project.

Use [setup-pstack](../setup-pstack/SKILL.md) only to configure optional project-local role overrides. It offers models the current runtime actually exposes and preserves the other runtime's settings. It does not write global configuration. A help question does not authorize running setup or changing model choices.

If cost matters, explain that delegation and review panels use additional tokens. Inherited models and smaller panels are the local defaults to consider. Keep independent verification where the task warrants it. Do not advertise upstream Grok or Claude model slugs as Codex options.

For an example prompt, read [prompting.md](references/prompting.md) and [recipes.md](references/recipes.md).

## Start a task with poteto-mode

Name the skill and state a goal, a check for completion, and any real constraints. Codex accepts an explicit `$poteto-mode` skill mention. Claude Code uses `/poteto-mode`. The mode selects a playbook and the skills that help the task. Beads tracks meaningful steps; the local workflow does not require copying every upstream checklist.

Do not promise Cursor Custom Mode persistence or its keyboard shortcuts on either runtime. When a new task needs the mode, invoke it explicitly. See the runtime adaptation for discovery differences and available tools.

To give a child the same style, point it at the installed poteto-mode file and use the current runtime's delegation tool. The upstream `poteto-agent` type is not installed here. Keep writers on disjoint paths in the shared checkout.

## Pick a skill

Read the skill before recommending it. Poteto-mode is the general entry point; a named skill is useful when the user wants a specific outcome.

| The user wants to | Skill |
|---|---|
| Run a substantial task with a suitable playbook | [poteto-mode](../poteto-mode/SKILL.md) |
| Restate the goal and problem before starting | [in-your-own-words](../in-your-own-words/SKILL.md) |
| Improve the approach before doing the work | [sharpen](../sharpen/SKILL.md) |
| Understand how current code works | [how](../how/SKILL.md) |
| Understand why a design was chosen | [why](../why/SKILL.md) |
| Understand a change in plain language | [teach](../teach/SKILL.md) |
| Recover recent project context | [recall](../recall/SKILL.md) |
| Catch up on changes in this chat | [ketchup](../ketchup/SKILL.md) |
| Find what a small diff could break elsewhere | [blast-radius](../blast-radius/SKILL.md) |
| Settle consequential types, ownership, or module choices | [architect](../architect/SKILL.md) |
| Compare several attempts at one brief | [arena](../arena/SKILL.md) |
| Split independent checks across available agents | [swarm](../swarm/SKILL.md) |
| Review a diff from independent evidence lenses | [interrogate](../interrogate/SKILL.md) |
| Reproduce a bug through a cheap local test | [tdd](../tdd/SKILL.md) |
| Apply TypeScript guidance | [typescript-best-practices](../typescript-best-practices/SKILL.md) |
| Review comments for concrete maintainability concerns | [no-comments](../no-comments/SKILL.md) |
| Remove AI writing patterns | [unslop](../unslop/SKILL.md) |
| Write technical documentation | [technical-writing](../technical-writing/SKILL.md) |
| Restate the last reply plainly | [bro](../bro/SKILL.md) |
| Add a missing way to exercise app behavior | [create-verification-skill](../create-verification-skill/SKILL.md) |
| Audit an existing verification skill | [maintain-verification-skill](../maintain-verification-skill/SKILL.md) |
| Check a measured performance claim | [benchmark-checklist](../benchmark-checklist/SKILL.md) |
| Design a playbook for a large or unusual change | [figure-it-out](../figure-it-out/SKILL.md) |
| Keep a reviewable decision trail | [show-me-your-work](../show-me-your-work/SKILL.md) |
| Configure optional models for this project | [setup-pstack](../setup-pstack/SKILL.md) |
| Capture recurring working habits as a mode skill | [automate-me](../automate-me/SKILL.md) |
| Review a task's lessons when requested | [reflect](../reflect/SKILL.md) |
| Prevent recurring agent mistakes through structural checks | [correct](../correct/SKILL.md) |
| Build a UI for a Grok Bot webhook, when its tools exist | [make-bot-ui](../make-bot-ui/SKILL.md) |
| Find their way around pstack | poteto-help |

For additional project skills, read the neighboring directories' frontmatter and route by their actual descriptions. Linger also bundles its own [quality](../quality/SKILL.md), [Beads](../beads/SKILL.md), corpus, and synthetic evaluation workflows. Their evidence and human adoption gates still apply.

Close calls:

- How traces current behavior; why traces the reasons; teach explains the relevant evidence plainly.
- Arena gives workers the same brief. Swarm partitions checks or runs a bounded race.
- Architect settles a consequential design and then implements within scope. Add "with checkpoint" when the user wants to review the design first.
- Interrogate reviews the diff. Blast-radius checks its effects elsewhere.
- Recall reconstructs recent project history. Ketchup covers the current chat. Session pickup resumes one specific prior task.
- Figure-it-out designs one run. Orchestrate is an advanced playbook with extra prerequisites.

## Playbooks and principles

Playbooks live under [poteto-mode](../poteto-mode/SKILL.md); they are not separate slash commands. Describe the outcome to select one. "Check on PR 123" selects Babysit in status mode; "fix the failing checks" authorizes its repair mode. Merging requires the user's authority.

The [multi-phase plan playbook](../poteto-mode/playbooks/multi-phase-plan.md) handles planning requests and respects an explicit planning-only checkpoint. Existing instructions and the requested scope decide whether to implement. Do not infer that asking for a plan authorizes code changes.

The runtime adaptation marks Shipping, Orchestrate, Autopilot, and worktree cleanup unavailable by default. Explain the prerequisites if asked; a help question does not activate them. This repo forbids worktrees unless the user explicitly requests one.

Principles are supporting skills that poteto-mode reads when relevant. Examples include proving behavior, testing an assumption shared by failed fixes, explaining a measured number, and testing observable behavior. Read the named principle before explaining it. Its directory is `principle-<name>`.

## Fix a run that went wrong

| Symptom | Check or steer |
|---|---|
| The mode is no longer guiding the task | Invoke poteto-mode explicitly and restate the goal. Do not prescribe Cursor keyboard shortcuts. |
| A new question became the next step of an old task | Say "new task" and state its scope. |
| A model choice had no effect | Read this runtime's section of `.agents/pstack-models.md` and check that the tool supports it. |
| A skill did not load automatically | Check its installed path, description, and invocation policy. Codex and Claude Code differ; see the runtime adaptation. |
| Parallel agents overwrote each other | Assign disjoint paths and serialize shared writes in the same checkout. |
| A long run made activity without completing anything | State an observable completion check and a stopping condition. Use only available, authorized follow-up tools. |
| A reply claimed success from a passing build alone | Ask for evidence that exercises the changed behavior. |

For a run that drifts, use the short steers in [prompting.md](references/prompting.md).

## Make pstack my own

Automate-me drafts a personal mode skill from project-scoped history. Reflect reviews lessons when requested. Correct addresses recurring mistake classes within the authorized scope. The authoring and eval playbooks support skill edits and evidence about how they behave. Use the current runtime's skill-creator workflow.

Fix a broken skill only when skill edits are authorized. Preserve local runtime mappings and validate metadata and references. Opening a PR is a separate authorized action.

## Reply

Lead with the answer. Give at most one example prompt adapted to the current runtime, then a link to the source file. Keep it short unless the user asks for the whole map.
