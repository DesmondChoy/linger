---
name: principle-prove-it-works
description: "Apply after completing a task, before declaring done. Verify against the real artifact (run the feature, read the actual value, inspect the diff), not a proxy, self-report, or 'it compiles.'"
---

# Prove It Works

Verify every task output by checking the real thing directly. Do not infer from proxies, self-reports, or "it compiles."

**Why:** Unverified work has unknown correctness. Indirect verification (file mtimes, output freshness, agent self-reports, cached screenshots) feels cheaper than direct observation. Acting on a wrong inference costs far more than checking the source.

**Pattern:** After completing any task, ask: "how do I prove this actually works?"

Check the real thing, not a proxy:
- Check process liveness directly, not indirectly through derived state
- Read the actual value, not a cached or derived representation
- When verification fails, suspect the observation method before suspecting the system

Select checks that establish the changed behavior or contract. Run required repository checks and the smallest relevant build, test, or feature exercise. Exercise the full communication path when the change affects integration behavior and narrower evidence cannot establish correctness. For documentation and mechanical changes, direct inspection, diff review, and relevant validation may be sufficient.

Once checks pass, repeat or broaden them only for new changes, failures, or unresolved concerns. Distinguish baseline failures and unavailable checks from passes; do not create tests that merely mirror the implementation or add no meaningful signal.

Delegation: trust artifacts, not self-reports.
When verifying delegated work, inspect the actual output artifact (git diff, file contents, runtime behavior), not the delegate's summary. Agents report what they intended, not always what happened.

## Script the check when you can

Prefer existing deterministic checks when they establish the result. Add a reusable script only when repeated verification or a concrete evidence gap justifies its maintenance cost. Direct inspection is sufficient when it reliably verifies a low-impact artifact.

Keep the artifact visible for the human. Commit it only when commits are authorized and the trail needs to remain auditable, as for a large port or migration (the **show-me-your-work** skill). Most work just needs it visible, not committed.
