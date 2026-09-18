"""Revision repairs retain accepted mappings without inheriting their authority."""

import json
from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry

from apps.backend.contracts import ContextResolution, MuseRevisionInput, MuseRevisionReview, MuseTurn, TurnPolicy
from src.linger.agents.muse.agent import validate_muse_output
from src.linger.agents.muse.claim_repair import accepted_claims_for_revision, retained_claim_errors
from src.linger.agents.muse.models import MuseCandidate
from src.linger.agents.provenance.models import ProvenanceReview
from src.linger.orchestration.turn_context import reset_turn_evidence, set_turn_evidence
from tests.test_muse_repair_feedback import BOOK


CLAIM = "The knowledge does not solve the problem."


def candidate(reply=CLAIM, claims=(CLAIM,), quote=None):
    return MuseCandidate.model_validate({
        "reply": reply,
        "evidence_uses": [{
            "source_kind": "book_corpus", "evidence_id": BOOK.evidence_id,
            "source_location": BOOK.location, "supported_claims": list(claims),
            "exact_quote": quote,
        }] if claims else [],
        "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
    })


def review(*, supported=True, location=None):
    return ProvenanceReview.model_validate({
        "response_decision": "revise", "capture_decision": "no_candidate",
        "emotional_boundary_decision": "not_required",
        "findings": [{
            "code": "unsupported_claim", "applies_to": "response",
            "location": location or {
                "kind": "text_span", "source_field": "candidate.response", "path": "", "quote": "Other fault.",
            },
            "explanation": "Fixture review of another defect.",
        }],
        "claim_audit": [{
            "group_index": 0, "supported": supported,
            "support_summary": "Fixture verdict on whether knowledge solves the stated problem.",
            "source_contributions": [{
                "declaration_index": 0, "claim_index": 0,
                "contributes": True, "source_excerpt": BOOK.text,
            }],
        }],
    })


def revision_context(*, claims=(), quotes=(), reader_lines=()):
    payload = MuseRevisionInput(
        mode="revision",
        muse_turn=MuseTurn(
            turn_id="revision", user_message="Help me reflect.", reading_context=None,
            policy=TurnPolicy(allow_retrieval=False, allow_connection=False),
        ),
        context_resolution=ContextResolution(status="unknown", explanation="Test context."),
        review=MuseRevisionReview(
            findings=review().response_findings,
            previously_accepted_claims=claims, source_quote_interiors=quotes,
            released_reader_lines=reader_lines,
        ),
    )
    return SimpleNamespace(prompt=payload.model_dump_json())


def test_only_untouched_accepted_groups_create_revision_obligations():
    draft = candidate(CLAIM + " Other fault.")
    assert accepted_claims_for_revision(draft, review()) == (CLAIM,)
    assert accepted_claims_for_revision(draft, review(supported=False)) == ()
    for path in ("/0", "/0/evidence_id", "/0/exact_quote", "/0/supported_claims/0"):
        rejected = review(location={
            "kind": "structural", "source_field": "candidate.evidence_uses", "path": path,
        })
        assert accepted_claims_for_revision(draft, rejected) == ()


def test_overlapping_or_global_findings_remove_preservation_obligation():
    draft = candidate(CLAIM + " Other fault.")
    for location in (
        {"kind": "text_span", "source_field": "candidate.response", "path": "", "quote": "knowledge"},
        {"kind": "structural", "source_field": "candidate.response", "path": ""},
        {"kind": "structural", "source_field": "context.policy", "path": ""},
    ):
        assert accepted_claims_for_revision(draft, review(location=location)) == ()


def test_rejected_overbroad_mapping_can_be_removed_without_deleting_reflection():
    draft = candidate("You might ask what still matters.", ("You might ask what still matters.",))
    obligations = accepted_claims_for_revision(draft, review(supported=False))
    assert retained_claim_errors(candidate(draft.reply, ()), obligations) == []


def test_unchanged_claim_cannot_lose_coverage_but_split_or_expanded_spans_work():
    assert retained_claim_errors(candidate(claims=()), (CLAIM,))
    split = candidate(claims=("The knowledge ", "does not solve the problem."))
    assert retained_claim_errors(split, (CLAIM,)) == []
    expanded = candidate(CLAIM + " More context.", (CLAIM + " More context.",))
    assert retained_claim_errors(expanded, (CLAIM,)) == []
    assert retained_claim_errors(candidate("A different interpretation.", ()), (CLAIM,)) == []


def test_all_retained_occurrences_need_current_coverage():
    repeated = candidate(CLAIM + " However, " + CLAIM, (CLAIM + " However,",))
    errors = retained_claim_errors(repeated, (CLAIM,))
    assert len(errors) == 1
    assert errors[0]["response_start"] == repeated.reply.rfind(CLAIM)


def test_actual_muse_validator_repairs_lost_mapping_in_existing_output_budget():
    with pytest.raises(ModelRetry) as caught:
        validate_muse_output(revision_context(claims=(CLAIM,)), candidate(claims=()))
    assert "dropped part or all" in str(caught.value)


