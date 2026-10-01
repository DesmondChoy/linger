"""Real gate reports must remain consumable by the final publication guard."""

import importlib.util
from pathlib import Path

import pytest

from tests.test_release_gate import (
    IMAGE, SHA, _provider, _run, behavioral_repo, release_repo,
)


SPEC = importlib.util.spec_from_file_location(
    "release_publication_candidate", Path(__file__).resolve().parents[1] / ".github/scripts/release_candidate.py",
)
candidate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(candidate)


def authorize(report, *, live_enabled="true", approvals=None):
    decision = report["publication"]
    return candidate.publication_authorization(
        report, sha=SHA, image_id=IMAGE, route=decision["route"],
        live_enabled=live_enabled, auto_enabled=str(decision["auto_publish_enabled"]).lower(),
        threshold=decision["threshold"], configuration_sha="c" * 40,
        approvals=approvals if approvals is not None else [],
    )


@pytest.mark.parametrize("behavioral", [False, True])
@pytest.mark.parametrize("automatic", [False, True])
def test_actual_gate_report_authorizes_only_its_recorded_route(request, tmp_path, monkeypatch, behavioral, automatic):
    repo = request.getfixturevalue("behavioral_repo" if behavioral else "release_repo")
    _provider(monkeypatch, repo[-1])
    report = _run(repo, tmp_path / "output", repetitions=2,
                  auto_publish_enabled=automatic, auto_publish_threshold="60")
    assert report["status"] == ("review_required" if behavioral else "passed")
    assert report["publication"]["route"] == ("automatic" if automatic else "manual")
    if behavioral:
        assert report["totals"]["scenes_ungraded"] == 2
        assert report["totals"]["judgments_failed"] == 2
    if not automatic:
        with pytest.raises(ValueError, match="approval"):
            authorize(report)
    approvals = [] if automatic else [{"state": "approved", "environments": [{"name": "linger-release"}]}]
    record = authorize(report, approvals=approvals)
    assert record["publication"] == report["publication"]
    assert record["human_approvals"] == approvals
    with pytest.raises(ValueError, match="disabled"):
        authorize(report, live_enabled="false", approvals=approvals)


def test_real_perfect_score_at_exact_threshold_still_requires_review(release_repo, tmp_path, monkeypatch):
    _provider(monkeypatch, release_repo[-1])
    report = _run(release_repo, tmp_path / "output", auto_publish_enabled=True, auto_publish_threshold="100")
    assert report["publication"]["route"] == "manual"
    with pytest.raises(ValueError, match="approval"):
        authorize(report)


def test_real_gate_safety_failure_cannot_authorize_publication(release_repo, tmp_path, monkeypatch):
    release_repo[-1]["scenes"][0].update(ground_truth_result="fails_hard_gates", hard_failures=["unexpected_memory_writes"])
    _provider(monkeypatch, release_repo[-1])
    report = _run(release_repo, tmp_path / "output", auto_publish_enabled=True, auto_publish_threshold="0")
    assert report["publication"]["route"] == "blocked"
    with pytest.raises(ValueError, match="Complete"):
        authorize(report)
