"""Independent event identification cannot borrow a proposed grant's rationale."""

import asyncio
from unittest.mock import AsyncMock, patch

from src.linger.agents.librarian.models import BoundaryInferenceDecision, BookRequestPlan
from src.linger.orchestration.boundary import infer_spoiler_boundary
from tests.boundary_fixtures import event_resolution, quoted_support
from tests.test_boundary_inference import FakeLibrarian, WORK_ID, VERSION_ID, memory


def candidate(line, memories, evidence, statements):
    selected = evidence[0].evidence_id
    return BoundaryInferenceDecision(
        outcome="candidate", work_id=WORK_ID, book_version_id=VERSION_ID,
        chapter_number=5, confidence=.99, authorization_basis="memory_supported",
        supporting_memory_ids=(memories[0].memory_id,),
        supporting_evidence=quoted_support(evidence, (selected,)),
        memory_assessments=({"memory_id": memories[0].memory_id,
            "status": "grounded_prior_knowledge", "evidence_ids": (selected,),
            "reason": "The prior event is grounded."},),
        event_resolution=event_resolution(line, evidence, (selected,)),
    )


def run_boundary(identifier, *, line="I've read on. Alice gets bigger again.", judge=None):
    async def propose(*args):
        return candidate(*args)

    with (
        patch("src.linger.orchestration.boundary.evidence_strength.plan_book_request",
              new=AsyncMock(return_value=BookRequestPlan(parts=()))),
        patch("src.linger.orchestration.boundary.identify_reader_event",
              new=identifier, create=True),
    ):
        return asyncio.run(infer_spoiler_boundary(
            line, work_id=WORK_ID, book_version_id=VERSION_ID,
            memories=(memory("prior", "Alice and the Caterpillar"),),
            librarian=FakeLibrarian(), judge=judge or propose,
        ))


def test_independent_unresolved_event_blocks_otherwise_valid_invented_grant():
    async def unresolved(*args):
        from src.linger.agents.librarian.models import BoundaryEventUnresolved
        return BoundaryEventUnresolved(outcome="unresolved", reason_code="conflicting_context",
                                       explanation="Several growth events fit; the reader did not mention a mushroom.")

    identifier = AsyncMock(side_effect=unresolved)
    result = run_boundary(identifier)
    assert result.kind == "uncertain"
    assert result.reason_code == "conflicting_context"
    assert result.candidate_chapter is None
    identifier.assert_awaited_once()


def test_matching_event_grants_without_leaking_gate_input_or_output():
    from src.linger.agents.librarian.models import BoundaryEventIdentified

    seen = []

    async def identify(task):
        seen.append(task)
        return BoundaryEventIdentified(
            outcome="identified", evidence_ids=(task.full_work_candidates[0].evidence_id,),
            reader_spans=(task.current_line,), explanation="Private stop identification.",
        )

    result = run_boundary(identify, line="I finished the Caterpillar's question about who Alice is.")
    assert result.kind == "candidate"
    assert result.max_chapter_inclusive == 5
    assert set(seen[0].model_dump()) == {"current_line", "prior_reader_statements", "full_work_candidates"}
    assert "Alice and the Caterpillar" not in seen[0].model_dump_json()
    assert "Private stop identification" not in result.model_dump_json()
    assert "PRIVATE_LATER_CHAPTER_TEXT" not in result.model_dump_json()


def test_independent_execution_failure_fails_closed_without_second_call():
    identifier = AsyncMock(side_effect=RuntimeError("provider incomplete output"))
    result = run_boundary(identifier)
    assert result.kind == "uncertain"
    assert result.reason_code == "inference_unavailable"
    assert result.supporting_locations == ()
    identifier.assert_awaited_once()


def test_independent_later_occurrence_cannot_raise_proposed_ceiling():
    from src.linger.agents.librarian.models import BoundaryEventIdentified

    async def identify(task):
        return BoundaryEventIdentified(
            outcome="identified", evidence_ids=(task.full_work_candidates[1].evidence_id,),
            reader_spans=(task.current_line,), explanation="The reader's event is later.",
        )

    result = run_boundary(identify)
    assert result.kind == "uncertain"
    assert result.reason_code == "conflicting_context"
    assert result.candidate_chapter is None


def test_uncertain_proposal_does_not_run_identification():
    from src.linger.agents.librarian.models import BoundaryUncertainDecision

    async def judge(line, memories, evidence, statements):
        return BoundaryUncertainDecision(
            outcome="uncertain", confidence=.5, reason_code="conflicting_context",
            memory_assessments=({"memory_id": memories[0].memory_id, "status": "not_supported",
                                 "evidence_ids": (), "reason": "Unresolved."},),
        )

    identifier = AsyncMock(side_effect=AssertionError("Must not run"))
    assert run_boundary(identifier, judge=judge).kind == "uncertain"
    identifier.assert_not_awaited()


