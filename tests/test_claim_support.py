"""Bind source declarations to the actual claims in a candidate response."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from pydantic_ai import ModelRetry

from src.linger.agents.muse.models import MuseCandidate


CLAIM = "The passage describes changing perceptions."


def candidate(reply=CLAIM, claims=(CLAIM,)):
    return MuseCandidate.model_validate({
        "reply": reply,
        "evidence_uses": [{
            "source_kind": "web", "evidence_id": "https://example.org/source",
            "supported_claims": claims,
        }],
        "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
    })


def test_source_declaration_carries_the_claim_it_supports():
    result = candidate()
    assert result.evidence_uses[0].supported_claims == (CLAIM,)


@pytest.mark.parametrize("claims", [(), ("   ",), (CLAIM, CLAIM)])
def test_support_mapping_requires_nonempty_distinct_claims(claims):
    with pytest.raises(ValidationError):
        candidate(claims=claims)


def test_muse_retries_a_claim_not_present_in_the_reply():
    from src.linger.agents.muse.agent import validate_muse_output

    result = candidate(reply="A different claim.")
    with pytest.raises(ModelRetry, match="supported_claims"):
        validate_muse_output(SimpleNamespace(), result)


def test_release_rejects_a_stale_mapping_even_after_review_passes():
    from src.linger.orchestration.reflection import ReleaseValidationError, _validate_release

    result = candidate().model_copy(update={"reply": "A revised response."})
    with pytest.raises(ReleaseValidationError, match="supported_claims"):
        _validate_release(result, [], None, frozenset())


def test_personal_reflection_needs_no_source_mapping():
    from src.linger.agents.muse.agent import validate_muse_output

    result = MuseCandidate.model_validate({
        "reply": "Try saying: Can I join in?", "evidence_uses": [],
        "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
    })
    assert validate_muse_output(SimpleNamespace(), result) == result


def test_provenance_receives_exact_mapping_even_without_discovery():
    from src.linger.orchestration.reflection import _provenance_input

    payload = _provenance_input(candidate(), {}, [], "What does the source say?", ())
    assert payload.candidate.response == CLAIM
    assert payload.candidate.evidence_uses[0].supported_claims == (CLAIM,)
    assert payload.candidate.evidence_uses[0].evidence_id == "https://example.org/source"
    assert payload.untrusted_tool_outcomes == ()
    assert payload.canonical_connection_evidence == ()


def test_same_claim_can_require_more_than_one_source():
    data = candidate().model_dump()
    second = dict(data["evidence_uses"][0], evidence_id="https://example.org/second")
    data["evidence_uses"] = [data["evidence_uses"][0], second]
    result = MuseCandidate.model_validate(data)
    from src.linger.agents.muse.models import validate_supported_claims
    validate_supported_claims(result.reply, result.evidence_uses)
    assert len(result.evidence_uses) == 2


def test_mapping_does_not_authorize_an_unregistered_source():
    from src.linger.orchestration.reflection import ReleaseValidationError, _validate_release

    with pytest.raises(ReleaseValidationError, match="unregistered connection evidence"):
        _validate_release(candidate(), [], None, frozenset())
