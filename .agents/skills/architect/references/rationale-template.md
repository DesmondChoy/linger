# Rationale template

The prose that ships alongside the type sketch. One page. Sentence-case headings, no boilerplate. Replace the italic notes with actual content.

## Problem

*One paragraph. What we're trying to do, and what about the existing system or constraints makes the shape non-obvious. If [Phase A](../SKILL.md#phase-a-ground-the-problem) surfaced constraints the design must honor (existing types to interop with, callers we can't break, invariants that crossed our boundary), name them here so the reader sees the same constraints you saw.*

## Usage (caller's view)

*Write this first, before the type sketch. Show the README or quickstart the consumer reads, plus two or three realistic call sites in their own code. What they import, what they call, what comes back. The type sketch in [Shape](#shape) is derived from this. The two must agree; when they diverge, reconcile the sketch to the usage, not the reverse. The caller's experience is the spec. The types serve it.*

## Shape

*The recommended architecture. Data structures first; then how data flows through the signatures. Name the load-bearing decisions. State which invariants are encoded in types, where validation lives, and what the system deliberately does not do. Judge interface depth explicitly. State what complexity the public surface hides, what remains exposed to callers, and why the interface is no larger than needed. Cite the principle behind each decision (e.g., `per boundary-discipline`); don't restate it.*

## Synthesis decision

*Include when [arena](../../arena/SKILL.md) was used. Record which candidate became the base and why, what was adapted from others, and what was rejected. Omit for a single design.*

## Tradeoffs accepted

*One bullet per tradeoff the chosen shape makes. Form: "we accept X in exchange for Y." Name anything a future reader might mistake for an oversight, including things that look like premature optimization or premature simplification.*

## Alternatives considered

*Name meaningful alternatives considered and why they were rejected, including their interface depth and exposed complexity when relevant. If the evidence identified a clear fit, state the deciding constraints briefly; do not invent alternatives to fill a quota.*

## Open questions and risks

*Record material unresolved choices, missing authority, and relevant risks with the evidence already gathered. Resolve ordinary implementation choices within existing authorization. Ask the user only about remaining decisions that need their input, after completing independent authorized preparation.*

## Next implementation step

*The first thing to build against the sketch. One sentence. What you'd start writing immediately after synthesis (or after the Phase C checkpoint, if a checkpoint was opted into).*
