### Bug fix

Own the diagnosis, fix, and verification. Follow the evidence and remove speculative changes when it refutes their premise.

1. Reproduce the failure with the smallest test or runtime exercise that reaches the affected behavior. Use the real UI, CLI, or integration surface when narrower evidence cannot capture the symptom. If reproduction is unavailable, inspect reachable evidence, state the limitation, and ask only for information or access that remains necessary.
2. Form hypotheses and use relevant source, history, instrumentation, or runtime evidence to eliminate them. Use **how** or **why** when they resolve a specific gap. Delegate independent evidence gathering when it improves speed or quality; keep dependent diagnosis and shared edits coordinated.
3. Implement the smallest fix supported by the evidence. Use **architect** only if the fix leaves a consequential structural choice unresolved. Delegate a bounded implementation or review when useful and inspect the resulting diff yourself.
4. Re-run the original reproduction where available and the relevant checks for the changed contract. A focused unit test can establish a local bug fix; broader integration evidence is needed when the defect crosses that boundary. Do not claim a reproduced or verified fix beyond the evidence obtained.
5. Use **tdd** when explicitly requested or when the bug has a cheap local regression test. Reuse existing checks for covered behavior. A regression test and fix may share one commit; separate failing commits are not required.
6. Complete authorized preparation before requesting a missing decision or authority, and continue independent work while waiting. Run **Opening a PR** only for authorized git or PR actions.

**Reply:** the failure, supported root cause, fix, verification, and any unresolved evidence limits.
