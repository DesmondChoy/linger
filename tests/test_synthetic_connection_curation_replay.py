"""Combined replay preserves adopted identity and each Scene's authority."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from apps.backend import sessions
from evals.synthetic_journals.adoption import build_ground_truth_adoption
from evals.synthetic_journals.connection_contract import compile_connection_replay_plan
from evals.synthetic_journals.connection_curation_replay import replay_connection_curation_scenes
from evals.synthetic_journals.connection_replay import ConnectionSceneObservation
from evals.synthetic_journals.curation_replay import CurationSceneObservation, replay_curation_scene
from evals.synthetic_journals.models import ProposedGroundTruth, SyntheticBackstory
from src.linger.agents.serendipity.models import CandidateRubric, ConnectionCandidate, ConnectionProposal
from src.linger.evaluation_transcript import ConnectionEvaluationEvent, record_connection_event
from tests.test_synthetic_connection_replay import response, source_events
from tests.test_synthetic_connection_scenario import (
    CURATION,
    WEAK,
    connection_curation_documents,
    connection_documents,
)
from tests.test_synthetic_curation_replay import _curation_documents, _response_for

ROOT = Path(__file__).resolve().parents[1]


def _models(content, labels):
    backstory_bytes = json.dumps(content, sort_keys=True).encode()
    labels = labels | {"backstory_sha256": hashlib.sha256(backstory_bytes).hexdigest()}
    ground_truth_bytes = json.dumps(labels, sort_keys=True).encode()
    backstory = SyntheticBackstory.model_validate_json(backstory_bytes)
    ground_truth = ProposedGroundTruth.model_validate_json(ground_truth_bytes)
    adoption = build_ground_truth_adoption(
        ground_truth, ground_truth_bytes, reviewer_id="independent-test-human"
    )
    return backstory, ground_truth, adoption, backstory_bytes, ground_truth_bytes


def _scenario(*, reverse_objectives=False, interleave=False):
    content, labels = connection_curation_documents(ROOT)
    if reverse_objectives:
        content["objective_ids"].reverse()
    if interleave:
        curation, connection = content["scenes"][:5], content["scenes"][5:]
        content["scenes"] = [curation[0], connection[0], *curation[1:], connection[1]]
        for order, scene in enumerate(content["scenes"], start=1):
            scene["order"] = order
    return _models(content, labels)


def _connection_events(scene, memory_id):
    searches = source_events(scene, memory_id)
    evidence_ids = tuple(
        json.loads(event.evidence_json[0])["evidence_id"] for event in searches
    )
    if scene.proposals[0].connection.decision == "proposal":
        candidates = tuple(
            ConnectionCandidate(
                candidate_id=f"candidate-{index}",
                tentative_claim=claim,
                evidence_ids=evidence_ids if index == 1 else evidence_ids[-1:],
                shared_structure="A familiar image appears in different contexts.",
                meaningful_difference="The sources concern different experiences.",
                interpretation=claim,
                comparison_note="A controlled test comparison.",
                rubric=CandidateRubric(cue_fit=fit, reflective_value=value, safety="clear"),
            )
            for index, claim, fit, value in (
                (1, "A tentative literary parallel.", "direct", "high"),
                (2, "A possible contrast in interpretation.", "partial", "medium"),
            )
        )
        selected = ConnectionProposal(
            shortlist=candidates,
            selected_candidate_id="candidate-1",
            uncertainty="medium",
            presentation="direct",
            suggested_follow_up="Does the comparison help?",
            policy_flags=("contains_web_claim",),
        )
        discovery = ConnectionEvaluationEvent(
            kind="discovery", status="proposal", decision_json=selected.model_dump_json()
        )
        citations = evidence_ids
    else:
        discovery = ConnectionEvaluationEvent(kind="discovery", status="decline")
        citations = ()
    return (
        *searches,
        discovery,
        ConnectionEvaluationEvent(
            kind="release", status="released", release_source="muse_candidate",
            provenance_verdicts=("pass",), released_evidence_ids=citations,
        ),
    )


@pytest.mark.parametrize("reverse_objectives", [False, True])
@pytest.mark.parametrize("interleave", [False, True])
def test_replay_keeps_original_order_account_inputs_and_adoption(reverse_objectives, interleave):
    backstory, truth, adoption, backstory_bytes, truth_bytes = _scenario(
        reverse_objectives=reverse_objectives, interleave=interleave
    )
    original = tuple(item.model_dump_json() for item in (backstory, truth, adoption))
    plan = compile_connection_replay_plan(backstory, truth)
    connection_by_text = {scene.line.text: scene for scene in plan.scenes}
    curation_by_props = {
        scene.prop_ids: scene for scene in backstory.scenes if scene.objective_ids == (CURATION,)
    }
    order, accounts, roots, session_ids = [], set(), set(), []

    async def chat(request, service, account, *, initial_reading, public_source_urls, connection_book_scopes=None):
        scene = connection_by_text[request.message]
        records = service.list_active(account)
        assert len(records) == len(scene.props) == 1
        assert records[0].text == scene.props[0].source_text
        assert not service.capture_enabled(account)
        assert not sessions.history(request.session_id)
        assert initial_reading.work_id == scene.source_setup.book_scopes[0].work_id
        assert initial_reading.chapter_max == scene.source_setup.book_scopes[0].safe_ceiling_chapter
        assert public_source_urls == tuple(source.url for source in scene.source_setup.public_sources)
        assert "ground_truth" not in request.model_dump_json()
        order.append(scene.scene.scene_id)
        accounts.add(account.account_id)
        roots.add(service.root)
        session_ids.append(request.session_id)
        for event in _connection_events(scene, records[0].memory_id):
            record_connection_event(event)
        return response()

    async def curate(batch):
        scene = curation_by_props[tuple(memory.memory_id for memory in batch.memories)]
        expected = {prop.prop_id: prop.source_text for prop in backstory.props}
        assert all(memory.text == expected[memory.memory_id] for memory in batch.memories)
        assert set(batch.model_dump()) == {"account_scope", "memories"}
        order.append(scene.scene_id)
        accounts.add(batch.account_scope)
        return _response_for(batch, truth)

    result = asyncio.run(replay_connection_curation_scenes(
        backstory, truth, adoption=adoption, ground_truth_bytes=truth_bytes,
        backstory_bytes=backstory_bytes, chat_handler=chat, curation_handler=curate,
        configured_model="test:connection-curation",
    ))

    assert order == [scene.scene_id for scene in backstory.scenes]
    assert [scene.scene_id for scene in result.scenes] == order
    assert len(result.scenes) == 7
    assert len(accounts) == 1
    assert len(set(session_ids)) == 2
    assert all(not sessions.history(session_id) for session_id in session_ids)
    assert all(not root.exists() for root in roots)
    assert result.objective_ids == backstory.objective_ids
    assert result.dataset_version == adoption.adopted_ground_truth_identity
    assert result.backstory_sha256 == hashlib.sha256(backstory_bytes).hexdigest()
    assert result.proposed_ground_truth_sha256 == hashlib.sha256(truth_bytes).hexdigest()
    assert tuple(item.model_dump_json() for item in (backstory, truth, adoption)) == original
    curation = [scene for scene in result.scenes if isinstance(scene, CurationSceneObservation)]
    connections = [scene for scene in result.scenes if isinstance(scene, ConnectionSceneObservation)]
    assert len(curation) == 5 and len(connections) == 2
    assert all(scene.grade.hard_pass for scene in curation)
    assert all(scene.source_hashes_before == scene.source_hashes_after for scene in curation)
    assert all(scene.hard_gate_pass for scene in connections)
    assert all(scene.semantic_review_required for scene in connections)


@pytest.mark.parametrize("change", [
    "backstory_object", "truth_object", "backstory_bytes", "truth_bytes", "adoption",
])
def test_replay_rejects_changed_inputs_before_any_handler(change):
    backstory, truth, adoption, backstory_bytes, truth_bytes = _scenario()
    if change == "backstory_object":
        backstory = backstory.model_copy(update={
            "backstory": backstory.backstory.model_copy(update={"context": "Changed context."}),
        })
    elif change == "truth_object":
        truth = truth.model_copy(update={"proposals": ()})
    elif change == "backstory_bytes":
        backstory_bytes += b"\n"
    elif change == "truth_bytes":
        truth_bytes += b"\n"
    else:
        adoption = adoption.model_copy(update={"adopted_ground_truth_identity": "0" * 64})
    chat, curate = AsyncMock(), AsyncMock()
    with pytest.raises(ValueError):
        asyncio.run(replay_connection_curation_scenes(
            backstory, truth, adoption=adoption, ground_truth_bytes=truth_bytes,
            backstory_bytes=backstory_bytes, chat_handler=chat, curation_handler=curate,
            configured_model="test:connection-curation",
        ))
    chat.assert_not_awaited()
    curate.assert_not_awaited()


@pytest.mark.parametrize("selection", ["curation", "connection", "extra_objective"])
def test_replay_requires_exact_objective_pair_before_handlers(selection):
    if selection == "curation":
        content, labels, _ = _curation_documents()
    elif selection == "connection":
        content, labels = connection_documents(ROOT)
    else:
        content, labels = connection_curation_documents(ROOT)
        content["objective_ids"].append(WEAK)
        content["scenes"][-1]["objective_ids"].append(WEAK)
        _, connection_labels = connection_documents(ROOT)
        labels["proposals"].append(connection_labels["proposals"][2])
    backstory, truth, adoption, backstory_bytes, truth_bytes = _models(content, labels)
    chat, curate = AsyncMock(), AsyncMock()
    with pytest.raises(ValueError):
        asyncio.run(replay_connection_curation_scenes(
            backstory, truth, adoption=adoption, ground_truth_bytes=truth_bytes,
            backstory_bytes=backstory_bytes, chat_handler=chat, curation_handler=curate,
        ))
    chat.assert_not_awaited()
    curate.assert_not_awaited()


def test_invalid_later_curation_labels_prevent_earlier_connection_execution():
    content, labels = connection_curation_documents(ROOT)
    content["scenes"] = [content["scenes"][5], *content["scenes"][:5], content["scenes"][6]]
    for order, scene in enumerate(content["scenes"], start=1):
        scene["order"] = order
    labels["proposals"][0]["curation"]["primary_behavior"] = "paraphrased_duplicate"
    backstory, truth, adoption, backstory_bytes, truth_bytes = _models(content, labels)
    chat, curate = AsyncMock(), AsyncMock()
    with pytest.raises(ValueError):
        asyncio.run(replay_connection_curation_scenes(
            backstory, truth, adoption=adoption, ground_truth_bytes=truth_bytes,
            backstory_bytes=backstory_bytes, chat_handler=chat, curation_handler=curate,
        ))
    chat.assert_not_awaited()
    curate.assert_not_awaited()


@pytest.mark.parametrize("injected_handler", ["chat_handler", "curation_handler"])
def test_model_label_cannot_disguise_a_production_handler(injected_handler):
    backstory, truth, adoption, backstory_bytes, truth_bytes = _scenario()
    handler = AsyncMock()
    with pytest.raises(ValueError, match="both injected"):
        asyncio.run(replay_connection_curation_scenes(
            backstory, truth, adoption=adoption, ground_truth_bytes=truth_bytes,
            backstory_bytes=backstory_bytes, configured_model="test:connection-curation",
            **{injected_handler: handler},
        ))
    handler.assert_not_awaited()


@pytest.mark.parametrize("failing_kind", ["connection", "curation"])
def test_one_execution_failure_is_recorded_and_later_scenes_continue(failing_kind):
    from evals.synthetic_journals.connection_curation_replay import FailedSceneObservation

    backstory, truth, adoption, backstory_bytes, truth_bytes = _scenario(interleave=True)
    line_scenes = {line.text: line.scene_id for line in backstory.lines}
    curation_scenes = {
        scene.prop_ids: scene.scene_id for scene in backstory.scenes
        if scene.objective_ids == (CURATION,)
    }
    order, failures = [], []

    def visit(scene_id, kind):
        order.append(scene_id)
        if kind == failing_kind and not failures:
            failures.append(scene_id)
            raise RuntimeError("private test text must not enter execution metadata")

    async def chat(request, service, account, *, initial_reading, public_source_urls, connection_book_scopes=None):
        visit(line_scenes[request.message], "connection")
        return response()

    async def curate(batch):
        visit(curation_scenes[tuple(memory.memory_id for memory in batch.memories)], "curation")
        return _response_for(batch, truth)

    result = asyncio.run(replay_connection_curation_scenes(
        backstory, truth, adoption=adoption, ground_truth_bytes=truth_bytes,
        backstory_bytes=backstory_bytes, chat_handler=chat, curation_handler=curate,
        configured_model="test:connection-curation",
    ))

    assert order == [scene.scene_id for scene in backstory.scenes]
    assert [scene.scene_id for scene in result.scenes] == order
    failed = [scene for scene in result.scenes if isinstance(scene, FailedSceneObservation)]
    assert len(failed) == 1
    assert failed[0].scene_id == failures[0]
    expected_objective = next(scene.objective_ids[0] for scene in backstory.scenes
                              if scene.scene_id == failures[0])
    assert failed[0].objective_id == expected_objective
    assert failed[0].model_dump()["execution_error"] == {
        "code": "scene_execution_failed", "error_type": "RuntimeError",
    }
    assert failed[0].hard_gate_pass is False
    assert failed[0].hard_failures == ("execution_failure",)
    assert failed[0].ground_truth_result == "fails_hard_gates"
    assert "private test text" not in result.model_dump_json()
    assert not isinstance(result.scenes[-1], FailedSceneObservation)


def test_production_curation_dispatch_keeps_default_sculptor_and_provenance():
    from evals.synthetic_journals.connection_curation_replay import FailedSceneObservation

    backstory, truth, adoption, backstory_bytes, truth_bytes = _scenario()
    loop = AsyncMock(side_effect=RuntimeError("Stopped before production model calls"))
    with (
        patch("evals.synthetic_journals.connection_curation_replay.configure_synthetic_evaluation_telemetry"),
        patch("evals.synthetic_journals.connection_curation_replay.replay_curation_scene", wraps=replay_curation_scene) as scene_replay,
        patch("evals.synthetic_journals.curation_replay.run_curation_loop", loop),
    ):
        result = asyncio.run(replay_connection_curation_scenes(
            backstory, truth, adoption=adoption, ground_truth_bytes=truth_bytes,
            backstory_bytes=backstory_bytes, chat_handler=AsyncMock(return_value=response()),
        ))
    assert len(result.scenes) == 7
    assert sum(isinstance(scene, FailedSceneObservation) for scene in result.scenes) == 5
    assert scene_replay.await_count == loop.await_count == 5
    assert all(call.kwargs["handler"] is None for call in scene_replay.await_args_list)
    assert all("provenance" not in call.kwargs and "sculptor" not in call.kwargs
               for call in loop.await_args_list)


def test_cli_writes_every_scene_before_returning_execution_failure(tmp_path, monkeypatch):
    from evals.synthetic_journals import connection_curation_replay as combined

    backstory, truth, adoption, backstory_bytes, truth_bytes = _scenario(interleave=True)
    backstory_path = tmp_path / "backstory.json"
    truth_path = tmp_path / "ground-truth.json"
    adoption_path = tmp_path / "ground-truth-adoption.json"
    output = tmp_path / "results" / "run.json"
    backstory_path.write_bytes(backstory_bytes)
    truth_path.write_bytes(truth_bytes)
    adoption_path.write_text(adoption.model_dump_json(), encoding="utf-8")
    visits = []
    line_scenes = {line.text: line.scene_id for line in backstory.lines}
    curation_scenes = {
        scene.prop_ids: scene.scene_id for scene in backstory.scenes
        if scene.objective_ids == (CURATION,)
    }

    async def chat(request, service, account, *, initial_reading, public_source_urls, connection_book_scopes=None):
        visits.append(line_scenes[request.message])
        return response()

    async def curate(batch):
        visits.append(curation_scenes[tuple(memory.memory_id for memory in batch.memories)])
        if len(visits) == 1:
            raise RuntimeError("first Scene failed")
        return _response_for(batch, truth)

    async def injected_replay(actual_backstory, actual_truth, **kwargs):
        assert actual_backstory == backstory and actual_truth == truth
        assert kwargs["adoption"] == adoption
        assert kwargs["backstory_bytes"] == backstory_bytes
        assert kwargs["ground_truth_bytes"] == truth_bytes
        return await replay_connection_curation_scenes(
            actual_backstory, actual_truth, **kwargs, chat_handler=chat,
            curation_handler=curate, configured_model="test:connection-curation",
        )

    monkeypatch.setattr(combined, "replay_connection_curation_scenes", injected_replay)
    exit_code = combined.main([
        str(backstory_path), str(truth_path), "--adoption", str(adoption_path),
        "--output", str(output),
    ])

    assert exit_code == 1
    run = combined.ConnectionCurationEvaluationRun.model_validate_json(output.read_bytes())
    expected_order = [scene.scene_id for scene in backstory.scenes]
    assert visits == expected_order
    assert [scene.scene_id for scene in run.scenes] == expected_order
    assert len(run.scenes) == 7
    assert isinstance(run.scenes[0], combined.FailedSceneObservation)
    assert sum(isinstance(scene, combined.FailedSceneObservation) for scene in run.scenes) == 1
    assert run.dataset_version == adoption.adopted_ground_truth_identity
    assert backstory_path.read_bytes() == backstory_bytes
    assert truth_path.read_bytes() == truth_bytes


def test_standalone_connection_runner_rejects_combined_scenario_before_handler():
    from evals.synthetic_journals.connection_replay import replay_connection_scenes

    backstory, truth, adoption, backstory_bytes, truth_bytes = _scenario()
    chat = AsyncMock()
    with pytest.raises(ValueError, match="standalone connection replay"):
        asyncio.run(replay_connection_scenes(
            backstory, truth, adoption=adoption, ground_truth_bytes=truth_bytes,
            backstory_bytes=backstory_bytes, chat_handler=chat,
        ))
    chat.assert_not_awaited()
