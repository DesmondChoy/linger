"""Book needs must be fixed before retrieved passages can influence selection."""

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
def test_book_request_is_fixed_before_selection_and_non_book_context_is_absent(purpose):
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
            assert "my two voices" not in json.dumps(payload)
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
    expected_error = UnexpectedModelBehavior if fault == "invented_anchor" else ValueError
    with pytest.raises(expected_error):
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

    with pytest.raises(ValueError, match="every requested part"):
        asyncio.run(judge_evidence_strength(
            "Compare the refusal with the invitation", (record("refusal", "Mara refused."),),
            agent=build_librarian_agent(FunctionModel(model)),
        ))


def test_book_request_cannot_replace_reader_words_with_a_generated_question():
    with pytest.raises(ValidationError, match="Extra inputs"):
        BookRequestPart.model_validate({
            "context_spans": [],
            "purpose": "reference",
            "reader_spans": ["Mara refusing the invitation"],
            "question": "Why did Mara speak in two voices at work and home?",
        })


def test_empty_plan_stops_before_private_retrieval_or_assessment():
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
    planner.assert_awaited_once()
    librarian.retrieve_for_judgement.assert_not_called()
    assessor.assert_not_called()


def test_planning_failure_stops_before_private_retrieval():
    from unittest.mock import Mock, patch

    from src.linger.orchestration.book_evidence import EvidenceJudgementError, retrieve_book_evidence

    librarian = Mock()
    with patch("src.linger.orchestration.book_evidence.plan_book_request", side_effect=ValueError("invalid reader span")):
        with pytest.raises(EvidenceJudgementError):
            asyncio.run(retrieve_book_evidence(
                "The scene the reader actually named.", book_scopes=(), librarian=librarian,
            ))
    librarian.retrieve_for_judgement.assert_not_called()


def test_over_budget_plan_is_rejected_without_truncating_requested_parts():
    from unittest.mock import Mock, patch

    from src.linger.agents.librarian.models import BookRequestPlan
    from src.linger.orchestration.book_evidence import EvidenceJudgementError, retrieve_book_evidence

    plan = BookRequestPlan(parts=(BookRequestPart(
        context_spans=(), purpose="answer", reader_spans=("a" * 1001, "b" * 1001),
    ),))
    librarian = Mock()
    with patch("src.linger.orchestration.book_evidence.plan_book_request", return_value=plan):
        with pytest.raises(EvidenceJudgementError, match="retrieval budget"):
            asyncio.run(retrieve_book_evidence(
                "Compare the two prior passages.", book_scopes=(), librarian=librarian,
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
