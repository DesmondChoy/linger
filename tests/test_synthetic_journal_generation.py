"""Generation contracts shared by every synthetic-journal persona."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from evals.synthetic_journals.contracts import (
    AnnotationContext,
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
    assemble_annotations,
    build_chunk_requests,
    dataset_review_prompt,
    journal_chunk_prompt,
    merge_journal_chunks,
    profile_prompt,
    validate_journal_chunk_output,
    validate_profile_output,
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
                end_date=history.start_date + timedelta(days=history.span_days),
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
        assert sum(chunk.attachment_target for chunk in chunks) == (
            persona.history_profile.attachments.target_count
        )
        observed_events = {
            name: sum(
                getattr(chunk.event_targets, name)
                for chunk in chunks
            )
            for name in type(
                persona.history_profile.planned_event_counts
            ).model_fields
        }
        assert observed_events == (
            persona.history_profile.planned_event_counts.model_dump()
        )


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
                entries=(),
                context=AnnotationContext(
                    capture_enabled=True,
                    trusted_account_scope=True,
                    source_event_state="new",
                ),
            ),
            dataset_review_prompt(
                persona=persona,
                profile=profile,
                entries=(),
            ),
        )
        assert all("{{" not in prompt for prompt in rendered)
        assert "Synthetic journal capture policy v1" in rendered[-2]
        assert "planned_event_counts" not in rendered[-2]


def test_generated_profile_and_chunk_validate_without_model_authored_ids() -> None:
    persona = next(item for item in _personas() if item.persona_id == "idris-okafor")
    profile = validate_profile_output(_profile(persona).model_dump_json(), persona)
    request = build_chunk_requests(persona)[0]
    buckets = [
        name
        for name in ("short", "medium", "long")
        for _ in range(getattr(request.length_targets, name))
    ]
    ranges = persona.history_profile.entry_word_ranges
    entries = []
    for offset, bucket in enumerate(buckets):
        word_count = getattr(ranges, bucket).min_words
        entries.append(
            {
                "sequence": request.sequence_start + offset,
                "timestamp": (
                    request.earliest_timestamp + timedelta(hours=offset)
                ).isoformat(),
                "text": " ".join(f"word{index}" for index in range(word_count)),
                "attachments": [],
                "book_contexts": [],
            }
        )

    chunk = validate_journal_chunk_output(
        json.dumps({"entries": entries}),
        persona=persona,
        profile=profile,
        prior_entries=(),
        request=request,
    )

    assert [entry.entry_id for entry in chunk] == [
        f"entry-{sequence:03d}"
        for sequence in range(request.sequence_start, request.sequence_end + 1)
    ]
    assert all(not entry.attachments for entry in chunk)


def test_merge_rejects_a_partial_journal() -> None:
    persona = next(item for item in _personas() if item.persona_id == "idris-okafor")
    profile = _profile(persona)
    request = build_chunk_requests(persona)[0]
    buckets = [
        name
        for name in ("short", "medium", "long")
        for _ in range(getattr(request.length_targets, name))
    ]
    entries = [
        {
            "sequence": request.sequence_start + offset,
            "timestamp": (
                request.earliest_timestamp + timedelta(hours=offset)
            ).isoformat(),
            "text": " ".join(
                "word" for _ in range(
                    getattr(persona.history_profile.entry_word_ranges, bucket).min_words
                )
            ),
            "attachments": [],
            "book_contexts": [],
        }
        for offset, bucket in enumerate(buckets)
    ]
    chunk = validate_journal_chunk_output(
        json.dumps({"entries": entries}),
        persona=persona,
        profile=profile,
        prior_entries=(),
        request=request,
    )

    with pytest.raises(ValueError, match="entry count"):
        merge_journal_chunks(persona, (chunk,))


def test_annotation_assembly_derives_review_state_and_validates_event_coverage() -> None:
    persona = next(item for item in _personas() if item.persona_id == "idris-okafor")
    profile = _profile(persona)
    request = build_chunk_requests(persona)[0]
    ranges = persona.history_profile.entry_word_ranges
    buckets = [
        name
        for name in ("short", "medium", "long")
        for _ in range(getattr(request.length_targets, name))
    ]
    draft_entries = [
        {
            "sequence": request.sequence_start + offset,
            "timestamp": (
                request.earliest_timestamp + timedelta(hours=offset)
            ).isoformat(),
            "text": " ".join(
                "word" for _ in range(getattr(ranges, bucket).min_words)
            ),
            "attachments": [],
            "book_contexts": [],
        }
        for offset, bucket in enumerate(buckets)
    ]
    entries = validate_journal_chunk_output(
        json.dumps({"entries": draft_entries}),
        persona=persona,
        profile=profile,
        prior_entries=(),
        request=request,
    )
    annotation = {
        "entries": [
            {
                "entry_id": entry.entry_id,
                "hard_expectations": {
                    "muse_nomination": {
                        "outcome": "no_candidate",
                        "reason_codes": ["transient_or_low_signal"],
                        "candidate_text": None,
                    },
                    "provenance_capture": {
                        "outcome": "no_candidate",
                        "reason_codes": [],
                    },
                    "memory_policy": {
                        "outcome": "not_applicable",
                        "reason_code": "not_applicable",
                    },
                    "book_evidence_status": "not_applicable",
                },
                "soft_assessment": {
                    "durability": "low",
                    "review_notes": "Transient test entry.",
                },
            }
            for entry in entries
        ]
    }
    entry_ids = [entry.entry_id for entry in entries]
    coverage = {
        name: entry_ids[:count]
        for name, count in (
            persona.history_profile.planned_event_counts.model_dump().items()
        )
    }
    review = {
        "event_coverage": coverage,
        "relations": [],
        "dataset_review": {
            "policy_gaps": [],
            "continuity_failures": [],
            "stereotype_concerns": [],
            "entries_requiring_adjudication": [],
        },
    }

    result = assemble_annotations(
        persona=persona,
        entries=entries,
        context=AnnotationContext(
            capture_enabled=True,
            trusted_account_scope=True,
            source_event_state="new",
        ),
        annotation_text=json.dumps(annotation),
        review_text=json.dumps(review),
    )

    assert all(item.human_review == "pending" for item in result.entries)
    assert all(
        not item.hard_expectations.muse_nomination.candidate_spans
        for item in result.entries
    )

    disabled = AnnotationContext(
        capture_enabled=False,
        trusted_account_scope=True,
        source_event_state="new",
    )
    with pytest.raises(ValueError, match="disabled capture"):
        assemble_annotations(
            persona=persona,
            entries=entries,
            context=disabled,
            annotation_text=json.dumps(annotation),
            review_text=json.dumps(review),
        )

    for item in annotation["entries"]:
        item["hard_expectations"]["muse_nomination"]["reason_codes"] = [
            "automatic_capture_disabled"
        ]
    disabled_result = assemble_annotations(
        persona=persona,
        entries=entries,
        context=disabled,
        annotation_text=json.dumps(annotation),
        review_text=json.dumps(review),
    )
    assert all(
        item.hard_expectations.muse_nomination.reason_codes
        == ("automatic_capture_disabled",)
        for item in disabled_result.entries
    )
