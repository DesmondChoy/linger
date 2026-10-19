"""The application derives candidate bookkeeping; the model repairs only real faults."""

import asyncio
import json

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from src.linger.agents.librarian.agent import build_librarian_agent
from src.linger.agents.librarian.models import boundary_candidate_inventory_errors
from src.linger.agents.librarian.skills import BOUNDARY_INFERENCE
from tests.test_boundary_event_resolution import identified_stop, request


def run_boundary(outputs):
    """Return each scripted output in turn and record the retry prompts received."""
    calls = []

    def model(messages, info):
        calls.append(messages)
        tool = next(
            tool for tool in info.output_tools
            if tool.name.endswith("BoundaryInferenceDecision")
        )
        return ModelResponse(parts=[ToolCallPart(tool.name, outputs[min(len(calls), len(outputs)) - 1])])

    run = build_librarian_agent(FunctionModel(model)).run(
        request().model_dump_json(), **BOUNDARY_INFERENCE.run_options(),
    )
    return run, calls


def retry_errors(messages):
    retry = next(
        part for message in reversed(messages) for part in message.parts
        if isinstance(part, RetryPromptPart)
    )
    return {error["path"]: error for error in json.loads(retry.content)["errors"]}


@pytest.mark.parametrize("placement", ["nested", "top_level"])
@pytest.mark.parametrize(
    "inventory",
    [[], ["other-return"], ["earlier-event", "invented"], ["current-event", "earlier-event"]],
)
def test_model_written_inventory_is_ignored_without_spending_a_retry(placement, inventory):
    output = identified_stop().model_dump(mode="json")
    target = output["event_resolution"] if placement == "nested" else output
    target["other_evidence_ids"] = inventory
    run, calls = run_boundary([output])
    assert asyncio.run(run).output == identified_stop()
    assert len(calls) == 1


def test_repeated_support_for_one_record_keeps_the_anchor_that_binds():
    output = identified_stop().model_dump(mode="json")
    current = next(a for a in output["supporting_evidence"] if a["evidence_id"] == "current-event")
    output["supporting_evidence"].insert(0, {"evidence_id": "current-event", "source_excerpt": "Not in the record."})
    output["supporting_evidence"].append(dict(current))
    run, calls = run_boundary([output])
    support = asyncio.run(run).output.supporting_evidence
    assert sorted(support, key=lambda a: a.evidence_id) == sorted(
        identified_stop().supporting_evidence, key=lambda a: a.evidence_id,
    )
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("fault", "field"),
    [("invented", "unknown_evidence_ids"), ("other-return", "duplicate_evidence_ids")],
)
def test_occurrence_id_faults_are_repaired_within_the_single_retry(fault, field):
    invalid = identified_stop().model_dump(mode="json")
    invalid["event_resolution"]["occurrences"][0]["evidence_ids"].append(fault)
    run, calls = run_boundary([invalid, identified_stop().model_dump(mode="json")])
    assert asyncio.run(run).output == identified_stop()
    assert len(calls) == 2
    assert retry_errors(calls[1])["event_resolution.occurrences"][field] == [fault]


def test_repeated_occurrence_fault_still_exhausts_one_retry_without_a_grant():
    invalid = identified_stop().model_dump(mode="json")
    invalid["event_resolution"]["occurrences"][1]["evidence_ids"].append("invented")
    run, calls = run_boundary([invalid])
    with pytest.raises(UnexpectedModelBehavior):
        asyncio.run(run)
    assert len(calls) == 2


def test_missing_selected_support_is_repaired():
    invalid = identified_stop().model_dump(mode="json")
    invalid["supporting_evidence"] = [
        a for a in invalid["supporting_evidence"] if a["evidence_id"] != "current-event"
    ]
    run, calls = run_boundary([invalid, identified_stop().model_dump(mode="json")])
    assert asyncio.run(run).output == identified_stop()
    assert retry_errors(calls[1])["supporting_evidence"]["missing_evidence_ids"] == ["current-event"]


@pytest.mark.parametrize("repair_memory", [True, False])
def test_memory_typo_and_support_faults_share_the_single_repair(repair_memory):
    complete = identified_stop().model_dump(mode="json")
    invalid = identified_stop().model_dump(mode="json")
    invalid["memory_assessments"][0]["memory_id"] = "eariler"
    invalid["supporting_memory_ids"] = ["eariler"]
    invalid["supporting_evidence"] = [
        anchor for anchor in invalid["supporting_evidence"]
        if anchor["evidence_id"] != "current-event"
    ]
    original = json.dumps(invalid, sort_keys=True)
    repaired = json.loads(json.dumps(complete))
    if not repair_memory:
        repaired["memory_assessments"][0]["memory_id"] = "eariler"
        repaired["supporting_memory_ids"] = ["eariler"]
    run, calls = run_boundary([invalid, repaired])
    if repair_memory:
        assert asyncio.run(run).output == identified_stop()
    else:
        with pytest.raises(UnexpectedModelBehavior):
            asyncio.run(run)
    assert len(calls) == 2
    by_path = retry_errors(calls[1])
    memory = by_path["memory_assessments"]
    assert memory["required_memory_ids"] == ["earlier"]
    assert memory["actual_memory_ids"] == ["eariler"]
    assert memory["missing_memory_ids"] == ["earlier"]
    assert memory["unknown_memory_ids"] == ["eariler"]
    assert by_path["supporting_memory_ids"]["unknown_memory_ids"] == ["eariler"]
    assert by_path["supporting_evidence"]["missing_evidence_ids"] == ["current-event"]
    assert json.dumps(invalid, sort_keys=True) == original


@pytest.mark.parametrize("resolution", [None, {"occurrences": None}])
def test_memory_identity_faults_are_reported_with_malformed_event_resolution(resolution):
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
