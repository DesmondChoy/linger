"""Book selection is graded separately from trusted reading permissions."""

import asyncio
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.synthetic_journals.connection_replay import grade_connection_scene, replay_connection_scene
from evals.synthetic_journals.validate_scenario import ScenarioValidationError
from src.linger.evaluation_transcript import ConnectionEvaluationEvent
from src.linger.services.memory import AccountContext, MemoryPolicyService
from tests.test_synthetic_connection_replay import response, restraint_events
from tests.test_synthetic_connection_scenario import connection_documents, validate_documents

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("pg11", "pg500", "pg2397")
FORBIDDEN = ("pga0100011", "pg23")


def multibook_documents():
    content, labels = connection_documents(ROOT)
    from src.linger.corpus.registry import CORPORA

    for setup in content["source_setups"]:
        setup["book_scopes"] = [setup.pop("book_scope")]
        for work_id, ceiling in (("pg500", 30), ("pg2397", 22), ("pga0100011", 10), ("pg23", 11)):
            setup["book_scopes"].append({
                "kind": "reader_confirmed", "work_id": work_id,
                "book_version_id": CORPORA[work_id].book.book_version_id,
                "safe_ceiling_chapter": ceiling,
            })
    for proposal in labels["proposals"]:
        expectation = proposal["connection"]
        if expectation["decision"] == "not_requested":
            continue
        expectation["required_evidence_ids"] = list(expectation["required_evidence_ids"])
        expectation["book_retrieval"] = {
            "required_work_ids": list(REQUIRED), "forbidden_work_ids": list(FORBIDDEN),
        }
        for work_id, relative, quote in (
            ("pg500", "chapters/30-chapter-30.md", "I want to keep my word."),
            ("pg2397", "sections/024-part-i-chapter-22.md", "There is joy in\nself-forgetfulness."),
        ):
            path = CORPORA[work_id].root / relative
            raw = path.read_bytes()
            text = raw.decode()
            start = text.index(quote)
            evidence_id = f"{proposal['proposal_id']}-{work_id}"
            proposal["evidence"].append({
                "kind": "repository_text", "evidence_id": evidence_id,
                "repository_path": str(path.relative_to(ROOT)),
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "start_codepoint": start, "end_codepoint": start + len(quote), "text": quote,
            })
            expectation["permitted_evidence_ids"].append(evidence_id)
            if expectation["decision"] == "proposal":
                expectation["required_evidence_ids"].append(evidence_id)
    return content, labels


def test_multiple_books_compile_with_natural_keller_chapter_and_separate_labels():
    content, labels = multibook_documents()
    plan = validate_documents(content, labels, ROOT)
    assert {scope.work_id for scope in plan.scenes[0].source_setup.book_scopes} == set(REQUIRED + FORBIDDEN)
    assert {record.work_id for span in plan.scenes[0].evidence_by_id.values() for record in span.accepted_runtime_records} == set(REQUIRED)
    keller = next(span for span in plan.scenes[0].evidence_by_id.values() if span.authored.chapter_id.endswith("sec024"))
    assert keller.chapter_number == 22
    assert "required_work_ids" not in plan.backstory.model_dump_json()
    assert "forbidden_work_ids" not in plan.backstory.model_dump_json()


def test_legacy_singular_scope_is_read_without_rewriting_adopted_bytes():
    content, labels = connection_documents(ROOT)
    raw = json.dumps(content, sort_keys=True).encode()
    plan = validate_documents(content, labels, ROOT)
    assert len(plan.scenes[0].source_setup.book_scopes) == 1
    assert hashlib.sha256(raw).hexdigest() == plan.ground_truth.backstory_sha256
    assert "book_scope" not in plan.scenes[0].source_setup.model_dump()


@pytest.mark.parametrize("mutation, message", [
    ("duplicate", "book work IDs"),
    ("ambiguous", "book_scope and book_scopes"),
    ("overlap", "disjoint"),
    ("unclassified", "cover available books"),
    ("no_evidence", "inspectable evidence for every required book"),
    ("ceiling", "exceeds trusted Scene ceiling"),
])
def test_multibook_contract_rejects_ambiguous_or_unprovable_selection(mutation, message):
    content, labels = multibook_documents()
    setup = content["source_setups"][0]
    expectation = labels["proposals"][0]["connection"]
    if mutation == "duplicate":
        setup["book_scopes"].append(setup["book_scopes"][0])
    elif mutation == "ambiguous":
        setup["book_scope"] = setup["book_scopes"][0]
    elif mutation == "overlap":
        expectation["book_retrieval"]["forbidden_work_ids"].append("pg11")
    elif mutation == "unclassified":
        expectation["book_retrieval"]["forbidden_work_ids"].pop()
    elif mutation == "no_evidence":
        expectation["book_retrieval"]["required_work_ids"].append("pg23")
        expectation["book_retrieval"]["forbidden_work_ids"].remove("pg23")
    elif mutation == "ceiling":
        setup["book_scopes"][2]["safe_ceiling_chapter"] = 21
    with pytest.raises((ValidationError, ScenarioValidationError), match=message):
        validate_documents(content, labels, ROOT)


