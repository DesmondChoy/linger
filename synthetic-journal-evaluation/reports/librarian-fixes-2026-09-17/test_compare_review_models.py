"""Offline contract and shared-budget checks; no live model calls."""
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, ThinkingPart, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage
import pytest

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('review_model_comparison', BASE / 'compare_review_models.py')
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


def test_all_twelve_saved_inputs_preserve_exact_prompts_and_canonical_context():
    cases = comparison.load_inputs(comparison.DEFAULT_INPUT)
    assert len(cases) == len({c['case_id'] for c in cases}) == 12
    for case in cases:
        source = comparison.read(Path(case['source_file']))
        if case['source_sequence'] is not None:
            if 'cases' in source:
                exchanges = next(c for c in source['cases'] if c['case_id'] == 'father-william')['agent_exchanges']
            elif 'recorders' in source:
                exchanges = source['recorders'][0]['exchanges']
            else:
                scene = 'alice-race-reflection' if 'suite-10-' in case['case_id'] else (
                    'S2' if 'suite-8-' in case['case_id'] else 'S1')
                exchanges = next(s for s in source['scenes'] if s['scene_id'] == scene)['agent_exchanges']
            original = next(e for e in exchanges if e['sequence'] == case['source_sequence'])['input_prompt']
            assert case['input_prompt'] == original
        assert comparison.digest(case['input_prompt'].encode()) == case['input_sha256']
    assert all(c['expected'] is None for c in cases[:8])
    assert all(c['expected'] is not None for c in cases[8:])


def test_dry_plan_never_reserves_constructs_models_or_changes_ledger(tmp_path, monkeypatch, capsys):
    budget = tmp_path / 'live-budget.json'
    budget.write_text('{"maximum_iterations":20,"iterations":[]}')
    before = budget.read_bytes()
    def forbidden(*args, **kwargs):
        raise AssertionError('Dry plan attempted a live action')
    monkeypatch.setattr(comparison, 'reserve', forbidden)
    monkeypatch.setattr(comparison, 'make_agent', forbidden)
    comparison.main(SimpleNamespace(inputs=comparison.DEFAULT_INPUT, budget=budget,
                                    execute=False, approved_models=None))
    report = json.loads(capsys.readouterr().out)
    assert report['top_level_runs'] == 24
    assert report['models'] == list(comparison.MODELS)
    assert report['model_settings'] == {'openai_reasoning_effort': 'medium'}
    assert report['output_retries'] == 2
    assert report['additional_run_retries'] == 0
    assert report['provider_calls'] is report['budget_reserved'] is False
    assert budget.read_bytes() == before
    assert not budget.with_suffix('.lock').exists()


def test_execute_requires_exact_approved_models_before_reservation(monkeypatch):
    monkeypatch.setattr(comparison, 'plan', lambda folder: {})
    def forbidden(*args):
        raise AssertionError('Reserved without model approval acknowledgement')
    monkeypatch.setattr(comparison, 'reserve', forbidden)
    with pytest.raises(ValueError, match='separate approval'):
        comparison.main(SimpleNamespace(inputs=comparison.DEFAULT_INPUT, execute=True,
                                        approved_models=['openai:gpt-5.6-luna'], budget=Path('unused')))


def test_comparison_reserves_one_shared_iteration_with_both_models_and_never_resets(tmp_path):
    budget = tmp_path / 'live-budget.json'
    prior = [{'iteration': i, 'reservation_id': str(i)} for i in range(1, 20)]
    comparison.write(budget, {'maximum_iterations': 20, 'iterations': prior})
    folder, reservation = comparison.reserve(budget, tmp_path, {'fixed': 'plan'})
    current = comparison.read(budget)['iterations']
    assert current[:-1] == prior
    assert len(current) == 20
    assert reservation['iteration'] == 20
    assert reservation['models'] == list(comparison.MODELS)
    assert reservation['model_settings'] == {'openai_reasoning_effort': 'medium'}
    assert comparison.read(folder / 'plan.json') == {'fixed': 'plan'}
    with pytest.raises(RuntimeError, match='exhausted'):
        comparison.reserve(budget, tmp_path, {})
    assert comparison.read(budget)['iterations'] == current


def test_real_agent_receives_saved_input_and_same_skill_and_keeps_review():
    from src.linger.agents.provenance.agent import build_provenance_agent
    from src.linger.agents.provenance.skills import CANDIDATE_REVIEW
    case = comparison.load_inputs(comparison.DEFAULT_INPUT)[8]
    saved = comparison.read(comparison.DEFAULT_INPUT / 'suite-mapping.json')['diagnostics'][0]['review']
    calls = []
    def respond(messages, info):
        prompts = [p.content for m in messages for p in m.parts if isinstance(p, UserPromptPart)]
        assert prompts == [case['input_prompt']]
        assert CANDIDATE_REVIEW.instructions in info.instructions
        calls.append(messages)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, saved)],
                             usage=RequestUsage(input_tokens=100, output_tokens=20))
    row = asyncio.run(comparison.review_once(build_provenance_agent(FunctionModel(respond)), case))
    assert len(calls) == 1
    assert row['status'] == 'success'
    assert row['review'] == saved
    assert row['existing_control_grade']['passed'] is True
    assert row['usage_complete'] is True
    assert row['exchanges'][0]['input_prompt'] == case['input_prompt']


