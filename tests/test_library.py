"""Reader shelves preserve literary locations and serve exact granted source text."""

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
from src.linger.corpus.douglass import BOOK as DOUGLASS
from src.linger.corpus.story_of_my_life import BOOK as KELLER
from src.linger.corpus import registry

with patch.dict(os.environ, {"LINGER_MODEL": "google:gemini-2.5-flash", "GOOGLE_API_KEY": "test-key"}):
    from apps.backend import main, sessions

BOOKS = (ALICE, ANIMAL_FARM, PINOCCHIO, DOUGLASS, KELLER)


class LibraryEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(_env_file=None, linger_model="google:gemini-2.5-flash")
        main.app.dependency_overrides[get_settings] = lambda: self.settings
        self.addCleanup(main.app.dependency_overrides.pop, get_settings)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    def test_shelf_preserves_natural_chapters_and_parts_without_opening_bodies(self) -> None:
        original = Path.read_text

        def metadata_only(path, *args, **kwargs):
            self.assertEqual("catalog.json", path.name)
            return original(path, *args, **kwargs)

        with patch.object(Path, "read_text", autospec=True, side_effect=metadata_only):
            response = self.client.get("/api/library")
        self.assertEqual(200, response.status_code)
        books = {book["work_id"]: book for book in response.json()}
        self.assertEqual({book.work_id for book in BOOKS}, set(books))
        for book in BOOKS:
            shelf = books[book.work_id]
            start = next(unit for unit in shelf["units"] if unit["unit_id"] == shelf["start_unit_id"])
            self.assertEqual(("main", 1, "chapter"), (start["part_id"], start["chapter_number"], start["kind"]))
        douglass = books[DOUGLASS.work_id]
        self.assertEqual("pg23-vd3f08ac3-sec04", douglass["start_unit_id"])
        self.assertIsNone(douglass["units"][0]["chapter_number"])
        keller = books[KELLER.work_id]
        self.assertEqual("pg2397-vb3cc1e13-sec003", keller["start_unit_id"])
        repeated = [unit for unit in keller["units"] if unit["chapter_number"] == 1]
        self.assertEqual({"main", "part-iii"}, {unit["part_id"] for unit in repeated})
        self.assertEqual(2, len({unit["label"] for unit in repeated}))
        letters = [unit for unit in keller["units"] if unit["kind"] == "letter"]
        self.assertTrue(letters)
        self.assertTrue(all(unit["chapter_number"] is None and unit["label"] for unit in letters))

    def test_exact_revision_grants_filter_shelf_and_deny_before_read(self) -> None:
        self.settings = self.settings.model_copy(update={"allowed_book_version_ids": (ALICE.book_version_id, "pg2397-wrong-revision")})
        response = self.client.get("/api/library")
        self.assertEqual(200, response.status_code)
        self.assertEqual([ALICE.work_id], [book["work_id"] for book in response.json()])
        with patch.object(Path, "read_text", side_effect=AssertionError("denied book opened")):
            for book in BOOKS[1:]:
                response = self.client.get(f"/api/library/{book.work_id}/{book.book_version_id}/units/any")
                self.assertEqual(404, response.status_code)

    def test_each_book_serves_exact_source_for_first_and_last_narrative_chapters(self) -> None:
        shelves = {book["work_id"]: book for book in self.client.get("/api/library").json()}
        for book in BOOKS:
            with self.subTest(book=book.title):
                catalog = json.loads((book.default_output / "catalog.json").read_text())
                entries = catalog.get("chapters", catalog.get("sections"))
                source = book.parse_source(book.default_source)
                expected = {
                    entry.get("chapter_id", entry.get("section_id")): parsed.body
                    for entry, parsed in zip(entries, source, strict=True)
                }
                chapters = [unit for unit in shelves[book.work_id]["units"] if unit["part_id"] == "main" and unit["kind"] == "chapter"]
                for unit in (chapters[0], chapters[-1]):
                    response = self.client.get(f"/api/library/{book.work_id}/{book.book_version_id}/units/{unit['unit_id']}")
                    self.assertEqual(200, response.status_code)
                    self.assertEqual({"text": expected[unit["unit_id"]]}, response.json())

    def test_named_letter_and_supplementary_chapter_have_independent_exact_text(self) -> None:
        shelf = next(book for book in self.client.get("/api/library").json() if book["work_id"] == KELLER.work_id)
        letter = next(unit for unit in shelf["units"] if unit["kind"] == "letter")
        supplementary = next(unit for unit in shelf["units"] if unit["part_id"] == "part-iii" and unit["chapter_number"] == 1)
        catalog = json.loads((KELLER.default_output / "catalog.json").read_text())
        source = KELLER.parse_source(KELLER.default_source)
        expected = {entry["section_id"]: parsed.body for entry, parsed in zip(catalog["sections"], source, strict=True)}
        for unit in (letter, supplementary):
            response = self.client.get(f"/api/library/{KELLER.work_id}/{KELLER.book_version_id}/units/{unit['unit_id']}")
            self.assertEqual(200, response.status_code)
            self.assertEqual({"text": expected[unit["unit_id"]]}, response.json())

    def test_unknown_books_revisions_and_locations_are_unavailable(self) -> None:
        for path in (
            f"unknown/{ALICE.book_version_id}/units/{ALICE.book_version_id}-ch01",
            f"{ALICE.work_id}/{PINOCCHIO.book_version_id}/units/{ALICE.book_version_id}-ch01",
            f"{ALICE.work_id}/{ALICE.book_version_id}/units/missing",
            f"{ALICE.work_id}/{ALICE.book_version_id}/units/{KELLER.book_version_id}-sec003",
            f"{ALICE.work_id}/{ALICE.book_version_id}/chapters/1",
        ):
            with self.subTest(path=path):
                self.assertEqual(404, self.client.get(f"/api/library/{path}").status_code)

    def test_corrupt_catalog_or_body_cannot_serve_another_location(self) -> None:
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
                    response = self.client.get(f"/api/library/{ALICE.work_id}/{ALICE.book_version_id}/units/{chapter['chapter_id']}")
                self.assertEqual(503, response.status_code)
                self.assertNotIn("text", response.json())

    def test_reading_does_not_change_chat_history_or_progress_authority(self) -> None:
        session_id = "library-reader-test"
        self.addCleanup(sessions.clear, session_id)
        sessions.set_book_selection(session_id, sessions.BookSelection(book_id=ALICE.work_id))
        sessions.set_reading_candidate(session_id, sessions.ReadingCandidate(book_id=ALICE.work_id, chapter=2))
        before = sessions.snapshot_reading_state(session_id)
        catalog = json.loads((PINOCCHIO.default_output / "catalog.json").read_text())
        unit_id = catalog["chapters"][-1]["chapter_id"]
        response = self.client.get(f"/api/library/{PINOCCHIO.work_id}/{PINOCCHIO.book_version_id}/units/{unit_id}", params={"session_id": session_id})
        self.assertEqual(200, response.status_code)
        self.assertEqual(before, sessions.snapshot_reading_state(session_id))
        self.assertEqual([], sessions.history(session_id))
        self.assertEqual((), sessions.reader_statements(session_id))
