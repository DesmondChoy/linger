"""Real gate reports must remain consumable by the final publication guard."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from tests.test_release_gate import (
    IMAGE, SHA, _provider, _run, behavioral_repo, release_repo,
)
from tests.test_release_workflow_checks import publication_evidence


SPEC = importlib.util.spec_from_file_location(
    "release_publication_candidate", Path(__file__).resolve().parents[1] / ".github/scripts/release_candidate.py",
)
candidate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(candidate)


def authorize(report, *, live_enabled="true", approvals=None):
    decision = report["publication"]
    configuration = {
        "live_evaluations_enabled": live_enabled == "true",
        "auto_publish_enabled": decision["auto_publish_enabled"],
        "auto_publish_threshold": json.loads(decision["threshold"]),
        "configuration_sha": "c" * 40,
    }
    return candidate.publication_authorization(
        report, sha=SHA, image_id=IMAGE, route=decision["route"],
        live_enabled=live_enabled, auto_enabled=str(decision["auto_publish_enabled"]).lower(),
        threshold=decision["threshold"], configuration_sha="c" * 40,
        approvals=approvals if approvals is not None else [],
        configuration=configuration,
        image_checks=candidate.record_image_checks(SHA, IMAGE, "success", "success"),
    )


def manual_approval():
    return [{"state": "approved", "environments": [{"name": "linger-release"}]}]


def skipped_report(*, automatic=False):
    configuration = {
        "live_evaluations_enabled": False, "auto_publish_enabled": automatic,
        "auto_publish_threshold": 95, "configuration_sha": "c" * 40,
    }
    return candidate.skipped_evaluations(
        SHA, IMAGE, configuration, candidate.record_image_checks(SHA, IMAGE, "success", "success"),
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
    with pytest.raises(ValueError):
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


@pytest.fixture
def publication_cli(tmp_path):
    if shutil.which("jq") is None:
        pytest.skip("The publisher uses jq, available on the GitHub runner.")
    root = Path(__file__).resolve().parents[1]
    scripts = tmp_path / ".github/scripts"
    scripts.mkdir(parents=True)
    (scripts / "release_candidate.py").symlink_to(root / ".github/scripts/release_candidate.py")
    evidence = tmp_path / "release-evidence"
    evidence.mkdir()
    (evidence / "publication.json").write_text(json.dumps(
        authorize(publication_evidence(), approvals=manual_approval()),
    ))
    image_directory = tmp_path / "release-image"
    image_directory.mkdir()
    (image_directory / "image.tar.gz").write_bytes(b"tested image")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    docker = binaries / "docker"
    docker.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["DOCKER_CALLS"], "a") as output:
    output.write(json.dumps(args) + "\\n")
if args[:2] == ["image", "inspect"]:
    print(os.environ["REGISTRY_DIGESTS"] if "--format" in args else "[" + os.environ["IMAGE_INFO"] + "]")
elif args[0] == "login":
    sys.stdin.read()
elif args[0] == "load":
    assert Path(args[2]).read_bytes() == b"tested image"
elif args[0] not in {"tag", "push", "logout"}:
    raise SystemExit("Unexpected Docker command: " + str(args))
''')
    docker.chmod(0o755)
    image = {"Id": IMAGE, "Architecture": "amd64", "Os": "linux", "Config": {"Labels": {"org.opencontainers.image.revision": SHA}}}
    digest = "ghcr.io/desmondchoy/linger@sha256:" + "d" * 64
    environment = dict(os.environ, PATH=str(binaries) + os.pathsep + os.environ["PATH"],
                       CANDIDATE_SHA=SHA, CI_RUN_ID="42", GITHUB_REPOSITORY="DesmondChoy/linger",
                       EVALUATED_IMAGE_ID=IMAGE, PUBLICATION_ROUTE="manual", GITHUB_RUN_ID="123",
                       GITHUB_RUN_ATTEMPT="2", GH_TOKEN="test-token", GITHUB_ACTOR="test-maintainer",
                       GITHUB_STEP_SUMMARY=str(tmp_path / "summary.md"), DOCKER_CALLS=str(tmp_path / "docker.jsonl"),
                       IMAGE_INFO=json.dumps(image), REGISTRY_DIGESTS=json.dumps([digest]))

    def run(**overrides):
        result = subprocess.run(["bash", str(root / ".github/scripts/publish-candidate.sh")],
                                cwd=tmp_path, env=environment | overrides, capture_output=True, text=True)
        calls_path = tmp_path / "docker.jsonl"
        calls = [json.loads(line) for line in calls_path.read_text().splitlines()] if calls_path.exists() else []
        return result, calls

    return run, image, evidence, digest


def test_publication_loads_and_pushes_one_evaluated_image(publication_cli):
    run, _, evidence, digest = publication_cli
    result, calls = run()
    assert result.returncode == 0, result.stderr
    assert calls[0] == ["load", "--input", "release-image/image.tar.gz"]
    assert calls[1] == ["image", "inspect", IMAGE]
    expected_tag = f"ghcr.io/desmondchoy/linger:release-{SHA}-123-2"
    assert [call for call in calls if call[0] == "tag"] == [["tag", IMAGE, expected_tag]]
    assert [call for call in calls if call[0] == "push"] == [["push", expected_tag]]
    record = json.loads((evidence / "approved-release.json").read_text())
    assert record["image"] == {"candidate_sha": SHA, "image_id": IMAGE, "platform": "linux/amd64"}
    assert record["release_image"] == digest
    assert record["github_run_attempt"] == "2"


def test_publication_exports_the_recorded_digest_for_deployment(publication_cli, tmp_path):
    run, _, evidence, digest = publication_cli
    output = tmp_path / "publication-output"
    result, _ = run(GITHUB_OUTPUT=str(output))
    assert result.returncode == 0, result.stderr
    record = json.loads((evidence / "approved-release.json").read_text())
    assert f"release_image={digest}\n" in output.read_text()
    assert record["release_image"] == digest


def test_completed_live_evaluation_can_still_publish_automatically(publication_cli):
    run, _, evidence, digest = publication_cli
    authorization = authorize(publication_evidence(route="automatic", enabled=True))
    (evidence / "publication.json").write_text(json.dumps(authorization))
    result, calls = run(PUBLICATION_ROUTE="automatic")
    assert result.returncode == 0, result.stderr
    assert len([call for call in calls if call[0] == "push"]) == 1
    record = json.loads((evidence / "approved-release.json").read_text())
    assert record["release_image"] == digest
    assert record["authorization"]["evaluation_status"] == "completed"
    assert record["authorization"]["human_approvals"] == []
    assert record["authorization"]["publication"]["route"] == "automatic"


@pytest.mark.parametrize("changes", [
    {"Id": "sha256:" + "c" * 64}, {"Architecture": "arm64"}, {"Os": "windows"},
    {"Config": {"Labels": {"org.opencontainers.image.revision": "c" * 40}}},
])
def test_publication_rejects_a_different_image_before_registry_access(publication_cli, changes):
    run, image, evidence, _ = publication_cli
    result, calls = run(IMAGE_INFO=json.dumps(image | changes))
    assert result.returncode != 0
    assert not any(call[0] in {"login", "tag", "push"} for call in calls)
    assert not (evidence / "approved-release.json").exists()


def test_publication_requires_authorization_before_loading_image(publication_cli):
    run, _, evidence, _ = publication_cli
    (evidence / "publication.json").unlink()
    result, calls = run()
    assert result.returncode != 0
    assert calls == []


def test_publication_requires_a_registry_digest_for_its_record(publication_cli):
    run, _, evidence, _ = publication_cli
    result, calls = run(REGISTRY_DIGESTS="[]")
    assert result.returncode != 0
    assert len([call for call in calls if call[0] == "push"]) == 1
    assert not (evidence / "approved-release.json").exists()


@pytest.mark.parametrize("automatic", [False, True])
def test_disabled_live_publication_pushes_same_image_only_after_human_approval(publication_cli, automatic):
    run, _, evidence, digest = publication_cli
    report = skipped_report(automatic=automatic)
    record = authorize(report, live_enabled="false", approvals=manual_approval())
    (evidence / "publication.json").write_text(json.dumps(record))
    result, calls = run()
    assert result.returncode == 0, result.stderr
    assert calls[0] == ["load", "--input", "release-image/image.tar.gz"]
    assert not any(call[0] == "build" for call in calls)
    assert len([call for call in calls if call[0] == "push"]) == 1
    approved = json.loads((evidence / "approved-release.json").read_text())
    assert approved["release_image"] == digest
    assert approved["candidate_sha"] == SHA
    assert approved["ci_run_id"] == "42"
    assert approved["image"]["image_id"] == IMAGE
    assert approved["authorization"] == record
    assert record["configuration_sha"] == "c" * 40
    assert record["evaluation_status"] == "skipped"
    assert record["publication"]["route"] == "manual"
    assert record["publication"]["automated_pass_percentage"] is None
    assert record["publication"]["judgments_total"] is None
    assert record["human_approvals"] == manual_approval()


@pytest.mark.parametrize("change", [
    {"human_approvals": []},
    {"human_approvals": [{"state": "rejected", "environments": [{"name": "linger-release"}]}]},
    {"human_approvals": [{"state": "approved", "environments": [{"name": "linger-release-auto"}]}]},
    {"evaluation_status": "completed"}, {"evaluation_status": "failed"},
    {"live_evaluations_enabled": "false"}, {"image_checks": {}},
])
def test_disabled_live_bad_authority_is_rejected_before_loading_or_pushing(publication_cli, change):
    run, _, evidence, _ = publication_cli
    record = authorize(skipped_report(), live_enabled="false", approvals=manual_approval())
    (evidence / "publication.json").write_text(json.dumps(record | change))
    result, calls = run()
    assert result.returncode != 0
    assert calls == []
    assert not (evidence / "approved-release.json").exists()


@pytest.mark.parametrize("change", [
    {"route": "automatic"}, {"automated_pass_percentage": 100},
    {"judgments_passed": 0}, {"judgments_total": 0},
])
def test_disabled_live_cannot_fabricate_scores_or_automatic_authority(publication_cli, change):
    run, _, evidence, _ = publication_cli
    record = authorize(skipped_report(automatic=True), live_enabled="false", approvals=manual_approval())
    record["publication"].update(change)
    (evidence / "publication.json").write_text(json.dumps(record))
    result, calls = run(PUBLICATION_ROUTE=record["publication"]["route"])
    assert result.returncode != 0
    assert calls == []


def test_missing_saved_image_never_triggers_a_rebuild(publication_cli):
    run, _, evidence, _ = publication_cli
    (evidence.parent / "release-image/image.tar.gz").unlink()
    result, calls = run()
    assert result.returncode != 0
    assert not any(call[0] in {"build", "tag", "login", "push"} for call in calls)
