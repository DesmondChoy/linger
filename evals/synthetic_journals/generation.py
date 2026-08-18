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
    ChunkRequest,
    EntryLengthMix,
    JournalAnnotations,
    JournalEntry,
    JournalProfile,
    PersonaInput,
    json_text,
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
    persona: PersonaInput,
    profile: JournalProfile,
    entries: tuple[JournalEntry, ...],
    evidence: tuple[EvidenceRecord, ...] = (),
) -> str:
    """Render the grader-side annotation prompt with the canonical policy."""
    policy = CAPTURE_POLICY_PATH.read_text(encoding="utf-8")
    return _render(
        "03-annotate-journal-entries.md",
        {
            "PERSONA_INPUT_JSON": json_text(persona),
            "JOURNAL_PROFILE_JSON": json_text(profile),
            "JOURNAL_ENTRIES_JSON": json_text(entries),
            "CAPTURE_POLICY_CONTRACT": policy,
            "LIBRARIAN_EVIDENCE_RECORDS_JSON": json_text(evidence),
        },
    )


def validate_annotation_output(text: str) -> JournalAnnotations:
    """Reject malformed annotation output before dataset packaging."""
    return JournalAnnotations.model_validate_json(text)


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
