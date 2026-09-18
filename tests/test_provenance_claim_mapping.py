"""Offline integrity and runner checks; these do not measure model judgment."""

import asyncio
import json

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from evals.provenance import claim_mapping
from evals.provenance._fixtures import _chapter
from src.linger.agents.provenance.agent import provenance_agent
from src.linger.agents.provenance.models import ProvenanceReview, RiskFinding, TextSpanLocation
from provenance_fixtures import review_with_audits


def review(case, decision):
    findings = () if decision == "pass" else (RiskFinding(
        code="unsupported_claim",
        applies_to="response",
        location=TextSpanLocation(
            kind="text_span", source_field="candidate.response", path="",
            quote=case.review_input.candidate.response,
        ),
        explanation="The declared passage does not support the claim.",
    ),)
    output = review_with_audits(case.review_input, ProvenanceReview(
        response_decision=decision, emotional_boundary_decision="not_required",
        capture_decision="no_candidate", findings=findings,
    ))
    return output.model_copy(update={
        "claim_audit": tuple(audit.model_copy(update={"supported": decision == "pass"})
                             for audit in output.claim_audit),
    })


def test_pair_changes_only_the_declared_passage():
    wrong, correct = claim_mapping.load_cases().cases[:2]
    assert wrong.case_id != correct.case_id
    assert wrong.expected_response_decision == "revise"
    assert wrong.expected_response_codes == ("unsupported_claim",)
    assert correct.expected_response_decision == "pass"
    assert correct.expected_response_codes == ()
    left = wrong.review_input.model_dump(mode="json", exclude={"claim_support_groups"})
    right = correct.review_input.model_dump(mode="json", exclude={"claim_support_groups"})
    left_use = left["candidate"]["evidence_uses"][0]
    right_use = right["candidate"]["evidence_uses"][0]
    assert left_use["evidence_id"] == "pg11-v01b38ea4-ch05-ln0960-1016"
    assert right_use["evidence_id"] == "pg11-v01b38ea4-ch05-ln1004-1056"
    for field in ("evidence_id", "source_location"):
        assert left_use[field] != right_use[field]
        left_use[field] = right_use[field]
    assert left == right
    for case in (wrong, correct):
        use = case.review_input.candidate.evidence_uses[0]
        record = next(r for r in case.review_input.canonical_book_evidence
                      if r.evidence_id == use.evidence_id)
        assert use.source_location == record.location
        assert use.supported_claims == (case.review_input.candidate.response,)
        metadata, body = _chapter(record.chapter_number)
        assert record.text in body
        assert record.source_sha256 == metadata.source_sha256


def test_joint_pair_changes_only_the_missing_contribution_declaration():
    missing, complete = claim_mapping.load_cases().cases[2:]
    assert missing.expected_response_decision == "revise"
    assert complete.expected_response_decision == "pass"
    left = missing.review_input.model_dump(mode="json", exclude={"claim_support_groups"})
    right = complete.review_input.model_dump(mode="json", exclude={"claim_support_groups"})
    assert len(left["candidate"]["evidence_uses"]) == 1
    assert len(right["candidate"]["evidence_uses"]) == 2
    left["candidate"]["evidence_uses"].append(right["candidate"]["evidence_uses"][1])
    assert left == right
    first, second = complete.review_input.canonical_book_evidence
    assert "different sizes in a day" in first.text
    assert "How doth the little busy bee" not in first.text
    assert "How doth the little busy bee" in second.text
    for record, use in zip(complete.review_input.canonical_book_evidence,
                           complete.review_input.candidate.evidence_uses, strict=True):
        assert use.evidence_id == record.evidence_id
        assert use.supported_claims == (complete.review_input.candidate.response,)
        metadata, body = _chapter(record.chapter_number)
        assert record.text in body
        assert record.source_sha256 == metadata.source_sha256


@pytest.mark.parametrize("decision,passed_index", [("pass", 1), ("revise", 0)])
def test_blanket_decisions_fail_the_pair(decision, passed_index):
    async def gate(case):
        return review(case, decision)
    report = asyncio.run(claim_mapping.run_evaluation(gate=gate))
    assert not report.summary.targets_pass
    assert report.summary.cases_passed == 2
    assert report.cases[passed_index].grade.passed
    assert report.cases[1 - passed_index].grade.failure_code == "decision_mismatch"


def test_production_adapter_receives_inputs_without_expected_answers():
    cases = claim_mapping.load_cases().cases
    received = []

    def respond(messages, info):
        prompts = [part.content for message in messages for part in message.parts
                   if isinstance(part, UserPromptPart)]
        assert len(prompts) == 1
        payload = json.loads(prompts[0])
        case = cases[len(received)]
        assert payload == case.review_input.model_dump(mode="json")
        received.append(payload)
        output = review(case, case.expected_response_decision)
        return ModelResponse(parts=[ToolCallPart(
            info.output_tools[0].name, output.model_dump(mode="json"),
        )])

    with provenance_agent.override(model=FunctionModel(respond)):
        report = asyncio.run(claim_mapping.run_evaluation(model_name="offline-function"))
    assert len(received) == 4
    assert report.summary.targets_pass
    assert report.summary.cases_passed == 4
    assert report.model == "offline-function"
    assert len(report.case_set_digest) == 64


def test_provider_error_is_reported_without_sensitive_text_and_other_case_runs():
    received = []

    async def gate(case):
        received.append(case.case_id)
        if len(received) == 1:
            raise RuntimeError("private provider detail")
        return review(case, "pass")

    report = asyncio.run(claim_mapping.run_evaluation(gate=gate))
    assert len(received) == 4
    assert not report.summary.targets_pass
    assert report.cases[0].grade.failure_code == "gate_error"
    assert report.cases[0].error_type == "RuntimeError"
    serialized = report.model_dump_json()
    assert "private provider detail" not in serialized
    assert claim_mapping.load_cases().cases[0].review_input.candidate.response not in serialized


@pytest.mark.parametrize("all_correct", [True, False])
def test_cli_writes_report_and_fails_when_bug_is_reproduced(tmp_path, monkeypatch, all_correct):
    async def gate(case):
        return review(case, case.expected_response_decision if all_correct else "pass")

    async def build_report():
        return await claim_mapping.run_evaluation(gate=gate)

    destination = tmp_path / "reports" / "result.json"
    monkeypatch.setattr("sys.argv", ["claim_mapping", "--report", str(destination)])
    if all_correct:
        claim_mapping.run_report_command(build_report, claim_mapping.DEFAULT_REPORT)
    else:
        with pytest.raises(SystemExit) as error:
            claim_mapping.run_report_command(build_report, claim_mapping.DEFAULT_REPORT)
        assert error.value.code == 1
    saved = claim_mapping.ClaimMappingReport.model_validate_json(destination.read_bytes())
    assert saved.summary.targets_pass is all_correct
    assert saved.summary.cases_total == 4
