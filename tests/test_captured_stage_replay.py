"""Captured-stage diagnostics preserve authority and exercise current validators offline."""

import asyncio
import hashlib
import json

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest, ModelResponse, TextPart, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from evals.synthetic_journals import captured_stage_replay as replay
from evals.synthetic_journals.captured_stage_tasks import prepare_captured_task
from evals.synthetic_journals.transcript import AgentExchange
from src.linger.agents.contracts import PromptFingerprint
from src.linger.agents.librarian.agent import build_librarian_agent
from src.linger.agents.librarian.models import (
    BookRequestPlan, LibrarianBookRequestInput, LibrarianEvidenceStrengthInput,
)
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.agents.provenance.agent import build_provenance_agent
from src.linger.agents.provenance.review_context import review_input, reset_review_input, set_review_input
from tests.test_provenance_group_audit import LATER, checked, request as review_request
from tests.test_synthetic_connection_curation_replay import _scenario


def exchange(*, role="Librarian", stage="book_request", prompt=None, history=()):
    return AgentExchange(
        sequence=1, role=role, stage=stage, input_origin="Application", input_receiver=role,
        output_origin=role, output_receiver="Application", input_contract="CapturedInput",
        output_contract="CapturedOutput", prompt_fingerprint=PromptFingerprint(
            template_id="recorded-stage", digest="1" * 64,
        ), input_prompt=prompt or LibrarianBookRequestInput(current_line="Who questions Alice?").model_dump_json(),
        message_history=history, model_messages=(), output=None, tool_exchanges=(), usage=None,
        status="failure", failure_code="old_failure", trace_id="0" * 32, span_id="0" * 16,
    )


def source_files(tmp_path, item):
    story, truth, adoption, story_bytes, truth_bytes = _scenario()
    source = tmp_path / "original.json"
    source.write_text(json.dumps({
        "content_classification": "synthetic", "ground_truth_status": "adopted", "run_id": "original-run",
        "backstory_sha256": truth.backstory_sha256,
        "proposed_ground_truth_sha256": hashlib.sha256(truth_bytes).hexdigest(),
        "dataset_version": adoption.adopted_ground_truth_identity,
        "scenes": [{"scene_id": story.scenes[-1].scene_id, "agent_exchanges": [item.model_dump(mode="json")]}],
    }))
    paths = {"backstory": tmp_path / "backstory.json", "ground_truth": tmp_path / "truth.json",
             "adoption": tmp_path / "adoption.json"}
    paths["backstory"].write_bytes(story_bytes)
    paths["ground_truth"].write_bytes(truth_bytes)
    paths["adoption"].write_text(adoption.model_dump_json())
    snapshot = replay.load_captured_stage(source, scene_id=story.scenes[-1].scene_id, sequence=1)
    return source, snapshot, paths


def book_output(span="Who questions Alice?"):
    return {"parts": [{"context_spans": [], "reader_spans": [span], "purpose": "answer"}]}