def multibook_events(scene):
    events = list(restraint_events(scene))
    for span in scene.evidence_by_id.values():
        book = span.accepted_runtime_records[0]
        if book.work_id == "pg11":
            continue
        events.append(ConnectionEvaluationEvent(
            kind="search", status="evidence_found", source="book_corpus",
            evidence_json=(json.dumps({
                "evidence_id": book.evidence_id, "work_id": book.work_id,
                "book_version_id": book.book_version_id, "chapter_id": book.chapter_id,
                "chapter": book.chapter_number, "location": book.location,
                "source_sha256": book.source_sha256, "source_lines": list(book.source_lines),
                "excerpt": book.text, "source_kind": "book_corpus",
            }),),
        ))
    events.append(ConnectionEvaluationEvent(
        kind="book_retrieval", status="ok", requested_work_ids=REQUIRED, retrieved_work_ids=REQUIRED,
    ))
    return events


@pytest.mark.parametrize("mutation, failure", [
    ("none", None),
    ("empty_distractor_search", "forbidden_book_searched"),
    ("filtered_distractor_result", "forbidden_book_retrieved"),
    ("no_observation", "missing_book_retrieval_observation"),
    ("empty_required_result", "required_book_not_retrieved"),
])
def test_selection_grades_searches_and_raw_results_even_when_uncited(mutation, failure):
    scene = validate_documents(*multibook_documents(), ROOT).scenes[1]
    events = multibook_events(scene)
    if mutation == "empty_distractor_search":
        events.append(ConnectionEvaluationEvent(kind="book_retrieval", status="ok", requested_work_ids=("pg23",)))
    elif mutation == "filtered_distractor_result":
        events.append(ConnectionEvaluationEvent(kind="book_retrieval", status="ok", requested_work_ids=("pg11",), retrieved_work_ids=("pg23",)))
    elif mutation == "no_observation":
        events.pop()
    elif mutation == "empty_required_result":
        events[-1] = ConnectionEvaluationEvent(kind="book_retrieval", status="ok", requested_work_ids=REQUIRED, retrieved_work_ids=("pg11",))
    grades = grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"})
    if failure is None:
        assert all(not grade.failures for grade in grades)
    else:
        assert all(failure in grade.failures and grade.first_failure_stage == "retrieval" for grade in grades)


def test_unretrieved_distractor_memory_does_not_fail_book_selection():
    content, labels = multibook_documents()
    distractor = {
        **content["props"][0], "prop_id": "unrelated-memory",
        "source_text": "The kitchen tap was repaired yesterday.",
    }
    content["props"].append(distractor)
    for scene in content["scenes"][:2]:
        scene["prop_ids"].append(distractor["prop_id"])
    for proposal in labels["proposals"][:3]:
        proposal["prop_relevance"].append({"prop_id": distractor["prop_id"], "relevance": "distractor"})
        proposal["evidence"].append({
            "kind": "prop", "evidence_id": f"{proposal['proposal_id']}-distractor",
            "prop_id": distractor["prop_id"],
        })
    scene = validate_documents(content, labels, ROOT).scenes[1]
    grades = grade_connection_scene(scene, response(), multibook_events(scene), {
        "memory": "memory-runtime", "unrelated-memory": "distractor-runtime",
    })
    assert all(not grade.failures for grade in grades)


def test_replay_supplies_all_books_without_a_primary_or_selection_labels(tmp_path):
    scene = validate_documents(*multibook_documents(), ROOT).scenes[1]
    received = []

    async def handler(request, service, account, *, initial_reading, connection_book_scopes, public_source_urls):
        assert initial_reading is None
        assert {scope.work_id for scope in connection_book_scopes} == set(REQUIRED + FORBIDDEN)
        assert all(not {"required_work_ids", "forbidden_work_ids"} & set(scope.model_dump()) for scope in connection_book_scopes)
        assert request.message == scene.line.text
        received.append(connection_book_scopes)
        return response()

    asyncio.run(replay_connection_scene(
        scene, run_id="multibook-fixture", handler=handler,
        service=MemoryPolicyService(tmp_path), account=AccountContext("fixture"),
    ))
    assert len(received) == 1


