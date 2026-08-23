"""Deterministically validate a synthetic-journal pre-generation report."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_SECTIONS = (
    "Decision",
    "Your selection",
    "Target evaluation design",
    "Current implementation and required work",
    "Expected behavior and evaluation",
    "Proposed generator prompt",
    "Ground truth lifecycle",
    "Architecture and academic relevance",
)
CANONICAL_NOUNS = (
    "Objective",
    "Backstory",
    "Prop",
    "Scene",
    "Line",
    "Ground truth",
)
FILENAME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{6}[+-]\d{4}-pre-generation-report(?:-\d{2})?\.md$"
)


def _strip_emphasis(value: str) -> str:
    return re.sub(r"[*_`]", "", value).strip()


def _section(text: str, heading: str) -> str:
    match = re.search(
        rf"^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    return match.group(1) if match else ""


def narrative_word_count(text: str) -> int:
    """Count narrative words, excluding headings, tables, and fenced blocks."""
    lines: list[str] = []
    inside_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            inside_fence = not inside_fence
            continue
        if inside_fence or line.lstrip().startswith("|") or line.startswith("#"):
            continue
        lines.append(line)
    return len(re.findall(r"\b[\w'-]+\b", "\n".join(lines)))


def validate_report(
    path: Path, selected_objective_ids: tuple[str, ...] = ()
) -> list[str]:
    errors: list[str] = []
    if not FILENAME_PATTERN.fullmatch(path.name):
        errors.append("filename does not match the timestamped report contract")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read report: {exc}"]

    headings = re.findall(r"^## (.+?)\s*$", text, flags=re.MULTILINE)
    positions = [headings.index(name) if name in headings else -1 for name in REQUIRED_SECTIONS]
    missing = [name for name, position in zip(REQUIRED_SECTIONS, positions) if position < 0]
    if missing:
        errors.append(f"missing required sections: {', '.join(missing)}")
    elif positions != sorted(positions):
        errors.append("required sections are out of order")
    forbidden = [name for name in ("Risks and opportunity", "Provenance") if name in headings]
    if forbidden:
        errors.append(f"forbidden sections present: {', '.join(forbidden)}")

    words = narrative_word_count(text)
    if words > 900:
        errors.append(f"narrative prose is {words} words; maximum is 900")

    target = _section(text, "Target evaluation design")
    rows: list[str] = []
    for line in target.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [_strip_emphasis(cell) for cell in line.strip().strip("|").split("|")]
        if cells and cells[0] in CANONICAL_NOUNS:
            rows.append(cells[0])
    if tuple(rows) != CANONICAL_NOUNS:
        errors.append(f"canonical-noun rows are {rows!r}; expected {list(CANONICAL_NOUNS)!r}")
    if "../../docs/specification.md#721-canonical-vocabulary" not in target:
        errors.append("Target evaluation design lacks the Section 7.2.1 relative link")

    prompt_section = _section(text, "Proposed generator prompt")
    prompt_match = re.search(r"^```(?:text)?\s*$\n(.*?)^```\s*$", prompt_section, re.MULTILINE | re.DOTALL)
    if not prompt_match:
        errors.append("Proposed generator prompt lacks one fenced prompt")
    else:
        prompt = prompt_match.group(1)
        for label, pattern in (
            ("status", r"\bSTATUS\b"),
            ("preconditions", r"\bPRECONDITIONS?\b"),
            ("Backstory", r"\bBackstor(?:y|ies)\b"),
            ("Props or no Props", r"\bProps?\b"),
            ("Scenes", r"\bScenes?\b"),
            ("Lines or offline inputs", r"\bLines?\b|\boffline inputs?\b"),
            ("authoring manifest", r"\bauthoring manifest\b"),
            ("proposed Ground truth", r"\bproposed Ground truth\b"),
            ("adopted v1 models", r"evals/synthetic_journals/models\.py"),
            (
                "deterministic package validator",
                r"evals/synthetic_journals/validate_package\.py",
            ),
        ):
            if not re.search(pattern, prompt, flags=re.IGNORECASE):
                errors.append(f"fenced prompt lacks {label} instructions")
        if "longitudinal_memory_retrieval" in selected_objective_ids:
            retrieval_requirements = (
                (
                    "longitudinal retrieval run configuration",
                    r"synthetic-journal-evaluation/run-configurations/"
                    r"longitudinal-memory-retrieval-10-to-1\.json",
                ),
                ("one relevant Prop", r"exactly one\b.*\brelevant\b.*\bProp"),
                ("ten distractor Props", r"\bten\b.*\bdistractor"),
                (
                    "shared 11-Prop bank",
                    r"\bshare\w*\b.*\b(?:same\b.*)?11\b.*\bProps?",
                ),
                (
                    "comparison with no relevant Props",
                    r"\bcomparison\b.*\bnone\b.*\brelevant",
                ),
                ("typed Prop relevance judgments", r"\bprop_relevance\b"),
            )
            for label, pattern in retrieval_requirements:
                if not re.search(
                    pattern, prompt, flags=re.IGNORECASE | re.DOTALL
                ):
                    errors.append(f"fenced prompt lacks {label}")
        if "reviewed_automatic_memory_capture" in selected_objective_ids:
            capture_path = (
                "synthetic-journal-evaluation/run-configurations/"
                "reviewed-automatic-memory-capture-10-to-1.json"
            )
            if capture_path not in prompt:
                errors.append(
                    "fenced prompt lacks reviewed automatic capture run configuration"
                )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--objective-id", action="append", default=[])
    args = parser.parse_args()
    errors = validate_report(args.report, tuple(args.objective_id))
    if errors:
        for error in errors:
            print(f"REPORT_VALIDATION_ERROR={error}", file=sys.stderr)
        return 1
    print(f"Report is valid: {args.report} ({narrative_word_count(args.report.read_text(encoding='utf-8'))} narrative words)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
