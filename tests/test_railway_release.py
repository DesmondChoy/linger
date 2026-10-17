"""Only an approved, publicly pullable image may reach the existing production service."""

import base64
import copy
from http.server import BaseHTTPRequestHandler, HTTPServer
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import threading

import pytest

from tests.test_release_workflow_checks import candidate, publication_evidence

SCRIPT = Path(__file__).resolve().parents[1] / ".github/scripts/railway_release.py"
spec = importlib.util.spec_from_file_location("railway_release", SCRIPT)
railway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(railway)
SHA = "a" * 40
REPO = "DesmondChoy/linger"
IMAGE = "sha256:" + "b" * 64
REFERENCE = "ghcr.io/desmondchoy/linger@sha256:" + "c" * 64
APPROVALS = [{"state": "approved", "environments": [{"name": "linger-release"}]}]


def promotion():
    return {
        "head": {"ref": "main", "repo": {"full_name": REPO}},
        "base": {"ref": "release-candidate", "repo": {"full_name": REPO}},
        "merged_at": "2026-10-17T00:00:00Z", "merge_commit_sha": SHA,
        "html_url": "https://github.com/DesmondChoy/linger/pull/123",
    }


def publication(evidence=None, *, live=False, automatic=False):
    """Produce the existing publication contract using the shared release policy."""
    configuration = {"live_evaluations_enabled": live, "auto_publish_enabled": automatic,
                     "auto_publish_threshold": 95, "configuration_sha": SHA}
    checks = candidate.record_image_checks(SHA, IMAGE, "success", "success")
    summary = (publication_evidence(route="automatic" if automatic else "manual", enabled=automatic)
               if live else candidate.skipped_evaluations(SHA, IMAGE, configuration, checks))
    route = summary["publication"]["route"]
    approvals = copy.deepcopy(APPROVALS) if route == "manual" else []
    authorization = candidate.publication_authorization(
        summary, sha=SHA, image_id=IMAGE, route=route, live_enabled=str(live).lower(),
        auto_enabled=str(automatic).lower(), threshold="95", configuration_sha=SHA,
        configuration=configuration, image_checks=checks, approvals=approvals,
    )
    summary_text = json.dumps(summary, indent=2) + "\n"
    summary_hash = "evaluation_summary_sha256" if live else "skipped_evaluation_record_sha256"
    authorization[summary_hash] = hashlib.sha256(summary_text.encode()).hexdigest()
    record = {
        "candidate_sha": SHA, "ci_run_id": "42", "github_run_id": "100", "github_run_attempt": "2",
        "release_image": REFERENCE,
        "image": {"candidate_sha": SHA, "image_id": IMAGE, "platform": "linux/amd64"},
        "authorization": authorization,
    }
    if evidence is not None:
        for name, value in {
            "approved-release.json": record, "publication.json": authorization, "image.json": record["image"],
            "release-configuration.json": configuration, "image-checks.json": checks,
            "approvals.json": approvals,
        }.items():
            (evidence / name).write_text(json.dumps(value, indent=2) + "\n")
        (evidence / "behavioral").mkdir(exist_ok=True)
        (evidence / "behavioral/summary.json").write_text(summary_text)
    return record


