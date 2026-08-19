"""Persona-neutral prompt assembly for synthetic journal generation."""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Mapping

from src.linger.contracts.librarian import EvidenceRecord

from .contracts import (
    AnnotationContext,
    AnnotationDraft,
    Attachment,
    CandidateSpan,
    ChunkRequest,
    DatasetReviewDraft,
    EntryLengthMix,
    EntryAnnotation,
    EntryRelation,
    HardExpectations,
    JournalAnnotations,
    JournalChunkDraft,
    JournalEntry,
    JournalEntries,
    JournalProfile,
    MuseNominationExpectation,
    PersonaInput,
    PlannedEventCounts,
    classify_entry_length,
    json_text,
    validate_annotation,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_DIRECTORY = REPO_ROOT / "prompts" / "synthetic-journals"
CAPTURE_POLICY_PATH = (
    REPO_ROOT
    / "data"
    / "synthetic-journals"
    / "policies"
    / "capture-policy-v1.md"
)
_PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def build_chunk_requests(persona: PersonaInput) -> tuple[ChunkRequest, ...]:
    """Build deterministic chunk boundaries from any conforming persona input."""
    profile = persona.history_profile
    schedule = _length_schedule(profile.entry_length_mix)
    chunk_count = math.ceil(profile.entry_count / profile.generation_chunk_size)
    chunk_sizes = tuple(
        min(
            profile.generation_chunk_size,
            profile.entry_count - offset * profile.generation_chunk_size,
        )
        for offset in range(chunk_count)
    )
    attachment_targets = _allocate_total(profile.attachments.target_count, chunk_sizes)
    event_targets = _event_targets(profile.planned_event_counts, chunk_count)
    requests: list[ChunkRequest] = []
    for chunk_offset in range(chunk_count):
        sequence_start = chunk_offset * profile.generation_chunk_size + 1
        sequence_end = min(
            profile.entry_count,
            sequence_start + profile.generation_chunk_size - 1,
        )
        lengths = Counter(schedule[sequence_start - 1 : sequence_end])
        first_day = (sequence_start - 1) * profile.span_days // profile.entry_count
        last_day = sequence_end * profile.span_days // profile.entry_count
        requests.append(
            ChunkRequest(
                chunk_request_version=1,
                chunk_index=chunk_offset + 1,
                sequence_start=sequence_start,
                sequence_end=sequence_end,
                earliest_timestamp=datetime.combine(
                    profile.start_date + timedelta(days=first_day),
                    time(hour=8),
                    tzinfo=UTC,
                ),
                latest_timestamp=datetime.combine(
                    profile.start_date + timedelta(days=last_day),
                    time(hour=22),
                    tzinfo=UTC,
                ),
                length_targets=EntryLengthMix(
                    short=lengths["short"],
                    medium=lengths["medium"],
                    long=lengths["long"],
                ),
                attachment_target=attachment_targets[chunk_offset],
                event_targets=event_targets[chunk_offset],
            )
        )
    return tuple(requests)


def profile_prompt(persona: PersonaInput) -> str:
    """Render the shared profile prompt for one validated persona."""
    return _render(
        "01-create-journal-profile.md",
        {"PERSONA_INPUT_JSON": json_text(persona)},
    )


def journal_chunk_prompt(
    *,
    persona: PersonaInput,
    profile: JournalProfile,
    prior_entries: tuple[JournalEntry, ...],
    request: ChunkRequest,
    evidence: tuple[EvidenceRecord, ...] = (),
) -> str:
    """Render one chronological chunk prompt with typed, corpus-backed inputs."""
    return _render(
        "02-generate-journal-entries.md",
        {
            "PERSONA_INPUT_JSON": json_text(persona),
            "JOURNAL_PROFILE_JSON": json_text(profile),
            "PRIOR_ENTRIES_JSON": json_text(prior_entries),
            "CHUNK_REQUEST_JSON": json_text(request),
            "LIBRARIAN_EVIDENCE_RECORDS_JSON": json_text(evidence),
        },
    )


def annotation_prompt(
    *,
    entries: tuple[JournalEntry, ...],
    context: AnnotationContext,
    evidence: tuple[EvidenceRecord, ...] = (),
) -> str:
    """Render entry labels without exposing persona quotas or authoring intent."""
    policy = CAPTURE_POLICY_PATH.read_text(encoding="utf-8")
    return _render(
        "03-annotate-journal-entries.md",
        {
            "JOURNAL_ENTRIES_JSON": json_text(entries),
            "ANNOTATION_CONTEXT_JSON": json_text(context),
            "CAPTURE_POLICY_CONTRACT": policy,
            "LIBRARIAN_EVIDENCE_RECORDS_JSON": json_text(evidence),
        },
    )


def dataset_review_prompt(
    *,
    persona: PersonaInput,
    profile: JournalProfile,
    entries: tuple[JournalEntry, ...],
) -> str:
    """Render a holistic review that cannot influence entry-level labels."""
    return _render(
        "04-review-journal-dataset.md",
        {
            "PERSONA_INPUT_JSON": json_text(persona),
            "JOURNAL_PROFILE_JSON": json_text(profile),
            "JOURNAL_ENTRIES_JSON": json_text(entries),
        },
    )


def validate_profile_output(text: str, persona: PersonaInput) -> JournalProfile:
    """Validate one generated profile against its authoritative persona input."""
    profile = JournalProfile.model_validate_json(text)
    if profile.persona_id != persona.persona_id:
        raise ValueError("journal profile belongs to another persona")
    expected_books = {
        (book.book_id, book.book_version_id) for book in persona.reading_list
    }
    observed_books = {
        (book.book_id, book.book_version_id) for book in profile.reading_trajectory
    }
    if observed_books != expected_books:
        raise ValueError("journal profile reading trajectory must match the reading list")
    history = persona.history_profile
    if profile.realism_plan.short_or_fragmentary_entries != history.entry_length_mix.short:
        raise ValueError("journal profile short-entry target differs from the persona input")
    if profile.chronology[0].start_date != history.start_date:
        raise ValueError("journal profile chronology must begin on the persona start date")
    expected_end = history.start_date + timedelta(days=history.span_days)
    if profile.chronology[-1].end_date != expected_end:
        raise ValueError("journal profile chronology must cover the complete date range")
    return profile


def validate_journal_chunk_output(
    text: str,
    *,
    persona: PersonaInput,
    profile: JournalProfile,
    prior_entries: tuple[JournalEntry, ...],
    request: ChunkRequest,
) -> tuple[JournalEntry, ...]:
    """Validate one model chunk and assign stable entry and attachment IDs."""
    if profile.persona_id != persona.persona_id:
        raise ValueError("journal profile belongs to another persona")
    expected_start = 1 if not prior_entries else prior_entries[-1].sequence + 1
    if request.sequence_start != expected_start:
        raise ValueError("journal chunk request must begin after accepted prior entries")
    draft = JournalChunkDraft.model_validate_json(text)
    expected_sequences = list(range(request.sequence_start, request.sequence_end + 1))
    if [entry.sequence for entry in draft.entries] != expected_sequences:
        raise ValueError("journal chunk does not match the requested sequence range")
    timestamps = [entry.timestamp for entry in draft.entries]
    if timestamps != sorted(timestamps):
        raise ValueError("journal chunk timestamps must be chronological")
    if prior_entries and timestamps[0] < prior_entries[-1].timestamp:
        raise ValueError("journal chunk begins before the accepted prior entries")

    observed_lengths = Counter()
    observed_attachments = 0
    allowed_books = {
        (book.book_id, book.book_version_id) for book in persona.reading_list
    }
    next_attachment = 1 + sum(len(entry.attachments) for entry in prior_entries)
    entries: list[JournalEntry] = []
    for draft_entry in draft.entries:
        if not request.earliest_timestamp <= draft_entry.timestamp <= request.latest_timestamp:
            raise ValueError(
                f"entry-{draft_entry.sequence:03d} is outside the requested timestamp window"
            )
        observed_lengths[
            classify_entry_length(draft_entry.text, persona.history_profile.entry_word_ranges)
        ] += 1
        observed_attachments += len(draft_entry.attachments)
        if any(
            attachment.kind not in persona.history_profile.attachments.allowed_kinds
            for attachment in draft_entry.attachments
        ):
            raise ValueError(f"entry-{draft_entry.sequence:03d} uses a forbidden attachment")
        if any(
            (context.book_id, context.book_version_id) not in allowed_books
            for context in draft_entry.book_contexts
        ):
            raise ValueError(f"entry-{draft_entry.sequence:03d} uses an unlisted book")
        for context in draft_entry.book_contexts:
            if context.declared_position and context.declared_position not in draft_entry.text:
                raise ValueError("declared reading positions must be exact text slices")

        attachments = tuple(
            Attachment(
                attachment_id=f"attachment-{index:03d}",
                kind=attachment.kind,
                description=attachment.description,
            )
            for index, attachment in enumerate(
                draft_entry.attachments,
                start=next_attachment,
            )
        )
        next_attachment += len(attachments)
        entries.append(
            JournalEntry(
                entry_id=f"entry-{draft_entry.sequence:03d}",
                sequence=draft_entry.sequence,
                timestamp=draft_entry.timestamp,
                text=draft_entry.text,
                attachments=attachments,
                book_contexts=draft_entry.book_contexts,
            )
        )

    if dict(observed_lengths) != {
        name: count
        for name, count in request.length_targets.model_dump().items()
        if count
    }:
        raise ValueError("journal chunk does not match its requested length targets")
    if observed_attachments != request.attachment_target:
        raise ValueError("journal chunk does not match its attachment target")
    return tuple(entries)


def merge_journal_chunks(
    persona: PersonaInput,
    chunks: tuple[tuple[JournalEntry, ...], ...],
) -> JournalEntries:
    """Merge validated chunks and enforce the complete persona contract."""
    entries = tuple(entry for chunk in chunks for entry in chunk)
    journal = JournalEntries(
        journal_dataset_version=1,
        persona_id=persona.persona_id,
        entries=entries,
    )
    history = persona.history_profile
    if len(entries) != history.entry_count or entries[0].sequence != 1:
        raise ValueError("complete journal does not cover the requested entry count")
    lengths = Counter(
        classify_entry_length(entry.text, history.entry_word_ranges) for entry in entries
    )
    if {name: lengths[name] for name in ("short", "medium", "long")} != (
        history.entry_length_mix.model_dump()
    ):
        raise ValueError("complete journal does not match the requested length mix")
    if sum(len(entry.attachments) for entry in entries) != history.attachments.target_count:
        raise ValueError("complete journal does not match the requested attachment count")
    return journal


def assemble_annotations(
    *,
    persona: PersonaInput,
    entries: tuple[JournalEntry, ...],
    context: AnnotationContext,
    annotation_text: str,
    review_text: str,
) -> JournalAnnotations:
    """Derive exact spans and merge isolated labels with holistic review output."""
    annotation = AnnotationDraft.model_validate_json(annotation_text)
    review = DatasetReviewDraft.model_validate_json(review_text)
    entry_ids = [entry.entry_id for entry in entries]
    if [item.entry_id for item in annotation.entries] != entry_ids:
        raise ValueError("annotation output must cover entries once and in order")
    _validate_event_coverage(persona, review, set(entry_ids))

    relations_by_entry: dict[str, list[EntryRelation]] = {
        entry_id: [] for entry_id in entry_ids
    }
    sequence_by_id = {entry.entry_id: entry.sequence for entry in entries}
    for relation in review.relations:
        if (
            relation.entry_id not in sequence_by_id
            or relation.target_entry_id not in sequence_by_id
        ):
            raise ValueError("dataset relation references an unknown entry")
        if sequence_by_id[relation.target_entry_id] >= sequence_by_id[relation.entry_id]:
            raise ValueError("dataset relations must target earlier entries")
        relations_by_entry[relation.entry_id].append(
            EntryRelation(
                target_entry_id=relation.target_entry_id,
                relation=relation.relation,
            )
        )

    final_entries: list[EntryAnnotation] = []
    for entry, draft in zip(entries, annotation.entries, strict=True):
        nomination = draft.hard_expectations.muse_nomination
        spans: tuple[CandidateSpan, ...] = ()
        if nomination.outcome == "candidate":
            candidate = nomination.candidate_text
            if not candidate:
                raise ValueError(f"{entry.entry_id} candidate is missing exact text")
            start = entry.text.find(candidate)
            if start < 0 or start != entry.text.rfind(candidate):
                raise ValueError(
                    f"{entry.entry_id} candidate text must occur exactly once"
                )
            spans = (
                CandidateSpan(
                    start_codepoint=start,
                    end_codepoint=start + len(candidate),
                    text=candidate,
                ),
            )
        elif nomination.candidate_text is not None:
            raise ValueError(f"{entry.entry_id} non-candidate must use null candidate text")

        hard = HardExpectations(
            muse_nomination=MuseNominationExpectation(
                outcome=nomination.outcome,
                reason_codes=nomination.reason_codes,
                candidate_spans=spans,
            ),
            provenance_capture=draft.hard_expectations.provenance_capture,
            memory_policy=draft.hard_expectations.memory_policy,
            book_evidence_status=draft.hard_expectations.book_evidence_status,
        )
        _validate_contextual_outcome(hard, context)
        final = EntryAnnotation(
            entry_id=entry.entry_id,
            hard_expectations=hard,
            relations=tuple(relations_by_entry[entry.entry_id]),
            soft_assessment=draft.soft_assessment,
            human_review="pending",
        )
        validate_annotation(entry, final, set(entry_ids))
        final_entries.append(final)

    if any(
        entry_id not in set(entry_ids)
        for entry_id in review.dataset_review.entries_requiring_adjudication
    ):
        raise ValueError("dataset review adjudication list contains an unknown entry")
    return JournalAnnotations(
        annotation_version=1,
        capture_policy_version=1,
        persona_id=persona.persona_id,
        entries=tuple(final_entries),
        dataset_review=review.dataset_review,
    )


def _render(filename: str, variables: Mapping[str, str]) -> str:
    template = (PROMPT_DIRECTORY / filename).read_text(encoding="utf-8")
    expected = set(_PLACEHOLDER.findall(template))
    supplied = set(variables)
    if supplied != expected:
        missing = sorted(expected - supplied)
        extra = sorted(supplied - expected)
        raise ValueError(f"prompt variable mismatch: missing={missing}, extra={extra}")
    rendered = template
    for name, value in variables.items():
        rendered = rendered.replace(f"{{{{{name}}}}}", value)
    if _PLACEHOLDER.search(rendered):
        raise ValueError("rendered prompt contains an unresolved variable")
    return rendered


def _length_schedule(mix: EntryLengthMix) -> tuple[str, ...]:
    """Spread length buckets across the history without persona-specific order."""
    remaining = mix.model_dump()
    total = mix.total
    schedule: list[str] = []
    preference = {"medium": 2, "short": 1, "long": 0}
    while len(schedule) < total:
        slots = total - len(schedule)
        available = [name for name, count in remaining.items() if count]
        chosen = max(
            available,
            key=lambda name: (remaining[name] / slots, preference[name]),
        )
        schedule.append(chosen)
        remaining[chosen] -= 1
    return tuple(schedule)


def _allocate_total(total: int, capacities: tuple[int, ...]) -> tuple[int, ...]:
    """Distribute a bounded total across chunks without exceeding chunk size."""
    allocations = [0] * len(capacities)
    for _ in range(total):
        available = [
            index
            for index, capacity in enumerate(capacities)
            if allocations[index] < capacity
        ]
        if not available:
            raise ValueError("requested total exceeds chunk capacity")
        chosen = min(
            available,
            key=lambda index: (allocations[index] / capacities[index], index),
        )
        allocations[chosen] += 1
    return tuple(allocations)


def _event_targets(
    totals: PlannedEventCounts,
    chunk_count: int,
) -> tuple[PlannedEventCounts, ...]:
    """Spread authoring events while keeping dependent events after chunk one."""
    by_chunk = [
        {name: 0 for name in type(totals).model_fields}
        for _ in range(chunk_count)
    ]
    requires_prior_context = {
        "later_updates",
        "corrections",
        "deletion_requests",
        "near_duplicates",
        "reconnect_queries",
    }
    for name, total in totals.model_dump().items():
        eligible = list(range(chunk_count))
        if name in requires_prior_context and chunk_count > 1:
            eligible = eligible[1:]
        for offset in range(total):
            index = eligible[offset % len(eligible)]
            by_chunk[index][name] += 1
    return tuple(PlannedEventCounts(**values) for values in by_chunk)


def _validate_event_coverage(
    persona: PersonaInput,
    review: DatasetReviewDraft,
    entry_ids: set[str],
) -> None:
    expected = persona.history_profile.planned_event_counts.model_dump()
    observed = review.event_coverage.model_dump()
    for name, expected_count in expected.items():
        covered = observed[name]
        if len(covered) != expected_count:
            raise ValueError(
                f"event coverage for {name} has {len(covered)} entries; "
                f"expected {expected_count}"
            )
        if len(covered) != len(set(covered)):
            raise ValueError(f"event coverage for {name} repeats an entry")
        if any(entry_id not in entry_ids for entry_id in covered):
            raise ValueError(f"event coverage for {name} references an unknown entry")


def _validate_contextual_outcome(
    hard: HardExpectations,
    context: AnnotationContext,
) -> None:
    """Check deterministic stage outcomes against the declared replay context."""
    nomination = hard.muse_nomination.outcome
    provenance = hard.provenance_capture
    memory = hard.memory_policy
    if not context.capture_enabled:
        if (
            nomination != "no_candidate"
            or hard.muse_nomination.reason_codes != ("automatic_capture_disabled",)
            or provenance.outcome != "no_candidate"
            or memory.outcome != "not_applicable"
        ):
            raise ValueError("disabled capture must stop at Muse without a candidate")
        return
    if nomination != "candidate":
        return
    if not context.trusted_account_scope:
        if provenance.outcome != "reject_capture" or "boundary_violation" not in (
            provenance.reason_codes
        ):
            raise ValueError("untrusted account scope requires a boundary rejection")
        return
    if provenance.outcome != "allow_capture":
        return
    if context.source_event_state == "conflict":
        expected = ("refuse", "source_event_conflict")
    else:
        expected = ("commit", None)
    if (memory.outcome, memory.reason_code) != expected:
        raise ValueError("memory expectation contradicts the annotation context")
