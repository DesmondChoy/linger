"""Optional boundary proof permits only adopted, canonically bound additions."""

import json

import pytest
from pydantic import ValidationError

from evals.synthetic_journals.book_contract import BookContractError, compile_book_replay_plan
from evals.synthetic_journals.book_replay import _grade_proposal
from evals.synthetic_journals.models import ProposedGroundTruth, SyntheticBackstory
from tests.test_synthetic_book_contract import VERSION, _excerpt
from tests.test_synthetic_book_replay import _documents, replay_observed


def documents_with_optional():
    content, truth = _documents()
    facts = truth['book_scene_facts'][0]
    facts['scope']['optional_supporting_evidence_ids'] = ['optional']
    facts['evidence'].append(_excerpt(
        f'{VERSION}-ch01', '01-down-the-rabbit-hole.md', 'optional',
        'Alice was beginning to get very tired of sitting by her sister on the\nbank, and of having nothing to do:',
    ))
    facts['evidence'].append(_excerpt(
        f'{VERSION}-ch02', '02-the-pool-of-tears.md', 'unlisted',
        'she was nine feet high.',
    ))
    return content, truth


def compile_documents(content, truth):
    return compile_book_replay_plan(
        SyntheticBackstory.model_validate_json(json.dumps(content)),
        ProposedGroundTruth.model_validate_json(json.dumps(truth)),
    )


def test_earlier_optional_support_does_not_change_required_derived_ceiling():
    plan = compile_documents(*documents_with_optional())
    assert plan.scenes[0].safe_ceiling_chapter == 5
    assert plan.scenes[0].evidence_by_id['optional'].chapter_number == 1


@pytest.mark.parametrize('ids', [['missing'], ['later']])
def test_optional_support_must_resolve_within_required_ceiling(ids):
    content, truth = documents_with_optional()
    truth['book_scene_facts'][0]['scope']['optional_supporting_evidence_ids'] = ids
    with pytest.raises(BookContractError, match='optional supporting evidence'):
        compile_documents(content, truth)


@pytest.mark.parametrize('ids', [['optional', 'optional'], ['support']])
def test_optional_support_ids_are_unique_and_disjoint_from_required(ids):
    _, truth = documents_with_optional()
    truth['book_scene_facts'][0]['scope']['optional_supporting_evidence_ids'] = ids
    with pytest.raises(ValidationError, match='optional|disjoint'):
        ProposedGroundTruth.model_validate_json(json.dumps(truth))


@pytest.mark.parametrize('mutation,passes', [
    ('absent', True), ('present', True), ('missing_required', False),
    ('unlisted', False), ('forged', False), ('later', False), ('wrong_ceiling', False),
])
def test_both_objectives_grade_optional_support_without_weakening_required_proof(
    replay_observed, mutation, passes,
):
    _, run = replay_observed
    scene = compile_documents(*documents_with_optional()).scenes[0]
    observation = run.scenes[0]
    optional = min(scene.evidence_by_id['optional'].accepted_runtime_records, key=lambda r: len(r.text))
    required = observation.boundary_support_evidence
    actual = required
    if mutation == 'present':
        actual += (optional,)
    elif mutation == 'missing_required':
        actual = (optional,)
    elif mutation == 'unlisted':
        actual += (scene.evidence_by_id['unlisted'].accepted_runtime_records[0],)
    elif mutation == 'forged':
        actual += (optional.model_copy(update={'text': optional.text + ' invented'}),)
    elif mutation == 'later':
        actual += (scene.evidence_by_id['later'].accepted_runtime_records[0],)
    observation = observation.model_copy(update={
        'boundary_support_evidence': actual,
        **({'routed_ceiling': 1} if mutation == 'wrong_ceiling' else {}),
    })
    assert len(scene.proposals) == 2
    for proposal in scene.proposals:
        grade = _grade_proposal(scene, proposal, observation)
        assert grade.hard_pass is passes, grade.failures
        if not passes and mutation != 'wrong_ceiling':
            assert 'boundary_support_differs_from_ground_truth' in grade.failures


def test_legacy_empty_optional_set_keeps_strict_support_check(replay_observed):
    plan, run = replay_observed
    scene, observation = plan.scenes[0], run.scenes[0]
    assert scene.facts.scope.optional_supporting_evidence_ids == ()
    extra = scene.evidence_by_id['later'].accepted_runtime_records[0]
    observation = observation.model_copy(update={
        'boundary_support_evidence': observation.boundary_support_evidence + (extra,),
    })
    assert all('boundary_support_differs_from_ground_truth' in _grade_proposal(
        scene, proposal, observation,
    ).failures for proposal in scene.proposals)
