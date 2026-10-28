"""Verify contained application outcomes without erasing their failed judgments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel
from pydantic_ai.messages import ModelMessagesTypeAdapter, ToolCallPart

from apps.backend.contracts import ContextResolution, MuseDraftInput, MuseRevisionInput
from apps.backend.librarian import Librarian
from apps.backend.schemas import CaptureInspection
from evals.synthetic_journals.continuity_replay import ContinuitySceneObservation, _structural_findings
from evals.synthetic_journals.transcript import AgentExchange
from src.linger.agents.librarian.models import (
    BookRequestPlan, LibrarianBookRequestInput, LibrarianBoundaryInferenceInput,
)
from src.linger.agents.muse.models import MuseCandidate, NoMemoryCandidate, SessionLineUse
from src.linger.agents.provenance.models import ProvenanceInput, ProvenanceReview
from src.linger.contracts.emotional import EmotionalBoundaryAssessment, EmotionalBoundaryInput
from src.linger.contracts.librarian import ClarificationRequest
from src.linger.contracts.triage import TurnNeeds, TurnTriageInput
from src.linger.orchestration.reflection import decline_text
from src.linger.orchestration.boundary import _clarification


@dataclass(frozen=True)
class SafeFallback:
    kind: str
    line_id: str
    reason: str
    behavioral_details: tuple[str, ...]
    execution_details: tuple[str, ...]
    exchange_sequences: tuple[int, ...]


_BOUNDARY_MISMATCHES = frozenset({
    "inferred_scope_differs_from_ground_truth",
    "boundary_memory_support_differs_from_authorised_props",
    "boundary_support_differs_from_ground_truth",
    "boundary_decision_differs_from_ground_truth",
    "inferred_ceiling_differs_from_ground_truth",
})
_PREFIX = (("Provenance", "emotional_boundary_preflight"), ("Muse", "turn_triage"))
_Model = TypeVar("_Model", bound=BaseModel)


def _parse(model: type[_Model], value: object) -> _Model:
    return model.model_validate_json(json.dumps(value))


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("Safe fallback evidence is incomplete or inconsistent.")


def _no_capture(raw: dict) -> None:
    _require(all(key in raw for key in (
        "nomination", "provenance_decision", "binding", "storage", "reason_code", "curation_status",
    )))
    capture = _parse(CaptureInspection, raw)
    _require(
        capture.nomination == capture.provenance_decision == "no_candidate"
        and capture.binding == capture.storage == capture.reason_code == "not_applicable"
        and capture.curation_status is None
    )


def _exchanges(raw: list) -> tuple[AgentExchange, ...]:
    _require(isinstance(raw, list) and bool(raw))
    required = {"sequence", "role", "stage", "status", "failure_code", "failure_category",
                "output", "input_prompt", "tool_exchanges", "model_messages"}
    _require(all(isinstance(item, dict) and required <= item.keys() for item in raw))
    exchanges = tuple(_parse(AgentExchange, item) for item in raw)
    _require([item.sequence for item in exchanges] == list(range(1, len(exchanges) + 1)))
    return exchanges


def _successful(exchange: AgentExchange) -> bool:
    return (
        exchange.status == "success" and exchange.output is not None
        and not exchange.failure_code and not exchange.failure_category
        and not exchange.provider_status_code and not exchange.provider_error_kind
    )


def _failed_calls_match(exchange: AgentExchange) -> bool:
    messages = ModelMessagesTypeAdapter.validate_json(json.dumps(exchange.model_messages))
    calls = [part for message in messages for part in message.parts if isinstance(part, ToolCallPart)]
    return bool(calls) and [(call.tool_call_id, call.tool_name, call.args_as_dict()) for call in calls] == [
        (tool.tool_call_id, tool.tool_name,
         json.loads(tool.arguments) if isinstance(tool.arguments, str) else tool.arguments)
        for tool in exchange.tool_exchanges
    ]


def _reviews(
    exchanges: tuple[AgentExchange, ...], line: str, *, session_lines: tuple[str, ...] = (),
) -> tuple[ProvenanceReview, ProvenanceInput]:
    """Bind successful preflight, candidates, and each review to this reader Line."""
    _require(tuple((item.role, item.stage) for item in exchanges[:2]) == _PREFIX)
    preflight, triage = exchanges[:2]
    _require(
        EmotionalBoundaryInput.model_validate_json(preflight.input_prompt).current_line == line
        and _parse(EmotionalBoundaryAssessment, preflight.output).decision == "continue_reflection"
        and TurnTriageInput.model_validate_json(triage.input_prompt).current_line == line
        and _parse(TurnNeeds, triage.output).override_attempt == "no_attempt"
    )
    candidate = previous_candidate = review = task = None
    for exchange in exchanges[2:]:
        if exchange.role == "Librarian":
            continue
        if exchange.role == "Muse":
            envelope = (MuseDraftInput if exchange.stage == "draft" else MuseRevisionInput).model_validate_json(
                exchange.input_prompt,
            )
            _require(
                envelope.muse_turn.user_message == line
                and envelope.muse_turn.policy.allow_memory_capture is False
                and envelope.context_resolution.status == "unknown"
                and not envelope.prior_evidence and not envelope.muse_turn.connection_book_scopes
                and envelope.muse_turn.reading_context is None
            )
            if exchange.stage == "revision":
                _require(review is not None and review.response_decision == "revise"
                         and envelope.review.findings == review.response_findings)
            previous_candidate, candidate = candidate, _parse(MuseCandidate, exchange.output)
            _require(all(isinstance(use, SessionLineUse) and any(use.quote in text for text in session_lines)
                         for use in candidate.evidence_uses)
                     and isinstance(candidate.memory, NoMemoryCandidate)
                     and candidate.memory.reason_code == "automatic_capture_disabled")
        else:
            _require(exchange.role == "Provenance" and exchange.stage == "review" and candidate is not None)
            task = ProvenanceInput.model_validate_json(exchange.input_prompt)
            _require(
                task.current_line.text == line and task.candidate.response == candidate.reply
                and task.candidate.evidence_uses == candidate.evidence_uses
                and task.candidate.memory == candidate.memory
                and task.canonical_session_lines == tuple(dict.fromkeys(use.quote for use in candidate.evidence_uses))
                and not task.canonical_book_evidence and not task.canonical_connection_evidence
                and not task.untrusted_tool_outcomes and not task.context.policy.allow_memory_capture
                and task.context.reading_context is None and task.context.passage_scope is None
                and not task.context.connection_book_scopes
                and task.context.override_attempt == "no_attempt"
            )
            if previous_candidate is None:
                _require(task.previous_response_review is None)
            else:
                previous = task.previous_response_review
                _require(previous is not None and review is not None
                         and previous.candidate.response == previous_candidate.reply
                         and previous.candidate.memory == previous_candidate.memory
                         and previous.candidate.evidence_uses == previous_candidate.evidence_uses
                         and previous.findings == review.response_findings)
            review = _parse(ProvenanceReview, exchange.output)
            _require(review.capture_decision == "no_candidate"
                     and review.emotional_boundary_decision == "not_required")
    _require(review is not None and task is not None)
    return review, task


def _continuity(artifact: dict, scene: dict, planned: dict, backstory: dict) -> tuple[SafeFallback, ...]:
    _require(artifact.get("capture_enabled") is False
             and planned["objective_ids"] == ["session_scoped_conversation_continuity"])
    observed = _parse(ContinuitySceneObservation, scene)
    _require(observed.role == "continuity" and observed.ground_truth_result == "not_applicable")
    exchanges = _exchanges(scene["agent_exchanges"])
    _require(all(_successful(item) and not item.tool_exchanges for item in exchanges))
    lines = {item["line_id"]: item for item in backstory["lines"]}
    _require([turn.line_id for turn in observed.turns] == planned["line_ids"]
             and [turn.order for turn in observed.turns] == list(range(1, len(observed.turns) + 1))
             and observed.session_turn_release_sources == tuple(turn.release_source for turn in observed.turns)
             and observed.structural_findings == _structural_findings(
                 observed.turns, observed.session_turn_release_sources, exchanges,
             ))
    results = []
    previous_last = 0
    for turn in observed.turns:
        _require(turn.input_line == lines[turn.line_id]["text"]
                 and turn.exchange_sequence_first == previous_last + 1
                 and turn.exchange_sequence_last is not None)
        previous_last = turn.exchange_sequence_last
        selected = tuple(item for item in exchanges
                         if turn.exchange_sequence_first <= item.sequence <= turn.exchange_sequence_last)
        _require(len(selected) == turn.exchange_sequence_last - turn.exchange_sequence_first + 1)
        _no_capture(scene["turns"][turn.order - 1]["capture"])
        stages = tuple((item.role, item.stage) for item in selected)
        base = _PREFIX + (("Muse", "draft"), ("Provenance", "review"))
        _require(stages in (base, base + (("Muse", "revision"), ("Provenance", "review"))))
        _require(all(not item.tool_exchanges for item in selected)
                 and turn.boundary_origin is None and turn.context_resolution_status == "unknown"
                 and turn.prior_evidence_rehydrated == 0)
        review, task = _reviews(
            selected, turn.input_line,
            session_lines=tuple(previous.input_line for previous in observed.turns[:turn.order]),
        )
        _require(task.context.required_clarification is None)
        if turn.release_source == "muse_candidate":
            _require(review.response_decision == "pass" and turn.reply == task.candidate.response)
            continue
        _require(turn.release_source == "application_safe_decline")
        _require((review.response_decision == "reject" or
                  (review.response_decision == "revise" and len(selected) == 6))
                 and turn.reply == decline_text(None, tuple(finding.code for finding in review.findings)))
        detail = f"unreleased_turn:{turn.line_id}"
        _require(detail in observed.structural_findings)
        results.append(SafeFallback(
            "continuity_safe_refusal", turn.line_id,
            "The complete reviewed turn ended in the fixed application refusal without tool use or capture; continuity usefulness still failed.",
            (detail,), (), (),
        ))
    _require(previous_last == len(exchanges))
    return tuple(results)


def _book(scene: dict, planned: dict, backstory: dict, truth: dict) -> tuple[SafeFallback, ...]:
    _require(planned["line_ids"] == [scene["line_id"]]
             and "spoiler_boundary_clarification" in planned["objective_ids"])
    line = next(item for item in backstory["lines"] if item["line_id"] == scene["line_id"])
    _require(scene["input_line"] == line["text"])
    context = _parse(ContextResolution, scene["context_resolution"])
    _require(context.status == "unknown" and context.work_id is None
             and context.book_version_id is None and context.chapter_max is None
             and context.boundary_source is None and not context.unit_ids)
    _require(scene["release_source"] == "application_clarification" and scene["boundary_decision"] == "clarify"
             and scene["route_called"] is True and scene["boundary_handoff_content_free"] is True)
    _require(all(scene[key] is None for key in ("routed_ceiling", "routed_work_id", "routed_book_version_id")))
    _require(all(scene[key] == [] for key in (
        "routed_passage_ids", "boundary_support_memory_ids", "boundary_support_evidence",
        "grounding_calls", "released_evidence_ids",
    )))
    _no_capture(scene["capture"])
    exchanges = _exchanges(scene["agent_exchanges"])
    _require(tuple((item.role, item.stage) for item in exchanges) == _PREFIX + (
        ("Muse", "draft"), ("Librarian", "book_request"),
        ("Librarian", "boundary_inference"), ("Provenance", "review"),
    ))
    failure = exchanges[4]
    _require({"provider_status_code", "provider_error_kind"} <= scene["agent_exchanges"][4].keys())
    _require(all(_successful(item) for item in exchanges if item is not failure))
    _require(
        failure.status == "failure" and failure.failure_code == "boundary_inference_model_failed"
        and failure.failure_category == "model_response_error" and failure.output is None
        and failure.provider_status_code is None and failure.provider_error_kind is None
        and bool(failure.correlation_id)
        and failure.model_messages_include_history and not failure.message_history
        and bool(failure.model_messages) and _failed_calls_match(failure)
        and bool(failure.tool_exchanges)
        and all(tool.tool_name in {"final_result_BoundaryInferenceDecision", "final_result_BoundaryUncertainDecision"}
                and tool.result is None and tool.outcome is None for tool in failure.tool_exchanges)
    )
    request = LibrarianBoundaryInferenceInput.model_validate_json(failure.input_prompt)
    _require(request.current_line == line["text"] and not request.prior_reader_statements
             and bool(request.full_work_candidates))
    props = {item["prop_id"]: item["source_text"] for item in backstory["props"]
             if item["prop_id"] in planned["prop_ids"]}
    seeded = scene["seeded_props"]
    _require(len(seeded) == len(props) and {item["prop_id"] for item in seeded} == set(props)
             and len({item["memory_id"] for item in seeded}) == len(seeded)
             and all(item["source_text"] == props[item["prop_id"]] for item in seeded))
    memory_text = {item["memory_id"]: item["source_text"] for item in seeded}
    _require(all(item.text == memory_text.get(item.memory_id) and not item.evidence_ids
                 for item in request.relevant_memories))
    record = request.full_work_candidates[0]
    scope = Librarian().registered_scope(record.work_id, record.book_version_id)
    _require(scope is not None and all(
        (item.work_id, item.book_version_id) == (record.work_id, record.book_version_id)
        for item in request.full_work_candidates
    ))
    book_request = LibrarianBookRequestInput.model_validate_json(exchanges[3].input_prompt)
    _parse(BookRequestPlan, exchanges[3].output)
    _require(book_request.current_line == line["text"] and not book_request.prior_reader_statements)
    _require(all(not item.tool_exchanges for item in exchanges if item not in (exchanges[2], failure)))
    _require(len(exchanges[2].tool_exchanges) == 1)
    route = exchanges[2].tool_exchanges[0]
    _require(route.tool_name == "librarian_route" and route.outcome == "success"
             and (json.loads(route.arguments) if isinstance(route.arguments, str) else route.arguments) == {})
    clarification = _parse(ClarificationRequest, route.result)
    _require(clarification.reason_code == "inference_unavailable"
             and clarification.request_id == failure.correlation_id
             and clarification.question == scene["routed_clarification_question"] == scene["reply"]
             and clarification.question == _clarification(scope))
    review, review_input = _reviews(exchanges, line["text"])
    _require(review.response_decision == "pass" and not review.findings
             and scene["provenance_verdicts"] == ["pass"]
             and review_input.context.required_clarification == clarification.question)
    proposals = {item["proposal_id"]: item for item in truth["proposals"] if item["scene_id"] == scene["scene_id"]}
    details = tuple(dict.fromkeys(
        detail for grade in scene["grades"]
        if proposals[grade["proposal_id"]]["objective_id"] == grade["objective_id"] == "spoiler_boundary_clarification"
        and grade["hard_pass"] is False
        for detail in grade["failures"] if detail in _BOUNDARY_MISMATCHES
    ))
    _require(bool(details) and scene["ground_truth_result"] == "fails_hard_gates")
    return (SafeFallback(
        "book_boundary_clarification", scene["line_id"],
        "Boundary model validation failed, but the reviewed application clarification granted no book scope, released no evidence, and saved nothing; the original judgment still fails.",
        details, ("Librarian boundary_inference: boundary_inference_model_failed",), (failure.sequence,),
    ),)


def verified_safe_fallbacks(
    artifact: dict, scene: dict, planned: dict, backstory: dict, truth: dict, runner: str,
) -> tuple[SafeFallback, ...]:
    """Missing or inconsistent affirmative evidence never grants a release exception."""
    try:
        _require(scene["scene_id"] == planned["scene_id"])
        name = runner.removeprefix("evals.synthetic_journals.")
        if name in {"retrieval_replay", "continuity_replay"} and scene.get("role") == "continuity":
            return _continuity(artifact, scene, planned, backstory)
        if name == "book_replay":
            _require(artifact.get("capture_enabled", False) is False)
            return _book(scene, planned, backstory, truth)
    except (KeyError, TypeError, ValueError, StopIteration, IndexError, AttributeError):
        pass
    return ()
