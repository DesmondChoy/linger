"""Adopted connection replay keeps source inputs and answer keys separate."""

import asyncio
import json
from pathlib import Path

import pytest

from evals.synthetic_journals.adoption import build_ground_truth_adoption
from evals.synthetic_journals.connection_replay import grade_connection_scene, replay_connection_scenes
from src.linger.evaluation_transcript import ConnectionEvaluationEvent, record_connection_event
from tests.test_synthetic_connection_package import connection_documents, validate_documents

ROOT = Path(__file__).resolve().parents[1]


def package():
    content, labels = connection_documents(ROOT)
    plan = validate_documents(content, labels, ROOT)
    backstory_bytes = json.dumps(content, sort_keys=True).encode()
    truth_bytes = json.dumps(labels).encode()
    adoption = build_ground_truth_adoption(plan.ground_truth, truth_bytes, reviewer_id="independent-test-human")
    return plan, adoption, backstory_bytes, truth_bytes


def source_events(scene, memory_id="memory-runtime"):
    book = next(iter(scene.evidence_by_id.values())).accepted_runtime_records[0]
    public = scene.source_setup.public_sources[0]
    records = (
        {"evidence_id": memory_id, "source_kind": "memory", "excerpt": scene.props[0].source_text, "trust_level": "account_scoped"},
        {"evidence_id": book.evidence_id, "work_id": book.work_id, "book_version_id": book.book_version_id, "chapter_id": book.chapter_id, "chapter": book.chapter_number, "location": book.location, "source_sha256": book.source_sha256, "source_lines": list(book.source_lines), "excerpt": book.text, "source_kind": "book_corpus"},
        {"evidence_id": public.url, "source_kind": "web", "title": public.title, "excerpt": public.text, "trust_level": "external"},
    )
    return tuple(ConnectionEvaluationEvent(kind="search", status="evidence_found", source=record["source_kind"], evidence_json=(json.dumps(record),)) for record in records)


def response():
    from tests.test_serendipity_evals import CrossSourceObjectiveStageTests
    return CrossSourceObjectiveStageTests()._response(serendipity_status="declined", librarian_status="declined", release_source="muse_candidate", failure_stage=None)


def restraint_events(scene):
    return (*source_events(scene), ConnectionEvaluationEvent(kind="discovery", status="decline"), ConnectionEvaluationEvent(kind="release", status="released", release_source="muse_candidate", provenance_verdicts=("pass",)))


def test_restraint_requires_inspected_sources_even_without_required_citations():
    plan, *_ = package()
    scene = plan.scenes[1]
    events = restraint_events(scene)
    grades = grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"})
    assert all(not grade.failures for grade in grades)
    missing = grade_connection_scene(scene, response(), events[1:], {"memory": "memory-runtime"})
    assert all("required_source_not_inspected" in grade.failures for grade in missing)
    assert all(grade.first_failure_stage == "retrieval" for grade in missing)


def test_sent_private_query_fails_but_blocked_query_is_not_disclosure():
    plan, *_ = package()
    scene = plan.scenes[1]
    for status, expected in (("sent", True), ("blocked", False)):
        events = (*restraint_events(scene), ConnectionEvaluationEvent(kind="query", status=status, query=scene.props[0].source_text))
        grades = grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"})
        assert all(("private_query_disclosure" in grade.failures) == expected for grade in grades)


def test_discovery_failure_after_inspection_is_a_selection_failure():
    plan, *_ = package()
    scene = plan.scenes[1]
    events = list(restraint_events(scene))
    events[-2] = ConnectionEvaluationEvent(kind="discovery", status="failed", failure_code="connection_discovery_failed")
    grades = grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"})
    assert all(grade.stages[1].status == "passed" for grade in grades)
    assert all(grade.first_failure_stage == "serendipity_selection" for grade in grades)


