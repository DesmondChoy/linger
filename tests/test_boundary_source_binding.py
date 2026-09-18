"""Private chapter permission anchors must bind to their exact canonical record."""

import asyncio
import json

import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from src.linger.agents.librarian.agent import build_librarian_agent
from src.linger.agents.librarian.models import (
    BoundaryInferenceDecision,
    boundary_candidate_inventory_errors,
    boundary_memory_assessment_errors,
)
from src.linger.agents.librarian.skills import BOUNDARY_INFERENCE_NO_HISTORY
from tests.test_boundary_event_resolution import identified_stop, record, request


def payload():
    result = identified_stop().model_dump(mode="json")
    result["supporting_evidence"] = [
        {"evidence_id": "earlier-event", "source_excerpt": "Canonical event earlier-event."},
        {"evidence_id": "current-event", "source_excerpt": "Canonical event current-event."},
    ]
    return result


@pytest.mark.parametrize("index", [0, 1])
def test_quote_from_another_valid_record_does_not_bind_memory_or_current_event(index):
    output = payload()
    output["supporting_evidence"][index]["source_excerpt"] = "Canonical event other-return."
    errors = boundary_candidate_inventory_errors(output, request())
    assert any(error["path"] == f"supporting_evidence[{index}].source_excerpt" for error in errors)


def test_correct_private_anchors_and_optional_bridge_are_accepted():
    task = request()
    bridge = record("connecting-event", 7)
    task = task.model_copy(update={"full_work_candidates": (*task.full_work_candidates, bridge)})
    output = payload()
    output["supporting_evidence"].append({"evidence_id": bridge.evidence_id, "source_excerpt": bridge.text})
    output["event_resolution"]["other_evidence_ids"].append(bridge.evidence_id)
    decision = BoundaryInferenceDecision.model_validate_json(json.dumps(output))
    assert boundary_memory_assessment_errors(decision, task) == []


def test_quote_and_inventory_and_missing_memory_support_repair_together():
    invalid = payload()
    invalid["supporting_evidence"] = [invalid["supporting_evidence"][1]]
    invalid["supporting_evidence"][0]["source_excerpt"] = "A fabricated event."
    invalid["event_resolution"]["other_evidence_ids"].append("invented")
    calls = []

    def respond(messages, info):
        calls.append(messages)
        if len(calls) == 2:
            feedback = " ".join(str(p.content) for m in messages for p in m.parts if isinstance(p, RetryPromptPart))
            assert "supporting_evidence[0].source_excerpt" in feedback
            assert "earlier-event" in feedback
            assert "invented" in feedback
        tool = next(t for t in info.output_tools if t.name.endswith("BoundaryInferenceDecision"))
        return ModelResponse(parts=[ToolCallPart(tool.name, invalid if len(calls) == 1 else payload())])

    result = asyncio.run(build_librarian_agent(FunctionModel(respond)).run(
        request().model_dump_json(), **BOUNDARY_INFERENCE_NO_HISTORY.run_options(),
    ))
    assert result.output.chapter_number == 8
    assert len(calls) == 2


def test_repeated_wrong_binding_exhausts_existing_single_repair():
    calls = []
    output = payload()
    output["supporting_evidence"][0]["source_excerpt"] = "Canonical event other-return."

    def respond(messages, info):
        calls.append(messages)
        tool = next(t for t in info.output_tools if t.name.endswith("BoundaryInferenceDecision"))
        return ModelResponse(parts=[ToolCallPart(tool.name, output)])

    with pytest.raises(UnexpectedModelBehavior):
        asyncio.run(build_librarian_agent(FunctionModel(respond)).run(
            request().model_dump_json(), **BOUNDARY_INFERENCE_NO_HISTORY.run_options(),
        ))
    assert len(calls) == 2


def test_application_validation_rechecks_injected_mismatched_quote():
    decision = BoundaryInferenceDecision.model_validate_json(json.dumps(payload()))
    wrong = decision.supporting_evidence[0].model_copy(update={"source_excerpt": "Canonical event other-return."})
    decision = decision.model_copy(update={"supporting_evidence": (wrong, *decision.supporting_evidence[1:])})
    assert any(e["path"] == "supporting_evidence[0].source_excerpt" for e in boundary_memory_assessment_errors(decision, request()))


def test_old_id_only_candidate_contract_is_removed():
    output = payload()
    output.pop("supporting_evidence")
    output["supporting_evidence_ids"] = ["earlier-event", "current-event"]
    with pytest.raises(ValidationError):
        BoundaryInferenceDecision.model_validate_json(json.dumps(output))


@pytest.mark.parametrize("quote", ["", "  ", "canonical event earlier-event.", "Canonical event earlier-event!", "Canonical episode earlier-event.", r"Canonical event\nearlier-event."])
def test_binding_rejects_blank_or_altered_words_case_and_punctuation(quote):
    output = payload()
    output["supporting_evidence"][0]["source_excerpt"] = quote
    assert any(e["path"] == "supporting_evidence[0].source_excerpt" for e in boundary_candidate_inventory_errors(output, request()))


def test_repeated_permission_anchor_is_rejected_before_grant():
    output = payload()
    output["supporting_evidence"].append(output["supporting_evidence"][0])
    assert any(e["path"] == "supporting_evidence[2].evidence_id" for e in boundary_candidate_inventory_errors(output, request()))
    with pytest.raises(ValidationError, match="unique"):
        BoundaryInferenceDecision.model_validate_json(json.dumps(output))


