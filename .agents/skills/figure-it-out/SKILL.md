---
name: figure-it-out
description: "Design an auditable playbook when no narrower one fits: a large migration, an ambitious multi-part change, or work a human reviews after stepping away. Scales rigor to the task, runs a hypothesis loop, and logs decisions via show-me-your-work. Use for /figure-it-out, 'figure it out', a large migration, or when no narrower playbook applies."
metadata:
  short-description: design a rigorous, auditable playbook for a task no bundled playbook fits
---

# Figure it out

When the task matches no playbook, design one. The deliverable before any code is the workflow itself: a sequence of phases that scales rigor to the task, runs the scientific method, and leaves a decision trail a human can audit after stepping away. Scale rigor to concrete uncertainty, impact, and reversibility. Use the smallest workflow that can establish the requested outcome.

Don't reinvent a playbook you already have. A focused single-unit task that matches Bug fix, Perf, Feature, Visual parity, Eval, or Multi-phase plan routes there. But a large or cross-cutting version of one (a migration across many call sites, an ambitious multi-part change), or work the user reviews after stepping away, belongs here even though a single-unit version would be a Feature. The rigor and the audit trail are the point.

## Start

Use Beads when repository instructions require durable tracking. Otherwise use a Codex plan when the phases help. Read the Principles section of **poteto-mode** before designing the run.

## Phase A: Frame

Ground first, then commit. Don't start the run until you can state:

- The definition of done as a falsifiable predicate (the **prove-it-works** principle skill). "Done well" has to be checkable.
- Scope, quantified: rough units and effort, plus the blockers grounding surfaced. Raise them before spending hours, not after fifty doomed commits.
- The rigor level and the concrete risks that justify it. Use stronger gates for irreversible decisions and high-impact changes, and focused checks for reversible, low-impact work.

Share the framing and tradeoffs before a long run, then proceed within existing authorization. Honor explicit user checkpoints. Ask only when a material decision or required authority remains unresolved, after completing independent authorized preparation. Duration alone does not require approval.

## Phase B: Design the workflow

Decompose into atomic, independently-landable units. Sequence riskiest-unknown-first so option value stays high. Scaffold and verification come before features (the **foundational-thinking** principle skill).

- Identify suitable verification and capture a relevant baseline before changing behavior. Reuse existing checks; add a harness only when it resolves a concrete verification gap.
- Use **architect** for consequential unresolved design choices. Use competing prototypes or **arena** when they can resolve that uncertainty or the user requests them. A settled design needs no tournament.
- Decide what fans out. Parallelize only across genuine seams. In Linger, give concurrent writers disjoint paths in the shared checkout and serialize overlap. Do not create worktrees.
- Write the designed phase list down. That list is what the human reviews.

Then put the design into motion. Add its steps to the todolist as concrete items, after the Phase C entry and before Phase D. Run each under the Phase C loop discipline, and weave the Phase D log through them, a row as each step lands, rather than saving the whole trail for the end.

## Phase C: Run the loop

Each unit is an experiment: state the hypothesis, make the smallest change, measure against the predicate on the real artifact, keep it if it advanced, revert it if it didn't.
Apply **sequence-verifiable-units**: group coordinated edits into coherent units and verify before dependent work builds on them.

- Verify by inspecting the artifact, never a self-report. When something passes too easily, suspect the observation method before the system. A blank screenshot passes a lazy gate.
- Inspect delegated artifacts and relevant verification before accepting the result. Add an independent reviewer when the risk or uncertainty warrants one. Investigate a suspect gate and correct it when its contract is wrong.
- A verdict is VERIFIED, NOT VERIFIED, or INCONCLUSIVE. Inconclusive is not a pass. Don't hide a negative.

## Phase D: Keep the audit trail

Log the run via the **show-me-your-work** skill when an audit trail materially helps. Keep the trail local by default. Commit it only when the user has authorized a commit and the reviewer needs the trail to trust the work.

## Phase E: Verify and hand back

Check the whole against the Phase A predicate on the real product, not just the harness. Encode any recurring correction as a gate, a lint rule, a check, or a script, so the win can't silently regress (the **encode-lessons-in-structure** principle skill).

**Reply:** the playbook you designed, the rigor level and why, the decision-trail path, what's verified against the predicate, and what's still open.
