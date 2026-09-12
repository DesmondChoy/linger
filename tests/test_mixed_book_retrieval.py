"""Natural chapter and exact-unit boundaries across both retrieval engines."""
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.backend.contracts import BookScope, LibrarianRequest
from apps.backend.librarian import CorpusScopeError, Librarian
from apps.backend.hybrid_librarian import HybridLibrarian
from src.linger.corpus.registry import CORPORA
from src.linger.corpus.units import load_units
from test_hybrid_librarian import ConstantEmbedding, TermReranker


class MixedBookRetrievalTests(unittest.TestCase):
    def test_search_opens_only_permitted_units_and_preserves_locations(self):
        for work_id, part_id, chapter_max, unit_order, query in (
            ('pg23', 'main', 1, 4, 'mother'),
            ('pg2397', 'main', 1, 3, 'garden'),
            ('pg2397', 'part-iii', 1, 136, 'book'),
            ('pg2397', 'letters', None, 27, 'helen'),
            ('pg23', 'frontmatter', None, 1, 'Douglass'),
        ):
            registration = CORPORA[work_id]
            unit = next(unit for unit in load_units(registration) if unit.order == unit_order)
            scope = BookScope(
                work_id=work_id, book_version_id=registration.book.book_version_id,
                part_id=part_id, chapter_max=chapter_max,
                unit_ids=(unit.chapter_id,) if chapter_max is None else (),
            )
            for retriever in (Librarian(), HybridLibrarian(embedding_model=ConstantEmbedding(), reranker=TermReranker())):
                with self.subTest(work=work_id, part=part_id, engine=type(retriever).__name__):
                    opened = []
                    original = Path.read_text
                    def track(path, *args, **kwargs):
                        if path.suffix == '.md':
                            opened.append(path)
                        return original(path, *args, **kwargs)
                    with patch.object(Path, 'read_text', autospec=True, side_effect=track):
                        bundle = retriever.retrieve(LibrarianRequest(query=query, book_scopes=[scope]))
                        self.assertTrue(bundle.items)
                        for item in bundle.items:
                            self.assertEqual(unit.chapter_id, item.chapter_id)
                            self.assertEqual(chapter_max, item.chapter)
                            self.assertEqual(part_id, item.part_id)
                            self.assertIn(unit.label, item.location)
                            record = retriever.fetch_by_id(item.evidence_id)
                            self.assertEqual(item.excerpt, record.text)
                            self.assertEqual(part_id, record.part_id)
                            self.assertEqual(chapter_max, record.chapter_number)
                    self.assertEqual({registration.root / unit.path}, set(opened))

    def test_hybrid_cache_cannot_reuse_another_part_or_letter(self):
        registration = CORPORA['pg2397']
        retriever = HybridLibrarian(embedding_model=ConstantEmbedding(), reranker=TermReranker())
        for part_id, chapter_max, exact_id in (
            ('main', 1, None), ('part-iii', 1, None),
            ('letters', None, 'pg2397-vb3cc1e13-sec027'),
            ('letters', None, 'pg2397-vb3cc1e13-sec028'),
        ):
            scope = BookScope(work_id='pg2397', book_version_id=registration.book.book_version_id,
                              chapter_max=chapter_max, part_id=part_id, unit_ids=(exact_id,) if exact_id else ())
            result = retriever.retrieve(LibrarianRequest(query='Helen book dear', book_scopes=[scope]))
            self.assertTrue(result.items)
            self.assertTrue(all(item.part_id == part_id for item in result.items))
            if exact_id:
                self.assertTrue(all(item.chapter_id == exact_id for item in result.items))

    def test_wrong_part_or_unit_is_rejected_before_opening_body(self):
        for scope in (
            BookScope(work_id='pg23', book_version_id=CORPORA['pg23'].book.book_version_id, chapter_max=1, part_id='part-iii'),
            BookScope(work_id='pg23', book_version_id=CORPORA['pg23'].book.book_version_id, unit_ids=('pg2397-vb3cc1e13-sec027',), part_id='letters'),
            BookScope(work_id='pg23', book_version_id=CORPORA['pg23'].book.book_version_id, unit_ids=('pg23-vd3f08ac3-sec01',), part_id='main'),
        ):
            with self.subTest(scope=scope):
                original = Path.read_text
                def metadata_only(path, *args, **kwargs):
                    self.assertEqual('catalog.json', path.name)
                    return original(path, *args, **kwargs)
                with patch.object(Path, 'read_text', autospec=True, side_effect=metadata_only):
                    with self.assertRaises(CorpusScopeError):
                        Librarian().retrieve(LibrarianRequest(query='book', book_scopes=[scope]))
