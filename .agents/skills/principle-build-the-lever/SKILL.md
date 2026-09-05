---
name: principle-build-the-lever
description: "Apply when repetition, error risk, or a verification gap warrants automation. Reuse existing tools or build the smallest useful codemod, script, generator, or shared recipe."
---
# Build the Lever

Use automation when it makes the work faster, more reliable, or easier to verify at a reasonable maintenance cost.

**Pattern:** Check for an existing tool first. Build a small tool when repetition, error risk, or a concrete verification gap justifies it. Direct edits and inspection are appropriate when they establish the outcome more simply.

- For repetitive edits, learn the transformation on one unit, then validate the automation against it. Make the tool safe to rerun where repeated use is expected.
- Prefer a deterministic script over asking many agents to apply the same mechanical transformation.
- Give delegates a shared recipe when consistency requires one. A bounded prompt can be sufficient; create a skill only when reuse or complexity warrants a maintained artifact.
- Keep useful tools reviewable. Applying this principle may reuse an existing tool and does not require a new file in the diff.
- Commit a reusable tool only when commits are authorized and it belongs in the maintained project.

Per the [Laziness Protocol](../principle-laziness-protocol/SKILL.md), build the smallest tool that does or proves the job.

Distinct from [Encode Lessons in Structure](../principle-encode-lessons-in-structure/SKILL.md), which makes a recurring instruction a durable guardrail. This is throughput and reviewability on the work in front of you. For scripting the verification itself, see [Prove It Works](../principle-prove-it-works/SKILL.md).
