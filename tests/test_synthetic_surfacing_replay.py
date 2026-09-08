"""Exercise durable surfacing replay, failure denominators, and adoption authority."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import logfire
import pytest
from logfire.testing import TestExporter
from pydantic_ai.models.test import TestModel

from evals.synthetic_journals.adoption import (
    GroundTruthAdoptionError,
    build_ground_truth_adoption,
)
from evals.synthetic_journals.surfacing_contract import compile_surfacing_scenes
from evals.synthetic_journals.surfacing_replay import (
    SurfacingEvaluationRun,
    build_surfacing_identities,
    main,
    replay_surfacing_scenes,
)
from src.linger.agents.contracts import PromptFingerprint
from src.linger.agents.sculptor.surfacing_agent import build_surfacing_agent
from src.linger.agents.sculptor.surfacing_models import (
    Defer,
    DoNotSurface,
    SurfaceNow,
    SurfacingDecision,
    SurfacingInput,
)
from src.linger.orchestration.surfacing import propose_surfacing
from tests.surfacing_fixtures import (
    json_bytes,
    make_surfacing_package,
    surfacing_documents,
)


def _responses():
    backstory, ground_truth = make_surfacing_package()
    scenes = compile_surfacing_scenes(backstory, ground_truth)
    responses = {}
    for scene in scenes:
        expected = scene.expectation
        fields = {
            "decision": expected.decision,
            "source_memory_ids": expected.required_source_ids,
            "rationale": "The bounded evidence supports this decision.",
        }
        if expected.decision == "surface_now":
            response = SurfaceNow(
                suggestion="Revisit the supplied intention.", **fields
            )
        elif expected.decision == "defer":
            response = Defer(
                suggestion="Revisit the supplied intention later.",
                reconsideration=expected.reconsideration,
                **fields,
            )
        else:
            response = DoNotSurface(reason=expected.reason, **fields)
        responses[scene.input.model_dump_json()] = response
    return backstory, ground_truth, scenes, responses


def test_records_ordered_scenes_without_claiming_semantic_quality() -> None:
    backstory, truth, compiled, responses = _responses()
    seen = []

    async def handler(input: SurfacingInput) -> SurfacingDecision:
        seen.append(input)
        return responses[input.model_dump_json()]

    result = asyncio.run(replay_surfacing_scenes(
        backstory, truth, handler=handler, configured_model="test:surfacing"
    ))

    assert seen == [scene.input for scene in compiled]
    assert [scene.scene_id for scene in result.scenes] == [
        scene.scene_id for scene in compiled
    ]
    assert result.ground_truth_status == "proposed"
    assert result.package_bytes_verified is False
    assert all(
        scene.ground_truth_result == "matches_proposal" for scene in result.scenes
    )
    assert all(
        scene.input_immutable and scene.source_immutable for scene in result.scenes
    )
    assert all(
        scene.source_hashes_before == scene.source_hashes_after
        for scene in result.scenes
    )
    assert result.metrics.scene_count == 6
    assert result.metrics.response_count == 6
    assert result.metrics.hard_gate_pass_rate == 1
    assert result.metrics.decision_accuracy == 1
    assert result.metrics.surface_decision_precision == 1
    assert result.metrics.surface_decision_recall == 1
    assert result.metrics.semantic_review_required_count == 6
    assert result.metrics.semantic_quality_evaluated is False
    restored = SurfacingEvaluationRun.model_validate_json(result.model_dump_json())
    assert restored == result


def test_model_and_contract_failures_remain_in_all_metrics_denominators() -> None:
    backstory, truth, compiled, responses = _responses()
    calls = 0

    async def handler(input: SurfacingInput) -> SurfacingDecision:
        nonlocal calls
        calls += 1
        response = responses[input.model_dump_json()]
        if response.decision == "surface_now":
            raise RuntimeError("test provider failed")
        if response.decision == "defer":
            return response.model_copy(
                update={"source_memory_ids": ("unknown-source",)}
            )
        return response

    result = asyncio.run(replay_surfacing_scenes(
        backstory, truth, handler=handler, configured_model="test:surfacing"
    ))

    assert calls == len(compiled)
    assert result.metrics.scene_count == 6
    assert result.metrics.response_count == 5
    assert result.metrics.execution_failure_count == 2
    assert result.metrics.decision_accuracy == pytest.approx(5 / 6)
    assert result.metrics.hard_gate_pass_rate == pytest.approx(4 / 6)
    assert result.metrics.surface_decision_precision is None
    assert result.metrics.surface_decision_recall == 0
    classes = {item.decision: item for item in result.metrics.class_decision_accuracy}
    assert classes["surface_now"].total == 1
    assert classes["surface_now"].accuracy == 0
    assert classes["defer"].accuracy == 1
    assert classes["do_not_surface"].accuracy == 1
    failed = [scene for scene in result.scenes if scene.execution_error is not None]
    assert {scene.execution_error.error_type for scene in failed} == {
        "RuntimeError", "InvalidSurfacingProposal"
    }
    assert sum(scene.response is None for scene in failed) == 1
    assert all(scene.ground_truth_result == "differs_from_proposal" for scene in failed)
    assert all(scene.grade.hard_failures for scene in failed)


@pytest.mark.parametrize("case_kind", ("superseded", "timely"))
@pytest.mark.parametrize("through_runtime", (False, True))
def test_invalid_source_labels_still_count_in_precision_and_recall(
    case_kind: str, through_runtime: bool
) -> None:
    backstory, truth, compiled, responses = _responses()
    target = next(
        scene for scene in compiled if scene.expectation.case_kind == case_kind
    )

    async def handler(input: SurfacingInput) -> SurfacingDecision:
        response = responses[input.model_dump_json()]
        if input == target.input:
            response = SurfaceNow(
                decision="surface_now",
                source_memory_ids=("unknown-source",),
                suggestion="A deliberately unsupported next action.",
                rationale="This label must count even though its source is invalid.",
            )
        if not through_runtime:
            return response
        seed = {"surface_now": 0, "defer": 1, "do_not_surface": 2}[response.decision]
        model = TestModel(custom_output_args=response, seed=seed)
        return await propose_surfacing(input, agent=build_surfacing_agent(model))

    result = asyncio.run(replay_surfacing_scenes(
        backstory, truth, handler=handler, configured_model="test:surfacing"
    ))

    negative = case_kind == "superseded"
    assert result.metrics.scene_count == result.metrics.response_count == 6
    assert result.metrics.execution_failure_count == 1
    assert result.metrics.predicted_surface_count == (2 if negative else 1)
    assert result.metrics.correct_surface_count == 1
    assert result.metrics.surface_decision_precision == (0.5 if negative else 1)
    assert result.metrics.surface_decision_recall == 1
    assert result.metrics.decision_accuracy == (pytest.approx(5 / 6) if negative else 1)
    assert result.metrics.hard_gate_pass_rate == pytest.approx(5 / 6)
    observation = next(
        scene for scene in result.scenes if scene.scene_id == target.scene_id
    )
    assert observation.response.source_memory_ids == ("unknown-source",)
    assert observation.grade.decision_match is (not negative)
    assert observation.execution_error.code == "invalid_surfacing_proposal"
    assert observation.grade.hard_failures


def test_invalid_schema_counts_as_missing_decision_in_complete_denominator() -> None:
    backstory, truth, _, responses = _responses()

    async def handler(input: SurfacingInput) -> SurfacingDecision:
        response = responses[input.model_dump_json()]
        if response.decision == "surface_now":
            return response.model_copy(update={"suggestion": ""})
        return response

    result = asyncio.run(replay_surfacing_scenes(
        backstory, truth, handler=handler, configured_model="test:surfacing"
    ))

    assert result.metrics.scene_count == 6
    assert result.metrics.response_count == 5
    assert result.metrics.execution_failure_count == 1
    assert result.metrics.decision_accuracy == pytest.approx(5 / 6)
    assert result.metrics.hard_gate_pass_rate == pytest.approx(5 / 6)
    assert result.metrics.surface_decision_precision is None
    assert result.metrics.surface_decision_recall == 0
    failed = next(scene for scene in result.scenes if scene.execution_error is not None)
    assert failed.response is None
    assert failed.grade.decision_match is False
    assert failed.execution_error.code == "invalid_surfacing_proposal"


def test_false_positive_surface_is_counted_separately_from_source_hard_gates() -> None:
    backstory, truth, _, responses = _responses()

    async def handler(input: SurfacingInput) -> SurfacingDecision:
        response = responses[input.model_dump_json()]
        if response.decision == "do_not_surface" and response.reason == "superseded":
            return SurfaceNow(
                decision="surface_now",
                source_memory_ids=(input.memories[0].memory_id,),
                suggestion="Follow the old intention.",
                rationale="Ignoring the cancellation is deliberately incorrect.",
            )
        return response

    result = asyncio.run(replay_surfacing_scenes(
        backstory, truth, handler=handler, configured_model="test:surfacing"
    ))

    assert result.metrics.predicted_surface_count == 2
    assert result.metrics.correct_surface_count == 1
    assert result.metrics.surface_decision_precision == 0.5
    assert result.metrics.surface_decision_recall == 1
    assert result.metrics.decision_accuracy == pytest.approx(5 / 6)
    assert result.metrics.hard_gate_pass_rate == pytest.approx(5 / 6)


def test_source_mutation_fails_without_contaminating_later_scenes() -> None:
    backstory, truth, _, responses = _responses()
    original = backstory.model_dump_json()
    calls = 0

    async def handler(input: SurfacingInput) -> SurfacingDecision:
        nonlocal calls
        calls += 1
        response = responses[input.model_dump_json()]
        if calls == 1:
            object.__setattr__(input.memories[0], "text", "mutated test source")
        return response

    result = asyncio.run(replay_surfacing_scenes(
        backstory, truth, handler=handler, configured_model="test:surfacing"
    ))

    assert calls == 6
    assert backstory.model_dump_json() == original
    assert result.scenes[0].source_immutable is False
    assert result.scenes[0].input_immutable is False
    assert result.scenes[0].source_hashes_before != result.scenes[0].source_hashes_after
    assert "supplied_input_changed" in result.scenes[0].grade.hard_failures
    assert all(scene.source_immutable for scene in result.scenes[1:])
    assert result.metrics.hard_gate_pass_rate == pytest.approx(5 / 6)


def test_adopted_grading_requires_exact_complete_ground_truth_bytes() -> None:
    backstory, truth, _, responses = _responses()
    _, _, backstory_bytes = surfacing_documents()
    truth_bytes = truth.model_dump_json().encode("utf-8")
    adoption = build_ground_truth_adoption(
        truth, truth_bytes, reviewer_id="independent-test-reviewer"
    )

    async def handler(input: SurfacingInput) -> SurfacingDecision:
        return responses[input.model_dump_json()]

    result = asyncio.run(replay_surfacing_scenes(
        backstory, truth, adoption=adoption, backstory_bytes=backstory_bytes,
        ground_truth_bytes=truth_bytes,
        handler=handler, configured_model="test:surfacing",
    ))
    assert result.ground_truth_status == "adopted"
    assert result.dataset_version == adoption.adopted_ground_truth_identity
    assert result.package_bytes_verified is True
    assert all(
        scene.ground_truth_result == "passes_hard_gates" for scene in result.scenes
    )
    assert result.metrics.semantic_quality_evaluated is False

    with patch(
        "evals.synthetic_journals.surfacing_replay."
        "configure_synthetic_evaluation_telemetry"
    ) as configure:
        with pytest.raises(
            ValueError, match="exact backstory_bytes and ground_truth_bytes"
        ):
            asyncio.run(replay_surfacing_scenes(backstory, truth, adoption=adoption))
        with pytest.raises(GroundTruthAdoptionError, match="exact file bytes"):
            asyncio.run(replay_surfacing_scenes(
                backstory, truth, adoption=adoption, backstory_bytes=backstory_bytes,
                ground_truth_bytes=truth_bytes + b"\n"
            ))
        truncated = adoption.model_copy(update={"decisions": adoption.decisions[:-1]})
        with pytest.raises(GroundTruthAdoptionError, match="every proposal"):
            asyncio.run(replay_surfacing_scenes(
                backstory, truth, adoption=truncated, backstory_bytes=backstory_bytes,
                ground_truth_bytes=truth_bytes
            ))
        changed_backstory = backstory.model_copy(update={
            "backstory": backstory.backstory.model_copy(update={"context": "changed"})
        })
        with pytest.raises(ValueError, match="Backstory bytes do not describe"):
            asyncio.run(replay_surfacing_scenes(
                changed_backstory, truth, adoption=adoption,
                backstory_bytes=backstory_bytes, ground_truth_bytes=truth_bytes,
            ))
        with pytest.raises(ValueError, match="backstory_sha256"):
            asyncio.run(replay_surfacing_scenes(
                changed_backstory, truth, adoption=adoption,
                backstory_bytes=changed_backstory.model_dump_json().encode(),
                ground_truth_bytes=truth_bytes,
            ))
        configure.assert_not_called()


def test_runtime_transcripts_exclude_answer_key_account_and_backstory_context() -> None:
    backstory, truth, _, responses = _responses()
    models = []

    async def handler(input: SurfacingInput) -> SurfacingDecision:
        response = responses[input.model_dump_json()]
        seed = {"surface_now": 0, "defer": 1, "do_not_surface": 2}[response.decision]
        model = TestModel(custom_output_args=response, seed=seed)
        models.append(model)
        return await propose_surfacing(input, agent=build_surfacing_agent(model))

    result = asyncio.run(replay_surfacing_scenes(
        backstory, truth, handler=handler, configured_model="test:surfacing"
    ))

    assert result.metrics.execution_failure_count == 0
    assert all(len(scene.agent_exchanges) == 1 for scene in result.scenes)
    assert all(
        model.last_model_request_parameters.function_tools == [] for model in models
    )
    prompts = "\n".join(
        scene.agent_exchanges[0].input_prompt for scene in result.scenes
    )
    assert backstory.backstory.evaluation_account_id not in prompts
    assert backstory.backstory.context not in prompts
    assert "semantic_criteria" not in prompts
    assert "required_source_ids" not in prompts
    assert "current_context" in prompts
    assert "now" in prompts


def test_native_synthetic_evaluation_spans_include_failed_scenes() -> None:
    backstory, truth = make_surfacing_package()
    secret_marker = "PROVIDER_EXCEPTION_SECRET_MUST_NOT_BE_EXPORTED"
    exporter = TestExporter()
    logfire.configure(
        send_to_logfire=False, console=False, inspect_arguments=False,
        additional_span_processors=[logfire.testing.SimpleSpanProcessor(exporter)],
    )

    async def handler(input: SurfacingInput) -> SurfacingDecision:
        raise RuntimeError(secret_marker)

    result = asyncio.run(replay_surfacing_scenes(
        backstory, truth, handler=handler, configured_model="test:surfacing"
    ))

    spans = exporter.exported_spans_as_dict()
    assert secret_marker not in json.dumps(spans)
    assert secret_marker not in result.model_dump_json()
    assert all(
        scene.execution_error.code == "surfacing_model_failed"
        for scene in result.scenes
    )
    experiment = next(span for span in spans if span["name"] == "evaluate {name}")
    cases = [span for span in spans if span["name"] == "case: {case_name}"]
    assert experiment["attributes"]["dataset_name"] == "proactive_memory_surfacing"
    assert "synthetic" in experiment["attributes"]["metadata"]
    assert len(cases) == 6
    assert {
        json.loads(case["attributes"]["labels"])["proposal_comparison"]["value"]
        for case in cases
    } == {"differs_from_proposal"}
    assert result.metrics.scene_count == result.metrics.execution_failure_count == 6
    assert result.metrics.decision_accuracy == 0
    assert result.metrics.hard_gate_pass_rate == 0
    assert result.metrics.surface_decision_precision is None
    assert result.metrics.surface_decision_recall == 0


def test_objective_identity_is_independent_of_unexecuted_agent_prompts() -> None:
    first_prompt = PromptFingerprint(
        template_id="unexecuted", version="1", digest="1" * 64
    )
    second_prompt = first_prompt.model_copy(update={"digest": "2" * 64})
    first = build_surfacing_identities(
        configured_model="test:surfacing", full_prompt_fingerprints=(first_prompt,)
    )
    second = build_surfacing_identities(
        configured_model="test:surfacing", full_prompt_fingerprints=(second_prompt,)
    )
    assert first.full_deployment.digest != second.full_deployment.digest
    assert first.objective_execution.digest == second.objective_execution.digest


def test_cli_validates_before_provider_access_and_writes_durable_failure_artifact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    backstory, truth, backstory_bytes = surfacing_documents()
    backstory_path = tmp_path / "backstory.json"
    truth_path = tmp_path / "ground-truth.json"
    output_path = tmp_path / "replay.json"
    backstory_path.write_bytes(backstory_bytes)
    truth_path.write_bytes(json_bytes(truth))
    with (
        patch(
            "evals.synthetic_journals.surfacing_replay._production_components",
            return_value=(
                AsyncMock(side_effect=RuntimeError("test provider failed")), ()
            ),
        ) as components,
        patch(
            "evals.synthetic_journals.surfacing_replay."
            "configure_synthetic_evaluation_telemetry"
        ) as configure,
    ):
        assert main([
            str(backstory_path), str(truth_path), "--output", str(output_path)
        ]) == 0
        handler = components.return_value[0]
        assert handler.await_count == 6
        configure.assert_called_once()
        artifact = SurfacingEvaluationRun.model_validate_json(output_path.read_bytes())
        assert artifact.metrics.execution_failure_count == 6
        handler.reset_mock()
        configure.reset_mock()
        truth_path.write_text("{}", encoding="utf-8")
        assert main([str(backstory_path), str(truth_path)]) == 1
        handler.assert_not_awaited()
        configure.assert_not_called()
    assert "EVALUATION_RUN_ERROR=" in capsys.readouterr().err


def test_invalid_cli_package_does_not_initialize_provider(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable, "-m", "evals.synthetic_journals.surfacing_replay",
            str(tmp_path / "missing-backstory.json"),
            str(tmp_path / "missing-ground-truth.json"),
        ],
        env={**os.environ, "LINGER_MODEL": "invalid-provider:test"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "EVALUATION_RUN_ERROR=" in result.stderr
    assert "No such file or directory" in result.stderr
    assert "Unsupported LINGER_MODEL" not in result.stderr
