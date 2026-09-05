---
name: principle-sequence-verifiable-units
description: "Apply to multi-step work (sweeps, migrations, runs of similar edits) and to how you stack commits and PRs. Break work into small units that each end in a verifiable state, verify before dependent work builds on it, and order delivery so the sequence proves itself to a reviewer."
---

# Sequence work into verifiable units

Order work as coherent units with meaningful checks before dependent work builds on them. Distinguish existing baseline failures from regressions introduced by a unit. The same discipline runs at two altitudes, how you execute and how you deliver.

**Why:** A break caught at the unit that caused it is cheap to localize. A break caught after a batch is buried, and you have already built further on a broken base. Sequencing those same units into a delivery a reviewer can replay turns "trust me" into "watch it go red, then green."

**Execution.** Group coordinated edits into coherent units that can be checked meaningfully. Verify each unit before dependent work builds on it; related mechanical edits may share a focused check. Capture the current baseline and preserve existing work. Do not rebase or rewrite history without authorization.

**Delivery.** Order authorized commits and PRs so a reviewer can understand the change and its evidence. A regression test and fix can form one coherent commit; use separate proof stages only when they materially help review.

**Pattern:**
- Pick a coherent unit whose result a relevant check can establish, such as a caller migration or a bug fix with its regression test.
- Verify at meaningful boundaries before dependent work advances. Repeat or broaden checks only when new changes, failures, or unresolved concerns justify it.
- Order the units so the sequence builds confidence on its own, for you while executing and for a reviewer reading the stack.

The sequencing complement to the **prove-it-works** principle skill, which keeps each check real, and the **build-the-lever** principle skill, which makes the per-unit check cheap.
