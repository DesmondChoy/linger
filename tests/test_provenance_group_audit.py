"""Collective entailment stays distinct from each source's concrete contribution."""

import pytest
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from evals.provenance.claim_mapping import load_cases
from src.linger.agents.provenance.agent import build_provenance_agent
from src.linger.agents.provenance.models import (
    ProvenanceInput, ProvenanceReview, SourceContributionAudit, build_claim_support_groups,
)
from src.linger.agents.provenance.skills import CANDIDATE_REVIEW

EARLIER = "I can’t explain _myself_, I’m afraid, sir"
LATER = "but it all\ncame different"


def request(index=3):
    return load_cases().cases[index].review_input


def checked(task, *, supported=True, contributes=None, excerpts=None, finding=False):
    members = task.claim_support_groups[0].declarations
    contributes = contributes if contributes is not None else [True] * len(members)
    excerpts = excerpts if excerpts is not None else [EARLIER, LATER][:len(members)]
    return ProvenanceReview.model_validate({
        "response_decision": "revise" if finding else "pass",
        "capture_decision": "no_candidate", "emotional_boundary_decision": "not_required",
        "findings": [{
            "code": "unsupported_claim", "applies_to": "response",
            "location": {"kind": "text_span", "source_field": "candidate.response", "path": "",
                         "quote": task.candidate.response},
            "explanation": "The declared group is missing the verse contribution.",
        }] if finding else [],
        "claim_audit": [{
            "group_index": 0, "supported": supported,
            "support_summary": ("The declared records supply the identity and verse contributions."
                                if supported else "The declared records do not supply the verse contribution."),
            "source_contributions": [
                {"declaration_index": m.declaration_index, "claim_index": m.claim_index,
                 "contributes": c, "source_excerpt": excerpt if c else None}
                for m, c, excerpt in zip(members, contributes, excerpts, strict=True)
            ],
        }],
    })


def test_valid_joint_group_accepts_distinct_source_contributions():
    task = request()
    task.validate_review(checked(task))
    geometry = build_claim_support_groups(task.candidate.evidence_uses, task.candidate.response)
    without_sources = {"declarations": {"__all__": {"canonical_source_text"}}}
    assert [g.model_dump(exclude=without_sources) for g in task.claim_support_groups] == [
        g.model_dump(exclude=without_sources) for g in geometry
    ]
    assert task.claim_support_groups[0].group_index == 0


def test_valid_partial_contribution_can_have_collectively_unsupported_claim():
    task = request(2)
    with pytest.raises(ValueError, match="unsupported declared claim requires a finding"):
        task.validate_review(checked(task, supported=False))
    task.validate_review(checked(task, supported=False, finding=True))


def test_wrong_source_can_be_both_noncontributing_and_collectively_unsupported():
    task = request(0)
    task.validate_review(checked(task, supported=False, contributes=[False], finding=True))


def test_noncontributing_member_still_needs_finding_if_group_is_supported():
    task = request()
    with pytest.raises(ValueError, match="noncontributing source requires a finding"):
        task.validate_review(checked(task, contributes=[False, True]))


def test_private_excerpt_cannot_borrow_available_undeclared_source():
    task = request(0)
    with pytest.raises(ValueError, match="this named canonical source") as failure:
        task.validate_review(checked(task, excerpts=[LATER]))
    error = failure.value.errors[0]
    assert error["current_target"] == task.canonical_book_evidence[0].text
    assert error["source_declaration"]["evidence_id"].endswith("ln0960-1016")


@pytest.mark.parametrize("excerpt", ["but it all came different", "but\tit\nall   came different"])
def test_private_excerpt_allows_only_whitespace_variation(excerpt):
    task = request(1)
    task.validate_review(checked(task, excerpts=[excerpt]))
    raw = task.model_dump(mode="json")
    raw["candidate"]["evidence_uses"][0]["exact_quote"] = excerpt
    assert not ProvenanceInput.model_validate(raw).quote_checks[0].quote_in_source


@pytest.mark.parametrize("excerpt", ["But it all came different", "but it all came differently", "but it all, came different", "but it _all_ came different"])
def test_private_excerpt_preserves_case_words_punctuation_and_markup(excerpt):
    with pytest.raises(ValueError, match="this named canonical source"):
        request(1).validate_review(checked(request(1), excerpts=[excerpt]))


@pytest.mark.parametrize("change", ["unknown_id", "wrong_kind"])
def test_positive_contribution_requires_named_source_identity(change):
    task = request(1)
    raw = task.model_dump(mode="json")
    use = raw["candidate"]["evidence_uses"][0]
    if change == "unknown_id":
        use["evidence_id"] = "not-canonical"
    else:
        use["source_kind"] = "memory"
        use.pop("source_location")
    task = ProvenanceInput.model_validate(raw)
    with pytest.raises(ValueError, match="this named canonical source"):
        task.validate_review(checked(task, excerpts=[LATER]))


