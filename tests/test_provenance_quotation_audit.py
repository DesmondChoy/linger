"""Quoted reply spans need their own source binding, even inside mapped claims."""

import pytest

from src.linger.agents.muse.models import BookEvidenceUse, MemoryEvidenceUse, SessionLineUse
from src.linger.agents.provenance.quotation_audit import (
    QuotationAudit,
    quotation_audit_errors,
    quoted_response_spans,
    source_quote_interiors,
)


def book(quote, claim='The source says this.'):
    return BookEvidenceUse(source_kind='book_corpus', evidence_id='book-record',
                           source_location='Chapter 3', exact_quote=quote,
                           supported_claims=(claim,))


def audit(index=0, classification='source_quote', declaration_index=0):
    return QuotationAudit(span_index=index, classification=classification,
                          declaration_index=declaration_index)


def errors(reply, rows, uses=(), valid=(), current='', session=(), findings=()):
    return quotation_audit_errors(
        response=reply, audits=rows, evidence_uses=uses,
        valid_quote_declarations=set(valid), verified_session_lines=session,
        current_line=current,
        finding_overlaps=lambda start, end: any(a < end and start < b for a, b in findings),
    )


def test_projection_retains_exact_inner_offsets_newlines_markup_and_repeated_occurrences():
    reply = 'Before “First\n_part_” then "same" and “same”.'
    spans = quoted_response_spans(reply)
    assert [s.text for s in spans] == ['First\n_part_', 'same', 'same']
    assert [s.span_index for s in spans] == [0, 1, 2]
    assert all(reply[s.start:s.end] == s.text for s in spans)
    assert spans[1].start != spans[2].start


def test_projection_keeps_balanced_nested_pairs_and_ignores_single_and_unmatched_quotes():
    reply = '“She said "hello".” Then \'single\' and “unfinished'
    assert [s.text for s in quoted_response_spans(reply)] == ['She said "hello".', 'hello']


def test_missing_audit_duplicate_and_unknown_rows_require_complete_current_inventory():
    reply = '“first” and “second”'
    for rows in ((), (audit(), audit()), (audit(0), audit(7))):
        assert any(e['path'] == 'quotation_audit' for e in errors(reply, rows))


def test_mapped_claim_does_not_cover_undeclared_second_alice_quotation():
    reply = '“Everybody has won.” Then “Why, she, of course,” said the Dodo.'
    uses = (book('Everybody has won.', reply),)
    rows = (audit(0), audit(1))
    result = errors(reply, rows, uses, valid=(0,))
    assert [e['path'] for e in result] == ['quotation_audit[1].declaration_index']
    second = quoted_response_spans(reply)[1]
    assert errors(reply, rows, uses, valid=(0,), findings=((second.start, second.end),)) == []


def test_quoted_memory_in_closing_question_needs_exact_quote_not_just_claim_mapping():
    reply = 'Does “quieter sort of freedom” still fit?'
    use = MemoryEvidenceUse(source_kind='memory', evidence_id='selected-memory',
                            exact_quote=None, supported_claims=(reply,))
    assert errors(reply, (audit(),), (use,))
    bound = use.model_copy(update={'exact_quote': 'quieter sort of freedom'})
    assert errors(reply, (audit(),), (bound,), valid=(0,)) == []


@pytest.mark.parametrize('quote,valid', [
    ('one', (0,)),
    ('one two', ()),
    ('one\ntwo', (0,)),
])
def test_source_quote_requires_complete_current_occurrence_and_valid_source(quote, valid):
    assert errors('“one two”', (audit(),), (book(quote),), valid=valid)


def test_quote_bound_elsewhere_in_reply_does_not_cover_the_current_occurrence():
    reply = '“one two” differs from “one two three”.'
    uses = (book('one two three'),)
    rows = (audit(0), audit(1))
    result = errors(reply, rows, uses, valid=(0,))
    assert [e['path'] for e in result] == ['quotation_audit[0].declaration_index']


def test_same_quote_at_two_occurrences_requires_two_rows_but_can_share_one_declaration():
    reply = '“words” then “words”.'
    assert errors(reply, (audit(0), audit(1)), (book('words'),), valid=(0,)) == []


@pytest.mark.parametrize('classification', ['title', 'proposed_wording', 'scare_quote'])
def test_non_source_classifications_do_not_borrow_matching_source_text(classification):
    assert errors('Try “words”.', (audit(classification=classification, declaration_index=None),),
                  (book('words'),), valid=(0,)) == []


def test_current_reader_wording_requires_actual_current_line_not_memory_or_prior_session():
    row = audit(classification='current_reader_wording', declaration_index=None)
    assert errors('You said “words”.', (row,), current='My words matter.') == []
    assert errors('You said “words”.', (row,), current='Different.', session=('My words matter.',))


def test_previous_session_quote_uses_existing_verified_session_contract():
    reply = 'Earlier you said “a quieter sort of freedom”.'
    use = SessionLineUse(source_kind='session_line', quote='a quieter sort of freedom',
                         supported_claims=(reply,))
    assert errors(reply, (audit(),), (use,), session=('I want a quieter sort of freedom.',)) == []
    assert errors(reply, (audit(),), (use,), session=('Unrelated earlier statement.',))


def test_unknown_or_missing_declaration_cannot_be_autoassigned_to_matching_source():
    reply = '“words”'
    for index in (None, 5):
        assert errors(reply, (audit(declaration_index=index),), (book('words'),), valid=(0,))


def test_source_quote_finding_must_overlap_current_quoted_occurrence():
    reply = '“words” and unrelated text'
    row = audit(declaration_index=None)
    assert errors(reply, (row,), findings=((12, 26),))
    span = quoted_response_spans(reply)[0]
    assert errors(reply, (row,), findings=((span.start, span.end),)) == []


def test_only_source_quote_interiors_become_retention_obligations():
    spans = quoted_response_spans('“words” and “a title” and “words”.')
    rows = (audit(0), audit(1, 'title', None), audit(2))
    assert source_quote_interiors(spans, rows) == ('words',)


@pytest.mark.parametrize('finding_index,accepted', [(0, True), (1, False)])
def test_quote_fault_can_use_current_finding_on_its_own_declaration(finding_index, accepted):
    result = quotation_audit_errors(
        response='“words”', audits=(audit(),), evidence_uses=(book(None),),
        valid_quote_declarations=set(), verified_session_lines=(), current_line='',
        finding_overlaps=lambda start, end: False,
        finding_on_declaration=lambda index: index == finding_index,
    )
    assert (result == []) is accepted


def test_undeclared_quote_still_requires_its_response_finding():
    result = quotation_audit_errors(
        response='“words”', audits=(audit(declaration_index=None),),
        evidence_uses=(book(None),), valid_quote_declarations=set(),
        verified_session_lines=(), current_line='',
        finding_overlaps=lambda start, end: False,
        finding_on_declaration=lambda index: True,
    )
    assert len(result) == 1
    assert result[0]['value'] is None
    assert 'Keep the existing declaration index' in result[0]['error']
    assert 'With null, a finding on an evidence declaration cannot cover' in result[0]['error']
    assert result[0]['current_target']['text'] == 'words'


def test_unmatched_other_quote_style_does_not_hide_a_balanced_source_quotation():
    reply = 'She wrote “Use a 5" nail.”'
    assert [span.text for span in quoted_response_spans(reply)] == ['Use a 5" nail.']
