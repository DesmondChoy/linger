"""Tests for isolated capture-only Scene replay."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.backend import sessions
from apps.backend.config import get_settings
from apps.backend.schemas import (
    CaptureInspection,
    ChatRequest,
    ChatResponse,
    ReleaseInspection,
    TurnInspection,
)
from evals.synthetic_journals.models import CaptureCandidate
from evals.synthetic_journals.replay import main as replay_main
from evals.synthetic_journals.replay import replay_capture_scenes
from evals.synthetic_journals.validate_package import validate_package_files
from src.linger.agents.muse.models import (
    MemoryCandidate,
    MuseCandidate,
    NoMemoryCandidate,
)
from src.linger.agents.provenance.models import ProvenanceReview
from src.linger.services.memory import AccountContext, MemoryPolicyService

ROOT = Path(__file__).resolve().parents[1]
CONTENT_PATH = (
    ROOT
    / "synthetic-journal-evaluation"
    / "reviewed-automatic-memory-capture-content.json"
)
MANIFEST_PATH = (
    ROOT
    / "synthetic-journal-evaluation"
    / "reviewed-automatic-memory-capture-authoring-manifest.json"
)


def _result(output: object) -> SimpleNamespace:
    return SimpleNamespace(output=output, new_messages=lambda: [])


def _no_capture_response() -> ChatResponse:
    capture = CaptureInspection(
        nomination="no_candidate",
        provenance_decision="no_candidate",
        binding="not_applicable",
        storage="not_applicable",
        reason_code="not_applicable",
    )
    return ChatResponse(
        reply="A synthetic reviewed reply.",
        inspection=TurnInspection(
            muse_turn={},
            context_resolution={},
            traces=[],
            prompt="synthetic",
            release=ReleaseInspection(
                release_source="muse_candidate",
                provenance_verdicts=("pass",),
                finding_codes=(),
                revision_count=0,
                failure_stage=None,
                capture=capture,
            ),
        ),
    )


def test_replay_isolates_account_store_sessions_and_turns() -> None:
    content, _ = validate_package_files(CONTENT_PATH, MANIFEST_PATH)
    requests: list[ChatRequest] = []
    accounts: set[str] = set()
    store_roots: set[Path] = set()

    async def chat_handler(
        request: ChatRequest,
        service: MemoryPolicyService,
        account: AccountContext,
    ) -> ChatResponse:
        requests.append(request)
        accounts.add(account.account_id)
        store_roots.add(service.root)
        assert service.capture_enabled(account)
        return _no_capture_response()

    result = asyncio.run(
        replay_capture_scenes(content, chat_handler=chat_handler)
    )

    lines = {line.line_id: line for line in content.lines}
    expected_messages = [
        lines[scene.line_ids[0]].text
        for scene in sorted(content.scenes, key=lambda item: item.order)
    ]
    assert [request.message for request in requests] == expected_messages
    assert len({request.session_id for request in requests}) == len(content.scenes)
    assert len({request.turn_id for request in requests}) == len(content.scenes)
    assert accounts == {result.evaluation_account_id}
    assert len(store_roots) == 1
    assert all(not path.exists() for path in store_roots)
    assert all(not sessions.history(item.session_id) for item in requests)
    assert result.capture_enabled is True
    assert result.evaluation_account_id != content.backstory.evaluation_account_id
    assert result.final_active_memory_ids == ()

    serialized_requests = json.dumps(
        [request.model_dump(mode="json") for request in requests]
    )
    assert content.backstory.context not in serialized_requests
    assert "expected_outcomes" not in serialized_requests
    assert "prohibited_outcomes" not in serialized_requests


def test_replay_rejects_more_than_one_line_per_scene() -> None:
    content, _ = validate_package_files(CONTENT_PATH, MANIFEST_PATH)
    first_scene = content.scenes[0].model_copy(
        update={"line_ids": (content.lines[0].line_id, content.lines[1].line_id)}
    )
    invalid = content.model_copy(
        update={"scenes": (first_scene, *content.scenes[1:])}
    )

    with pytest.raises(ValueError, match="exactly one Line"):
        asyncio.run(
            replay_capture_scenes(
                invalid,
                chat_handler=lambda *args: None,  # type: ignore[arg-type]
            )
        )


def test_cli_returns_nonzero_for_an_invalid_package(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = replay_main(
        [
            str(tmp_path / "missing-content.json"),
            str(tmp_path / "missing-manifest.json"),
        ]
    )

    assert result == 1
    assert "EVALUATION_RUN_ERROR=" in capsys.readouterr().err


def test_replay_uses_production_capture_path_without_handing_off_labels() -> None:
    content, manifest = validate_package_files(CONTENT_PATH, MANIFEST_PATH)
    lines = {line.line_id: line for line in content.lines}
    scenes_by_text = {
        lines[scene.line_ids[0]].text: scene.scene_id for scene in content.scenes
    }
    proposals = {proposal.scene_id: proposal for proposal in manifest.proposals}
    muse_payloads: list[dict[str, object]] = []
    histories: list[list[object]] = []

    async def muse_run(prompt: str, **kwargs: object) -> SimpleNamespace:
        payload = json.loads(prompt)
        muse_payloads.append(payload)
        histories.append(list(kwargs.get("message_history", [])))
        source = payload["muse_turn"]["user_message"]
        proposal = proposals[scenes_by_text[source]]
        if isinstance(proposal.capture, CaptureCandidate):
            span = proposal.capture.span
            memory = MemoryCandidate(
                kind="memory_candidate",
                text=span.text,
                start_codepoint=span.start_codepoint,
                end_codepoint=span.end_codepoint,
                reason_code="durable_reflection",
            )
        else:
            memory = NoMemoryCandidate(
                kind="no_memory_candidate",
                reason_code="transient_or_low_signal",
            )
        return _result(
            MuseCandidate(reply="A synthetic reviewed reply.", memory=memory)
        )

    async def provenance_run(prompt: str, **_: object) -> SimpleNamespace:
        payload = json.loads(prompt)
        proposal = proposals[scenes_by_text[payload["capture_source_text"]]]
        decision = (
            "allow_capture"
            if isinstance(proposal.capture, CaptureCandidate)
            else "no_candidate"
        )
        return _result(
            ProvenanceReview(
                findings=(),
                response_decision="pass",
                capture_decision=decision,
            )
        )

    get_settings.cache_clear()
    try:
        with patch.dict(
            os.environ,
            {
                "LINGER_MODEL": "openai:gpt-5.6-luna",
                "OPENAI_API_KEY": "test-key",
            },
        ):
            from apps.backend import main

            muse = AsyncMock()
            muse.run.side_effect = muse_run
            provenance = AsyncMock()
            provenance.run.side_effect = provenance_run
            with (
                patch.object(main, "muse_chat_agent", muse),
                patch.object(main, "provenance_agent", provenance),
            ):
                result = asyncio.run(
                    replay_capture_scenes(
                        content,
                        chat_handler=main.chat,
                    )
                )
    finally:
        get_settings.cache_clear()

    committed = [scene for scene in result.scenes if scene.memory_id is not None]
    expected_span = next(
        proposal.capture.span
        for proposal in manifest.proposals
        if isinstance(proposal.capture, CaptureCandidate)
    )
    assert len(committed) == 1
    assert committed[0].stored_text == expected_span.text
    assert len(result.final_active_memory_ids) == 1
    assert all(history == [] for history in histories)

    serialized_payloads = json.dumps(muse_payloads)
    assert content.backstory.context not in serialized_payloads
    assert "expected_outcomes" not in serialized_payloads
    assert "prohibited_outcomes" not in serialized_payloads
