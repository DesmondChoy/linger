### Perf issue

**You own the measurement story. Plan, review, verify the numbers.** Tie every fix to a measurement, don't read source instead of measuring.

1. Capture a baseline trace on the affected surface with the runtime's CLI, browser, computer-use, or profiling tools. Vet the baseline, and each later number, with the **benchmark-checklist** skill.
2. Use **how** to ground hypotheses. Do not claim a performance ceiling without running it first. Try the performance mantras in order, cheapest first:
   1. Don't do it. Stop work whose result nothing uses.
   2. Do it, but don't do it again.
   3. Do it less.
   4. Do it later.
   5. Do it when they're not looking.
   6. Do it concurrently.
   7. Do it cheaper.

   Stop when an earlier approach meets the target.
3. Plan the fix from the trace. Use **architect** for a consequential unresolved structural choice. Delegate bounded independent work when it improves speed or quality, using the inherited model unless a valid project override applies. Review the diff and capture a post-fix trace. Verify each coherent attempt before trying the next, per **sequence-verifiable-units**.
4. Parse and compare the artifacts. An inconclusive or wrong-surface result is not a pass. Report it.
5. Cite the measurements and artifact paths in the handoff or authorized PR.
6. Run **Opening a PR** only for authorized git or PR actions.

For sustained improvement against a metric rather than a one-off fix, use the Hillclimb playbook (`playbooks/hillclimb.md`).

**Reply:** baseline number, post-fix number, delta, artifact path.
