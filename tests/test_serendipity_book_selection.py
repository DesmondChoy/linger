"""Serendipity selects requested books and evaluation observes raw retrieval scope."""

import asyncio
from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from apps.backend.contracts import BookScope, EvidenceBundle, EvidenceItem
from src.linger.agents.librarian.models import EvidenceStrengthDecision
from src.linger.agents.serendipity.agent import build_serendipity_agent
from src.linger.agents.serendipity.models import ConnectionDiscoveryInput, ConnectionScope
from src.linger.agents.serendipity.skills import CONNECTION_DISCOVERY
from src.linger.agents.serendipity.tools import SerendipityDependencies, search_librarian
from src.linger.contracts.session import ReaderStatement
from src.linger.corpus.registry import CORPORA
from src.linger.evaluation_transcript import bind_evaluation_transcript_sink
from src.linger.orchestration.book_evidence import retrieve_book_evidence


REQUESTED_WORKS = ("pg11", "pg23", "pg2397")
SCOPES = tuple(
    BookScope(
        work_id=registration.book.work_id,
        book_version_id=registration.book.book_version_id,
        chapter_max=1,
    )
    for registration in CORPORA.values()
)
LINE = "Compare " + ", ".join(CORPORA[work].book.title for work in REQUESTED_WORKS) + "."
PRIOR = ReaderStatement(statement_id="prior", text="Consider how learning changes self-understanding.")


def passage(scope):
    return EvidenceItem(
        evidence_id=f"{scope.work_id}-passage", work_id=scope.work_id,
        book_version_id=scope.book_version_id, chapter_id=f"{scope.work_id}-chapter-1",
        chapter=1, source_title=CORPORA[scope.work_id].book.title,
        location="Chapter 1", source_sha256="a" * 64, source_lines=(1, 2),
        excerpt=f"A controlled passage from {scope.work_id}.", relevance=.9,
    )


async def select_all(query, records, *, max_evidence_records):
    assert query == LINE
    return EvidenceStrengthDecision(
        evidence_strength="sufficient", strength_reason="The requested records are available.",
        relevant_evidence_ids=tuple(record.evidence_id for record in records),
    )


def dependencies(librarian, *, scopes=SCOPES, judge=select_all, cue=LINE):
    return SerendipityDependencies(
        task=ConnectionDiscoveryInput(
            cue=cue, intent="find_connection", presentation="direct",
            scope=ConnectionScope(allowed_sources=("book_corpus",), book_scopes=scopes),
        ),
        librarian=librarian, strength_judge=judge, prior_reader_statements=(PRIOR,),
    )


class EmptyLibrarian:
    def __init__(self):
        self.requests = []

    def retrieve_for_judgement(self, request):
        self.requests.append(request)
        return EvidenceBundle(items=[], retrieval_note="No matches.")


def test_agent_selects_three_named_books_from_five_available_titles():
    librarian = EmptyLibrarian()
    deps = dependencies(librarian)
    descriptions = []

    def model(messages, info):
        tool = next(tool for tool in info.function_tools if tool.name == "search_librarian")
        descriptions.append(tool.description)
        for scope in deps.task.scope.book_scopes:
            assert CORPORA[scope.work_id].book.title in tool.description
            assert scope.work_id in tool.description
        assert "work_ids" in tool.parameters_json_schema["properties"]
        assert "query" not in tool.parameters_json_schema["properties"]
        returned = any(
            isinstance(part, ToolReturnPart) and part.tool_name == "search_librarian"
            for message in messages for part in message.parts
        )
        if not returned:
            return ModelResponse(parts=[ToolCallPart("search_librarian", {
                "work_ids": list(REQUESTED_WORKS),
            })])
        output = next(tool for tool in info.output_tools if tool.name.endswith("ConnectionDecline"))
        return ModelResponse(parts=[ToolCallPart(output.name, {
            "reason": "no_permitted_evidence",
            "safe_next_step": "No passages were found for the requested comparison.",
        })])

    agent = build_serendipity_agent(FunctionModel(model))
    result = asyncio.run(agent.run(deps.task.model_dump_json(), deps=deps, **CONNECTION_DISCOVERY.run_options()))

    assert result.output.reason == "no_permitted_evidence"
    assert len(descriptions) == 2
    selected_scopes = [scope for scope in SCOPES if scope.work_id in REQUESTED_WORKS]
    # Each selected book is searched on its own, so books never share a candidate budget.
    assert [(request.book_scopes, request.query) for request in librarian.requests] == [
        ([scope], query) for scope in selected_scopes for query in (LINE, PRIOR.text)
    ]
    assert deps.task.scope.book_scopes == SCOPES
    assert deps.prior_reader_statements == (PRIOR,)


