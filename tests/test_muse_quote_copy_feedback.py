"""Copy diagnostics show exact reply formatting while preserving strict validation."""

import json
from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry

from src.linger.agents.muse.agent import validate_muse_output
from src.linger.orchestration.turn_context import reset_turn_evidence, set_turn_evidence
from tests.test_muse_quote_repair import candidate, record


QUOTE = 'the pool of tears which she had wept when\nshe was nine feet high'
SOURCE = 'She was in ' + QUOTE + '.'


@pytest.mark.parametrize(('shown', 'declared'), [
    (QUOTE.replace('\n', ' ') + '.', QUOTE.replace('\n', ' ')),
    (QUOTE.replace('\n', ' ') + '.', QUOTE),
    (QUOTE.replace('\n', '\n> ') + '.', QUOTE),
    (QUOTE + '.', QUOTE),
])
def test_reports_complete_reply_occurrence_and_exact_copy_differences(shown, declared):
    output = candidate(declared).model_copy(update={'reply': 'The narrator says: “' + shown + '”'})
    output = output.model_copy(update={'evidence_uses': (
        output.evidence_uses[0].model_copy(update={'supported_claims': (output.reply,)}),
    )})
    before = output.model_dump()
    token = set_turn_evidence((record(SOURCE),))
    try:
        with pytest.raises(ModelRetry) as caught:
            validate_muse_output(SimpleNamespace(), output)
        error, = json.loads(str(caught.value))['errors']
        repair = error['reply_quote_repair']
        assert repair['current_reply_quote'] == shown
        assert output.reply[repair['response_start']:repair['response_end']] == shown
        assert repair['suggested_quote'] == QUOTE + '.'
        assert repair['suggested_quote'] in SOURCE
        assert repair['declaration_differences'][-1]['current_text'] == ''
        assert repair['declaration_differences'][-1]['source_text'] == '.'
        if shown != QUOTE + '.':
            assert repair['reply_differences']
        assert output.model_dump() == before
        fixed = repair['suggested_quote']
        corrected = candidate(fixed)
        assert validate_muse_output(SimpleNamespace(), corrected) is corrected
    finally:
        reset_turn_evidence(token)


@pytest.mark.parametrize('reply', [
    '“' + QUOTE.replace('nine', 'eight') + '”',
    '“' + QUOTE.replace('\n', ' ') + '” and “' + QUOTE.replace('\n', ' ') + '”',
])
def test_does_not_guess_an_altered_or_ambiguous_reply_occurrence(reply):
    output = candidate(QUOTE).model_copy(update={'reply': reply, 'evidence_uses': (
        candidate(QUOTE).evidence_uses[0].model_copy(update={'supported_claims': (reply,)}),
    )})
    token = set_turn_evidence((record(SOURCE),))
    try:
        with pytest.raises(ModelRetry) as caught:
            validate_muse_output(SimpleNamespace(), output)
        error, = json.loads(str(caught.value))['errors']
        assert 'reply_quote_repair' not in error
    finally:
        reset_turn_evidence(token)
