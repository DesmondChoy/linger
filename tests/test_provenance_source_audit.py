"""Complete response coverage is mechanical; semantic classification is the reviewer's job."""

import pytest

from src.linger.agents.provenance.models import ProvenanceInput, ProvenanceReview


def task(*, declare=True, extra_source=False):
    sources = [{"source_kind": "memory", "evidence_id": "memory-used",
                "excerpt": "I found the billing error and fixed it, but said nothing."}]
    if extra_source:
        sources.append({"source_kind": "memory", "evidence_id": "memory-unused",
                        "excerpt": "I prefer to read on the train."})
    return ProvenanceInput.model_validate({
        "context": {"policy": {"allow_retrieval": False, "allow_connection": True,
                               "allow_memory_capture": False}, "reading_context": None},
        "canonical_connection_evidence": sources,
        "candidate": {
            "response": "Your note says you fixed the error. You could consider what sharing it would mean.",
            "evidence_uses": ([{"source_kind": "memory", "evidence_id": "memory-used",
                                "supported_claims": ["Your note says you fixed the error."]}] if declare else []),
            "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
        },
        "current_line": {"text": "Can we reflect on my earlier note?"},
    })


def review(*, declare=True, supported=True, finding=None):
    return ProvenanceReview.model_validate({
        "response_decision": "revise" if finding else "pass",
        "emotional_boundary_decision": "not_required", "capture_decision": "no_candidate",
        "findings": [finding] if finding else [],
        "coverage_audit": [{"span_index": 0,
                            "classification": "reader_reflection" if declare else "source_dependent"}],
        "claim_audit": ([{"group_index": 0, "supported": supported,
                          "support_summary": "Fixture verdict on the note's support for the claimed correction.",
                          "source_contributions": [{"declaration_index": 0, "claim_index": 0,
                                                    "contributes": supported,
                                                    "source_excerpt": "I found the billing error and fixed it" if supported else None}]}]
                        if declare else []),
    })


def response_finding():
    return {"code": "unresolved_evidence", "applies_to": "response",
            "location": {"kind": "text_span", "source_field": "candidate.response", "path": "",
                         "quote": "Your note says you fixed the error."},
            "explanation": "Declare the memory actually used by this claim."}


def test_unused_canonical_memory_needs_no_declaration():
    task(extra_source=True).validate_review(review())


def test_used_memory_omission_requires_current_finding_even_when_fact_true():
    request = task(declare=False)
    with pytest.raises(ValueError, match="undeclared source use requires a finding"):
        request.validate_review(review(declare=False))
    request.validate_review(review(declare=False, finding=response_finding()))


def test_unsupported_mapping_needs_its_own_finding():
    request = task()
    with pytest.raises(ValueError, match="unsupported declared claim requires a finding"):
        request.validate_review(review(supported=False))
    request.validate_review(review(supported=False, finding=response_finding()))


@pytest.mark.parametrize("field", ["coverage_audit", "claim_audit"])
def test_review_cannot_silently_skip_audit_coverage(field):
    incomplete = review().model_copy(update={field: ()})
    with pytest.raises(ValueError, match="must assess every"):
        task().validate_review(incomplete)


def test_gap_offsets_preserve_unicode_punctuation_and_every_occurrence():
    raw = task().model_dump(mode="json")
    raw["candidate"]["response"] = "🙂 Covered. + Covered. / tail"
    raw["candidate"]["evidence_uses"][0]["supported_claims"] = ["Covered."]
    request = ProvenanceInput.model_validate(raw)
    spans = request.uncovered_response_spans
    assert [(s.span_index, s.start, s.end, s.text) for s in spans] == [
        (0, 0, 2, "🙂 "), (1, 10, 13, " + "), (2, 21, 28, " / tail"),
    ]
    assert all(request.candidate.response[s.start:s.end] == s.text for s in spans)


def test_overlapping_and_adjacent_claims_are_unioned_without_missing_tail():
    raw = task().model_dump(mode="json")
    raw["candidate"]["response"] = "prefix abcdefghi tail"
    raw["candidate"]["evidence_uses"][0]["supported_claims"] = ["abcdef", "defghi", "prefix "]
    request = ProvenanceInput.model_validate(raw)
    assert [span.text for span in request.uncovered_response_spans] == [" tail"]


def test_zero_sources_and_no_declarations_still_require_whole_reply_audit():
    request = task(declare=False).model_copy(update={"canonical_connection_evidence": ()})
    assert request.uncovered_response_spans[0].text == request.candidate.response
    with pytest.raises(ValueError, match="every uncovered response span"):
        request.validate_review(review(declare=False).model_copy(update={"coverage_audit": ()}))


def test_fake_large_declaration_does_not_remove_claim_support_gate():
    raw = task().model_dump(mode="json")
    raw["candidate"]["evidence_uses"][0]["supported_claims"] = [raw["candidate"]["response"]]
    request = ProvenanceInput.model_validate(raw)
    assert request.uncovered_response_spans == ()
    checked = review(supported=False).model_copy(update={"coverage_audit": ()})
    with pytest.raises(ValueError, match="unsupported declared claim requires a finding"):
        request.validate_review(checked)


