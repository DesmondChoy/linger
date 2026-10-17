"""Native deployment must preserve the reviewed commit, CI gate, and persistent service."""

import base64
import copy
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.util
import json
from pathlib import Path
import threading

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / ".github/scripts/railway_release.py"
spec = importlib.util.spec_from_file_location("railway_release", SCRIPT)
railway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(railway)
SHA = "a" * 40
REPO = "DesmondChoy/linger"


def promotion():
    return {
        "head": {"ref": "main", "repo": {"full_name": REPO}},
        "base": {"ref": "release-candidate", "repo": {"full_name": REPO}},
        "merged_at": "2026-10-17T00:00:00Z", "merge_commit_sha": SHA,
        "html_url": "https://github.com/DesmondChoy/linger/pull/123",
    }


def candidate_api(monkeypatch, *, tip=SHA, policy=None, pulls=None, run_changes=None):
    policy = policy or {
        "live_evaluations_enabled": False, "auto_publish_enabled": False, "auto_publish_threshold": 95,
    }
    run = {
        "head_sha": SHA, "head_branch": "release-candidate", "event": "push",
        "status": "completed", "conclusion": "success", "path": ".github/workflows/ci.yml",
        "repository": {"full_name": REPO}, "head_repository": {"full_name": REPO},
        "html_url": "https://github.com/DesmondChoy/linger/actions/runs/42",
    } | (run_changes or {})

    def api(repository, path):
        assert repository == REPO
        if path == "actions/runs/42":
            return run
        if path == "branches/release-candidate":
            return {"commit": {"sha": tip}}
        if path == f"contents/.github/release-config.json?ref={tip}":
            return {"type": "file", "encoding": "base64",
                    "content": base64.b64encode(json.dumps(policy).encode()).decode()}
        if path == f"commits/{SHA}/pulls?per_page=100":
            return [promotion()] if pulls is None else pulls
        pytest.fail(f"Unexpected GitHub request: {path}")

    monkeypatch.setattr(railway, "api", api)
    # configuration is shared with the existing release helper and uses its own API binding.
    monkeypatch.setitem(railway.configuration.__globals__, "api", api)


def test_accepts_reviewed_promotion_with_exact_successful_push_ci(monkeypatch):
    candidate_api(monkeypatch)
    result = railway.resolve(REPO, SHA, "42")
    assert result["candidate_sha"] == SHA
    assert result["promotion_url"].endswith("/123")


@pytest.mark.parametrize("side,key,value", [
    ("head", "ref", "feature"), ("head", "repo", {"full_name": "fork/linger"}),
    ("base", "ref", "main"), ("base", "repo", None),
])
def test_promotion_check_blocks_wrong_branch_or_repository(side, key, value):
    pull = promotion()
    pull[side][key] = value
    with pytest.raises(ValueError, match="same-repository"):
        railway.validate_promotion(pull, REPO)


@pytest.mark.parametrize("pulls", [[], [promotion() | {"merged_at": None}],
                                  [promotion() | {"merge_commit_sha": "b" * 40}]])
def test_direct_push_or_unmerged_pr_cannot_deploy(monkeypatch, pulls):
    candidate_api(monkeypatch, pulls=pulls)
    with pytest.raises(ValueError, match="merged"):
        railway.resolve(REPO, SHA, "42")


@pytest.mark.parametrize("changes", [
    {"head_sha": "b" * 40}, {"event": "pull_request"}, {"event": "workflow_dispatch"},
    {"conclusion": "failure"}, {"status": "in_progress"}, {"head_branch": "main"},
    {"path": ".github/workflows/other.yml"}, {"head_repository": {"full_name": "fork/linger"}},
])
def test_unsuitable_ci_cannot_deploy(monkeypatch, changes):
    candidate_api(monkeypatch, run_changes=changes)
    with pytest.raises(ValueError):
        railway.resolve(REPO, SHA, "42")


def test_completed_ci_for_an_older_release_tip_cannot_replace_a_newer_candidate(monkeypatch):
    candidate_api(monkeypatch, tip="b" * 40)
    with pytest.raises(ValueError, match="stale"):
        railway.resolve(REPO, SHA, "42")


@pytest.mark.parametrize("flag", ["live_evaluations_enabled", "auto_publish_enabled"])
def test_native_route_stops_if_paid_or_image_publication_policy_is_enabled(monkeypatch, flag):
    candidate_api(monkeypatch, policy={
        "live_evaluations_enabled": False, "auto_publish_enabled": False,
        "auto_publish_threshold": 95, flag: True,
    })
    with pytest.raises(ValueError, match="disabled"):
        railway.resolve(REPO, SHA, "42")


def deployment(message, status="SUCCESS"):
    return {"id": "new-deployment", "status": status, "meta": {
        "cliMessage": message, "imageDigest": "sha256:built-by-railpack",
        "serviceManifest": {"build": {"builder": "RAILPACK"}},
        "volumeMounts": ["/var/lib/linger"],
    }}


