"""Evaluation contracts distinguish source formatting from changed content."""

from types import SimpleNamespace
import asyncio
import json

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from evals.librarian.benchmark import Hit, _citation_resolves
from evals.librarian.live_validation import _usage
from apps.backend import sessions
from apps.backend.chat_turn import resolve_reading_context
from apps.backend.schemas import ChatRequest
from src.linger.agents.muse.models import MuseCandidate
from src.linger.agents.provenance.models import ProvenanceInput, ProvenanceReview
from tests.provenance_fixtures import review_with_audits


def test_citation_accepts_only_canonical_blank_line_normalization():
    original = ['first paragraph', '', '', 'second paragraph']
    hit = Hit('source', 1, (1, 4), 'first paragraph\n\nsecond paragraph', 1.0)
    assert _citation_resolves(hit, original)
    assert not _citation_resolves(Hit('source', 1, (1, 4), 'first paragraph\n\nchanged paragraph', 1.0), original)
    assert not _citation_resolves(Hit('source', 1, (1, 4), 'firstparagraph\n\nsecond paragraph', 1.0), original)


def test_usage_reads_installed_sdk_property():
    result = SimpleNamespace(usage=SimpleNamespace(input_tokens=10, output_tokens=3, requests=2))
    assert _usage([result]) == {'available': True, 'input_tokens': 10, 'output_tokens': 3, 'requests': 2}


def test_usage_does_not_label_partial_counts_as_complete():
    complete = SimpleNamespace(usage=SimpleNamespace(input_tokens=10, output_tokens=3, requests=2))
    incomplete = SimpleNamespace(usage=None)
    assert _usage([complete, incomplete]) == {
        'available': False, 'input_tokens': None, 'output_tokens': None, 'requests': None,
    }


@pytest.mark.parametrize('introduction', [
    "I'm reading Alice's Adventures in Wonderland, and I've completed chapter 5.",
    "I'm reading Alice's Adventures in Wonderland, and I have completed chapter 5.",
])
def test_completion_clause_is_not_part_of_the_book_title(introduction):
    session_id = 'title-completion-regression'
    try:
        context = resolve_reading_context(ChatRequest(session_id=session_id, message=introduction))
        assert context.status == 'confirmed'
        assert context.work_id == 'pg11'
        assert context.chapter_max == 5
    finally:
        sessions.clear(session_id)


def test_release_component_delivers_the_reader_request_to_independent_review(monkeypatch):
    from evals.librarian import live_validation
    from evals.librarian.benchmark import BenchmarkCase

    case = BenchmarkCase(
        case_id="reader-request-handoff", query="Could we explore this idea?",
        chapter_max=5, expected_strength="none", relevant_ranges=(),
    )
    muse_requests = []
    review_requests = []

    def latest_prompt(messages):
        return next(part.content for message in reversed(messages)
                    for part in message.parts if isinstance(part, UserPromptPart))

    def draft(messages, info):
        muse_requests.append(json.loads(latest_prompt(messages)))
        output = {
            "reply": "What would you like to explore about it?", "evidence_uses": [],
            "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
        }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    def review(messages, info):
        request = ProvenanceInput.model_validate_json(latest_prompt(messages))
        review_requests.append(request)
        output = review_with_audits(request, {
            "findings": [], "response_decision": "pass",
            "emotional_boundary_decision": "not_required", "capture_decision": "no_candidate",
        })
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output.model_dump(mode="json"))])

    monkeypatch.setattr(live_validation, "muse_chat_agent", Agent(FunctionModel(draft), output_type=MuseCandidate))
    monkeypatch.setattr(live_validation, "provenance_agent", Agent(FunctionModel(review), output_type=ProvenanceReview))
    result = asyncio.run(live_validation._run_case(case))

    assert result["release_source"] == "muse_candidate"
    assert len(muse_requests) == len(review_requests) == 1
    reader_message = muse_requests[0]["muse_turn"]["user_message"]
    assert case.query in reader_message
    assert "completed chapter 5" in reader_message
    assert review_requests[0].current_line.text == reader_message
