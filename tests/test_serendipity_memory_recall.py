"""Single-answer memory recall as its own Serendipity skill and result."""

import asyncio

import pytest
from pydantic import ValidationError
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from apps.backend.librarian import Librarian
from src.linger.agents.serendipity.agent import build_serendipity_agent
from src.linger.agents.serendipity.models import (
    SERENDIPITY_RESPONSE_ADAPTER,
    CandidateRubric,
    ConnectionCandidate,
    ConnectionDecline,
    ConnectionDiscoveryInput,
    ConnectionProposal,
    ConnectionScope,
    MemoryRecall,
    MemorySearchResult,
)
from src.linger.agents.serendipity.skills import CONNECTION_DISCOVERY, MEMORY_RECALL
from src.linger.agents.serendipity.tools import SerendipityDependencies
from src.linger.contracts.curation import CuratedMemory

TEA = CuratedMemory(
    memory_id="memory-tea", text="My favourite tea is peppermint.", kind="original",
    source_memory_ids=("memory-tea",), created_at="2026-09-07T00:00:00Z",
)


def dependencies(intent, memories=(TEA,)):
    return SerendipityDependencies(
        task=ConnectionDiscoveryInput(
            cue="What is my favourite tea?",
            intent=intent,
            presentation="ask_before_showing",
            scope=ConnectionScope(allowed_sources=("memory",)),
        ),
        librarian=Librarian(),
        memories=memories,
    )


def recall(*evidence_ids):
    return MemoryRecall(
        evidence_ids=evidence_ids,
        relevance_note="The reader's own earlier statement of their favourite tea.",
    )


def proposal():
    candidates = tuple(ConnectionCandidate(
        candidate_id=f"candidate-{index}",
        tentative_claim=claim,
        evidence_ids=("memory-tea",) if index == 0 else ("memory-habit",),
        shared_structure="Both concern the same preference.",
        meaningful_difference="One is a record; the other is a question.",
        interpretation=claim,
        rubric=CandidateRubric(
            cue_fit="direct" if index == 0 else "partial",
            reflective_value="high" if index == 0 else "medium", safety="clear",
        ),
        comparison_note="The first addresses the question more directly.",
    ) for index, claim in ((0, "The record names the tea."), (1, "The record implies a habit.")))
    return ConnectionProposal(
        shortlist=candidates, selected_candidate_id="candidate-0",
        uncertainty="low", presentation="ask_before_showing",
        suggested_follow_up="Would that help?",
    )


def run(skill, deps, outputs, *, expected_search=None):
    """Search once, then return each scripted output until one is accepted."""
    retries = []
    remaining = list(outputs)

    async def model(messages, info):
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("search_memories", {"query": "favourite tea"})])
        if expected_search is not None:
            returned = next(
                part.content
                for message in messages for part in message.parts
                if isinstance(part, ToolReturnPart) and part.tool_name == "search_memories"
            )
            assert MemorySearchResult.model_validate(returned) == expected_search
        retries.extend(
            str(part.content) for part in messages[-1].parts if isinstance(part, RetryPromptPart)
        )
        output = remaining.pop(0)
        tool = next(tool for tool in info.output_tools if tool.name.endswith(type(output).__name__))
        return ModelResponse(parts=[ToolCallPart(tool.name, output.model_dump(mode="json"))])

    result = asyncio.run(build_serendipity_agent(FunctionModel(model)).run(
        deps.task.model_dump_json(), deps=deps, **skill.run_options(),
    ))
    return result.output, retries


def test_one_matching_record_is_a_complete_recall():
    output, retries = run(MEMORY_RECALL, dependencies("recall_memory"), [recall("memory-tea")])

    assert output == recall("memory-tea")
    assert retries == []


def test_recall_task_retries_a_proposal():
    output, retries = run(
        MEMORY_RECALL, dependencies("recall_memory"), [proposal(), recall("memory-tea")],
    )

    assert isinstance(output, MemoryRecall)
    assert len(retries) == 1


def test_connection_task_retries_a_recall():
    decline = ConnectionDecline(reason="insufficient_evidence", safe_next_step="Reply plainly.")
    output, retries = run(
        CONNECTION_DISCOVERY, dependencies("find_connection"), [recall("memory-tea"), decline],
    )

    assert output == decline
    assert len(retries) == 1


def test_recall_retries_an_id_this_run_did_not_return():
    output, retries = run(
        MEMORY_RECALL, dependencies("recall_memory"),
        [recall("memory-tea", "memory-unseen"), recall("memory-tea")],
    )

    assert output == recall("memory-tea")
    assert len(retries) == 1
    assert "memory-unseen" in retries[0]


def test_recall_task_may_decline_without_a_matching_record():
    unrelated = CuratedMemory(
        memory_id="memory-piano", text="I practise piano every evening.", kind="original",
        source_memory_ids=("memory-piano",), created_at="2026-09-07T00:00:00Z",
    )
    decline = ConnectionDecline(reason="no_matching_memory", safe_next_step="Reply plainly.")
    output, retries = run(
        MEMORY_RECALL, dependencies("recall_memory", memories=(unrelated,)), [decline],
        expected_search=MemorySearchResult(outcome="no_evidence", evidence=()),
    )

    assert output == decline
    assert retries == []


@pytest.mark.parametrize("evidence_ids", [(), ("a", "b", "c", "d"), ("a", "a"), ("",)])
def test_recall_requires_one_to_three_unique_ids(evidence_ids):
    with pytest.raises(ValidationError):
        recall(*evidence_ids)


def test_recall_bounds_its_relevance_note():
    for note in ("", "x" * 501):
        with pytest.raises(ValidationError):
            MemoryRecall(evidence_ids=("memory-tea",), relevance_note=note)


def test_response_adapter_discriminates_a_recall():
    parsed = SERENDIPITY_RESPONSE_ADAPTER.validate_python(recall("memory-tea").model_dump())

    assert parsed == recall("memory-tea")
