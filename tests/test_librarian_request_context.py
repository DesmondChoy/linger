"""Exact scene context must survive planning into retrieval and assessment."""

import asyncio
import json
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from apps.backend.contracts import BookScope, EvidenceBundle, EvidenceItem
from src.linger.agents.librarian.agent import build_librarian_agent
from src.linger.agents.librarian.models import BookRequestPart, BookRequestPlan
from src.linger.orchestration.book_evidence import retrieve_book_evidence
from src.linger.orchestration.evidence_strength import plan_book_request

SCENE = "Mara refuses the captain's invitation at the bridge"
QUESTION = "Quote her reply and how the narrator describes her saying it."
PRIVATE = "I keep hesitating about my new role at work."
LINE = f"I've read the scene where {SCENE}. {PRIVATE} {QUESTION}"
PLAN = {"parts": [{"context_spans": [SCENE], "purpose": "answer", "reader_spans": [QUESTION]}]}


def passage(identity, chapter, text):
    return EvidenceItem(
        evidence_id=identity, work_id="fiction", book_version_id="fiction-v1",
        chapter_id=f"fiction-ch{chapter}", chapter=chapter, location=f"Chapter {chapter}",
        source_title="Fiction", source_sha256="a" * 64, source_lines=(1, 2),
        excerpt=text, relevance=.9,
    )


def test_preceding_scene_resolves_quotation_pronouns_before_retrieval():
    desired = passage("bridge-reply", 5, "No, Mara replied doubtfully.")
    unrelated = passage("earlier-reply", 1, "Yes, she answered.")
    phases = []

    class Librarian:
        def retrieve_for_judgement(self, request):
            if request.query == f"{SCENE} {QUESTION}":
                phases.append("focused_retrieval")
                assert PRIVATE not in request.query
            else:
                phases.append("original_retrieval")
                assert request.query == LINE
            assert request.book_scopes[0].chapter_max == 5
            selected = desired if SCENE in request.query else unrelated
            return EvidenceBundle(items=[selected], retrieval_note="controlled query-sensitive search")

    def model(messages, info):
        prompts = [part for message in messages for part in message.parts if isinstance(part, UserPromptPart)]
        assert len(prompts) == 1
        payload = json.loads(prompts[0].content)
        if "current_line" in payload:
            phases.append("planning")
            assert payload["current_line"] == LINE
            output = PLAN
        else:
            phases.append("assessment")
            assert BookRequestPlan.model_validate(payload["request"]) == BookRequestPlan.model_validate(PLAN)
            assert PRIVATE not in json.dumps(payload["request"])
            assert payload["original_request"]["current_line"] == LINE
            assert payload["evidence"][0]["evidence_id"] == desired.evidence_id
            output = {
                "evidence_strength": "sufficient", "strength_reason": "The located reply includes the requested narration.",
                "relevant_evidence_ids": [desired.evidence_id],
                "support": [{"evidence_id": desired.evidence_id, "part_index": 0,
                             "necessary_support": "The exact reply and narrator's qualification."}],
            }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    with patch("src.linger.agents.librarian.agent.librarian_agent", build_librarian_agent(FunctionModel(model))):
        result = asyncio.run(retrieve_book_evidence(
            LINE, book_scopes=(BookScope(work_id="fiction", book_version_id="fiction-v1", chapter_max=5),),
            librarian=Librarian(),
        ))
    assert phases == ["planning", "focused_retrieval", "original_retrieval", "assessment"]
    assert result.items == (desired,)


@pytest.mark.parametrize("field", ["context_spans", "reader_spans"])
def test_context_and_question_are_both_exactly_validated_with_repair(field):
    calls = []

    def model(messages, info):
        calls.append(messages)
        part = {**PLAN["parts"][0]}
        if len(calls) == 1:
            part[field] = [part[field][0].lower()]
        else:
            feedback = next(part for message in messages for part in message.parts if isinstance(part, RetryPromptPart))
            error = json.loads(feedback.content)["errors"][0]
            assert error["path"] == f"parts[0].{field}[0]"
            part[field] = [error["suggested_reader_span"]]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"parts": [part]})])

    result = asyncio.run(plan_book_request(LINE, agent=build_librarian_agent(FunctionModel(model))))
    assert len(calls) == 2
    assert result == BookRequestPlan.model_validate(PLAN)


def test_context_from_an_unsupplied_source_is_not_accepted():
    calls = []

    def model(messages, info):
        calls.append(messages)
        output = {"parts": [{**PLAN["parts"][0], "context_spans": ["Mara at the palace in the later chapter"]}]}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    with pytest.raises(UnexpectedModelBehavior):
        asyncio.run(plan_book_request(LINE, agent=build_librarian_agent(FunctionModel(model))))
    assert len(calls) == 2


def test_self_contained_question_can_explicitly_have_no_context():
    part = BookRequestPart(context_spans=(), purpose="answer", reader_spans=("Why does Mara refuse the captain's invitation?",))
    assert part.context_spans == ()
    with pytest.raises(ValidationError):
        BookRequestPart.model_validate({"purpose": "answer", "reader_spans": part.reader_spans})