@pytest.mark.parametrize("excerpts", [None, "", " \n\t"])
def test_positive_contribution_cannot_omit_a_nonblank_excerpt(excerpts):
    with pytest.raises(ValueError, match="nonblank source_excerpt"):
        SourceContributionAudit(declaration_index=0, claim_index=0, contributes=True, source_excerpt=excerpts)


def test_negative_contribution_cannot_smuggle_unchecked_excerpt():
    with pytest.raises(ValueError, match="source_excerpt=null"):
        SourceContributionAudit(declaration_index=0, claim_index=0, contributes=False, source_excerpt=LATER)


@pytest.mark.parametrize("member_indices", [[0], [0, 0], [0, 3]])
def test_group_audit_requires_exact_current_member_inventory(member_indices):
    task = request()
    raw = checked(task).model_dump(mode="json")
    raw["claim_audit"][0]["source_contributions"] = [
        {"declaration_index": index, "claim_index": 0, "contributes": True, "source_excerpt": EARLIER}
        for index in member_indices
    ]
    with pytest.raises(ValueError, match="every current group member exactly once"):
        task.validate_review(ProvenanceReview.model_validate(raw))


def test_old_flat_claim_audit_has_no_compatibility_alias():
    raw = checked(request()).model_dump(mode="json")
    raw["claim_audit"] = [{"declaration_index": 0, "claim_index": 0, "supported": True}]
    with pytest.raises(ValueError):
        ProvenanceReview.model_validate(raw)


@pytest.mark.parametrize("summary", [None, "", " \n\t", "x" * 801])
def test_collective_support_requires_a_bounded_nonblank_summary(summary):
    raw = checked(request()).model_dump(mode="json")
    if summary is None:
        del raw["claim_audit"][0]["support_summary"]
    else:
        raw["claim_audit"][0]["support_summary"] = summary
    with pytest.raises(ValueError) as failure:
        ProvenanceReview.model_validate(raw)
    assert failure.value.errors()[0]["loc"] == ("claim_audit", 0, "support_summary")


@pytest.mark.parametrize("case_index,supported", [(2, False), (3, True)])
def test_actual_agent_exposes_audits_before_verdict_and_repairs_missing_summary(case_index, supported):
    task = request(case_index)
    valid = checked(task, supported=supported, finding=not supported)
    calls = 0

    def respond(messages, info):
        nonlocal calls
        calls += 1
        schema = info.output_tools[0].parameters_json_schema
        properties = list(schema["properties"])
        assert properties == [
            "coverage_audit", "quotation_audit", "claim_audit", "finding_resolutions",
            "findings", "emotional_boundary_decision", "capture_decision", "response_decision",
        ]
        group_schema = schema["$defs"]["ClaimSupportAudit"]
        assert list(group_schema["properties"]) == [
            "group_index", "source_contributions", "support_summary", "supported",
        ]
        assert "support_summary" in group_schema["required"]
        prompts = [part.content for message in messages for part in message.parts
                   if isinstance(part, UserPromptPart)]
        assert prompts == [task.model_dump_json()]
        output = valid.model_dump(mode="json")
        if calls == 1:
            del output["claim_audit"][0]["support_summary"]
        else:
            retries = [part for message in messages for part in message.parts
                       if isinstance(part, RetryPromptPart)]
            assert len(retries) == 1
            assert "support_summary" in str(retries[0].content)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    result = build_provenance_agent(FunctionModel(respond)).run_sync(
        task.model_dump_json(), **CANDIDATE_REVIEW.run_options(),
    )
    assert calls == 2
    assert result.output == valid
    assert result.output.response_decision == ("pass" if supported else "revise")
    task.validate_review(result.output)


SMOKE_S = (
    "Yet the comparison has an important limit: Gordon describes a supportive space for perplexity, "
    "while Alice experiences the Caterpillar’s questioning as disorienting and adversarial."
)
SMOKE_T = "Confusion may become productive, but questioning alone does not make it educational."


def overlap_request(response, first_claim, second_claim):
    raw = request().model_dump(mode="json")
    raw["candidate"]["response"] = response
    for use, claim in zip(raw["candidate"]["evidence_uses"], (first_claim, second_claim), strict=True):
        use["supported_claims"] = [claim]
        use["exact_quote"] = None
    return ProvenanceInput.model_validate(raw)


def coverage_rows(member):
    return [(c.occurrence_index, c.start, c.end, c.text) for c in member.coverage]


def test_smoke_nested_claims_keep_whole_groups_and_scope_each_source():
    full = SMOKE_S + " " + SMOKE_T
    groups = overlap_request(full, full, SMOKE_S).claim_support_groups
    assert [g.claim for g in groups] == [full, SMOKE_S]
    assert [[m.declaration_index for m in g.declarations] for g in groups] == [[0, 1], [0, 1]]
    assert [m.direct for m in groups[0].declarations] == [True, False]
    assert [m.direct for m in groups[1].declarations] == [False, True]
    assert coverage_rows(groups[0].declarations[1]) == [(0, 0, len(SMOKE_S), SMOKE_S)]
    assert all(SMOKE_T not in c.text for g in groups for m in g.declarations
               if m.declaration_index == 1 for c in m.coverage)


