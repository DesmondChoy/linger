"""A boundary decision must account for each supplied memory before granting scope."""

import asyncio
import json

import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from src.linger.agents.librarian.agent import build_librarian_agent
from src.linger.agents.librarian.models import (
    BoundaryInferenceDecision, BoundaryMemory, LibrarianBoundaryInferenceInput,
    PassageInferenceDecision, boundary_memory_assessment_errors,
)
from src.linger.agents.librarian.skills import BOUNDARY_INFERENCE
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.orchestration.boundary import infer_spoiler_boundary
from tests.test_boundary_inference import FakeLibrarian, VERSION_ID, WORK_ID, memory


def evidence(identity="earlier"):
    return EvidenceRecord(
        evidence_id=identity, work_id="book", book_version_id="book-v1",
        chapter_id="book-ch1", chapter_number=1, location="Chapter1",
        source_sha256="a" * 64, source_lines=(1, 2), text="The captain declined the invitation.",
    )


def task(memory_id="memory-earlier"):
    return LibrarianBoundaryInferenceInput(
        current_line="I finished the bridge scene after the captain's refusal.",
        prior_reader_statements=(),
        relevant_memories=(BoundaryMemory(
            memory_id=memory_id, text="I read the captain refusing the invitation.", evidence_ids=(),
        ),),
        full_work_candidates=(evidence(), evidence("current")),
    )


def candidate(memory_id="memory-earlier"):
    return {
        "memory_assessments": [{
            "memory_id": memory_id, "status": "grounded_prior_knowledge",
            "evidence_ids": ["earlier"], "reason": "The memory describes the canonical earlier refusal.",
        }],
        "outcome": "candidate", "work_id": "book", "book_version_id": "book-v1",
        "chapter_number": 1, "confidence": .9, "authorization_basis": "memory_supported",
        "supporting_memory_ids": [memory_id], "supporting_evidence_ids": ["earlier", "current"],
    }


def uncertain(status="grounded_prior_knowledge"):
    assessment = candidate()["memory_assessments"][0]
    assessment["status"] = status
    return {
        "memory_assessments": [assessment], "outcome": "uncertain",
        "confidence": .2, "reason_code": "conflicting_context" if status == "conflicting" else "low_confidence",
    }


@pytest.mark.parametrize("fault", ["missing", "unknown_memory", "unknown_evidence", "line_only"])
def test_boundary_repairs_inconsistent_assessments_within_existing_retry_budget(fault):
    calls = []

    def model(messages, info):
        calls.append(messages)
        output = candidate()
        if len(calls) == 1:
            if fault == "missing":
                output.update(memory_assessments=[], authorization_basis="line_only", supporting_memory_ids=[])
            elif fault == "unknown_memory":
                output = candidate("invented-memory")
            elif fault == "unknown_evidence":
                output["memory_assessments"][0]["evidence_ids"] = ["invented-evidence"]
                output["supporting_evidence_ids"].append("invented-evidence")
            else:
                output.update(authorization_basis="line_only", supporting_memory_ids=[])
        else:
            assert any(isinstance(part, RetryPromptPart) for message in messages for part in message.parts)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    result = asyncio.run(build_librarian_agent(FunctionModel(model)).run(
        task().model_dump_json(), **BOUNDARY_INFERENCE.run_options(),
    ))
    assert len(calls) == 2
    assert result.output.authorization_basis == "memory_supported"
    assert result.output.supporting_memory_ids == ("memory-earlier",)
    assert task().relevant_memories[0].evidence_ids == ()


def test_repeated_omission_exhausts_existing_retry_budget_without_a_grant():
    calls = []

    def model(messages, info):
        calls.append(messages)
        output = candidate()
        output.update(memory_assessments=[], authorization_basis="line_only", supporting_memory_ids=[])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    with pytest.raises(UnexpectedModelBehavior):
        asyncio.run(build_librarian_agent(FunctionModel(model)).run(
            task().model_dump_json(), **BOUNDARY_INFERENCE.run_options(),
        ))
    assert len(calls) == 2


