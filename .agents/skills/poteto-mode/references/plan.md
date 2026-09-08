# Plan

Produce a phased implementation plan grounded in the **Principles** section of the `poteto-mode` skill. For a plan-only request, the plan is the deliverable. When planning is part of an already authorized implementation task, continue into implementation unless the user requested a checkpoint.

Use Beads when repository instructions require durable plan tracking. Otherwise use a Codex plan only when it helps organize the planning work.

## 0. Triage

Use a concise plan when the user asks for one or dependencies, uncertainty, or scope make planning useful. An obvious small change can proceed directly when implementation is authorized. File count alone does not determine the workflow.

## 1. Re-read principles

Read the **Principles** section of `poteto-mode` and the leaf skills relevant to this plan. Apply the workflow and authority defaults in `AGENTS.md`; cite principles only when they explain a decision.

## 2. Scope and constraints

State the scope and constraints from the request and available evidence. Ask only when a material ambiguity remains, after completing independent authorized preparation; use the question tools allowed by the current runtime.

Resolve what is in scope vs explicitly out, technical or platform constraints, patterns to preserve, and the definition of done.

## 3. Explore in subagents

Delegate bounded independent exploration when it improves speed or quality. Keep useful local work moving while explorers run, and inspect their evidence. A narrow, well-understood plan can be grounded directly.

- Use `spawn_agent` only when delegation is allowed. Run at most three read-only explorers and give each a distinct scope.
- Omit model overrides by default. Apply only valid project-local overrides from `.agents/pstack-models.md`.

Each explorer returns file pointers, conventions, dependencies, test infrastructure, and entry points. No inlined dumps.

## 4. Write the plan

Use the user's requested destination when supplied. Otherwise keep a small plan in the response or Beads; use a reviewable scratch artifact when a longer plan needs one. Create maintained plan documents only when useful and within scope. A larger plan may use one file or a directory such as:

```
NN-slug/
├── overview.md
├── phase-1-scaffold.md
├── phase-2-...md
└── testing.md
```

### Phase sizing

- Group coordinated changes into coherent units with meaningful verification.
- Split at real dependency or ownership boundaries, especially before consequential uncertainty.
- Avoid fixed quotas for files, functions, phases, or test cases. Each phase should produce evidence that supports dependent work.

### Overview file

- **Context.** Problem and why now.
- **Scope.** Included; explicitly excluded.
- **Constraints.** Technical, platform, dependency, pattern.
- **Alternatives.** Compare meaningful contenders when the choice remains consequential and unresolved. A well-supported approach needs no fixed number of alternatives.
- **Applicable skills.** Domain skills the implementer should invoke, by name.
- **Phases.** Ordered standard-markdown links to phase files.
- **Verification.** Project-level commands.
- **Implementation guidance.** Per section 6.

### Phase files

- Back-link to overview.
- **Goal.** What the phase accomplishes.
- **Changes.** Files affected and the change at a high level. What and why, not how. No code snippets.
- **Data structures.** Name the key types or schemas. One-line sketch only (the **foundational-thinking** principle skill).
- **Verification.** Per section 5.

Order phases so infrastructure and shared types land first (the **foundational-thinking** principle skill). Each phase should be independently shippable.

For changes touching existing code, apply the **redesign-from-first-principles** principle skill: if we'd built this with the new requirement on day one, what would it look like? Redesign holistically; deliver incrementally.

If a phase creates or edits a skill, instruct the implementer to use **skill-creator**.

## 5. Verification per phase

Choose verification for the phase's changed contract and concrete risk. Reuse existing checks and add coverage only for meaningful gaps. Name required repository gates and relevant focused tests, inspections, or runtime exercises.

Exercise the real UI, CLI, or integration path when narrower checks cannot establish the changed behavior. Documentation and low-impact mechanical changes may need only direct inspection and focused validation. For a local bug fix, a regression test may be sufficient; an integration defect needs evidence across the affected boundary.

State unavailable checks and baseline failures accurately. Repeat or broaden verification only for new changes, failures, or unresolved concerns.

## 6. Implementation guidance

In the overview, name which poteto-mode non-negotiables the implementer must apply, by name:

- the **how** skill over each unfamiliar subsystem before changing it.
- the **interrogate** skill for adversarial review on contested designs before shipping.
- the repository's **quality** skill before an authorized commit. Use **deslop** only as an optional additional pass. Use **unslop** over prose when routed.
- the **show-me-your-work** skill to keep a decision trail when the plan is large enough to need an auditable record.
- the **babysit** skill only when the user explicitly asks for PR monitoring.

## 7. Hand back

Summarize phases, scope, relevant methods, and verification. Stop for a plan-only request or an explicit user checkpoint. Otherwise continue the already authorized implementation without a new approval step.
