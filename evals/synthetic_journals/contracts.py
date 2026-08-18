"""Typed contracts for generated journal datasets and replay manifests."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from src.linger.contracts.librarian import EvidenceRecord

_ENTRY_ID = re.compile(r"^entry-(\d{3})$")
_WORD = re.compile(r"[\w]+(?:[’'-][\w]+)*", re.UNICODE)


class StrictModel(BaseModel):
    """Reject accidental drift in generated and reviewed artifacts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class PersonaBackground(StrictModel):
    demographics: tuple[str, ...]
    occupation: str
    life_context: tuple[str, ...]
    reading_habits: tuple[str, ...]
    voice_notes: tuple[str, ...]
    recurring_themes: tuple[str, ...]
    guardrails: tuple[str, ...]


class ReadingListItem(StrictModel):
    book_id: str = Field(min_length=1)
    book_version_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    author: str = Field(min_length=1)
    interest: str = Field(min_length=1)


class EntryLengthMix(StrictModel):
    short: int = Field(ge=0)
    medium: int = Field(ge=0)
    long: int = Field(ge=0)

    @property
    def total(self) -> int:
        return self.short + self.medium + self.long


class WordRange(StrictModel):
    min_words: int = Field(ge=1)
    max_words: int = Field(ge=1)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.max_words < self.min_words:
            raise ValueError("max_words must be at least min_words")
        return self


class EntryWordRanges(StrictModel):
    short: WordRange
    medium: WordRange
    long: WordRange

    @model_validator(mode="after")
    def contiguous(self) -> Self:
        if self.short.max_words + 1 != self.medium.min_words:
            raise ValueError("short and medium word ranges must be contiguous")
        if self.medium.max_words + 1 != self.long.min_words:
            raise ValueError("medium and long word ranges must be contiguous")
        return self


class PlannedEventCounts(StrictModel):
    durable_reflections: int = Field(ge=0)
    explicit_preferences_or_intentions: int = Field(ge=0)
    concrete_incidents: int = Field(ge=0)
    later_updates: int = Field(ge=0)
    unrelated_notes: int = Field(ge=0)
    transient_notes: int = Field(ge=0)
    sensitive_speculations: int = Field(ge=0)
    corrections: int = Field(ge=0)
    deletion_requests: int = Field(ge=0)
    near_duplicates: int = Field(ge=0)
    reconnect_queries: int = Field(ge=0)


class AttachmentPlan(StrictModel):
    allowed_kinds: tuple[Literal["image"], ...]
    target_count: int = Field(ge=0)
    description_rules: tuple[str, ...]

    @model_validator(mode="after")
    def configured_when_used(self) -> Self:
        if self.target_count and (not self.allowed_kinds or not self.description_rules):
            raise ValueError("planned attachments require kinds and description rules")
        return self


class HistoryProfile(StrictModel):
    start_date: date
    span_days: int = Field(ge=1)
    entry_count: int = Field(ge=6)
    generation_chunk_size: int = Field(ge=2, le=6)
    position_expression: Literal["precise", "vague", "mixed", "usually_absent"]
    media_frequency: Literal["none", "occasional", "frequent"]
    claim_style: Literal["exploratory", "mixed", "assertive"]
    external_reference_density: Literal["none", "low", "high"]
    entry_length_mix: EntryLengthMix
    entry_word_ranges: EntryWordRanges
    planned_event_counts: PlannedEventCounts
    attachments: AttachmentPlan

    @model_validator(mode="after")
    def counts_match(self) -> Self:
        if self.entry_length_mix.total != self.entry_count:
            raise ValueError("entry length mix must equal entry_count")
        if self.attachments.target_count > self.entry_count:
            raise ValueError("attachment target cannot exceed entry_count")
        return self


class PersonaInput(StrictModel):
    schema_version: Literal[1]
    persona_id: str = Field(pattern=r"^[a-z0-9-]+$")
    person_name: str = Field(min_length=1)
    background: PersonaBackground
    reading_list: tuple[ReadingListItem, ...] = Field(min_length=1)
    history_profile: HistoryProfile

    @model_validator(mode="after")
    def reading_versions_are_unique(self) -> Self:
        versions = [item.book_version_id for item in self.reading_list]
        if len(versions) != len(set(versions)):
            raise ValueError("reading-list book versions must be unique")
        return self


class JournalVoice(StrictModel):
    first_person_characteristics: tuple[str, ...] = Field(min_length=1)
    recurring_phrases_or_habits: tuple[str, ...]
    avoid: tuple[str, ...] = Field(min_length=1)