def test_book_source_hash_change_is_not_accepted():
    plan, *_ = package()
    scene = plan.scenes[1]
    events = list(restraint_events(scene))
    record = json.loads(events[1].evidence_json[0])
    record["source_sha256"] = "0" * 64
    events[1] = ConnectionEvaluationEvent(kind="search", status="evidence_found", source="book_corpus", evidence_json=(json.dumps(record),))
    assert all("required_source_not_inspected" in grade.failures for grade in grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"}))


def test_adopted_replay_preserves_account_scope_and_never_passes_labels():
    plan, adoption, raw, truth_raw = package()
    accounts, counts, scopes, urls = [], [], [], []

    async def handler(request, service, account, *, initial_reading, public_source_urls):
        accounts.append(account.account_id)
        counts.append(len(service.list_active(account)))
        scopes.append(initial_reading)
        urls.append(public_source_urls)
        assert request.message in {scene.line.text for scene in plan.scenes}
        assert "proposed" not in request.model_dump_json()
        record_connection_event(ConnectionEvaluationEvent(kind="release", status="released", release_source="muse_candidate", provenance_verdicts=("pass",)))
        return response()

    run = asyncio.run(replay_connection_scenes(plan.backstory, plan.ground_truth, adoption=adoption, ground_truth_bytes=truth_raw, backstory_bytes=raw, chat_handler=handler))
    assert len(set(accounts)) == 1
    assert counts == [1, 1, 0]
    assert scopes[0] == scopes[1] and scopes[2] is None
    assert urls[0] == urls[1] and urls[2] == ()
    assert len(run.scenes) == 3
    assert not run.scenes[0].hard_gate_pass
    assert run.scenes[-1].hard_gate_pass
    assert run.ground_truth_status == "adopted"


def test_changed_objects_cannot_reuse_adopted_bytes():
    plan, adoption, raw, truth_raw = package()
    changed = plan.ground_truth.model_copy(update={"proposals": ()})
    with pytest.raises(ValueError, match="adopted package bytes"):
        asyncio.run(replay_connection_scenes(plan.backstory, changed, adoption=adoption, ground_truth_bytes=truth_raw, backstory_bytes=raw))


def test_full_mixed_citations_are_graded_from_private_release_event():
    from src.linger.agents.serendipity.models import ConnectionCandidate, CandidateRubric, ConnectionProposal
    plan, *_ = package()
    scene = plan.scenes[0]
    searches = source_events(scene)
    ids = tuple(json.loads(event.evidence_json[0])["evidence_id"] for event in searches)
    candidates = tuple(ConnectionCandidate(
        candidate_id=f"candidate-{name}", tentative_claim=claim, evidence_ids=ids,
        shared_structure="Continuity through changes.", meaningful_difference="Different contexts.",
        interpretation=claim, comparison_note="Test comparison.",
        rubric=CandidateRubric(cue_fit=fit, reflective_value=value, safety="clear"),
    ) for name, claim, fit, value in (("first", "A tentative parallel.", "direct", "high"), ("second", "A second parallel.", "partial", "medium")))
    proposal = ConnectionProposal(shortlist=candidates, selected_candidate_id="candidate-first", uncertainty="medium", presentation="direct", suggested_follow_up="How does that feel?", policy_flags=("contains_web_claim",))
    events = (*searches, ConnectionEvaluationEvent(kind="discovery", status="proposal", decision_json=proposal.model_dump_json()), ConnectionEvaluationEvent(kind="release", status="released", release_source="muse_candidate", provenance_verdicts=("pass",), released_evidence_ids=ids))
    observed = response()
    # Public API deliberately retains only book handles for session re-resolution.
    observed.inspection.release = observed.inspection.release.model_copy(update={"released_evidence_ids": (ids[1],)})
    grades = grade_connection_scene(scene, observed, events, {"memory": "memory-runtime"})
    assert all(not grade.failures for grade in grades)
    assert all(grade.semantic_review_required for grade in grades)
