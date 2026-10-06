"""The release boundary rejects untrusted or incomplete evidence before use."""

import copy
import base64
import importlib.util
import json
from pathlib import Path

import pytest


def load_script(name):
    path = Path(__file__).resolve().parents[1] / ".github" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


candidate = load_script("release_candidate")
security = load_script("security_gate")
SHA = "a" * 40
IMAGE = "sha256:" + "b" * 64
REPO = "DesmondChoy/linger"


def trusted_run():
    return {
        "head_sha": SHA, "head_branch": "release-candidate", "event": "push", "status": "completed",
        "conclusion": "success", "path": ".github/workflows/ci.yml",
        "repository": {"full_name": REPO}, "head_repository": {"full_name": REPO},
    }


def test_candidate_accepts_successful_release_candidate_push():
    candidate.validate_run(trusted_run(), SHA, REPO)


@pytest.mark.parametrize("key,value", [
    ("head_sha", "c" * 40), ("head_branch", "main"), ("head_branch", "feature"), ("event", "pull_request"),
    ("event", "workflow_dispatch"), ("status", "in_progress"), ("conclusion", "failure"),
    ("path", ".github/workflows/untrusted.yml"),
    ("head_repository", {"full_name": "fork/linger"}),
    ("repository", {"full_name": "fork/linger"}),
])
def test_candidate_rejects_wrong_ci_origin(key, value):
    run = trusted_run()
    run[key] = value
    with pytest.raises(ValueError):
        candidate.validate_run(run, SHA, REPO)


def test_release_requires_real_reviewers():
    for environment in ({}, {"protection_rules": []}, {"protection_rules": [{"type": "required_reviewers", "reviewers": []}]}):
        with pytest.raises(ValueError, match="reviewers"):
            candidate.validate_environment(environment)
    candidate.validate_environment({"protection_rules": [{"type": "required_reviewers", "reviewers": [{"type": "User"}]}]})


def settings(**changes):
    return {"live_evaluations_enabled": False, "auto_publish_enabled": False, "auto_publish_threshold": 95} | changes


@pytest.mark.parametrize("value", [
    {}, settings(live_evaluations_enabled="true"), settings(auto_publish_enabled=1),
    settings(auto_publish_threshold=True), settings(auto_publish_threshold="95"),
    settings(auto_publish_threshold=-1), settings(auto_publish_threshold=101),
    settings(auto_publish_threshold=float("nan")), settings(auto_publish_threshold=float("inf")),
    settings(unrecognized_setting=True),
])
def test_configuration_rejects_ambiguous_or_invalid_values(value):
    with pytest.raises(ValueError):
        candidate.validate_configuration(value)


@pytest.mark.parametrize("threshold", [0, 95, 99.5, 100])
def test_configuration_accepts_explicit_switches_and_bounded_threshold(threshold):
    assert candidate.validate_configuration(settings(auto_publish_threshold=threshold))["auto_publish_threshold"] == threshold


def test_disabled_candidate_configuration_needs_no_release_environment(monkeypatch, tmp_path):
    calls = []
    configuration_sha = "c" * 40

    def github(repository, path):
        calls.append((repository, path))
        if path == "branches/release-candidate":
            return {"commit": {"sha": configuration_sha}}
        return {"type": "file", "encoding": "base64", "content": base64.b64encode(json.dumps(settings()).encode()).decode()}

    monkeypatch.setattr(candidate, "api", github)
    summary = tmp_path / "summary.md"
    outputs = tmp_path / "outputs"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    result = candidate.configuration(REPO, SHA)
    candidate.emit(result)
    assert result == settings() | {"configuration_sha": configuration_sha}
    assert calls == [(REPO, "branches/release-candidate"), (REPO, f"contents/.github/release-config.json?ref={configuration_sha}")]
    assert "Evaluation and publication jobs are skipped" in summary.read_text()
    assert "live_evaluations_enabled=false\n" in outputs.read_text()
    assert f"configuration_sha={configuration_sha}\n" in outputs.read_text()


def test_candidate_configuration_ref_must_be_an_exact_sha(monkeypatch):
    monkeypatch.setattr(candidate, "api", lambda *_: pytest.fail("Invalid refs must not reach the API"))
    with pytest.raises(ValueError, match="40-character"):
        candidate.configuration(REPO, "release-candidate")


def candidate_api(monkeypatch, *, comparison="ahead"):
    run = trusted_run() | {"id": 42, "html_url": "https://example.test/ci/42"}
    calls = []

    def github(repository, path):
        calls.append(path)
        if path.startswith("actions/workflows/ci.yml/runs?"):
            return {"workflow_runs": [run]}
        if path == "actions/runs/42":
            return run
        if path == f"compare/{SHA}...release-candidate":
            return {"status": comparison}
        if path == "environments/linger-release":
            return {"protection_rules": [{"type": "required_reviewers", "reviewers": [{"type": "User"}]}]}
        pytest.fail(f"Unexpected API path: {path}")

    monkeypatch.setattr(candidate, "api", github)
    return calls


