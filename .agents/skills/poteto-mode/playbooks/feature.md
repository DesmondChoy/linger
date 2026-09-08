### Feature

Own the requested outcome, implementation, review, and verification.

1. Trace the affected contract and callers. Use **how** when the flow is unclear; follow an established local pattern when it already fits.
2. Name the relevant data shape and ownership. Use **architect** for consequential unresolved design choices. Use **arena** when independent alternatives can resolve uncertainty or the user requests it.
3. Identify bounded independent work that could improve speed or quality through delegation. Give writers disjoint paths, serialize shared edits, and keep useful local work moving while they run. Work directly when coordination would outweigh the benefit; no tournament or delegation quota is required.
4. Implement the smallest change that meets the requirements. Give any delegate a concrete scope and success criteria, then inspect its artifacts and diff. Update affected consumers within scope and preserve unrelated work.
5. Verify the changed contract with relevant tests or an exercise of the affected surface. Reuse existing checks and add coverage for meaningful gaps. Group coordinated edits into coherent units and verify before dependent work builds on them. Report inconclusive or unavailable checks accurately.
6. Resolve routine implementation choices within existing authorization. If a material decision or missing authority requires the user, complete authorized preparation first and present the concrete result. Honor explicit checkpoints.
7. Use **quality** for significant implementation changes and before an authorized commit. Add **interrogate** when a contested design warrants independent review. Run **Opening a PR** only for authorized git or PR actions.

**Reply:** what changed, consequential choices, verification, and any unresolved decisions or limits.
