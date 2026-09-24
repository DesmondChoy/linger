"""Revision-check objections to unchanged first-draft text are reported, not graded."""

from evals.synthetic_journals.provenance_diagnostics import late_provenance_findings
from evals.synthetic_journals.transcript import AgentExchange
from src.linger.agents.provenance.models import ProvenanceInput, ProvenanceReview
from tests.test_provenance_source_audit import response_finding, task

REFLECTION = "You could consider what sharing it would mean."
CLAIM = "Your note says you fixed the error."


def text_finding(quote):
    finding = response_finding()
    finding["location"]["quote"] = quote
    return finding


def mapping_finding():
    finding = response_finding()
    finding["location"] = {"kind": "structural", "source_field": "candidate.evidence_uses",
                           "path": "/0/supported_claims/0"}
    return finding


def revise(*findings):
    return {"response_decision": "revise", "emotional_boundary_decision": "not_required",
            "capture_decision": "no_candidate", "findings": list(findings)}


def exchange(prompt: ProvenanceInput, output: dict) -> AgentExchange:
    ProvenanceReview.model_validate(output)
    return AgentExchange.model_construct(role="Provenance", stage="review", status="success",
                                         input_prompt=prompt.model_dump_json(), output=output)


def revision_input(first: ProvenanceInput, first_output: dict, response: str) -> ProvenanceInput:
    raw = first.model_dump(mode="json")
    raw["previous_response_review"] = {"candidate": raw["candidate"], "findings": first_output["findings"]}
    raw["candidate"] = {**raw["candidate"], "response": response}
    return ProvenanceInput.model_validate(raw)


def test_new_objection_to_unchanged_accepted_claim_is_late():
    first = task()
    first_output = revise(text_finding(REFLECTION))
    second = revision_input(first, first_output, first.candidate.response)
    late = late_provenance_findings([
        exchange(first, first_output),
        exchange(second, revise(mapping_finding(), text_finding(REFLECTION))),
    ])
    assert [(item.code, item.text) for item in late] == [("unresolved_evidence", CLAIM)]


def test_objection_to_revised_text_or_first_review_finding_is_not_late():
    first = task()
    first_output = revise(text_finding(CLAIM))
    revised = CLAIM + " Perhaps sharing it matters to you."
    second = revision_input(first, first_output, revised)
    late = late_provenance_findings([
        exchange(first, first_output),
        exchange(second, revise(mapping_finding(), text_finding("Perhaps sharing it matters to you."))),
    ])
    assert late == ()


def test_single_review_has_no_late_findings():
    first = task()
    assert late_provenance_findings([exchange(first, revise(text_finding(CLAIM)))]) == ()
