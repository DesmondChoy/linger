"""Repair observed candidate inventory faults within the existing single retry."""

import asyncio
import json

import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from src.linger.agents.librarian.agent import build_librarian_agent
from src.linger.agents.librarian.models import (
    BoundaryInferenceDecision,
    boundary_candidate_inventory_errors,
)
from src.linger.agents.librarian.skills import BOUNDARY_INFERENCE
from tests.test_boundary_event_resolution import identified_stop, request


def test_nested_inventory_is_required_even_when_the_array_would_be_empty():
    payload = identified_stop().model_dump(mode="json")
    del payload["event_resolution"]["other_evidence_ids"]
    with pytest.raises(ValidationError, match="event_resolution.other_evidence_ids"):
        BoundaryInferenceDecision.model_validate(payload)


@pytest.mark.parametrize(
    "fault", ["misplaced", "deleted", "memory_omitted", "duplicate_and_memory_omitted"]
)
def test_inventory_repair_reports_all_errors_before_consuming_retry(fault):
    complete = identified_stop().model_dump(mode="json")
    invalid = identified_stop().model_dump(mode="json")
    if fault == "misplaced":
        invalid["other_evidence_ids"] = invalid["event_resolution"].pop(
            "other_evidence_ids"
        )
    elif fault == "deleted":
        del invalid["event_resolution"]["other_evidence_ids"]
    else:
        invalid["event_resolution"]["other_evidence_ids"] = (
            ["other-return"] if fault == "duplicate_and_memory_omitted" else []
        )
    calls = []

    def model(messages, info):
        calls.append(messages)
        if len(calls) == 1:
            output = invalid
        else:
            retry = next(
                part
                for message in reversed(messages)
                for part in message.parts
                if isinstance(part, RetryPromptPart)
            )
            repair = json.loads(retry.content)
            inventory = next(
                error for error in repair["errors"] if "missing_evidence_ids" in error
            )
            assert inventory["missing_evidence_ids"] == ["earlier-event"]
            assert inventory["duplicate_evidence_ids"] == (
                ["other-return"] if fault == "duplicate_and_memory_omitted" else []
            )
            assert "event_resolution.other_evidence_ids" in repair["repair"]
            assert "memory" in repair["repair"]
            if fault in {"misplaced", "deleted"}:
                assert any(
                    error["path"] == "event_resolution.other_evidence_ids"
                    for error in repair["errors"]
                )
            output = complete
        tool = next(
            tool
            for tool in info.output_tools
            if tool.name.endswith("BoundaryInferenceDecision")
        )
        return ModelResponse(parts=[ToolCallPart(tool.name, output)])

    result = asyncio.run(
        build_librarian_agent(FunctionModel(model)).run(
            request().model_dump_json(),
            **BOUNDARY_INFERENCE.run_options(),
        )
    )
    assert len(calls) == 2
    assert result.output == identified_stop()


def test_inventory_validation_names_unknown_ids_without_rewriting_output():
    payload = identified_stop().model_dump(mode="json")
    payload["event_resolution"]["other_evidence_ids"].append("invented")
    errors = boundary_candidate_inventory_errors(payload, request())
    assert errors[0]["unknown_evidence_ids"] == ["invented"]
    assert payload["event_resolution"]["other_evidence_ids"] == [
        "earlier-event",
        "invented",
    ]


def test_repeated_inventory_fault_still_exhausts_one_retry_without_a_grant():
    payload = identified_stop().model_dump(mode="json")
    payload["event_resolution"]["other_evidence_ids"] = []
    calls = []

    def model(messages, info):
        calls.append(messages)
        tool = next(
            tool
            for tool in info.output_tools
            if tool.name.endswith("BoundaryInferenceDecision")
        )
        return ModelResponse(parts=[ToolCallPart(tool.name, payload)])

    with pytest.raises(UnexpectedModelBehavior):
        asyncio.run(
            build_librarian_agent(FunctionModel(model)).run(
                request().model_dump_json(),
                **BOUNDARY_INFERENCE.run_options(),
            )
        )
    assert len(calls) == 2


