"""Typed contracts for Sculptor's offline retrieval error analysis and research."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from src.linger.contracts.base import StrictModel


class TracePassage(StrictModel):
    evidence_id: str
    chapter: int
    selected: bool | None = None
    text: str


class RetrievalTrace(StrictModel):
    """What retrieval did for one practice need; held-back needs are never traced."""

    need_id: str
    question: str
    answering_chapter: int
    passed: bool
    plan: dict[str, Any]
    librarian_judgement: str
    librarian_reason: str | None
    librarian_limitations: list[str] | str
    librarian_error: str | None
    search_queries: list[str]
    passages_returned: list[TracePassage]
    search_steps: list[dict[str, Any]]
    answer_passages: list[TracePassage] = []
    answer_ranks: list[dict[str, Any]] | str = []


class ChapterTags(StrictModel):
    routing_description: str
    characters: list[str]
    retrieval_cues: list[str]


class FailureCategory(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    definition: str = Field(min_length=1)
    need_ids: tuple[str, ...] = Field(min_length=1)


class TraceNote(StrictModel):
    need_id: str
    passed: bool
    note: str = Field(description="The first failure seen in this trace; empty only for a clean pass.")


class EarlierRound(StrictModel):
    round: int
    categories: tuple[FailureCategory, ...]
    specification: dict[str, Any]
    practice_passed: int
    practice_total: int


class ErrorAnalysisInput(StrictModel):
    book_title: str
    retrieval_description: str
    chapter_tags: dict[int, ChapterTags]
    traces: tuple[RetrievalTrace, ...] = Field(min_length=1)
    earlier_rounds: tuple[EarlierRound, ...] = ()


class ErrorAnalysis(StrictModel):
    notes: tuple[TraceNote, ...] = Field(min_length=1)
    categories: tuple[FailureCategory, ...] = Field(max_length=6)


class ResearchInput(StrictModel):
    book_title: str
    retrieval_description: str
    chapter_tags: dict[int, ChapterTags]
    traces: tuple[RetrievalTrace, ...] = Field(min_length=1)
    error_analysis: ErrorAnalysis
    earlier_rounds: tuple[EarlierRound, ...] = ()
    max_searches: int = Field(ge=1)
    max_pages: int = Field(ge=1)


class Source(StrictModel):
    url: str
    title: str
    supports: str = Field(min_length=1, description="What this page shows that the approach relies on.")


class ResearchSpecification(StrictModel):
    target_category: str
    problem: str = Field(min_length=1)
    approach: str = Field(min_length=1)
    sources: tuple[Source, ...] = Field(min_length=1)
    retrieval_changes: tuple[str, ...] = Field(min_length=1)
    sculptor_data: str | None = Field(
        description="What Sculptor will write and tune for this approach, or null when it writes nothing."
    )
    expected_fixes: tuple[str, ...] = Field(min_length=1)
    risks: tuple[str, ...] = Field(min_length=1)
    test_plan: str = Field(min_length=1)
    limits_check: str = Field(min_length=1, description="How the approach keeps every fixed limit.")


def error_analysis_errors(analysis: ErrorAnalysis, task: ErrorAnalysisInput) -> list[str]:
    outcomes = {trace.need_id: trace.passed for trace in task.traces}
    noted = [note.need_id for note in analysis.notes]
    failed = {need_id for need_id, passed in outcomes.items() if not passed}
    errors = []
    if sorted(noted) != sorted(outcomes):
        errors.append(f"Write exactly one note per trace: expected {sorted(outcomes)}, received {noted}.")
    for note in analysis.notes:
        if note.need_id in outcomes and note.passed != outcomes[note.need_id]:
            errors.append(f"{note.need_id}: the trace {'passed' if outcomes[note.need_id] else 'failed'}.")
        if not note.passed and not note.note.strip():
            errors.append(f"{note.need_id}: a failed trace needs a note.")
    categorised = {need_id for category in analysis.categories for need_id in category.need_ids}
    if categorised - failed:
        errors.append(f"Categories may list only failed needs; remove {sorted(categorised - failed)}.")
    if failed - categorised:
        errors.append(f"Put every failed need in a category; missing {sorted(failed - categorised)}.")
    return errors


def specification_errors(
    specification: ResearchSpecification, task: ResearchInput, opened_urls: set[str],
) -> list[str]:
    categories = {category.name for category in task.error_analysis.categories}
    failed = {trace.need_id for trace in task.traces if not trace.passed}
    errors = []
    if specification.target_category not in categories:
        errors.append(f"Target one approved category exactly: {sorted(categories)}.")
    unread = [source.url for source in specification.sources if source.url not in opened_urls]
    if unread:
        errors.append(f"Cite only pages you opened with get_page in this run; not opened: {unread}.")
    if set(specification.expected_fixes) - failed:
        errors.append(f"Expected fixes must be failed practice needs: {sorted(failed)}.")
    return errors
