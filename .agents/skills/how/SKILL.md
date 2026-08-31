---
name: how
description: Explain how a subsystem, feature, or runtime flow works by tracing the actual code and producing an evidence-backed architectural explanation. Use for codebase "how does this work?" questions and explicit architecture critiques; do not use for implementation work or line-level code review.
---

# How

Build a working mental model of the requested code, then explain it at the level of a senior engineer onboarding to the area. Prefer the maintained implementation, tests, configuration, and repository instructions over guesses from names or stale documentation.

This is a read-only workflow. Do not edit files, update trackers, or run mutating commands unless the user separately asks for implementation.

## Choose the Mode

- **Explain** is the default.
- **Critique** applies only when the user explicitly asks for architectural issues, problems, tradeoffs, or improvements. Explain the current design before judging it.

If the scope is ambiguous, state the narrowest reasonable interpretation and begin tracing. Ask only when different interpretations would materially change the answer and the repository cannot resolve them.

## Explain

### 1. Scope and locate

Identify whether the request concerns a subsystem, feature flow, service boundary, or narrow symbol. Read applicable repository instructions first. Use fast local search such as `rg --files` and `rg` to locate entry points, key types, tests, and configuration, then read the implementations.

Classify the question:

- **Narrow:** one module, utility, function, or short call chain. Investigate and explain directly in the main agent; do not delegate.
- **Broad:** a subsystem spanning multiple files or services, a cross-cutting feature, or a runtime flow with independent slices. Use bounded parallel exploration when Codex collaboration agents are available and applicable instructions permit delegation.

When uncertain, start narrow. Expand only when the trace demonstrates that more components matter.

### 2. Trace the behavior

For narrow questions, follow the full path yourself: trigger or caller, transformations and decisions, boundaries, outputs or side effects, and relevant tests.

For broad questions:

1. Split the question into two or three non-overlapping angles, limited by the available collaboration slots. Useful angles include entry point and orchestration, domain model and state, persistence or external boundaries, and presentation or delivery.
2. Spawn internal collaboration agents, not user-visible Codex tasks. Give each agent a standalone, read-only prompt based on [the explorer guide](references/explorer-prompt.md), a distinct angle, and the repository path. Do not hard-code a model unless the user or current instructions require one.
3. Continue a useful local trace while the explorers work. Wait only for agents whose findings are needed.
4. Verify important claims and contradictions against the code. The main agent owns synthesis and the final answer.

If collaboration is unavailable or not permitted, trace the angles sequentially in the main agent.

### 3. Explain

Use [the explanation guide](references/explainer-prompt.md). Adapt the structure to the question instead of filling every section mechanically.

The answer should usually cover:

- **Overview:** what the component does and why it exists.
- **Key concepts:** only the types, services, or abstractions needed to follow the flow.
- **How it works:** the trigger-to-effect path, transformations, decisions, and boundaries.
- **Where things live:** a compact map of the few files a maintainer should open first.
- **Gotchas:** verified sharp edges, surprising behavior, or unresolved gaps.

Use concrete symbol names and precise code references. In Codex desktop, prefer clickable Markdown links with absolute local paths and a line number. Include a Mermaid or ASCII diagram only when a multi-component relationship or sequence is materially easier to understand visually.

Distinguish confirmed current behavior from inference, historical context, proposals, and unknowns. Do not claim that an unused type, design document, or test helper is part of the live runtime without tracing a real consumer.

## Critique

Complete the explanation first so the current architecture is clear on its own.

Then read [the critic guide](references/critic-prompt.md) and [the critique rubric](references/critique-rubric.md). When internal collaboration agents are available and permitted, ask two or three independent critics to inspect the actual code. Give each the explanation, relevant file paths, and rubric; keep their prompts independent so one critic's conclusions do not anchor another. Distinct rubric lenses are preferable to invented model diversity.

If delegation is unavailable, perform one separate critique pass yourself after the explanation.

Act as the lead reviewer rather than concatenating findings. Verify evidence and classify each distinct concern:

- **Act on:** a demonstrated architectural problem worth fixing now.
- **Consider:** a real concern whose cost-benefit is unclear.
- **Noted:** a valid low-priority tradeoff or debt item.
- **Dismissed:** incorrect, unsupported, missing context, or merely stylistic.

Present the explanation first, followed by the critique verdict. Avoid prescribing rewrites unless the current design has a demonstrated cost.
