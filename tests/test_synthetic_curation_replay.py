"""Tests for package-backed bounded-curation replay."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import logfire
import pytest
from logfire.testing import TestExporter
from pydantic_ai.models.test import TestModel

from evals.sculptor.harness import ExpectedCurationProposal
from evals.synthetic_journals.adoption import build_ground_truth_adoption
from evals.synthetic_journals.curation_replay import (
    CURATION_OBJECTIVE_ID,
    build_curation_identities,
    main as curation_main,
    replay_curation_scenes,
)
from evals.synthetic_journals.models import ProposedGroundTruth, SyntheticBackstory
from evals.synthetic_journals.replay import RUNTIME_PROMPT_FINGERPRINTS
from evals.synthetic_journals.validate_package import (
    PackageValidationError,
    validate_package,
)
from src.linger.agents.contracts import PromptFingerprint
from src.linger.agents.sculptor.agent import build_sculptor_agent
from src.linger.agents.sculptor.models import (
    AccountScopedMemories,
    CurationProposal,
    DerivedSummary,
    DuplicateLink,
    NoCurationProposal,
    SculptorResponse,
    TopicGroup,
)
from src.linger.orchestration.curation import propose_curation


def _json_bytes(document: dict[str, object]) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _curation_documents() -> tuple[dict[str, object], dict[str, object], bytes]:
    cases = (
        (
            "exact",
            "exact_duplicate",
            (
                "I usually read for twenty minutes before bed.",
                "I usually read for twenty minutes before bed.",
            ),
            (0, 1),
        ),
        (
            "paraphrase",
            "paraphrased_duplicate",
            (
                "Sketching after work helps me settle down.",
                "I unwind in the evening by drawing for a while.",
            ),
            (0, 1),
        ),
        (
            "summary",
            "noisy_memory_summary",
            (
                "A short walk after work clears my head.",
                "Rain is fine, but I prefer walking without headphones.",
                "The number 14 bus was late this morning.",
            ),
            (0, 1),
        ),
        (
            "topic",
            "related_topic_group",
            (
                "A quiet cup of tea helps me shift out of work mode.",
                "Reading fiction is another gentle end-of-day ritual.",
                "I need to replace the kitchen tap washer.",
            ),
            (0, 1),
        ),
        (
            "no-change",
            "superficial_similarity_no_change",
            (
                "Alice showed me how to book the meeting room.",
                "The database book uses Alice as a sample user.",
            ),
            (),
        ),
    )

    props: list[dict[str, object]] = []
    scenes: list[dict[str, object]] = []
    proposals: list[dict[str, object]] = []
    for order, (slug, behavior, texts, expected_indexes) in enumerate(cases, start=1):
        scene_id = f"scene-{slug}"
        prop_ids = tuple(f"prop-{slug}-{index}" for index in range(1, len(texts) + 1))
        for prop_id, text in zip(prop_ids, texts, strict=True):
            props.append(
                {
                    "prop_id": prop_id,
                    "backstory_id": "backstory-curation",
                    "person_id": "person-curation",
                    "evaluation_account_id": "account-curation",
                    "source_text": text,
                    "lifecycle": [{"scene_id": scene_id, "state": "active"}],
                }
            )
        scenes.append(
            {
                "scene_id": scene_id,
                "backstory_id": "backstory-curation",
                "objective_ids": [CURATION_OBJECTIVE_ID],
                "order": order,
                "fresh_session": True,
                "prop_ids": list(prop_ids),
                "line_ids": [],
                "offline_input_ids": [],
            }
        )

        expected_source_ids = [prop_ids[index] for index in expected_indexes]
        if behavior in {"exact_duplicate", "paraphrased_duplicate"}:
            expected: dict[str, object] = {
                "kind": "curation_proposal",
                "action": {
                    "action": "link_duplicates",
                    "source_memory_ids": expected_source_ids,
                },
            }
        elif behavior == "noisy_memory_summary":
            expected = {
                "kind": "curation_proposal",
                "action": {
                    "action": "update_derived_summary",
                    "source_memory_ids": expected_source_ids,
                    "max_summary_words": 40,
                    "semantic_review": {
                        "criteria": ["Uses only the two cited walking records."],
                        "forbidden_claims": ["The bus delay affected the walk."],
                    },
                },
            }
        elif behavior == "related_topic_group":
            expected = {
                "kind": "curation_proposal",
                "action": {
                    "action": "assign_topic_group",
                    "source_memory_ids": expected_source_ids,
                    "semantic_review": {
                        "criteria": ["Names a coherent end-of-day theme."],
                        "forbidden_claims": ["The tap repair is restorative."],
                    },
                },
            }
        else:
            expected = {
                "kind": "no_curation_proposal",
                "reason_category": "superficial_similarity",
            }

        proposals.append(
            {
                "proposal_id": f"proposal-{slug}",
                "scene_id": scene_id,
                "objective_id": CURATION_OBJECTIVE_ID,
                "expected_outcomes": ["Sculptor returns the proposed response kind."],
                "prohibited_outcomes": ["Sculptor claims to modify source memory."],
                "exact_spans": [
                    {
                        "source_kind": "prop",
                        "source_id": prop_id,
                        "start_codepoint": 0,
                        "end_codepoint": len(text),
                        "text": text,
                    }
                    for prop_id, text in zip(prop_ids, texts, strict=True)
                ],
                "evidence": [
                    {
                        "kind": "prop",
                        "evidence_id": f"evidence-{prop_id}",
                        "prop_id": prop_id,
                    }
                    for prop_id in prop_ids
                ],
                "curation": {
                    "primary_behavior": behavior,
                    "expected": expected,
                },
            }
        )

    backstory: dict[str, object] = {
        "objective_ids": [CURATION_OBJECTIVE_ID],
        "run_configuration_ids": [],
        "backstory": {
            "backstory_id": "backstory-curation",
            "person_id": "person-curation",
            "evaluation_account_id": "account-curation",
            "context": "A person is reflecting on routines and practical errands.",
        },
        "props": props,
        "scenes": scenes,
        "lines": [],
        "offline_inputs": [],
    }
    backstory_bytes = _json_bytes(backstory)
    ground_truth: dict[str, object] = {
        "backstory_sha256": hashlib.sha256(backstory_bytes).hexdigest(),
        "ground_truth_status": "proposed",
        "proposals": proposals,
    }
    return backstory, ground_truth, backstory_bytes


def _curation_models() -> tuple[SyntheticBackstory, ProposedGroundTruth, bytes]:
    backstory, ground_truth, backstory_bytes = _curation_documents()
    return (
        SyntheticBackstory.model_validate_json(backstory_bytes),
        ProposedGroundTruth.model_validate_json(_json_bytes(ground_truth)),
        backstory_bytes,
    )


def _response_for(
    batch: AccountScopedMemories,
    ground_truth: ProposedGroundTruth,
) -> SculptorResponse:
    scene_slug = batch.memories[0].memory_id.removeprefix("prop-").rsplit("-", 1)[0]
    proposal = next(
        item
        for item in ground_truth.proposals
        if item.scene_id == f"scene-{scene_slug}"
    )
    assert proposal.curation is not None
    expected = proposal.curation.expected
    if not isinstance(expected, ExpectedCurationProposal):
        return NoCurationProposal(
            kind="no_curation_proposal",
            reason="The shared wording refers to unrelated contexts.",
        )
    action = expected.action
    if action.action == "link_duplicates":
        response_action = DuplicateLink(
            action="link_duplicates",
            source_memory_ids=action.source_memory_ids,
        )
    elif action.action == "update_derived_summary":
        response_action = DerivedSummary(
            action="update_derived_summary",
            source_memory_ids=action.source_memory_ids,
            summary="Short walks after work can help, even in rain and without audio.",
        )
    else:
        response_action = TopicGroup(
            action="assign_topic_group",
            source_memory_ids=action.source_memory_ids,
            topic_label="Gentle end-of-day rituals",
        )
    return CurationProposal(kind="curation_proposal", action=response_action)


def test_validates_exactly_one_scene_per_accepted_curation_behavior() -> None:
    backstory, ground_truth, backstory_bytes = _curation_models()

    validate_package(
        backstory,
        ground_truth,
        backstory_bytes=backstory_bytes,
        run_configurations={},
    )

    assert len(backstory.scenes) == 5
    assert not backstory.lines
    assert not backstory.offline_inputs
    assert {
        proposal.curation.primary_behavior
        for proposal in ground_truth.proposals
        if proposal.curation is not None
    } == {
        "exact_duplicate",
        "paraphrased_duplicate",
        "noisy_memory_summary",
        "related_topic_group",
        "superficial_similarity_no_change",
    }


def test_rejects_missing_ground_truth_inactive_props_and_duplicate_evidence() -> None:
    backstory, ground_truth, backstory_bytes = _curation_models()

    missing_curation = ground_truth.model_copy(
        update={
            "proposals": (
                ground_truth.proposals[0].model_copy(update={"curation": None}),
                *ground_truth.proposals[1:],
            )
        }
    )
    with pytest.raises(PackageValidationError, match="lacks typed curation"):
        validate_package(
            backstory,
            missing_curation,
            backstory_bytes=backstory_bytes,
            run_configurations={},
        )

    first_prop = backstory.props[0]
    inactive_prop = first_prop.model_copy(
        update={
            "lifecycle": (
                first_prop.lifecycle[0].model_copy(update={"state": "inactive"}),
            )
        }
    )
    inactive_backstory = backstory.model_copy(
        update={"props": (inactive_prop, *backstory.props[1:])}
    )
    with pytest.raises(PackageValidationError, match="must be active"):
        validate_package(
            inactive_backstory,
            ground_truth,
            backstory_bytes=backstory_bytes,
            run_configurations={},
        )

    exact = ground_truth.proposals[0]
    duplicate_evidence = exact.model_copy(
        update={"evidence": (*exact.evidence, exact.evidence[0])}
    )
    invalid_evidence = ground_truth.model_copy(
        update={"proposals": (duplicate_evidence, *ground_truth.proposals[1:])}
    )
    with pytest.raises(PackageValidationError, match="exactly once"):
        validate_package(
            backstory,
            invalid_evidence,
            backstory_bytes=backstory_bytes,
            run_configurations={},
        )


def test_rejects_duplicate_or_unsupported_expected_source_ids() -> None:
    backstory, ground_truth, backstory_bytes = _curation_models()
    proposal = ground_truth.proposals[0]
    assert proposal.curation is not None
    expected = proposal.curation.expected
    assert isinstance(expected, ExpectedCurationProposal)
    source_id = expected.action.source_memory_ids[0]
    duplicate_action = expected.action.model_copy(
        update={"source_memory_ids": (source_id, source_id)}
    )
    duplicate_expected = expected.model_copy(update={"action": duplicate_action})
    duplicate_curation = proposal.curation.model_copy(
        update={"expected": duplicate_expected}
    )
    invalid_sources = ground_truth.model_copy(
        update={
            "proposals": (
                proposal.model_copy(update={"curation": duplicate_curation}),
                *ground_truth.proposals[1:],
            )
        }
    )

    with pytest.raises(PackageValidationError, match="duplicate expected source IDs"):
        validate_package(
            backstory,
            invalid_sources,
            backstory_bytes=backstory_bytes,
            run_configurations={},
        )

    missing_span = ground_truth.model_copy(
        update={
            "proposals": (
                proposal.model_copy(update={"exact_spans": proposal.exact_spans[:1]}),
                *ground_truth.proposals[1:],
            )
        }
    )
    with pytest.raises(PackageValidationError, match="lacks exact spans"):
        validate_package(
            backstory,
            missing_span,
            backstory_bytes=backstory_bytes,
            run_configurations={},
        )


def test_replay_resolves_active_same_account_props_and_all_outcomes() -> None:
    backstory, ground_truth, _ = _curation_models()
    observed_batches: list[AccountScopedMemories] = []

    async def handler(batch: AccountScopedMemories) -> SculptorResponse:
        observed_batches.append(batch)
        return _response_for(batch, ground_truth)

    result = asyncio.run(
        replay_curation_scenes(
            backstory,
            ground_truth,
            curation_handler=handler,
            configured_model="test:curation-model",
        )
    )

    assert len(observed_batches) == 5
    assert {batch.account_scope for batch in observed_batches} == {"account-curation"}
    assert [
        tuple(memory.memory_id for memory in batch.memories)
        for batch in observed_batches
    ] == [scene.prop_ids for scene in backstory.scenes]
    assert {scene.response.kind for scene in result.scenes} == {
        "curation_proposal",
        "no_curation_proposal",
    }
    assert all(
        scene.ground_truth_result == "matches_proposal" for scene in result.scenes
    )
    assert all(scene.grade.hard_pass for scene in result.scenes)
    assert all(
        scene.source_hashes_before == scene.source_hashes_after
        for scene in result.scenes
    )
    assert all(scene.source_immutable for scene in result.scenes)
    assert result.ground_truth_status == "proposed"
    assert result.content_classification == "synthetic"


def test_replay_grades_adopted_curation_hard_gates() -> None:
    backstory, ground_truth, _ = _curation_models()
    ground_truth_bytes = ground_truth.model_dump_json().encode("utf-8")
    adoption = build_ground_truth_adoption(
        ground_truth,
        ground_truth_bytes,
        reviewer_id="independent.developer@example.com",
    )

    async def handler(batch: AccountScopedMemories) -> SculptorResponse:
        return _response_for(batch, ground_truth)

    result = asyncio.run(
        replay_curation_scenes(
            backstory,
            ground_truth,
            adoption=adoption,
            curation_handler=handler,
            configured_model="test:curation-model",
        )
    )

    assert result.ground_truth_status == "adopted"
    assert result.dataset_version == adoption.adopted_ground_truth_identity
    assert all(
        scene.ground_truth_result == "passes_hard_gates"
        for scene in result.scenes
    )


def test_production_boundary_has_no_tools_writes_or_ground_truth_input() -> None:
    backstory, ground_truth, _ = _curation_models()
    models: list[TestModel] = []
    original_props = tuple(prop.source_text for prop in backstory.props)

    async def handler(batch: AccountScopedMemories) -> SculptorResponse:
        response = _response_for(batch, ground_truth)
        model = TestModel(
            custom_output_args=response,
            seed=1 if isinstance(response, NoCurationProposal) else 0,
        )
        models.append(model)
        return await propose_curation(batch, agent=build_sculptor_agent(model))

    result = asyncio.run(
        replay_curation_scenes(
            backstory,
            ground_truth,
            curation_handler=handler,
            configured_model="test:curation-model",
        )
    )

    assert tuple(prop.source_text for prop in backstory.props) == original_props
    assert len(models) == len(backstory.scenes)
    assert all(model.last_model_request_parameters is not None for model in models)
    assert all(
        model.last_model_request_parameters.function_tools == []  # type: ignore[union-attr]
        for model in models
    )
    assert all(len(scene.agent_exchanges) == 1 for scene in result.scenes)
    prompts = "\n".join(
        scene.agent_exchanges[0].input_prompt for scene in result.scenes
    )
    assert backstory.backstory.context not in prompts
    assert "expected_outcomes" not in prompts
    assert "account-curation" not in prompts


def test_production_replay_uses_the_established_synthetic_telemetry_boundary() -> None:
    backstory, ground_truth, _ = _curation_models()
    evaluation_agent_set = (object(),)

    async def response(batch: AccountScopedMemories) -> SculptorResponse:
        return _response_for(batch, ground_truth)

    with (
        patch(
            "evals.synthetic_journals.curation_replay.evaluation_agents",
            return_value=evaluation_agent_set,
        ),
        patch(
            "evals.synthetic_journals.curation_replay."
            "configure_synthetic_evaluation_telemetry"
        ) as configure,
        patch(
            "evals.synthetic_journals.curation_replay.propose_curation",
            new=AsyncMock(side_effect=response),
        ),
    ):
        result = asyncio.run(replay_curation_scenes(backstory, ground_truth))

    configure.assert_called_once_with(evaluation_agent_set)
    assert len(result.scenes) == 5


def test_replay_fails_if_a_handler_mutates_supplied_source_content() -> None:
    backstory, ground_truth, _ = _curation_models()

    async def mutating_handler(batch: AccountScopedMemories) -> SculptorResponse:
        object.__setattr__(batch.memories[0], "text", "mutated source")
        return _response_for(batch, ground_truth)

    with pytest.raises(RuntimeError, match="synthetic curation cases failed"):
        asyncio.run(
            replay_curation_scenes(
                backstory,
                ground_truth,
                curation_handler=mutating_handler,
                configured_model="test:curation-model",
            )
        )


def test_objective_identity_ignores_inactive_prompt_changes() -> None:
    inactive_a = PromptFingerprint(
        template_id="inactive.prompt",
        version="1",
        digest="1" * 64,
    )
    inactive_b = inactive_a.model_copy(update={"digest": "2" * 64})
    first = build_curation_identities(
        configured_model="test:curation-model",
        full_prompt_fingerprints=(*RUNTIME_PROMPT_FINGERPRINTS, inactive_a),
    )
    second = build_curation_identities(
        configured_model="test:curation-model",
        full_prompt_fingerprints=(*RUNTIME_PROMPT_FINGERPRINTS, inactive_b),
    )

    assert first.full_deployment.digest != second.full_deployment.digest
    assert first.objective_execution.digest == second.objective_execution.digest
    assert first.full_deployment.purpose == "full_deployment_lineage"
    assert first.objective_execution.purpose == "objective_execution_comparison"


def test_replay_exports_synthetic_native_evaluation_cases() -> None:
    backstory, ground_truth, _ = _curation_models()
    exporter = TestExporter()
    logfire.configure(
        send_to_logfire=False,
        console=False,
        inspect_arguments=False,
        additional_span_processors=[logfire.testing.SimpleSpanProcessor(exporter)],
    )

    async def handler(batch: AccountScopedMemories) -> SculptorResponse:
        return _response_for(batch, ground_truth)

    result = asyncio.run(
        replay_curation_scenes(
            backstory,
            ground_truth,
            curation_handler=handler,
            configured_model="test:curation-model",
        )
    )
    spans = exporter.exported_spans_as_dict()
    experiment = next(span for span in spans if span["name"] == "evaluate {name}")
    cases = [span for span in spans if span["name"] == "case: {case_name}"]
    metadata = experiment["attributes"]["metadata"]

    assert experiment["attributes"]["dataset_name"] == CURATION_OBJECTIVE_ID
    assert "synthetic" in metadata
    assert result.identities.full_deployment.digest in metadata
    assert result.identities.objective_execution.digest in metadata
    assert len(cases) == 5
    assert {
        json.loads(case["attributes"]["labels"])["proposal_comparison"]["value"]
        for case in cases
    } == {"matches_proposal"}


def test_cli_returns_nonzero_for_an_invalid_package(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = curation_main(
        [
            str(tmp_path / "missing-backstory.json"),
            str(tmp_path / "missing-ground-truth.json"),
        ]
    )

    assert result == 1
    assert "EVALUATION_RUN_ERROR=" in capsys.readouterr().err