class RecurringThread(StrictModel):
    thread_id: str = Field(pattern=r"^thread-\d{3}$")
    description: str = Field(min_length=1)
    starting_view: str = Field(min_length=1)
    possible_development: str = Field(min_length=1)


class ReadingTrajectory(StrictModel):
    book_id: str = Field(min_length=1)
    book_version_id: str = Field(min_length=1)
    stages: tuple[str, ...] = Field(min_length=1)


class ChronologyPhase(StrictModel):
    phase: int = Field(ge=1)
    start_date: date
    end_date: date
    continuity_notes: tuple[str, ...]
    planned_beats: tuple[str, ...]

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("chronology phase ends before it starts")
        return self


class RealismPlan(StrictModel):
    short_or_fragmentary_entries: int = Field(ge=0)
    ordinary_or_low_stakes_entries: int = Field(ge=0)
    entries_without_a_closing_insight: int = Field(ge=0)
    repetition_or_unplanned_callbacks: tuple[str, ...]


class JournalProfile(StrictModel):
    journal_profile_version: Literal[1]
    persona_id: str = Field(pattern=r"^[a-z0-9-]+$")
    voice: JournalVoice
    everyday_context: tuple[str, ...] = Field(min_length=1)
    recurring_threads: tuple[RecurringThread, ...] = Field(min_length=1)
    reading_trajectory: tuple[ReadingTrajectory, ...] = Field(min_length=1)
    chronology: tuple[ChronologyPhase, ...] = Field(min_length=1)
    realism_plan: RealismPlan
    continuity_invariants: tuple[str, ...] = Field(min_length=1)
    stereotype_review_questions: tuple[str, ...] = Field(min_length=1)


class ChunkRequest(StrictModel):
    chunk_request_version: Literal[1]
    chunk_index: int = Field(ge=1)
    sequence_start: int = Field(ge=1)
    sequence_end: int = Field(ge=1)
    earliest_timestamp: datetime
    latest_timestamp: datetime
    length_targets: EntryLengthMix

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.sequence_end < self.sequence_start:
            raise ValueError("chunk sequence range is reversed")
        if self.length_targets.total != self.sequence_end - self.sequence_start + 1:
            raise ValueError("chunk length targets must equal its sequence count")
        if self.latest_timestamp < self.earliest_timestamp:
            raise ValueError("chunk timestamp range is reversed")
        return self


class Attachment(StrictModel):
    attachment_id: str = Field(pattern=r"^attachment-\d{3}$")
    kind: Literal["image"]
    description: str = Field(min_length=1)


class BookContext(StrictModel):
    book_id: str = Field(min_length=1)
    book_version_id: str = Field(min_length=1)
    declared_position: str | None


class JournalEntry(StrictModel):
    entry_id: str = Field(pattern=r"^entry-\d{3}$")
    sequence: int = Field(ge=1)
    timestamp: datetime
    text: str = Field(min_length=1, max_length=8_000)
    attachments: tuple[Attachment, ...]
    book_contexts: tuple[BookContext, ...]

    @model_validator(mode="after")
    def identity_matches_sequence(self) -> Self:
        if self.entry_id != f"entry-{self.sequence:03d}":
            raise ValueError("entry_id must encode sequence")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("entry timestamps must include a UTC offset")
        return self


