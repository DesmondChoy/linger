### Runtime forensics

**You own the diagnosis. Instrument the live process, don't theorize from source.** For "why is X leaking / spinning / slow at runtime", heap snapshots, idle-but-busy processes, intermittent glitches. The deliverable is a cited diagnosis, not a fix.

1. Capture the live signal on the matching surface with the runtime's CLI, browser, computer-use, or profiling tools: a CPU profile for a spinning process, a heap snapshot for a leak, a CDP trace for a visual glitch. A real artifact, not a guess.
2. Reduce the artifact to the smoking gun: the function on the hot path, the retainer chain from the leaked object to a GC root, the loop firing without input. Delegate large-artifact parsing when it helps and is allowed (the **guard-the-context-window** principle skill). Keep the reduced finding in the main thread and use the inherited model unless a valid project override applies.
3. Prove the mechanism before believing it. Use diagnostic instrumentation supported by the available tools to confirm the hypothesis. Inspect and instrument only the authorized target; preserve a read-only request and avoid production or persistent changes without permission.
4. Map the finding back to source: file, symbol, the line that allocates or schedules.
5. Keep the result focused on the diagnosis and evidence; no throughput report is required.

**Reply:** the signal captured, the reduced finding, how you proved the mechanism, the source location, artifact paths. No fix unless asked; hand back to Bug fix or Perf once the cause is known.
