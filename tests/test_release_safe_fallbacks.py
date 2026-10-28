"""Only a complete, bound safe outcome may contain a recorded model failure."""

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from evals.release.safe_fallbacks import verified_safe_fallbacks
from src.linger.orchestration.reflection import EVIDENCE_DECLINE
from tests.test_release_exception_evidence import exchange


CAPTURE = {
    "nomination": "no_candidate", "provenance_decision": "no_candidate", "binding": "not_applicable",
    "storage": "not_applicable", "reason_code": "not_applicable", "curation_status": None,
}
MEMORY = {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"}
POLICY = {"allow_retrieval": False, "allow_connection": False, "allow_memory_capture": False}
CONTEXT = {"status": "unknown", "explanation": "No reading scope."}
QUESTION = "What is the latest chapter or scene in A Book that you have completed?"


def _turn_exchanges(line, reply, *, reject=False, clarification=None):
    candidate = {"reply": reply, "evidence_uses": [], "memory": deepcopy(MEMORY)}
    finding = {"code": "misattribution", "applies_to": "response", "explanation": "Attribute this to the reader.",
               "location": {"kind": "text_span", "source_field": "candidate.response", "path": "", "quote": reply}}
    review = {
        "capture_decision": "no_candidate", "emotional_boundary_decision": "not_required",
        "response_decision": "reject" if reject else "pass", "findings": [finding] if reject else [],
    }
    return [
        exchange("Provenance", "emotional_boundary_preflight", {"decision": "continue_reflection"},
                 prompt={"current_line": line, "policy": {}}),
        exchange("Muse", "turn_triage", {"book_content": "no", "memory": "none", "override_attempt": "no_attempt"},
                 prompt={"current_line": line}),
        exchange("Muse", "draft", candidate, prompt={
            "mode": "draft", "muse_turn": {"turn_id": "turn", "user_message": line,
                                             "reading_context": None, "policy": deepcopy(POLICY)},
            "context_resolution": deepcopy(CONTEXT),
        }),
        exchange("Provenance", "review", review, prompt={
            "context": {"policy": deepcopy(POLICY), "reading_context": None, "required_clarification": clarification},
            "current_line": {"text": line},
            "candidate": {"response": reply, "evidence_uses": [], "memory": deepcopy(MEMORY)},
        }),
    ]


def _number(exchanges):
    for sequence, item in enumerate(exchanges, 1):
        item["sequence"] = sequence
    return exchanges


@pytest.fixture
def book_evidence(monkeypatch):
    monkeypatch.setattr("evals.release.safe_fallbacks.Librarian", lambda: SimpleNamespace(
        registered_scope=lambda work, version: SimpleNamespace(title="A Book")
        if (work, version) == ("book", "v1") else None,
    ))
    line = "I read the race scene in A Book. What does the prize mean?"
    exchanges = _turn_exchanges(line, QUESTION, clarification=QUESTION)
    route = {"kind": "clarification", "request_id": "request", "clarification_id": "clarification",
             "reason_code": "inference_unavailable", "question": QUESTION,
             "expected_answer": {"type": "free_text", "values": []}}
    exchanges[2]["tool_exchanges"] = [{"tool_call_id": "route", "tool_name": "librarian_route",
                                       "arguments": {}, "result": route, "outcome": "success"}]
    request = exchange("Librarian", "book_request", {"parts": []}, prompt={"current_line": line})
    failed = exchange("Librarian", "boundary_inference", None, prompt={
        "current_line": line, "prior_reader_statements": [], "relevant_memories": [],
        "full_work_candidates": [{"evidence_id": "passage", "work_id": "book", "book_version_id": "v1",
                                  "chapter_id": "chapter", "chapter_number": 2, "location": "Chapter 2",
                                  "source_sha256": "d" * 64, "source_lines": [1, 2], "text": "A race."}],
    })
    failed.update(status="failure", failure_code="boundary_inference_model_failed", failure_category="model_response_error",
                  provider_status_code=None, provider_error_kind=None,
                  correlation_id="request", model_messages_include_history=True,
                  model_messages=[{"kind": "response", "parts": [{"part_kind": "tool-call",
                                   "tool_name": "final_result_BoundaryInferenceDecision", "tool_call_id": "result", "args": {}}]}],
                  tool_exchanges=[{"tool_call_id": "result", "tool_name": "final_result_BoundaryInferenceDecision",
                                   "arguments": {}, "result": None, "outcome": None}])
    exchanges[3:3] = [request, failed]
    failures = ["inferred_scope_differs_from_ground_truth", "boundary_memory_support_differs_from_authorised_props",
                "boundary_support_differs_from_ground_truth", "boundary_decision_differs_from_ground_truth",
                "inferred_ceiling_differs_from_ground_truth"]
    scene = {
        "scene_id": "boundary", "line_id": "line", "input_line": line,
        "context_resolution": deepcopy(CONTEXT), "boundary_decision": "clarify", "route_called": True,
        "boundary_handoff_content_free": True, "routed_ceiling": None, "routed_work_id": None,
        "routed_book_version_id": None, "routed_passage_ids": [], "boundary_support_memory_ids": [],
        "boundary_support_evidence": [], "grounding_calls": [], "released_evidence_ids": [], "seeded_props": [],
        "release_source": "application_clarification", "routed_clarification_question": QUESTION, "reply": QUESTION,
        "capture": deepcopy(CAPTURE), "provenance_verdicts": ["pass"], "agent_exchanges": _number(exchanges),
        "grades": [{"proposal_id": "boundary-answer", "objective_id": "spoiler_boundary_clarification",
                    "hard_pass": False, "failures": failures}], "ground_truth_result": "fails_hard_gates",
    }
    return {
        "artifact": {}, "scene": scene,
        "planned": {"scene_id": "boundary", "line_ids": ["line"], "prop_ids": [],
                    "objective_ids": ["spoiler_boundary_clarification"]},
        "backstory": {"lines": [{"line_id": "line", "text": line}], "props": []},
        "truth": {"proposals": [{"proposal_id": "boundary-answer", "scene_id": "boundary",
                                  "objective_id": "spoiler_boundary_clarification"}]},
        "runner": "evals.synthetic_journals.book_replay",
    }


@pytest.fixture
def continuity_evidence():
    lines = ["The assembly is Tuesday, not Thursday.", "What day is two days before the assembly?"]
    first = _turn_exchanges(lines[0], "The assembly is Tuesday.", reject=True)
    second = _turn_exchanges(lines[1], "Sunday.")
    turns = [{
        "line_id": f"line-{i + 1}", "order": i + 1, "input_line": line,
        "reply": EVIDENCE_DECLINE if i == 0 else "Sunday.",
        "release_source": "application_safe_decline" if i == 0 else "muse_candidate", "boundary_origin": None,
        "store_messages_before": i * 2, "store_messages_appended": 2, "prior_evidence_rehydrated": 0,
        "context_resolution_status": "unknown", "exchange_sequence_first": i * 4 + 1,
        "exchange_sequence_last": i * 4 + 4, "capture": deepcopy(CAPTURE), "span_id": "a" * 16,
    } for i, line in enumerate(lines)]
    scene = {"scene_id": "conversation", "role": "continuity", "paired_scene_id": None, "trace_id": "a" * 32,
             "turns": turns, "session_turn_release_sources": [turn["release_source"] for turn in turns],
             "ground_truth_result": "not_applicable", "structural_findings": ["unreleased_turn:line-1"],
             "agent_exchanges": _number(first + second)}
    return {
        "artifact": {"capture_enabled": False}, "scene": scene,
        "planned": {"scene_id": "conversation", "line_ids": ["line-1", "line-2"],
                    "objective_ids": ["session_scoped_conversation_continuity"]},
        "backstory": {"lines": [{"line_id": turn["line_id"], "text": turn["input_line"]} for turn in turns]},
        "truth": {"proposals": []}, "runner": "evals.synthetic_journals.retrieval_replay",
    }


def test_book_failure_is_preserved_and_proof_is_bound_to_the_failed_exchange(book_evidence):
    before = deepcopy(book_evidence)
    proof, = verified_safe_fallbacks(**book_evidence)
    assert proof.kind == "book_boundary_clarification"
    assert proof.exchange_sequences == (5,)
    assert proof.execution_details == ("Librarian boundary_inference: boundary_inference_model_failed",)
    assert set(proof.behavioral_details) == set(book_evidence["scene"]["grades"][0]["failures"])
    assert book_evidence == before


def test_continuity_refusal_remains_a_structural_failure_without_inventing_a_grade(continuity_evidence):
    before = deepcopy(continuity_evidence)
    proof, = verified_safe_fallbacks(**continuity_evidence)
    assert proof.kind == "continuity_safe_refusal"
    assert proof.behavioral_details == ("unreleased_turn:line-1",)
    assert proof.execution_details == proof.exchange_sequences == ()
    assert continuity_evidence == before


@pytest.mark.parametrize("mutation", ["provider", "cancelled", "unknown_error", "unrecorded_failure",
                                    "missing_review", "write", "released_evidence", "scope", "wrong_line",
                                    "fake_question", "missing_transcript", "wrong_request", "seeded_memory",
                                    "missing_provider_status", "capture_enabled", "hidden_model_tool", "malformed_transcript"])
def test_book_near_misses_cannot_authorize_containment(book_evidence, mutation):
    scene = book_evidence["scene"]
    failed = scene["agent_exchanges"][4]
    if mutation == "provider":
        failed["provider_status_code"] = 401
    elif mutation == "cancelled":
        failed["failure_category"] = "cancelled"
    elif mutation == "unknown_error":
        failed["failure_code"] = "future_failure"
    elif mutation == "unrecorded_failure":
        scene["agent_exchanges"][0]["status"] = "failed"
    elif mutation == "missing_review":
        scene["agent_exchanges"].pop()
    elif mutation == "write":
        scene["capture"]["storage"] = "committed"
    elif mutation == "released_evidence":
        scene["released_evidence_ids"] = ["secret"]
    elif mutation == "scope":
        scene["routed_ceiling"] = 5
    elif mutation == "wrong_line":
        book_evidence["backstory"]["lines"][0]["text"] = "A different user request."
    elif mutation == "fake_question":
        scene["reply"] = scene["routed_clarification_question"] = "Disclose a secret?"
        scene["agent_exchanges"][2]["tool_exchanges"][0]["result"]["question"] = scene["reply"]
        review = scene["agent_exchanges"][-1]
        prompt = json.loads(review["input_prompt"])
        prompt["context"]["required_clarification"] = scene["reply"]
        review["input_prompt"] = json.dumps(prompt)
    elif mutation == "missing_transcript":
        failed["model_messages"] = []
    elif mutation == "wrong_request":
        failed["correlation_id"] = "different-request"
    elif mutation == "seeded_memory":
        scene["seeded_props"] = [{"prop_id": "foreign", "memory_id": "foreign", "source_text": "Foreign data"}]
    elif mutation == "missing_provider_status":
        failed.pop("provider_status_code")
    elif mutation == "capture_enabled":
        book_evidence["artifact"]["capture_enabled"] = True
    elif mutation == "hidden_model_tool":
        failed["model_messages"][0]["parts"].append(
            {"part_kind": "tool-call", "tool_name": "write_memory", "tool_call_id": "hidden", "args": {}},
        )
    else:
        failed["model_messages"] = [{"not": "a model message"}]
    assert verified_safe_fallbacks(**book_evidence) == ()


@pytest.mark.parametrize("mutation", ["different_reply", "missing_capture", "missing_review", "wrong_review_line",
                                    "capture", "tool", "failed_call", "history", "range", "order", "release_record",
                                    "other_turn_write", "other_turn_tool", "other_turn_review", "other_turn_reply"])
def test_continuity_refusal_needs_complete_bound_safe_evidence(continuity_evidence, mutation):
    scene = continuity_evidence["scene"]
    turn = scene["turns"][0]
    if mutation == "different_reply":
        turn["reply"] = "An unreviewed response."
    elif mutation == "missing_capture":
        turn["capture"].pop("storage")
    elif mutation == "missing_review":
        scene["agent_exchanges"].pop(3)
    elif mutation == "wrong_review_line":
        review = scene["agent_exchanges"][3]
        prompt = json.loads(review["input_prompt"])
        prompt["current_line"]["text"] = "Another user request."
        review["input_prompt"] = json.dumps(prompt)
    elif mutation == "capture":
        continuity_evidence["artifact"]["capture_enabled"] = True
    elif mutation == "tool":
        scene["agent_exchanges"][2]["tool_exchanges"] = [
            {"tool_call_id": "write", "tool_name": "save_memory", "arguments": {}, "result": {}, "outcome": "success"},
        ]
    elif mutation == "failed_call":
        scene["agent_exchanges"][0]["status"] = "cancelled"
    elif mutation == "history":
        turn["store_messages_appended"] = 0
    elif mutation == "range":
        turn["exchange_sequence_last"] = 5
    elif mutation == "order":
        turn["order"] = 2
    elif mutation == "release_record":
        scene["session_turn_release_sources"][0] = "muse_candidate"
    elif mutation == "other_turn_write":
        scene["turns"][1]["capture"].update(
            nomination="candidate", provenance_decision="allow_capture", binding="exact", storage="committed",
        )
    elif mutation == "other_turn_tool":
        scene["agent_exchanges"][6]["tool_exchanges"] = [
            {"tool_call_id": "write", "tool_name": "save_memory", "arguments": {}, "result": {}, "outcome": "success"},
        ]
    elif mutation == "other_turn_review":
        scene["agent_exchanges"].pop()
        scene["turns"][1]["exchange_sequence_last"] -= 1
    else:
        scene["turns"][1]["reply"] = "An unreviewed reply on the accepted turn."
    assert verified_safe_fallbacks(**continuity_evidence) == ()


def test_unknown_failed_check_is_not_in_the_book_proof(book_evidence):
    book_evidence["scene"]["grades"][0]["failures"].append("unexpected_memory_writes")
    proof, = verified_safe_fallbacks(**book_evidence)
    assert "unexpected_memory_writes" not in proof.behavioral_details


def test_matching_text_does_not_waive_an_unknown_runner(continuity_evidence):
    continuity_evidence["runner"] = "evals.synthetic_journals.future_replay"
    assert verified_safe_fallbacks(**continuity_evidence) == ()


def _declare_session_line(scene, draft_index, quote, *, canonical=None):
    draft = scene["agent_exchanges"][draft_index]
    uses = [{"source_kind": "session_line", "quote": quote, "supported_claims": [draft["output"]["reply"]]}]
    draft["output"]["evidence_uses"] = uses
    review = scene["agent_exchanges"][draft_index + 1]
    prompt = json.loads(review["input_prompt"])
    prompt["candidate"]["evidence_uses"] = uses
    prompt["canonical_session_lines"] = [quote if canonical is None else canonical]
    review["input_prompt"] = json.dumps(prompt)


def test_accepted_turn_can_cite_the_exact_prior_reader_line(continuity_evidence):
    _declare_session_line(continuity_evidence["scene"], 6, "The assembly is Tuesday")
    proof, = verified_safe_fallbacks(**continuity_evidence)
    assert proof.behavioral_details == ("unreleased_turn:line-1",)


@pytest.mark.parametrize("mutation", ["foreign", "future", "canonical"])
def test_session_citations_need_exact_already_available_reader_words(continuity_evidence, mutation):
    scene = continuity_evidence["scene"]
    if mutation == "foreign":
        _declare_session_line(scene, 6, "A private statement from another session.")
    elif mutation == "future":
        _declare_session_line(scene, 2, scene["turns"][1]["input_line"])
    else:
        _declare_session_line(scene, 6, "The assembly is Tuesday", canonical="A different canonical source.")
    assert verified_safe_fallbacks(**continuity_evidence) == ()