def test_resolve_accepts_successful_rc_push_without_retained_images(monkeypatch):
    calls = candidate_api(monkeypatch)
    assert candidate.resolve(REPO, SHA, "")["ci_run_id"] == "42"
    assert "branch=release-candidate" in calls[0]


@pytest.mark.parametrize("comparison", ["behind", "diverged"])
def test_resolve_rejects_candidate_removed_from_release_branch(monkeypatch, comparison):
    candidate_api(monkeypatch, comparison=comparison)
    with pytest.raises(ValueError, match="reachable"):
        candidate.resolve(REPO, SHA, "42")


def publication_evidence(route="manual", enabled=False):
    return {
        "status": "review_required", "identity": {"candidate_sha": SHA, "image_id": IMAGE},
        "problems": [],
        "totals": {
            "requested_runs": 1, "completed_runs": 1, "not_started_runs": 0,
            "failed_runs": 0, "blocked_runs": 0, "scenes_ungraded": 0,
            "judgments_passed": 2, "judgments_failed": 0, "judgments_total": 2,
        },
        "runs": [{
            "status": "passed", "execution_status": "completed", "returncode": 0, "problems": [],
            "telemetry": {"flushed": True, "url": "https://example.test/trace"},
            "results": {
                "blocking_failures": [], "execution_failures": [], "scenes_ungraded": 0,
                "judgments_passed": 2, "judgments_failed": 0, "judgments_total": 2,
            },
        }],
        "publication": candidate.publication_decision(
            judgments_passed=2, judgments_total=2, complete=True, blocked=False,
            auto_publish_enabled=enabled, threshold="95",
        ) | {"route": route},
    }


def authorize(summary=None, **changes):
    arguments = {
        "sha": SHA, "image_id": IMAGE, "route": "manual", "live_enabled": "true",
        "configuration_sha": "c" * 40,
        "auto_enabled": "false", "threshold": "95", "approvals": [
            {"state": "approved", "environments": [{"name": "linger-release"}]},
        ],
    } | changes
    return candidate.publication_authorization(summary or publication_evidence(), **arguments)


def test_manual_publication_records_actual_environment_approval():
    record = authorize()
    assert record["publication"]["route"] == "manual"
    assert record["human_approvals"][0]["state"] == "approved"


@pytest.mark.parametrize("changes", [
    {"live_enabled": "false"}, {"live_enabled": ""}, {"approvals": []},
    {"approvals": [{"state": "rejected", "environments": [{"name": "linger-release"}]}]},
    {"approvals": [{"state": "approved", "environments": [{"name": "another-environment"}]}]},
    {"sha": "c" * 40}, {"image_id": "sha256:" + "d" * 64},
    {"configuration_sha": "release-candidate"},
    {"route": "automatic"}, {"auto_enabled": "true"}, {"threshold": "94"},
])
def test_publication_rejects_missing_authority_or_changed_evidence(changes):
    with pytest.raises(ValueError):
        authorize(**changes)


def test_automatic_publication_records_policy_without_fabricating_human_approval():
    record = authorize(publication_evidence("automatic", True), route="automatic", auto_enabled="true", approvals=[])
    assert record["publication"]["route"] == "automatic"
    assert record["human_approvals"] == []


@pytest.mark.parametrize("status", ["ready", "blocked", "failed"])
def test_preflight_or_failed_evidence_never_authorizes_publication(status):
    with pytest.raises(ValueError, match="Complete"):
        authorize(publication_evidence() | {"status": status})


@pytest.mark.parametrize("missing", ["runs", "totals", "problems"])
def test_route_labels_without_complete_evidence_cannot_authorize(missing):
    summary = publication_evidence("automatic", True)
    del summary[missing]
    with pytest.raises(ValueError, match="Complete"):
        authorize(summary, route="automatic", auto_enabled="true", approvals=[])


@pytest.mark.parametrize("change", [
    {"returncode": 1}, {"execution_status": "not_started"}, {"status": "failed"},
    {"problems": ["Failed"]}, {"telemetry": {"flushed": False, "url": "https://example.test/trace"}},
])
def test_execution_failure_cannot_be_hidden_by_automatic_route_label(change):
    summary = publication_evidence("automatic", True)
    summary["runs"][0].update(change)
    with pytest.raises(ValueError):
        authorize(summary, route="automatic", auto_enabled="true", approvals=[])


def test_security_failure_cannot_be_hidden_by_automatic_route_label():
    summary = publication_evidence("automatic", True)
    summary["runs"][0]["results"]["blocking_failures"] = [{"detail": "attack_succeeded"}]
    with pytest.raises(ValueError):
        authorize(summary, route="automatic", auto_enabled="true", approvals=[])


