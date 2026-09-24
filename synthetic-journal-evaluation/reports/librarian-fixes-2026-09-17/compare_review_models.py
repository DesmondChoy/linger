"""Prepare twelve fixed reviews; execute only after exact-model approval.

Default is a read-only dry plan. Live comparison consumes ONE shared iteration,
uses two explicit models sequentially, and never retries a failed agent run.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

BASE = Path(__file__).resolve().parent
ROOT = next(p for p in BASE.parents if (p / 'pyproject.toml').is_file())
sys.path.insert(0, str(ROOT))
MODELS = ('openai:gpt-5.6-luna', 'openai:gpt-5.6-sol')
MODEL_SETTINGS = {'openai_reasoning_effort': 'medium'}
DEFAULT_INPUT = BASE / 'iteration-13-4d9bca6b'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def now():
    return datetime.now(UTC).isoformat()


def load_inputs(folder):
    """Retain exact saved prompts, not reconstructed reader or evidence text."""
    from src.linger.agents.provenance.models import ProvenanceInput
    from src.linger.agents.provenance.prompt import PROMPT_FINGERPRINT
    from evals.provenance.claim_mapping import load_cases

    cases = []

    def add(case_id, path, exchange, expected=None):
        prompt = exchange['input_prompt']
        payload = json.loads(prompt)
        typed = ProvenanceInput.model_validate(payload)
        if typed.model_dump(mode='json') != payload:
            raise ValueError(f'Saved input no longer matches current typed projection: {case_id}')
        if exchange['prompt_fingerprint']['digest'] != PROMPT_FINGERPRINT.digest:
            raise ValueError(f'Saved prompt fingerprint differs: {case_id}')
        cases.append(dict(case_id=case_id, source_file=str(path), source_sha256=digest(path.read_bytes()),
                          source_sequence=exchange.get('sequence'), input_prompt=prompt,
                          input_sha256=digest(prompt.encode()), expected=expected))

    def reviews(exchanges):
        return [e for e in exchanges if e['role'] == 'Provenance' and e['stage'] == 'review']

    path = folder / 'suite-smoke.diagnostics.json'
    smoke = reviews(read(path)['recorders'][0]['exchanges'])
    if len(smoke) != 2:
        raise ValueError('Expected exactly two saved smoke reviews')
    for label, exchange in zip(('draft', 'revision'), smoke):
        add('smoke-' + label, path, exchange)
    for suite, scene, labels in ((10, 'alice-race-reflection', ('draft', 'revision')),
                                  (8, 'S2', ('final',)), (6, 'S1', ('final',))):
        path = folder / f'suite-{suite}.json'
        row = next(s for s in read(path)['scenes'] if s['scene_id'] == scene)
        exchanges = reviews(row['agent_exchanges'])
        if len(exchanges) != 2:
            raise ValueError(f'Expected exactly two saved reviews in suite {suite} {scene}')
        selected = exchanges if len(labels) == 2 else exchanges[-1:]
        for label, exchange in zip(labels, selected):
            add(f'suite-{suite}-{scene}-{label}', path, exchange)
    path = folder / 'suite-release.json'
    father = next(c for c in read(path)['cases'] if c['case_id'] == 'father-william')
    exchanges = reviews(father['agent_exchanges'])
    if len(exchanges) != 2:
        raise ValueError('Expected exactly two saved Father William reviews')
    for label, exchange in zip(('draft', 'revision'), exchanges):
        add('father-william-' + label, path, exchange)
    path = folder / 'suite-mapping.json'
    mapping = read(path)
    expected = {c.case_id: c for c in load_cases().cases}
    if {d['case_id'] for d in mapping['diagnostics']} != set(expected) or len(mapping['diagnostics']) != 4:
        raise ValueError('Saved mapping controls differ from the four fixed controls')
    for item in mapping['diagnostics']:
        case = expected[item['case_id']]
        if item['review_input'] != case.review_input.model_dump(mode='json'):
            raise ValueError('Saved mapping input differs from the existing control')
        prompts = [part['content'] for message in item['model_messages'] for part in message['parts']
                   if part.get('part_kind') == 'user-prompt']
        if prompts != [case.review_input.model_dump_json()]:
            raise ValueError('Saved control prompt differs from its original typed serialization')
        add(item['case_id'], path, dict(input_prompt=prompts[0],
            prompt_fingerprint={'digest': mapping['prompt_digest']}),
            expected=case.model_dump(mode='json'))
    if len(cases) != 12:
        raise ValueError('Comparison must contain exactly twelve fixed inputs')
    return cases


def source_hashes():
    names = subprocess.check_output(['git', 'ls-files', '-co', '--exclude-standard', '--',
        'apps/backend', 'src/linger', 'evals', 'pyproject.toml', 'uv.lock'], cwd=ROOT, text=True).splitlines()
    paths = {ROOT / name for name in names} | {Path(__file__)}
    return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in sorted(paths) if p.is_file()}


def plan(folder):
    from src.linger.agents.provenance.skills import CANDIDATE_REVIEW
    cases = load_inputs(folder)
    return dict(kind='controlled_provenance_model_comparison', models=list(MODELS),
        model_settings=MODEL_SETTINGS, cases=cases, prompt_fingerprint=CANDIDATE_REVIEW.fingerprint(
            template_id='provenance.release-gate').model_dump(mode='json'),
        output_retries=CANDIDATE_REVIEW.output_retries, tool_retries=CANDIDATE_REVIEW.tool_retries,
        top_level_runs=24, maximum_concurrent_runs=1, additional_run_retries=0,
        provider_calls=False, budget_reserved=False, source_hashes=source_hashes(),
        semantic_review_required=True, production_model_changed=False)


def reserve(budget_path, output_parent, prepared):
    """Use the existing ledger's lock and atomic replacement, without a reset."""
    with budget_path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        budget = read(budget_path)
        entries = budget['iterations']
        if not isinstance(entries, list) or len(entries) >= min(20, budget['maximum_iterations']):
            raise RuntimeError('Live evaluation iteration budget exhausted')
        number = len(entries) + 1
        folder = output_parent / f'iteration-{number:02d}-review-comparison-{uuid4().hex[:8]}'
        folder.mkdir(exist_ok=False)
        entry = dict(iteration=number, reservation_id=uuid4().hex, reserved_at=now(),
            status='reserved', suites=['controlled-provenance-model-comparison'],
            models=list(MODELS), model_settings=dict(MODEL_SETTINGS), directory=str(folder),
            prepared_sha256=digest(json.dumps(prepared, sort_keys=True).encode()))
        entries.append(entry)
        write(budget_path, budget)
        write(folder / 'reservation.json', entry)
        write(folder / 'plan.json', prepared)
        return folder, entry


