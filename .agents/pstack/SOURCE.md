# pstack source pin

- Imported: 2026-09-01
- Refreshed: 2026-10-16
- Upstream suite: `cursor/plugins/pstack@99743e9c151c8537cbbf1f98bb38f34ef3368453` (0.15.25)
- Previous upstream pin: `46125561306434d8a1d7745d540d8932ab0cd2a2`
- Codex-aware starting port: `michael-denyer/pstack-claude@c2ade4bba14fb4706857286afb5528bc2244bf44`
- Installed scope: project-local `.agents/skills/`
- Imported skill directories: 61 (53 current pstack directories plus eight retained port/team-kit skills)
- Preserved existing skill: `.agents/skills/how/`

To refresh the suite, compare the pinned upstream tree with `.agents/skills/`, reapply the Linger authority rules and the Codex and Claude Code mappings in `poteto-mode/references/runtime-adaptation.md`, keep skill bodies runtime-neutral, then run every skill through Codex's `quick_validate.py` and `uv run python .agents/pstack/validate.py` for shared discovery, metadata, and links. Preserve existing invocation policies and the local `how` implementation.

The 2026-10-16 refresh adds all ten upstream skill directories, adapts help and model setup to the shared local configuration, and preserves the project-specific skills. Optional bot, forge, orchestration, and worktree workflows still require their actual tools and authorization. Bundled script tests require Bun; the core skills do not.
