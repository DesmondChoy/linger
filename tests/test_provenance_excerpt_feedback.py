"""Copy feedback is local evidence, never a substitute for the submitted proof."""
import asyncio
import json

import pytest
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from src.linger.agents.provenance.agent import build_provenance_agent
from src.linger.agents.provenance.skills import CANDIDATE_REVIEW
from tests.test_provenance_group_audit import checked, request

BAD = 'For some minutes he puffed away without speaking'
GOOD = 'For\nsome minutes it puffed away without speaking'


def test_private_copy_feedback_exposes_same_source_words_without_accepting_changed_pronoun():
    task = request(1)
    with pytest.raises(ValueError) as failure:
        task.validate_review(checked(task, excerpts=[BAD]))
    error = failure.value.errors[0]
    context = error['literal_source_context']
    assert GOOD in context
    assert BAD not in context
    assert context in task.contribution_source_text(0)
    assert error['value'] == BAD
    assert 'only whitespace may differ' in error['error']


def test_real_agent_repairs_literal_words_within_existing_output_budget():
    task = request(1)
    calls = 0
    def respond(messages, info):
        nonlocal calls
        calls += 1
        retries = [p for m in messages for p in m.parts if isinstance(p, RetryPromptPart)]
        if calls == 1:
            output = checked(task, excerpts=[BAD])
        else:
            payload = json.loads(retries[-1].content)
            assert GOOD in payload['errors'][0]['literal_source_context']
            output = checked(task, excerpts=[GOOD])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output.model_dump(mode='json'))])
    result = asyncio.run(build_provenance_agent(FunctionModel(respond)).run(task.model_dump_json(), **CANDIDATE_REVIEW.run_options()))
    assert calls == 2
    assert result.output.claim_audit[0].source_contributions[0].source_excerpt == GOOD
    task.validate_review(result.output)


def test_copy_hint_is_exact_bounded_and_not_available_for_ambiguous_or_unrelated_sources():
    from src.linger.agents.provenance.excerpt_feedback import literal_source_context
    assert literal_source_context(BAD, None) is None
    assert literal_source_context(BAD, 'An entirely unrelated account of a journey.') is None
    assert literal_source_context(BAD, (GOOD + '. ') * 2) is None
    assert literal_source_context(BAD, GOOD + ' ' + 'word ' * 2049) is None
    assert literal_source_context('word ' * 200, GOOD) is None
    context = literal_source_context(BAD, 'Before.\n' + GOOD + ', then it stopped.\nAfter.')
    assert GOOD in context
    assert context in 'Before.\n' + GOOD + ', then it stopped.\nAfter.'


def test_wrong_record_remains_rejected_even_when_another_supplied_record_has_the_words():
    task = request(0)
    with pytest.raises(ValueError, match='this named canonical source') as failure:
        task.validate_review(checked(task, excerpts=[GOOD]))
    error = failure.value.errors[0]
    if error['literal_source_context'] is not None:
        assert error['literal_source_context'] in task.contribution_source_text(0)
    assert error['source_declaration']['evidence_id'].endswith('ln0960-1016')


def test_long_copy_context_includes_changed_words_before_the_longest_matching_tail():
    from src.linger.agents.provenance.excerpt_feedback import literal_source_context
    bad = ('For some minutes he puffed away without speaking, but at last he unfolded his arms, '
           'took the hookah out of his mouth again, and said, “So you\nthink you’re changed, do you?”')
    context = literal_source_context(bad, request(1).contribution_source_text(0))
    assert GOOD in context
    assert 'it unfolded\nits arms' in context
    assert context in request(1).contribution_source_text(0)
