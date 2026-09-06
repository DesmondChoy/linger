"""The chapter runtime must reject section metadata before returning evidence."""

import json
from pathlib import Path

import pytest

from apps.backend.contracts import BookScope, LibrarianRequest
from apps.backend.librarian import Librarian
from src.linger.corpus import registry
from src.linger.corpus.alice import BOOK
from src.linger.corpus.book import CorpusBuildError, initialise_corpus
from src.linger.corpus.registry import CorpusRegistration


def test_chapter_retrieval_rejects_section_file_under_chapter_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / BOOK.book_version_id
    initialise_corpus(BOOK, output=root)
    path = root / "chapters/01-down-the-rabbit-hole.md"
    encoded, body = path.read_text(encoding="utf-8")[4:].split("\n---\n\n", 1)
    metadata = json.loads(encoded)
    metadata["schema_version"] = 2
    metadata["section_id"] = metadata.pop("chapter_id").replace("-ch01", "-sec01")
    metadata["section_number"] = metadata.pop("chapter_number")
    path.write_text(
        "---\n" + json.dumps(metadata) + "\n---\n\n" + body, encoding="utf-8",
    )
    monkeypatch.setattr(registry, "CORPORA", {
        BOOK.work_id: CorpusRegistration(book=BOOK, root=root),
    })
    request = LibrarianRequest(
        query="rabbit hole",
        book_scopes=[BookScope(
            work_id=BOOK.work_id,
            book_version_id=BOOK.book_version_id,
            chapter_max=1,
        )],
        retrieval_score_threshold=0.5,
    )

    with pytest.raises(CorpusBuildError):
        Librarian().retrieve(request)
