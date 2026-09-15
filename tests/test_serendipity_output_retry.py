"""Repair winner-specific declarations before discovery leaves the agent."""

import asyncio

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from apps.backend.librarian import Librarian
from src.linger.agents.serendipity.agent import build_serendipity_agent
from src.linger.agents.serendipity.models import (
    CandidateRubric,
    ConnectionCandidate,
    ConnectionDiscoveryInput,
    ConnectionProposal,
    ConnectionScope,
)
from src.linger.agents.serendipity.skills import CONNECTION_DISCOVERY
from src.linger.agents.serendipity.tools import SerendipityDependencies
from src.linger.contracts.connection_evidence import MemoryConnectionEvidence, WebConnectionEvidence


WEB_URL = "https://example.com/reporting-errors"


def dependencies():
    memory = MemoryConnectionEvidence(evidence_id="memory-1", excerpt="I corrected a mistake quietly.")
    page = WebConnectionEvidence(evidence_id=WEB_URL, title="Reporting errors", excerpt="The study describes reporting errors.")
    return SerendipityDependencies(
        task=ConnectionDiscoveryInput(
            cue="Help me compare my note with the reporting study.",
            intent="find_connection", presentation="ask_before_showing",
            scope=ConnectionScope(allowed_sources=("memory", "web"), web_source_urls=(WEB_URL,)),
        ),
        librarian=Librarian(),
        evidence={memory.evidence_id: memory, page.evidence_id: page},
        opened_web_evidence={page.evidence_id: page},
    )


def proposal(winner_has_web, flag):
    candidates = tuple(ConnectionCandidate(
        candidate_id=f"candidate-{index}",
        tentative_claim=claim,
        evidence_ids=(WEB_URL if has_web else "memory-1",),
        shared_structure="An error can be corrected before it is discussed.",
        meaningful_difference="The note describes one event; the study describes a group.",
        interpretation=claim,
        rubric=CandidateRubric(
            cue_fit="direct" if index == 0 else "partial",
            reflective_value="high" if index == 0 else "medium", safety="clear",
        ),
        comparison_note="The first addresses the current question more directly.",
    ) for index, has_web, claim in (
        (0, winner_has_web, "Consider what makes reporting feel possible."),
        (1, not winner_has_web, "Consider the difference between repair and disclosure."),
    ))
    return ConnectionProposal(
        shortlist=candidates, selected_candidate_id="candidate-0",
        uncertainty="medium", presentation="ask_before_showing",
        suggested_follow_up="Would that comparison help?",
        policy_flags=("contains_web_claim",) if flag else (),
    )


@pytest.mark.parametrize("winner_has_web", [False, True])
@pytest.mark.parametrize("initially_correct", [False, True])
def test_web_flag_is_checked_against_winner_and_repaired_before_return(winner_has_web, initially_correct):
    deps = dependencies()
    calls = []

    async def model(messages, info):
        calls.append(messages)
        if len(calls) > 1:
            retries = [part for message in messages for part in message.parts if isinstance(part, RetryPromptPart)]
            assert retries
            assert "contains_web_claim" in str(retries[-1].content)
            assert "selected" in str(retries[-1].content)
        flag = winner_has_web if initially_correct or len(calls) > 1 else not winner_has_web
        tool = next(tool for tool in info.output_tools if tool.name.endswith("ConnectionProposal"))
        return ModelResponse(parts=[ToolCallPart(tool.name, proposal(winner_has_web, flag).model_dump(mode="json"))])

    result = asyncio.run(build_serendipity_agent(FunctionModel(model)).run(
        deps.task.model_dump_json(), deps=deps, **CONNECTION_DISCOVERY.run_options(),
    ))

    assert len(calls) == (1 if initially_correct else 2)
    assert ("contains_web_claim" in result.output.policy_flags) is winner_has_web
    assert result.output.selected_candidate_id == "candidate-0"


def test_persistent_winner_flag_mismatch_exhausts_existing_retry_budget():
    deps = dependencies()
    calls = []

    async def model(messages, info):
        calls.append(messages)
        tool = next(tool for tool in info.output_tools if tool.name.endswith("ConnectionProposal"))
        return ModelResponse(parts=[ToolCallPart(tool.name, proposal(False, True).model_dump(mode="json"))])

    with pytest.raises(UnexpectedModelBehavior, match="retries"):
        asyncio.run(build_serendipity_agent(FunctionModel(model)).run(
            deps.task.model_dump_json(), deps=deps, **CONNECTION_DISCOVERY.run_options(),
        ))
    assert len(calls) == 3
