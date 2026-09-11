from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


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

[Section 7.2.1](../../../docs/specification.md#721-canonical-vocabulary)

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
Write PACKAGE_DIRECTORY/backstory.json and the separate Ground truth file at
PACKAGE_DIRECTORY/ground-truth.json containing proposed Ground truth.
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
    path = tmp_path / "pre-generation-report.md"
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


def test_rejects_prompt_without_ground_truth_file(tmp_path: Path) -> None:
    text = report_text().replace(
        "Write PACKAGE_DIRECTORY/backstory.json and the separate Ground truth file at\n"
        "PACKAGE_DIRECTORY/ground-truth.json containing proposed Ground truth.\n",
        "Write PACKAGE_DIRECTORY/backstory.json.\n",
    )
    path = write_report(tmp_path, text)

    errors = validate_report(path)
    assert any("Ground truth file" in error for error in errors)
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


def test_accepts_capture_objective_mentioned_outside_prompt(tmp_path: Path) -> None:
    text = report_text(extra="reviewed_automatic_memory_capture")
    path = write_report(tmp_path, text)

    assert validate_report(path) == []


def test_requires_capture_configuration_only_when_selected(tmp_path: Path) -> None:
    path = write_report(tmp_path, report_text())

    errors = validate_report(path, ("reviewed_automatic_memory_capture",))

    assert any("automatic capture run configuration" in error for error in errors)


def test_requires_retrieval_configuration_for_selected_objective(
    tmp_path: Path,
) -> None:
    path = write_report(tmp_path, report_text())

    errors = validate_report(path, ("longitudinal_memory_retrieval",))

    assert any("longitudinal retrieval run configuration" in error for error in errors)
    assert any("ten distractor Props" in error for error in errors)


def test_accepts_complete_retrieval_configuration_prompt(tmp_path: Path) -> None:
    prompt = """
Use synthetic-journal-evaluation/generation-presets/longitudinal-memory-retrieval-10-to-1.json
and include its ID in
run_configuration_ids. Make the two retrieval Scenes share the same 11 active
Props. In the target Scene, exactly one relevant Prop and ten distractor Props
are available. In the comparison Scene, none of the Props is relevant. Record
every proposed judgment in GroundTruthProposal.prop_relevance.
"""
    path = write_report(tmp_path, report_text(prompt=prompt))

    assert validate_report(path, ("longitudinal_memory_retrieval",)) == []


def test_accepts_offline_inputs_without_lines(tmp_path: Path) -> None:
    text = report_text().replace(
        "Create one Backstory, no Props, three Scenes, and one Line per Scene.",
        "Create one Backstory, no Props, and three Scenes with offline inputs.",
    )
    path = write_report(tmp_path, text)

    assert validate_report(path) == []


def conversational_surfacing_report() -> str:
    return report_text(prompt="""
Objective: proactive_memory_surfacing. Stop until adopted repository contracts
represent the complete conversation workflow and its evaluation runner exists.
Current contracts only describe the offline component and cannot represent
this plan. Do not invent a schema, edit those contracts, or create any files
while these prerequisites remain unmet.

After those prerequisites and human approval, author one person's Backstory
and separately sourced Props for one evaluation account. An initial Scene
contains an update Line; later Scenes start fresh chats with natural Lines
while preserving the actual durable memory state. The application must review and capture
the update, review and apply curation, and make the resulting memory available
to a timely surfacing decision before Muse drafts and Provenance reviews the
reply for deterministic release. Runtime-created memories are outcomes, not
Props. Include negative contrasts for cancellation, repetition, weak support,
sensitive inference, and rejected capture or curation. Describe each expected
terminal response, source support, state change, and unchanged original.

Keep proposed Ground truth separate from the Backstory and all runtime inputs.
Anchor proposed labels to the adopted contract's Scene and source identifiers
and exact spans. Do not grade recorded behavior or claim label adoption.
""").replace(
        "Create one Backstory, no Props, three Scenes, and one Line per Scene.",
        "Plan one Backstory with Props and conversational Scenes containing Lines.",
    )


def test_accepts_blocked_conversational_surfacing_target(tmp_path: Path) -> None:
    text = conversational_surfacing_report()
    path = write_report(tmp_path, text)

    assert validate_report(path, ("proactive_memory_surfacing",)) == []


@pytest.mark.parametrize(
    ("omitted", "error_label"),
    [
        ("evals/synthetic_journals/models.py", "package models"),
        (
            "evals/synthetic_journals/validate_package.py",
            "deterministic package validator",
        ),
        ("PACKAGE_DIRECTORY/ground-truth.json", "package Ground truth path"),
    ],
)
def test_blocked_surfacing_prompt_still_requires_shared_package_contract(
    tmp_path: Path, omitted: str, error_label: str
) -> None:
    text = conversational_surfacing_report().replace(omitted, "omitted")
    path = write_report(tmp_path, text)

    errors = validate_report(path, ("proactive_memory_surfacing",))

    assert any(error_label in error for error in errors)


def test_rejects_prompt_without_sibling_package_paths(tmp_path: Path) -> None:
    text = report_text().replace(
        "PACKAGE_DIRECTORY/backstory.json",
        "backstory.json",
    )
    path = write_report(tmp_path, text)

    assert any("package Backstory path" in error for error in validate_report(path))


def test_rejects_bad_filename(tmp_path: Path) -> None:
    path = tmp_path / "2026-08-22T120000+0800-pre-generation-report.md"
    path.write_text(report_text(), encoding="utf-8")

    assert any("filename" in error for error in validate_report(path))
