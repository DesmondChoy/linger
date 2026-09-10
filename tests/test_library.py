"""Reader shelves and chapters follow the granted canonical book registry."""

import json
import os
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.backend.config import Settings, get_settings
from src.linger.corpus.alice import BOOK as ALICE
from src.linger.corpus.animal_farm import BOOK as ANIMAL_FARM
from src.linger.corpus.pinocchio import BOOK as PINOCCHIO
from src.linger.corpus import registry

with patch.dict(os.environ, {"LINGER_MODEL": "google:gemini-2.5-flash", "GOOGLE_API_KEY": "test-key"}):
    from apps.backend import main, sessions


class LibraryEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(_env_file=None, linger_model="google:gemini-2.5-flash")
        main.app.dependency_overrides[get_settings] = lambda: self.settings
        self.addCleanup(main.app.dependency_overrides.pop, get_settings)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    def test_shelf_lists_all_enabled_books_without_opening_chapter_bodies(self) -> None:
        original = Path.read_text

        def metadata_only(path, *args, **kwargs):
            self.assertEqual("catalog.json", path.name)
            return original(path, *args, **kwargs)

        with patch.object(Path, "read_text", autospec=True, side_effect=metadata_only):
            response = self.client.get("/api/library")
        self.assertEqual(200, response.status_code)
        books = response.json()
        self.assertEqual([ALICE.work_id, ANIMAL_FARM.work_id, PINOCCHIO.work_id], [book["work_id"] for book in books])
        self.assertEqual([12, 10, 36], [len(book["chapters"]) for book in books])
        self.assertEqual(PINOCCHIO.author, books[2]["author"])
        self.assertEqual({"number", "title", "summary"}, set(books[1]["chapters"][0]))

    def test_exact_revision_grants_filter_shelf_and_deny_chapter_before_read(self) -> None:
        self.settings = self.settings.model_copy(update={"allowed_book_version_ids": (ALICE.book_version_id, "pg500-wrong-revision")})
        response = self.client.get("/api/library")
        self.assertEqual(200, response.status_code)
        self.assertEqual([ALICE.work_id], [book["work_id"] for book in response.json()])
        with patch.object(Path, "read_text", side_effect=AssertionError("denied book opened")):
            for book in (ANIMAL_FARM, PINOCCHIO):
                response = self.client.get(f"/api/library/{book.work_id}/{book.book_version_id}/chapters/1")
                self.assertEqual(404, response.status_code)

    def test_each_book_serves_its_exact_canonical_chapter(self) -> None:
        for book in (ALICE, ANIMAL_FARM, PINOCCHIO):
            with self.subTest(book=book.title):
                catalog = json.loads((book.default_output / "catalog.json").read_text())
                source_chapters = book.parse_source(book.default_source)
                for chapter in (catalog["chapters"][0], catalog["chapters"][-1]):
                    expected = source_chapters[chapter["chapter_number"] - 1].body
                    response = self.client.get(f"/api/library/{book.work_id}/{book.book_version_id}/chapters/{chapter['chapter_number']}")
                    self.assertEqual(200, response.status_code)
                    self.assertEqual({"text": expected}, response.json())

    def test_unknown_books_revisions_and_chapters_are_unavailable(self) -> None:
        for path in (
            f"unknown/{ALICE.book_version_id}/chapters/1",
            f"{ALICE.work_id}/{PINOCCHIO.book_version_id}/chapters/1",
            f"{ALICE.work_id}/{ALICE.book_version_id}/chapters/0",
            f"{ALICE.work_id}/{ALICE.book_version_id}/chapters/13",
        ):
            with self.subTest(path=path):
                self.assertEqual(404, self.client.get(f"/api/library/{path}").status_code)

    def test_corrupt_catalog_or_body_cannot_serve_another_chapter(self) -> None:
        registration = registry.CORPORA[ALICE.work_id]
        original_catalog = (registration.root / "catalog.json").read_text()
        for corruption in ("identity", "path", "body"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                catalog = json.loads(original_catalog)
                chapter = catalog["chapters"][0]
                chapter_path = root / chapter["path"]
                chapter_path.parent.mkdir()
                body = (registration.root / chapter["path"]).read_text()
                if corruption == "identity":
                    catalog["book_version_id"] = PINOCCHIO.book_version_id
                elif corruption == "path":
                    chapter["path"] = "../outside.md"
                else:
                    body += "Unreviewed chapter addition.\n"
                chapter_path.write_text(body)
                (root / "catalog.json").write_text(json.dumps(catalog))
                with patch.dict(registry.CORPORA, {ALICE.work_id: replace(registration, root=root)}):
                    response = self.client.get(f"/api/library/{ALICE.work_id}/{ALICE.book_version_id}/chapters/1")
                self.assertEqual(503, response.status_code)
                self.assertNotIn("text", response.json())

    def test_reading_does_not_change_chat_history_or_progress_authority(self) -> None:
        session_id = "library-reader-test"
        self.addCleanup(sessions.clear, session_id)
        sessions.set_book_selection(session_id, sessions.BookSelection(book_id=ALICE.work_id))
        sessions.set_reading_candidate(session_id, sessions.ReadingCandidate(book_id=ALICE.work_id, chapter=2))
        before = sessions.snapshot_reading_state(session_id)
        response = self.client.get(f"/api/library/{PINOCCHIO.work_id}/{PINOCCHIO.book_version_id}/chapters/36", params={"session_id": session_id})
        self.assertEqual(200, response.status_code)
        self.assertEqual(before, sessions.snapshot_reading_state(session_id))
        self.assertEqual([], sessions.history(session_id))
        self.assertEqual((), sessions.reader_statements(session_id))