@pytest.mark.parametrize("work_ids", [None, (), ("pg11", "pg11"), ("ungranted-work",)])
def test_multibook_search_requires_a_unique_granted_selection(work_ids):
    librarian = EmptyLibrarian()
    deps = dependencies(librarian)
    arguments = {} if work_ids is None else {"work_ids": work_ids}

    with pytest.raises(ModelRetry, match="work_ids"):
        asyncio.run(search_librarian(SimpleNamespace(deps=deps), **arguments))

    assert librarian.requests == []
    assert deps.searches == []


def test_single_book_search_keeps_its_existing_no_argument_call():
    librarian = EmptyLibrarian()
    deps = dependencies(librarian, scopes=SCOPES[:1])

    result = asyncio.run(search_librarian(SimpleNamespace(deps=deps)))

    assert result.outcome == "no_evidence"
    assert [request.query for request in librarian.requests] == [LINE, PRIOR.text]
    assert all(request.book_scopes == list(SCOPES[:1]) for request in librarian.requests)


def test_title_free_discovery_can_explore_all_grants_and_return_only_relevant_support():
    cue = "Does anything I've read help me think about putting off a promise when something more fun comes up?"
    requests, events = [], []
    records = tuple(passage(scope) for scope in SCOPES)
    chosen = next(record for record in records if record.work_id == "pg500")

    class Librarian:
        def retrieve_for_judgement(self, request):
            requests.append(request)
            return EvidenceBundle(items=list(records), retrieval_note="Candidates across the permitted books.")

    async def judge(query, candidates, *, max_evidence_records):
        assert query == cue
        assert {record.work_id for record in candidates} == {scope.work_id for scope in SCOPES}
        return EvidenceStrengthDecision(
            evidence_strength="sufficient", strength_reason="One passage supports the particular connection.",
            relevant_evidence_ids=(chosen.evidence_id,),
        )

    deps = dependencies(Librarian(), judge=judge, cue=cue)
    with bind_evaluation_transcript_sink(SimpleNamespace(record_connection_event=events.append)):
        result = asyncio.run(search_librarian(
            SimpleNamespace(deps=deps), work_ids=tuple(scope.work_id for scope in SCOPES),
        ))

    assert [(request.book_scopes, request.query) for request in requests] == [
        ([scope], query) for scope in SCOPES for query in (cue, PRIOR.text)
    ]
    assert result.evidence == (chosen,)
    raw_results = [event for event in events if event.kind == "book_retrieval" and event.status == "ok"]
    assert all(set(event.retrieved_work_ids) == {scope.work_id for scope in SCOPES} for event in raw_results)


@pytest.mark.parametrize("purpose", ["connection_discovery", "evidence_retrieval"])
def test_private_book_events_record_raw_returns_before_scope_filtering_and_judging(purpose):
    events, queries = [], []
    selected = next(scope for scope in SCOPES if scope.work_id == "pg11")
    unexpected = next(scope for scope in SCOPES if scope.work_id == "pg500")
    accepted, rejected = passage(selected), passage(unexpected)

    class Librarian:
        def retrieve_for_judgement(self, request):
            queries.append(request.query)
            if purpose == "connection_discovery":
                assert events[-1].kind == "book_retrieval"
                assert events[-1].status == "attempted"
                assert events[-1].requested_work_ids == (selected.work_id,)
            return EvidenceBundle(items=[rejected, accepted], retrieval_note="Raw candidates.")

    async def judge(query, records, *, max_evidence_records):
        assert tuple(record.work_id for record in records) == (selected.work_id,)
        if purpose == "connection_discovery":
            assert events[-1].status == "ok"
            assert events[-1].retrieved_work_ids == (unexpected.work_id, selected.work_id)
        return await select_all(query, records, max_evidence_records=max_evidence_records)

    with bind_evaluation_transcript_sink(SimpleNamespace(record_connection_event=events.append)):
        result = asyncio.run(retrieve_book_evidence(
            LINE, book_scopes=(selected,), librarian=Librarian(),
            strength_judge=judge, prior_reader_statements=(PRIOR,), purpose=purpose,
        ))

    assert result.items == (accepted,)
    assert queries == [LINE, PRIOR.text]
    assert [event.status for event in events] == (
        ["attempted", "ok", "attempted", "ok"] if purpose == "connection_discovery" else []
    )
    assert all(event.evidence_json == () for event in events)


