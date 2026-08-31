# Explanation Guide

Use this guide after tracing the code. The main agent owns the explanation and must reconcile any explorer findings against the implementation.

## Evidence Standard

- Treat current code, consumers, tests, configuration, and repository instructions as evidence.
- Resolve contradictions by checking the code. Do not settle them by majority vote among explorers.
- Separate live behavior from dead code, target-state documents, historical context, and proposals.
- Acknowledge gaps directly instead of smoothing them over.

## Structure

Adapt these sections to the question. Omit sections that add no value.

### Overview

In one or two paragraphs, explain what the component does, why it exists, and where it sits in the larger system.

### Key Concepts

Define only the types, services, state, or abstractions needed to follow the rest. Describe the responsibility of each in concrete language.

### How It Works

Walk from trigger to effect. Name the functions or methods that run, the data they receive or produce, their decisions, and the boundaries they cross. Explain why complexity exists when that context is established by the repository.

Use prose rather than pseudocode. Include short code excerpts only when the exact expression is essential. Add a diagram only when it clarifies a multi-component relationship, repeated mapping, or sequence that prose would make harder to follow.

### Where Things Live

Provide a compact map of the few files a maintainer should open first. In Codex desktop, use clickable Markdown links with absolute paths and useful line numbers.

### Gotchas

Call out verified sharp edges, surprising conditions, important invariants, or unresolved gaps. Do not invent historical explanations.

## Style

- Prefer concrete subject-verb statements: "`ComposerService` calls `StreamHandler.begin()`" is clearer than "the service delegates to the handler."
- Explain at the user's altitude; do not pad a simple flow or turn the answer into annotated source code.
- Lead with the mental model, then support it with evidence.
- Make uncertainty and inference explicit.
