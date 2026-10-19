#!/usr/bin/env python3
"""Check the shared pstack installation's discovery, metadata, and file links."""

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml


def validate(root: Path) -> tuple[list[str], int, int]:
    skills = root / ".agents/skills"
    claude_skills = root / ".claude/skills"
    errors: list[str] = []
    links = 0
    if not claude_skills.is_symlink() or claude_skills.resolve() != skills.resolve():
        errors.append(".claude/skills must point to the shared .agents/skills directory")

    entries = sorted(skills.glob("*/SKILL.md"))
    if not entries:
        errors.append("No project skills found")
    allowed = {"name", "description", "license", "allowed-tools", "metadata"}
    for entry in entries:
        relative = entry.relative_to(root)
        match = re.match(r"\A---\n(.*?)\n---(?:\n|$)", entry.read_text(), re.S)
        if not match:
            errors.append(f"{relative}: missing YAML frontmatter")
            continue
        try:
            metadata = yaml.safe_load(match[1])
        except yaml.YAMLError as exc:
            errors.append(f"{relative}: {exc}")
            continue
        if not isinstance(metadata, dict):
            errors.append(f"{relative}: frontmatter must be a mapping")
            continue
        if metadata.get("name") != entry.parent.name:
            errors.append(f"{relative}: skill name must match its directory")
        if not isinstance(metadata.get("description"), str) or not metadata["description"].strip():
            errors.append(f"{relative}: missing description")
        unexpected = metadata.keys() - allowed
        if unexpected:
            errors.append(f"{relative}: unsupported frontmatter keys {sorted(unexpected)}")
        sidecar = entry.parent / "agents/openai.yaml"
        if sidecar.exists():
            try:
                config = yaml.safe_load(sidecar.read_text())
                if not isinstance(config, dict):
                    raise ValueError("metadata must be a mapping")
                policy = config.get("policy", {})
                if not isinstance(policy, dict):
                    raise ValueError("policy must be a mapping")
                if "allow_implicit_invocation" in policy and not isinstance(
                    policy["allow_implicit_invocation"], bool
                ):
                    raise ValueError("allow_implicit_invocation must be a boolean")
            except (yaml.YAMLError, ValueError) as exc:
                errors.append(f"{sidecar.relative_to(root)}: {exc}")

    documents = sorted(skills.rglob("*.md")) + sorted((root / ".agents/pstack").glob("*.md"))
    for document in documents:
        fence = None
        for line_number, line in enumerate(document.read_text().splitlines(), 1):
            location = f"{document.relative_to(root)}:{line_number}"
            if re.match(r"^(<{7}|={7}$|>{7})", line):
                errors.append(f"{location}: unresolved merge marker")
            marker = re.match(r"^\s*(`{3,}|~{3,})", line)
            if marker:
                if fence is None:
                    fence = marker[1]
                elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                    fence = None
                continue
            if fence is not None:
                continue
            prose = re.sub(r"`+[^`]*`+", "", line)
            for target in re.findall(r"\[[^\]\n]*\]\(([^)\n]+)\)", prose):
                target = target.strip().strip("<>")
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                path = unquote(parsed.path)
                if any(token in path for token in ("*", "<", ">")):
                    continue
                links += 1
                if not (document.parent / path).exists():
                    errors.append(f"{location}: missing link target {path}")
    return errors, len(entries), links


if __name__ == "__main__":
    failures, skill_count, link_count = validate(Path(__file__).resolve().parents[2])
    if failures:
        print("\n".join(failures), file=sys.stderr)
        sys.exit(1)
    print(f"Validated {skill_count} shared skills and {link_count} local links for Codex and Claude Code.")