class JournalEntries(StrictModel):
    journal_dataset_version: Literal[1]
    persona_id: str = Field(pattern=r"^[a-z0-9-]+$")
    entries: tuple[JournalEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        sequences = [entry.sequence for entry in self.entries]
        expected = list(range(sequences[0], sequences[-1] + 1))
        if sequences != expected:
            raise ValueError("entries must be ordered with contiguous sequences")
        timestamps = [entry.timestamp for entry in self.entries]
        if timestamps != sorted(timestamps):
            raise ValueError("entries must be chronological")
        return self


class JournalChunkInput(StrictModel):
    persona: PersonaInput
    journal_profile: JournalProfile
    prior_entries: tuple[JournalEntry, ...]
    chunk_request: ChunkRequest
    librarian_evidence_records: tuple[EvidenceRecord, ...]

    @model_validator(mode="after")
    def aligned(self) -> Self:
        if self.journal_profile.persona_id != self.persona.persona_id:
            raise ValueError("journal profile belongs to another persona")
        expected_start = 1 if not self.prior_entries else self.prior_entries[-1].sequence + 1
        if self.chunk_request.sequence_start != expected_start:
            raise ValueError("chunk must begin after the accepted prior entries")
        return self


class CandidateSpan(StrictModel):
    start_codepoint: int = Field(ge=0)
    end_codepoint: int = Field(ge=0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if self.end_codepoint <= self.start_codepoint:
            raise ValueError("candidate span must be non-empty")
        return self


class MuseNominationExpectation(StrictModel):
    outcome: Literal["candidate", "no_candidate", "ambiguous"]
    reason_codes: tuple[str, ...]
    candidate_spans: tuple[CandidateSpan, ...]

    @model_validator(mode="after")
    def spans_match_outcome(self) -> Self:
        if self.outcome == "candidate" and not self.candidate_spans:
            raise ValueError("candidate expectation requires an exact source span")
        if self.outcome == "no_candidate" and self.candidate_spans:
            raise ValueError("no-candidate expectation cannot contain spans")
        return self


class ProvenanceCaptureExpectation(StrictModel):
    outcome: Literal["allow_capture", "reject_capture", "no_candidate", "ambiguous"]
    reason_codes: tuple[str, ...]


class MemoryPolicyExpectation(StrictModel):
    outcome: Literal["commit", "refuse", "not_applicable", "ambiguous"]
    reason_code: str | None


class HardExpectations(StrictModel):
    muse_nomination: MuseNominationExpectation
    provenance_capture: ProvenanceCaptureExpectation
    memory_policy: MemoryPolicyExpectation
    book_evidence_status: Literal["verified", "not_applicable", "unresolved"]


class EntryRelation(StrictModel):
    target_entry_id: str = Field(pattern=r"^entry-\d{3}$")
    relation: Literal[
        "updates", "contradicts", "near_duplicate", "supports", "unrelated"
    ]


class SoftAssessment(StrictModel):
    durability: Literal["low", "medium", "high", "ambiguous"]
    review_notes: str = Field(min_length=1)


class EntryAnnotation(StrictModel):
    entry_id: str = Field(pattern=r"^entry-\d{3}$")
    hard_expectations: HardExpectations
    relations: tuple[EntryRelation, ...]
    soft_assessment: SoftAssessment
    human_review: Literal["pending", "approved", "rejected"]


class DatasetReview(StrictModel):
    policy_gaps: tuple[str, ...]
    continuity_failures: tuple[str, ...]
    stereotype_concerns: tuple[str, ...]
    entries_requiring_adjudication: tuple[str, ...]


class JournalAnnotations(StrictModel):
    annotation_version: Literal[1]
    capture_policy_version: Literal[1]
    persona_id: str = Field(pattern=r"^[a-z0-9-]+$")
    entries: tuple[EntryAnnotation, ...] = Field(min_length=1)
    dataset_review: DatasetReview


class JournalNoteEvent(StrictModel):
    kind: Literal["journal_note"]
    event_id: str = Field(pattern=r"^event-\d{3}$")
    entry_id: str = Field(pattern=r"^entry-\d{3}$")


class ExplicitSaveEvent(StrictModel):
    kind: Literal["explicit_save"]
    event_id: str = Field(pattern=r"^event-\d{3}$")
    entry_id: str = Field(pattern=r"^entry-\d{3}$")
    span: CandidateSpan


class CorrectMemoryEvent(StrictModel):
    kind: Literal["correct_memory"]
    event_id: str = Field(pattern=r"^event-\d{3}$")
    target_event_id: str = Field(pattern=r"^event-\d{3}$")
    entry_id: str = Field(pattern=r"^entry-\d{3}$")
    span: CandidateSpan


class DeleteMemoryEvent(StrictModel):
    kind: Literal["delete_memory"]
    event_id: str = Field(pattern=r"^event-\d{3}$")
    target_event_id: str = Field(pattern=r"^event-\d{3}$")


ReplayEvent = Annotated[
    JournalNoteEvent | ExplicitSaveEvent | CorrectMemoryEvent | DeleteMemoryEvent,
    Field(discriminator="kind"),
]
REPLAY_EVENT_ADAPTER = TypeAdapter(ReplayEvent)


class ReplayConfiguration(StrictModel):
    capture_enabled: bool
    session_mode: Literal["fresh_session_per_entry"]
    events: tuple[ReplayEvent, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def events_are_unique(self) -> Self:
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("replay event IDs must be unique")
        return self


class DatasetArtifacts(StrictModel):
    persona_input: str = Field(pattern=r"^[a-z0-9-]+\.json$")
    journal_profile: str = Field(pattern=r"^[a-z0-9-]+\.json$")
    journal_entries: str = Field(pattern=r"^[a-z0-9-]+\.json$")
    annotations: str = Field(pattern=r"^[a-z0-9-]+\.json$")
    generation_record: str = Field(pattern=r"^[a-z0-9-]+\.json$")


class DatasetApproval(StrictModel):
    status: Literal["draft", "frozen"]
    reviewed_by: tuple[str, ...]
    reviewed_at: datetime | None
    notes: tuple[str, ...]

    @model_validator(mode="after")
    def frozen_requires_review(self) -> Self:
        if self.status == "frozen" and (not self.reviewed_by or self.reviewed_at is None):
            raise ValueError("a frozen dataset requires named, dated review")
        return self


class DatasetManifest(StrictModel):
    schema_version: Literal[1]
    dataset_id: str = Field(pattern=r"^[a-z0-9-]+-v\d+$")
    persona_id: str = Field(pattern=r"^[a-z0-9-]+$")
    dataset_version: int = Field(ge=1)
    artifacts: DatasetArtifacts
    replay: ReplayConfiguration
    approval: DatasetApproval


class PromptRecord(StrictModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class GenerationRecord(StrictModel):
    schema_version: Literal[1]
    dataset_id: str = Field(pattern=r"^[a-z0-9-]+-v\d+$")
    generated_at: datetime
    generator: str = Field(min_length=1)
    capture_policy_version: Literal[1]
    prompts: tuple[PromptRecord, ...] = Field(min_length=3)
    notes: tuple[str, ...]


class SyntheticJournalDataset(StrictModel):
    manifest: DatasetManifest
    persona: PersonaInput
    journal_profile: JournalProfile
    journal_entries: JournalEntries
    annotations: JournalAnnotations
    generation: GenerationRecord

    @model_validator(mode="after")
    def artifacts_are_consistent(self) -> Self:
        persona_id = self.manifest.persona_id
        if {
            self.persona.persona_id,
            self.journal_profile.persona_id,
            self.journal_entries.persona_id,
            self.annotations.persona_id,
        } != {persona_id}:
            raise ValueError("dataset artifacts name different personas")
        if self.manifest.dataset_id != self.generation.dataset_id:
            raise ValueError("generation record names another dataset")

        entries = self.journal_entries.entries
        if len(entries) != self.persona.history_profile.entry_count:
            raise ValueError("journal entry count differs from the persona contract")
        if entries[0].sequence != 1:
            raise ValueError("a complete dataset must begin with entry 1")

        entry_ids = {entry.entry_id for entry in entries}
        annotations = {item.entry_id: item for item in self.annotations.entries}
        if set(annotations) != entry_ids:
            raise ValueError("annotations must cover every journal entry exactly once")

        profile = self.persona.history_profile
        end_date = profile.start_date + timedelta(days=profile.span_days)
        observed_lengths = {"short": 0, "medium": 0, "long": 0}
        attachment_count = 0
        allowed_books = {
            (book.book_id, book.book_version_id) for book in self.persona.reading_list
        }
        for entry in entries:
            if not profile.start_date <= entry.timestamp.date() <= end_date:
                raise ValueError(f"{entry.entry_id} is outside the fictional date range")
            length = classify_entry_length(entry.text, profile.entry_word_ranges)
            observed_lengths[length] += 1
            attachment_count += len(entry.attachments)
            if any(attachment.kind not in profile.attachments.allowed_kinds for attachment in entry.attachments):
                raise ValueError(f"{entry.entry_id} uses a forbidden attachment kind")
            if any(
                (context.book_id, context.book_version_id) not in allowed_books
                for context in entry.book_contexts
            ):
                raise ValueError(f"{entry.entry_id} uses a book outside the persona input")
            validate_annotation(entry, annotations[entry.entry_id], entry_ids)

        if observed_lengths != profile.entry_length_mix.model_dump():
            raise ValueError("observed entry-length mix differs from the persona contract")
        if attachment_count != profile.attachments.target_count:
            raise ValueError("observed attachment count differs from the persona contract")

        note_ids = [
            event.entry_id
            for event in self.manifest.replay.events
            if isinstance(event, JournalNoteEvent)
        ]
        if note_ids != [entry.entry_id for entry in entries]:
            raise ValueError("replay must contain every journal note once, in order")

        prior_events: dict[str, ReplayEvent] = {}
        replayed_entry_ids: set[str] = set()
        entry_by_id = {entry.entry_id: entry for entry in entries}
        for event in self.manifest.replay.events:
            if isinstance(event, JournalNoteEvent):
                replayed_entry_ids.add(event.entry_id)
            if isinstance(event, (ExplicitSaveEvent, CorrectMemoryEvent)):
                entry = entry_by_id.get(event.entry_id)
                if entry is None:
                    raise ValueError(f"{event.event_id} references an unknown entry")
                if event.entry_id not in replayed_entry_ids:
                    raise ValueError(
                        f"{event.event_id} must use text from an earlier journal note"
                    )
                if (
                    entry.text[event.span.start_codepoint : event.span.end_codepoint]
                    != event.span.text
                ):
                    raise ValueError(f"{event.event_id} has a non-exact control span")
            if isinstance(event, (CorrectMemoryEvent, DeleteMemoryEvent)):
                target = prior_events.get(event.target_event_id)
                if target is None:
                    raise ValueError(
                        f"{event.event_id} must target an earlier replay event"
                    )
                if isinstance(target, DeleteMemoryEvent):
                    raise ValueError(
                        f"{event.event_id} cannot target a delete operation"
                    )
            prior_events[event.event_id] = event

        if self.manifest.approval.status == "frozen" and any(
            annotation.human_review != "approved" for annotation in annotations.values()
        ):
            raise ValueError("a frozen dataset requires every annotation to be approved")
        return self


def count_words(text: str) -> int:
    """Count lexical words consistently for generation and validation."""
    return len(_WORD.findall(text))


def classify_entry_length(text: str, ranges: EntryWordRanges) -> str:
    """Return the declared length bucket or fail outside all ranges."""
    count = count_words(text)
    for name in ("short", "medium", "long"):
        word_range = getattr(ranges, name)
        if word_range.min_words <= count <= word_range.max_words:
            return name
    raise ValueError(f"entry has {count} words, outside the declared ranges")


def validate_annotation(
    entry: JournalEntry,
    annotation: EntryAnnotation,
    entry_ids: set[str],
) -> None:
    """Validate sidecar spans and references without exposing it to agents."""
    nomination = annotation.hard_expectations.muse_nomination
    for span in nomination.candidate_spans:
        if entry.text[span.start_codepoint : span.end_codepoint] != span.text:
            raise ValueError(f"{entry.entry_id} has a non-exact candidate span")
    for relation in annotation.relations:
        if relation.target_entry_id not in entry_ids:
            raise ValueError(f"{entry.entry_id} relates to an unknown entry")
        if relation.target_entry_id == entry.entry_id:
            raise ValueError(f"{entry.entry_id} cannot relate to itself")

    provenance = annotation.hard_expectations.provenance_capture.outcome
    policy = annotation.hard_expectations.memory_policy.outcome
    if nomination.outcome == "no_candidate" and provenance not in {
        "no_candidate",
        "ambiguous",
    }:
        raise ValueError("Provenance cannot review an absent candidate")
    if policy == "commit" and (
        nomination.outcome != "candidate" or provenance != "allow_capture"
    ):
        raise ValueError("a commit expectation requires a candidate and capture approval")


def load_dataset(directory: Path, *, require_frozen: bool = True) -> SyntheticJournalDataset:
    """Load one self-contained dataset directory and validate every boundary."""
    manifest = DatasetManifest.model_validate_json(
        (directory / "manifest.json").read_text(encoding="utf-8")
    )
    artifacts = manifest.artifacts

    def read(name: str) -> str:
        return (directory / name).read_text(encoding="utf-8")

    dataset = SyntheticJournalDataset(
        manifest=manifest,
        persona=PersonaInput.model_validate_json(read(artifacts.persona_input)),
        journal_profile=JournalProfile.model_validate_json(read(artifacts.journal_profile)),
        journal_entries=JournalEntries.model_validate_json(read(artifacts.journal_entries)),
        annotations=JournalAnnotations.model_validate_json(read(artifacts.annotations)),
        generation=GenerationRecord.model_validate_json(read(artifacts.generation_record)),
    )
    if require_frozen and dataset.manifest.approval.status != "frozen":
        raise ValueError("evaluation replay requires a frozen, human-reviewed dataset")
    return dataset


def json_text(value: BaseModel | tuple[BaseModel, ...]) -> str:
    """Render one validated prompt variable as stable, readable JSON."""
    if isinstance(value, tuple):
        payload = [item.model_dump(mode="json") for item in value]
    else:
        payload = value.model_dump(mode="json")
    return json.dumps(payload, ensure_ascii=False, indent=2)
