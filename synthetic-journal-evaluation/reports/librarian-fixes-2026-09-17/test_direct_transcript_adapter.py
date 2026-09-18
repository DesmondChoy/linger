"""Direct adapter keeps the notebook path and sanitized nested failure evidence."""

import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, TextPart, ThinkingPart
from pydantic_ai.models.function import FunctionModel

from src.linger.contracts.librarian import RetrievalFailure, RetrievalResult
from src.linger.orchestration.turn_context import confirmed_reading, reader_message

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("direct_transcript_adapter", BASE / "run_live.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


@pytest.mark.parametrize('unexpected', [False, True])
def test_direct_helper_records_each_nested_call_even_when_judgment_fails(tmp_path, monkeypatch, unexpected):
    cases = adapter.load_cases().cases[-2:]
    model_calls = []
    search_calls = []

    def respond(messages, info):
        model_calls.append(len(model_calls))
        if len(model_calls) == 2:
            if unexpected:
                raise RuntimeError('PRIVATE_EXCEPTION_MESSAGE')
            raise ModelHTTPError(429, 'PRIVATE_MODEL_NAME', 'PRIVATE_PROVIDER_BODY')
        return ModelResponse(parts=[ThinkingPart('PRIVATE_THINKING'), TextPart('No relevant evidence.')])

    agent = Agent(FunctionModel(respond), output_type=str, retries=0)

    async def search(**kwargs):
        case = cases[len(search_calls)]
        search_calls.append(kwargs)
        assert kwargs == {'work_id': adapter.WORK_ID, 'book_version_id': adapter.BOOK_VERSION_ID,
                          'max_final_evidence': 5}
        assert reader_message() == case.query
        assert confirmed_reading().chapter_max == case.chapter_max
        try:
            await adapter.run_agent_traced(
                agent, case.query, span_name='test.direct.judgment', role='Librarian',
                stage='evidence_strength', input_contract='test-input', output_contract='test-output',
                prompt_template_id='test-direct', prompt_digest='a' * 64,
                failure_code='evidence_judgement_unavailable',
            )
        except ModelHTTPError:
            return RetrievalFailure(kind='failure', request_id='test-request',
                                    error_code='evidence_judgement_unavailable', retryable=True)
        return RetrievalResult(
            kind='result', request_id='test-request', outcome='no_evidence', evidence_strength='none',
            strength_reason='Offline fixture only.', searched_scope={
                'work_id': adapter.WORK_ID, 'book_version_id': adapter.BOOK_VERSION_ID,
                'max_chapter_inclusive': case.chapter_max,
            },
        )

    monkeypatch.setattr(adapter, 'librarian_search', search)
    monkeypatch.setattr(adapter, 'load_cases', lambda: SimpleNamespace(cases=cases))
    monkeypatch.setattr(adapter, 'get_settings', lambda: SimpleNamespace(
        linger_model='openai:gpt-5.6-luna', linger_web_search_enabled=False,
    ))
    monkeypatch.setattr(adapter, 'configure_component_evaluation_telemetry', lambda agent: None)
    monkeypatch.setattr(adapter.logfire, 'force_flush', lambda: True)
    output = tmp_path / 'direct.json'
    if unexpected:
        with pytest.raises(RuntimeError, match='PRIVATE_EXCEPTION_MESSAGE'):
            asyncio.run(adapter.main(SimpleNamespace(mode='direct', output=output)))
    else:
        asyncio.run(adapter.main(SimpleNamespace(mode='direct', output=output)))
    progress = json.loads(output.with_suffix('.progress.json').read_text())
    assert len(search_calls) == len(model_calls) == 2
    assert len(progress['cases']) == 2
    success, failure = progress['cases']
    assert success['strength_correct'] is True
    assert success['agent_exchanges'][0]['status'] == 'success'
    exchange, = failure['agent_exchanges']
    assert exchange['stage'] == 'evidence_strength'
    assert exchange['status'] == 'failure'
    assert exchange['failure_category'] == ('unknown_error' if unexpected else 'provider_error')
    assert exchange['provider_status_code'] == (None if unexpected else 429)
    assert exchange['provider_error_kind'] == (None if unexpected else 'http')
    assert exchange['model_messages']
    assert 'PRIVATE_' not in json.dumps(progress)
    assert progress['status'] == ('failed' if unexpected else 'complete')
    if unexpected:
        assert failure['error_type'] == 'RuntimeError'
        assert not output.exists()
    else:
        report = json.loads(output.read_text())
        assert report['cases'] == progress['cases']
        assert report['summary']['result_count'] == 1
        assert failure['response_kind'] == 'failure'
    with pytest.raises(FileExistsError):
        asyncio.run(adapter.main(SimpleNamespace(mode='direct', output=output)))