def test_partial_overlap_projects_only_actual_shared_response_positions():
    groups = overlap_request("First shared last", "First shared", "shared last").claim_support_groups
    assert coverage_rows(groups[0].declarations[1]) == [(0, 6, 12, "shared")]
    assert coverage_rows(groups[1].declarations[0]) == [(0, 6, 12, "shared")]
    assert [g.claim for g in groups] == ["First shared", "shared last"]


def test_repeated_claim_does_not_borrow_coverage_from_another_occurrence():
    groups = overlap_request("Shared tail. Shared", "Shared tail.", "Shared").claim_support_groups
    short = groups[1]
    assert [(o.start, o.end) for o in short.occurrences] == [(0, 6), (13, 19)]
    assert coverage_rows(short.declarations[0]) == [(0, 0, 6, "Shared")]
    assert coverage_rows(short.declarations[1]) == [(0, 0, 6, "Shared"), (1, 13, 19, "Shared")]


def test_forged_overlap_coverage_is_discarded_on_roundtrip():
    task = overlap_request("First shared last", "First shared", "shared last")
    raw = task.model_dump(mode="json")
    raw["claim_support_groups"] = [{"claim": "forged", "declarations": [{"coverage": "all"}]}]
    assert ProvenanceInput.model_validate(raw).claim_support_groups == task.claim_support_groups


def overlap_review(task, *, false_members=(), unsupported_groups=(), findings=()):
    """Mechanical review fixture; copied proof does not assert semantic entailment."""
    from tests.provenance_fixtures import review_with_audits

    review = review_with_audits(task, {
        "response_decision": "revise" if findings else "pass",
        "capture_decision": "no_candidate", "emotional_boundary_decision": "not_required",
        "findings": list(findings),
    }).model_dump(mode="json")
    for audit in review["claim_audit"]:
        if audit["group_index"] in unsupported_groups:
            audit["supported"] = False
        for member in audit["source_contributions"]:
            if (audit["group_index"], member["declaration_index"]) in false_members:
                member.update(contributes=False, source_excerpt=None)
    return ProvenanceReview.model_validate(review)


def test_overlap_only_noncontribution_does_not_invent_a_wrong_mapping():
    task = overlap_request("First shared last", "First shared", "shared last")
    # Each source may support its own distinct part while adding nothing in the intersection.
    task.validate_review(overlap_review(task, false_members={(0, 1), (1, 0)}))
    with pytest.raises(ValueError, match="noncontributing source requires a finding"):
        task.validate_review(overlap_review(task, false_members={(0, 0)}))


def test_unsupported_tail_cannot_use_finding_on_overlap_only_shorter_mapping():
    task = overlap_request(SMOKE_S + " " + SMOKE_T, SMOKE_S + " " + SMOKE_T, SMOKE_S)
    finding = {
        "code": "unsupported_claim", "applies_to": "response",
        "location": {"kind": "structural", "source_field": "candidate.evidence_uses",
                     "path": "/1/supported_claims/0"},
        "explanation": "The conclusion T lacks declared support.",
    }
    with pytest.raises(ValueError, match="unsupported declared claim requires a finding"):
        task.validate_review(overlap_review(task, unsupported_groups={0}, findings=[finding]))
    finding["location"]["path"] = "/0/supported_claims/0"
    task.validate_review(overlap_review(task, unsupported_groups={0}, findings=[finding]))


def test_repeated_overlapping_occurrences_merge_only_within_each_group_occurrence():
    groups = overlap_request("aaaa", "aaaa", "aaa").claim_support_groups
    assert coverage_rows(groups[0].declarations[1]) == [(0, 0, 4, "aaaa")]
    assert coverage_rows(groups[1].declarations[0]) == [(0, 0, 3, "aaa"), (1, 1, 4, "aaa")]


def test_review_must_audit_overlap_members_not_only_original_exact_text_members():
    task = overlap_request(SMOKE_S + " " + SMOKE_T, SMOKE_S + " " + SMOKE_T, SMOKE_S)
    raw = overlap_review(task).model_dump(mode="json")
    for group, audit in zip(task.claim_support_groups, raw["claim_audit"], strict=True):
        direct = {(m.declaration_index, m.claim_index) for m in group.declarations if m.direct}
        audit["source_contributions"] = [item for item in audit["source_contributions"]
                                          if (item["declaration_index"], item["claim_index"]) in direct]
    with pytest.raises(ValueError, match="every current group member exactly once"):
        task.validate_review(ProvenanceReview.model_validate(raw))
