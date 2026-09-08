### Opening a PR

Run this playbook only when the user explicitly authorizes the requested git and GitHub mutations. A request to implement, review, diagnose, or verify does not authorize a commit, push, or pull request.

1. Work in the current checkout and current branch. Linger forbids worktrees unless the user explicitly requests one. Preserve unrelated user changes and stage only intended paths.
2. Run the repository's `quality` skill and the relevant tests or checks. The optional `deslop`, `no-comments`, `technical-writing`, and `unslop` passes do not replace repository quality gates.
3. Inspect the final diff and `git status`. Separate intended hunks from unrelated edits, including within a shared file. Ask only if they cannot be distinguished safely. Investigate verification failures, distinguish baseline failures from regressions, and satisfy required gates before publishing. Finish independent authorized preparation before requesting any missing decision or authority.
4. Commit only when authorized. Use a focused conventional subject when it fits the repository. Do not amend, rebase, or rewrite history unless the user explicitly requests it.
5. Before a Git push in this Beads repository, sync Beads as required by `AGENTS.md` with `bd dolt push`. If that sync or the Git push fails, stop and report the exact command and error.
6. Push only when authorized. Open a pull request only when the user asked for one. Never infer PR authority from a playbook that links here.

When a pull request is requested, write its title and description from the verified diff. Include intent, scope, real tradeoffs, blast radius, and verification. Use source paths and commands that exist. Do not start a babysit or merge workflow unless the user asks for it.

**Reply:** the commit or PR link when created, the focused scope, verification results, and any blocked sync or push step.