def exploratory_documents(search_mode="exploratory"):
    content, labels = multibook_documents()
    for proposal in labels["proposals"]:
        expectation = proposal["connection"]
        if expectation["decision"] == "not_requested":
            continue
        expectation["book_retrieval"] = {
            "search_mode": search_mode,
            "required_work_ids": ["pg500"],
            "optional_work_ids": ["pg11", "pg2397"],
            "forbidden_work_ids": list(FORBIDDEN),
        }
        optional_ids = {
            item["evidence_id"] for item in proposal["evidence"]
            if item["kind"] == "repository_text" and not item["evidence_id"].endswith("-pg500")
        }
        expectation["required_evidence_ids"] = [
            identity for identity in expectation["required_evidence_ids"] if identity not in optional_ids
        ]
    return content, labels


def exploratory_events(scene, *, inspected=("pg500",), searched=REQUIRED + FORBIDDEN, retrieved=REQUIRED + FORBIDDEN):
    events = [
        event for event in multibook_events(scene)
        if event.kind != "book_retrieval" and (
            event.source != "book_corpus"
            or any(json.loads(record)["work_id"] in inspected for record in event.evidence_json)
        )
    ]
    return [*events, ConnectionEvaluationEvent(
        kind="book_retrieval", status="attempted", requested_work_ids=searched,
    ), ConnectionEvaluationEvent(
        kind="book_retrieval", status="ok", requested_work_ids=searched, retrieved_work_ids=retrieved,
    )]


def test_exploratory_search_can_inspect_all_grants_without_using_optional_or_forbidden_books():
    scene = validate_documents(*exploratory_documents(), ROOT).scenes[1]
    grades = grade_connection_scene(scene, response(), exploratory_events(scene), {"memory": "memory-runtime"})
    assert all(not grade.failures for grade in grades)


@pytest.mark.parametrize("optional", [(), ("pg11",), ("pg2397",), ("pg11", "pg2397")])
@pytest.mark.parametrize("search_mode", ["targeted", "exploratory"])
def test_optional_books_and_spans_are_not_required_inspection(search_mode, optional):
    scene = validate_documents(*exploratory_documents(search_mode), ROOT).scenes[1]
    observed = ("pg500", *optional)
    events = exploratory_events(scene, inspected=observed, searched=observed, retrieved=observed)
    grades = grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"})
    assert all(not grade.failures for grade in grades)


@pytest.mark.parametrize("missing, failure", [
    ("search", "required_book_not_searched"),
    ("retrieval", "required_book_not_retrieved"),
    ("exact_evidence", "required_source_not_inspected"),
])
def test_exploratory_search_still_requires_the_required_book(missing, failure):
    scene = validate_documents(*exploratory_documents(), ROOT).scenes[1]
    events = exploratory_events(
        scene,
        searched=("pg11",) if missing == "search" else REQUIRED + FORBIDDEN,
        retrieved=("pg11",) if missing == "retrieval" else REQUIRED + FORBIDDEN,
        inspected=() if missing == "exact_evidence" else ("pg500",),
    )
    grades = grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"})
    assert all(failure in grade.failures and grade.first_failure_stage == "retrieval" for grade in grades)


@pytest.mark.parametrize("search_mode", ["targeted", "exploratory"])
def test_uncited_forbidden_raw_and_surfaced_results_are_allowed_only_during_exploration(search_mode):
    scene = validate_documents(*exploratory_documents(search_mode), ROOT).scenes[1]
    events = exploratory_events(scene)
    events.append(ConnectionEvaluationEvent(
        kind="search", status="evidence_found", source="book_corpus",
        evidence_json=(json.dumps({
            "evidence_id": "uncited-distractor", "source_kind": "book_corpus", "work_id": "pg23",
        }),),
    ))
    grades = grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"})
    if search_mode == "exploratory":
        assert all(not grade.failures for grade in grades)
    else:
        assert all({"forbidden_book_searched", "forbidden_book_retrieved"} <= set(grade.failures) for grade in grades)


@pytest.mark.parametrize("field, failure", [
    ("requested_work_ids", "forbidden_book_searched"),
    ("retrieved_work_ids", "forbidden_book_retrieved"),
])
def test_exploration_still_rejects_books_outside_trusted_grants(field, failure):
    scene = validate_documents(*exploratory_documents(), ROOT).scenes[1]
    events = [*exploratory_events(scene), ConnectionEvaluationEvent(
        kind="book_retrieval", status="ok", **{field: ("ungranted-book",)},
    )]
    grades = grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"})
    assert all(failure in grade.failures for grade in grades)


def _selected_evidence_decision(evidence_ids):
    from src.linger.agents.serendipity.models import CandidateRubric, ConnectionCandidate, ConnectionProposal

    return ConnectionProposal(
        shortlist=tuple(ConnectionCandidate(
            candidate_id=f"candidate-{index}", tentative_claim=f"A tentative comparison {index}.",
            # A shortlist compares two connections, so the runner-up rests on its own record.
            evidence_ids=evidence_ids if index == 0 else (f"{evidence_ids[-1]}-alt",),
            shared_structure="A common question.",
            meaningful_difference="Different circumstances.", interpretation="A tentative reading.",
            comparison_note="Compare their support.",
            rubric=CandidateRubric(cue_fit="direct" if index == 0 else "partial", reflective_value="high", safety="clear"),
        ) for index in range(2)),
        selected_candidate_id="candidate-0", uncertainty="medium", presentation="direct",
        suggested_follow_up="How does that comparison feel?",
        policy_flags=("contains_web_claim",) if any(identity.startswith("https://") for identity in evidence_ids) else (),
    ).model_dump_json()


