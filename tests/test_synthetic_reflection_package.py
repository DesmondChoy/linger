"""Tests for deterministic validation of reflection-and-grounding packages."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from evals.synthetic_journals.models import ProposedGroundTruth, SyntheticBackstory
from evals.synthetic_journals.validate_package import (
    PackageValidationError,
    validate_package,
)

OBJECTIVE_ID = "weak_evidence_safe_decline"
CORPUS_CHAPTER = "data/corpus/alice-in-wonderland/pg11-v01b38ea4/chapters/01-down-the-rabbit-hole.md"
QUOTE = "a book of rules for shutting people up like telescopes"


def _corpus_evidence(repository_root: Path) -> dict[str, object]:
    source = (repository_root / CORPUS_CHAPTER).read_text(encoding="utf-8")
    start = source.index(QUOTE)
    return {
        "kind": "repository_text",
        "evidence_id": "ev-1",
        "repository_path": CORPUS_CHAPTER,
        "source_sha256": hashlib.sha256(
            (repository_root / CORPUS_CHAPTER).read_bytes()
        ).hexdigest(),
        "start_codepoint": start,
        "end_codepoint": start + len(QUOTE),
        "text": QUOTE,
    }


def _content_document() -> dict[str, object]:
    return {
        "objective_ids": [OBJECTIVE_ID],
        "run_configuration_ids": [],
        "backstory": {
            "backstory_id": "backstory-1",
            "person_id": "person-1",
            "evaluation_account_id": "account-1",
            "context": "A reader revisiting a childhood favourite.",
        },
        "props": [],
        "scenes": [
            {
                "scene_id": "scene-01",
                "backstory_id": "backstory-1",
                "objective_ids": [OBJECTIVE_ID],
                "order": 1,
                "fresh_session": True,
                "prop_ids": [],
                "line_ids": ["line-01"],
                "offline_input_ids": [],
            },
            {
                "scene_id": "scene-02",
                "backstory_id": "backstory-1",
                "objective_ids": [OBJECTIVE_ID],
                "order": 2,
                "fresh_session": True,
                "prop_ids": [],
                "line_ids": ["line-02"],
                "offline_input_ids": [],
            },
        ],
        "lines": [
            {
                "line_id": "line-01",
                "scene_id": "scene-01",
                "order": 1,
                "text": "What is Alice hoping to find back at the table?",
            },
            {
                "line_id": "line-02",
                "scene_id": "scene-02",
                "order": 1,
                "text": "Rereading this after ten years feels different somehow.",
            },
        ],
        "offline_inputs": [],
    }


def _ground_truth_document(
    content: dict[str, object],
    backstory_bytes: bytes,
    repository_root: Path,
) -> dict[str, object]:
    return {
        "backstory_sha256": hashlib.sha256(backstory_bytes).hexdigest(),
        "ground_truth_status": "proposed",
        "proposals": [
            {
                "proposal_id": "proposal-scene-01",
                "scene_id": "scene-01",
                "objective_id": OBJECTIVE_ID,
                "expected_outcomes": ["Releases a grounded reflection."],
                "prohibited_outcomes": ["Cites unresolvable evidence."],
                "evidence": [_corpus_evidence(repository_root)],
                "grounding": {
                    "primary_behavior": "grounded_reflection",
                    "expected": {
                        "kind": "grounded_release",
                        "permitted_evidence_ids": ["ev-1"],
                        "chapter_max": 6,
                    },
                },
            },
            {
                "proposal_id": "proposal-scene-02",
                "scene_id": "scene-02",
                "objective_id": OBJECTIVE_ID,
                "expected_outcomes": ["Reflects without retrieving evidence."],
                "prohibited_outcomes": ["Retrieves without a demonstrated need."],
                "evidence": [],
                "grounding": {
                    "primary_behavior": "non_grounded_reflection",
                    "expected": {"kind": "ungrounded_release"},
                },
            },
        ],
    }


def _json_bytes(document: dict[str, object]) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _validate(
    content_document: dict[str, object],
    ground_truth_document: dict[str, object],
    repository_root: Path,
) -> None:
    backstory_bytes = _json_bytes(content_document)
    ground_truth_document = deepcopy(ground_truth_document)
    ground_truth_document["backstory_sha256"] = hashlib.sha256(
        backstory_bytes
    ).hexdigest()
    validate_package(
        SyntheticBackstory.model_validate_json(backstory_bytes),
        ProposedGroundTruth.model_validate_json(
            _json_bytes(ground_truth_document)
        ),
        backstory_bytes=backstory_bytes,
        run_configurations={},
        repository_root=repository_root,
    )


@pytest.fixture
def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def package(repository_root: Path) -> tuple[dict[str, object], dict[str, object]]:
    content = _content_document()
    ground_truth = _ground_truth_document(
        content, _json_bytes(content), repository_root
    )
    return content, ground_truth


def test_validates_a_grounded_and_non_grounded_scene_pair(
    package: tuple[dict[str, object], dict[str, object]],
    repository_root: Path,
) -> None:
    content, ground_truth = package
    _validate(content, ground_truth, repository_root)


def test_reflection_scene_requires_typed_grounding_ground_truth(
    package: tuple[dict[str, object], dict[str, object]],
    repository_root: Path,
) -> None:
    content, ground_truth = package
    del ground_truth["proposals"][0]["grounding"]  # type: ignore[index]

    with pytest.raises(PackageValidationError) as error:
        _validate(content, ground_truth, repository_root)
    assert "lacks typed grounding Ground truth" in str(error.value)


def test_grounding_is_rejected_on_a_non_reflection_objective(
    package: tuple[dict[str, object], dict[str, object]],
    repository_root: Path,
) -> None:
    content, ground_truth = package
    content["objective_ids"] = [OBJECTIVE_ID, "bounded_memory_curation"]
    content["scenes"][1]["objective_ids"] = ["bounded_memory_curation"]  # type: ignore[index]
    ground_truth["proposals"][1]["objective_id"] = "bounded_memory_curation"  # type: ignore[index]

    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="only for weak_evidence_safe_decline"):
        _validate(content, ground_truth, repository_root)


def test_permitted_evidence_must_be_corpus_backed(
    package: tuple[dict[str, object], dict[str, object]],
    repository_root: Path,
) -> None:
    """A Prop cannot authorise a released book citation."""
    content, ground_truth = package
    ground_truth["proposals"][0]["evidence"] = [  # type: ignore[index]
        {"kind": "prop", "evidence_id": "ev-1", "prop_id": "prop-1"}
    ]
    content["props"] = [
        {
            "prop_id": "prop-1",
            "backstory_id": "backstory-1",
            "person_id": "person-1",
            "evaluation_account_id": "account-1",
            "source_text": "A remembered conversation about the story.",
            "lifecycle": [{"scene_id": "scene-01", "state": "active"}],
        }
    ]
    content["scenes"][0]["prop_ids"] = ["prop-1"]  # type: ignore[index]

    with pytest.raises(PackageValidationError) as error:
        _validate(content, ground_truth, repository_root)
    assert "permits non-corpus evidence" in str(error.value)


def test_chapter_ceiling_cannot_exceed_the_shipped_corpus(
    package: tuple[dict[str, object], dict[str, object]],
    repository_root: Path,
) -> None:
    content, ground_truth = package
    ground_truth["proposals"][0]["grounding"]["expected"]["chapter_max"] = 99  # type: ignore[index]

    with pytest.raises(PackageValidationError) as error:
        _validate(content, ground_truth, repository_root)
    assert "beyond every shipped work" in str(error.value)


def test_non_grounded_scene_cannot_declare_evidence(
    package: tuple[dict[str, object], dict[str, object]],
    repository_root: Path,
) -> None:
    content, ground_truth = package
    ground_truth["proposals"][1]["evidence"] = [  # type: ignore[index]
        _corpus_evidence(repository_root) | {"evidence_id": "ev-2"}
    ]

    with pytest.raises(PackageValidationError) as error:
        _validate(content, ground_truth, repository_root)
    assert "expects no grounded release" in str(error.value)


def test_reflection_scene_rejects_offline_inputs(
    package: tuple[dict[str, object], dict[str, object]],
    repository_root: Path,
) -> None:
    content, ground_truth = package
    content["offline_inputs"] = [
        {
            "offline_input_id": "offline-01",
            "scene_id": "scene-01",
            "order": 1,
            "kind": "note",
            "text": "An offline note.",
        }
    ]
    content["scenes"][0]["offline_input_ids"] = ["offline-01"]  # type: ignore[index]

    with pytest.raises(PackageValidationError) as error:
        _validate(content, ground_truth, repository_root)
    assert "cannot use offline inputs" in str(error.value)


def test_reflection_proposal_rejects_capture_ground_truth(
    package: tuple[dict[str, object], dict[str, object]],
    repository_root: Path,
) -> None:
    content, ground_truth = package
    ground_truth["proposals"][1]["capture"] = {"kind": "no_candidate"}  # type: ignore[index]

    with pytest.raises(PackageValidationError) as error:
        _validate(content, ground_truth, repository_root)
    assert "cannot contain capture or curation Ground truth" in str(error.value)
