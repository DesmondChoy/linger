"""Contradictory support reviews request repair, without overriding semantic judgment."""

import pytest
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from evals.provenance.claim_mapping import load_cases
from src.linger.agents.provenance.agent import build_provenance_agent
from src.linger.agents.provenance.models import ProvenanceInput, ProvenanceReview, ReviewValidationError
from src.linger.agents.provenance.skills import CANDIDATE_REVIEW
from tests.provenance_fixtures import review_with_audits


def joint_request():
    return load_cases().cases[3].review_input


def review(task, location, *, code="unsupported_claim", supported=True, contributes=True):
    output = review_with_audits(task, {
        "response_decision": "revise", "capture_decision": "no_candidate",
        "emotional_boundary_decision": "not_required",
        "findings": [{"code": code, "applies_to": "response", "location": location,
                      "explanation": "The first record does not independently establish the complete claim."}],
    }).model_dump(mode="json")
    audit = output["claim_audit"][0]
    audit["supported"] = supported
    audit["source_contributions"][0].update(
        contributes=contributes,
        source_excerpt="I can’t explain _myself_, I’m afraid, sir" if contributes else None,
    )
    audit["source_contributions"][1]["source_excerpt"] = "but it all\ncame different"
    return ProvenanceReview.model_validate(output)


def leaf_location(task, *, kind="text_span", quote=None, path="/0/supported_claims/0"):
    location = {"kind": kind, "source_field": "candidate.evidence_uses", "path": path}
    if kind == "text_span":
        location["quote"] = task.candidate.response if quote is None else quote
    return location


@pytest.mark.parametrize("target", ["text_leaf", "structural_leaf", "response"])
@pytest.mark.parametrize("code", ["unsupported_claim", "misattribution"])
def test_complete_supported_claim_cannot_also_have_exact_unsupported_finding(target, code):
    task = joint_request()
    location = leaf_location(task, kind="structural" if target == "structural_leaf" else "text_span")
    if target == "response":
        location.update(source_field="candidate.response", path="")
    with pytest.raises(ReviewValidationError, match="contradicts the supported claim audit") as failure:
        task.validate_review(review(task, location, code=code))
    error = failure.value.errors[0]
    assert error["path"] == "findings[0]"
    assert error["current_target"]["claim"] == task.candidate.response
    assert "Reassess" in error["error"]


@pytest.mark.parametrize("code", ["unresolved_evidence", "uncited_web_claim"])
def test_complete_support_does_not_cancel_independent_risks(code):
    task = joint_request()
    task.validate_review(review(task, leaf_location(task), code=code))


@pytest.mark.parametrize("target", ["partial_leaf", "partial_response", "declaration", "claim_list"])
@pytest.mark.parametrize("code", ["unsupported_claim", "misattribution"])
def test_broader_or_partial_findings_are_not_assumed_to_deny_whole_claim(target, code):
    task = joint_request()
    location = leaf_location(task, quote="Alice struggles to explain who she is")
    if target == "partial_response":
        location.update(source_field="candidate.response", path="")
    elif target in {"declaration", "claim_list"}:
        location = leaf_location(task, kind="structural", path="/0" if target == "declaration" else "/0/supported_claims")
    task.validate_review(review(task, location, code=code))


@pytest.mark.parametrize("code", ["unsupported_claim", "misattribution"])
def test_supported_group_can_still_reject_noncontributing_direct_mapping(code):
    task = joint_request()
    task.validate_review(review(task, leaf_location(task), contributes=False, code=code))


@pytest.mark.parametrize("code", ["unsupported_claim", "misattribution"])
def test_unsupported_group_keeps_its_finding_despite_positive_contributions(code):
    task = joint_request()
    task.validate_review(review(task, leaf_location(task), supported=False, code=code))


@pytest.mark.parametrize("field", ["exact_quote", "evidence_id", "source_location"])
def test_supported_claim_keeps_independent_quote_or_source_finding(field):
    raw = joint_request().model_dump(mode="json")
    raw["candidate"]["evidence_uses"][0]["exact_quote"] = "Invented quoted words."
    task = ProvenanceInput.model_validate(raw)
    assert not task.quote_checks[0].quote_in_source
    assert not task.quote_checks[0].quote_in_response
    location = leaf_location(task, kind="structural", path=f"/0/{field}")
    task.validate_review(review(task, location, code="misattribution"))


def test_session_quote_attribution_can_be_flagged_separately_from_claim_support():
    raw = joint_request().model_dump(mode="json")
    quote = "I can’t explain _myself_, I’m afraid, sir"
    raw["canonical_session_lines"] = [quote]
    raw["candidate"]["evidence_uses"][0] = {
        "source_kind": "session_line", "quote": quote,
        "supported_claims": [raw["candidate"]["response"]],
    }
    task = ProvenanceInput.model_validate(raw)
    task.validate_review(review(task, leaf_location(task, kind="structural", path="/0/quote"), code="misattribution"))


def test_unrelated_response_finding_does_not_conflict_with_supported_group():
    raw = joint_request().model_dump(mode="json")
    raw["candidate"]["response"] += " An additional unsupported claim."
    task = ProvenanceInput.model_validate(raw)
    location = {"kind": "text_span", "source_field": "candidate.response", "path": "",
                "quote": "An additional unsupported claim."}
    task.validate_review(review(task, location))


def test_noncontributing_overlap_member_does_not_trigger_consistency_rule():
    raw = joint_request().model_dump(mode="json")
    raw["candidate"]["evidence_uses"][1]["supported_claims"] = [
        "later reports that a familiar verse came out differently."
    ]
    task = ProvenanceInput.model_validate(raw)
    assert not task.claim_support_groups[0].declarations[1].direct
    output = review(task, leaf_location(task)).model_dump(mode="json")
    output["claim_audit"][0]["source_contributions"][1].update(contributes=False, source_excerpt=None)
    task.validate_review(ProvenanceReview.model_validate(output))


@pytest.mark.parametrize("repair", ["withdraw_finding", "correct_audit", "locate_quote_defect"])
@pytest.mark.parametrize("code", ["unsupported_claim", "misattribution"])
def test_agent_repairs_consistency_without_automatic_approval(repair, code):
    task = joint_request()
    if repair == "locate_quote_defect":
        raw = task.model_dump(mode="json")
        raw["candidate"]["evidence_uses"][0]["exact_quote"] = "Invented quoted words."
        task = ProvenanceInput.model_validate(raw)
    inconsistent = review(task, leaf_location(task), code=code)
    corrected = inconsistent.model_dump(mode="json")
    if repair == "withdraw_finding":
        corrected.update(findings=[], response_decision="pass")
    elif repair == "correct_audit":
        corrected["claim_audit"][0]["supported"] = False
    else:
        corrected["findings"][0].update(
            code="misattribution",
            location=leaf_location(task, kind="structural", path="/0/exact_quote"),
            explanation="The declared quotation occurs in neither the named source nor the reply.",
        )
    calls = 0

    def respond(messages, info):
        nonlocal calls
        calls += 1
        if calls > 1:
            retry = [part for message in messages for part in message.parts if isinstance(part, RetryPromptPart)]
            assert len(retry) == 1
            assert "contradicts the supported claim audit" in str(retry[0].content)
        return ModelResponse(parts=[ToolCallPart(
            info.output_tools[0].name, inconsistent.model_dump(mode="json") if calls == 1 else corrected,
        )])

    result = build_provenance_agent(FunctionModel(respond)).run_sync(
        task.model_dump_json(), **CANDIDATE_REVIEW.run_options(),
    )
    assert calls == 2
    assert result.output == ProvenanceReview.model_validate(corrected)