def github_api(monkeypatch, *, tip=SHA, policy_changes=None, pulls=None, ci_changes=None,
               release_changes=None, publish_status="success", publish_sha=SHA, expired=False, approvals=None):
    policy = {"live_evaluations_enabled": False, "auto_publish_enabled": False,
              "auto_publish_threshold": 95} | (policy_changes or {})
    ci = {
        "head_sha": SHA, "head_branch": "release-candidate", "event": "push", "status": "completed",
        "conclusion": "success", "path": ".github/workflows/ci.yml",
        "repository": {"full_name": REPO}, "head_repository": {"full_name": REPO}, "html_url": "https://example.test/ci/42",
    } | (ci_changes or {})
    release = {
        "path": ".github/workflows/release-auto.yml", "event": "workflow_run", "head_branch": "main",
        "repository": {"full_name": REPO}, "head_repository": {"full_name": REPO},
        "status": "completed", "conclusion": "failure",
    } | (release_changes or {})
    calls = []

    def api(repository, path):
        assert repository == REPO
        calls.append(path)
        if path == "actions/runs/42":
            return ci
        if path == "branches/release-candidate":
            return {"commit": {"sha": tip}}
        if path == f"contents/.github/release-config.json?ref={tip}":
            return {"type": "file", "encoding": "base64", "content": base64.b64encode(json.dumps(policy).encode()).decode()}
        if path == f"commits/{SHA}/pulls?per_page=100":
            return [promotion()] if pulls is None else pulls
        if path == "actions/runs/100/attempts/2":
            return release
        if path == "actions/runs/100/attempts/2/jobs?per_page=100":
            return {"jobs": [{"name": f"release / Publish approved {publish_sha}", "conclusion": publish_status}]}
        if path == "actions/runs/100/artifacts?per_page=100":
            return {"artifacts": [{"name": f"release-publication-{SHA}-100-2", "expired": expired}]}
        if path == "actions/runs/100/approvals":
            return copy.deepcopy(APPROVALS if approvals is None else approvals)
        pytest.fail(f"Unexpected GitHub request: {path}")

    monkeypatch.setattr(railway, "api", api)
    monkeypatch.setitem(railway.configuration.__globals__, "api", api)
    return calls


def test_accepts_exact_candidate_ci_and_merged_promotion(monkeypatch):
    github_api(monkeypatch)
    assert railway.resolve(REPO, SHA, "42")["promotion_url"].endswith("/123")


@pytest.mark.parametrize("side,key,value", [
    ("head", "ref", "feature"), ("head", "repo", {"full_name": "fork/linger"}),
    ("base", "ref", "main"), ("base", "repo", None),
])
def test_promotion_blocks_wrong_source(side, key, value):
    pull = promotion()
    pull[side][key] = value
    with pytest.raises(ValueError, match="same-repository"):
        railway.validate_promotion(pull, REPO)


@pytest.mark.parametrize("pulls", [[], [promotion() | {"merged_at": None}],
                                  [promotion() | {"merge_commit_sha": "b" * 40}]])
def test_direct_push_or_unmerged_pr_cannot_deploy(monkeypatch, pulls):
    github_api(monkeypatch, pulls=pulls)
    with pytest.raises(ValueError, match="merged"):
        railway.resolve(REPO, SHA, "42")


@pytest.mark.parametrize("changes", [
    {"head_sha": "b" * 40}, {"event": "pull_request"}, {"event": "workflow_dispatch"}, {"event": "schedule"},
    {"conclusion": "failure"}, {"status": "in_progress"}, {"head_branch": "main"},
    {"path": ".github/workflows/other.yml"}, {"head_repository": {"full_name": "fork/linger"}},
])
def test_unsuitable_ci_cannot_deploy(monkeypatch, changes):
    github_api(monkeypatch, ci_changes=changes)
    with pytest.raises(ValueError):
        railway.resolve(REPO, SHA, "42")


def test_old_candidate_cannot_replace_newer_release_tip(monkeypatch):
    github_api(monkeypatch, tip="b" * 40)
    with pytest.raises(ValueError, match="stale"):
        railway.resolve(REPO, SHA, "42")


@pytest.mark.parametrize("field,value", [
    ("release_image", "ghcr.io/desmondchoy/linger:latest"),
    ("release_image", "ghcr.io/attacker/linger@sha256:" + "c" * 64),
    ("github_run_attempt", "1"), ("github_run_id", "999"), ("ci_run_id", "0"),
])
def test_publication_identity_is_not_user_selectable(monkeypatch, tmp_path, field, value):
    github_api(monkeypatch)
    record = publication(tmp_path) | {field: value}
    with pytest.raises(ValueError):
        railway.validate_publication(record, REPO, "100", "2", tmp_path)


