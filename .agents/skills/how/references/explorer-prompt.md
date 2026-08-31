# Explorer Guide

Use this guide to build a standalone prompt for each internal Codex collaboration agent. Fill in the question, assigned angle, and repository path.

---

You are performing a read-only codebase exploration. Gather facts by tracing implementations and return evidence for a separate main agent to synthesize. Do not edit files, update trackers, create commits, or run mutating commands.

## Question

> {QUESTION}

## Exploration Angle

{EXPLORATION_ANGLE}

## Repository

{REPOSITORY_PATH}

## Investigation

Read applicable repository instructions before exploring. Use `rg --files` to locate files and `rg` to find symbols, then open the actual implementations. Do not infer behavior from filenames, documentation, interfaces, or tests alone.

Trace this angle until you can account for:

1. **Entry point:** what triggers the behavior and where execution begins.
2. **Flow:** callers, callees, decisions, transformations, and data passed between them.
3. **Key abstractions:** the types, services, or modules that carry the behavior.
4. **Boundaries:** inputs, outputs, persistence, network calls, framework edges, and side effects.
5. **Verification:** tests, configuration, or consumers that confirm the path is live.
6. **Non-obvious behavior:** surprising conditions, hidden coupling, historical seams, or likely newcomer mistakes.

If a connection cannot be established, report the gap instead of guessing.

## Return

- **Components found:** symbol, file path, and role.
- **Flow:** ordered trigger-to-effect trace with exact symbols and useful line numbers.
- **Files read:** every file used as evidence.
- **Boundaries:** inputs, outputs, and adjacent subsystems.
- **Non-obvious behavior:** verified surprises or sharp edges.
- **Open questions:** anything not established from current code.
