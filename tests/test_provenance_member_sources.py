"""Each claim member exposes only its named canonical source, without widening coverage."""

import pytest
from pydantic import ValidationError

from evals.provenance.claim_mapping import load_cases
from src.linger.agents.provenance.models import ProvenanceInput, StructuralLocation, TextSpanLocation


def task(index=3):
    return load_cases().cases[index].review_input


@pytest.mark.parametrize("index,expected_indices", [(0, [0]), (1, [1]), (2, [0]), (3, [0, 1])])
def test_projection_resolves_only_declared_records_even_when_other_evidence_is_available(index, expected_indices):
    request = task(index)
    members = request.claim_support_groups[0].declarations
    assert [member.canonical_source_text for member in members] == [
        request.canonical_book_evidence[i].text for i in expected_indices
    ]
    assert len(request.canonical_book_evidence) == 2
    if index in {0, 2}:
        assert "How doth the little busy bee" not in members[0].canonical_source_text
        assert "How doth the little busy bee" in request.canonical_book_evidence[1].text


@pytest.mark.parametrize("kind", ["memory", "web"])
@pytest.mark.parametrize("identity", ["valid", "missing", "wrong_kind"])
def test_connection_projection_preserves_exact_named_kind(kind, identity):
    raw = task(0).model_dump(mode="json")
    source = {"source_kind": kind, "evidence_id": "source-used", "excerpt": "Exact _markup_,\nspelling and space."}
    if kind == "web":
        source["title"] = "A public source"
    raw["canonical_connection_evidence"] = [source]
    use = {"source_kind": kind, "evidence_id": "source-used", "supported_claims": [raw["candidate"]["response"]]}
    if identity == "missing":
        use["evidence_id"] = "absent"
    elif identity == "wrong_kind":
        use["source_kind"] = "web" if kind == "memory" else "memory"
    raw["candidate"]["evidence_uses"] = [use]
    member = ProvenanceInput.model_validate(raw).claim_support_groups[0].declarations[0]
    assert member.canonical_source_text == (source["excerpt"] if identity == "valid" else None)


def test_unknown_book_source_does_not_fall_back_to_available_record():
    raw = task(0).model_dump(mode="json")
    raw["candidate"]["evidence_uses"][0]["evidence_id"] = "absent"
    assert ProvenanceInput.model_validate(raw).claim_support_groups[0].declarations[0].canonical_source_text is None


@pytest.mark.parametrize("verified", [True, False])
def test_session_projection_requires_the_exact_verified_quote(verified):
    raw = task(0).model_dump(mode="json")
    quote = "I felt unsure of myself."
    raw["canonical_session_lines"] = [quote if verified else "Earlier, I felt unsure of myself. That changed."]
    raw["candidate"]["evidence_uses"] = [{
        "source_kind": "session_line", "quote": quote,
        "supported_claims": [raw["candidate"]["response"]],
    }]
    member = ProvenanceInput.model_validate(raw).claim_support_groups[0].declarations[0]
    assert member.canonical_source_text == (quote if verified else None)


def test_serialized_member_text_and_coverage_cannot_override_canonical_inputs():
    original = task()
    raw = original.model_dump(mode="json")
    member = raw["claim_support_groups"][0]["declarations"][0]
    member["canonical_source_text"] = "Injected replacement text."
    member["coverage"] = []
    restored = ProvenanceInput.model_validate(raw)
    assert restored.claim_support_groups == original.claim_support_groups
    assert restored.claim_support_groups[0].declarations[0].canonical_source_text == original.canonical_book_evidence[0].text
    raw["canonical_book_evidence"][0]["text"] = "Changed authoritative input."
    assert ProvenanceInput.model_validate(raw).claim_support_groups[0].declarations[0].canonical_source_text == "Changed authoritative input."


def test_overlap_member_has_its_own_full_source_without_new_coverage():
    raw = task().model_dump(mode="json")
    raw["candidate"]["response"] = "Shared tail. Shared"
    for use, claim in zip(raw["candidate"]["evidence_uses"], ("Shared tail.", "Shared"), strict=True):
        use["supported_claims"] = [claim]
    request = ProvenanceInput.model_validate(raw)
    group = request.claim_support_groups[1]
    overlap = group.declarations[0]
    assert overlap.direct is False
    assert overlap.canonical_source_text == request.canonical_book_evidence[0].text
    assert [(c.occurrence_index, c.start, c.end, c.text) for c in overlap.coverage] == [(0, 0, 6, "Shared")]
    assert group.declarations[1].canonical_source_text == request.canonical_book_evidence[1].text
    assert len(group.declarations[1].coverage) == 2


@pytest.mark.parametrize("extra_quote", [None, "Offending text"])
def test_structural_locations_still_reject_extra_quote(extra_quote):
    raw = {"kind": "structural", "source_field": "candidate.evidence_uses", "path": "/0/supported_claims/0"}
    StructuralLocation.model_validate(raw)
    with pytest.raises(ValidationError, match="Extra inputs"):
        StructuralLocation.model_validate({**raw, "quote": extra_quote})


def test_text_span_locations_still_require_quoted_text():
    raw = {"kind": "text_span", "source_field": "candidate.response", "path": ""}
    with pytest.raises(ValidationError, match="Field required"):
        TextSpanLocation.model_validate(raw)
    assert TextSpanLocation.model_validate({**raw, "quote": "Exact text."}).quote == "Exact text."
