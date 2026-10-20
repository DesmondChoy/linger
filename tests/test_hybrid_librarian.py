"""Tests for the measured production Librarian retrieval strategy."""

import re
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np

from apps.backend.contracts import BookScope, LibrarianRequest
from apps.backend.hybrid_librarian import (
    EMBEDDING_MODEL,
    RERANKER_MODEL,
    HybridLibrarian,
)
from src.linger.corpus import registry
from src.linger.corpus.alice import BOOK, BOOK_VERSION_ID, WORK_ID
from src.linger.corpus.animal_farm import BOOK as ANIMAL_FARM
from src.linger.corpus.pinocchio import BOOK as PINOCCHIO


WORDS = re.compile(r"[a-z]+")


class ConstantEmbedding:
    """Makes semantic retrieval deterministic; the reranker decides relevance."""

    def passage_embed(self, documents: list[str]):
        return iter(np.ones((len(documents), 2)))

    def query_embed(self, query: str):
        return iter((np.ones(2),))


class TermReranker:
    def rerank(self, query: str, documents: list[str]):
        terms = set(WORDS.findall(query.casefold()))
        return [10.0 if terms & set(WORDS.findall(document.casefold())) else -10.0 for document in documents]


class RecordingEmbedding(ConstantEmbedding):
    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def passage_embed(self, documents: list[str]):
        self.batches.append(documents)
        return super().passage_embed(documents)


class RecordingReranker(TermReranker):
    def __init__(self) -> None:
        self.documents: list[str] = []

    def rerank(self, query: str, documents: list[str]):
        self.documents.extend(documents)
        return super().rerank(query, documents)


def pinocchio_scope(chapter_max: int) -> BookScope:
    return BookScope(
        work_id=PINOCCHIO.work_id, book_version_id=PINOCCHIO.book_version_id, chapter_max=chapter_max
    )


def request(query: str, *, chapter_max: int = 5) -> LibrarianRequest:
    return LibrarianRequest(
        query=query,
        book_scopes=[
            BookScope(
                work_id=WORK_ID,
                book_version_id=BOOK_VERSION_ID,
                chapter_max=chapter_max,
            )
        ],
    )


