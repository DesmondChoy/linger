---
name: principle-fix-root-causes
description: "Apply when debugging. Trace each symptom to its root cause and fix it there; reproduce first, ask why until you reach it, resist nil-check guards that silence crashes."
---

# Fix Root Causes

When debugging, fix the fault, not the place where it surfaced. The symptom is where a wrong state became visible. The root cause is the first place the system did something it should not do, or failed to handle a state it should handle.

**Why:** A symptom fix hides the evidence and leaves the fault free to surface somewhere else. Each one makes the system harder to reason about, because the code now carries a workaround for a bug that nobody named.

**Pattern:**
- Reproduce with a focused test or runtime exercise where practical. If reproduction is unavailable, state the evidence limit and do not claim the original symptom was verified fixed.
- Ask "why" until you hit the root cause
- Ask whether the triggering state is legitimate. If it is, handling it where the code broke can be the root-cause fix. If the state should never exist, trace what produced it; a guard, retry, swallowed error, clamp, or discarded state at the symptom may hide the fault.
- If a workaround needs a paragraph-long comment to justify it, the code is wrong (fix the code, not the comment)
- Inspect related instances when they help establish the cause. Fix verified issues within the authorized scope and report relevant findings outside it.
- When stuck, instrument. Read the actual error and state.
- If the deciding fact required a deep investigation, propose the cheap signal that would have exposed it earlier.

**Restart bugs: suspect state before code**

Code doesn't change between runs. State does. When something "fails after restart," suspect stale persistent state first: config files, caches, lock files, serialized state. If clearing a state file restores behavior, prioritize state validation as the fix.
