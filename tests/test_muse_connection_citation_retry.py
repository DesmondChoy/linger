"""Repair corrupt connection-source declarations inside Muse's existing run."""

import asyncio
import json

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from src.linger.agents.muse.agent import build_muse_agent, validate_muse_output
from src.linger.agents.muse.models import MuseCandidate
from src.linger.agents.muse.skills import REFLECTION
from src.linger.contracts.connection_evidence import MemoryConnectionEvidence
from src.linger.orchestration.inspection_context import (
    begin_connection_inspection, register_connection_evidence, reset_connection_inspection,
)

SOURCE_ID = 'mem_' + '1234567890abcdef' * 4
CLAIM = 'You wrote that you felt unsure about the new role.'
SOURCE = MemoryConnectionEvidence(evidence_id=SOURCE_ID, excerpt=CLAIM)


@pytest.fixture(autouse=True)
def authorized_memory():
    token = begin_connection_inspection()
    register_connection_evidence([SOURCE])
    try:
        yield
    finally:
        reset_connection_inspection(token)


def candidate(identity=SOURCE_ID, quote=None):
    return MuseCandidate.model_validate({
        'reply': CLAIM,
        'evidence_uses': [{'source_kind': 'memory', 'evidence_id': identity,
                           'supported_claims': [CLAIM], 'exact_quote': quote}],
        'memory': {'kind': 'no_memory_candidate', 'reason_code': 'automatic_capture_disabled'},
    })


def test_truncated_memory_id_is_repaired_before_provenance():
    calls = []

    async def model(messages, info):
        calls.append(messages)
        if len(calls) > 1:
            retry = [part for message in messages for part in message.parts if isinstance(part, RetryPromptPart)][-1]
            errors = json.loads(retry.content)['errors']
            assert errors[0]['path'] == 'evidence_uses[0].evidence_id'
            assert errors[0]['available_source_ids'] == [SOURCE_ID]
        output = candidate(SOURCE_ID[:-1] if len(calls) == 1 else SOURCE_ID)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output.model_dump(mode='json'))])

    result = asyncio.run(build_muse_agent(FunctionModel(model)).run('Reflect on this memory.', **REFLECTION.run_options()))
    assert len(calls) == 2
    assert result.output.evidence_uses[0].evidence_id == SOURCE_ID


def test_unregistered_memory_and_inexact_quote_are_never_accepted():
    for output in (candidate('invented'), candidate(quote='You felt sure about the new role.')):
        with pytest.raises(ModelRetry):
            validate_muse_output(None, output)
    assert validate_muse_output(None, candidate(quote=CLAIM)) == candidate(quote=CLAIM)