@pytest.mark.parametrize("wrong_quote", [False, True])
def test_application_grants_only_bound_anchors_and_handoff_keeps_quotes_private(wrong_quote):
    from unittest.mock import AsyncMock, patch

    from src.linger.agents.librarian.models import BookRequestPlan
    from src.linger.contracts.librarian import BoundaryCandidate, BoundaryUncertain
    from src.linger.orchestration.boundary import infer_spoiler_boundary
    from tests.boundary_fixtures import event_resolution, quoted_support, identify_fixture_event
    from tests.test_boundary_inference import FakeLibrarian, VERSION_ID, WORK_ID, memory

    librarian = FakeLibrarian()
    stored = memory("prior", "I read Alice and the Caterpillar.")
    line = "I finished the Caterpillar encounter."

    async def judge(current_line, memories, evidence, prior_statements):
        identity = librarian.chapter_five.evidence_id
        decision = BoundaryInferenceDecision(
            memory_assessments=({"memory_id": stored.memory_id, "status": "grounded_prior_knowledge",
                                 "evidence_ids": (identity,), "reason": "The remembered event is in this passage."},),
            outcome="candidate", work_id=WORK_ID, book_version_id=VERSION_ID,
            chapter_number=5, confidence=.99, authorization_basis="memory_supported",
            supporting_memory_ids=(stored.memory_id,),
            supporting_evidence=quoted_support(evidence, (identity,)),
            event_resolution=event_resolution(current_line, evidence, (identity,)),
        )
        if wrong_quote:
            anchor = decision.supporting_evidence[0].model_copy(
                update={"source_excerpt": librarian.chapter_eight.excerpt}
            )
            return decision.model_copy(update={"supporting_evidence": (anchor,)})
        return decision

    with patch("src.linger.orchestration.evidence_strength.plan_book_request",
               AsyncMock(return_value=BookRequestPlan(parts=()))):
        result = asyncio.run(infer_spoiler_boundary(
            line, work_id=WORK_ID, book_version_id=VERSION_ID,
            memories=(stored,), librarian=librarian, judge=judge,
            event_identifier=identify_fixture_event(5),
        ))
    assert isinstance(result, BoundaryUncertain if wrong_quote else BoundaryCandidate)
    assert librarian.chapter_five.excerpt not in result.model_dump_json()
    assert librarian.chapter_eight.excerpt not in result.model_dump_json()
    if not wrong_quote:
        assert result.max_chapter_inclusive == 5


@pytest.mark.parametrize("canonical,excerpt", [
    ("Before. Canonical event\nearlier-event. After.", "Canonical event earlier-event."),
    ("Canonical event earlier-event.", "Canonical\t event\r\nearlier-event."),
])
def test_private_source_binding_accepts_whitespace_only_wrapping(canonical, excerpt):
    task = request()
    records = tuple(item.model_copy(update={"text": canonical}) if item.evidence_id == "earlier-event" else item for item in task.full_work_candidates)
    task = task.model_copy(update={"full_work_candidates": records})
    output = payload()
    output["supporting_evidence"][0]["source_excerpt"] = excerpt
    assert boundary_candidate_inventory_errors(output, task) == []
    decision = BoundaryInferenceDecision.model_validate(output)
    assert boundary_memory_assessment_errors(decision, task) == []


def test_old_private_exact_quote_field_is_removed():
    output = payload()
    anchor = output["supporting_evidence"][0]
    anchor["exact_quote"] = anchor.pop("source_excerpt")
    with pytest.raises(ValidationError):
        BoundaryInferenceDecision.model_validate(output)


@pytest.mark.parametrize("excerpt", ["He was in its element.", "He was in his element."])
def test_private_binding_preserves_original_pronouns_and_markup(excerpt):
    task = request()
    task = task.model_copy(update={"full_work_candidates": tuple(
        item.model_copy(update={"text": "He was in _his_ element."})
        if item.evidence_id == "earlier-event" else item for item in task.full_work_candidates
    )})
    output = payload()
    output["supporting_evidence"][0]["source_excerpt"] = excerpt
    assert any(e["path"] == "supporting_evidence[0].source_excerpt"
               for e in boundary_candidate_inventory_errors(output, task))


def test_private_binding_does_not_accept_pronoun_substitution():
    task = request()
    task = task.model_copy(update={"full_work_candidates": tuple(
        item.model_copy(update={"text": "He was in his element."})
        if item.evidence_id == "earlier-event" else item for item in task.full_work_candidates
    )})
    output = payload()
    output["supporting_evidence"][0]["source_excerpt"] = "He was in its element."
    errors = boundary_candidate_inventory_errors(output, task)
    assert any(e["path"] == "supporting_evidence[0].source_excerpt" for e in errors)
    assert "pronoun" in errors[0]["error"]


def test_private_binding_rejects_unknown_source_id_even_with_real_words():
    output = payload()
    output["supporting_evidence"][0]["evidence_id"] = "unknown-record"
    assert any(e["path"] == "supporting_evidence[0].evidence_id"
               for e in boundary_candidate_inventory_errors(output, request()))