@pytest.mark.parametrize("unavailable", [False, True])
def test_private_book_attempts_survive_empty_or_failed_retrieval(unavailable):
    events = []

    class Librarian:
        def retrieve_for_judgement(self, request):
            if unavailable:
                raise OSError("Retrieval unavailable")
            return EvidenceBundle(items=[], retrieval_note="No matching records.")

    deps = dependencies(Librarian(), scopes=SCOPES[:1])
    with bind_evaluation_transcript_sink(SimpleNamespace(record_connection_event=events.append)):
        result = asyncio.run(search_librarian(SimpleNamespace(deps=deps)))

    retrieval_events = [event for event in events if event.kind == "book_retrieval"]
    assert [event.status for event in retrieval_events] == (
        ["attempted"] if unavailable else ["attempted", "ok", "attempted", "ok"]
    )
    assert all(event.requested_work_ids == (SCOPES[0].work_id,) for event in retrieval_events)
    assert all(event.retrieved_work_ids == () and event.evidence_json == () for event in retrieval_events)
    assert result.outcome == ("retrieval_unavailable" if unavailable else "no_evidence")
    assert deps.evidence == {}


def test_each_book_keeps_its_own_candidate_budget_in_a_multibook_search():
    from src.linger.orchestration.book_evidence import MAX_BOOK_CANDIDATES

    scopes = tuple(scope for scope in SCOPES if scope.work_id in ("pg11", "pg2397"))
    seen = []

    def many(scope, count):
        base = passage(scope)
        return [base.model_copy(update={"evidence_id": f"{scope.work_id}-{index}"}) for index in range(count)]

    class Librarian:
        def retrieve_for_judgement(self, request):
            # The first book floods every search; only a per-book budget keeps the second visible.
            return EvidenceBundle(items=many(request.book_scopes[0], 40), retrieval_note="Ranked candidates.")

    async def judge(query, candidates, *, max_evidence_records):
        seen.extend(candidates)
        return EvidenceStrengthDecision(evidence_strength="none", strength_reason="Budget check only.")

    asyncio.run(retrieve_book_evidence(LINE, book_scopes=scopes, librarian=Librarian(), strength_judge=judge))

    by_work = {scope.work_id: sum(record.work_id == scope.work_id for record in seen) for scope in scopes}
    assert by_work == {"pg11": MAX_BOOK_CANDIDATES, "pg2397": MAX_BOOK_CANDIDATES}


@pytest.mark.parametrize(("work_id", "query", "expected"), [
    ("pg2397", "Keller forgetting all about college at the lake",
     "forgetting all about college at the lake"),
    ("pg2397", "Helen Keller's first word", "first word"),
    ("pg2397", "Helen Keller", "Helen Keller"),
    ("pg23", "Narrative of the Life of Frederick Douglass learning to read",
     "Narrative of the Life of Frederick Douglass learning to read"),
    ("pg500", "Pinocchio promising the Fairy", "Pinocchio promising the Fairy"),
    ("unregistered", "Keller at the lake", "Keller at the lake"),
])
def test_book_queries_drop_only_the_searched_authors_name(work_id, query, expected):
    from src.linger.orchestration.book_evidence import _without_author

    assert _without_author(query, work_id) == expected

