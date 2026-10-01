"""Offline deployment readiness and same-origin static assets."""

import hashlib
import json
import logging
import os
import sqlite3
import tempfile
import threading
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI
from starlette.routing import Router
from starlette.staticfiles import StaticFiles

from .config import Settings


def mount_frontend(app: FastAPI, directory: Path) -> None:
    # Mounted last: unknown API routes cannot fall through into the static site.
    app.mount("/api", Router())
    app.mount("/", StaticFiles(directory=directory, html=True))


def verify_model_manifest(cache: Path) -> None:
    manifest = json.loads((cache / "manifest.json").read_text())
    files = manifest["files"]
    if not files:
        raise ValueError("empty model manifest")
    for name, expected in files.items():
        path = cache / name
        if not path.resolve().is_relative_to(cache.resolve()):
            raise ValueError("model file outside cache")
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise ValueError("model file checksum mismatch")


class DeploymentReadiness:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.ready = False
        self._immutable_ready = False
        self.result: dict[str, str] = {"status": "not_ready", "check": "startup"}
        self._lock = threading.Lock()

    def check(self) -> None:
        with self._lock:
            stage = "configuration"
            try:
                provider, _, model = self.settings.linger_model.partition(":")
                if not model:
                    raise ValueError("model must name a provider")
                self.settings.api_key_for(provider)
                stage = "storage"
                for directory in (self.settings.linger_state_dir, self.settings.linger_memory_dir):
                    directory.mkdir(parents=True, exist_ok=True)
                    with tempfile.TemporaryFile(dir=directory) as stream:
                        stream.write(b"readiness")
                        stream.flush()
                        os.fsync(stream.fileno())
                for filename, table in (("accounts.sqlite3", "accounts"), ("transcripts.sqlite3", "transcript_sessions")):
                    uri = (self.settings.linger_state_dir / filename).resolve().as_uri() + "?mode=rw"
                    with closing(sqlite3.connect(uri, uri=True)) as conn:
                        if conn.execute("PRAGMA quick_check").fetchone() != ("ok",):
                            raise ValueError("database integrity failure")
                        conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
                        conn.execute("BEGIN IMMEDIATE")
                        conn.rollback()
                if self._immutable_ready:
                    self.ready = True
                    self.result = {"status": "ready"}
                    return
                stage = "corpus"
                from src.linger.corpus.registry import CORPORA, registration_errors
                from src.linger.corpus.units import load_units, read_unit

                if registration_errors():
                    raise ValueError("invalid corpus registration")
                allowed = set(self.settings.allowed_book_version_ids)
                registrations = [r for r in CORPORA.values() if r.book.book_version_id in allowed]
                if {r.book.book_version_id for r in registrations} != allowed:
                    raise ValueError("unknown permitted corpus")
                for registration in registrations:
                    for unit in load_units(registration):
                        read_unit(registration, unit)
                stage = "local_models"
                cache = os.environ.get("FASTEMBED_CACHE_PATH")
                if self.settings.linger_static_dir is not None:
                    if not cache:
                        raise ValueError("missing packaged model cache")
                    verify_model_manifest(Path(cache))
                from fastembed import TextEmbedding
                from fastembed.rerank.cross_encoder import TextCrossEncoder
                from apps.backend.hybrid_librarian import EMBEDDING_MODEL, RERANKER_MODEL
                from apps.backend.rerank_windows import TokenWindowReranker
                from src.linger.orchestration.grounding import librarian_service

                if librarian_service._embedding is None:
                    librarian_service._embedding = TextEmbedding(
                        model_name=EMBEDDING_MODEL, local_files_only=True,
                    )
                if librarian_service._reranker is None:
                    librarian_service._reranker = TokenWindowReranker(TextCrossEncoder(
                        model_name=RERANKER_MODEL, local_files_only=True,
                    ))
                list(librarian_service._embedding.query_embed("readiness"))
                list(librarian_service._reranker.rerank("readiness", ["A reader opens a book."]))
                stage = "frontend"
                if self.settings.linger_static_dir is not None:
                    if not (self.settings.linger_static_dir / "index.html").is_file():
                        raise ValueError("missing frontend")
            except Exception:
                self.ready = False
                self.result = {"status": "not_ready", "check": stage}
                logging.getLogger(__name__).error("Deployment readiness failed: %s", stage)
            else:
                self._immutable_ready = True
                self.ready = True
                self.result = {"status": "ready"}
