"""Typed contract for Sculptor's offline chapter-cue revision."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import Field

from src.linger.contracts.base import StrictModel


class ChapterCues(StrictModel):
    """Reviewed reading aids that search reads beside every passage of a chapter."""

    chapter_number: int = Field(ge=1)
    routing_description: str = Field(min_length=1)
    characters: tuple[str, ...]
    retrieval_cues: tuple[str, ...] = Field(min_length=1)

    @property
    def word_count(self) -> int:
        return sum(
            len(text.split())
            for text in (self.routing_description, *self.characters, *self.retrieval_cues)
        )


class CueChapter(StrictModel):
    chapter_number: int = Field(ge=1)
    title: str
    text: str
    cues: ChapterCues


class PracticeOutcome(StrictModel):
    need_id: str
    question: str
    target_chapter: int = Field(ge=1)
    reached: bool
    chapters_returned: tuple[int, ...] = Field(
        description="Chapters of the passages search returned, best first."
    )


class CueRound(StrictModel):
    label: str
    failure_patterns: tuple[str, ...] = Field(
        default=(), description="Patterns Sculptor named when it wrote this round's cues."
    )
    outcomes: tuple[PracticeOutcome, ...]


class ChapterCueRevisionInput(StrictModel):
    book_title: str
    word_budget: int = Field(ge=1, description="Maximum words per chapter across all cue fields.")
    chapters: tuple[CueChapter, ...] = Field(min_length=1)
    rounds: tuple[CueRound, ...] = Field(
        min_length=1, description="Practice outcomes, oldest first; the last used the current cues."
    )


class ChapterCueRevision(StrictModel):
    failure_patterns: tuple[str, ...] = Field(min_length=1, max_length=6)
    chapters: tuple[ChapterCues, ...] = Field(min_length=1)


class InvalidChapterCueRevision(ValueError):
    """The proposal breaks the application's coverage or budget contract."""


def chapter_cue_errors(
    revision: ChapterCueRevision, chapter_numbers: Sequence[int], word_budget: int,
) -> list[str]:
    """Check coverage, budget, and nonempty aids for a proposal or an approved revision."""
    received = [chapter.chapter_number for chapter in revision.chapters]
    errors = []
    if sorted(received) != sorted(chapter_numbers):
        errors.append(
            f"Revise every chapter exactly once: expected {sorted(chapter_numbers)}, received {received}."
        )
    for chapter in revision.chapters:
        if chapter.word_count > word_budget:
            errors.append(
                f"Chapter {chapter.chapter_number} uses {chapter.word_count} words; "
                f"the budget is {word_budget}."
            )
        texts = (chapter.routing_description, *chapter.characters, *chapter.retrieval_cues)
        if any(not text.strip() for text in texts):
            errors.append(f"Chapter {chapter.chapter_number} has an empty description, character, or cue.")
    return errors


def task_errors(revision: ChapterCueRevision, task: ChapterCueRevisionInput) -> list[str]:
    return chapter_cue_errors(
        revision, [chapter.chapter_number for chapter in task.chapters], task.word_budget,
    )
