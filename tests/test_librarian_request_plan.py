"""Book planning focuses retrieval without hiding original reader requirements."""

import asyncio
import json

import pytest
from pydantic import ValidationError
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from src.linger.agents.librarian.agent import build_librarian_agent
from src.linger.agents.librarian.models import BookRequestPart
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.orchestration.evidence_strength import judge_evidence_strength


def record(identity, text):
    return EvidenceRecord(
        evidence_id=identity, work_id="test", book_version_id="test-v1",
        chapter_id="test-ch01", chapter_number=1, location="Chapter1",
        source_sha256="a" * 64, source_lines=(1, 2), text=text,
    )


@pytest.mark.parametrize("purpose", ["reference", "answer"])
def test_book_request_precedes_selection_and_original_context_survives(purpose):
    question = "Compare Mara refusing the invitation with my two voices at work and home."
    anchor = "Mara refusing the invitation"
    inputs = []

    def model(messages, info):
        payload = json.loads(next(
            part.content for message in messages for part in message.parts
            if isinstance(part, UserPromptPart)
        ))
        inputs.append(payload)
        if "current_line" in payload:
            assert "evidence" not in payload
            assert payload["current_line"] == question
            output = {"parts": [{"context_spans": [], "purpose": purpose, "reader_spans": [anchor]}]}
        else:
            assert payload["original_request"]["current_line"] == question
            assert "my two voices" not in json.dumps(payload["request"])
            assert payload["request"]["parts"][0]["reader_spans"] == [anchor]
            assert payload["request"]["parts"][0]["purpose"] == purpose
            output = {
                "evidence_strength": "sufficient", "strength_reason": "The refusal is present.",
                "relevant_evidence_ids": ["refusal"], "limitations": [],
                "support": [{"evidence_id": "refusal", "part_index": 0,
                             "necessary_support": "The requested refusal."}],
            }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    result = asyncio.run(judge_evidence_strength(
        "All occasions when Mara seems divided", (
            record("refusal", "Mara refused the invitation."),
            record("temptation", "Mara spoke in two voices."),
        ), reader_question=question, agent=build_librarian_agent(FunctionModel(model)),
    ))
    assert result.relevant_evidence_ids == ("refusal",)
    assert len(inputs) == 2


