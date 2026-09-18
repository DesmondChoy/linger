"""Mechanical quote facts remain exact, source-bound and current after serialization."""

import json

import pytest

from evals.provenance.claim_mapping import load_cases
from src.linger.agents.provenance.models import ProvenanceInput


def quoted_request():
    raw = load_cases().cases[0].review_input.model_dump(mode="json")
    quote = "I know\nwho I _was_ when I got up this morning"
    raw["candidate"]["response"] = f'Alice says: “{quote}”.'
    use = raw["candidate"]["evidence_uses"][0]
    use["exact_quote"] = quote
    use["supported_claims"] = [raw["candidate"]["response"]]
    return ProvenanceInput.model_validate(raw)


def test_decoded_newline_and_markdown_match_round_trip_in_actual_prompt():
    request = quoted_request()
    encoded = request.model_dump_json()
    assert json.loads(encoded)["quote_checks"] == [{
        "declaration_index": 0, "source_found": True,
        "quote_in_source": True, "quote_in_response": True,
    }]
    assert ProvenanceInput.model_validate_json(encoded) == request


@pytest.mark.parametrize("change,source_found,source_match,response_match", [
    ("normalized_source", True, False, True),
    ("normalized_response", True, True, False),
    ("wrong_id", False, False, True),
    ("wrong_kind", False, False, True),
])
def test_exact_match_never_normalizes_or_borrows_another_source(
    change, source_found, source_match, response_match,
):
    request = quoted_request()
    raw = request.model_dump(mode="json")
    if change == "normalized_source":
        raw["canonical_book_evidence"][0]["text"] = raw["canonical_book_evidence"][0]["text"].replace("\n", " ")
    elif change == "normalized_response":
        raw["candidate"]["response"] = raw["candidate"]["response"].replace("\n", " ")
    elif change == "wrong_id":
        raw["candidate"]["evidence_uses"][0]["evidence_id"] = "unknown"
    else:
        use = raw["candidate"]["evidence_uses"][0]
        use["source_kind"] = "memory"
        del use["source_location"]
    # The serialized true flags above must not override the new current strings.
    check = ProvenanceInput.model_validate(raw).quote_checks[0]
    assert (check.source_found, check.quote_in_source, check.quote_in_response) == (
        source_found, source_match, response_match,
    )


@pytest.mark.parametrize("source_kind", ["memory", "web"])
def test_connection_quotes_match_the_named_kind_and_current_excerpt(source_kind):
    raw = quoted_request().model_dump(mode="json")
    quote = raw["candidate"]["evidence_uses"][0]["exact_quote"]
    raw["canonical_connection_evidence"] = [{
        "source_kind": source_kind, "evidence_id": "connection-source", "excerpt": quote,
        **({"title": "Opened source"} if source_kind == "web" else {}),
    }]
    use = raw["candidate"]["evidence_uses"][0]
    use.update(source_kind=source_kind, evidence_id="connection-source")
    del use["source_location"]
    request = ProvenanceInput.model_validate(raw)
    assert request.quote_checks[0].quote_in_source
    source = request.canonical_connection_evidence[0].model_copy(update={"excerpt": "Other text"})
    changed = request.model_copy(update={"canonical_connection_evidence": (source,)})
    assert not changed.quote_checks[0].quote_in_source
    assert request.quote_checks[0].quote_in_source


def test_supplied_computed_flags_cannot_forge_or_suppress_facts():
    raw = quoted_request().model_dump(mode="json")
    raw["quote_checks"] = [{"declaration_index": 99, "quote_in_source": False}]
    request = ProvenanceInput.model_validate(raw)
    assert request.quote_checks[0].declaration_index == 0
    assert request.quote_checks[0].quote_in_source
    raw["candidate"]["evidence_uses"][0]["exact_quote"] = None
    assert not ProvenanceInput.model_validate(raw).quote_checks


@pytest.mark.parametrize("valid", [True, False])
def test_only_canonically_matching_quotes_remove_response_gaps(valid):
    raw = quoted_request().model_dump(mode="json")
    use = raw["candidate"]["evidence_uses"][0]
    quote = use["exact_quote"]
    use["supported_claims"] = ["Alice says:"]
    if not valid:
        raw["canonical_book_evidence"][0]["text"] = "Different canonical text."
    request = ProvenanceInput.model_validate(raw)
    gaps = "".join(span.text for span in request.uncovered_response_spans)
    assert (quote not in gaps) is valid
    assert ProvenanceInput.model_validate_json(request.model_dump_json()) == request


