"""Book identity is shared, catalogue-bound, and independent of chapter progress."""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from corpus_fixtures import fake_registration
from src.linger.corpus import registry
from src.linger.corpus.alice import BOOK_VERSION_ID
from src.linger.corpus.registry import BookClarification, ResolvedBook


class BookRegistryTests(unittest.TestCase):
    def test_shipped_registry_has_no_registration_errors(self) -> None:
        self.assertEqual((), registry.registration_errors())

    def test_reviewed_names_normalize_case_quotes_and_whitespace(self) -> None:
        for name in ("  ALICE   IN WONDERLAND. ", "Alice’s Adventures in Wonderland", "pg11"):
            with self.subTest(name=name):
                result = registry.resolve_book_identity(name, (BOOK_VERSION_ID,), exact=True)
                self.assertIsInstance(result, ResolvedBook)
                self.assertEqual("pg11", result.registration.book.work_id)

    def test_candidate_alias_is_never_a_confirmed_identity(self) -> None:
        result = registry.resolve_book_identity("Wonderland", (BOOK_VERSION_ID,), exact=True)
        self.assertIsInstance(result, BookClarification)

    def test_exact_mode_does_not_extract_a_book_from_unrelated_prose(self) -> None:
        result = registry.resolve_book_identity(
            "The snow made a winter wonderland.", (BOOK_VERSION_ID,), exact=True
        )
        self.assertIsNone(result)

    def test_author_can_disambiguate_the_same_title(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = fake_registration(root, work_id="first", catalog={
                "title": "The Notebook", "author": "Avery Reed", "chapters": [],
            })
            second = fake_registration(root, work_id="second", catalog={
                "title": "The Notebook", "author": "Morgan Lake", "chapters": [],
            })
            with patch.object(registry, "CORPORA", {"first": first, "second": second}):
                allowed = (first.book.book_version_id, second.book.book_version_id)
                self.assertEqual((), registry.registration_errors())
                self.assertIsInstance(
                    registry.resolve_book_identity("The Notebook", allowed), BookClarification
                )
                for exact, text in (
                    (True, "The Notebook by Morgan Lake"),
                    (False, "What does The Notebook by Morgan Lake say about identity?"),
                ):
                    with self.subTest(exact=exact):
                        result = registry.resolve_book_identity(text, allowed, exact=exact)
                        self.assertIsInstance(result, ResolvedBook)
                        self.assertEqual("second", result.registration.book.work_id)

    def test_unavailable_identity_is_not_replaced_by_an_allowed_shorter_alias(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = fake_registration(root, work_id="first", catalog={
                "title": "The Orchard Notebook", "chapters": [],
            })
            second = replace(fake_registration(root, work_id="second", catalog={
                "title": "A Different Garden", "chapters": [],
            }), aliases=("orchard",))
            with patch.object(registry, "CORPORA", {"first": first, "second": second}):
                result = registry.resolve_book_identity(
                    "The Orchard Notebook", (second.book.book_version_id,)
                )
                self.assertIsInstance(result, BookClarification)
                self.assertEqual((), result.candidates)

    def test_registration_reports_name_collisions_but_allows_shared_candidate_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = replace(fake_registration(root, work_id="first", catalog={
                "title": "The Orchard Notebook", "chapters": [],
            }), aliases=("the notebook",))
            second = replace(fake_registration(root, work_id="second", catalog={
                "title": "The Garden Notebook", "chapters": [],
            }), aliases=("the notebook",))
            with patch.object(registry, "CORPORA", {"first": first, "second": second}):
                self.assertTrue(any("Name collision" in item for item in registry.registration_errors()))
            with patch.object(registry, "CORPORA", {
                "first": replace(first, aliases=(), candidate_aliases=("notebook",)),
                "second": replace(second, aliases=(), candidate_aliases=("notebook",)),
            }):
                self.assertEqual((), registry.registration_errors())

    def test_registration_reports_alias_embedded_in_another_books_title(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = fake_registration(root, work_id="first", catalog={
                "title": "The Orchard Notebook", "chapters": [],
            })
            second = replace(fake_registration(root, work_id="second", catalog={
                "title": "A Different Garden", "chapters": [],
            }), aliases=("orchard",))
            with patch.object(registry, "CORPORA", {"first": first, "second": second}):
                self.assertTrue(any("Alias overlap" in item for item in registry.registration_errors()))

    def test_registration_rejects_promoting_another_books_candidate_alias(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = replace(fake_registration(root, work_id="first", catalog={
                "title": "The Orchard Notebook", "chapters": [],
            }), candidate_aliases=("notebook",))
            second = replace(fake_registration(root, work_id="second", catalog={
                "title": "The Garden Notebook", "chapters": [],
            }), aliases=("notebook",))
            with patch.object(registry, "CORPORA", {"first": first, "second": second}):
                self.assertTrue(any(
                    "candidate alias of first" in item for item in registry.registration_errors()
                ))