def test_wait_matches_exact_upload_and_waits_for_health(monkeypatch):
    results = iter([
        [deployment("earlier run")],
        [deployment("this run", "BUILDING"), deployment("earlier run")],
        [deployment("this run"), deployment("earlier run")],
    ])
    sleeps = []
    monkeypatch.setattr(railway, "deployments", lambda: next(results))
    monkeypatch.setattr(railway.time, "sleep", sleeps.append)
    assert railway.wait_for_deployment("this run")["id"] == "new-deployment"
    assert len(sleeps) == 2


@pytest.mark.parametrize("change,reason", [
    ({"status": "FAILED"}, "FAILED"), ({"status": "CRASHED"}, "CRASHED"),
    ({"meta": {"cliMessage": "this run", "serviceManifest": {"build": {"builder": "DOCKERFILE"}}}}, "Railpack"),
    ({"meta": {"cliMessage": "this run", "serviceManifest": {"build": {"builder": "RAILPACK"}}}}, "volume"),
])
def test_failed_build_wrong_builder_or_missing_volume_fails(monkeypatch, change, reason):
    monkeypatch.setattr(railway, "deployments", lambda: [deployment("this run") | copy.deepcopy(change)])
    with pytest.raises(ValueError, match=reason):
        railway.wait_for_deployment("this run")


def test_wait_expires_instead_of_accepting_an_old_healthy_deployment(monkeypatch):
    ticks = iter([0, 0, 11])
    monkeypatch.setattr(railway.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(railway.time, "sleep", lambda _: None)
    monkeypatch.setattr(railway, "deployments", lambda: [deployment("earlier run")])
    with pytest.raises(TimeoutError):
        railway.wait_for_deployment("missing upload", timeout=10)


@pytest.mark.parametrize("http_ready", [True, False])
def test_deploy_records_exact_upload_even_if_public_verification_fails(monkeypatch, tmp_path, http_ready):
    source = tmp_path / "source"
    source.mkdir()
    for name in ("railpack.json", ".railwayignore"):
        (source / name).touch()
    calls = []

    def command(*args, cwd=None):
        calls.append((args, cwd))
        if args[:3] == ("git", "rev-parse", "HEAD"):
            return SHA
        return ""

    monkeypatch.setattr(railway, "command", command)
    monkeypatch.setattr(railway, "resolve", lambda *args: {"candidate_sha": SHA, "ci_run_id": "42"})
    monkeypatch.setenv("GITHUB_RUN_ID", "100")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    message = f"GitHub release {SHA} run 100 attempt 2"
    monkeypatch.setattr(railway, "wait_for_deployment", lambda value: deployment(value))
    def verify():
        if not http_ready:
            raise ValueError("Public API is not ready")
        return {"ready": True, "frontend": True, "provider_calls": 0}

    monkeypatch.setattr(railway, "verify_site", verify)
    output = tmp_path / "evidence.json"
    if http_ready:
        result = railway.deploy(REPO, SHA, "42", source, output)
        assert result["status"] == "success"
    else:
        with pytest.raises(ValueError, match="Public API"):
            railway.deploy(REPO, SHA, "42", source, output)
        result = json.loads(output.read_text())
        assert result["status"] == "failed"
    assert calls[-1] == ((
        "railway", "up", "--project", railway.PROJECT, "--environment", railway.ENVIRONMENT,
        "--service", railway.SERVICE, "--detach", "--yes", "--message", message,
    ), source)
    assert result["deployment_id"] == "new-deployment"
    assert json.loads(output.read_text()) == result


@pytest.mark.parametrize("head,dirty,reason", [("b" * 40, "", "approved"), (SHA, " M source.py", "clean")])
def test_wrong_or_dirty_checkout_never_uploads(monkeypatch, tmp_path, head, dirty, reason):
    def command(*args, cwd=None):
        assert args[0] == "git", "Railway must never be called for an unapproved checkout"
        return head if args[1] == "rev-parse" else dirty

    monkeypatch.setattr(railway, "command", command)
    output = tmp_path / "evidence.json"
    with pytest.raises(ValueError, match=reason):
        railway.deploy(REPO, SHA, "42", tmp_path, output)
    assert json.loads(output.read_text())["status"] == "failed"


@pytest.mark.parametrize("ready,html,expected", [
    ("ready", '<div id="root"></div>', True),
    ("starting", '<div id="root"></div>', False),
    ("ready", "unrelated site", False),
])
def test_http_verification_checks_frontend_and_readiness_without_provider_calls(monkeypatch, ready, html, expected):
    paths = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            paths.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "application/json" if self.path == "/api/ready" else "text/html")
            self.end_headers()
            body = json.dumps({"status": ready}) if self.path == "/api/ready" else html
            self.wfile.write(body.encode())

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    monkeypatch.setattr(railway, "SITE", f"http://127.0.0.1:{server.server_port}")
    try:
        if expected:
            assert railway.verify_site() == {"ready": True, "frontend": True, "provider_calls": 0}
        else:
            with pytest.raises(ValueError):
                railway.verify_site()
        assert set(paths) <= {"/", "/api/ready"}
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