@pytest.mark.parametrize("fault", ["invented_anchor", "invented_part"])
def test_invented_request_anchors_or_selection_parts_are_rejected(fault):
    calls = 0

    def model(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1 or fault == "invented_anchor":
            output = {"parts": [{"context_spans": [], "purpose": "answer", "reader_spans": [
                "a question never asked" if fault == "invented_anchor" else "Mara refuses"
            ]}]}
        else:
            output = {
                "evidence_strength": "sufficient", "strength_reason": "Direct refusal.",
                "relevant_evidence_ids": ["refusal"], "limitations": [],
                "support": [{"evidence_id": "refusal", "part_index": 1,
                             "necessary_support": "A made-up second requirement."}],
            }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    from pydantic_ai.exceptions import UnexpectedModelBehavior
    with pytest.raises(UnexpectedModelBehavior):
        asyncio.run(judge_evidence_strength(
            "Mara refuses", (record("refusal", "Mara refuses."),),
            agent=build_librarian_agent(FunctionModel(model)),
        ))


@pytest.mark.parametrize("parts, mappings", [
    (["Mara's reply and the narrator's description"], [("reply", 0), ("narration", 0)]),
    (["Mara's reply", "the narrator's description"], [("reply", 0), ("narration", 1)]),
])
def test_one_or_multiple_book_needs_can_require_multiple_passages(parts, mappings):
    calls = 0

    def model(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            output = {"parts": [{"context_spans": [], "purpose": "answer", "reader_spans": [text]} for text in parts]}
        else:
            output = {
                "evidence_strength": "sufficient", "strength_reason": "Complete requested quotation.",
                "relevant_evidence_ids": ["reply", "narration"], "limitations": [],
                "support": [{"evidence_id": identity, "part_index": index,
                             "necessary_support": "Requested wording in this record."}
                            for identity, index in mappings],
            }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    result = asyncio.run(judge_evidence_strength(
        "Please quote Mara's reply and the narrator's description.",
        (record("reply", "No, said Mara."), record("narration", "She answered doubtfully.")),
        agent=build_librarian_agent(FunctionModel(model)),
    ))
    assert result.relevant_evidence_ids == ("reply", "narration")


def test_sufficient_cannot_omit_an_existing_book_need():
    calls = 0

    def model(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            output = {"parts": [{"context_spans": [], "purpose": "answer", "reader_spans": [text]}
                                for text in ("the refusal", "the invitation")]}
        else:
            output = {
                "evidence_strength": "sufficient", "strength_reason": "Only the refusal.",
                "relevant_evidence_ids": ["refusal"], "limitations": [],
                "support": [{"evidence_id": "refusal", "part_index": 0,
                             "necessary_support": "The refusal."}],
            }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    from pydantic_ai.exceptions import UnexpectedModelBehavior
    with pytest.raises(UnexpectedModelBehavior):
        asyncio.run(judge_evidence_strength(
            "Compare the refusal with the invitation", (record("refusal", "Mara refused."),),
            agent=build_librarian_agent(FunctionModel(model)),
        ))


@pytest.mark.parametrize("fault", [None, "invented_span", "missing_support"])
def test_assessment_recovers_omitted_need_without_relaxing_span_or_coverage_checks(fault):
    question = "Compare the refusal with the invitation. My work situation feels similar."

    def model(messages, info):
        payload = json.loads(next(
            part.content for message in messages for part in message.parts
            if isinstance(part, UserPromptPart)
        ))
        if "current_line" in payload:
            output = {"parts": [{"context_spans": [], "purpose": "reference",
                                  "reader_spans": ["the refusal"]}]}
        else:
            assert payload["original_request"]["current_line"] == question
            output = {
                "additional_parts": [{"context_spans": [], "purpose": "reference",
                                      "reader_spans": ["the celebration" if fault == "invented_span" else "the invitation"]}],
                "evidence_strength": "sufficient", "strength_reason": "Both requested events are supported.",
                "relevant_evidence_ids": ["refusal"],
                "support": [{"evidence_id": "refusal", "part_index": 0,
                             "necessary_support": "The refusal."}],
            }
            if fault != "missing_support":
                output["relevant_evidence_ids"].append("invitation")
                output["support"].append({"evidence_id": "invitation", "part_index": 1,
                                          "necessary_support": "The invitation named in the original request."})
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    invocation = judge_evidence_strength(
        question, (record("refusal", "Mara refused."), record("invitation", "Mara was invited.")),
        agent=build_librarian_agent(FunctionModel(model)),
    )
    if fault:
        from pydantic_ai.exceptions import UnexpectedModelBehavior
        with pytest.raises(UnexpectedModelBehavior):
            asyncio.run(invocation)
    else:
        result = asyncio.run(invocation)
        assert result.evidence_strength == "sufficient"
        assert result.relevant_evidence_ids == ("refusal", "invitation")


def test_book_request_cannot_replace_reader_words_with_a_generated_question():
    with pytest.raises(ValidationError, match="Extra inputs"):
        BookRequestPart.model_validate({
            "context_spans": [],
            "purpose": "reference",
            "reader_spans": ["Mara refusing the invitation"],
            "question": "Why did Mara speak in two voices at work and home?",
        })


def test_no_authorized_scope_stops_before_planning_retrieval_or_assessment():
    from unittest.mock import Mock, patch

    from src.linger.agents.librarian.models import BookRequestPlan
    from src.linger.orchestration.book_evidence import retrieve_book_evidence

    librarian = Mock()
    with (
        patch("src.linger.orchestration.book_evidence.plan_book_request", return_value=BookRequestPlan(parts=())) as planner,
        patch("src.linger.orchestration.book_evidence.assess_book_evidence") as assessor,
    ):
        result = asyncio.run(retrieve_book_evidence(
            "Help me find a sentence to say.", book_scopes=(), librarian=librarian,
        ))
    assert result.items == ()
    assert result.judgement.evidence_strength == "none"
    planner.assert_not_awaited()
    librarian.retrieve_for_judgement.assert_not_called()
    assessor.assert_not_called()


@pytest.mark.parametrize("planning_failed", [False, True])
def test_empty_or_failed_plan_recovers_original_request_within_scope(planning_failed):
    from unittest.mock import Mock, patch

    from apps.backend.contracts import BookScope, EvidenceBundle, EvidenceItem
    from src.linger.agents.librarian.models import BookRequestPlan, EvidenceStrengthDecision
    from src.linger.orchestration.book_evidence import retrieve_book_evidence

    librarian = Mock()
    question = "The scene the reader actually named."
    scope = BookScope(work_id="test", book_version_id="test-v1", chapter_max=1)
    item = EvidenceItem(
        evidence_id="scene", work_id="test", book_version_id="test-v1",
        chapter_id="test-ch01", chapter=1, location="Chapter 1", source_title="Test",
        source_sha256="a" * 64, source_lines=(1, 2), excerpt="The named scene.", relevance=.9,
    )
    librarian.retrieve_for_judgement.return_value = EvidenceBundle(items=[item], retrieval_note="bounded recovery")
    with (
        patch("src.linger.orchestration.book_evidence.plan_book_request",
              return_value=BookRequestPlan(parts=()),
              side_effect=ValueError("invalid reader span") if planning_failed else None),
        patch("src.linger.orchestration.book_evidence.assess_book_evidence", return_value=EvidenceStrengthDecision(
            evidence_strength="sufficient", strength_reason="Original need is supported.",
            relevant_evidence_ids=("scene",),
        )) as assessor,
    ):
        result = asyncio.run(retrieve_book_evidence(question, book_scopes=(scope,), librarian=librarian))
    request = librarian.retrieve_for_judgement.call_args.args[0]
    assert request.query == question
    assert request.book_scopes == [scope]
    assert librarian.retrieve_for_judgement.call_count == 1
    assert assessor.await_args.args[0].parts == ()
    assert assessor.await_args.kwargs["original_request"].current_line == question
    assert result.items == (item,)


def test_over_budget_plan_is_rejected_without_truncating_requested_parts():
    from unittest.mock import Mock, patch

    from src.linger.agents.librarian.models import BookRequestPlan
    from apps.backend.contracts import BookScope
    from src.linger.orchestration.book_evidence import (
        EvidenceJudgementError, MAX_QUERY_CHARACTERS, MAX_SEARCH_QUERIES, retrieve_book_evidence,
    )

    original = "".join(f"{index:04d}" + "a" * (MAX_QUERY_CHARACTERS - 4)
                       for index in range(MAX_SEARCH_QUERIES + 1))
    plan = BookRequestPlan(parts=(BookRequestPart(
        context_spans=(), purpose="answer", reader_spans=(original,),
    ),))
    librarian = Mock()
    with patch("src.linger.orchestration.book_evidence.plan_book_request", return_value=plan):
        with pytest.raises(EvidenceJudgementError, match="retrieval query budget"):
            asyncio.run(retrieve_book_evidence(
                original, book_scopes=(BookScope(work_id="test", book_version_id="test-v1", chapter_max=1),),
                librarian=librarian,
            ))
    librarian.retrieve_for_judgement.assert_not_called()


def test_case_only_reader_span_can_be_repaired_within_existing_retry_budget():
    from pydantic_ai.messages import RetryPromptPart
    from src.linger.orchestration.evidence_strength import plan_book_request

    calls = []
    original = "The gardeners painted the roses."

    def model(messages, info):
        calls.append(messages)
        if len(calls) == 1:
            span = original.lower()
        else:
            feedback = next(part for message in messages for part in message.parts if isinstance(part, RetryPromptPart))
            errors = json.loads(feedback.content)["errors"]
            assert errors[0]["path"] == "parts[0].reader_spans[0]"
            assert errors[0]["suggested_reader_span"] == original
            span = errors[0]["suggested_reader_span"]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "parts": [{"context_spans": [], "purpose": "reference", "reader_spans": [span]}],
        })])

    result = asyncio.run(plan_book_request(original, agent=build_librarian_agent(FunctionModel(model))))
    assert result.parts[0].reader_spans == (original,)
    assert len(calls) == 2