async def review_once(agent, case):
    from pydantic import TypeAdapter
    from pydantic_ai.usage import RunUsage
    from apps.backend.telemetry import run_agent_traced
    from evals.synthetic_journals.transcript import SceneTranscriptRecorder
    from src.linger.evaluation_transcript import bind_evaluation_transcript_sink
    from src.linger.agents.provenance.prompt import PROMPT_FINGERPRINT
    from src.linger.agents.provenance.skills import CANDIDATE_REVIEW
    from evals.provenance.risk_codes import RiskCodeEvalCase, grade_review

    recorder, usage = SceneTranscriptRecorder(), RunUsage()
    row = dict(case_id=case['case_id'], input_sha256=case['input_sha256'], status='failed', review=None)
    try:
        with bind_evaluation_transcript_sink(recorder):
            result = await run_agent_traced(agent, case['input_prompt'],
                span_name='provenance.controlled_comparison', role='Provenance', stage='review',
                input_contract='src.linger.agents.provenance.models.ProvenanceInput',
                output_contract='src.linger.agents.provenance.models.ProvenanceReview',
                prompt_template_id=PROMPT_FINGERPRINT.template_id, prompt_digest=PROMPT_FINGERPRINT.digest,
                failure_code='provenance_model_failed', usage=usage, model_settings=MODEL_SETTINGS,
                **CANDIDATE_REVIEW.run_options())
        row.update(status='success', review=result.output.model_dump(mode='json'))
    except Exception:
        # The existing transcript API retains known, sanitized failure categories.
        # Do not save raw exceptions, model names from exceptions, or provider bodies.
        pass
    if row['status'] == 'success' and case['expected'] is not None:
        row['existing_control_grade'] = grade_review(
            RiskCodeEvalCase.model_validate(case['expected']), result.output).model_dump(mode='json')
    row.update(exchanges=[e.model_dump(mode='json') for e in recorder.exchanges],
               usage=TypeAdapter(RunUsage).dump_python(usage, mode='json') if usage.requests else None,
               usage_complete=row['status'] == 'success')
    return row


def make_agent(model_name):
    from apps.backend.config import get_settings
    from pydantic_ai.models.openai import OpenAIResponsesModel
    from pydantic_ai.providers.openai import OpenAIProvider
    from src.linger.agents.provenance.agent import build_provenance_agent
    return build_provenance_agent(OpenAIResponsesModel(model_name.split(':', 1)[1],
        provider=OpenAIProvider(api_key=get_settings().api_key_for('openai')),
        settings=dict(MODEL_SETTINGS)))


async def execute(prepared, folder):
    import logfire
    from apps.backend.telemetry import configure_component_evaluation_telemetry
    results = []
    for model_name in MODELS:
        agent = make_agent(model_name)
        configure_component_evaluation_telemetry(agent)
        for case in prepared['cases']:
            row = await review_once(agent, case)
            row['model'] = model_name
            results.append(row)
            write(folder / 'results.json', results)
    logfire.force_flush()
    return dict(kind=prepared['kind'], models=list(MODELS), model_settings=MODEL_SETTINGS,
        results_count=len(results), successful_reviews=sum(r['status'] == 'success' for r in results),
        source_unchanged=source_hashes() == prepared['source_hashes'],
        saved_inputs_unchanged=all(digest(Path(c['source_file']).read_bytes()) == c['source_sha256']
                                   for c in prepared['cases']),
        semantic_review_required=True, all_pass=None, production_model_changed=False)


def main(args):
    prepared = plan(args.inputs.resolve())
    if not args.execute:
        print(json.dumps({**prepared, 'cases': [
            {k: v for k, v in c.items() if k not in ('input_prompt', 'expected')}
            for c in prepared['cases']]}, indent=2))
        return
    if tuple(args.approved_models or ()) != MODELS:
        raise ValueError('Live execution requires separate approval for both exact models; pass --approved-models only after approval')
    folder, reservation = reserve(args.budget.resolve(), BASE, prepared)
    # A failed or interrupted run consumes its reservation; never refund/retry it.
    summary = asyncio.run(execute(prepared, folder))
    write(folder / 'summary.json', summary)
    with args.budget.resolve().with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        budget = read(args.budget.resolve())
        entry = next(e for e in budget['iterations'] if e['reservation_id'] == reservation['reservation_id'])
        entry.update(status='complete', finished_at=now(), summary=str(folder / 'summary.json'),
                     all_pass=None, semantic_review_required=True)
        write(args.budget.resolve(), budget)
    print(folder)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, default=DEFAULT_INPUT)
    parser.add_argument('--budget', type=Path, default=BASE / 'live-budget.json')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--approved-models', nargs=2, choices=MODELS)
    main(parser.parse_args())
