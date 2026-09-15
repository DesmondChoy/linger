"""A revision cannot lose the findings that caused it."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from src.linger.agents.provenance.models import ProvenanceInput, ProvenanceReview
from src.linger.orchestration.reflection import _provenance_input
from tests.test_reflection import candidate, reflection_reply, result, review


def resolution(index=0, status="resolved"):
    return {
        "finding_index": index,
        "status": status,
        "explanation": "The revised reply removes the unsupported factual attribution.",
    }


def test_revision_review_receives_original_candidate_and_response_findings():
    first_review = review("revise", capture="reject_capture", finding="Map the full factual claim.")
    muse = AsyncMock()
    muse.run.side_effect = [result("Original factual claim."), result("Try a reflective question.")]
    provenance = AsyncMock()
    second = review("pass").model_dump()
    second["finding_resolutions"] = [resolution()]
    provenance.run.side_effect = [result(first_review), result(second)]

    released = asyncio.run(reflection_reply("Help me reflect", [], muse=muse, provenance=provenance))

    first_input = json.loads(provenance.run.await_args_list[0].args[0])
    second_input = json.loads(provenance.run.await_args_list[1].args[0])
    previous = second_input["previous_response_review"]
    assert previous["candidate"] == first_input["candidate"]
    assert previous["findings"] == [f.model_dump(mode="json") for f in first_review.response_findings]
    assert first_input["previous_response_review"] is None
    assert released.reply == "Try a reflective question."
    assert released.provenance_verdicts == ("revise", "pass")


def test_pass_without_accounting_for_prior_findings_cannot_release_revision():
    muse = AsyncMock()
    muse.run.side_effect = [result("Original claim."), result("Reworded claim.")]
    provenance = AsyncMock()
    provenance.run.side_effect = [result(review("revise")), result(review("pass"))]

    released = asyncio.run(reflection_reply("Help me reflect", [], muse=muse, provenance=provenance))

    assert released.release_source == "application_safe_decline"
    assert released.failure_stage == "provenance_review"
    assert released.failure_type == "validation"


def revision_input():
    payload = _provenance_input(candidate("Reworded claim."), {}, [], "Help me reflect", ())
    return ProvenanceInput.model_validate({
        **payload.model_dump(),
        "previous_response_review": {
            "candidate": {"response": "Original claim.", "evidence_uses": [], "memory": candidate("Original claim.").memory.model_dump()},
            "findings": [f.model_dump() for f in review("revise").response_findings],
        },
    })


@pytest.mark.parametrize("resolutions", [[], [resolution(1)], [resolution(), resolution()]])
def test_revision_requires_each_prior_finding_exactly_once(resolutions):
    payload = revision_input()
    second = ProvenanceReview.model_validate({**review("pass").model_dump(), "finding_resolutions": resolutions})
    with pytest.raises(ValueError, match="finding_resolutions"):
        payload.validate_review(second)


def test_unresolved_finding_cannot_be_marked_passed():
    payload = revision_input()
    with pytest.raises(ValueError, match="unresolved"):
        second = ProvenanceReview.model_validate({
            **review("pass").model_dump(), "finding_resolutions": [resolution(status="unresolved")],
        })
        payload.validate_review(second)


def test_resolution_does_not_hide_a_new_finding():
    payload = revision_input()
    second = ProvenanceReview.model_validate({
        **review("revise", finding="A new factual claim has no supporting evidence.").model_dump(),
        "finding_resolutions": [resolution()],
    })
    payload.validate_review(second)
    assert second.response_decision == "revise"


def test_initial_review_cannot_resolve_nonexistent_findings():
    payload = _provenance_input(candidate("A reply."), {}, [], "Help me reflect", ())
    second = ProvenanceReview.model_validate({**review("pass").model_dump(), "finding_resolutions": [resolution()]})
    with pytest.raises(ValueError, match="finding_resolutions"):
        payload.validate_review(second)


def test_prior_capture_findings_cannot_become_response_repair_obligations():
    payload = revision_input().model_dump()
    payload["previous_response_review"]["findings"] = [
        f.model_dump() for f in review("pass", capture="reject_capture").capture_findings
    ]
    with pytest.raises(ValidationError, match="response"):
        ProvenanceInput.model_validate(payload)