def test_span_feedback_reports_all_errors_and_only_unique_case_suggestions():
    from src.linger.agents.librarian.models import (
        BookRequestPlan, LibrarianBookRequestInput, book_request_span_errors,
    )

    original = "The gardeners paint. ALICE waits. Alice waits."
    plan = BookRequestPlan(parts=(BookRequestPart(
        context_spans=(), purpose="reference",
        reader_spans=("the gardeners paint.", "invented words", "alice waits.", " "),
    ),))
    errors = book_request_span_errors(plan, LibrarianBookRequestInput(current_line=original))
    assert [item["path"] for item in errors] == [
        f"parts[0].reader_spans[{index}]" for index in range(4)
    ]
    assert errors[0]["suggested_reader_span"] == "The gardeners paint."
    assert all("suggested_reader_span" not in item for item in errors[1:])
    assert plan.parts[0].reader_spans[0] == "the gardeners paint."


def test_application_still_rejects_invalid_spans_from_an_injected_agent():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from src.linger.agents.librarian.models import BookRequestPlan
    from src.linger.orchestration.evidence_strength import plan_book_request

    agent = AsyncMock()
    agent.run.return_value = SimpleNamespace(output=BookRequestPlan(parts=(
        BookRequestPart(context_spans=(), purpose="reference", reader_spans=("invented words",)),
    )))
    with pytest.raises(ValueError, match="reader span"):
        asyncio.run(plan_book_request("The gardeners paint.", agent=agent))


