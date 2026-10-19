# Word the prompt

A prompt states the intent and the check for completion. A few plain sentences usually suffice. The user's explicit constraints and checkpoints remain authoritative. Use `$skill-name` for an explicit Codex skill mention, or `/skill-name` in Claude Code. The examples below use slash names as shorthand.

## Put in

- The goal. Say what is wrong or what the user wants.
- The done check. It can pass or fail. "Make it better" and a duration are not checks.
- The proof to show. Ask for the real command output, a video of the flow, the stored value, or a before and after number.
- What the user already knows. A symptom, a repro step, a log, or a link saves the agent a search.
- The real constraints. "repro first", "don't change any code yet", "zero behavior change", and "let me review before proceeding" each change what the agent does.

## Leave out

- The how. Say what to achieve, and leave the agent room to find a better way.
- A list of skills or steps. A hand-written order drops or reorders steps the playbook keeps. Name a skill only to override one choice.
- The user's theory of the cause, until the agent restates the problem. A stated guess narrows the search.

## Load the context first

- For a noisy report, ask the agent to restate the underlying issue in its own words and in plain English before it does anything else. A misreading shows up before any code exists.
- In a fresh chat, `/recall` earlier work on the topic. Old chats hold context that the new agent lacks.
- Before a change to unfamiliar code, ask `/how` for the mechanics and `/why` for the reasons. An agent with no traced model fixes the symptom at the first plausible spot.
- Ask `/teach` to make the case for a choice, as in "convince me it fixes the cause and not the symptom". A case is easier to check than a summary.

## Design before the plan

- Compare designs when a consequential uncertainty warrants it. Ask for prototypes and screenshots when they can resolve that uncertainty. Routine work with a clear local precedent does not need competing designs.
- Let prototypes answer the open questions. Don't review an abstract plan adversarially, because reviewers invent risks that never happen.
- For a shared package or API, ask for the README or a tutorial first, then work back to the code. The doc becomes the target the agent checks itself against.
- Ask for the plan only after the design is settled. Each step of the plan ends in a check.

## Follow up short

- "do it", "continue", and "keep going until done" are whole prompts once the chat holds the task.
- Start with "new task" when the subject changes. Otherwise the mode treats the message as the next step.

## Before stepping away

- State when you are stepping away and which decisions the agent may make. Explicit checkpoints still apply.
- Write completion as checks each iteration can run. Use only the follow-up tools available and authorized on the current runtime.
- Keep agents in this checkout with disjoint write scopes. This repo forbids worktrees unless the user explicitly requests one.
- State any additional authority you intend to grant, such as permission to commit. Stepping away alone does not grant that authority.
- Ask for a decision log to audit later.
- Give an exit: "if you're truly stuck after a few hours, stop and write up why".

## Steer in one line

- Restate the goal: "i said the goal is to repro. i did not ask for a fix yet."
- Name the principle: "apply prove it works. show me the real output, not the build log."
- A principle name works because the agent already read the rule. Its reply names the decision the rule changed.
