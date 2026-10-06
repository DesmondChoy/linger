"""Typed contracts for Serendipity's offline review of its own component failures.

Serendipity reads its practice-case runs, names the most frequent failure, and
specifies exact edits to its connection-discovery instructions. Application
code applies the edits to a candidate copy and scores it; the model never
writes a file or changes the production skill.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import Field
from pydantic_ai import ModelRetry, RunContext

from src.linger.contracts.base import StrictModel

MAX_EDITS = 5
# A correction that rewrites the skill wholesale cannot be attributed to the
# failure it names, so the edit stays small relative to the instructions.
MAX_ADDED_WORDS = 400


class ObservedRun(StrictModel):
    """What one repetition of a case did, as the component grader saw it."""

    passed: bool
    status: str
    decline_reason: str | None = None
    searches: tuple[str, ...] = ()
    response: dict[str, Any] | None = None
    failures: tuple[str, ...] = ()


class CaseTrace(StrictModel):
    """One practice case: its task, evidence, expected result, and every run."""

    case_id: str
    behavior: str
    tier: str
    description: str
    task: dict[str, Any]
    evidence: tuple[dict[str, Any], ...]
    book_judgement: dict[str, Any] | None = None
    expected_searches: dict[str, Any]
    expected: dict[str, Any]
    passes: int = Field(ge=0)
    repeats: int = Field(ge=1)
    runs: tuple[ObservedRun, ...] = Field(min_length=1)


class FailureCategory(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    definition: str = Field(min_length=1)
    case_ids: tuple[str, ...] = Field(min_length=1)


class TraceNote(StrictModel):
    case_id: str
    note: str = Field(min_length=1, description="The first failure seen in this case's failing runs.")


class SkillEdit(StrictModel):
    """Replace one exact passage of the current instructions."""

    find: str = Field(min_length=1, description="Text copied exactly from the current instructions; it must occur once.")
    replace: str = Field(description="The new text. Empty deletes the passage.")
    reason: str = Field(min_length=1)


class EarlierRound(StrictModel):
    round: int = Field(ge=1)
    categories: tuple[FailureCategory, ...]
    target_category: str
    edits: tuple[SkillEdit, ...]
    expected_fixes: tuple[str, ...]
    practice_passes_before: int
    practice_passes_after: int
    practice_runs: int
    outcome: str


class SelfReviewInput(StrictModel):
    skill_name: str
    current_instructions: str = Field(min_length=1)
    cases: tuple[CaseTrace, ...] = Field(min_length=1)
    earlier_rounds: tuple[EarlierRound, ...] = ()


class SkillCorrection(StrictModel):
    notes: tuple[TraceNote, ...] = Field(min_length=1)
    categories: tuple[FailureCategory, ...] = Field(min_length=1, max_length=6)
    target_category: str
    diagnosis: str = Field(min_length=1, description="Why the current instructions produce the target failure.")
    edits: tuple[SkillEdit, ...] = Field(min_length=1, max_length=MAX_EDITS)
    expected_fixes: tuple[str, ...] = Field(min_length=1)
    at_risk: tuple[str, ...] = ()
    risks: str = Field(min_length=1)


def failing_case_ids(task: SelfReviewInput) -> set[str]:
    return {case.case_id for case in task.cases if case.passes < case.repeats}


def _words(text: str) -> int:
    return len(text.split())


def _leaked_identifiers(task: SelfReviewInput) -> set[str]:
    """Identifiers that would tie the instructions to particular test cases."""
    names = {case.case_id for case in task.cases}
    for case in task.cases:
        names.update(str(item["evidence_id"]) for item in case.evidence if "evidence_id" in item)
    return {name for name in names if not name.startswith(("http://", "https://"))}


def _find_pattern(find: str) -> re.Pattern[str]:
    """Match the quoted words exactly, but any run of whitespace between them.

    The instructions wrap at a fixed width, and a quoted passage rarely keeps
    the same line breaks; where a line breaks does not change what it says.
    """
    return re.compile(r"\s+".join(re.escape(word) for word in find.split()))


def apply_edits(instructions: str, edits: tuple[SkillEdit, ...]) -> str:
    """Apply non-overlapping replacements; raise when any edit is ambiguous."""
    spans: list[tuple[int, int, str]] = []
    for edit in edits:
        matches = list(_find_pattern(edit.find).finditer(instructions)) if edit.find.split() else []
        if len(matches) != 1:
            raise ValueError(f"edit text occurs {len(matches)} times, not once: {edit.find[:80]!r}")
        spans.append((matches[0].start(), matches[0].end(), edit.replace))
    spans.sort()
    for (_, end, _), (start, _, _) in zip(spans, spans[1:]):
        if start < end:
            raise ValueError("edits overlap")
    for start, end, replacement in reversed(spans):
        instructions = instructions[:start] + replacement + instructions[end:]
    return instructions


def correction_errors(correction: SkillCorrection, task: SelfReviewInput) -> list[str]:
    """Contract errors the model can repair within its own run."""
    errors: list[str] = []
    case_ids = {case.case_id for case in task.cases}
    failing = failing_case_ids(task)

    noted = [note.case_id for note in correction.notes]
    if missing := sorted(failing - set(noted)):
        errors.append(f"Write one note for every failing case; missing: {missing}.")
    if extra := sorted(set(noted) - failing):
        errors.append(f"Notes are for failing cases only; these passed every run: {extra}.")
    if len(noted) != len(set(noted)):
        errors.append("Write exactly one note per failing case.")

    categorised = {case_id for category in correction.categories for case_id in category.case_ids}
    if missing := sorted(failing - categorised):
        errors.append(f"Every failing case belongs to a category; uncategorised: {missing}.")
    if extra := sorted(categorised - failing):
        errors.append(f"Categories hold failing cases only; not failing: {extra}.")
    names = [category.name for category in correction.categories]
    if len(names) != len(set(names)):
        errors.append("Category names must be distinct.")
    if correction.target_category not in names:
        errors.append(f"target_category must be one of the category names: {names}.")

    if unknown := sorted(set(correction.expected_fixes) - failing):
        errors.append(f"expected_fixes must name failing practice cases; unknown or passing: {unknown}.")
    if unknown := sorted(set(correction.at_risk) - case_ids):
        errors.append(f"at_risk must name practice cases; unknown: {unknown}.")

    try:
        revised = apply_edits(task.current_instructions, correction.edits)
    except ValueError as error:
        errors.append(
            f"Each edit's find text must be copied exactly from current_instructions, occur once, "
            f"and not overlap another edit ({error})."
        )
    else:
        if revised == task.current_instructions:
            errors.append("The edits leave the instructions unchanged.")
        added = _words(revised) - _words(task.current_instructions)
        if added > MAX_ADDED_WORDS:
            errors.append(f"The edits add {added} words; keep the change under {MAX_ADDED_WORDS}.")

    new_text = "\n".join(edit.replace for edit in correction.edits)
    leaked = sorted(
        name for name in _leaked_identifiers(task)
        if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", new_text)
    )
    if leaked:
        errors.append(
            "Instructions must state general rules, not refer to evaluation cases or their "
            f"evidence identifiers: {leaked}."
        )
    return errors


def checked_correction(ctx: RunContext[Any], correction: SkillCorrection) -> SkillCorrection:
    """Return Serendipity's correction, or send its contract errors back for repair."""
    if not isinstance(ctx.prompt, str):
        raise ValueError("self-review requires the typed task prompt")
    errors = correction_errors(correction, SelfReviewInput.model_validate_json(ctx.prompt))
    if errors:
        raise ModelRetry("The correction breaks the application's contract:\n- " + "\n- ".join(errors))
    return correction