def test_bound_quote_and_matching_location_label_need_no_duplicate_mapping():
    from provenance_fixtures import review_with_audits

    raw = quoted_request().model_dump(mode="json")
    use = raw["candidate"]["evidence_uses"][0]
    quote = use["exact_quote"]
    raw["candidate"]["response"] = f'In Chapter 5, the sentence is: “{quote}”.'
    use["supported_claims"] = [quote]
    request = ProvenanceInput.model_validate(raw)
    checked = review_with_audits(request, {
        "response_decision": "pass", "emotional_boundary_decision": "not_required",
        "capture_decision": "no_candidate",
    })
    request.validate_review(checked)
    assert len(checked.coverage_audit) == len(request.uncovered_response_spans)
    assert request.uncovered_response_spans[0].text == 'In Chapter 5, the sentence is: “'


def test_matching_quote_does_not_override_wrong_visible_location_finding():
    from provenance_fixtures import review_with_audits

    raw = quoted_request().model_dump(mode="json")
    use = raw["candidate"]["evidence_uses"][0]
    raw["candidate"]["response"] = f'In Chapter 9, the sentence is: “{use["exact_quote"]}”.'
    use["supported_claims"] = [use["exact_quote"]]
    request = ProvenanceInput.model_validate(raw)
    checked = review_with_audits(request, {
        "response_decision": "revise", "emotional_boundary_decision": "not_required",
        "capture_decision": "no_candidate", "findings": [{
            "code": "misattribution", "applies_to": "response",
            "location": {"kind": "text_span", "source_field": "candidate.response",
                         "path": "", "quote": "In Chapter 9"},
            "explanation": "The quoted canonical passage belongs to Chapter 5.",
        }],
    })
    assert request.quote_checks[0].quote_in_source
    request.validate_review(checked)
    assert checked.response_decision == "revise"


def test_quoted_span_projection_recomputes_forged_rows_and_round_trips():
    raw = quoted_request().model_dump(mode="json")
    raw["quoted_response_spans"] = [{"span_index": 99, "text": "forged"}]
    task = ProvenanceInput.model_validate(raw)
    span, = task.quoted_response_spans
    assert span.span_index == 0
    assert task.candidate.response[span.start:span.end] == span.text
    assert span.text == task.candidate.evidence_uses[0].exact_quote
    assert ProvenanceInput.model_validate_json(task.model_dump_json()) == task


def quotation_review(task, finding_path=None):
    from provenance_fixtures import review_with_audits

    return review_with_audits(task, {
        "response_decision": "revise" if finding_path is not None else "pass",
        "emotional_boundary_decision": "not_required", "capture_decision": "no_candidate",
        "quotation_audit": [{"span_index": 0, "classification": "source_quote", "declaration_index": 0}],
        "findings": [] if finding_path is None else [{
            "code": "misattribution", "applies_to": "response",
            "location": {"kind": "structural", "source_field": "candidate.evidence_uses", "path": finding_path},
            "explanation": "The source quotation is not bound to its declared source.",
        }],
    })


def test_source_quote_binding_uses_current_canonical_text_not_supplied_flags():
    raw = quoted_request().model_dump(mode="json")
    raw["canonical_book_evidence"][0]["text"] = "Different canonical source text."
    task = ProvenanceInput.model_validate(raw)
    with pytest.raises(ValueError, match="source quotation is not fully covered"):
        task.validate_review(quotation_review(task))


@pytest.mark.parametrize("finding_path", ["/0", "/0/exact_quote", "/0/evidence_id"])
def test_unbound_quote_accepts_current_finding_on_own_declaration(finding_path):
    raw = quoted_request().model_dump(mode="json")
    raw["candidate"]["evidence_uses"][0]["exact_quote"] = None
    task = ProvenanceInput.model_validate(raw)
    task.validate_review(quotation_review(task, finding_path))


@pytest.mark.parametrize("finding_path", ["/1/exact_quote", "/0/supported_claims/0"])
def test_unbound_quote_cannot_use_unrelated_mapping_finding(finding_path):
    raw = quoted_request().model_dump(mode="json")
    use = raw["candidate"]["evidence_uses"][0]
    use["exact_quote"] = None
    raw["candidate"]["evidence_uses"].append(dict(use))
    task = ProvenanceInput.model_validate(raw)
    with pytest.raises(ValueError, match="source quotation is not fully covered"):
        task.validate_review(quotation_review(task, finding_path))