def test_low_confidence_or_line_only_proposal_does_not_run_identification():
    for change in ({"confidence": .5}, {"authorization_basis": "line_only", "supporting_memory_ids": ()}):
        async def judge(*args):
            return candidate(*args).model_copy(update=change)

        identifier = AsyncMock(side_effect=AssertionError("Must not run"))
        assert run_boundary(identifier, judge=judge).kind == "uncertain"
        identifier.assert_not_awaited()


def test_same_chapter_different_windows_must_overlap_current_event_not_prior_memory():
    from src.linger.orchestration.boundary import _same_stopping_occurrence
    from tests.test_boundary_event_resolution import record

    prior = record("memory", 5).model_copy(update={"source_lines": (1, 20)})
    stop = record("stop", 5).model_copy(update={"source_lines": (40, 60)})
    same = stop.model_copy(update={"evidence_id": "overlap", "source_lines": (50, 70)})
    assert _same_stopping_occurrence((same,), (stop,), 5)
    assert not _same_stopping_occurrence((prior,), (stop,), 5)
    assert not _same_stopping_occurrence((same,), (prior,), 5)
    for changes in ({"work_id": "other"}, {"book_version_id": "other-v1"},
                    {"chapter_id": "other-section"}, {"source_sha256": "b" * 64},
                    {"chapter_number": 6}, {"source_lines": (61, 70)}):
        assert not _same_stopping_occurrence((same.model_copy(update=changes),), (stop,), 5)


def test_input_validation_rejects_forged_reader_and_evidence_references():
    from src.linger.agents.librarian.models import (
        BoundaryEventIdentified, LibrarianEventIdentificationInput, event_identification_errors,
    )
    from src.linger.contracts.session import ReaderStatement
    from tests.test_boundary_event_resolution import record

    task = LibrarianEventIdentificationInput(
        current_line="I finished the return after valuation.",
        prior_reader_statements=(ReaderStatement(statement_id="prior", text="I remember a literacy lesson."),),
        full_work_candidates=(record("return", 8),),
    )
    valid = BoundaryEventIdentified(outcome="identified", evidence_ids=("return",),
                                   reader_spans=(task.current_line,), explanation="The stated cause identifies the return.")
    assert event_identification_errors(valid, task) == []
    for changes in ({"evidence_ids": ("invented",)}, {"evidence_ids": ("return", "return")},
                    {"reader_spans": ("after imprisonment",)}, {"reader_spans": (" ",)},
                    {"reader_spans": (task.prior_reader_statements[0].text,)}):
        assert event_identification_errors(valid.model_copy(update=changes), task)


def test_selected_skill_repairs_anchors_and_records_independent_transcript():
    import json
    from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart, UserPromptPart
    from pydantic_ai.models.function import FunctionModel
    from src.linger.agents.librarian.agent import build_librarian_agent
    from src.linger.agents.librarian.models import LibrarianEventIdentificationInput
    from src.linger.agents.librarian.skills import EVENT_IDENTIFICATION, BOUNDARY_INFERENCE
    from src.linger.orchestration.boundary import identify_reader_event
    from tests.test_boundary_event_resolution import request

    original = request()
    task = LibrarianEventIdentificationInput(
        current_line=original.current_line, prior_reader_statements=original.prior_reader_statements,
        full_work_candidates=original.full_work_candidates,
    )
    calls = []

    def respond(messages, info):
        calls.append(messages)
        assert EVENT_IDENTIFICATION.instructions in info.instructions
        assert BOUNDARY_INFERENCE.instructions not in info.instructions
        payload = json.loads(next(part.content for message in messages for part in message.parts
                                  if isinstance(part, UserPromptPart)))
        assert set(payload) == {"current_line", "prior_reader_statements", "full_work_candidates"}
        if len(calls) == 2:
            assert any(isinstance(part, RetryPromptPart) for message in messages for part in message.parts)
        tool = next(tool for tool in info.output_tools if tool.name.endswith("BoundaryEventIdentified"))
        return ModelResponse(parts=[ToolCallPart(tool.name, {
            "outcome": "identified", "evidence_ids": ["current-event"],
            "reader_spans": ["invented distinguishing detail" if len(calls) == 1 else task.current_line],
            "explanation": "The stated cause distinguishes the current return.",
        })])

    result = asyncio.run(identify_reader_event(task, agent=build_librarian_agent(FunctionModel(respond))))
    assert result.evidence_ids == ("current-event",)
    assert len(calls) == 2


def test_event_identification_trace_uses_registered_fingerprint():
    from types import SimpleNamespace
    from src.linger.agents.librarian.models import BoundaryEventUnresolved, LibrarianEventIdentificationInput
    from src.linger.agents.librarian.boundary_prompt import EVENT_IDENTIFICATION_PROMPT_FINGERPRINT
    from src.linger.orchestration.boundary import identify_reader_event
    from evals.synthetic_journals.replay import RUNTIME_PROMPT_FINGERPRINTS

    task = LibrarianEventIdentificationInput(current_line="Where did I stop?", prior_reader_statements=(), full_work_candidates=())
    output = BoundaryEventUnresolved(outcome="unresolved", reason_code="insufficient_context", explanation="No event supplied.")
    with patch("src.linger.orchestration.boundary.run_agent_traced", new=AsyncMock(return_value=SimpleNamespace(output=output))) as traced:
        assert asyncio.run(identify_reader_event(task)) == output
    kwargs = traced.await_args.kwargs
    assert kwargs["stage"] == "event_identification"
    assert kwargs["prompt_digest"] == EVENT_IDENTIFICATION_PROMPT_FINGERPRINT.digest
    assert EVENT_IDENTIFICATION_PROMPT_FINGERPRINT in RUNTIME_PROMPT_FINGERPRINTS
    assert kwargs["failure_code"] == "event_identification_model_failed"