def test_mistyped_selected_evidence_id_is_repaired_within_the_assessment_run():
    from src.linger.agents.librarian.models import BookRequestPlan, LibrarianBookRequestInput
    from src.linger.orchestration.evidence_strength import assess_book_evidence

    lake = record("pg2397-sec024-ln3115-3140", "All thoughts of work and college were thrust into the background.")
    other = record("pg2397-sec022-ln2441-2467", "College left little time for solitude.")
    plan = BookRequestPlan.model_validate({"parts": [{
        "context_spans": [], "purpose": "reference", "reader_spans": ["forgetting all about college at the lake"],
    }]})
    attempts = []

    def model(messages, info):
        # Run 4 spliced one record's section onto another record's line range.
        if attempts:
            retry = str(messages[-1].parts[0].content)
            assert "closest_supplied_ids" in retry and lake.evidence_id in retry
        evidence_id = "pg2397-sec022-ln3115-3140" if not attempts else lake.evidence_id
        attempts.append(evidence_id)
        # The first attempt also leaves a selected record without support, which the
        # schema rejects; the ID fault must still be reported in that same retry.
        selected = [evidence_id, other.evidence_id] if len(attempts) == 1 else [evidence_id]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "evidence_strength": "sufficient", "strength_reason": "The lake passage answers the need.",
            "relevant_evidence_ids": selected, "additional_parts": [],
            "support": [{"evidence_id": evidence_id, "part_index": 0, "necessary_support": "Work and college recede at the lake."}],
        })])

    decision = asyncio.run(assess_book_evidence(
        plan, (lake, other),
        original_request=LibrarianBookRequestInput(current_line="Keller forgetting all about college at the lake"),
        agent=build_librarian_agent(FunctionModel(model)),
    ))

    assert decision.relevant_evidence_ids == (lake.evidence_id,)
    assert len(attempts) == 2


def test_assessment_id_errors_name_the_closest_supplied_record():
    from src.linger.agents.librarian.models import (
        BookRequestPlan, LibrarianBookRequestInput, LibrarianEvidenceStrengthInput,
        evidence_assessment_errors,
    )

    lake = record("pg2397-vb3cc1e13-sec024-ln3115-3140", "Lake text.")
    other = record("pg2397-vb3cc1e13-sec022-ln2441-2467", "College text.")
    request = LibrarianEvidenceStrengthInput(
        original_request=LibrarianBookRequestInput(current_line="the lake"),
        request=BookRequestPlan(parts=()), evidence=(lake, other), max_evidence_records=1,
    )
    # Run 5 recorded both faults at once: a spliced ID and support drifting from the selection.
    wrong = "pg2397-vb3cc1e13-sec022-ln3115-3140"
    drifted = "pg2397-vb3cc1e13-sec022-ln2441-2475"

    errors = evidence_assessment_errors({
        "relevant_evidence_ids": [wrong, other.evidence_id],
        "support": [{"evidence_id": identity} for identity in (wrong, drifted)],
    }, request)

    assert [error["path"] for error in errors] == [
        "relevant_evidence_ids", "relevant_evidence_ids[0]",
        "support[0].evidence_id", "support[1].evidence_id", "support",
    ]
    assert lake.evidence_id in errors[1]["closest_supplied_ids"]
    assert other.evidence_id in errors[3]["closest_supplied_ids"]
    assert errors[4]["selected_without_support"] == [other.evidence_id]
    assert errors[4]["support_not_selected"] == [drifted]