def test_retained_source_quote_needs_full_current_canonical_binding():
    token = set_turn_evidence((BOOK,))
    try:
        words = "We’re fixing it,"
        context = revision_context(quotes=(words,))
        reply = f'“{words}”'
        for quote in (None, "fixing it"):
            with pytest.raises(ModelRetry) as caught:
                validate_muse_output(context, candidate(reply, (reply,), quote))
            assert any(error["value"] == words for error in json.loads(str(caught.value))["errors"])
        assert validate_muse_output(context, candidate(reply, (reply,), words)).reply == reply
    finally:
        reset_turn_evidence(token)


def test_retained_earlier_reader_quote_uses_only_released_reader_lines():
    words = "I kept thinking about the meeting."
    reply = f'You wrote: “{words}”'
    output = MuseCandidate.model_validate({
        "reply": reply, "evidence_uses": [{
            "source_kind": "session_line", "quote": words, "supported_claims": [reply],
        }],
        "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
    })
    with pytest.raises(ModelRetry):
        validate_muse_output(revision_context(quotes=(words,)), output)
    assert validate_muse_output(
        revision_context(quotes=(words,), reader_lines=(f"Yesterday {words}",)), output,
    ) == output


def test_retained_source_quote_punctuation_change_still_needs_complete_binding():
    token = set_turn_evidence((BOOK,))
    try:
        words = "We’re fixing it,"
        context = revision_context(quotes=("We’re fixing it.",))
        reply = f'“{words}”'
        with pytest.raises(ModelRetry) as caught:
            validate_muse_output(context, candidate(reply, (reply,), words[:-1]))
        assert any(error["value"] == words for error in json.loads(str(caught.value))["errors"])
        assert validate_muse_output(context, candidate(reply, (reply,), words)).reply == reply
    finally:
        reset_turn_evidence(token)


@pytest.mark.parametrize("reply", [
    'Proposed wording: “The phrase ‘We’re fixing it’ stays with me.”',
    '“We’re fixing something else.”',
    'We’re fixing it,',
])
def test_quote_retention_does_not_classify_new_or_unquoted_wording(reply):
    token = set_turn_evidence((BOOK,))
    try:
        output = candidate(reply, (reply,))
        assert validate_muse_output(revision_context(quotes=("We’re fixing it.",)), output) == output
    finally:
        reset_turn_evidence(token)


def test_new_declared_quote_cannot_omit_visible_terminal_punctuation():
    token = set_turn_evidence((BOOK,))
    try:
        reply = '“We’re fixing it,”'
        with pytest.raises(ModelRetry) as caught:
            validate_muse_output(SimpleNamespace(), candidate(reply, (reply,), 'We’re fixing it'))
        assert 'complete quoted occurrence' in str(caught.value)
        assert validate_muse_output(SimpleNamespace(), candidate(reply, (reply,), 'We’re fixing it,')).reply == reply
    finally:
        reset_turn_evidence(token)


@pytest.mark.parametrize('reply', [
    'We’re fixing it. Proposed wording: “We’re fixing it.”',
    '“We’re fixing it” is the phrase. Proposed wording: “We’re fixing it.”',
    'Proposed wording: “The phrase ‘We’re fixing it’ stays with me.”',
])
def test_new_quote_edge_check_does_not_reclassify_other_wording(reply):
    token = set_turn_evidence((BOOK,))
    try:
        output = candidate(reply, (reply,), 'We’re fixing it')
        assert validate_muse_output(SimpleNamespace(), output) == output
    finally:
        reset_turn_evidence(token)


def test_complete_canonical_declaration_covers_other_partial_quote_declaration():
    token = set_turn_evidence((BOOK,))
    try:
        reply = '“We’re fixing it,”'
        partial = candidate(reply, (reply,), 'We’re fixing it')
        complete = candidate(reply, (reply,), 'We’re fixing it,')
        output = partial.model_copy(update={
            'evidence_uses': (*partial.evidence_uses, *complete.evidence_uses),
        })
        assert validate_muse_output(SimpleNamespace(), output) == output
        unknown = complete.evidence_uses[0].model_copy(update={'evidence_id': 'unavailable'})
        with pytest.raises(ModelRetry) as caught:
            validate_muse_output(SimpleNamespace(), partial.model_copy(update={
                'evidence_uses': (*partial.evidence_uses, unknown),
            }))
        assert 'complete quoted occurrence' in str(caught.value)
    finally:
        reset_turn_evidence(token)


def test_overlap_projection_preserves_whole_claims_without_optional_source_obligations():
    from tests.test_provenance_group_audit import overlap_request, overlap_review

    task = overlap_request("First shared last. Other fault.", "First shared", "shared last")
    draft = MuseCandidate.model_validate({
        "reply": task.candidate.response,
        "evidence_uses": [use.model_dump(mode="json") for use in task.candidate.evidence_uses],
        "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
    })
    finding = {
        "code": "unsupported_claim", "applies_to": "response",
        "location": {"kind": "text_span", "source_field": "candidate.response", "path": "",
                     "quote": "Other fault."},
        "explanation": "Independent defect outside both claims.",
    }
    verdict = overlap_review(task, false_members={(0, 1), (1, 0)}, findings=[finding])
    task.validate_review(verdict)
    assert accepted_claims_for_revision(draft, verdict) == ("First shared", "shared last")
    incomplete = overlap_review(task, false_members={(0, 0)}, findings=[finding])
    assert accepted_claims_for_revision(draft, incomplete) == ("shared last",)
