"""Production-boundary replay tests for persona-neutral journal datasets."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.backend.config import get_settings
from apps.backend.schemas import (
    CaptureInspection,
    ChatRequest,
    ChatResponse,
    ReleaseInspection,
    TurnInspection,
)
from evals.synthetic_journals.contracts import (
    SyntheticJournalDataset,
    load_dataset,
)
from evals.synthetic_journals.replay import replay_dataset
from src.linger.agents.muse.models import (
    MemoryCandidate,
    MuseCandidate,
    NoMemoryCandidate,
)
from src.linger.agents.provenance.models import ProvenanceReview, RiskFinding
from src.linger.services.memory import AccountContext, MemoryPolicyService

get_settings.cache_clear()
with patch.dict(
    os.environ,
    {
        "LINGER_MODEL": "google:gemini-2.5-flash",
        "GOOGLE_API_KEY": "test-key",
    },
):
    from apps.backend import main

ROOT = Path(__file__).resolve().parents[1]
MAYA_V1 = ROOT / "data" / "synthetic-journals" / "datasets" / "maya-chen" / "v1"


def _frozen_maya() -> SyntheticJournalDataset:
    payload = load_dataset(MAYA_V1, require_frozen=False).model_dump(mode="json")
    payload["manifest"]["approval"] = {
        "status": "frozen",
        "reviewed_by": ["test-reviewer"],
        "reviewed_at": "2026-08-18T00:00:00+08:00",
        "notes": ["Ephemeral test approval; checked-in Maya remains a draft."],
    }
    for annotation in payload["annotations"]["entries"]:
        annotation["human_review"] = "approved"
    return SyntheticJournalDataset.model_validate(payload)


def _agent_result(output: object) -> SimpleNamespace:
    return SimpleNamespace(output=output, new_messages=lambda: [])


def test_frozen_dataset_replays_through_real_chat_capture_path() -> None:
    dataset = _frozen_maya()
    annotations = {
        annotation.entry_id: annotation for annotation in dataset.annotations.entries
    }
    entries_by_text = {
        entry.text: entry.entry_id for entry in dataset.journal_entries.entries
    }
    muse_inputs: list[dict[str, object]] = []
    histories: list[list[object]] = []

    async def muse_run(prompt: str, **kwargs: object) -> SimpleNamespace:
        payload = json.loads(prompt)
        muse_inputs.append(payload)
        histories.append(list(kwargs.get("message_history", [])))
        source = payload["muse_turn"]["user_message"]
        annotation = annotations[entries_by_text[source]]
        expected = annotation.hard_expectations.muse_nomination
        if expected.outcome == "candidate":
            span = expected.candidate_spans[0]
            memory = MemoryCandidate(
                kind="memory_candidate",
                text=span.text,
                start_codepoint=span.start_codepoint,
                end_codepoint=span.end_codepoint,
                reason_code=expected.reason_codes[0],
            )
        else:
            memory = NoMemoryCandidate(
                kind="no_memory_candidate",
                reason_code=expected.reason_codes[0],
            )
        return _agent_result(MuseCandidate(reply="A synthetic reviewed reply.", memory=memory))

    async def provenance_run(prompt: str, **_: object) -> SimpleNamespace:
        payload = json.loads(prompt)
        annotation = annotations[entries_by_text[payload["capture_source_text"]]]
        expected = annotation.hard_expectations.provenance_capture
        findings = tuple(
            RiskFinding(
                code=code,
                quote="synthetic candidate",
                explanation="Synthetic expected capture veto.",
            )
            for code in expected.reason_codes
        )
        return _agent_result(
            ProvenanceReview(
                findings=findings,
                response_decision="pass",
                capture_decision=expected.outcome,
            )
        )

    muse = AsyncMock()
    muse.run.side_effect = muse_run
    provenance = AsyncMock()
    provenance.run.side_effect = provenance_run
    with tempfile.TemporaryDirectory() as directory:
        service = MemoryPolicyService(Path(directory))
        with (
            patch.object(main, "muse_chat_agent", muse),
            patch.object(main, "provenance_agent", provenance),
        ):
            report = asyncio.run(
                replay_dataset(
                    dataset,
                    chat_handler=main.chat,
                    memory_service=service,
                )
            )
        active = service.list_active(
            AccountContext(f"synthetic-eval:{dataset.manifest.dataset_id}")
        )

    assert report.hard_pass, report.failures
    assert len(report.event_results) == len(dataset.journal_entries.entries)
    assert len(active) == 7
    expected_commits = {
        annotation.hard_expectations.muse_nomination.candidate_spans[0].text
        for annotation in dataset.annotations.entries
        if annotation.hard_expectations.memory_policy.outcome == "commit"
    }
    assert {record.text for record in active} == expected_commits
    assert all(history == [] for history in histories)
    assert {payload["muse_turn"]["user_message"] for payload in muse_inputs} == set(
        entries_by_text
    )
    serialized_inputs = json.dumps(muse_inputs)
    assert "hard_expectations" not in serialized_inputs
    assert "human_review" not in serialized_inputs
    assert "journal_profile_version" not in serialized_inputs


def test_manifest_controls_use_deterministic_memory_paths() -> None:
    payload = _frozen_maya().model_dump(mode="json")
    entries = payload["journal_entries"]["entries"]
    first_text = entries[0]["text"]
    second_text = entries[1]["text"]
    note_events = payload["manifest"]["replay"]["events"]
    payload["manifest"]["replay"]["capture_enabled"] = False
    payload["manifest"]["replay"]["events"] = [
        note_events[0],
        {
            "kind": "explicit_save",
            "event_id": "event-101",
            "entry_id": "entry-001",
            "span": {
                "start_codepoint": 0,
                "end_codepoint": len(first_text),
                "text": first_text,
            },
        },
        note_events[1],
        {
            "kind": "correct_memory",
            "event_id": "event-102",
            "target_event_id": "event-101",
            "entry_id": "entry-002",
            "span": {
                "start_codepoint": 0,
                "end_codepoint": len(second_text),
                "text": second_text,
            },
        },
        {
            "kind": "delete_memory",
            "event_id": "event-103",
            "target_event_id": "event-102",
        },
        *note_events[2:],
    ]
    for annotation in payload["annotations"]["entries"]:
        hard = annotation["hard_expectations"]
        hard["muse_nomination"] = {
            "outcome": "ambiguous",
            "reason_codes": ["nomination_policy_ambiguous"],
            "candidate_spans": [],
        }
        hard["provenance_capture"] = {
            "outcome": "ambiguous",
            "reason_codes": [],
        }
        hard["memory_policy"] = {"outcome": "ambiguous", "reason_code": None}
    dataset = SyntheticJournalDataset.model_validate(payload)
    requests: list[ChatRequest] = []

    async def no_capture_chat(
        request: ChatRequest,
        _: MemoryPolicyService,
        __: AccountContext,
    ) -> ChatResponse:
        requests.append(request)
        capture = CaptureInspection(
            nomination="no_candidate",
            provenance_decision="no_candidate",
            binding="not_applicable",
            storage="not_applicable",
            reason_code="not_applicable",
        )
        return ChatResponse(
            reply="Synthetic reply.",
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

    with tempfile.TemporaryDirectory() as directory:
        service = MemoryPolicyService(Path(directory))
        report = asyncio.run(
            replay_dataset(
                dataset,
                chat_handler=no_capture_chat,
                memory_service=service,
            )
        )

    assert report.hard_pass, report.failures
    assert report.final_active_memory_ids == ()
    assert [request.message for request in requests] == [
        entry.text for entry in dataset.journal_entries.entries
    ]
    assert len({request.session_id for request in requests}) == len(requests)


def test_replay_rejects_a_draft_dataset() -> None:
    draft = load_dataset(MAYA_V1, require_frozen=False)
    with pytest.raises(ValueError, match="human-reviewed"):
        asyncio.run(replay_dataset(draft))