def test_real_shared_agent_records_both_calls_without_first_judgment_in_second_prompt():
    import json
    from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
    from pydantic_ai.models.function import FunctionModel
    from evals.synthetic_journals.transcript import SceneTranscriptRecorder
    from src.linger.agents.librarian.agent import librarian_agent
    from src.linger.agents.librarian.models import LibrarianBoundaryInferenceInput
    from src.linger.evaluation_transcript import bind_evaluation_transcript_sink

    line = "I finished the Caterpillar's question about who Alice is."

    def respond(messages, info):
        prompts = [part.content for message in messages for part in message.parts if isinstance(part, UserPromptPart)]
        assert len(prompts) == 1
        payload = json.loads(prompts[0])
        if "relevant_memories" in payload:
            task = LibrarianBoundaryInferenceInput.model_validate(payload)
            output = candidate(task.current_line, task.relevant_memories, task.full_work_candidates, task.prior_reader_statements)
            name = "BoundaryInferenceDecision"
        else:
            from src.linger.agents.librarian.models import BoundaryEventIdentified
            assert set(payload) == {"current_line", "prior_reader_statements", "full_work_candidates"}
            assert payload["current_line"] == line
            output = BoundaryEventIdentified(
                outcome="identified", evidence_ids=(payload["full_work_candidates"][0]["evidence_id"],),
                reader_spans=(line,), explanation="The stated question identifies this event.",
            )
            name = "BoundaryEventIdentified"
        tool = next(tool for tool in info.output_tools if tool.name.endswith(name))
        return ModelResponse(parts=[ToolCallPart(tool.name, output.model_dump(mode="json"))])

    recorder = SceneTranscriptRecorder()
    with (bind_evaluation_transcript_sink(recorder),
          librarian_agent.override(model=FunctionModel(respond)),
          patch("src.linger.orchestration.boundary.evidence_strength.plan_book_request",
                new=AsyncMock(return_value=BookRequestPlan(parts=())))):
        result = asyncio.run(infer_spoiler_boundary(
            line, work_id=WORK_ID, book_version_id=VERSION_ID,
            memories=(memory("prior", "Alice and the Caterpillar"),), librarian=FakeLibrarian(),
        ))
    assert result.kind == "candidate"
    assert [exchange.stage for exchange in recorder.exchanges] == ["boundary_inference", "event_identification"]
    assert [exchange.skill_id for exchange in recorder.exchanges] == ["librarian.boundary-inference", "librarian.event-identification"]
    assert all(exchange.status == "success" and exchange.model_messages for exchange in recorder.exchanges)
    assert recorder.exchanges[0].prompt_fingerprint != recorder.exchanges[1].prompt_fingerprint
    assert "relevant_memories" not in recorder.exchanges[1].input_prompt
    assert "event_resolution" not in recorder.exchanges[1].input_prompt


def test_failed_identification_records_its_own_repair_and_failure_category():
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.exceptions import UnexpectedModelBehavior
    from evals.synthetic_journals.transcript import SceneTranscriptRecorder
    from src.linger.agents.librarian.agent import build_librarian_agent
    from src.linger.agents.librarian.models import LibrarianEventIdentificationInput
    from src.linger.evaluation_transcript import bind_evaluation_transcript_sink
    from src.linger.orchestration.boundary import identify_reader_event
    import pytest

    calls = []

    def invalid(messages, info):
        calls.append(messages)
        tool = next(tool for tool in info.output_tools if tool.name.endswith("BoundaryEventIdentified"))
        return ModelResponse(parts=[ToolCallPart(tool.name, {
            "outcome": "identified", "evidence_ids": ["invented"],
            "reader_spans": ["Where did I stop?"], "explanation": "Invalid source reference.",
        })])

    task = LibrarianEventIdentificationInput(current_line="Where did I stop?", prior_reader_statements=(), full_work_candidates=())
    recorder = SceneTranscriptRecorder()
    with bind_evaluation_transcript_sink(recorder), pytest.raises(UnexpectedModelBehavior):
        asyncio.run(identify_reader_event(task, agent=build_librarian_agent(FunctionModel(invalid))))
    assert len(calls) == 2
    exchange, = recorder.exchanges
    assert exchange.stage == "event_identification"
    assert exchange.failure_code == "event_identification_model_failed"
    assert exchange.failure_category == "model_response_error"
    assert exchange.status == "failure"
    assert "retry-prompt" in str(exchange.model_messages)
