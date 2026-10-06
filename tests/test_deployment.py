import hashlib
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.backend.accounts import AccountStore
from apps.backend.config import REPO_ROOT, Settings
from apps.backend.deployment import DeploymentReadiness, mount_frontend, verify_model_manifest
from apps.backend.transcripts import TranscriptStore


def settings(**values):
    return Settings(_env_file=None, linger_model="openai:offline", openai_api_key="offline", **values)


def test_host_state_paths_preserved_and_deployed_state_is_separate(tmp_path):
    host = settings()
    assert host.linger_state_dir == REPO_ROOT / "data"
    assert host.linger_memory_dir == REPO_ROOT / "memories"
    deployed = settings(linger_state_dir=tmp_path, linger_memory_dir=tmp_path / "memories")
    assert deployed.linger_state_dir == tmp_path
    assert deployed.linger_memory_dir == tmp_path / "memories"


def test_static_site_never_masks_unknown_api_routes(tmp_path):
    (tmp_path / "index.html").write_text("<h1>Linger</h1>")
    (tmp_path / "app.js").write_text("export const loaded = true")
    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    mount_frontend(app, tmp_path)
    client = TestClient(app)
    assert client.get("/").text == "<h1>Linger</h1>"
    assert client.get("/app.js").status_code == 200
    assert client.get("/api/health").json() == {"status": "ok"}
    for method in ("get", "post", "delete"):
        response = getattr(client, method)("/api/missing")
        assert response.status_code == 404
        assert "<h1>" not in response.text
    assert client.get("/.env").status_code == 404


def test_model_manifest_detects_changed_missing_and_escaping_files(tmp_path):
    weights = tmp_path / "weights.onnx"
    weights.write_bytes(b"local weights")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"files": {"weights.onnx": hashlib.sha256(weights.read_bytes()).hexdigest()}}))
    verify_model_manifest(tmp_path)
    weights.write_bytes(b"different weights")
    with pytest.raises(ValueError, match="checksum"):
        verify_model_manifest(tmp_path)
    weights.unlink()
    with pytest.raises(FileNotFoundError):
        verify_model_manifest(tmp_path)
    manifest.write_text(json.dumps({"files": {"../outside": "irrelevant"}}))
    with pytest.raises(ValueError, match="outside"):
        verify_model_manifest(tmp_path)


@pytest.fixture
def readiness(tmp_path, monkeypatch):
    from src.linger.orchestration.grounding import librarian_service
    from conftest import TermEmbedding, TermReranker

    monkeypatch.setattr(librarian_service, "_embedding", TermEmbedding())
    monkeypatch.setattr(librarian_service, "_reranker", TermReranker())
    AccountStore(tmp_path / "accounts.sqlite3")
    TranscriptStore(tmp_path / "transcripts.sqlite3")
    return DeploymentReadiness(settings(
        linger_state_dir=tmp_path, linger_memory_dir=tmp_path / "memories",
    ))


def test_readiness_rechecks_storage_after_success(readiness):
    readiness.check()
    assert readiness.ready
    # Missing storage must fail without silently creating a new empty database.
    path = readiness.settings.linger_state_dir / "accounts.sqlite3"
    path.unlink()
    readiness.check()
    assert not readiness.ready
    assert readiness.result == {"status": "not_ready", "check": "storage"}
    assert not path.exists()
    AccountStore(path)
    readiness.check()
    assert readiness.ready


def test_readiness_detects_corrupt_database_after_success(readiness):
    readiness.check()
    assert readiness.ready
    (readiness.settings.linger_state_dir / "transcripts.sqlite3").write_bytes(b"corrupt database")
    readiness.check()
    assert readiness.result == {"status": "not_ready", "check": "storage"}
    assert not readiness.ready


def test_readiness_rejects_unknown_corpus(readiness):
    readiness.settings.allowed_book_version_ids = ("missing-corpus",)
    readiness.check()
    assert readiness.result == {"status": "not_ready", "check": "corpus"}


def test_readiness_rejects_missing_packaged_models(readiness, tmp_path, monkeypatch):
    readiness.settings.linger_static_dir = tmp_path
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_path / "absent"))
    readiness.check()
    assert readiness.result == {"status": "not_ready", "check": "local_models"}