@pytest.mark.parametrize("field,value", [
    ("human_approvals", []), ("image_id", "sha256:" + "d" * 64),
    ("configuration_sha", "d" * 40), ("image_checks", {}), ("evaluation_status", "completed"),
    ("skipped_evaluation_record_sha256", "d" * 64),
    ("publication", {"route": "automatic", "auto_publish_enabled": True}),
])
def test_offline_evidence_needs_exact_image_checks_and_approval(monkeypatch, tmp_path, field, value):
    github_api(monkeypatch)
    record = publication(tmp_path)
    record["authorization"][field] = value
    (tmp_path / "publication.json").write_text(json.dumps(record["authorization"]))
    with pytest.raises(ValueError):
        railway.validate_publication(record, REPO, "100", "2", tmp_path)


@pytest.mark.parametrize("live,automatic", [(False, False), (False, True), (True, False), (True, True)])
def test_consumer_accepts_both_existing_publication_modes(monkeypatch, tmp_path, live, automatic):
    github_api(monkeypatch, policy_changes={"live_evaluations_enabled": live, "auto_publish_enabled": automatic})
    record = publication(tmp_path, live=live, automatic=automatic)
    assert "evidence_mode" not in record
    assert railway.validate_publication(record, REPO, "100", "2", tmp_path)["candidate_sha"] == SHA
    if not live:
        assert record["authorization"]["publication"]["route"] == "manual"
        assert record["authorization"]["publication"]["automated_pass_percentage"] is None


@pytest.mark.parametrize("name,field,value", [
    ("image.json", "image_id", "sha256:" + "d" * 64),
    ("image-checks.json", "offline_smoke", "failed"),
    ("release-configuration.json", "auto_publish_threshold", 90),
    ("behavioral/summary.json", "status", "passed"),
    ("publication.json", "evaluation_status", "completed"),
])
def test_retained_evidence_must_match_publication(monkeypatch, tmp_path, name, field, value):
    github_api(monkeypatch)
    record = publication(tmp_path)
    path = tmp_path / name
    path.write_text(json.dumps(json.loads(path.read_text()) | {field: value}))
    with pytest.raises(ValueError):
        railway.validate_publication(record, REPO, "100", "2", tmp_path)


def test_summary_bytes_must_match_hash_in_authorization(monkeypatch, tmp_path):
    github_api(monkeypatch)
    record = publication(tmp_path)
    with (tmp_path / "behavioral/summary.json").open("a") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="authorization differs"):
        railway.validate_publication(record, REPO, "100", "2", tmp_path)


def test_manual_publication_requires_live_approval_history(monkeypatch, tmp_path):
    github_api(monkeypatch, approvals=[])
    record = publication(tmp_path)
    with pytest.raises(ValueError, match="human release approval"):
        railway.validate_publication(record, REPO, "100", "2", tmp_path)


def test_retry_accepts_failed_original_run_when_its_publication_succeeded(monkeypatch, tmp_path):
    calls = github_api(monkeypatch)
    commands = []

    def command(*args):
        commands.append(args)
        publication(tmp_path)
        return ""

    monkeypatch.setattr(railway, "command", command)
    assert railway.load_publication(REPO, "100", "2", tmp_path)["release_image"] == REFERENCE
    assert commands == [("gh", "run", "download", "100", "--repo", REPO, "--name",
                         f"release-publication-{SHA}-100-2", "--dir", str(tmp_path))]
    assert "actions/runs/100/attempts/2/jobs?per_page=100" in calls


@pytest.mark.parametrize("options", [
    {"publish_status": "failure"}, {"publish_status": "skipped"}, {"expired": True},
    {"release_changes": {"path": ".github/workflows/untrusted.yml"}},
    {"release_changes": {"event": "pull_request"}}, {"release_changes": {"head_branch": "feature"}},
    {"release_changes": {"head_repository": {"full_name": "fork/linger"}}},
])
def test_retry_rejects_untrusted_unpublished_or_expired_sources(monkeypatch, tmp_path, options):
    github_api(monkeypatch, **options)
    monkeypatch.setattr(railway, "command", lambda *_: pytest.fail("No artifact download permitted"))
    with pytest.raises(ValueError):
        railway.load_publication(REPO, "100", "2", tmp_path)


