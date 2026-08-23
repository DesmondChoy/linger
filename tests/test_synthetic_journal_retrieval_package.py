"""Focused validation for the longitudinal retrieval Prop mix."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest

from evals.synthetic_journals.models import AuthoringManifest, SyntheticContent
from evals.synthetic_journals.validate_package import (
    DEFAULT_RUN_CONFIGURATION_DIRECTORY,
    PackageValidationError,
    load_run_configurations,
    validate_package,
)

OBJECTIVE_ID = "longitudinal_memory_retrieval"
RUN_CONFIGURATION_ID = "longitudinal-memory-retrieval-10-to-1"


def _content_document(*, shifted_comparison_bank: bool = False) -> dict[str, object]:
    target_ids = [f"prop-{index:02d}" for index in range(1, 12)]
    comparison_ids = (
        [f"prop-{index:02d}" for index in range(2, 13)]
        if shifted_comparison_bank
        else target_ids
    )
    scene_banks = {
        "scene-target": target_ids,
        "scene-comparison": comparison_ids,
    }
    all_prop_ids = sorted(set(target_ids) | set(comparison_ids))
    props = []
    for prop_id in all_prop_ids:
        props.append(
            {
                "prop_id": prop_id,
                "backstory_id": "backstory-01",
                "person_id": "person-01",
                "evaluation_account_id": "account-01",
                "source_text": f"A plausible prior memory recorded as {prop_id}.",
                "lifecycle": [
                    {"scene_id": scene_id, "state": "active"}
                    for scene_id, prop_ids in scene_banks.items()
                    if prop_id in prop_ids
                ],
            }
        )
    return {
        "schema_version": 1,
        "objective_ids": [OBJECTIVE_ID],
        "run_configuration_ids": [RUN_CONFIGURATION_ID],
        "backstory": {
            "backstory_id": "backstory-01",
            "person_id": "person-01",
            "evaluation_account_id": "account-01",
            "context": "One person has several related memories across sessions.",
        },
        "props": props,
        "scenes": [
            {
                "scene_id": "scene-target",
                "backstory_id": "backstory-01",
                "objective_ids": [OBJECTIVE_ID],
                "order": 1,
                "fresh_session": True,
                "prop_ids": target_ids,
                "line_ids": ["line-target"],
                "offline_input_ids": [],
            },
            {
                "scene_id": "scene-comparison",
                "backstory_id": "backstory-01",
                "objective_ids": [OBJECTIVE_ID],
                "order": 2,
                "fresh_session": True,
                "prop_ids": comparison_ids,
                "line_ids": ["line-comparison"],
                "offline_input_ids": [],
            },
        ],
        "lines": [
            {
                "line_id": "line-target",
                "scene_id": "scene-target",
                "order": 1,
                "text": "I keep returning to the same difficult decision.",
            },
            {
                "line_id": "line-comparison",
                "scene_id": "scene-comparison",
                "order": 1,
                "text": "I have a nearby question that my earlier memories do not answer.",
            },
        ],
        "offline_inputs": [],
    }


def _json_bytes(document: dict[str, object]) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _manifest_document(
    content: dict[str, object], content_bytes: bytes
) -> dict[str, object]:
    scenes = content["scenes"]
    assert isinstance(scenes, list)
    proposals = []
    for scene in scenes:
        scene_id = scene["scene_id"]
        prop_ids = scene["prop_ids"]
        is_target = scene_id == "scene-target"
        relevant_id = prop_ids[0] if is_target else None
        proposals.append(
            {
                "proposal_id": f"proposal-{scene_id}",
                "scene_id": scene_id,
                "objective_id": OBJECTIVE_ID,
                "expected_outcomes": ["Retrieval follows the proposed relevance."],
                "prohibited_outcomes": ["A distractor is presented as support."],
                "exact_spans": [],
                "evidence": (
                    [
                        {
                            "kind": "prop",
                            "evidence_id": "evidence-relevant-prop",
                            "prop_id": relevant_id,
                        }
                    ]
                    if relevant_id is not None
                    else []
                ),
                "prop_relevance": [
                    {
                        "prop_id": prop_id,
                        "relevance": (
                            "relevant" if prop_id == relevant_id else "distractor"
                        ),
                    }
                    for prop_id in prop_ids
                ],
                "pairing": None,
                "capture": None,
            }
        )
    return {
        "schema_version": 1,
        "content_sha256": hashlib.sha256(content_bytes).hexdigest(),
        "ground_truth_status": "proposed",
        "proposals": proposals,
    }


def _validate(
    content_document: dict[str, object], manifest_document: dict[str, object]
) -> None:
    content_bytes = _json_bytes(content_document)
    content = SyntheticContent.model_validate_json(content_bytes)
    manifest = AuthoringManifest.model_validate_json(_json_bytes(manifest_document))
    validate_package(
        content,
        manifest,
        content_bytes=content_bytes,
        run_configurations=load_run_configurations(
            DEFAULT_RUN_CONFIGURATION_DIRECTORY
        ),
    )


def _valid_documents() -> tuple[dict[str, object], dict[str, object]]:
    content = _content_document()
    return content, _manifest_document(content, _json_bytes(content))


def test_validates_shared_prop_bank_with_target_and_comparison_mix() -> None:
    content, manifest = _valid_documents()

    _validate(content, manifest)


def test_rejects_wrong_prop_count() -> None:
    content, manifest = _valid_documents()
    for scene in content["scenes"]:  # type: ignore[union-attr]
        scene["prop_ids"] = scene["prop_ids"][:-1]  # type: ignore[index]
    content["props"].pop()  # type: ignore[union-attr]
    manifest = _manifest_document(content, _json_bytes(content))

    with pytest.raises(PackageValidationError, match="requires 11 Props"):
        _validate(content, manifest)


def test_rejects_missing_prop_relevance_judgment() -> None:
    content, manifest = _valid_documents()
    manifest["proposals"][0]["prop_relevance"].pop()  # type: ignore[index]

    with pytest.raises(PackageValidationError, match="judgment for every Prop"):
        _validate(content, manifest)


def test_rejects_wrong_relevance_mix() -> None:
    content, manifest = _valid_documents()
    target = manifest["proposals"][0]  # type: ignore[index]
    second = target["prop_relevance"][1]
    second["relevance"] = "relevant"
    target["evidence"].append(
        {
            "kind": "prop",
            "evidence_id": "evidence-second-relevant-prop",
            "prop_id": second["prop_id"],
        }
    )

    with pytest.raises(PackageValidationError, match="retrieval Prop mixes"):
        _validate(content, manifest)


def test_rejects_different_prop_banks() -> None:
    content = _content_document(shifted_comparison_bank=True)
    manifest = _manifest_document(content, _json_bytes(content))

    with pytest.raises(PackageValidationError, match="same Prop bank"):
        _validate(content, manifest)


def test_rejects_inactive_prop() -> None:
    content, _ = _valid_documents()
    content["props"][0]["lifecycle"][0]["state"] = "inactive"  # type: ignore[index]
    manifest = _manifest_document(content, _json_bytes(content))

    with pytest.raises(PackageValidationError, match="requires Prop .* to be active"):
        _validate(content, manifest)


def test_rejects_prop_evidence_for_a_distractor() -> None:
    content, manifest = _valid_documents()
    comparison = manifest["proposals"][1]  # type: ignore[index]
    comparison["evidence"] = [
        {
            "kind": "prop",
            "evidence_id": "evidence-distractor",
            "prop_id": content["scenes"][1]["prop_ids"][0],  # type: ignore[index]
        }
    ]

    with pytest.raises(PackageValidationError, match="exactly match"):
        _validate(content, manifest)


def test_schema_exposes_typed_prop_relevance() -> None:
    manifest_schema = AuthoringManifest.model_json_schema()
    judgment_schema = manifest_schema["$defs"]["PropRelevanceJudgment"]

    assert judgment_schema["properties"]["relevance"]["enum"] == [
        "relevant",
        "distractor",
    ]