def test_inspect_only_lists_stages_without_preparing_or_calling_models(tmp_path, monkeypatch, capsys):
    source, snapshot, _ = source_files(tmp_path, exchange())

    def forbidden(*args, **kwargs):
        raise AssertionError("Offline inspection must not construct or run a model")

    monkeypatch.setattr("evals.synthetic_journals.captured_stage_tasks.prepare_captured_task", forbidden)
    monkeypatch.setattr(replay, "configure_synthetic_evaluation_telemetry", forbidden)
    assert replay.main(["inspect", str(source)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["scene_id"] == snapshot.scene_id
    assert result["supported"] is True
    assert "Who questions Alice?" not in str(result)


def test_repetition_reuses_frozen_input_history_and_current_span_validator(tmp_path):
    history = tuple(ModelMessagesTypeAdapter.dump_python([
        ModelRequest(parts=[UserPromptPart("Earlier reader wording.")]),
        ModelResponse(parts=[TextPart("Earlier released response.")]),
    ], mode="json"))
    source, snapshot, paths = source_files(tmp_path, exchange(history=history))
    original = source.read_bytes()
    calls = []

    def respond(messages, info):
        calls.append(messages)
        output = book_output("invented reader wording") if len(calls) % 2 else book_output()
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    result = asyncio.run(replay.replay_captured_stage(
        snapshot, **paths, repetitions=2, agent=build_librarian_agent(FunctionModel(respond)),
    ))
    assert len(calls) == 4
    assert all(attempt.status == "accepted" for attempt in result.attempts)
    assert all(attempt.agent_exchanges[0].usage.requests == 2 for attempt in result.attempts)
    assert all(json.dumps(attempt.agent_exchanges[0].message_history) == json.dumps(history)
               for attempt in result.attempts)
    assert source.read_bytes() == original
    assert result.execution_mode == "injected_model"
    assert result.snapshot == snapshot
    assert result.current_prompt_fingerprint != snapshot.exchange().prompt_fingerprint
    assert result.execution_identity.model["model.provider"] == "function"
    assert len(result.execution_identity.code_sha256) == len(result.execution_identity.model_sha256) == 64
    assert all("adopted_ground_truth_identity" not in item.input_prompt
               for attempt in result.attempts for item in attempt.agent_exchanges)
    assert replay.CapturedStageReplayRun.model_validate_json(result.model_dump_json()).model_dump_json() == result.model_dump_json()


def test_exhausted_repairs_keep_all_model_attempts_and_continue_repetitions(tmp_path):
    _, snapshot, paths = source_files(tmp_path, exchange())

    def invalid(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, book_output("invented"))])

    result = asyncio.run(replay.replay_captured_stage(
        snapshot, **paths, repetitions=2, agent=build_librarian_agent(FunctionModel(invalid)),
    ))
    assert len(result.attempts) == 2
    for attempt in result.attempts:
        assert attempt.status == "failed"
        assert attempt.failure.category == "model_response_error"
        recorded = attempt.agent_exchanges[0]
        assert recorded.status == "failure" and recorded.model_messages_include_history
        assert sum(part["part_kind"] == "tool-call" for message in recorded.model_messages
                   for part in message["parts"]) == 2
        assert any(part["part_kind"] == "retry-prompt" for message in recorded.model_messages
                   for part in message["parts"])


def test_provenance_replay_rebinds_typed_input_and_restores_previous_binding(tmp_path):
    task = review_request(1)
    _, snapshot, paths = source_files(tmp_path, exchange(role="Provenance", stage="review", prompt=task.model_dump_json()))
    calls = []

    def respond(messages, info):
        assert review_input() == task
        calls.append(messages)
        output = checked(task, excerpts=["invented quote"] if len(calls) == 1 else [LATER])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output.model_dump(mode="json"))])

    previous = review_request(0)
    token = set_review_input(previous)
    try:
        result = asyncio.run(replay.replay_captured_stage(
            snapshot, **paths, agent=build_provenance_agent(FunctionModel(respond)),
        ))
        assert review_input() == previous
    finally:
        reset_review_input(token)
    assert result.attempts[0].status == "accepted"
    assert len(calls) == 2
    assert result.attempts[0].agent_exchanges[0].usage.requests == 2