def test_publication_job_must_name_the_exact_recorded_candidate(monkeypatch, tmp_path):
    github_api(monkeypatch, publish_sha="d" * 40)
    monkeypatch.setattr(railway, "command", lambda *_: publication(tmp_path))
    with pytest.raises(ValueError, match="successful job"):
        railway.load_publication(REPO, "100", "2", tmp_path)


def test_registry_check_is_anonymous_and_binds_manifest_to_tested_image(monkeypatch):
    body = json.dumps({"config": {"digest": IMAGE}}).encode()
    digest = "sha256:" + hashlib.sha256(body).hexdigest()
    requests = []

    def open_url(request, **kwargs):
        requests.append(request)
        if isinstance(request, str):
            assert request.startswith("https://ghcr.io/token?")
            return io.BytesIO(b'{"token":"anonymous-pull-token"}')
        assert request.get_header("Authorization") == "Bearer anonymous-pull-token"
        assert request.full_url.endswith(digest)
        return io.BytesIO(body)

    monkeypatch.setenv("GH_TOKEN", "must-not-forward")
    monkeypatch.setenv("RAILWAY_TOKEN", "must-not-forward")
    monkeypatch.setattr(railway, "urlopen", open_url)
    assert railway.public_image(f"ghcr.io/desmondchoy/linger@{digest}", IMAGE)["public"]
    with pytest.raises(ValueError, match="public"):
        railway.public_image(f"ghcr.io/desmondchoy/linger@{digest}", "sha256:" + "d" * 64)
    assert len(requests) == 4


def active_service():
    return {"source": {"image": REFERENCE}, "healthcheckPath": "/api/ready",
            "activeDeployments": [{"id": "new-deployment", "status": "SUCCESS"}]}


@pytest.mark.parametrize("problem", ["extra-environment", "missing-volume", "wrong-volume", "healthcheck"])
def test_preflight_refuses_topology_storage_or_healthcheck_drift(monkeypatch, problem):
    environments = [{"node": {"id": railway.ENVIRONMENT}}]
    volumes = [{"node": {"serviceId": railway.SERVICE, "volumeId": railway.VOLUME,
                          "mountPath": "/var/lib/linger", "isPendingDeletion": False}}]
    if problem == "extra-environment":
        environments.append({"node": {"id": "another-environment"}})
    elif problem == "missing-volume":
        volumes = []
    elif problem == "wrong-volume":
        volumes[0]["node"]["volumeId"] = "replacement-volume"
    value = {"project": {"environments": {"edges": environments}},
             "environment": {"projectId": railway.PROJECT, "volumeInstances": {"edges": volumes}}}
    monkeypatch.setattr(railway, "railway_api", lambda *_: value)
    current = active_service()
    if problem == "healthcheck":
        current["healthcheckPath"] = None
    monkeypatch.setattr(railway, "service", lambda: current)
    with pytest.raises(ValueError):
        railway.preflight()


def deployment(status="SUCCESS"):
    return {"id": "new-deployment", "projectId": railway.PROJECT, "environmentId": railway.ENVIRONMENT,
            "serviceId": railway.SERVICE, "status": status,
            "meta": {"imageDigest": REFERENCE.split("@")[1], "volumeMounts": ["/var/lib/linger"]}}


@pytest.mark.parametrize("change,reason", [
    ({"status": "FAILED"}, "FAILED"), ({"serviceId": "another-service"}, "another"),
    ({"meta": {"imageDigest": "sha256:" + "d" * 64}}, "digest"),
    ({"meta": {"imageDigest": REFERENCE.split("@")[1], "volumeMounts": []}}, "state mount"),
])
def test_exact_deployment_must_match_image_service_and_volume(monkeypatch, change, reason):
    monkeypatch.setattr(railway, "railway_api", lambda *_: {"deployment": deployment() | change})
    monkeypatch.setattr(railway, "service", active_service)
    with pytest.raises(ValueError, match=reason):
        railway.wait_for_deployment("new-deployment", REFERENCE)


