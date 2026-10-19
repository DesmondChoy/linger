"""Evaluation contracts distinguish source formatting from changed content."""

from types import SimpleNamespace
import asyncio
import json

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from evals.librarian.benchmark import Hit, _citation_resolves, load_cases
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


@pytest.mark.parametrize("case_id,record_id,strength,coverage", [
    ("identity-theme", "pg11-v01b38ea4-ch05-ln0977-0977", "sufficient", 0.0),
    ("identity-theme", "pg11-v01b38ea4-ch05-ln1029-1029", "sufficient", 0.0),
    ("drink-me-mechanism", "pg11-v01b38ea4-ch01-ln0186-0192", "weak", 1.0),
    ("drink-me-mechanism", "pg11-v01b38ea4-ch01-ln0186-0192", "sufficient", 1.0),
])
def test_live_grades_source_coverage_and_the_observed_strength(
    monkeypatch, case_id, record_id, strength, coverage,
):
    from apps.backend.librarian import Librarian
    from evals.librarian import live_validation
    from src.linger.contracts.librarian import RetrievalResult, SearchedScope

    case = next(case for case in load_cases().cases if case.case_id == case_id)
    record = Librarian().fetch_by_id(record_id)
    retrieval = RetrievalResult(
        kind="result", request_id="grading-test", outcome="evidence_found",
        evidence_strength=strength, strength_reason="Controlled judgment for grader testing.",
        searched_scope=SearchedScope(
            work_id=record.work_id, book_version_id=record.book_version_id,
            max_chapter_inclusive=case.chapter_max,
        ),
        evidence=(record,),
    )
    candidate = MuseCandidate.model_validate({
        "reply": record.text,
        "evidence_uses": [{
            "source_kind": "book_corpus", "evidence_id": record.evidence_id,
            "source_location": record.location, "exact_quote": record.text,
            "supported_claims": [record.text],
        }],
        "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
    })
    messages = (
        ModelResponse(parts=[ToolCallPart("librarian_search", {}, tool_call_id="search")]),
        ModelRequest(parts=[ToolReturnPart("librarian_search", retrieval, tool_call_id="search")]),
    )

    async def release(*args, muse, **kwargs):
        muse.results.append(SimpleNamespace(output=candidate, new_messages=lambda: messages))
        return SimpleNamespace(
            reply=candidate.reply, release_source="muse_candidate",
            provenance_verdicts=("pass",), finding_codes=(), failure_stage=None,
        )

    monkeypatch.setattr(live_validation, "reflection_reply", release)
    for expected in ("weak", "sufficient"):
        result = asyncio.run(live_validation._run_case(case.model_copy(update={"expected_strength": expected})))
        assert result["predicted_strength"] == strength
        assert result["strength_correct"] is (strength == expected)
        assert result["final_evidence_recall"] == coverage
        assert result["final_citation_precision"] == coverage


NECK_ONLY_REPLY = (
    "In Chapter 5, the Pigeon reads Alice’s unusually long neck as proof that "
    "she’s a serpent. It’s also on constant watch for serpents because they "
    "threaten its eggs, so it treats Alice as the danger it expects to find."
)
BOTH_REASONS_REPLY = (
    "In Chapter 5, the Pigeon sees Alice’s unusually long neck and suspects she "
    "is after its eggs. When Alice points out that girls eat eggs too, the Pigeon "
    "reasons that egg-eating makes someone serpent-like."
)


