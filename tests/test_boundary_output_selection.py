"""Only advertise boundary outcomes supported by application-owned input."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from src.linger.agents.librarian.agent import build_librarian_agent
from src.linger.agents.librarian.boundary_prompt import (
    NO_HISTORY_PROMPT_FINGERPRINT, PROMPT_FINGERPRINT,
)
from src.linger.agents.librarian.models import BoundaryUncertainDecision
from src.linger.agents.librarian.skills import BOUNDARY_INFERENCE_NO_HISTORY
from src.linger.contracts.session import ReaderStatement
from src.linger.orchestration.boundary import judge_spoiler_boundary
from tests.test_boundary_event_resolution import identified_stop, request


def test_no_history_repairs_unavailable_passage_branch_to_memory_assessed_candidate():
    task = request()
    calls = []

    def respond(messages, info):
        calls.append(messages)
        assert len(info.output_tools) == 2
        assert all('PassageInferenceDecision' not in tool.name for tool in info.output_tools)
        assert BOUNDARY_INFERENCE_NO_HISTORY.instructions in info.instructions
        if len(calls) == 1:
            # The output tool previously offered despite absent earlier statements.
            return ModelResponse(parts=[ToolCallPart('final_result_PassageInferenceDecision', {
                'outcome': 'passages', 'work_id': 'book', 'book_version_id': 'book-v1',
                'confidence': .99, 'authorization_basis': 'line_only',
                'supporting_statement_ids': [], 'supporting_evidence_ids': ['current-event'],
                'passage_evidence_ids': ['current-event'],
            })])
        assert any(isinstance(part, RetryPromptPart) for message in messages for part in message.parts)
        tool = next(tool for tool in info.output_tools if tool.name.endswith('BoundaryInferenceDecision'))
        return ModelResponse(parts=[ToolCallPart(tool.name, identified_stop().model_dump(mode='json'))])

    result = asyncio.run(judge_spoiler_boundary(
        task.current_line, task.relevant_memories, task.full_work_candidates, (),
        agent=build_librarian_agent(FunctionModel(respond)),
    ))
    assert result == identified_stop()
    assert len(calls) == 2


@pytest.mark.parametrize('with_history', [False, True])
def test_selected_schema_fingerprint_matches_trace_and_manifest(with_history):
    from evals.synthetic_journals.replay import RUNTIME_PROMPT_FINGERPRINTS

    uncertain = BoundaryUncertainDecision(
        memory_assessments=(), outcome='uncertain', confidence=.1,
        reason_code='insufficient_context',
    )
    history = (ReaderStatement(statement_id='earlier', text='I read the opening.'),) if with_history else ()
    with patch('src.linger.orchestration.boundary.run_agent_traced', new=AsyncMock(
        return_value=SimpleNamespace(output=uncertain),
    )) as run:
        result = asyncio.run(judge_spoiler_boundary('Where was I?', (), (), history))
    assert result == uncertain
    options = run.await_args.kwargs
    fingerprint = PROMPT_FINGERPRINT if with_history else NO_HISTORY_PROMPT_FINGERPRINT
    assert options['prompt_template_id'] == fingerprint.template_id
    assert options['prompt_digest'] == fingerprint.digest
    assert fingerprint in RUNTIME_PROMPT_FINGERPRINTS
    assert PROMPT_FINGERPRINT.digest != NO_HISTORY_PROMPT_FINGERPRINT.digest
    expected = 'LibrarianBoundaryDecision' if with_history else 'LibrarianChapterBoundaryDecision'
    assert options['output_contract'].endswith(expected)


def test_no_history_without_memory_can_still_return_uncertainty():
    def respond(messages, info):
        assert len(info.output_tools) == 2
        tool = next(tool for tool in info.output_tools if tool.name.endswith('BoundaryUncertainDecision'))
        return ModelResponse(parts=[ToolCallPart(tool.name, {
            'memory_assessments': [], 'outcome': 'uncertain', 'confidence': .1,
            'reason_code': 'insufficient_context',
        })])

    result = asyncio.run(judge_spoiler_boundary(
        'I cannot recall where I stopped.', (), (), (),
        agent=build_librarian_agent(FunctionModel(respond)),
    ))
    assert isinstance(result, BoundaryUncertainDecision)