def test_missing_inventory_and_selected_support_are_repaired_together():
    complete = identified_stop().model_dump(mode="json")
    invalid = identified_stop().model_dump(mode="json")
    invalid["event_resolution"]["other_evidence_ids"] = []
    invalid["supporting_evidence"] = [a for a in invalid["supporting_evidence"] if a["evidence_id"] != "current-event"]
    calls = []

    def model(messages, info):
        calls.append(messages)
        if len(calls) > 1:
            retry = next(part for message in reversed(messages) for part in message.parts
                         if isinstance(part, RetryPromptPart))
            errors = json.loads(retry.content)["errors"]
            by_path = {error["path"]: error for error in errors}
            assert by_path["event_resolution"]["missing_evidence_ids"] == ["earlier-event"]
            assert by_path["supporting_evidence"]["missing_evidence_ids"] == ["current-event"]
        tool = next(tool for tool in info.output_tools
                    if tool.name.endswith("BoundaryInferenceDecision"))
        return ModelResponse(parts=[ToolCallPart(tool.name, invalid if len(calls) == 1 else complete)])

    result = asyncio.run(build_librarian_agent(FunctionModel(model)).run(
        request().model_dump_json(), **BOUNDARY_INFERENCE.run_options(),
    ))
    assert len(calls) == 2
    assert result.output == identified_stop()


@pytest.mark.parametrize("repair_memory", [True, False])
def test_memory_typo_and_inventory_faults_share_the_single_repair(repair_memory):
    complete = identified_stop().model_dump(mode="json")
    invalid = identified_stop().model_dump(mode="json")
    invalid["memory_assessments"][0]["memory_id"] = "eariler"
    invalid["supporting_memory_ids"] = ["eariler"]
    invalid["event_resolution"]["other_evidence_ids"] = ["current-event"]
    invalid["supporting_evidence"] = [
        anchor for anchor in invalid["supporting_evidence"]
        if anchor["evidence_id"] != "current-event"
    ]
    original = json.dumps(invalid, sort_keys=True)
    calls = []

    def model(messages, info):
        calls.append(messages)
        output = invalid
        if len(calls) > 1:
            retry = next(part for message in reversed(messages) for part in message.parts
                         if isinstance(part, RetryPromptPart))
            errors = json.loads(retry.content)["errors"]
            by_path = {error["path"]: error for error in errors}
            memory = by_path["memory_assessments"]
            assert memory["required_memory_ids"] == ["earlier"]
            assert memory["actual_memory_ids"] == ["eariler"]
            assert memory["missing_memory_ids"] == ["earlier"]
            assert memory["unknown_memory_ids"] == ["eariler"]
            assert by_path["supporting_memory_ids"]["unknown_memory_ids"] == ["eariler"]
            assert by_path["event_resolution"]["missing_evidence_ids"] == ["earlier-event"]
            assert by_path["event_resolution"]["duplicate_evidence_ids"] == ["current-event"]
            assert by_path["supporting_evidence"]["missing_evidence_ids"] == ["current-event"]
            output = json.loads(json.dumps(complete))
            if not repair_memory:
                output["memory_assessments"][0]["memory_id"] = "eariler"
                output["supporting_memory_ids"] = ["eariler"]
        tool = next(tool for tool in info.output_tools
                    if tool.name.endswith("BoundaryInferenceDecision"))
        return ModelResponse(parts=[ToolCallPart(tool.name, output)])

    run = build_librarian_agent(FunctionModel(model)).run(
        request().model_dump_json(), **BOUNDARY_INFERENCE.run_options(),
    )
    if repair_memory:
        assert asyncio.run(run).output == identified_stop()
    else:
        with pytest.raises(UnexpectedModelBehavior):
            asyncio.run(run)
    assert len(calls) == 2
    assert json.dumps(invalid, sort_keys=True) == original


@pytest.mark.parametrize("resolution", [None, {"occurrences": None}])
def test_memory_identity_faults_are_reported_with_malformed_event_inventory(resolution):
    output = identified_stop().model_dump(mode="json")
    output["memory_assessments"] *= 2
    output["supporting_memory_ids"] = ["invented", "invented"]
    output["event_resolution"] = resolution
    errors = boundary_candidate_inventory_errors(output, request())
    by_path = {error["path"]: error for error in errors}
    assert by_path["memory_assessments"]["duplicate_memory_ids"] == ["earlier"]
    assert by_path["supporting_memory_ids"]["unknown_memory_ids"] == ["invented"]
    assert by_path["supporting_memory_ids"]["missing_memory_ids"] == ["earlier"]


def test_raw_memory_support_preserves_mixed_assessment_semantics():
    task = request()
    task = task.model_copy(update={"relevant_memories": (
        *task.relevant_memories,
        task.relevant_memories[0].model_copy(update={"memory_id": "unrelated"}),
    )})
    output = identified_stop().model_dump(mode="json")
    output["memory_assessments"].append({
        "memory_id": "unrelated", "status": "not_supported", "evidence_ids": [],
        "reason": "This memory does not establish reading progress.",
    })
    assert boundary_candidate_inventory_errors(output, task) == []
    output["supporting_memory_ids"].append("unrelated")
    errors = boundary_candidate_inventory_errors(output, task)
    assert any(error["path"] == "supporting_memory_ids"
               and error["unexpected_memory_ids"] == ["unrelated"] for error in errors)