@pytest.mark.parametrize("reply,release_source,recall,missing,evidence_recall,graded,complete", [
    (NECK_ONLY_REPLY, "muse_candidate", 0.5, ["egg-eating-admission"], 1.0, 1, 0),
    (BOTH_REASONS_REPLY, "muse_candidate", 1.0, [], 1.0, 1, 1),
    ("I couldn’t verify that, so I’d rather not guess.", "application_safe_decline", None, [], 0.0, 0, 0),
], ids=["released-without-admission", "released-complete", "declined"])
def test_live_reports_whether_the_released_reply_states_each_required_fact(
    monkeypatch, reply, release_source, recall, missing, evidence_recall, graded, complete,
):
    from apps.backend.librarian import Librarian
    from evals.librarian import live_validation
    from src.linger.contracts.librarian import RetrievalResult, SearchedScope

    record = Librarian().fetch_by_id("pg11-v01b38ea4-ch05-ln1208-1212")
    retrieval = RetrievalResult(
        kind="result", request_id="reply-fact-test", outcome="evidence_found",
        evidence_strength="sufficient", strength_reason="Controlled judgment for grader testing.",
        searched_scope=SearchedScope(
            work_id=record.work_id, book_version_id=record.book_version_id,
            max_chapter_inclusive=5,
        ),
        evidence=(record,),
    )
    # The draft always cites the passage covering both reasons. A declined turn
    # still has a draft, which must not be graded because it was never released.
    candidate = MuseCandidate.model_validate({
        "reply": NECK_ONLY_REPLY if release_source != "muse_candidate" else reply,
        "evidence_uses": [{
            "source_kind": "book_corpus", "evidence_id": record.evidence_id,
            "source_location": record.location, "exact_quote": None,
            "supported_claims": ["The Pigeon takes Alice for a serpent."],
        }],
        "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
    })
    messages = (
        ModelResponse(parts=[ToolCallPart("librarian_search", {}, tool_call_id="search")]),
        ModelRequest(parts=[ToolReturnPart("librarian_search", retrieval, tool_call_id="search")]),
    )

    async def release(*args, muse, **kwargs):
        muse.results.append(SimpleNamespace(output=candidate, new_messages=lambda: messages))
        return SimpleNamespace(
            reply=reply, release_source=release_source,
            provenance_verdicts=("pass",), finding_codes=(), failure_stage=None,
        )

    monkeypatch.setattr(live_validation, "reflection_reply", release)
    # `father-william` declares no required facts, so it is never graded on them.
    report = asyncio.run(live_validation.run_validation(
        case_ids={"pigeon-serpent", "father-william"},
    ))
    by_id = {item["case_id"]: item for item in report["cases"]}

    pigeon = by_id["pigeon-serpent"]
    assert pigeon["reply_fact_recall"] == recall
    assert pigeon["missing_reply_facts"] == missing
    assert pigeon["final_evidence_recall"] == evidence_recall
    assert by_id["father-william"]["reply_fact_recall"] is None
    assert by_id["father-william"]["missing_reply_facts"] == []

    summary = report["summary"]
    assert summary["reply_fact_recall"] == recall
    assert summary["reply_fact_graded_count"] == graded
    assert summary["reply_fact_complete_count"] == complete


def test_reply_fact_recall_does_not_change_whether_live_targets_pass(monkeypatch):
    from apps.backend.librarian import Librarian
    from evals.librarian import live_validation
    from src.linger.contracts.librarian import RetrievalResult, SearchedScope

    record = Librarian().fetch_by_id("pg11-v01b38ea4-ch05-ln1208-1212")
    retrieval = RetrievalResult(
        kind="result", request_id="reply-fact-test", outcome="evidence_found",
        evidence_strength="sufficient", strength_reason="Controlled judgment for grader testing.",
        searched_scope=SearchedScope(
            work_id=record.work_id, book_version_id=record.book_version_id,
            max_chapter_inclusive=5,
        ),
        evidence=(record,),
    )
    messages = (
        ModelResponse(parts=[ToolCallPart("librarian_search", {}, tool_call_id="search")]),
        ModelRequest(parts=[ToolReturnPart("librarian_search", retrieval, tool_call_id="search")]),
    )

    def summary(reply):
        candidate = MuseCandidate.model_validate({
            "reply": reply,
            "evidence_uses": [{
                "source_kind": "book_corpus", "evidence_id": record.evidence_id,
                "source_location": record.location, "exact_quote": None,
                "supported_claims": ["The Pigeon takes Alice for a serpent."],
            }],
            "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
        })

        async def release(*args, muse, **kwargs):
            muse.results.append(SimpleNamespace(output=candidate, new_messages=lambda: messages))
            return SimpleNamespace(
                reply=reply, release_source="muse_candidate",
                provenance_verdicts=("pass",), finding_codes=(), failure_stage=None,
            )

        monkeypatch.setattr(live_validation, "reflection_reply", release)
        return asyncio.run(live_validation.run_validation())["summary"]

    # Targets require the complete case set, so the benchmark is this one case.
    benchmark = live_validation.load_cases()
    only_pigeon = benchmark.model_copy(update={
        "cases": tuple(case for case in benchmark.cases if case.case_id == "pigeon-serpent"),
    })
    monkeypatch.setattr(live_validation, "load_cases", lambda: only_pigeon)

    incomplete, complete = summary(NECK_ONLY_REPLY), summary(BOTH_REASONS_REPLY)

    assert (incomplete["reply_fact_recall"], complete["reply_fact_recall"]) == (0.5, 1.0)
    # Every target is met with half the required facts missing from the reply.
    assert incomplete["targets_pass"] is True
    assert complete["targets_pass"] is True
