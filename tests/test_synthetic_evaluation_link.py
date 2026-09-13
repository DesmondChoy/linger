"""Evaluation links remain available independently of grades and export errors."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import Mock

import pytest
from pydantic_evals.reporting import EvaluationReport

from evals.synthetic_journals import evaluation_link
from evals.synthetic_journals.curation_replay import replay_curation_scenes
from tests.test_synthetic_curation_replay import _curation_models, _response_for

EVALUATION_URL = "https://logfire.example/project/evals/compare?experiment=trace-span"


def _status(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    captured = capsys.readouterr()
    assert not captured.out
    markers = [
        line.removeprefix(evaluation_link.LOGFIRE_MARKER)
        for line in captured.err.splitlines()
        if line.startswith(evaluation_link.LOGFIRE_MARKER)
    ]
    assert len(markers) == 1
    return json.loads(markers[0])


def test_emits_public_sdk_url_and_export_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = EvaluationReport(
        name="scenario", cases=[], trace_id="a" * 32, span_id="b" * 16
    )
    url = Mock(return_value=EVALUATION_URL)
    flush = Mock(return_value=True)
    monkeypatch.setattr(evaluation_link.logfire, "url_from_eval", url)
    monkeypatch.setattr(evaluation_link.logfire, "force_flush", flush)

    evaluation_link.emit_evaluation_link(report)

    assert _status(capsys) == {
        "url": EVALUATION_URL,
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "flushed": True,
    }
    url.assert_called_once_with(report)
    flush.assert_called_once_with()


def test_unavailable_url_and_incomplete_export_are_explicit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        evaluation_link.logfire, "url_from_eval", Mock(return_value=None)
    )
    monkeypatch.setattr(
        evaluation_link.logfire, "force_flush", Mock(return_value=False)
    )

    evaluation_link.emit_evaluation_link(EvaluationReport(name="scenario", cases=[]))

    assert _status(capsys) == {
        "url": None, "trace_id": None, "span_id": None, "flushed": False
    }


def test_url_error_still_attempts_flush_without_exposing_exception_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        evaluation_link.logfire,
        "url_from_eval",
        Mock(side_effect=ValueError("credential=must-not-be-printed")),
    )
    flush = Mock(return_value=True)
    monkeypatch.setattr(evaluation_link.logfire, "force_flush", flush)

    evaluation_link.emit_evaluation_link(EvaluationReport(name="scenario", cases=[]))

    assert _status(capsys) == {
        "url": None,
        "trace_id": None,
        "span_id": None,
        "flushed": True,
        "error": "url_from_eval: ValueError",
    }
    flush.assert_called_once_with()


def test_export_error_keeps_completed_replay_and_its_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    backstory, ground_truth, _ = _curation_models()
    monkeypatch.setattr(
        evaluation_link.logfire, "url_from_eval", Mock(return_value=EVALUATION_URL)
    )
    monkeypatch.setattr(
        evaluation_link.logfire,
        "force_flush",
        Mock(side_effect=RuntimeError("credential=must-not-be-printed")),
    )

    async def handler(batch):
        return _response_for(batch, ground_truth)

    run = asyncio.run(replay_curation_scenes(
        backstory,
        ground_truth,
        curation_handler=handler,
        configured_model="test:curation-model",
    ))

    assert len(run.scenes) == len(backstory.scenes)
    status = _status(capsys)
    assert status["url"] == EVALUATION_URL
    assert status["flushed"] is False
    assert status["error"] == "force_flush: RuntimeError"


def test_failed_case_emits_one_link_before_replay_raises(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    backstory, ground_truth, _ = _curation_models()
    reports = []

    def url(report):
        reports.append(report)
        return EVALUATION_URL

    monkeypatch.setattr(evaluation_link.logfire, "url_from_eval", url)
    monkeypatch.setattr(
        evaluation_link.logfire, "force_flush", Mock(return_value=True)
    )

    async def handler(batch):
        raise RuntimeError("the scenario handler failed")

    with pytest.raises(RuntimeError, match="synthetic curation cases failed"):
        asyncio.run(replay_curation_scenes(
            backstory,
            ground_truth,
            curation_handler=handler,
            configured_model="test:curation-model",
        ))

    status = _status(capsys)
    assert status["url"] == EVALUATION_URL
    assert status["flushed"] is True
    assert len(reports) == 1
    assert reports[0].failures
