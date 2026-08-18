"""Generation contracts shared by every synthetic-journal persona."""

from __future__ import annotations

from pathlib import Path

from evals.synthetic_journals.contracts import (
    ChronologyPhase,
    JournalProfile,
    JournalVoice,
    PersonaInput,
    ReadingTrajectory,
    RealismPlan,
    RecurringThread,
)
from evals.synthetic_journals.generation import (
    annotation_prompt,
    build_chunk_requests,
    journal_chunk_prompt,
    profile_prompt,
)

ROOT = Path(__file__).resolve().parents[1]
PERSONA_DIRECTORY = ROOT / "data" / "synthetic-journals" / "personas"


def _personas() -> tuple[PersonaInput, ...]:
    return tuple(
        PersonaInput.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(PERSONA_DIRECTORY.glob("*/input.json"))
    )


def _profile(persona: PersonaInput) -> JournalProfile:
    history = persona.history_profile
    book = persona.reading_list[0]
    return JournalProfile(
        journal_profile_version=1,
        persona_id=persona.persona_id,
        voice=JournalVoice(
            first_person_characteristics=("concrete",),
            recurring_phrases_or_habits=(),
            avoid=("evaluation language",),
        ),
        everyday_context=("ordinary life",),
        recurring_threads=(
            RecurringThread(
                thread_id="thread-001",
                description="one recurring concern",
                starting_view="uncertain",
                possible_development="reconsidered later",
            ),
        ),
        reading_trajectory=(
            ReadingTrajectory(
                book_id=book.book_id,
                book_version_id=book.book_version_id,
                stages=("general reaction",),
            ),
        ),
        chronology=(
            ChronologyPhase(
                phase=1,
                start_date=history.start_date,
                end_date=history.start_date,
                continuity_notes=(),
                planned_beats=(),
            ),
        ),
        realism_plan=RealismPlan(
            short_or_fragmentary_entries=history.entry_length_mix.short,
            ordinary_or_low_stakes_entries=1,
            entries_without_a_closing_insight=1,
            repetition_or_unplanned_callbacks=(),
        ),
        continuity_invariants=("preserve the supplied biography",),
        stereotype_review_questions=("Did generation avoid demographic causation?",),
    )


def test_chunk_builder_covers_every_persona_without_special_cases() -> None:
    for persona in _personas():
        chunks = build_chunk_requests(persona)
        assert chunks[0].sequence_start == 1
        assert chunks[-1].sequence_end == persona.history_profile.entry_count
        assert sum(chunk.length_targets.total for chunk in chunks) == (
            persona.history_profile.entry_count
        )
        observed = {"short": 0, "medium": 0, "long": 0}
        for chunk in chunks:
            for name, count in chunk.length_targets.model_dump().items():
                observed[name] += count
        assert observed == persona.history_profile.entry_length_mix.model_dump()


def test_shared_prompts_render_without_hidden_variables() -> None:
    for persona in _personas():
        profile = _profile(persona)
        request = build_chunk_requests(persona)[0]
        rendered = (
            profile_prompt(persona),
            journal_chunk_prompt(
                persona=persona,
                profile=profile,
                prior_entries=(),
                request=request,
            ),
            annotation_prompt(
                persona=persona,
                profile=profile,
                entries=(),
            ),
        )
        assert all("{{" not in prompt for prompt in rendered)
        assert "Synthetic journal capture policy v1" in rendered[-1]