@pytest.mark.parametrize("use, failure", [
    ("selected", "unpermitted_selected_evidence"),
    ("cited", "unpermitted_citation"),
])
def test_exploration_never_authorizes_forbidden_final_evidence(use, failure):
    scene = validate_documents(*exploratory_documents(), ROOT).scenes[1]
    events = exploratory_events(scene)
    events = [
        replace(event, status="proposal", decision_json=_selected_evidence_decision(("forbidden-book-record",)))
        if use == "selected" and event.kind == "discovery"
        else replace(event, released_evidence_ids=("forbidden-book-record",))
        if use == "cited" and event.kind == "release"
        else event
        for event in events
    ]
    grades = grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"})
    assert all(failure in grade.failures for grade in grades)


def test_optional_books_need_no_citation_in_an_exploratory_proposal():
    scene = validate_documents(*exploratory_documents(), ROOT).scenes[0]
    events = exploratory_events(scene)
    ids = tuple(json.loads(record)["evidence_id"] for event in events for record in event.evidence_json)
    events = [
        replace(event, status="proposal", decision_json=_selected_evidence_decision(ids))
        if event.kind == "discovery"
        else replace(event, released_evidence_ids=ids)
        if event.kind == "release"
        else event
        for event in events
    ]
    grades = grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"})
    assert all(not grade.failures for grade in grades)


@pytest.mark.parametrize("mutation, message", [
    ("duplicate_optional", "unique"),
    ("optional_required_overlap", "disjoint"),
    ("optional_forbidden_overlap", "disjoint"),
    ("unclassified_optional", "cover available books"),
    ("missing_optional_permission", "inspectable evidence for every optional book"),
    ("missing_required_permission", "inspectable evidence for every required book"),
    ("optional_required_citation", "optional book evidence cannot require citation"),
    ("invalid_mode", "search_mode"),
])
def test_exploratory_contract_rejects_inconsistent_book_expectations(mutation, message):
    content, labels = exploratory_documents()
    proposal = labels["proposals"][0]
    expectation = proposal["connection"]
    selection = expectation["book_retrieval"]
    if mutation == "duplicate_optional":
        selection["optional_work_ids"].append("pg11")
    elif mutation == "optional_required_overlap":
        selection["optional_work_ids"].append("pg500")
    elif mutation == "optional_forbidden_overlap":
        selection["optional_work_ids"].append("pg23")
    elif mutation == "unclassified_optional":
        selection["optional_work_ids"].remove("pg2397")
    elif mutation in {"missing_optional_permission", "missing_required_permission"}:
        work_id = "pg2397" if mutation == "missing_optional_permission" else "pg500"
        evidence_id = next(item["evidence_id"] for item in proposal["evidence"] if item["evidence_id"].endswith(f"-{work_id}"))
        expectation["permitted_evidence_ids"].remove(evidence_id)
        expectation["required_evidence_ids"] = [identity for identity in expectation["required_evidence_ids"] if identity != evidence_id]
    elif mutation == "optional_required_citation":
        evidence_id = next(item["evidence_id"] for item in proposal["evidence"] if item["evidence_id"].endswith("-pg2397"))
        expectation["required_evidence_ids"].append(evidence_id)
    elif mutation == "invalid_mode":
        selection["search_mode"] = "unrestricted"
    with pytest.raises((ValidationError, ScenarioValidationError), match=message):
        validate_documents(content, labels, ROOT)


def test_exploratory_labels_do_not_change_runtime_inputs(tmp_path):
    scene = validate_documents(*exploratory_documents(), ROOT).scenes[1]
    received = []

    async def handler(request, service, account, *, initial_reading, connection_book_scopes, public_source_urls):
        assert initial_reading is None
        assert {scope.work_id for scope in connection_book_scopes} == set(REQUIRED + FORBIDDEN)
        serialized = request.model_dump_json() + json.dumps([scope.model_dump() for scope in connection_book_scopes])
        assert all(label not in serialized for label in ("search_mode", "required_work_ids", "optional_work_ids", "forbidden_work_ids"))
        received.append(request.message)
        return response()

    asyncio.run(replay_connection_scene(
        scene, run_id="exploratory-fixture", handler=handler,
        service=MemoryPolicyService(tmp_path), account=AccountContext("fixture"),
    ))
    assert received == [scene.line.text]
