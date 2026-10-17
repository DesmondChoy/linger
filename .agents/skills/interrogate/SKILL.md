---
name: interrogate
description: "Use for \"interrogate\", \"adversarial review\", \"multi-model review\", \"challenge this\", \"stress test this code\", \"find blind spots\", or \"tear this apart\". Up to three reviewers challenge changes from independent angles."
metadata:
  short-description: have independent reviewers try to break a diff
---

# Interrogate

Spawn up to three reviewers to adversarially review code changes. Each reviewer gets the same prompt and rubric plus an independent evidence lens. Valid project-local model overrides can add model diversity; otherwise reviewers inherit the parent model. Agreement across independent reviews is high-confidence signal; lone-reviewer findings are worth reading but lower confidence.

The deliverable is a synthesized verdict. Do NOT auto-apply changes.

**Runtime note.** Tool, model, and task-history names below resolve per runtime (Codex or Claude Code) via [`runtime-adaptation.md`](../poteto-mode/references/runtime-adaptation.md).

## Step 1, Determine Scope

Identify what to review from context:

- If the user points at specific files or a diff, use that.
- If on a feature branch, run `git diff main...HEAD` (or the appropriate base branch) for the full changeset.
- If the user's message references recent work, gather the relevant files.

Package the diff or file contents with any surrounding context files the reviewers need to understand the code.

## Step 2, Intent

Before spawning reviewers, state the intent in one clear paragraph from the user's message, commit messages, the PR description if one exists, and the code. If you're unsure about the intent, ask the user before proceeding.

## Step 3, Spawn Reviewers

Launch up to three reviewers in parallel with the runtime's subagent tool (`spawn_agent` on Codex, `Agent` on Claude Code). Use valid `interrogate reviewers` entries from `.agents/pstack-models.md` when present. Otherwise omit model overrides and distinguish reviewers with independent evidence lenses.

| Reviewer | Default lens |
|----------|--------------|
| Reviewer A | correctness and boundary behavior |
| Reviewer B | maintainability and architecture |
| Reviewer C | tests, failure modes, and operational risk |

For each reviewer, state that the task is read-only and grant no write scope. Apply a configured model only when it is valid; otherwise omit the override.

If a configured model is invalid, omit the override, continue with parent-model inheritance, and report the stale configuration. Do not open a pull request or edit configuration unless the user asks.

Read `references/reviewer-prompt.md` and fill in the same template for every reviewer with the stated intent, the diff or file contents, the rubric from `references/rubric.md`, and the code-quality lens from `references/code-quality-review.md`. Use only model settings exposed by the current runtime, following **poteto-mode**'s runtime adaptation.

## Step 4, Synthesize

As results come back, build a unified picture. Parse every reviewer's findings. Merge findings that describe the same issue differently, and note which models raised each one. Findings two or more models raised independently are the highest signal. Read a lone model's finding, but weight it accordingly. Note disagreements. If one model flags something and another explicitly says the opposite, that is context for the verdict.

## Step 5, Lead Judgment

You are the lead reviewer, a pragmatic senior engineer, not a neutral aggregator. Read `references/lead-judgment.md` for the full framework. Put every finding in one of four buckets, with the model(s) that raised it and a one-line rationale.

- **Act on**. Real issues affecting correctness, security, or maintainability given the actual goals. They would block a real PR.
- **Consider**. Legitimate, but you're not sure they outweigh the cost of addressing them now. Worth the user's attention.
- **Noted**. Technically valid but not actionable. Context-dependent, premature optimization, or low-impact at this stage.
- **Dismissed**. Wrong, nitpicky, or missing context, with a brief reason.

## Output Format

### Intent
> [The stated intent paragraph from Step 2]

### Reviewers
- Reviewer [label]: [model name], [N findings] (one bullet per reviewer)

### Act On
[Each: description, which models raised it, why it matters.]

### Consider
[Each: description, which models raised it, the tradeoff.]

### Noted
[Brief list.]

### Dismissed
[Each with a brief rationale.]

### Agreement Map
[Where models agreed and diverged, and what that pattern tells us.]
