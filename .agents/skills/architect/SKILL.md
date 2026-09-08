---
name: architect
description: "Sketch types, signatures, and module structure before code, then stay in the loop while implementation fills in. Use for /architect, 'architect this', 'design this', or non-trivial work where jumping to code would lock in the wrong shape."
metadata:
  short-description: resolve consequential choices in types, ownership, and module shape
---

# Architect

Design before implementing. Sketch the relevant types, signatures, and module boundaries in a design artifact. Use independent perspectives when they can resolve a consequential choice, then implement against the chosen sketch when authorized. Keep working application code intact while exploring alternatives. If implementation proves the sketch wrong, throw it out and redesign.

Stay within the user's requested mode. A design or architecture request produces a design unless the user also asks for implementation. Commit or pull-request language in this skill is conditional on current authorization.

**Platform note.** On Codex or another non-Claude runtime, the Claude tool names, `claude-*` slugs, and Claude built-in skills named below are Claude defaults. Resolve them via [`codex-tools.md`](../poteto-mode/references/codex-tools.md).

## Start

Use Beads when repository instructions require durable tracking. Otherwise use a Codex plan when the phases materially help.

1. Ground
2. Sketch
3. Agree
4. Implement
5. Scrap

## Phase A: Ground the problem

Trace the relevant callers, contracts, and ownership boundaries. Use the **how** skill when the flow is unclear and **why** when historical rationale could change the decision. A clear local precedent can supply the grounding directly; no separate research phase is needed for a settled contract.

## Phase B: Sketch

Write the caller's usage first, then derive the types, signatures, and module map needed for this change. Use `references/rationale-template.md` when the design needs a full package; keep a small design to a concise sketch and rationale.

Compare alternatives when current evidence leaves a consequential choice unresolved. Use **arena** with `references/runner-prompt.md` for independent design candidates when their comparison will improve the decision, or when the user explicitly requests a tournament. A fixed number of candidates is not required for ordinary architecture work; one well-supported design may suffice.

When running an arena, use up to three runners within runtime limits. They inherit the parent model by default, or use valid project-local overrides from [Models](#models). Record the synthesis decision when combining candidates.

Screen the proposed design against [`references/design-red-flags.md`](references/design-red-flags.md). Prefer an interface that hides complexity behind a small, useful surface. Reject or revise shallow modules, information leakage, and unnecessary pass-through methods.

## Phase C: Agree (opt-in)

When implementation is already authorized, proceed with the chosen design. For a design-only request, deliver the design. Do not add an approval step for an ordinary implementation choice.

Opt in to a checkpoint when the invoker explicitly asks: "/architect with checkpoint," "stop and show me before implementing," or similar. Then surface the synthesized design and pause for sign-off.

If a material choice or required authority remains missing, complete independent authorized preparation before asking about that gap. A separate design commit or adversarial **interrogate** review is optional when it helps the requested delivery; commits require authorization.

If the human pushes back on the shape (in a checkpoint or after the fact), treat that as Phase A evidence. Re-ground and re-run Phase B before writing more code.

## Phase D: Implement against the sketch

Implement the chosen sketch in coherent, verifiable steps. The sketch records the intended contract; keep the product working as the implementation develops.

Deviations from the sketch are signal worth surfacing, not friction to absorb silently. If a function needs a parameter the sketch didn't anticipate, ask whether the sketch was wrong, the requirement was missed, or the implementation is overreaching. Surface it; don't bolt it on.

## Phase E: Scrap when the architecture is wrong

If implementation keeps producing friction the sketch can't absorb, throw the sketch out. Don't bolt fixes onto a wrong design, per the **redesign-from-first-principles** and **fix-root-causes** principle skills.

The signal is a *pattern*, not single instances. Tells:

- The same shape of workaround appearing repeatedly across unrelated code.
- Multiple unrelated edge cases that all need special-case branches.
- Types that need escape hatches (`any`, casts, optional fields always set in practice) to compile.
- The "we need a lock" reflex when the sketch said the state wasn't shared.
- Callers having to know the abstraction's internal rules to use it.
- Two or more independent Phase D deviations of the same shape across the implementation. Surfacing deviations is Phase D's job; a repeated pattern of them is Phase E's trigger.

Use judgment. A few edge cases don't condemn an architecture. Some problems are legitimately complex; complexity in the data is not complexity in the design. The rewrite signal is repeated friction of the same shape, not single hard cases.

When you scrap:

1. Re-run the **how** skill over what's been built. The implementation lessons enter the new design as inputs, not vibes.
2. Redesign as if the new constraints had been day-one assumptions, per redesign-from-first-principles.
3. Subtract before adding, per the **subtract-before-you-add** principle skill. The new sketch should be smaller than the old one before it grows.
4. Return to Phase B with the new evidence. Run another arena only if competing designs would resolve the remaining uncertainty.

## Outputs

For small changes, provide the caller's usage, relevant types or signatures, and a concise rationale. Add a module map for larger work and a synthesis decision when multiple candidates were combined. The design may stay in a reviewable response or scratch artifact unless a repository document is useful or requested.

## Models

Architect runners inherit the parent Codex model by default. Optional valid project overrides live in `.agents/pstack-models.md`; see `setup-pstack`. Run at most three children at once.
