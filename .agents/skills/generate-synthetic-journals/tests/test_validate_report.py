from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_report.py"
SPEC = importlib.util.spec_from_file_location("validate_report", SCRIPT)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)

CANONICAL_NOUNS = validator.CANONICAL_NOUNS
narrative_word_count = validator.narrative_word_count
validate_report = validator.validate_report


def report_text(*, prompt: str = "", extra: str = "") -> str:
    noun_rows = "\n".join(f"| {noun} | use |" for noun in CANONICAL_NOUNS)
    return f"""# Report

## Decision

Insufficient.

## Your selection

- One.

## Target evaluation design

[Section 7.2.1](../../docs/specification.md#721-canonical-vocabulary)

| Noun | Use |
|---|---|
{noun_rows}

## Current implementation and required work

Observed. Proposed. Assumed.

## Expected behavior and evaluation

One Line has a likely response and success check.

## Proposed generator prompt

```text
STATUS: Target state — do not run.
PRECONDITIONS: contract adopted.
Create one Backstory, no Props, three Scenes, and one Line per Scene.
Write a separate authoring manifest containing proposed Ground truth.
Use evals/synthetic_journals/models.py and validate with
evals/synthetic_journals/validate_package.py.
{prompt}
```

## Ground truth lifecycle

Validate objective facts, then adopt independently.

## Architecture and academic relevance

Authority remains separate.

> **Human decision required:** approve, revise, or abandon.
{extra}
"""


def write_report(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "2026-08-22T120000+0800-pre-generation-report.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_report_passes(tmp_path: Path) -> None:
    path = write_report(tmp_path, report_text())

    assert validate_report(path) == []


def test_narrative_count_excludes_headings_tables_and_fences() -> None:
    text = "# heading words\n| table words | ignored |\n```text\nfenced words\n```\ncount these"

    assert narrative_word_count(text) == 2


def test_rejects_excess_narrative(tmp_path: Path) -> None:
    path = write_report(tmp_path, report_text(extra="word " * 901))

    assert any("maximum is 900" in error for error in validate_report(path))


def test_rejects_prompt_without_authoring_manifest(tmp_path: Path) -> None:
    text = report_text().replace(
        "Write a separate authoring manifest containing proposed Ground truth.\n",
        "",
    )
    path = write_report(tmp_path, text)

    errors = validate_report(path)
    assert any("authoring manifest" in error for error in errors)
    assert any("proposed Ground truth" in error for error in errors)


def test_rejects_prompt_without_adopted_package_validator(tmp_path: Path) -> None:
    text = report_text().replace(
        "evals/synthetic_journals/validate_package.py.",
        "an unspecified validator.",
    )
    path = write_report(tmp_path, text)

    assert any(
        "deterministic package validator" in error
        for error in validate_report(path)
    )


def test_capture_prompt_requires_resolved_run_configuration(tmp_path: Path) -> None:
    text = report_text(extra="reviewed_automatic_memory_capture")
    path = write_report(tmp_path, text)

    assert any("1:10 run configuration" in error for error in validate_report(path))

    config_path = (
        "synthetic-journal-evaluation/run-configurations/"
        "reviewed-automatic-memory-capture-10-to-1.json"
    )
    text = report_text(
        prompt=f"Use the resolved run configuration at {config_path}.",
        extra="reviewed_automatic_memory_capture",
    )
    path = write_report(tmp_path, text)

    assert validate_report(path) == []


def test_accepts_offline_inputs_without_lines(tmp_path: Path) -> None:
    text = report_text().replace(
        "Create one Backstory, no Props, three Scenes, and one Line per Scene.",
        "Create one Backstory, no Props, and three Scenes with offline inputs.",
    )
    path = write_report(tmp_path, text)

    assert validate_report(path) == []


def test_rejects_bad_filename(tmp_path: Path) -> None:
    path = tmp_path / "report.md"
    path.write_text(report_text(), encoding="utf-8")

    assert any("filename" in error for error in validate_report(path))
