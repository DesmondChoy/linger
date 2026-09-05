"""Small catalogue fixtures for identity and routing tests."""

import hashlib
import json
from pathlib import Path

from src.linger.corpus.book import BookCorpus
from src.linger.corpus.registry import CorpusRegistration


def fake_registration(tmp_path: Path, *, work_id: str, catalog: dict) -> CorpusRegistration:
    sha = hashlib.sha256(work_id.encode()).hexdigest()
    book_version_id = f"{work_id}-v{sha[:8]}"
    root = tmp_path / book_version_id
    root.mkdir()
    catalog = {**catalog, "work_id": work_id, "book_version_id": book_version_id}
    (root / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    book = BookCorpus(
        work_id=work_id,
        book_version_id=book_version_id,
        title=catalog.get("title", work_id),
        author=catalog.get("author", "Test Author"),
        source_path="fake.txt",
        source_sha256=sha,
        default_source=root / "source.txt",
        default_output=root,
        parse_source=lambda _path: (),
    )
    return CorpusRegistration(book=book, root=root)