@pytest.mark.parametrize('failure', ['invalid_output', 'http', 'generic'])
def test_failed_agent_keeps_sanitized_attempts_without_extra_outer_retry(failure):
    from src.linger.agents.provenance.agent import build_provenance_agent
    case = comparison.load_inputs(comparison.DEFAULT_INPUT)[8]
    calls = []
    def respond(messages, info):
        calls.append(messages)
        if failure == 'http':
            raise ModelHTTPError(503, 'PRIVATE_MODEL', 'PRIVATE_BODY')
        if failure == 'generic':
            raise RuntimeError('PRIVATE_MESSAGE')
        return ModelResponse(parts=[ThinkingPart('PRIVATE_THINKING'),
                                    ToolCallPart(info.output_tools[0].name, {})],
                             usage=RequestUsage(input_tokens=100, output_tokens=20))
    row = asyncio.run(comparison.review_once(build_provenance_agent(FunctionModel(respond)), case))
    assert row['status'] == 'failed'
    assert row['usage_complete'] is False
    assert len(calls) == (3 if failure == 'invalid_output' else 1)
    assert len(row['exchanges']) == 1
    exchange = row['exchanges'][0]
    assert exchange['status'] != 'success'
    assert exchange['provider_status_code'] == (503 if failure == 'http' else None)
    assert exchange['provider_error_kind'] == ('http' if failure == 'http' else None)
    assert 'PRIVATE_' not in json.dumps(row)
    if failure == 'invalid_output':
        assert row['usage']['requests'] == 3
        assert row['usage']['input_tokens'] == 300
        assert exchange['model_messages']


def test_both_models_run_each_frozen_case_once_and_never_claim_semantic_all_pass(tmp_path, monkeypatch):
    import apps.backend.telemetry as telemetry
    from src.linger.agents.provenance.agent import build_provenance_agent
    prepared = comparison.plan(comparison.DEFAULT_INPUT)
    calls = []
    def make_agent(model_name):
        index = 0
        def respond(messages, info):
            nonlocal index
            case = prepared['cases'][index]
            prompts = [p.content for m in messages for p in m.parts if isinstance(p, UserPromptPart)]
            assert prompts == [case['input_prompt']]
            source = comparison.read(Path(case['source_file']))
            if case['expected'] is not None:
                output = next(d['review'] for d in source['diagnostics'] if d['case_id'] == case['case_id'])
            else:
                if 'recorders' in source:
                    exchanges = source['recorders'][0]['exchanges']
                elif 'cases' in source:
                    exchanges = next(c for c in source['cases'] if c['case_id'] == 'father-william')['agent_exchanges']
                else:
                    scene = ('alice-race-reflection' if case['case_id'].startswith('suite-10')
                             else 'S2' if case['case_id'].startswith('suite-8') else 'S1')
                    exchanges = next(s for s in source['scenes'] if s['scene_id'] == scene)['agent_exchanges']
                output = next(e['output'] for e in exchanges if e['sequence'] == case['source_sequence'])
            calls.append((model_name, case['case_id']))
            index += 1
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])
        return build_provenance_agent(FunctionModel(respond))
    monkeypatch.setattr(comparison, 'make_agent', make_agent)
    monkeypatch.setattr(telemetry, 'configure_component_evaluation_telemetry', lambda agent: None)
    summary = asyncio.run(comparison.execute(prepared, tmp_path))
    assert calls == [(model, case['case_id']) for model in comparison.MODELS for case in prepared['cases']]
    assert summary['results_count'] == summary['successful_reviews'] == 24
    assert summary['all_pass'] is None
    assert summary['semantic_review_required'] is True
    assert summary['source_unchanged'] is summary['saved_inputs_unchanged'] is True
    rows = comparison.read(tmp_path / 'results.json')
    assert len(rows) == 24
    assert sum('existing_control_grade' in row for row in rows) == 8


def test_local_grade_error_is_not_silently_reported_as_success(monkeypatch):
    from evals.provenance import risk_codes
    from src.linger.agents.provenance.agent import build_provenance_agent
    case = comparison.load_inputs(comparison.DEFAULT_INPUT)[8]
    saved = comparison.read(comparison.DEFAULT_INPUT / 'suite-mapping.json')['diagnostics'][0]['review']
    def respond(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, saved)])
    def fail_grade(*args):
        raise ValueError('local grade bug')
    monkeypatch.setattr(risk_codes, 'grade_review', fail_grade)
    with pytest.raises(ValueError, match='local grade bug'):
        asyncio.run(comparison.review_once(build_provenance_agent(FunctionModel(respond)), case))
