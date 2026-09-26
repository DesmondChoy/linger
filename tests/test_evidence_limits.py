"""A declared evidence limit has its own home: covered, audited, and repairable."""

from types import SimpleNamespace

import pytest

from src.linger.agents.muse.models import (
    MuseCandidate, memory_attribution_errors, source_application_errors, supported_claim_errors,
)
from src.linger.agents.provenance.models import ProvenanceInput, ProvenanceReview
from src.linger.agents.provenance.review_context import reset_review_input, set_review_input
from src.linger.agents.provenance.review_validation import validate_provenance_review

URL = "https://example.org/essay"
SOURCE = "A mind is a procession of passing moods, each giving way to the next."
CLAIM = f"The essay calls a mind a procession of passing moods ([Essay]({URL}))"
LIMIT = "It does not say whether your promise lapses when your mood changes."
REFLECTION = "What would keeping it look like this week?"
REPLY = f"{CLAIM}. {LIMIT} {REFLECTION}"


def use(*, limits=(LIMIT,)):
    return {"source_kind": "web", "evidence_id": URL,
            "supported_claims": [CLAIM], "limit_claims": list(limits)}


def task(*, limits=(LIMIT,)):
    return ProvenanceInput.model_validate({
        "context": {"policy": {"allow_retrieval": False, "allow_connection": True,
                               "allow_memory_capture": False}, "reading_context": None},
        "canonical_connection_evidence": [
            {"source_kind": "web", "evidence_id": URL, "title": "Essay", "excerpt": SOURCE},
        ],
        "candidate": {
            "response": REPLY, "evidence_uses": [use(limits=limits)],
            "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
        },
        "current_line": {"text": "Does this essay let me off the hook for hosting?"},
    })


def review(request, *, withholds_only=True, accurate=True, findings=()):
    coverage = [{"span_index": span.span_index, "classification": "reader_reflection"}
                for span in request.uncovered_response_spans]
    return ProvenanceReview.model_validate({
        "response_decision": "revise" if findings or not (withholds_only and accurate) else "pass",
        "emotional_boundary_decision": "not_required", "capture_decision": "no_candidate",
        "findings": list(findings),
        "coverage_audit": coverage,
        "claim_audit": [{"group_index": 0, "supported": True,
                         "support_summary": "The page calls the mind a procession of moods.",
                         "source_contributions": [{"declaration_index": 0, "claim_index": 0,
                                                   "contributes": True,
                                                   "source_excerpt": "A mind is a procession of passing moods"}]}],
        "limit_audit": [{"limit_index": index, "withholds_only": withholds_only, "accurate": accurate}
                        for index in range(len(request.evidence_limit_claims))],
    })


def test_a_limit_is_covered_projected_with_its_source_and_exempt_from_reader_address():
    request = task()
    assert [span.text for span in request.uncovered_response_spans] == [". ", " " + REFLECTION]
    limit, = request.evidence_limit_claims
    assert (limit.declaration_index, limit.claim_index, limit.text) == (0, 0, LIMIT)
    assert limit.canonical_source_text == SOURCE
    candidate = MuseCandidate.model_validate({
        "reply": REPLY, "evidence_uses": [use()],
        "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
    })
    assert source_application_errors(candidate.reply, candidate.evidence_uses) == []
    request.validate_review(review(request))


def test_limit_spans_must_be_exact_and_separate_from_supported_claims():
    for limits, problem in (((LIMIT + "!",), "exact span"), ((CLAIM,), "also declared")):
        candidate = MuseCandidate.model_validate({
            "reply": REPLY, "evidence_uses": [use(limits=limits)],
            "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
        })
        error, = supported_claim_errors(candidate.reply, candidate.evidence_uses)
        assert error["path"] == "evidence_uses[0].limit_claims[0]"
        assert problem in error["error"]


def test_session_line_declarations_cannot_carry_limits():
    with pytest.raises(ValueError):
        MuseCandidate.model_validate({
            "reply": "You said you would host next month.",
            "evidence_uses": [{"source_kind": "session_line", "quote": "I would host next month",
                               "supported_claims": ["You said you would host next month."],
                               "limit_claims": ["You said"]}],
            "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
        })


def test_every_limit_must_be_audited():
    request = task()
    with pytest.raises(ValueError, match="every declared evidence limit"):
        request.validate_review(review(request).model_copy(update={"limit_audit": ()}))


@pytest.mark.parametrize("verdict", [{"withholds_only": False}, {"accurate": False}])
def test_a_rejected_limit_needs_a_finding_and_the_validator_derives_it(verdict):
    request = task()
    rejected = review(request, **verdict, findings=[{
        "code": "unsupported_claim", "applies_to": "response",
        "location": {"kind": "text_span", "source_field": "candidate.response", "path": "",
                     "quote": REFLECTION},
        "explanation": "Fixture finding elsewhere in the reply.",
    }])
    with pytest.raises(ValueError, match="rejected evidence limit requires a finding"):
        request.validate_review(rejected)
    token = set_review_input(request)
    try:
        result = validate_provenance_review(SimpleNamespace(deps=None), rejected)
    finally:
        reset_review_input(token)
    derived = result.findings[-1]
    assert (derived.location.source_field, derived.location.path) == (
        "candidate.evidence_uses", "/0/limit_claims/0",
    )


MEMORY_ID = "mem_host"
NOTE = "Your note says you still want to host the reading circle when your mood shifts."


def memory_candidate(reply, *, claims=(NOTE,)):
    return MuseCandidate.model_validate({
        "reply": reply,
        "evidence_uses": [{"source_kind": "memory", "evidence_id": MEMORY_ID,
                           "supported_claims": list(claims)}] if claims else [],
        "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
    })


def test_unmapped_report_of_the_stored_note_is_rejected():
    extra = "Your mood may change, but your note records continued ownership of it."
    candidate = memory_candidate(f"{NOTE} {extra} What would help?")
    error, = memory_attribution_errors(candidate.reply, candidate.evidence_uses)
    assert error["value"] == extra
    assert error["note_reference"] == "your note"


def test_reflection_that_refers_back_to_mapped_note_details_is_allowed():
    for reply in (
        f"{NOTE} Perhaps the promise can belong to the ongoing pattern of you.",
        f"{NOTE} The useful question for your notes might be what still feels like yours.",
        f"{NOTE} As you said just now, the pull is strong.",
    ):
        candidate = memory_candidate(reply)
        assert memory_attribution_errors(candidate.reply, candidate.evidence_uses) == []


def test_note_attribution_check_applies_only_when_a_memory_is_declared():
    candidate = memory_candidate("You previously said you would host.", claims=())
    assert memory_attribution_errors(candidate.reply, candidate.evidence_uses) == []


def test_claim_audit_error_names_a_stale_non_member_to_remove():
    request = task()
    stale = review(request).model_dump(mode="json")
    # A revision can drop a declaration from a claim; the prior audit entry must then go.
    stale["claim_audit"][0]["source_contributions"].append(
        {"declaration_index": 1, "claim_index": 0, "contributes": False, "source_excerpt": None},
    )
    errors = []
    request._audit_errors(ProvenanceReview.model_validate(stale), errors)

    error, = (error for error in errors if error["path"] == "claim_audit[0].source_contributions")
    assert error["remove_members"] == [[1, 0]]
    assert "add_members" not in error