@pytest.mark.parametrize("fault", ["duplicate_memory", "duplicate_evidence", "empty_grounding", "missing_anchor", "conflicting"])
def test_structurally_inconsistent_candidates_are_rejected(fault):
    output = candidate()
    if fault == "duplicate_memory":
        output["memory_assessments"] *= 2
    elif fault == "duplicate_evidence":
        output["memory_assessments"][0]["evidence_ids"] *= 2
    elif fault == "empty_grounding":
        output["memory_assessments"][0]["evidence_ids"] = []
    elif fault == "missing_anchor":
        output["supporting_evidence_ids"] = ["current"]
    else:
        output["memory_assessments"][0]["status"] = "conflicting"
    with pytest.raises(ValidationError):
        BoundaryInferenceDecision.model_validate(output)


@pytest.mark.parametrize("status", ["grounded_prior_knowledge", "not_supported", "conflicting"])
def test_uncertain_current_progress_does_not_become_a_candidate(status):
    decision = BoundaryInferenceDecision.model_validate(uncertain(status))
    assert boundary_memory_assessment_errors(decision, task()) == []
    assert decision.outcome == "uncertain"
    assert decision.supporting_memory_ids == ()
    assert decision.authorization_basis is None


@pytest.mark.parametrize("fault", ["missing", "unknown_evidence", "line_only", "conflicting"])
def test_application_rechecks_injected_decisions_without_auto_promotion(fault):
    librarian = FakeLibrarian()
    stored = memory("memory-earlier", "Alice and the Caterpillar")
    output = candidate()
    output.update(work_id=WORK_ID, book_version_id=VERSION_ID, chapter_number=5)
    output["memory_assessments"][0]["evidence_ids"] = [librarian.chapter_five.evidence_id]
    output["supporting_evidence_ids"] = [librarian.chapter_five.evidence_id]
    decision = BoundaryInferenceDecision.model_validate(output)
    if fault == "missing":
        decision = decision.model_copy(update={"memory_assessments": ()})
    elif fault == "unknown_evidence":
        decision = decision.model_copy(update={"memory_assessments": (
            decision.memory_assessments[0].model_copy(update={"evidence_ids": ("invented",)}),
        )})
    elif fault == "line_only":
        decision = decision.model_copy(update={"authorization_basis": "line_only", "supporting_memory_ids": ()})
    else:
        decision = decision.model_copy(update={"memory_assessments": (
            decision.memory_assessments[0].model_copy(update={"status": "conflicting"}),
        )})

    async def judge(*args):
        return decision

    result = asyncio.run(infer_spoiler_boundary(
        "I finished the Caterpillar encounter.", work_id=WORK_ID, book_version_id=VERSION_ID,
        memories=(stored,), librarian=librarian, judge=judge,
    ))
    assert result.kind == "uncertain"
    assert result.reason_code == "inference_unavailable"


def test_same_agent_keeps_concurrent_memory_inputs_separate():
    async def run():
        ready = asyncio.Event()
        seen = []

        async def model(messages, info):
            prompts = [part for message in messages for part in message.parts if isinstance(part, UserPromptPart)]
            assert len(prompts) == 1
            payload = json.loads(prompts[0].content)
            identity = payload["relevant_memories"][0]["memory_id"]
            seen.append(identity)
            if len(seen) == 2:
                ready.set()
            await ready.wait()
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, candidate(identity))])

        agent = build_librarian_agent(FunctionModel(model))
        outputs = await asyncio.wait_for(asyncio.gather(*(
            agent.run(task(identity).model_dump_json(), **BOUNDARY_INFERENCE.run_options())
            for identity in ("memory-one", "memory-two")
        )), 5)
        assert [result.output.supporting_memory_ids for result in outputs] == [("memory-one",), ("memory-two",)]

    asyncio.run(run())


def test_passage_output_is_not_forced_through_memory_assessment():
    output = {
        "outcome": "passages", "work_id": "book", "book_version_id": "book-v1",
        "confidence": .9, "authorization_basis": "session_supported",
        "supporting_statement_ids": ["reader-1"],
        "supporting_evidence_ids": ["anchor"], "passage_evidence_ids": ["fragment"],
    }

    def model(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    result = asyncio.run(build_librarian_agent(FunctionModel(model)).run(
        "Not a book-request or memory-assessment prompt.", output_type=PassageInferenceDecision,
    ))
    assert result.output.passage_evidence_ids == ("fragment",)