def test_wait_checks_exact_new_id_and_active_image(monkeypatch):
    values = iter([deployment("DEPLOYING"), deployment()])
    calls = []

    def api(query, variables):
        calls.append(variables)
        return {"deployment": next(values)}

    monkeypatch.setattr(railway, "railway_api", api)
    monkeypatch.setattr(railway.time, "sleep", lambda _: None)
    monkeypatch.setattr(railway, "service", active_service)
    assert railway.wait_for_deployment("new-deployment", REFERENCE)["id"] == "new-deployment"
    assert calls == [{"id": "new-deployment"}, {"id": "new-deployment"}]


@pytest.mark.parametrize("http_ready", [True, False])
def test_deploy_reuses_published_image_and_records_id_before_public_checks(monkeypatch, tmp_path, http_ready):
    monkeypatch.setattr(railway, "load_publication", lambda *_: publication())
    monkeypatch.setattr(railway, "public_image", lambda *_: {"public": True})
    monkeypatch.setattr(railway, "preflight", lambda: None)
    monkeypatch.setattr(railway, "validate_publication", lambda *_: {})
    monkeypatch.setattr(railway, "service", active_service)
    monkeypatch.setattr(railway, "wait_for_deployment", lambda *args: deployment())
    monkeypatch.setattr(railway, "command", lambda *_: pytest.fail("Deployment must not build, upload source, or run evals"))
    mutations = []

    def api(query, variables):
        mutations.append((query, variables))
        if "serviceInstanceDeployV2" in query:
            return {"serviceInstanceDeployV2": "new-deployment"}
        if "serviceInstanceUpdate" in query:
            return {"serviceInstanceUpdate": True}
        return {"variableUpsert": True}

    def verify():
        if not http_ready:
            raise ValueError("Public API is not ready")
        return {"ready": True, "frontend": True, "provider_calls": 0}

    monkeypatch.setattr(railway, "railway_api", api)
    monkeypatch.setattr(railway, "verify_site", verify)
    output = tmp_path / "evidence.json"
    if http_ready:
        result = railway.deploy(REPO, "100", "2", output)
        assert result["status"] == "success"
    else:
        with pytest.raises(ValueError, match="Public API"):
            railway.deploy(REPO, "100", "2", output)
        result = json.loads(output.read_text())
        assert result["status"] == "failed"
    assert result["deployment_id"] == "new-deployment"
    assert result["release_image"] == REFERENCE
    assert mutations[0][1]["input"]["skipDeploys"] is True
    # ServiceInstanceUpdateInput accepts source; volume mount requirements are checked separately.
    assert mutations[1][1]["input"] == {"source": {"image": REFERENCE, "repo": None}}
    assert mutations[2][1] == {"service": railway.SERVICE, "environment": railway.ENVIRONMENT}


def test_private_image_fails_before_any_railway_mutation(monkeypatch, tmp_path):
    monkeypatch.setattr(railway, "load_publication", lambda *_: publication())

    def private(*_):
        raise ValueError("GHCR package must be public")

    monkeypatch.setattr(railway, "public_image", private)
    monkeypatch.setattr(railway, "railway_api", lambda *_: pytest.fail("Railway must remain unchanged"))
    with pytest.raises(ValueError, match="public"):
        railway.deploy(REPO, "100", "2", tmp_path / "evidence.json")


@pytest.mark.parametrize("ready,html,expected", [
    ("ready", '<div id="root"></div>', True), ("starting", '<div id="root"></div>', False),
    ("ready", "unrelated site", False),
])
def test_http_checks_never_invoke_provider(monkeypatch, ready, html, expected):
    paths = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            paths.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "application/json" if self.path == "/api/ready" else "text/html")
            self.end_headers()
            self.wfile.write((json.dumps({"status": ready}) if self.path == "/api/ready" else html).encode())

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    monkeypatch.setattr(railway, "SITE", f"http://127.0.0.1:{server.server_port}")
    try:
        if expected:
            assert railway.verify_site()["provider_calls"] == 0
        else:
            with pytest.raises(ValueError):
                railway.verify_site()
        assert set(paths) <= {"/", "/api/ready"}
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