class HybridLibrarianTests(unittest.TestCase):
    def setUp(self) -> None:
        self.librarian = HybridLibrarian(
            embedding_model=ConstantEmbedding(), reranker=TermReranker()
        )

    def test_selected_models_are_versioned(self) -> None:
        self.assertEqual("BAAI/bge-small-en-v1.5", EMBEDDING_MODEL)
        self.assertEqual("Xenova/ms-marco-MiniLM-L-6-v2", RERANKER_MODEL)

    def test_returns_exact_canonical_evidence(self) -> None:
        bundle = self.librarian.retrieve(
            request("Why can Alice not explain herself to the Caterpillar?")
        )

        self.assertTrue(bundle.items)
        source_lines = BOOK.default_source.read_text(encoding="utf-8").splitlines()
        for item in bundle.items:
            with self.subTest(evidence_id=item.evidence_id):
                start, end = item.source_lines
                self.assertEqual("\n".join(source_lines[start - 1 : end]), item.excerpt)
                self.assertEqual(
                    f"{item.chapter_id}-ln{start:04d}-{end:04d}", item.evidence_id
                )

    def test_unrelated_query_is_removed_by_reranker(self) -> None:
        bundle = self.librarian.retrieve(request("spaceship nebula"))
        self.assertEqual([], bundle.items)

    def test_new_chapter_books_use_the_shared_hybrid_pipeline(self) -> None:
        for book, query in ((ANIMAL_FARM, "Major dream"), (PINOCCHIO, "Master Cherry")):
            with self.subTest(book=book.title):
                source_lines = book.default_source.read_text(encoding="utf-8").splitlines()
                bundle = self.librarian.retrieve(LibrarianRequest(
                    query=query,
                    book_scopes=[BookScope(
                        work_id=book.work_id,
                        book_version_id=book.book_version_id,
                        chapter_max=1,
                    )],
                ))
                self.assertTrue(bundle.items)
                for item in bundle.items:
                    self.assertEqual(book.work_id, item.work_id)
                    self.assertEqual(book.book_version_id, item.book_version_id)
                    self.assertEqual(1, item.chapter)
                    start, end = item.source_lines
                    self.assertEqual("\n".join(source_lines[start - 1:end]), item.excerpt)
                    self.assertEqual(item.excerpt, self.librarian.fetch_by_id(item.evidence_id).text)

    def test_duplicate_query_returns_stable_evidence_ids(self) -> None:
        first = self.librarian.retrieve(request("Caterpillar identity"))
        second = self.librarian.retrieve(request("Caterpillar identity"))
        self.assertEqual(
            [item.evidence_id for item in first.items],
            [item.evidence_id for item in second.items],
        )

    def test_equivalent_full_book_ceilings_reuse_embeddings(self) -> None:
        embedding = self.librarian._embedding_model()
        with patch.object(
            embedding, "passage_embed", wraps=embedding.passage_embed
        ) as embed:
            bundles = [
                self.librarian.retrieve(request("Alice", chapter_max=ceiling))
                for ceiling in (12, 13, 1000)
            ]

        self.assertEqual(1, embed.call_count)
        self.assertTrue(bundles[0].items)
        self.assertEqual(bundles[0].items, bundles[1].items)
        self.assertEqual(bundles[0].items, bundles[2].items)

    def test_lower_ceiling_builds_separate_spoiler_bounded_index(self) -> None:
        self.librarian.retrieve(request("Alice", chapter_max=1000))
        opened: list[Path] = []
        original = Path.read_text

        def recording_read(path: Path, *args, **kwargs):
            opened.append(path)
            return original(path, *args, **kwargs)

        embedding = self.librarian._embedding_model()
        with (
            patch.object(Path, "read_text", autospec=True, side_effect=recording_read),
            patch.object(
                embedding, "passage_embed", wraps=embedding.passage_embed
            ) as embed,
        ):
            bundle = self.librarian.retrieve(request("Alice", chapter_max=4))

        self.assertEqual(1, embed.call_count)
        self.assertTrue(bundle.items)
        self.assertTrue(all(item.chapter <= 4 for item in bundle.items))
        chapter_paths = [path for path in opened if path.suffix == ".md"]
        self.assertEqual(4, len(chapter_paths))
        self.assertTrue(
            all(int(path.name.split("-", 1)[0]) <= 4 for path in chapter_paths)
        )

    def test_fetch_by_id_inherits_exact_lookup_without_initializing_models(self) -> None:
        librarian = HybridLibrarian()

        with (
            patch.object(
                librarian,
                "_embedding_model",
                side_effect=AssertionError("fetch initialized embeddings"),
            ),
            patch.object(
                librarian,
                "_reranker_model",
                side_effect=AssertionError("fetch initialized reranker"),
            ),
        ):
            record = librarian.fetch_by_id(
                "pg11-v01b38ea4-ch05-ln0960-1016"
            )

        self.assertIsNotNone(record)
        assert record is not None
        source_lines = BOOK.default_source.read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            "\n".join(source_lines[record.source_lines[0] - 1 : record.source_lines[1]]),
            record.text,
        )
        self.assertEqual({}, librarian._indexes)

    def test_forbidden_chapter_is_never_opened_or_returned(self) -> None:
        opened: list[Path] = []
        original = Path.read_text

        def recording_read(path: Path, *args, **kwargs):
            opened.append(path)
            return original(path, *args, **kwargs)

        with patch.object(Path, "read_text", autospec=True, side_effect=recording_read):
            bundle = self.librarian.retrieve(request("Caterpillar", chapter_max=4))

        self.assertTrue(all(item.chapter <= 4 for item in bundle.items))
        self.assertFalse(any("05-advice-from-a-caterpillar" in str(path) for path in opened))
        self.assertFalse(any("06-pig-and-pepper" in str(path) for path in opened))

    def test_search_reads_revised_chapter_cues_but_returns_canonical_text(self) -> None:
        registration = registry.CORPORA[PINOCCHIO.work_id]
        pinocchio_request = LibrarianRequest(query="zanzibarine", book_scopes=[pinocchio_scope(3)])
        embedding, reranker = RecordingEmbedding(), RecordingReranker()
        librarian = HybridLibrarian(embedding_model=embedding, reranker=reranker, read_chapter_cues=True)
        production_embedding = RecordingEmbedding()
        production = HybridLibrarian(embedding_model=production_embedding, reranker=TermReranker())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / registration.root.name
            shutil.copytree(registration.root, root)
            with patch.dict(registry.CORPORA, {PINOCCHIO.work_id: replace(registration, root=root)}):
                self.assertEqual([], librarian.retrieve(pinocchio_request).items)
                self.assertEqual([], production.retrieve(pinocchio_request).items)
                for path in (root / "catalog.json", root / "chapters" / "01-chapter-01.md"):
                    text = path.read_text(encoding="utf-8")
                    path.write_text(text.replace('"talking firewood"', '"zanzibarine relic"', 1), encoding="utf-8")
                bundle = librarian.retrieve(pinocchio_request)
                keyword = librarian._bm25("zanzibarine", librarian._index(pinocchio_request))
                # Production search ignores cues unless the experiment opts in.
                self.assertEqual([], production.retrieve(pinocchio_request).items)

        self.assertEqual(2, len(embedding.batches))
        self.assertEqual(1, len(production_embedding.batches))
        self.assertTrue(keyword)
        self.assertTrue(any("zanzibarine relic" in document for document in embedding.batches[1]))
        self.assertTrue(any("zanzibarine relic" in document for document in reranker.documents))
        self.assertTrue(bundle.items)
        source_lines = PINOCCHIO.default_source.read_text(encoding="utf-8").splitlines()
        for item in bundle.items:
            self.assertEqual(1, item.chapter)
            start, end = item.source_lines
            self.assertEqual("\n".join(source_lines[start - 1:end]), item.excerpt)
            self.assertNotIn("zanzibarine", item.excerpt)

    def test_later_chapter_cues_never_reach_an_earlier_reader(self) -> None:
        opened: list[Path] = []
        original = Path.read_text

        def recording_read(path: Path, *args, **kwargs):
            opened.append(path)
            return original(path, *args, **kwargs)

        embedding, reranker = RecordingEmbedding(), RecordingReranker()
        librarian = HybridLibrarian(embedding_model=embedding, reranker=reranker, read_chapter_cues=True)
        with patch.object(Path, "read_text", autospec=True, side_effect=recording_read):
            bundle = librarian.retrieve(LibrarianRequest(
                # Chapter 11's cues; the reader has only reached chapter 3.
                query="compassionate sneezing sacrifice for Harlequin",
                book_scopes=[pinocchio_scope(3)],
            ))

        self.assertTrue(all(item.chapter <= 3 for item in bundle.items))
        chapter_paths = [path for path in opened if path.suffix == ".md"]
        self.assertTrue(chapter_paths)
        self.assertTrue(all(int(path.name.split("-", 1)[0]) <= 3 for path in chapter_paths))
        later_cues = {
            cue
            for unit in librarian.units_for(PINOCCHIO.work_id, PINOCCHIO.book_version_id)
            if unit.chapter_number > 3
            for cue in unit.retrieval_cues
        }
        searched = [*(document for batch in embedding.batches for document in batch), *reranker.documents]
        self.assertTrue(searched)
        self.assertFalse([cue for cue in later_cues for document in searched if cue in document])

    def test_reordered_scopes_reuse_one_cue_index(self) -> None:
        embedding = RecordingEmbedding()
        librarian = HybridLibrarian(embedding_model=embedding, reranker=TermReranker(), read_chapter_cues=True)
        scopes = [
            BookScope(work_id=WORK_ID, book_version_id=BOOK_VERSION_ID, chapter_max=2),
            pinocchio_scope(2),
        ]
        first = librarian.retrieve(LibrarianRequest(query="Alice Geppetto", book_scopes=scopes))
        second = librarian.retrieve(LibrarianRequest(query="Alice Geppetto", book_scopes=scopes[::-1]))

        self.assertEqual(1, len(embedding.batches))
        self.assertEqual(first.items, second.items)

if __name__ == "__main__":
    unittest.main()
