---
name: arena
description: "Spawn N parallel candidates at the same task, pick a base, graft the strongest parts of the losers into it. Use for /arena, 'arena this', 'throw it in the arena', or when one attempt at a non-trivial artifact would lock in the wrong shape."
metadata:
  short-description: run N parallel attempts at the same task and pick the best parts
---

# Arena

Fan out N parallel attempts at the same task. Read every candidate end to end. Pick the strongest as the base. Graft the best ideas from the others into it. Verify the synthesized result.

**Runtime note.** Tool, model, and task-history names below resolve per runtime (Codex or Claude Code) via [`runtime-adaptation.md`](../poteto-mode/references/runtime-adaptation.md).

## Start

Use Beads when repository instructions require durable tracking. Otherwise use the runtime's plan tool when the phases materially help.

1. Frame
2. Fan out
3. Cross-judge
4. Pick
5. Graft
6. Verify

## Phase A: Frame

Every candidate gets the same prompt, so the prompt is the contract.

1. State the artifact each candidate is producing.
2. Derive the rubric. State what success looks like for *this* task, then turn it into 3-6 concrete gradeable criteria. Concrete: `Adds a --dry-run flag that skips writes`. Vague: `code is correct`. The rubric is the picker's tool in Phase D; candidates only see the task.
3. Pick the runners, within the runtime's concurrency limit (three on Codex). Read optional valid overrides from `.agents/pstack-models.md`; otherwise omit model overrides so the runners inherit the parent. Independent prompts and lenses still matter when all runners use one model.
4. Assign output paths under `/tmp/arena-<slug>/candidate-<n>/`. Do not create worktrees in Linger. N candidates writing to the same path is shared mutable state and fails the **separate-before-serializing-shared-state** principle skill test.

## Phase B: Fan out

Spawn all N candidates in parallel with the runtime's subagent tool (`spawn_agent` on Codex, `Agent` on Claude Code), each with the task, shared-grounding path, owned output path, and instructions to produce both the artifact and a short rationale naming alternatives considered and rejected. Continue useful main-thread work while they run.

If a candidate produces no output, proceed with N-1 and note the dropout.

## Phase C: Cross-judge

After all Phase B candidates complete, use a free collaboration slot for one read-only judge if available. Apply a valid `arena cross-judge pool` override from `.agents/pstack-models.md`; otherwise inherit the parent. The judge sees the rubric and completed candidates by path label, scores each criterion, and recommends a base. It runs in parallel with the parent's reading in Phase D, not with candidates that are still writing.

## Phase D: Pick a base

Read every candidate end to end before picking. Score each against the rubric criterion by criterion, not on holistic feel, and compare with the cross-judge. Agreement on the base confirms the pick. Disagreement means one of you is biased or the rubric was ambiguous. Read both rationales before deciding.

Pick the base a future maintainer can extend most easily without breaking invariants. When two feel tied, prefer the cleaner boundary or smaller API, per the Laziness Protocol.

## Phase E: Graft

Walk each losing candidate once more for what is worth porting into the base, usually one or two things per candidate, not most of it. Fold each graft in by hand, per the **redesign-from-first-principles** principle skill, so the result stays coherent under one mental model. Don't paste mechanically.

If the candidates converge on one shape, that is strong agreement. Note it and ship the consensus shape. No graft is needed. If they wildly diverge, Phase A was under-specified. Reframe and re-run rather than averaging the divergence.

## Phase F: Verify

Verify the synthesized artifact like any other output, per the **prove-it-works** principle skill. If verification finds a problem the arena missed, either Phase A was wrong (re-frame and re-run) or a candidate caught it and you missed the graft (go back to Phase E). Don't paper over it.

## Outputs

One synthesized artifact and a short synthesis note naming the base and why, the cross-judge verdict when used, each graft with its source candidate, rejections and why, convergence or dropouts, and the verification result.

## Models

Arena roles inherit the parent model by default. Optional project overrides live in `.agents/pstack-models.md`; see `setup-pstack`.
