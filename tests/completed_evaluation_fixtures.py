"""Complete recorded task failures for release-policy regressions."""

from copy import deepcopy
import json

import pytest

from src.linger.orchestration.reflection import EVIDENCE_DECLINE
from tests.memory_injection_fixtures import exchange


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
def book_evidence():
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
