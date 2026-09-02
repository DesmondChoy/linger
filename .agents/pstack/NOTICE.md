# pstack notices

This repository vendors and adapts the pstack skill suite under `.agents/skills/` for project-local use with Codex.

## Sources

- Most pstack skills, principle skills, playbooks, references, and scripts derive from [`cursor/plugins/pstack` at `4612556`](https://github.com/cursor/plugins/tree/4612556/pstack). Copyright 2026 Lauren Tan. Licensed under the MIT license in [`LICENSE`](LICENSE).
- `deslop`, `fix-ci`, `fix-merge-conflicts`, `get-pr-comments`, `make-pr-easy-to-review`, `thermo-nuclear-code-quality-review`, and `what-did-i-get-done` derive from [`cursor/plugins/cursor-team-kit` at `e46364b`](https://github.com/cursor/plugins/tree/e46364b8be46000b7df0f260550cd712afbb8d36/cursor-team-kit). Copyright 2026 Cursor. Licensed under the MIT license in [`LICENSE-cursor-team-kit`](LICENSE-cursor-team-kit).
- The starting Codex-aware port came from [`michael-denyer/pstack-claude` at `c2ade4bba14fb4706857286afb5528bc2244bf44`](https://github.com/michael-denyer/pstack-claude/tree/c2ade4bba14fb4706857286afb5528bc2244bf44). Its upstream pstack pin was `4612556`.
- `babysit` is independently authored in that port, informed by Cursor's public babysit behavior.

The existing project-local `how` skill was adapted separately from [`poteto/how`](https://github.com/poteto/how) and was preserved instead of overwritten by this suite import.

## Project adaptation

The imported files were edited for Codex's supported skill frontmatter, project-local `.agents/skills` discovery, current collaboration tools and capacity, parent-model inheritance, Linger's no-worktree rule, Beads workflow, and the rule that skills never broaden user authorization. Claude and Cursor names that remain in retained upstream reference material resolve through `.agents/skills/poteto-mode/references/codex-tools.md`.

Plugin manifests, Claude hooks, command stubs, and the superpowers-derived hook wrapper from the source port were not imported.
