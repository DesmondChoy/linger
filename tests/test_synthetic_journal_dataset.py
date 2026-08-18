"""Deterministic gates for frozen synthetic-journal datasets."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.synthetic_journals.contracts import (
    JournalNoteEvent,
    SyntheticJournalDataset,
    load_dataset,
)

ROOT = Path(__file__).resolve().parents[1]
MAYA_V1 = ROOT / "data" / "synthetic-journals" / "datasets" / "maya-chen" / "v1"


def test_maya_pilot_validates_without_persona_specific_code() -> None:
    dataset = load_dataset(MAYA_V1, require_frozen=False)
    assert dataset.manifest.dataset_id == "maya-chen-v1"
    assert len(dataset.journal_entries.entries) == 14
    assert dataset.manifest.approval.status == "draft"
    assert all(
        isinstance(event, JournalNoteEvent) for event in dataset.manifest.replay.events
    )


def test_draft_dataset_cannot_enter_evaluation_replay() -> None:
    with pytest.raises(ValueError, match="human-reviewed"):
        load_dataset(MAYA_V1)


def test_generation_record_hashes_the_current_prompts() -> None:
    dataset = load_dataset(MAYA_V1, require_frozen=False)
    for record in dataset.generation.prompts:
        content = (ROOT / record.path).read_bytes()
        assert hashlib.sha256(content).hexdigest() == record.sha256


def test_non_exact_annotation_span_fails_the_dataset_gate() -> None:
    dataset = load_dataset(MAYA_V1, require_frozen=False)
    payload = dataset.model_dump(mode="json")
    candidate = payload["annotations"]["entries"][1]["hard_expectations"][
        "muse_nomination"
    ]["candidate_spans"][0]
    candidate["text"] = "paraphrased instead of copied"

    with pytest.raises(ValidationError, match="non-exact candidate span"):
        SyntheticJournalDataset.model_validate(payload)


def test_control_cannot_use_text_before_its_journal_note() -> None:
    dataset = load_dataset(MAYA_V1, require_frozen=False)
    payload = dataset.model_dump(mode="json")
    entry = payload["journal_entries"]["entries"][0]
    payload["manifest"]["replay"]["events"].insert(
        0,
        {
            "kind": "explicit_save",
            "event_id": "event-101",
            "entry_id": "entry-001",
            "span": {
                "start_codepoint": 0,
                "end_codepoint": len(entry["text"]),
                "text": entry["text"],
            },
        },
    )

    with pytest.raises(ValidationError, match="earlier journal note"):
        SyntheticJournalDataset.model_validate(payload)