@pytest.mark.parametrize("part_index", [0, 9])
def test_evidence_assessment_repairs_ids_and_bounds_requested_part_retries(tmp_path, part_index):
    evidence = EvidenceRecord(
        evidence_id="pg11-v01b38ea4-ch05-ln0964-0964", work_id="pg11", book_version_id="pg11-v01b38ea4",
        chapter_id="pg11-v01b38ea4-ch05", chapter_number=5, location="Chapter 5, source line 964",
        source_sha256="01b38ea4c710a84bc18d0bd41271a5a1a92b94e97b2812f4dece97d4a694725e",
        source_lines=(964, 964), text="Who are you? said the Caterpillar.",
    )
    task = LibrarianEvidenceStrengthInput(
        original_request=LibrarianBookRequestInput(current_line="Who questions Alice?"),
        request=BookRequestPlan.model_validate_json(json.dumps(book_output())), evidence=(evidence,),
    )
    _, snapshot, paths = source_files(tmp_path, exchange(stage="evidence_strength", prompt=task.model_dump_json()))
    calls = []

    def respond(messages, info):
        calls.append(messages)
        selected = "invented-id" if len(calls) == 1 else evidence.evidence_id
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "evidence_strength": "sufficient", "strength_reason": "The passage identifies the questioner.",
            "relevant_evidence_ids": [selected], "support": [{
                "evidence_id": selected, "part_index": part_index,
                "necessary_support": "The Caterpillar questions Alice.",
            }],
        })])

    result = asyncio.run(replay.replay_captured_stage(
        snapshot, **paths, agent=build_librarian_agent(FunctionModel(respond)),
    ))
    attempt = result.attempts[0]
    assert len(calls) == 2
    if part_index == 0:
        assert attempt.status == "accepted"
        assert attempt.output["relevant_evidence_ids"] == [evidence.evidence_id]
    else:
        assert attempt.failure.category == "model_response_error"
        assert attempt.agent_exchanges[0].status == "failure"


@pytest.mark.parametrize("mutation", ["adoption_mismatch", "source_changed", "snapshot_changed"])
def test_changed_source_or_adoption_stops_before_a_model_call(tmp_path, mutation):
    source, snapshot, paths = source_files(tmp_path, exchange())
    if mutation == "adoption_mismatch":
        snapshot = snapshot.model_copy(update={"dataset_version": "2" * 64})
    elif mutation == "source_changed":
        source.write_bytes(source.read_bytes() + b"\n")
    else:
        changed = snapshot.exchange().model_copy(update={"input_prompt": exchange().input_prompt + " "})
        encoded = changed.model_dump_json()
        snapshot = snapshot.model_copy(update={
            "exchange_json": encoded, "exchange_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
            "input_sha256": hashlib.sha256(changed.input_prompt.encode()).hexdigest(),
        })

    def forbidden(messages, info):
        raise AssertionError("Model must not run")

    with pytest.raises(ValueError):
        asyncio.run(replay.replay_captured_stage(
            snapshot, **paths, agent=build_librarian_agent(FunctionModel(forbidden)),
        ))


@pytest.mark.parametrize("code, expected", [
    ("insufficient_quota", "provider_quota"),
    ("credit_balance_exhausted", "provider_quota"),
    ("rate_limit_exceeded", "provider_rate_limit"),
    ("unknown-private-provider-code", "provider_http_error"),
])
def test_http_429_requires_known_provider_code_to_distinguish_quota_from_rate_limit(code, expected):
    async def fail():
        raise ModelHTTPError(429, "test-model", {"error": {"code": code, "message": "secret provider body"}})

    attempts = asyncio.run(replay.capture_stage_attempts(fail, repetitions=1))
    assert attempts[0].failure.category == expected
    assert attempts[0].failure.provider_status_code == 429
    assert "secret provider body" not in attempts[0].model_dump_json()
    assert "unknown-private-provider-code" not in attempts[0].model_dump_json()


def test_unsupported_tool_stage_rejected_before_loading_an_agent():
    with pytest.raises(ValueError, match="does not support"):
        prepare_captured_task(exchange(role="Serendipity", stage="source_gathering"))


def test_selector_requires_an_unambiguous_exchange(tmp_path):
    source, snapshot, _ = source_files(tmp_path, exchange())
    raw = json.loads(source.read_text())
    raw["scenes"][0]["agent_exchanges"].append(exchange().model_copy(update={"sequence": 2}).model_dump(mode="json"))
    source.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="matched 2"):
        replay.load_captured_stage(source, scene_id=snapshot.scene_id, role="Librarian")
    assert replay.load_captured_stage(source, scene_id=snapshot.scene_id, sequence=2).exchange().sequence == 2
