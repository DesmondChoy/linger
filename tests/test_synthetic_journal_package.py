"""Tests for strict synthetic journal package validation."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.synthetic_journals.models import ProposedGroundTruth, SyntheticBackstory
from evals.synthetic_journals.validate_package import (
    DEFAULT_RUN_CONFIGURATION_DIRECTORY,
    PackageValidationError,
    load_run_configurations,
    main,
    validate_package,
    validate_package_files,
)

OBJECTIVE_ID = "reviewed_automatic_memory_capture"
RUN_CONFIGURATION_ID = "reviewed-automatic-memory-capture-10-to-1"


def _content_document(
    *,
    scene_count: int = 11,
    use_run_configuration: bool = True,
) -> dict[str, object]:
    lines = []
    scenes = []
    for index in range(1, scene_count + 1):
        line_id = f"line-{index:02d}"
        scene_id = f"scene-{index:02d}"
        text = (
            "I want to keep making a little time to sketch after work."
            if index == 1
            else f"Routine update {index}: the bus was a few minutes late today."
        )
        lines.append(
            {
                "line_id": line_id,
                "scene_id": scene_id,
                "order": 1,
                "text": text,
            }
        )
        scenes.append(
            {
                "scene_id": scene_id,
                "backstory_id": "backstory-01",
                "objective_ids": [OBJECTIVE_ID],
                "order": index,
                "fresh_session": True,
                "prop_ids": [],
                "line_ids": [line_id],
                "offline_input_ids": [],
            }
        )
    return {
        "objective_ids": [OBJECTIVE_ID],
        "run_configuration_ids": (
            [RUN_CONFIGURATION_ID] if use_run_configuration else []
        ),
        "backstory": {
            "backstory_id": "backstory-01",
            "person_id": "person-01",
            "evaluation_account_id": "account-01",
            "context": "A commuter is trying to protect time for a neglected hobby.",
        },
        "props": [],
        "scenes": scenes,
        "lines": lines,
        "offline_inputs": [],
    }


def _json_bytes(document: dict[str, object]) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _ground_truth_document(
    content: dict[str, object],
    backstory_bytes: bytes,
) -> dict[str, object]:
    proposals = []
    lines = {line["line_id"]: line for line in content["lines"]}  # type: ignore[index]
    for scene in content["scenes"]:  # type: ignore[union-attr]
        scene_id = scene["scene_id"]
        line_id = scene["line_ids"][0]
        proposal: dict[str, object] = {
            "proposal_id": f"proposal-{scene_id}",
            "scene_id": scene_id,
            "objective_id": OBJECTIVE_ID,
            "expected_outcomes": ["The capture workflow follows the intended label."],
            "prohibited_outcomes": ["The workflow writes an unauthorized memory."],
            "exact_spans": [],
            "evidence": [],
            "pairing": None,
        }
        if scene_id == "scene-01":
            text = lines[line_id]["text"]
            candidate = "keep making a little time to sketch"
            start = text.index(candidate)
            proposal["capture"] = {
                "kind": "capture_candidate",
                "span": {
                    "source_kind": "line",
                    "source_id": line_id,
                    "start_codepoint": start,
                    "end_codepoint": start + len(candidate),
                    "text": candidate,
                },
            }
        else:
            proposal["capture"] = {"kind": "no_candidate"}
        proposals.append(proposal)
    return {
        "backstory_sha256": hashlib.sha256(backstory_bytes).hexdigest(),
        "ground_truth_status": "proposed",
        "proposals": proposals,
    }


def _validated_models(
    content_document: dict[str, object],
    ground_truth_document: dict[str, object],
) -> tuple[SyntheticBackstory, ProposedGroundTruth]:
    return (
        SyntheticBackstory.model_validate_json(_json_bytes(content_document)),
        ProposedGroundTruth.model_validate_json(_json_bytes(ground_truth_document)),
    )


def _run_configurations():
    return load_run_configurations(DEFAULT_RUN_CONFIGURATION_DIRECTORY)


def test_validates_one_positive_and_ten_no_candidates() -> None:
    content_document = _content_document()
    backstory_bytes = _json_bytes(content_document)
    ground_truth_document = _ground_truth_document(content_document, backstory_bytes)
    content, ground_truth = _validated_models(content_document, ground_truth_document)

    validate_package(
        content,
        ground_truth,
        backstory_bytes=backstory_bytes,
        run_configurations=_run_configurations(),
    )


def test_file_entrypoint_uses_exact_backstory_bytes(tmp_path: Path) -> None:
    content_document = _content_document()
    backstory_bytes = json.dumps(content_document, indent=2).encode("utf-8")
    ground_truth_document = _ground_truth_document(content_document, backstory_bytes)
    backstory_path = tmp_path / "backstory.json"
    ground_truth_path = tmp_path / "ground-truth.json"
    backstory_path.write_bytes(backstory_bytes)
    ground_truth_path.write_bytes(_json_bytes(ground_truth_document))

    content, ground_truth = validate_package_files(backstory_path, ground_truth_path)

    assert len(content.scenes) == 11
    assert len(ground_truth.proposals) == 11


def test_cli_reports_valid_package(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    content_document = _content_document()
    backstory_bytes = _json_bytes(content_document)
    ground_truth_document = _ground_truth_document(content_document, backstory_bytes)
    backstory_path = tmp_path / "backstory.json"
    ground_truth_path = tmp_path / "ground-truth.json"
    backstory_path.write_bytes(backstory_bytes)
    ground_truth_path.write_bytes(_json_bytes(ground_truth_document))

    assert main([str(backstory_path), str(ground_truth_path)]) == 0
    assert "PACKAGE_VALIDATION_OK=11 scenes,11 proposals" in capsys.readouterr().out


def test_rejects_unknown_fields_without_coercion() -> None:
    content_document = _content_document()
    content_document["schema_version"] = 1
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SyntheticBackstory.model_validate_json(_json_bytes(content_document))

    content_document = _content_document()
    content_document["scenes"][0]["order"] = "1"  # type: ignore[index]
    with pytest.raises(ValidationError, match="valid integer"):
        SyntheticBackstory.model_validate_json(_json_bytes(content_document))


def test_rejects_unknown_entity_reference() -> None:
    content_document = _content_document()
    content_document["scenes"][0]["line_ids"] = ["missing-line"]  # type: ignore[index]
    with pytest.raises(ValidationError, match="unknown Line IDs"):
        SyntheticBackstory.model_validate_json(_json_bytes(content_document))


def test_rejects_selected_objective_without_a_scene() -> None:
    content_document = _content_document()
    content_document["objective_ids"].append("unused_objective")  # type: ignore[union-attr]

    with pytest.raises(ValidationError, match="without a Scene"):
        SyntheticBackstory.model_validate_json(_json_bytes(content_document))


def test_prop_scope_and_lifecycle_must_match_assigned_scenes() -> None:
    content_document = _content_document(
        scene_count=2,
        use_run_configuration=False,
    )
    content_document["props"] = [
        {
            "prop_id": "prop-01",
            "backstory_id": "backstory-01",
            "person_id": "person-01",
            "evaluation_account_id": "account-01",
            "source_text": "Sketching used to help me unwind.",
            "lifecycle": [{"scene_id": "scene-01", "state": "active"}],
        }
    ]
    content_document["scenes"][0]["prop_ids"] = ["prop-01"]  # type: ignore[index]
    SyntheticBackstory.model_validate_json(_json_bytes(content_document))

    content_document["props"][0]["evaluation_account_id"] = "other-account"  # type: ignore[index]
    with pytest.raises(ValidationError, match="outside the package"):
        SyntheticBackstory.model_validate_json(_json_bytes(content_document))


def test_rejects_content_hash_mismatch() -> None:
    content_document = _content_document()
    backstory_bytes = _json_bytes(content_document)
    ground_truth_document = _ground_truth_document(content_document, backstory_bytes)
    ground_truth_document["backstory_sha256"] = "0" * 64
    content, ground_truth = _validated_models(content_document, ground_truth_document)

    with pytest.raises(PackageValidationError, match="backstory_sha256"):
        validate_package(
            content,
            ground_truth,
            backstory_bytes=backstory_bytes,
            run_configurations=_run_configurations(),
        )


def test_ground_truth_can_only_be_proposed() -> None:
    content_document = _content_document()
    backstory_bytes = _json_bytes(content_document)
    ground_truth_document = _ground_truth_document(content_document, backstory_bytes)
    ground_truth_document["ground_truth_status"] = "adopted"

    with pytest.raises(ValidationError, match="Input should be 'proposed'"):
        ProposedGroundTruth.model_validate_json(_json_bytes(ground_truth_document))


def test_rejects_exact_span_text_mismatch() -> None:
    content_document = _content_document()
    backstory_bytes = _json_bytes(content_document)
    ground_truth_document = _ground_truth_document(content_document, backstory_bytes)
    ground_truth_document["proposals"][0]["capture"]["span"][  # type: ignore[index]
        "text"
    ] = "wrong"
    content, ground_truth = _validated_models(content_document, ground_truth_document)

    with pytest.raises(PackageValidationError, match="span text mismatch"):
        validate_package(
            content,
            ground_truth,
            backstory_bytes=backstory_bytes,
            run_configurations=_run_configurations(),
        )


def test_exact_span_offsets_preserve_source_whitespace() -> None:
    content_document = _content_document()
    content_document["lines"][0]["text"] = (  # type: ignore[index]
        "  I want to keep making a little time to sketch after work.  "
    )
    backstory_bytes = _json_bytes(content_document)
    ground_truth_document = _ground_truth_document(content_document, backstory_bytes)
    content, ground_truth = _validated_models(content_document, ground_truth_document)

    assert content.lines[0].text.startswith("  ")
    validate_package(
        content,
        ground_truth,
        backstory_bytes=backstory_bytes,
        run_configurations=_run_configurations(),
    )


def test_rejects_capture_mix_other_than_one_to_ten() -> None:
    content_document = _content_document()
    backstory_bytes = _json_bytes(content_document)
    ground_truth_document = _ground_truth_document(content_document, backstory_bytes)
    second = ground_truth_document["proposals"][1]  # type: ignore[index]
    second_line = content_document["lines"][1]  # type: ignore[index]
    second["capture"] = {
        "kind": "capture_candidate",
        "span": {
            "source_kind": "line",
            "source_id": second_line["line_id"],
            "start_codepoint": 0,
            "end_codepoint": len(second_line["text"]),
            "text": second_line["text"],
        },
    }
    content, ground_truth = _validated_models(content_document, ground_truth_document)

    with pytest.raises(PackageValidationError, match="1 capture_candidate"):
        validate_package(
            content,
            ground_truth,
            backstory_bytes=backstory_bytes,
            run_configurations=_run_configurations(),
        )


def test_rejects_generic_spans_in_capture_run() -> None:
    content_document = _content_document()
    backstory_bytes = _json_bytes(content_document)
    ground_truth_document = _ground_truth_document(content_document, backstory_bytes)
    capture_span = deepcopy(
        ground_truth_document["proposals"][0]["capture"]["span"]  # type: ignore[index]
    )
    ground_truth_document["proposals"][0][  # type: ignore[index]
        "exact_spans"
    ] = [capture_span]
    content, ground_truth = _validated_models(content_document, ground_truth_document)

    with pytest.raises(PackageValidationError, match="generic exact_spans"):
        validate_package(
            content,
            ground_truth,
            backstory_bytes=backstory_bytes,
            run_configurations=_run_configurations(),
        )


def test_capture_ratio_is_not_a_universal_objective_rule() -> None:
    content_document = _content_document(
        scene_count=2,
        use_run_configuration=False,
    )
    backstory_bytes = _json_bytes(content_document)
    ground_truth_document = _ground_truth_document(content_document, backstory_bytes)
    content, ground_truth = _validated_models(content_document, ground_truth_document)

    validate_package(
        content,
        ground_truth,
        backstory_bytes=backstory_bytes,
        run_configurations=_run_configurations(),
    )


def test_pairing_checks_declared_matches_and_differences() -> None:
    content_document = _content_document()
    backstory_bytes = _json_bytes(content_document)
    ground_truth_document = _ground_truth_document(content_document, backstory_bytes)
    ground_truth_document["proposals"][0]["pairing"] = {  # type: ignore[index]
        "paired_scene_id": "scene-02",
        "match_fields": ["backstory_id", "fresh_session"],
        "difference_fields": ["line_text"],
    }
    content, ground_truth = _validated_models(content_document, ground_truth_document)
    validate_package(
        content,
        ground_truth,
        backstory_bytes=backstory_bytes,
        run_configurations=_run_configurations(),
    )

    broken_ground_truth = deepcopy(ground_truth_document)
    pairing = broken_ground_truth["proposals"][0]["pairing"]  # type: ignore[index]
    pairing["match_fields"] = ["line_text"]
    broken_pairing = broken_ground_truth["proposals"][0][  # type: ignore[index]
        "pairing"
    ]
    broken_pairing["difference_fields"] = [
        "fresh_session"
    ]
    _, broken = _validated_models(content_document, broken_ground_truth)
    with pytest.raises(PackageValidationError, match="must match on line_text"):
        validate_package(
            content,
            broken,
            backstory_bytes=backstory_bytes,
            run_configurations=_run_configurations(),
        )


def test_repository_evidence_resolves_hash_and_exact_span(tmp_path: Path) -> None:
    source_bytes = "Alpha βeta gamma.".encode("utf-8")
    source_path = tmp_path / "source.md"
    source_path.write_bytes(source_bytes)
    content_document = _content_document()
    backstory_bytes = _json_bytes(content_document)
    ground_truth_document = _ground_truth_document(content_document, backstory_bytes)
    ground_truth_document["proposals"][0]["evidence"] = [  # type: ignore[index]
        {
            "kind": "repository_text",
            "evidence_id": "evidence-01",
            "repository_path": "source.md",
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "start_codepoint": 6,
            "end_codepoint": 10,
            "text": "βeta",
        }
    ]
    content, ground_truth = _validated_models(content_document, ground_truth_document)
    validate_package(
        content,
        ground_truth,
        backstory_bytes=backstory_bytes,
        run_configurations=_run_configurations(),
        repository_root=tmp_path,
    )

    broken_ground_truth = deepcopy(ground_truth_document)
    broken_evidence = broken_ground_truth["proposals"][0][  # type: ignore[index]
        "evidence"
    ][0]
    broken_evidence["source_sha256"] = "0" * 64
    _, broken = _validated_models(content_document, broken_ground_truth)
    with pytest.raises(PackageValidationError, match="source_sha256"):
        validate_package(
            content,
            broken,
            backstory_bytes=backstory_bytes,
            run_configurations=_run_configurations(),
            repository_root=tmp_path,
        )


def test_json_schema_forbids_extra_fields_and_discriminates_capture() -> None:
    backstory_schema = SyntheticBackstory.model_json_schema()
    ground_truth_schema = ProposedGroundTruth.model_json_schema()

    assert backstory_schema["additionalProperties"] is False
    assert "schema_version" not in backstory_schema["properties"]
    assert "schema_version" not in ground_truth_schema["properties"]
    capture_schema = ground_truth_schema["$defs"]["GroundTruthProposal"]["properties"][
        "capture"
    ]["anyOf"][0]
    assert capture_schema["discriminator"]["propertyName"] == "kind"
    assert set(capture_schema["discriminator"]["mapping"]) == {
        "capture_candidate",
        "no_candidate",
    }
