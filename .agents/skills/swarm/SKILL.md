---
name: swarm
description: "Fan out N parallel workers, drain them, and return one report. Use for /swarm, 'swarm this', or parallel coverage, races, gauntlets, and exploration."
metadata:
  short-description: fan out N parallel workers across slices or races, then return one aggregated report
---

# Swarm

Fan out N parallel workers. They may cover separate slices, race the same brief, or mix both. The parent waits, aggregates, and returns one report.

**Platform note.** On Codex or another non-Claude runtime, the Claude tool names and `claude-*` slugs named below are Claude defaults. Resolve them via [`codex-tools.md`](../poteto-mode/references/codex-tools.md).

## Start

Use Beads when repository instructions require durable tracking. Otherwise use a Codex plan when these phases help.

1. Frame
2. Fan out
3. Aggregate
4. Report

## Phase A: Frame

1. State the done predicate and the artifact or report the swarm must return.
2. Choose the shape. Partition into slices, race N workers on identical briefs, or mix both. For a race or mixed shape, declare `first pass`, `rank all`, or `best-of` before spawning.
3. Set N from the user or derive it from the shape. Codex can run at most three child agents at once. Larger N runs in waves.
4. Read an optional valid `swarm workers` override from `.agents/pstack-models.md`; otherwise omit the model override and inherit the parent. For a model race, use only models exposed by the current collaboration tool.
5. Give each worker its own writable output under `/tmp/swarm-<slug>/worker-<n>/` or a disjoint repository path. Do not create worktrees in Linger.

## Phase B: Fan out

Spawn up to three workers with `spawn_agent`; drain completed workers before starting another wave. Every brief stands alone. Codex agents share this checkout, so output ownership is the isolation boundary.

Do not switch branches for a worker. If a task needs another git state, inspect it read-only with git commands or stop and ask for a compatible workflow.

Every brief stands alone. Include the goal, scope, exact slice or race arm, how to verify, and what to report. Reports use `PASS`, `ISSUES`, or `BLOCKED` with evidence.

If a worker drops out, proceed with N-1 and note it.

## Phase C: Aggregate

Read the terminal results. For coverage, every required slice needs a result. For a race, apply the selection rule declared up front. Use first pass, rank all, or best-of. Do not paste raw worker dumps.

Keep a compact result table, one-line evidenced issues, and explicit gaps or dropouts.

## Phase D: Report

Return one consolidated in-chat report with the table, issue one-liners, gaps or dropouts, and the race rule when used.

## Models

Swarm workers inherit the parent Codex model by default. Optional project overrides live in `.agents/pstack-models.md`; see `setup-pstack`.