def test_true_claim_with_wrong_named_record_stays_unresolved():
    raw = task(extra_source=True).model_dump(mode="json")
    raw["candidate"]["evidence_uses"][0]["evidence_id"] = "memory-unused"
    request = ProvenanceInput.model_validate(raw)
    with pytest.raises(ValueError, match="unsupported declared claim requires a finding"):
        request.validate_review(review(supported=False))
    finding = response_finding()
    finding["location"] = {"kind": "structural", "source_field": "candidate.evidence_uses",
                           "path": "/0/supported_claims/0"}
    request.validate_review(review(supported=False, finding=finding))


def test_current_input_errors_are_aggregated_with_exact_repair_targets():
    request = task(declare=False)
    raw = review(declare=False, finding=response_finding()).model_dump(mode="json")
    raw["findings"][0]["location"]["quote"] = "your note says you fixed the error."
    raw["coverage_audit"].append({"span_index": 9, "classification": "presentation"})
    with pytest.raises(ValueError) as failure:
        request.validate_review(ProvenanceReview.model_validate(raw))
    errors = {issue["path"]: issue for issue in failure.value.errors}
    assert errors["findings[0].location.quote"]["current_target"] == request.candidate.response
    assert errors["coverage_audit"]["current_target"] == [
        request.uncovered_response_spans[0].model_dump(mode="json"),
    ]
    assert "coverage_audit[0].classification" in errors


@pytest.mark.parametrize("indices", [[], [0, 0], [1]])
def test_coverage_indices_require_exact_current_coverage(indices):
    raw = review().model_dump(mode="json")
    raw["coverage_audit"] = [{"span_index": index, "classification": "presentation"} for index in indices]
    with pytest.raises(ValueError, match="every uncovered response span exactly once"):
        task().validate_review(ProvenanceReview.model_validate(raw))


def test_finding_must_overlap_current_gap_not_another_declared_part():
    raw = review(finding=response_finding()).model_dump(mode="json")
    raw["coverage_audit"][0]["classification"] = "source_dependent"
    with pytest.raises(ValueError, match="finding overlapping"):
        task().validate_review(ProvenanceReview.model_validate(raw))
    # A finding can cross the boundary: exact overlap, not containment, is required.
    raw["findings"][0]["location"]["quote"] = "fixed the error. You could"
    task().validate_review(ProvenanceReview.model_validate(raw))


def test_structural_response_finding_does_not_satisfy_specific_gap():
    finding = response_finding()
    finding["location"] = {"kind": "structural", "source_field": "candidate.response", "path": ""}
    with pytest.raises(ValueError, match="finding overlapping"):
        task(declare=False).validate_review(review(declare=False, finding=finding))


def test_forged_coverage_and_groups_are_recomputed_and_model_copy_is_current():
    request = task()
    raw = request.model_dump(mode="json")
    raw["uncovered_response_spans"] = []
    raw["claim_support_groups"] = [{"claim": "forged", "declarations": []}]
    restored = ProvenanceInput.model_validate(raw)
    assert restored == request
    assert restored.model_dump_json() == request.model_dump_json()
    changed = request.model_copy(update={"candidate": request.candidate.model_copy(update={
        "response": "A different complete reply.", "evidence_uses": (),
    })})
    assert changed.uncovered_response_spans[0].text == "A different complete reply."
    assert changed.claim_support_groups == ()


def test_exact_joint_claim_projection_lists_every_contributor_without_normalization():
    raw = task(extra_source=True).model_dump(mode="json")
    use = raw["candidate"]["evidence_uses"][0]
    raw["candidate"]["evidence_uses"].append({**use, "evidence_id": "memory-unused"})
    raw["candidate"]["evidence_uses"].append({
        "source_kind": "session_line", "quote": "I fixed the billing error.",
        "supported_claims": [use["supported_claims"][0], "Your note says you fixed the error"],
    })
    groups = ProvenanceInput.model_validate(raw).claim_support_groups
    assert len(groups) == 2
    assert [(d.declaration_index, d.claim_index) for d in groups[0].declarations] == [(0, 0), (1, 0), (2, 0), (2, 1)]
    assert [d.direct for d in groups[0].declarations] == [True, True, True, False]
    assert groups[0].declarations[0].evidence_id == "memory-used"
    assert groups[0].declarations[2].session_quote == "I fixed the billing error."
    assert [(d.declaration_index, d.claim_index) for d in groups[1].declarations if d.direct] == [(2, 1)]
    assert groups[0].claim != groups[1].claim
    assert groups[0].declarations[-1].coverage[0].text == "Your note says you fixed the error"


@pytest.mark.parametrize("field", ["source_audit", "source_references"])
def test_obsolete_interfaces_have_no_compatibility_alias(field):
    if field == "source_audit":
        raw = review().model_dump(mode="json")
        model = ProvenanceReview
    else:
        raw = task().model_dump(mode="json")
        model = ProvenanceInput
    raw[field] = []
    with pytest.raises(ValueError):
        model.model_validate(raw)
