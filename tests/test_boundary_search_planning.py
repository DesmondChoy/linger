"""Progress searches preserve the stopping event without granting disclosure."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from apps.backend.contracts import EvidenceBundle
from tests.boundary_fixtures import event_resolution, quoted_support, identify_fixture_event
from src.linger.agents.librarian.models import BoundaryUncertainDecision, BoundaryInferenceDecision, BookRequestPart, BookRequestPlan
from src.linger.contracts.session import ReaderStatement
from src.linger.orchestration import evidence_strength
from src.linger.orchestration.boundary import infer_spoiler_boundary
from tests.test_boundary_inference import FakeLibrarian, VERSION_ID, WORK_ID, item, memory


class PlanningLibrarian(FakeLibrarian):
    def __init__(self, results):
        super().__init__()
        self.results = results
        self.ordinary_requests = []

    def retrieve(self, request):
        self.ordinary_requests.append(request)
        return EvidenceBundle(items=[], retrieval_note="No candidate cleared retrieval thresholds.")

    def retrieve_for_judgement(self, request):
        self.requests.append(request)
        return EvidenceBundle(items=self.results.get(request.query, []), retrieval_note="Private candidates")


def plan(*queries, uncertain=False):
    return BookRequestPlan(
        parts=tuple(BookRequestPart(
            context_spans=(), reader_spans=(query,), purpose="progress", uncertain=uncertain,
        ) for query in queries),
    )


def uncertainty(memories):
    return BoundaryUncertainDecision(
        memory_assessments=tuple({
            "memory_id": record.memory_id, "status": "not_supported", "evidence_ids": (),
            "reason": "The current event remains unresolved.",
        } for record in memories),
        outcome="uncertain", confidence=0.2, reason_code="insufficient_context",
    )


def test_focused_progress_query_recovers_stopping_event_and_preserves_original_inputs(monkeypatch):
    progress = "Alice has just reached the croquet ground"
    line = progress + ". Why do expectations feel so difficult? My evening plans keep slipping."
    stored = memory("earlier", "Alice spoke with the Caterpillar")
    earlier, stopping = item(5, "Earlier remembered encounter"), item(8, "Current stopping event")
    librarian = PlanningLibrarian({progress: [stopping], stored.text: [earlier]})
    planner = AsyncMock(return_value=plan(progress))
    monkeypatch.setattr(evidence_strength, "plan_book_request", planner)
    received = []

    async def judge(current_line, memories, evidence, statements):
        received.append((current_line, memories, evidence, statements))
        return BoundaryInferenceDecision(
            memory_assessments=({"memory_id": stored.memory_id, "status": "grounded_prior_knowledge",
                                 "evidence_ids": (earlier.evidence_id,), "reason": "The earlier encounter is grounded."},),
            outcome="candidate", work_id=WORK_ID, book_version_id=VERSION_ID,
            chapter_number=8, confidence=0.9, authorization_basis="memory_supported",
            supporting_memory_ids=(stored.memory_id,),
            supporting_evidence=quoted_support(evidence, (earlier.evidence_id, stopping.evidence_id)),
            event_resolution=event_resolution(current_line, evidence, (earlier.evidence_id, stopping.evidence_id)),
        )

    result = asyncio.run(infer_spoiler_boundary(
        line, work_id=WORK_ID, book_version_id=VERSION_ID,
        memories=(stored,), librarian=librarian, judge=judge,
        event_identifier=identify_fixture_event(8),
    ))
    assert result.kind == "candidate"
    assert result.max_chapter_inclusive == 8
    assert received[0][0:2] == (line, (stored,))
    assert received[0][3] == ()
    assert [record.chapter_number for record in received[0][2]] == [8, 5]
    assert [request.query for request in librarian.requests] == [progress, line, stored.text]
    assert librarian.ordinary_requests == []
    assert all(request.purpose == "boundary_inference" for request in librarian.requests)
    assert all(request.book_scopes[0].chapter_max == 12 for request in librarian.requests)
    planner.assert_awaited_once_with(line, prior_reader_statements=(), search_target="reading_progress")
    assert "Current stopping event" not in result.model_dump_json()


@pytest.mark.parametrize("fallback", ["error", "empty"])
def test_failed_or_empty_planning_uses_original_query(monkeypatch, caplog, fallback):
    line = "Alice reached the croquet ground. My plans are tangled."
    librarian = PlanningLibrarian({line: [item(8, "Current event")]})
    planner = AsyncMock(side_effect=RuntimeError("private reader material") if fallback == "error" else None,
                        return_value=plan())
    monkeypatch.setattr(evidence_strength, "plan_book_request", planner)
    judge = AsyncMock(return_value=uncertainty(()))
    caplog.set_level("INFO")
    result = asyncio.run(infer_spoiler_boundary(
        line, work_id=WORK_ID, book_version_id=VERSION_ID,
        memories=(), librarian=librarian, judge=judge,
    ))
    planner.assert_awaited_once_with(line, prior_reader_statements=(), search_target="reading_progress")
    assert [request.query for request in librarian.requests] == [line]
    judge.assert_awaited_once()
    assert result.kind == "uncertain"
    assert "original" in caplog.text.lower()
    assert "private reader material" not in caplog.text
    assert line not in caplog.text


def test_each_progress_part_and_original_query_reach_private_judge(monkeypatch):
    first, second = "Alice reaches the garden", "then meets the queen"
    line = first + " and " + second + ". Why does this remind me of work?"
    planner = AsyncMock(return_value=plan(first, second, uncertain=True))
    monkeypatch.setattr(evidence_strength, "plan_book_request", planner)
    librarian = PlanningLibrarian({first: [item(7, "First event")], second: [item(8, "Second event")],
                                  line: [item(4, "Whole-message fallback")]})
    judge = AsyncMock(return_value=uncertainty(()))
    result = asyncio.run(infer_spoiler_boundary(
        line, work_id=WORK_ID, book_version_id=VERSION_ID,
        memories=(), librarian=librarian, judge=judge,
    ))
    assert [request.query for request in librarian.requests] == [first, second, line]
    assert [record.chapter_number for record in judge.await_args.args[2]] == [7, 8, 4]
    assert judge.await_args.args[0] == line
    assert result.kind == "uncertain"


def test_progress_search_keeps_exact_subject_context_for_a_pronoun(monkeypatch):
    line = "Alice's Adventures in Wonderland. She has reached the croquet ground."
    focused = "Alice's Adventures in Wonderland She has reached the croquet ground"
    planned = BookRequestPlan(parts=(BookRequestPart(
        context_spans=("Alice's Adventures in Wonderland",), purpose="progress",
        reader_spans=("She has reached the croquet ground",),
    ),))
    monkeypatch.setattr(evidence_strength, "plan_book_request", AsyncMock(return_value=planned))
    librarian = PlanningLibrarian({focused: [item(8, "The named book's stopping event")]})
    judge = AsyncMock(return_value=uncertainty(()))
    asyncio.run(infer_spoiler_boundary(
        line, work_id=WORK_ID, book_version_id=VERSION_ID,
        memories=(), librarian=librarian, judge=judge,
    ))
    assert [request.query for request in librarian.requests] == [focused, line]
    assert [record.chapter_number for record in judge.await_args.args[2]] == [8]
    assert judge.await_args.args[0] == line


def test_missing_current_evidence_cannot_be_replaced_by_memory(monkeypatch):
    progress = "Alice reached an unidentified place"
    line = progress + ". What does it mean?"
    stored = memory("earlier", "Alice and the Caterpillar")
    librarian = PlanningLibrarian({stored.text: [item(5, "Memory-only event")]})
    monkeypatch.setattr(evidence_strength, "plan_book_request", AsyncMock(return_value=plan(progress)))
    judge = AsyncMock()
    result = asyncio.run(infer_spoiler_boundary(
        line, work_id=WORK_ID, book_version_id=VERSION_ID,
        memories=(stored,), librarian=librarian, judge=judge,
    ))
    assert [request.query for request in librarian.requests] == [progress, line]
    judge.assert_not_awaited()
    assert result.kind == "uncertain"
    assert result.reason_code == "insufficient_context"


@pytest.mark.parametrize("memory_count", [1, 8])
def test_each_search_leader_precedes_lower_ranked_candidates(monkeypatch, memory_count):
    queries = tuple(f"Alice event {index}" for index in range(8))
    line = ". ".join(queries)
    memories = tuple(memory(f"memory-{i}", f"Alice remembered {i}") for i in range(memory_count))
    results = {query: [item(i + 1, f"Event {i}")] for i, query in enumerate(queries)}
    for i, query in enumerate((line, *(record.text for record in memories))):
        results[query] = [item(12, f"Stream {i} rank {rank}").model_copy(update={
            "evidence_id": f"{VERSION_ID}-ch12-ln{1300 + i * 5 + rank:04d}-{1300 + i * 5 + rank:04d}",
            "source_lines": (1300 + i * 5 + rank, 1300 + i * 5 + rank),
        }) for rank in range(5)]
    librarian = PlanningLibrarian(results)
    monkeypatch.setattr(evidence_strength, "plan_book_request", AsyncMock(return_value=plan(*queries)))
    judge = AsyncMock(return_value=uncertainty(memories))
    asyncio.run(infer_spoiler_boundary(
        line, work_id=WORK_ID, book_version_id=VERSION_ID,
        memories=memories, librarian=librarian, judge=judge,
    ))
    selected = judge.await_args.args[2]
    ids = {record.evidence_id for record in selected}
    leaders = {records[0].evidence_id for records in results.values()}
    assert leaders <= ids
    assert {record.evidence_id for record in selected[:len(leaders)]} == leaders
    assert len(selected) == len(ids) == min(20, 8 + 5 + memory_count * 5)
    assert all(request.max_results <= 5 for request in librarian.requests)


def test_original_history_fallback_keeps_query_limit_and_judge_context(monkeypatch):
    line = "Alice's present question " + "x" * 1200
    statements = (ReaderStatement(statement_id="reader-1", text="Alice's prior reading " + "y" * 1200),)
    fallback = statements[0].text
    librarian = PlanningLibrarian({fallback: [item(5, "Prior scene")]})
    librarian.candidate_paragraphs = lambda evidence: evidence
    planner = AsyncMock(return_value=plan())
    monkeypatch.setattr(evidence_strength, "plan_book_request", planner)
    judge = AsyncMock(return_value=uncertainty(()))
    asyncio.run(infer_spoiler_boundary(
        line, work_id=WORK_ID, book_version_id=VERSION_ID,
        memories=(), prior_reader_statements=statements, librarian=librarian, judge=judge,
    ))
    assert [request.query for request in librarian.requests] == [line, fallback]
    assert judge.await_args.args[0] == line
    assert judge.await_args.args[3] == statements
    planner.assert_awaited_once_with(line, prior_reader_statements=statements, search_target="reading_progress")


@pytest.mark.parametrize("focused", [False, True])
def test_long_boundary_search_preserves_stopping_event_after_query_limit(monkeypatch, focused):
    stop = "Alice has finished the croquet ground scene."
    line = "Alice " + "x" * 1994 + stop
    librarian = PlanningLibrarian({stop: [item(8, "Tail stopping event")]})
    monkeypatch.setattr(evidence_strength, "plan_book_request", AsyncMock(
        return_value=plan(line) if focused else plan(),
    ))
    judge = AsyncMock(return_value=uncertainty(()))
    asyncio.run(infer_spoiler_boundary(
        line, work_id=WORK_ID, book_version_id=VERSION_ID,
        memories=(), librarian=librarian, judge=judge,
    ))
    assert [request.query for request in librarian.requests] == [line[:2000], stop]
    assert "".join(request.query for request in librarian.requests) == line
    assert [record.chapter_number for record in judge.await_args.args[2]] == [8]
    assert judge.await_args.args[0] == line
