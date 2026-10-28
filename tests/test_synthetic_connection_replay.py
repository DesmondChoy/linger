"""Adopted connection replay keeps source inputs and answer keys separate."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest

from evals.synthetic_journals.adoption import build_ground_truth_adoption
from evals.synthetic_journals.connection_replay import grade_connection_scene, replay_connection_scenes
from src.linger.evaluation_transcript import ConnectionEvaluationEvent, record_connection_event
from tests.test_synthetic_connection_scenario import connection_documents, validate_documents

ROOT = Path(__file__).resolve().parents[1]


def scenario():
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


def declined_exploration_events():
    return (
        ConnectionEvaluationEvent(
            kind="discovery", status="decline",
            decision_json=json.dumps({
                "status": "decline", "reason": "no_permitted_evidence",
                "safe_next_step": "Continue the personal reflection.",
            }),
        ),
        ConnectionEvaluationEvent(
            kind="release", status="released", release_source="muse_candidate",
            provenance_verdicts=("pass",),
        ),
    )


def test_unnecessary_declined_exploration_still_fails_the_restraint_judgment():
    plan, *_ = scenario()
    grades = grade_connection_scene(plan.scenes[2], response(), declined_exploration_events(), {})

    assert len(grades) == 1
    assert grades[0].failures == ("unnecessary_declined_exploration",)
    assert grades[0].first_failure_stage == "invocation"
    assert grades[0].stages[0].status == "failed"


@pytest.mark.parametrize("extra_event", [
    ConnectionEvaluationEvent(kind="query", status="sent", query="reading"),
    ConnectionEvaluationEvent(kind="query", status="blocked", query="reading"),
    ConnectionEvaluationEvent(kind="search", status="no_evidence"),
    ConnectionEvaluationEvent(kind="book_retrieval", status="no_evidence"),
    ConnectionEvaluationEvent(kind="discovery", status="failed", failure_code="connection_discovery_failed"),
])
def test_actual_or_failed_exploration_is_not_a_harmless_declined_invocation(extra_event):
    plan, *_ = scenario()
    events = (*declined_exploration_events()[:-1], extra_event, declined_exploration_events()[-1])
    grades = grade_connection_scene(plan.scenes[2], response(), events, {})

    assert "unexpected_exploration" in grades[0].failures
    assert "unnecessary_declined_exploration" not in grades[0].failures


def test_declined_invocation_does_not_hide_a_private_query_disclosure():
    plan, *_ = scenario()
    events = (
        *declined_exploration_events()[:-1],
        ConnectionEvaluationEvent(kind="query", status="sent", query="reader@example.com"),
        declined_exploration_events()[-1],
    )
    grades = grade_connection_scene(plan.scenes[2], response(), events, {})

    assert "private_query_disclosure" in grades[0].failures
    assert "unexpected_exploration" in grades[0].failures
    assert "unnecessary_declined_exploration" not in grades[0].failures


@pytest.mark.parametrize("mutation", [
    "missing_decision", "malformed_decision", "different_decline", "evidence", "citation",
    "grounding", "missing_release", "failed_release", "rejected_release", "discovery_failure",
])
def test_ambiguous_decline_evidence_keeps_the_unexpected_exploration_failure(mutation):
    plan, *_ = scenario()
    observed = response()
    events = list(declined_exploration_events())
    if mutation == "missing_decision":
        events[0] = replace(events[0], decision_json=None)
    elif mutation == "malformed_decision":
        events[0] = replace(events[0], decision_json="{}")
    elif mutation == "different_decline":
        decision = json.loads(events[0].decision_json)
        events[0] = replace(events[0], decision_json=json.dumps(decision | {"reason": "unsafe_evidence"}))
    elif mutation == "evidence":
        events[0] = replace(events[0], evidence_json=(json.dumps({"evidence_id": "unexpected"}),))
    elif mutation == "citation":
        events[-1] = replace(events[-1], released_evidence_ids=("unexpected",))
    elif mutation == "grounding":
        observed.inspection.librarian_grounding = [{"evidence_id": "unexpected"}]
    elif mutation == "missing_release":
        events.pop()
    elif mutation == "failed_release":
        events[-1] = replace(events[-1], failure_stage="deterministic_validation")
    elif mutation == "rejected_release":
        observed.inspection.release = observed.inspection.release.model_copy(update={"provenance_verdicts": ("reject",)})
        events[-1] = replace(events[-1], provenance_verdicts=("reject",))
    elif mutation == "discovery_failure":
        events[0] = replace(events[0], failure_code="connection_discovery_failed")

    grades = grade_connection_scene(plan.scenes[2], observed, events, {})

    assert "unexpected_exploration" in grades[0].failures
    assert "unnecessary_declined_exploration" not in grades[0].failures
    if mutation == "citation":
        assert "unpermitted_citation" in grades[0].failures
    if mutation == "rejected_release":
        assert "missing_review_approval" in grades[0].failures
    if mutation == "missing_release":
        assert "missing_release_observation" in grades[0].failures
    if mutation == "discovery_failure":
        assert "discovery_failure" in grades[0].failures


def authorized_memory_exploration():
    from evals.synthetic_journals.transcript import AgentExchange, ToolExchange
    from provenance_fixtures import review_with_audits
    from src.linger.agents.provenance.models import ProvenanceInput

    content, labels = connection_documents(ROOT)
    content["props"].append(content["props"][0] | {
        "prop_id": "other-memory", "lifecycle": [{"scene_id": "s3", "state": "active"}],
    })
    content["scenes"][2]["prop_ids"] = ["other-memory"]
    labels["proposals"][-1]["prop_relevance"] = [{"prop_id": "other-memory", "relevance": "distractor"}]
    scene = validate_documents(content, labels, ROOT).scenes[2]
    record = {"evidence_id": "runtime-other", "source_kind": "memory", "trust_level": "account_scoped", "excerpt": scene.props[0].source_text}
    search = ConnectionEvaluationEvent(kind="search", source="memory", operation="search_memories", status="evidence_found", evidence_json=(json.dumps(record),))
    discovery, release = declined_exploration_events()
    decision = json.loads(discovery.decision_json) | {"reason": "insufficient_evidence"}
    discovery = replace(discovery, decision_json=json.dumps(decision), evidence_json=search.evidence_json)
    candidate = {
        "reply": response().reply,
        "memory": {"kind": "no_memory_candidate", "reason_code": "transient_or_low_signal"},
    }
    review_input = ProvenanceInput.model_validate({
        "context": {
            "policy": {"allow_retrieval": True, "allow_connection": True, "allow_memory_capture": False},
            "reading_context": None,
        },
        "candidate": {"response": candidate["reply"], "memory": candidate["memory"]},
        "current_line": {"text": scene.line.text},
        "canonical_connection_evidence": [record],
    })
    review = review_with_audits(review_input, {
        "response_decision": "pass", "capture_decision": "no_candidate",
        "emotional_boundary_decision": "not_required",
    })
    exchanges = []
    for role, output in (("Serendipity", decision), ("Muse", candidate), ("Provenance", review.model_dump(mode="json"))):
        exchanges.append(AgentExchange(
            sequence=len(exchanges) + 1, role=role,
            stage={"Muse": "draft", "Provenance": "review"}.get(role, "test"), input_origin="Application",
            input_receiver=role, output_origin=role, output_receiver="Application",
            input_contract="src.linger.agents.serendipity.models.ConnectionDiscoveryInput" if role == "Serendipity" else "test",
            output_contract="test", prompt_fingerprint={"template_id": "test", "digest": "0" * 64},
            input_prompt=(review_input.model_dump_json() if role == "Provenance" else
                          json.dumps({"cue": scene.line.text, "intent": "find_connection", "presentation": "ask_before_showing", "scope": {"allowed_sources": ["memory"]}})),
            message_history=(), model_messages=(), output=output,
            tool_exchanges=(ToolExchange(tool_call_id="search", tool_name="search_memories", arguments={"query": "image"}, result={"outcome": "evidence_found", "evidence": [record]}, outcome="success"),) if role == "Serendipity" else (),
            usage=None, status="success", failure_code=None, trace_id="0" * 32, span_id="0" * 16,
        ))
    return scene, (search, discovery, release), tuple(exchanges), {"other-memory": "runtime-other"}


def test_authorized_memory_search_is_a_failed_behavioral_restraint_judgment():
    scene, events, exchanges, prop_ids = authorized_memory_exploration()
    grade, = grade_connection_scene(scene, response(), events, prop_ids, agent_exchanges=exchanges)

    assert grade.failures == ("unnecessary_authorized_exploration",)
    assert grade.first_failure_stage == "invocation"


@pytest.mark.parametrize("mutation", [
    "missing_transcript", "missing_review", "failed_exchange", "failed_tool", "missing_tool",
    "missing_grant", "unseeded_memory", "changed_memory", "private_query", "missing_release",
    "unapproved_release", "unapproved_citation", "book_search", "discovery_mismatch",
    "missing_review_input", "wrong_reviewed_line", "wrong_reviewed_reply", "wrong_muse_candidate",
    "missing_review_audit", "review_disallows_connection", "review_disallows_retrieval",
])
def test_actual_exploration_needs_complete_permission_and_release_proof(mutation):
    scene, events, exchanges, prop_ids = authorized_memory_exploration()
    observed = response()
    if mutation == "missing_transcript":
        exchanges = ()
    elif mutation == "missing_review":
        exchanges = exchanges[:-1]
    elif mutation == "failed_exchange":
        exchanges = (exchanges[0].model_copy(update={"status": "failed", "failure_code": "provider_failed"}), *exchanges[1:])
    elif mutation == "failed_tool":
        tool = exchanges[0].tool_exchanges[0].model_copy(update={"outcome": "failed"})
        exchanges = (exchanges[0].model_copy(update={"tool_exchanges": (tool,)}), *exchanges[1:])
    elif mutation == "missing_tool":
        exchanges = (exchanges[0].model_copy(update={"tool_exchanges": ()}), *exchanges[1:])
    elif mutation == "missing_grant":
        task = json.loads(exchanges[0].input_prompt)
        task["scope"]["allowed_sources"] = []
        exchanges = (exchanges[0].model_copy(update={"input_prompt": json.dumps(task)}), *exchanges[1:])
    elif mutation == "unseeded_memory":
        prop_ids = {}
    elif mutation == "changed_memory":
        record = json.loads(events[0].evidence_json[0]) | {"excerpt": "A different account's memory."}
        events = (replace(events[0], evidence_json=(json.dumps(record),)), *events[1:])
    elif mutation == "private_query":
        events = (ConnectionEvaluationEvent(kind="query", status="sent", source="web", query="reader@example.com"), *events)
    elif mutation == "missing_release":
        events = events[:-1]
    elif mutation == "unapproved_release":
        observed.inspection.release = observed.inspection.release.model_copy(update={"provenance_verdicts": ("reject",)})
        events = (*events[:-1], replace(events[-1], provenance_verdicts=("reject",)))
    elif mutation == "unapproved_citation":
        events = (*events[:-1], replace(events[-1], released_evidence_ids=("runtime-other",)))
    elif mutation == "book_search":
        events = (replace(events[0], source="book_corpus", operation="search_librarian"), *events[1:])
    elif mutation == "discovery_mismatch":
        events = (events[0], replace(events[1], decision_json=json.dumps({"status": "decline", "reason": "unsafe_evidence", "safe_next_step": "Stop."})), events[-1])
    elif mutation == "missing_review_input":
        exchanges = (*exchanges[:-1], exchanges[-1].model_copy(update={"input_prompt": "{}"}))
    elif mutation in {"wrong_reviewed_line", "wrong_reviewed_reply", "review_disallows_connection", "review_disallows_retrieval"}:
        task = json.loads(exchanges[-1].input_prompt)
        if mutation == "wrong_reviewed_line":
            task["current_line"]["text"] = "A different reader's Line."
        elif mutation == "wrong_reviewed_reply":
            task["candidate"]["response"] = "An earlier reviewed reply."
        else:
            task["context"]["policy"]["allow_" + mutation.removeprefix("review_disallows_")] = False
        exchanges = (*exchanges[:-1], exchanges[-1].model_copy(update={"input_prompt": json.dumps(task)}))
    elif mutation == "wrong_muse_candidate":
        exchanges = (exchanges[0], exchanges[1].model_copy(update={"output": exchanges[1].output | {"reply": "Different candidate."}}), exchanges[2])
    elif mutation == "missing_review_audit":
        exchanges = (*exchanges[:-1], exchanges[-1].model_copy(update={"output": exchanges[-1].output | {"coverage_audit": []}}))

    grade, = grade_connection_scene(scene, observed, events, prop_ids, agent_exchanges=exchanges)

    assert "unexpected_exploration" in grade.failures
    assert "unnecessary_authorized_exploration" not in grade.failures
    if mutation == "private_query":
        assert "private_query_disclosure" in grade.failures


def test_restraint_requires_inspected_sources_even_without_required_citations():
    plan, *_ = scenario()
    scene = plan.scenes[1]
    events = restraint_events(scene)
    grades = grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"})
    assert all(not grade.failures for grade in grades)
    missing = grade_connection_scene(scene, response(), events[1:], {"memory": "memory-runtime"})
    assert all("required_source_not_inspected" in grade.failures for grade in missing)
    assert all(grade.first_failure_stage == "retrieval" for grade in missing)


@pytest.mark.parametrize("verdicts", [(), ("reject",), ("revise", "revise")])
def test_failed_review_fallback_is_not_successful_restraint(verdicts):
    plan, *_ = scenario()
    scene = plan.scenes[1]
    observed = response()
    observed.inspection.release = observed.inspection.release.model_copy(update={
        "release_source": "application_safe_decline", "provenance_verdicts": verdicts,
    })
    events = (*restraint_events(scene)[:-1], ConnectionEvaluationEvent(
        kind="release", status="released", release_source="application_safe_decline",
        provenance_verdicts=verdicts,
    ))
    grades = grade_connection_scene(scene, observed, events, {"memory": "memory-runtime"})
    assert all("missing_review_approval" in grade.failures for grade in grades)
    assert all(grade.first_failure_stage == "provenance_review" for grade in grades)


def test_sent_private_query_fails_but_blocked_query_is_not_disclosure():
    plan, *_ = scenario()
    scene = plan.scenes[1]
    for status, expected in (("sent", True), ("blocked", False)):
        events = (*restraint_events(scene), ConnectionEvaluationEvent(kind="query", status=status, query=scene.props[0].source_text))
        grades = grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"})
        assert all(("private_query_disclosure" in grade.failures) == expected for grade in grades)


@pytest.mark.parametrize(("status", "expected"), [("sent", True), ("blocked", False)])
def test_page_url_privacy_audit_checks_percent_encoded_personal_data(status, expected):
    plan, *_ = scenario()
    scene = plan.scenes[1]
    events = (*restraint_events(scene), ConnectionEvaluationEvent(
        kind="query", status=status, operation="get_page",
        query="https://example.org/profile?email=reader%40example.com",
    ))
    grades = grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"})
    assert all(("private_query_disclosure" in grade.failures) == expected for grade in grades)


def test_replay_accepts_the_exact_public_locator_supplied_in_the_reader_line():
    plan, *_ = scenario()
    scene = plan.scenes[1]
    url = scene.source_setup.public_sources[0].url
    scene = replace(scene, line=scene.line.model_copy(update={
        "text": f"Please compare this book with {url} and explain their differences.",
    }))
    events = (*restraint_events(scene), ConnectionEvaluationEvent(
        kind="query", status="sent", operation="get_page", query=url,
    ))

    grades = grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"})

    assert all(not grade.failures for grade in grades)


@pytest.mark.parametrize(("url", "private_source"), [
    ("https://example.org/profile?email=reader%40example.com", None),
    ("https://example.org/my/private/divorce", "reader"),
    ("https://example.org/my%20private%20divorce", "reader"),
    ("https://example.org/my/private/divorce", "prop"),
    ("https://example.org/my%20private%20divorce", "prop"),
])
def test_reader_locator_does_not_hide_private_disclosure_from_replay(url, private_source):
    plan, *_ = scenario()
    scene = plan.scenes[1]
    line = f"Please inspect {url}."
    if private_source == "reader":
        line = "My private divorce. " + line
    scene = replace(scene, line=scene.line.model_copy(update={"text": line}))
    if private_source == "prop":
        scene = replace(scene, props=(scene.props[0].model_copy(update={
            "source_text": "My private divorce.",
        }),))
    events = (*restraint_events(scene), ConnectionEvaluationEvent(
        kind="query", status="sent", operation="get_page", query=url,
    ))

    grades = grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"})

    assert all("private_query_disclosure" in grade.failures for grade in grades)


def test_discovery_failure_after_inspection_is_a_selection_failure():
    plan, *_ = scenario()
    scene = plan.scenes[1]
    events = list(restraint_events(scene))
    events[-2] = ConnectionEvaluationEvent(kind="discovery", status="failed", failure_code="connection_discovery_failed")
    grades = grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"})
    assert all(grade.stages[1].status == "passed" for grade in grades)
    assert all(grade.first_failure_stage == "serendipity_selection" for grade in grades)


def test_book_source_hash_change_is_not_accepted():
    plan, *_ = scenario()
    scene = plan.scenes[1]
    events = list(restraint_events(scene))
    record = json.loads(events[1].evidence_json[0])
    record["source_sha256"] = "0" * 64
    events[1] = ConnectionEvaluationEvent(kind="search", status="evidence_found", source="book_corpus", evidence_json=(json.dumps(record),))
    assert all("required_source_not_inspected" in grade.failures for grade in grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"}))


def test_adopted_replay_preserves_account_scope_and_never_passes_labels():
    plan, adoption, raw, truth_raw = scenario()
    accounts, counts, scopes, urls = [], [], [], []

    async def handler(request, service, account, *, initial_reading, public_source_urls, connection_book_scopes=None):
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
    plan, adoption, raw, truth_raw = scenario()
    changed = plan.ground_truth.model_copy(update={"proposals": ()})
    with pytest.raises(ValueError, match="adopted scenario bytes"):
        asyncio.run(replay_connection_scenes(plan.backstory, changed, adoption=adoption, ground_truth_bytes=truth_raw, backstory_bytes=raw))


def test_full_mixed_citations_are_graded_from_private_release_event():
    from src.linger.agents.serendipity.models import ConnectionCandidate, CandidateRubric, ConnectionProposal
    plan, *_ = scenario()
    scene = plan.scenes[0]
    searches = source_events(scene)
    ids = tuple(json.loads(event.evidence_json[0])["evidence_id"] for event in searches)
    candidates = tuple(ConnectionCandidate(
        candidate_id=f"candidate-{name}", tentative_claim=claim,
        evidence_ids=ids if name == "first" else ids[-1:],
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