@pytest.mark.parametrize("passed", [94, 95])
def test_automatic_route_at_or_below_threshold_is_rejected(passed):
    summary = publication_evidence("automatic", True)
    counts = {"judgments_passed": passed, "judgments_failed": 100 - passed, "judgments_total": 100}
    summary["totals"].update(counts)
    summary["runs"][0]["results"].update(counts)
    summary["publication"] = candidate.publication_decision(
        judgments_passed=passed, judgments_total=100, complete=True, blocked=False,
        auto_publish_enabled=True, threshold="95",
    ) | {"route": "automatic"}
    with pytest.raises(ValueError, match="computed"):
        authorize(summary, route="automatic", auto_enabled="true", approvals=[])


def test_summary_totals_must_match_evaluation_counts():
    summary = publication_evidence()
    summary["totals"]["judgments_passed"] = 1
    with pytest.raises(ValueError, match="totals"):
        authorize(summary)


def test_declared_ungraded_continuity_targets_are_excluded_from_score():
    summary = publication_evidence()
    summary["totals"]["scenes_ungraded"] = 1
    summary["runs"][0]["results"]["scenes_ungraded"] = 1
    assert authorize(summary)["publication"]["judgments_total"] == 2


def test_inspect_image_checks_the_evaluated_digest_without_archive_metadata(monkeypatch):
    calls = []
    image = {"Id": IMAGE, "Architecture": "amd64", "Os": "linux", "Config": {"Labels": {"org.opencontainers.image.revision": SHA}}}

    def docker(*args):
        calls.append(args)
        return json.dumps([image])

    monkeypatch.setattr(candidate, "command", docker)
    assert candidate.inspect_image(SHA, IMAGE) == {"candidate_sha": SHA, "image_id": IMAGE, "platform": "linux/amd64"}
    assert calls == [("docker", "image", "inspect", IMAGE)]


def test_inspect_image_rejects_mutable_tags_before_docker(monkeypatch):
    monkeypatch.setattr(candidate, "command", lambda *_: pytest.fail("A tag is not an evaluated identity"))
    with pytest.raises(ValueError, match="digest"):
        candidate.inspect_image(SHA, "linger:latest")


def test_image_must_match_revision_platform_and_digest():
    image = {"Id": IMAGE, "Architecture": "amd64", "Os": "linux", "Config": {"Labels": {"org.opencontainers.image.revision": SHA}}}
    candidate.validate_image(image, SHA, IMAGE)
    for key, value in (("Id", "sha256:" + "0" * 64), ("Architecture", "arm64"), ("Os", "windows"), ("Config", {"Labels": {}})):
        changed = copy.deepcopy(image)
        changed[key] = value
        with pytest.raises(ValueError):
            candidate.validate_image(changed, SHA, IMAGE)


def test_trivy_low_findings_reported_but_high_findings_block():
    document = {"SchemaVersion": 2, "ArtifactName": "uv.lock", "Results": [{"Target": "uv.lock", "Vulnerabilities": [
        {"VulnerabilityID": "CVE-low", "Severity": "LOW"},
        {"VulnerabilityID": "CVE-high", "Severity": "HIGH"},
        {"VulnerabilityID": "CVE-critical", "Severity": "CRITICAL"},
    ]}]}
    findings = security.trivy_findings(document)
    assert len(findings) == 2
    assert "CVE-high" in findings[0]
    document["Results"][0]["Vulnerabilities"] = []
    assert security.trivy_findings(document) == []


@pytest.mark.parametrize("document", [{}, {"SchemaVersion": 2, "ArtifactName": "repo", "Results": []}])
def test_trivy_missing_analysis_cannot_pass(document):
    with pytest.raises(ValueError):
        security.trivy_findings(document)


def sarif(score="8.1"):
    return {"version": "2.1.0", "runs": [{
        "tool": {"driver": {"name": "CodeQL", "rules": [{"id": "unsafe", "properties": {"security-severity": score}}]}},
        "results": [{"ruleId": "unsafe"}],
    }]}


def test_codeql_gates_numeric_security_severity():
    assert security.codeql_findings(sarif()) == ["unsafe: security severity 8.1"]
    assert security.codeql_findings(sarif("6.9")) == []


def test_failed_codeql_analysis_cannot_pass():
    document = sarif()
    document["runs"][0]["invocations"] = [{"executionSuccessful": False}]
    with pytest.raises(ValueError, match="unsuccessful"):
        security.codeql_findings(document)


def test_unknown_codeql_rule_cannot_pass():
    document = sarif()
    document["runs"][0]["results"][0]["ruleId"] = "missing"
    with pytest.raises(ValueError, match="metadata"):
        security.codeql_findings(document)
