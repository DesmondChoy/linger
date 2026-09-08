---
name: babysit
description: Monitor an open pull request and, when explicitly authorized, fix failing CI or straightforward review comments until it is merge-ready. Use for babysit this PR, keep it green, or monitor this pull request.
metadata:
  short-description: monitor an open PR, fix CI/comments, keep it merge-ready
---

# Babysit a PR

Use a Codex heartbeat automation for recurring follow-up. Use `gh pr checks --watch` for one active check run. Do not implement monitoring with long blocking sleeps.

**Platform note.** On Codex or another non-Claude runtime, the Claude tool names and Claude built-in skills named below (`loop`, `AskUserQuestion`) are Claude defaults. Resolve them via [`codex-tools.md`](../poteto-mode/references/codex-tools.md).

Inside poteto-mode, the **Babysit** playbook ([`../poteto-mode/playbooks/babysit.md`](../poteto-mode/playbooks/babysit.md)) supersedes this skill: it owns mode declaration, the merge frontier, stack safety, and the `watch-pr` watcher. This skill stays the standalone `/babysit` entry point for a single PR outside a poteto-mode run.

## When to use

- There's an open PR and the user explicitly wants it kept green, and you are not already inside a poteto-mode run (the playbook owns that case).
- The user invokes `/babysit` directly.
- A subagent that opens a PR does NOT babysit — return to the parent and let the parent decide.

## Steps

1. **Fetch PR state.**

   ```bash
   gh pr view <number> --json number,title,state,mergeable,reviewDecision,statusCheckRollup,mergeStateStatus,comments,reviews
   ```

2. **Triage in priority order.**
   - Merge conflicts (`mergeStateStatus == DIRTY`): inspect the conflict and propose the smallest safe resolution. Rebase, merge, or force-push only when the user explicitly authorized that exact history mutation.
   - Failing checks (`statusCheckRollup` entries with `conclusion: FAILURE`): pull logs with `gh run view <run-id> --log-failed`. Root-cause the failure. Change code, commit, and push only when the request authorizes those mutations and after repository quality and Beads sync requirements pass.
   - Review comments: investigate feedback and act on findings supported by current code and evidence. Resolve ordinary implementation choices within existing authorization. When a material product decision or required authority remains missing, complete independent authorized preparation and ask about that specific gap. Reply externally only when messaging is authorized.
   - Review-bot comments: classify fix/dismiss/ask per [`references/bugbot-triage.md`](references/bugbot-triage.md). Severity calls for stronger investigation and verification, not another approval by itself.

3. **Monitor.** Use the Codex recurring mechanism that matches the request:
   - Active CI run: poll `gh pr checks --watch` (it blocks until checks finish, so no separate loop interval needed).
   - Awaiting reviewer: a 20 to 30 minute heartbeat automation.
   - Idle but want to catch new comments: hourly.

4. **When to stop.**
   - Build is green, every comment resolved, branch merges cleanly → call it ready.
   - After repeated unsuccessful cycles, reassess the cause and verification method. Continue while making concrete progress within scope. Stop when the outcome is reached, the user asks, or an unresolved blocker requires user input or an external change. Preserve explicit user checkpoints.

5. **Report.** Summarize fixes applied, comments addressed, comments deferred (with reason), current PR status. Cite each commit by SHA.

## Hard rules

- Do not rewrite history on a branch others may have pulled without explicit authorization. Reuse authorization already provided for the same history mutation and scope.
- Don't tweak a test's expected values just to get a pass. Only change an assertion when the behaviour genuinely changed and the assertion was pinned to the old behaviour.
- Never skip hooks (`--no-verify`).
- Never bypass a failing check by marking it as not required.
- `gh pr ready` only when all checks are green and no unresolved review comments remain.

## Cross-refs

- `poteto-mode` routes here only when the user explicitly requests PR monitoring.
- Use `interrogate` before opening if the diff is contested; once open, babysit takes over.
- Use `unslop` on any prose you write here (PR comments, commit messages, status reports).

## Provenance

This is a Claude Code analog of Cursor's `/babysit`, not a port — Cursor's implementation is closed source. The skill is independently authored, with its own prose and structure; the workflow is informed by Cursor's public `/babysit` behavior. The only overlap with other PR tools is the `gh` CLI commands it runs, which are functional invocations rather than copied text.
