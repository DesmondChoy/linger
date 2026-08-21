"""Validated, demo-only reader histories for Serendipity development."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from src.linger.agents.contracts import StrictModel


REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = REPO_ROOT / "data" / "synthetic_readers.json"
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    {
        "a", "about", "an", "and", "are", "as", "at", "be", "because",
        "but", "by", "does", "feel", "for", "from", "have", "how", "i",
        "in", "is", "it", "me", "my", "of", "on", "or", "so", "that",
        "the", "this", "to", "was", "what", "when", "why", "with",
    }
)


class SyntheticReadingContext(StrictModel):
    work_id: str
    work_title: str
    chapter: int = Field(ge=1)
    chapter_state: Literal["started", "completed"]


class SyntheticTurn(StrictModel):
    turn_id: str
    reader_message: str = Field(min_length=1)
    assistant_response: str = Field(min_length=1)
    captured_memory_ids: tuple[str, ...] = ()


class SyntheticChatDay(StrictModel):
    date: date
    reading_context: SyntheticReadingContext
    turns: tuple[SyntheticTurn, ...] = Field(min_length=2)


class SyntheticMemory(StrictModel):
    memory_id: str
    text: str = Field(min_length=1)
    memory_type: Literal[
        "interpretation",
        "emotional_response",
        "personal_association",
        "reading_preference",
    ]
    work_id: str | None = None
    source_turn_id: str
    captured_on: date
    themes: tuple[str, ...] = Field(min_length=1)
    sensitivity: Literal["non_sensitive"] = "non_sensitive"
    authorised_for_connections: bool = True


class SyntheticReader(StrictModel):
    reader_id: str = Field(pattern=r"^demo-[a-z0-9-]+$")
    display_name: str
    profile_summary: str
    days: tuple[SyntheticChatDay, ...] = Field(min_length=3)
    memories: tuple[SyntheticMemory, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def history_is_coherent(self) -> "SyntheticReader":
        if [day.date for day in self.days] != sorted(day.date for day in self.days):
            raise ValueError("chat days must be chronological")
        turns = [turn for day in self.days for turn in day.turns]
        turn_ids = [turn.turn_id for turn in turns]
        memory_ids = [memory.memory_id for memory in self.memories]
        if len(turn_ids) != len(set(turn_ids)):
            raise ValueError("turn IDs must be unique within a reader")
        if len(memory_ids) != len(set(memory_ids)):
            raise ValueError("memory IDs must be unique within a reader")
        known_turns = set(turn_ids)
        known_memories = set(memory_ids)
        if any(memory.source_turn_id not in known_turns for memory in self.memories):
            raise ValueError("every memory must reference a known source turn")
        if any(
            not set(turn.captured_memory_ids).issubset(known_memories)
            for turn in turns
        ):
            raise ValueError("turns may reference only this reader's memories")
        return self


class SyntheticConnectionScenario(StrictModel):
    scenario_id: str
    reader_id: str
    current_cue: str = Field(min_length=1)
    target_type: Literal["reader_memory", "cross_book", "artwork", "song"]
    expected_memory_ids: tuple[str, ...] = Field(min_length=1)
    expected_connection: str = Field(min_length=1)


class SyntheticReaderDataset(StrictModel):
    schema_version: Literal[1]
    users: tuple[SyntheticReader, ...] = Field(min_length=3)
    connection_scenarios: tuple[SyntheticConnectionScenario, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def references_are_isolated(self) -> "SyntheticReaderDataset":
        readers = {reader.reader_id: reader for reader in self.users}
        if len(readers) != len(self.users):
            raise ValueError("reader IDs must be unique")
        all_memory_ids = [
            memory.memory_id for reader in self.users for memory in reader.memories
        ]
        if len(all_memory_ids) != len(set(all_memory_ids)):
            raise ValueError("memory IDs must be globally unique")
        scenario_ids = [scenario.scenario_id for scenario in self.connection_scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("connection scenario IDs must be unique")
        for scenario in self.connection_scenarios:
            reader = readers.get(scenario.reader_id)
            if reader is None:
                raise ValueError("connection scenarios must reference a known reader")
            owned = {memory.memory_id for memory in reader.memories}
            if not set(scenario.expected_memory_ids).issubset(owned):
                raise ValueError("scenarios may expect only reader-owned memories")
        return self


@dataclass(frozen=True)
class SyntheticMemoryMatch:
    evidence_id: str
    excerpt: str
    capture_type: Literal["automatic"]
    recorded_at: str
    relevance: float


@lru_cache
def load_synthetic_readers(path: Path = DATASET_PATH) -> SyntheticReaderDataset:
    """Load and strictly validate the immutable local demo fixture."""
    return SyntheticReaderDataset.model_validate_json(path.read_text(encoding="utf-8"))


def synthetic_reader(reader_id: str) -> SyntheticReader:
    for reader in load_synthetic_readers().users:
        if reader.reader_id == reader_id:
            return reader
    raise KeyError(f"Unknown synthetic reader: {reader_id}")


def synthetic_scenarios(reader_id: str) -> tuple[SyntheticConnectionScenario, ...]:
    synthetic_reader(reader_id)
    return tuple(
        scenario
        for scenario in load_synthetic_readers().connection_scenarios
        if scenario.reader_id == reader_id
    )


def _terms(text: str) -> set[str]:
    return {
        token
        for token in TOKEN_PATTERN.findall(text.casefold())
        if token not in STOPWORDS
    }


def synthetic_memory_texts(reader_id: str) -> tuple[str, ...]:
    """Return all authorised text for the selected reader's web privacy gate."""
    return tuple(
        memory.text
        for memory in synthetic_reader(reader_id).memories
        if memory.authorised_for_connections
    )


def synthetic_memory_evidence(
    reader_id: str,
    cue: str,
    limit: int = 5,
) -> tuple[SyntheticMemoryMatch, ...]:
    """Rank only the selected demo reader's authorised memories."""
    cue_terms = _terms(cue)
    ranked: list[tuple[float, SyntheticMemory]] = []
    for memory in synthetic_reader(reader_id).memories:
        if not memory.authorised_for_connections:
            continue
        memory_terms = _terms(f"{memory.text} {' '.join(memory.themes)}")
        overlap = len(cue_terms & memory_terms)
        if not overlap:
            continue
        score = overlap / max(1, len(cue_terms))
        ranked.append((score, memory))
    ranked.sort(key=lambda pair: (-pair[0], pair[1].captured_on, pair[1].memory_id))
    return tuple(
        SyntheticMemoryMatch(
            evidence_id=f"synthetic:{reader_id}:{memory.memory_id}",
            excerpt=memory.text,
            capture_type="automatic",
            recorded_at=memory.captured_on.isoformat(),
            relevance=min(score, 1.0),
        )
        for score, memory in ranked[:limit]
    )
